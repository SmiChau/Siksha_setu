from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Avg, Count
from django.core.paginator import Paginator
from django.utils.text import slugify

from .models import (
    Category, Course, Lesson, LessonResource, 
    MCQQuestion, Enrollment, LessonProgress, MCQAttempt
)
from reviews.models import Review, Certificate
from payments.models import Payment
from django.db.models import OuterRef, Subquery, DecimalField, Sum, Value, Max
from django.db.models.functions import Coalesce
from core.models import TeacherMessage


def course_list_view(request):
    """
    Main view for the course catalog.
    
    ACADEMIC JUSTIFICATION:
    1. **Dynamic Category Fetching**: We fetch only categories that have at least one 
       published course to prevent "Empty Result" states in the UI, ensuring a 
       high-integrity browsing experience.
    2. **Server-Side Filtering**: Filtering at the database level (ORM) is significantly 
       more performant than client-side for growing datasets.
    3. **SEO Friendly URLs**: Using query parameters (?category=slug) allows 
       search engines to index filtered views independently.
    """
    courses = Course.objects.filter(status='published').select_related('instructor', 'category')
    
    # Only show categories that actually have live courses
    categories = Category.objects.filter(courses__status='published').distinct()
    
    category_slug = request.GET.get('category')
    level = request.GET.get('level')
    price_filter = request.GET.get('price')
    query = request.GET.get('q')
    sort = request.GET.get('sort', 'popular')
    
    # Search logic (Combined with category filter)
    if query:
        courses = courses.filter(
            Q(title__icontains=query) |
            Q(category__name__icontains=query)
        )
    
    # Category Filtering
    selected_category_obj = None
    if category_slug:
        courses = courses.filter(category__slug=category_slug)
        selected_category_obj = Category.objects.filter(slug=category_slug).first()

    if level:
        courses = courses.filter(level=level)
    if price_filter == 'free':
        courses = courses.filter(is_free=True)
    elif price_filter == 'paid':
        courses = courses.filter(is_free=False)
    
    # Sorting
    if sort == 'newest':
        courses = courses.order_by('-created_at')
    elif sort == 'rating':
        courses = courses.annotate(avg_rating=Avg('reviews__rating')).order_by('-avg_rating')
    elif sort == 'price_low':
        courses = courses.order_by('price')
    elif sort == 'price_high':
        courses = courses.order_by('-price')
    else:
        # Default: Momentum/Weighted Score
        courses = sorted(courses, key=lambda c: c.calculate_weighted_score(), reverse=True)
    
    paginator = Paginator(courses, 12)
    page = request.GET.get('page', 1)
    courses = paginator.get_page(page)
    
    context = {
        'courses': courses,
        'categories': categories,
        'selected_category': category_slug,
        'selected_category_obj': selected_category_obj,
        'selected_level': level,
        'selected_price': price_filter,
        'search_query': query,
        'sort': sort,
    }
    return render(request, 'core/course_list.html', context)


def course_detail_view(request, slug):
    if slug in ["manage", "my-courses"]:
        raise Http404("Invalid course slug")

    # Fetch course by slug first
    course = Course.objects.select_related('instructor', 'category').prefetch_related('lessons', 'reviews').filter(slug=slug).first()
    
    if not course:
        raise Http404("No Course matches the given query.")

    # Access Control Logic:
    # 1. Published courses are visible to everyone.
    # 2. Non-published courses (drafts/pending) are only visible to the instructor or superusers.
    is_owner = request.user.is_authenticated and (request.user == course.instructor or request.user.is_superuser)
    
    if course.status != 'published' and not is_owner:
        raise Http404("No Course matches the given query.")
    
    Course.objects.filter(pk=course.pk).update(views_count=course.views_count + 1)
    
    lessons = course.lessons.all()
    
    # Handle Reviews
    user_review = None
    other_reviews = course.reviews.filter(is_approved=True).select_related('user').order_by('-created_at')
    
    if request.user.is_authenticated:
        user_review = other_reviews.filter(user=request.user).first()
        if user_review:
            other_reviews = other_reviews.exclude(user=request.user)
    
    # Enrollment & Progress
    enrollment = None
    lesson_progress = {}
    current_lesson = None
    can_access = False
    
    # Progress Vars
    unit_progress = 0
    quiz_score = 0
    mastery_score = 0
    mastery_status = "In Progress"
    is_mastered = False
    
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
        if enrollment:
            can_access = True
            progress_records = LessonProgress.objects.filter(enrollment=enrollment)
            lesson_progress = {p.lesson_id: p for p in progress_records}
            
            # Recalculate if needed to be fresh
            enrollment.update_scores() 
            unit_progress = enrollment.unit_progress
            quiz_score = enrollment.quiz_score
            mastery_score = enrollment.mastery_score
            is_mastered = enrollment.mastery_score >= 80
            mastery_status = "Mastered" if is_mastered else "In Progress"
            
    # Progressive Unlocking Logic
    # -----------------------------
    # Rule: If video_completed == true AND (quiz_exists == false OR quiz_submitted == true) 
    # -> unlock next lesson and quiz
    
    lessons_data = []
    previous_lesson_ready = True # First lesson is always unlocked
    
    for lesson in lessons:
        progress = lesson_progress.get(lesson.id)
        video_completed = progress.is_completed if progress else False
        quiz_completed = progress.quiz_completed if progress else False
        has_quiz = lesson.mcq_questions.exists()
        
        # Current lesson is unlocked if it's a preview OR if user is enrolled and the previous lesson was "ready"
        if lesson.is_preview:
            is_unlocked = True
        elif enrollment:
            is_unlocked = previous_lesson_ready
        else:
            is_unlocked = False
        
        # Check if THIS lesson is ready to unlock the NEXT one
        current_ready = video_completed and (not has_quiz or quiz_completed)
        
        # Attach to object for template access
        lesson.is_unlocked = is_unlocked
        lesson.video_completed = video_completed
        lesson.quiz_completed = quiz_completed
        lesson.has_quiz_actual = has_quiz
        
        # Resources data
        resources = lesson.resources.all()
        res_data = [{'title': r.title, 'url': r.get_resource_url(), 'type': r.resource_type} for r in resources]
        
        # Duration display
        total_seconds = lesson.total_duration_seconds
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        duration_display = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        
        lessons_data.append({
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description,
            'video_id': lesson.youtube_video_id,
            'video_file_url': lesson.video_file.url if lesson.video_file else None,
            'video_type': 'local' if lesson.video_file else 'youtube',
            'duration': duration_display,
            'duration_seconds': total_seconds, # For calculations
            'is_preview': lesson.is_preview,
            'resources': res_data,
            'is_unlocked': is_unlocked,
            'video_completed': video_completed,
            'quiz_completed': quiz_completed,
            'is_completed': video_completed, # Legacy compatibility
            'watch_time': progress.watch_time if progress else 0,
            'has_quiz': has_quiz,
            'quiz_count': lesson.mcq_questions.count(),
            'questions': [
                {
                    'id': q.id,
                    'text': q.question_text,
                    'options': [
                        {'key': 'A', 'text': q.option_a},
                        {'key': 'B', 'text': q.option_b},
                        {'key': 'C', 'text': q.option_c},
                        {'key': 'D', 'text': q.option_d},
                    ]
                } for q in lesson.mcq_questions.all()
            ]
        })
        
        # Update for next iteration
        previous_lesson_ready = current_ready

    # Set current lesson for initial rendering (first incomplete/unlocked lesson)
    if can_access:
        for l_data in lessons_data:
            if not l_data['video_completed'] and l_data['is_unlocked']:
                current_lesson = lessons.get(id=l_data['id'])
                break
    
    if not current_lesson and lessons.exists():
        current_lesson = lessons.first()

    what_you_learn = course.what_you_learn if isinstance(course.what_you_learn, list) else []
    requirements = course.requirements if isinstance(course.requirements, list) else []
    
    import json
    lessons_json = json.dumps(lessons_data)

    context = {
        'course': course,
        'lessons': lessons,
        'lessons_json': lessons_json, # FOR JS
        'user_review': user_review,
        'other_reviews': other_reviews,
        'enrollment': enrollment,
        'user_enrolled': enrollment is not None,
        'lesson_progress': lesson_progress,
        'current_lesson': current_lesson,
        'can_access': can_access,
        'what_you_learn': what_you_learn,
        'requirements': requirements,
        'average_rating': course.get_average_rating(),
        'total_reviews': course.reviews.filter(is_approved=True).count(),
        
        # WSM Context
        'unit_progress': unit_progress,
        'quiz_score': quiz_score,
        'mastery_score': mastery_score,
        'mastery_status': mastery_status,
        'is_mastered': is_mastered,
        'certificate_unlocked': is_mastered,
        'is_instructor': request.user == course.instructor,
    }
    return render(request, 'core/course_detail.html', context)


@login_required
def enroll_course_view(request, slug):
    course = get_object_or_404(Course, slug=slug, status='published')
    
    if request.user == course.instructor:
        messages.error(request, 'Instructors cannot enroll in their own course.')
        return redirect('courses:course_detail', slug=slug)
    
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot enroll in courses. Please use a student account for enrollment.")
        return redirect('courses:course_detail', slug=slug)
    
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, 'You are already enrolled in this course.')
        return redirect('courses:course_detail', slug=slug)
    
    if course.is_free:
        Enrollment.objects.create(student=request.user, course=course)
        messages.success(request, f'Successfully enrolled in {course.title}!')
        return redirect('courses:course_detail', slug=slug)
    else:
        return redirect('payments:initiate_payment', course_slug=slug)


@login_required
def lesson_view(request, course_slug, lesson_id):
    course = get_object_or_404(Course, slug=course_slug, status='published')
    lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
    
    enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
    
    if not lesson.is_preview and not enrollment:
        messages.error(request, 'Please enroll in this course to access this lesson.')
        return redirect('courses:course_detail', slug=course_slug)
    
    if enrollment:
        lesson_progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson
        )
    else:
        lesson_progress = None
    
    mcq_questions = lesson.mcq_questions.all()
    resources = lesson.resources.all()
    
    all_lessons = course.lessons.all()
    
    mcq_attempts = {}
    if enrollment:
        attempts = MCQAttempt.objects.filter(
            enrollment=enrollment,
            question__in=mcq_questions
        )
        mcq_attempts = {a.question_id: a for a in attempts}
    
    context = {
        'course': course,
        'lesson': lesson,
        'enrollment': enrollment,
        'lesson_progress': lesson_progress,
        'mcq_questions': mcq_questions,
        'resources': resources,
        'all_lessons': all_lessons,
        'mcq_attempts': mcq_attempts,
    }
    return render(request, 'courses/lesson.html', context)


@login_required
@require_POST
def mark_lesson_complete_view(request, course_slug, lesson_id):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)
    
    lesson_progress, created = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson
    )
    
    # Logic Guard: Admin/Staff do not affect progress
    if request.user.is_staff or request.user.is_superuser:
        import json
        return JsonResponse({
            'success': True,
            'unit_progress': enrollment.unit_progress,
            'quiz_score': enrollment.quiz_score,
            'mastery_score': enrollment.mastery_score,
            'mastery_status': "Mastered" if enrollment.mastery_score >= 80 else "In Progress",
            'is_mastered': enrollment.mastery_score >= 80,
            'certificate_unlocked': enrollment.certificate_unlocked,
            'lesson_completed': True,
            'newly_completed': False
        })
    
    import json
    newly_completed = False
    try:
        data = json.loads(request.body)
        # Frontend sends seconds
        watch_seconds = float(data.get('watch_time', 0))
        # Lesson duration in seconds
        video_duration_seconds = lesson.total_duration_seconds
        
        # Incremental update and check for completion
        newly_completed = lesson_progress.update_watch_time(watch_seconds, video_duration_seconds)
    except Exception as e:
        print(f"Error updating watch time: {e}")
        pass

    # Recalculate everything (Time-based logic with 5% steps)
    enrollment.update_scores()
    
    return JsonResponse({
        'success': True,
        'unit_progress': enrollment.unit_progress,
        'quiz_score': enrollment.quiz_score,
        'mastery_score': enrollment.mastery_score,
        'mastery_status': "Mastered" if enrollment.mastery_score >= 80 else "In Progress",
        'is_mastered': enrollment.mastery_score >= 80,
        'certificate_unlocked': enrollment.certificate_unlocked,
        'lesson_completed': lesson_progress.is_completed, # Important for quiz unlocking
        'newly_completed': newly_completed
    })


@login_required
@require_POST
def submit_mcq_answer_view(request, course_slug, lesson_id, question_id):
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
    question = get_object_or_404(MCQQuestion, id=question_id, lesson=lesson)
    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)
    
    selected_option = request.POST.get('option', '').upper()
    
    if selected_option not in ['A', 'B', 'C', 'D']:
        return JsonResponse({'success': False, 'error': 'Invalid option'})
    
    # Logic Guard: Admin/Staff do not affect progress or records
    if request.user.is_staff or request.user.is_superuser:
        return JsonResponse({
            'success': True,
            'is_correct': selected_option == question.correct_option,
            'correct_option': question.correct_option,
            'explanation': question.explanation,
            'mcq_score': enrollment.mcq_score
        })
    
    attempt, created = MCQAttempt.objects.update_or_create(
        enrollment=enrollment,
        question=question,
        defaults={'selected_option': selected_option}
    )
    
    enrollment.check_completion()
    
    return JsonResponse({
        'success': True,
        'is_correct': attempt.is_correct,
        'correct_option': question.correct_option,
        'explanation': question.explanation,
        'mcq_score': enrollment.mcq_score
    })


@login_required
def submit_review_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot submit course reviews.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.user == course.instructor:
        messages.error(request, "Instructors cannot submit reviews on their own course.")
        return redirect('courses:course_detail', slug=course.slug)
    
    # Safe enrollment check
    enrolled = Enrollment.objects.filter(
        student=request.user,
        course=course
    ).exists()

    if not enrolled:
        messages.error(request, "You must be enrolled in this course to submit a review.")
        return redirect('courses:course_detail', slug=course.slug)

    enrollment = Enrollment.objects.get(student=request.user, course=course)
    
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        title = request.POST.get('title', '')
        
        if not rating or not comment:
            messages.error(request, 'Please provide both rating and comment.')
            return redirect('courses:course_detail', slug=course_slug)
        
        review, created = Review.objects.update_or_create(
            user=request.user,
            course=course,
            defaults={
                'rating': int(rating),
                'comment': comment,
                'title': title
            }
        )
        
        if created:
            messages.success(request, 'Thank you for your review!')
        else:
            messages.success(request, 'Your review has been updated.')
        
        if enrollment.is_completed:
            certificate = Certificate.generate_for_enrollment(enrollment)
            if certificate:
                messages.success(request, 'Your certificate is now available!')
        
        return redirect('courses:course_detail', slug=course_slug)
    
    return redirect('courses:course_detail', slug=course_slug)


@login_required
@require_POST
def delete_review_view(request, course_slug, review_id):
    course = get_object_or_404(Course, slug=course_slug)
    review = get_object_or_404(Review, id=review_id, course=course)
    
    # Allow deletion if user is the owner OR is a superuser (admin)
    if request.user == review.user or request.user.is_superuser:
        review.delete()
        messages.success(request, "Review deleted.")
    else:
        messages.error(request, "You are not authorized to delete this review.")
    
    return redirect('courses:course_detail', slug=course_slug)


def get_top_rated_courses(limit=6):
    courses = Course.objects.filter(status='published')
    sorted_courses = sorted(courses, key=lambda c: c.calculate_weighted_score(), reverse=True)
    return sorted_courses[:limit]


def get_trending_courses(limit=6):
    from .utils import get_trending_courses as get_global_trending
    trending_data = get_global_trending(limit)
    return [item['course'] for item in trending_data]


def get_recommended_courses(user, limit=6):
    """
    Algorithm 3: Content-Based Filtering Recommendation Engine
    ----------------------------------------------------------
    ACADEMIC JUSTIFICATION:
    1.  **Why Content-Based?**
        - Operates purely on Item Features (Categories, Tags) and User Profile.
        - Addresses the "Cold Start" problem for new items (unlike Collaborative Filtering).
        - Highly explainable: "Recommended because you liked content X".
    
    2.  **Personalized Learning Support:**
        - Builds a unique 'Interest Profile' for every student based on their enrollment history.
        - Suggests courses that semantically align with what the student has already shown interest in,
          fostering deeper subject mastery.

    3.  **Scalability:**
        - Rule-based and deterministic. O(N*M) complexity where N=Users, M=Courses.
        - Does not require heavy matrix factorization or model training.
        - Can be cached easily per user.

    4.  **Future Extensibility:**
        - This logic creates the feature vectors (User Vector, Item Vector).
        - These vectors can later be fed into Cosine Similarity functions or Neural Networks 
          (e.g., Two-Tower architecture) for advanced ML ranking.

    ALGORITHM STEPS:
    1.  **User Profile Construction**: Aggregate weights from enrolled Categories & Tags.
    2.  **Candidate Selection**: Filter Active Courses NOT already enrolled.
    3.  **Similarity Scoring**: Score = (CategoryWeight * 0.4) + (TagJaccardIndex * 0.6).
    4.  **Ranking**: Sort by Score DESC.
    """
    if not user.is_authenticated:
        return get_top_rated_courses(limit)

    # --- Step 1: Build User Profile ---
    # Fetch all enrolled courses for the user
    # Optimize: Only fetch necessary fields to minimize memory footprint
    enrolled_courses = Course.objects.filter(
        enrollments__student=user
    ).values('id', 'category_id', 'what_you_learn')

    if not enrolled_courses:
        # Cold Start: Fallback to global popularity if user has no history
        return get_top_rated_courses(limit)

    enrolled_ids = set()
    category_counts = {}
    user_tags_set = set()
    total_enrollments = 0

    for item in enrolled_courses:
        enrolled_ids.add(item['id'])
        
        # Category Frequency Analysis
        cat_id = item['category_id']
        if cat_id:
            category_counts[cat_id] = category_counts.get(cat_id, 0) + 1
        
        # Tag Aggregation (using 'what_you_learn' as semantic tags)
        # Assuming 'what_you_learn' is a list of strings
        if item['what_you_learn'] and isinstance(item['what_you_learn'], list):
            for tag in item['what_you_learn']:
                if tag:
                    user_tags_set.add(tag.lower().strip())
        
        total_enrollments += 1

    # Normalize Category Weights (0.0 to 1.0)
    # e.g., If user enrolled in 3 Web Dev and 1 Data Science, Web Dev weight is 0.75
    category_weights = {k: v / total_enrollments for k, v in category_counts.items()}

    # --- Step 2: Candidate Selection ---
    # Fetch all published courses not already enrolled
    # Optimization: select_related for minimal joins later
    candidates = Course.objects.filter(
        status='published'
    ).exclude(
        id__in=enrolled_ids
    ).select_related('category').only('id', 'title', 'category', 'what_you_learn', 'thumbnail', 'price', 'is_free', 'instructor')

    scored_courses = []

    # --- Step 3: Compute Similarity Score ---
    for course in candidates:
        # A. Category Match Score (0.4 Weight)
        # Direct lookup in normalized user interest profile
        cat_score = category_weights.get(course.category_id, 0.0)
        
        # B. Tag Overlap Score (0.6 Weight)
        # Using Jaccard Similarity Index: Intersection / Union
        course_tags = set()
        if course.what_you_learn and isinstance(course.what_you_learn, list):
            course_tags = {t.lower().strip() for t in course.what_you_learn if t}
        
        tag_score = 0.0
        if user_tags_set or course_tags:
            intersection = user_tags_set.intersection(course_tags)
            union = user_tags_set.union(course_tags)
            if union:
                tag_score = len(intersection) / len(union)

        # Final Weighted Score
        # We prioritize Tags (Content) slightly more than broad Categories
        final_score = (cat_score * 0.4) + (tag_score * 0.6)
        
        scored_courses.append((course, final_score))

    # --- Step 4: Rank & Recommend ---
    # Sort by score DESC
    scored_courses.sort(key=lambda x: x[1], reverse=True)
    
    # Extract just the course objects
    recommended = [item[0] for item in scored_courses[:limit]]
    
    # Back-fill with popular courses if recommendation list is too short (Hybrid fallback)
    if len(recommended) < limit:
        top_rated = get_top_rated_courses(limit * 2) # Fetch extra to filter duplicates
        for c in top_rated:
            if len(recommended) >= limit:
                break
            if c.id not in enrolled_ids and c not in recommended:
                recommended.append(c)

    return recommended


@login_required
def my_courses_view(request):
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course', 'course__instructor').order_by('-enrolled_at')
    
    context = {
        'enrollments': enrollments
    }
    return render(request, 'courses/my_courses.html', context)
@login_required
@user_passes_test(lambda u: u.role == 'teacher', login_url='core:home')
def teacher_dashboard_view(request):
    
    # Subquery to calculate revenue for each course
    revenue_subquery = Payment.objects.filter(
        course=OuterRef('pk'),
        status='completed'
    ).values('course').annotate(
        total=Sum('amount')
    ).values('total')
    
    courses = Course.objects.filter(instructor=request.user).annotate(
        enrolled_students=Count('enrollments__student', filter=~Q(enrollments__student__is_staff=True, enrollments__student__is_superuser=True, enrollments__student=request.user), distinct=True),
        avg_rating=Avg('reviews__rating', filter=~Q(reviews__user__is_staff=True, reviews__user__is_superuser=True, reviews__user=request.user)),
        revenue_total=Coalesce(
            Subquery(revenue_subquery, output_field=DecimalField()), 
            Value(0, output_field=DecimalField())
        )
    )
    
    published_count = courses.filter(status='published').count()
    draft_count = courses.filter(status='draft').count()
    
    # Calculate totals from the annotated QuerySet to ensure consistency
    total_students = sum(c.enrolled_students for c in courses)
    total_revenue = sum(c.revenue_total for c in courses)
    
    # Calculate average rating across all courses
    total_rating_sum = 0
    rated_courses_count = 0
    for course in courses:
        r = course.avg_rating or 0
        if r > 0:
            total_rating_sum += r
            rated_courses_count += 1
            
    avg_rating = round(total_rating_sum / rated_courses_count, 1) if rated_courses_count > 0 else 0.0
    # Recent enrollments for this teacher's courses (excluding the instructor)
    recent_enrollments = Enrollment.objects.filter(
        course__instructor=request.user
    ).exclude(student=request.user).select_related('student', 'course').order_by('-enrolled_at')[:10]
    
    # Recent reviews for this teacher's courses (excluding the instructor)
    recent_reviews = Review.objects.filter(
        course__instructor=request.user
    ).exclude(user=request.user).select_related('user', 'course').order_by('-created_at')[:5]
    
    # Messages from students
    messages_received = TeacherMessage.objects.filter(teacher=request.user).order_by('-created_at')
    unread_count = messages_received.filter(is_read=False).count()

    context = {
        'user': request.user,
        'courses': courses,
        'total_courses': courses.count(),
        'published_count': published_count,
        'draft_count': draft_count,
        'total_students': total_students,
        'total_revenue': total_revenue,
        'avg_rating': avg_rating,
        'recent_enrollments': recent_enrollments,
        'recent_reviews': recent_reviews,
        'messages_received': messages_received,
        'unread_count': unread_count,
    }
    return render(request, 'accounts/teacher_dashboard.html', context)

@login_required
def course_create_step1_view(request, slug=None):
    if request.user.role != 'teacher':
        return redirect('core:home')
    
    course = None
    if slug:
        course = get_object_or_404(Course, slug=slug, instructor=request.user)
    
    if request.method == 'POST':
        from .forms import CourseDetailsForm
        form = CourseDetailsForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            course = form.save(commit=False)
            course.instructor = request.user
            course.save()
            messages.success(request, "Step 1: Course details saved.")
            return redirect('courses:course_edit_step2', slug=course.slug)
        else:
            messages.warning(request, "Please correct the errors below to proceed.")
    else:
        from .forms import CourseDetailsForm
        form = CourseDetailsForm(instance=course)
    
    context = {
        'form': form,
        'course': course,
        'step': 1
    }
    return render(request, 'courses/wizard/step1_details.html', context)

@login_required
def course_create_step2_view(request, slug):
    if request.user.role != 'teacher': return redirect('core:home')
    course = get_object_or_404(Course, slug=slug, instructor=request.user)
    
    from .forms import LessonForm
    from django.db.models import Max
    
    # Calculate next available order
    current_max = course.lessons.aggregate(Max('order'))['order__max'] or 0
    next_order = current_max + 1
    
    if request.method == 'POST':
        if 'delete_lesson' in request.POST:
            lesson_id = request.POST.get('delete_lesson')
            lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
            lesson.delete()
            messages.success(request, "Lesson deleted.")
            return redirect('courses:course_edit_step2', slug=course.slug)
        
        form = LessonForm(request.POST, request.FILES)
        if form.is_valid():
            lesson_order = form.cleaned_data.get('order')
            
            # If user left it as default 0 or some value that exists, let's check
            if Lesson.objects.filter(course=course, order=lesson_order).exists():
                form.add_error('order', f"A lesson with order {lesson_order} already exists. Please choose a different order or use the default ({next_order}).")
            else:
                lesson = form.save(commit=False)
                lesson.course = course
                lesson.save()
                messages.success(request, "Lesson added successfully.")
                return redirect('courses:course_edit_step2', slug=course.slug)
    else:
        # Default the order to the next available one
        form = LessonForm(initial={'order': next_order})
    
    lessons = course.lessons.all().order_by('order')
    context = {
        'course': course,
        'lessons': lessons,
        'form': form,
        'step': 2
    }
    return render(request, 'courses/wizard/step2_lessons.html', context)

@login_required
def course_create_step3_view(request, slug):
    if request.user.role != 'teacher': return redirect('core:home')
    course = get_object_or_404(Course, slug=slug, instructor=request.user)
    
    from .forms import LessonResourceForm
    if request.method == 'POST':
        if 'delete_resource' in request.POST:
            resource_id = request.POST.get('delete_resource')
            resource = get_object_or_404(LessonResource, id=resource_id, lesson__course=course)
            resource.delete()
            messages.success(request, "Resource deleted.")
            return redirect('courses:course_edit_step3', slug=course.slug)

        lesson_id = request.POST.get('lesson_id')
        lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
        form = LessonResourceForm(request.POST, request.FILES)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.lesson = lesson
            resource.save()
            messages.success(request, f"Resource added to {lesson.title}.")
            return redirect('courses:course_edit_step3', slug=course.slug)
            
    lessons = course.lessons.all().prefetch_related('resources')
    context = {
        'course': course,
        'lessons': lessons,
        'step': 3
    }
    return render(request, 'courses/wizard/step3_resources.html', context)

@login_required
def course_create_step4_view(request, slug):
    if request.user.role != 'teacher': return redirect('core:home')
    course = get_object_or_404(Course, slug=slug, instructor=request.user)
    
    from .forms import MCQQuestionForm
    from django.http import JsonResponse
    
    if request.method == 'POST':
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('X-CSRFToken')
        
        if 'delete_mcq' in request.POST:
            mcq_id = request.POST.get('delete_mcq')
            mcq = get_object_or_404(MCQQuestion, id=mcq_id, lesson__course=course)
            mcq.delete()
            messages.success(request, "Question deleted.")
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': 'Question deleted successfully'})
            return redirect('courses:course_edit_step4', slug=course.slug)

        lesson_id = request.POST.get('lesson_id')
        lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
        form = MCQQuestionForm(request.POST)
        
        if form.is_valid():
            mcq = form.save(commit=False)
            mcq.lesson = lesson
            mcq.save()
            messages.success(request, f"MCQ added to {lesson.title}.")
            
            if is_ajax:
                return JsonResponse({
                    'success': True, 
                    'message': f'MCQ added to {lesson.title}',
                    'mcq_count': lesson.mcq_questions.count()
                })
            return redirect('courses:course_edit_step4', slug=course.slug)
        else:
            # Form validation failed
            if is_ajax:
                errors = {field: error[0] for field, error in form.errors.items()}
                return JsonResponse({
                    'success': False, 
                    'error': 'Validation failed',
                    'errors': errors
                }, status=400)
            # For non-AJAX, continue to render with errors
            
    lessons = course.lessons.all().prefetch_related('mcq_questions')
    context = {
        'course': course,
        'lessons': lessons,
        'step': 4
    }
    return render(request, 'courses/wizard/step4_mcqs.html', context)

@login_required
def course_create_step5_view(request, slug):
    if request.user.role != 'teacher': return redirect('core:home')
    course = get_object_or_404(Course.objects.prefetch_related('lessons', 'lessons__resources', 'lessons__mcq_questions'), slug=slug, instructor=request.user)
    
    context = {
        'course': course,
        'step': 5
    }
    return render(request, 'courses/wizard/step5_review.html', context)

@login_required
def course_publish_view(request, slug):
    if request.user.role != 'teacher': return redirect('core:home')
    course = get_object_or_404(Course, slug=slug, instructor=request.user)
    
    if course.lessons.count() == 0:
        messages.error(request, "You cannot publish a course without any lessons.")
        return redirect('courses:course_edit_step2', slug=course.slug)
    
    course.status = 'published'
    course.save()
    messages.success(request, f"Congratulations! '{course.title}' is now published.")
    return redirect('courses:teacher_dashboard')

@login_required
def course_delete_view(request, slug):
    if request.user.role != 'teacher': return redirect('core:home')
    course = get_object_or_404(Course, slug=slug, instructor=request.user)
    course.delete()
    messages.success(request, "Course deleted successfully.")
    return redirect('courses:teacher_dashboard')


@login_required
@require_POST
def submit_lesson_quiz_view(request, course_slug, lesson_id):
    """
    Marks a quiz for a specific lesson as completed/submitted.
    """
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)
    
    lesson_progress, created = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson
    )
    
    lesson_progress.quiz_completed = True
    lesson_progress.save()
    
    enrollment.update_scores()
    
    return JsonResponse({
        'success': True,
        'quiz_completed': True,
        'unit_progress': enrollment.unit_progress,
        'quiz_score': enrollment.quiz_score,
        'mastery_score': enrollment.mastery_score,
        'mastery_status': "Mastered" if enrollment.mastery_score >= 80 else "In Progress",
    })

@login_required
@require_POST
def submit_mcq_answer(request, course_slug):
    """
    Handles MCQ submission via JSON Body.
    Expects: { question_id: <int>, selected_option: <str> }
    """
    import json
    try:
        data = json.loads(request.body)
        question_id = data.get('question_id')
        selected_option = data.get('selected_option', '').upper()
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'})

    if not question_id or not selected_option:
        return JsonResponse({'success': False, 'error': 'Missing parameters'})

    course = get_object_or_404(Course, slug=course_slug)
    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)
    question = get_object_or_404(MCQQuestion, id=question_id)
    
    # Verify question belongs to course (via lesson)
    if question.lesson.course != course:
         return JsonResponse({'success': False, 'error': 'Invalid question for this course'})

    if selected_option not in ['A', 'B', 'C', 'D']:
        return JsonResponse({'success': False, 'error': 'Invalid option'})
    
    attempt, created = MCQAttempt.objects.update_or_create(
        enrollment=enrollment,
        question=question,
        defaults={'selected_option': selected_option}
    )
    
    # Update progress and scores
    enrollment.update_scores()
    
    return JsonResponse({
        'success': True,
        'is_correct': attempt.is_correct,
        'correct_option': question.correct_option,
        'explanation': question.explanation,
        'quiz_score': enrollment.quiz_score,
        'unit_progress': enrollment.unit_progress,
        'mastery_score': enrollment.mastery_score,
        'mastery_status': "Mastered" if enrollment.mastery_score >= 80 else "In Progress",
        'certificate_unlocked': enrollment.certificate_unlocked
    })
