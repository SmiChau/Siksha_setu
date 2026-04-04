import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, Http404, FileResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Avg, Count
from django.core.exceptions import PermissionDenied, ValidationError, SuspiciousOperation
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
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
            Q(category__name__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
    
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
    
    # Optimized fetch for all user attempts in this course
    attempts_map = {}
    if enrollment:
        user_attempts = MCQAttempt.objects.filter(enrollment=enrollment).select_related('question')
        attempts_map = {a.question_id: a for a in user_attempts}

    for lesson in lessons:
        progress = lesson_progress.get(lesson.id)
        # Load persisted status
        is_persisted_unlocked = progress.is_unlocked if progress else False
        
        # Self-healing: Repair stale quiz_unlocked flag at course_detail load time too.
        # Covers old records and zero-duration lessons.
        if progress and not quiz_unlocked:
            total_secs = lesson.total_duration_seconds
            if total_secs > 0 and progress.watch_time > 0:
                if (progress.watch_time / total_secs) >= 0.50 or video_completed:
                    quiz_unlocked = True
                    progress.quiz_unlocked = True
                    progress.save(update_fields=['quiz_unlocked'])
            elif total_secs == 0 and progress.watch_time >= 30:
                quiz_unlocked = True
                progress.quiz_unlocked = True
                progress.save(update_fields=['quiz_unlocked'])
        
        # PERSISTENT UNLOCK LOGIC:
        # A lesson is unlocked IF:
        # 1. It is a preview
        # 2. It was already unlocked in the DB (is_persisted_unlocked)
        # 3. The user already completed THIS lesson (video_completed)
        # 4. The whole course is mastered
        # 5. The PREVIOUS lesson was completed (sequential flow)
        
        course_completed = enrollment.is_completed if enrollment else False
        
        if lesson.is_preview:
            is_unlocked = True
        elif enrollment:
            is_unlocked = is_persisted_unlocked or video_completed or course_completed or previous_lesson_ready
            
            # MONOTONIC FIX: If logic says True but DB says False, PERSIST the unlock now.
            if is_unlocked and progress and not progress.is_unlocked:
                progress.is_unlocked = True
                progress.save(update_fields=['is_unlocked'])
        else:
            is_unlocked = False
        
        # Is THIS lesson ready to unlock the NEXT one?
        # Criteria: Video 95%+ watch AND (No quiz EXISTS OR Quiz is completed)
        current_ready = video_completed and (not has_quiz or quiz_completed)
        
        # Attach to object for template access
        lesson.is_unlocked = is_unlocked
        lesson.video_completed = video_completed
        lesson.quiz_unlocked = quiz_unlocked
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
            'video_file_url': f"/courses/lesson/{lesson.id}/stream/" if lesson.video_file else None,
            'video_type': 'local' if lesson.video_file else 'youtube',
            'duration': duration_display,
            'duration_seconds': total_seconds, # For calculations
            'is_preview': lesson.is_preview,
            'resources': res_data,
            'is_unlocked': is_unlocked,
            'video_completed': video_completed,
            'quiz_unlocked': quiz_unlocked,      # ADDED: prevents JS from getting undefined
            'quiz_completed': quiz_completed,
            'is_completed': video_completed, # Legacy compatibility
            'watch_time': progress.watch_time if progress else 0,
            'max_position': progress.max_position if progress else 0,
            'has_quiz': has_quiz,
            'quiz_count': lesson.mcq_questions.count(),
            'questions': [
                {
                    'id': q.id,
                    'text': q.question_text,
                    'user_answer': attempts_map.get(q.id).selected_option if attempts_map.get(q.id) else None,
                    'is_correct': attempts_map.get(q.id).is_correct if attempts_map.get(q.id) else None,
                    'correct_option': q.correct_option,
                    'explanation': q.explanation,
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
    
    # Debug Guard
    print("ROLE:", request.user, "Staff:", request.user.is_staff, "Superuser:", request.user.is_superuser, "Role:", getattr(request.user, 'role', 'N/A'))
    
    # Only true superusers or explicit 'admin' role users are blocked from enrollment
    if request.user.is_superuser or getattr(request.user, 'role', None) == 'admin':
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
        # 1. Fetch current progress
        lesson_progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson
        )

        # 2. Check lesson unlock state (with persistence)
        is_persisted_unlocked = lesson_progress.is_unlocked
        video_completed = lesson_progress.is_completed
        quiz_completed = lesson_progress.quiz_completed
        
        # Determine the Unlock State by checking DB and derived logic (Sequential check)
        previous_lesson_ready = False
        prev_lesson = Lesson.objects.filter(course=course, order__lt=lesson.order).order_by('-order').first()
        if not prev_lesson:
            previous_lesson_ready = True # First lesson is always unlocked
        else:
            prev_p = LessonProgress.objects.filter(enrollment=enrollment, lesson=prev_lesson).first()
            p_v_done = prev_p.is_completed if prev_p else False
            p_q_done = not prev_lesson.mcq_questions.exists() or (prev_p and prev_p.quiz_completed)
            previous_lesson_ready = (p_v_done and p_q_done)

        is_unlocked = (
            lesson.is_preview or 
            is_persisted_unlocked or 
            video_completed or 
            enrollment.is_completed or 
            previous_lesson_ready
        )

        if not is_unlocked and not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "This lesson is locked. Complete the previous lesson and quiz first.")
            return redirect('courses:course_detail', slug=course_slug)
        
        # MONOTONIC REPAIR: If we are here, the lesson IS unlocked. Persist it.
        if not is_persisted_unlocked:
            lesson_progress.is_unlocked = True
            lesson_progress.save(update_fields=['is_unlocked'])

        # --- Self-Healing: Repair stale quiz_unlocked flag on each page load ---
        if not lesson_progress.quiz_unlocked:
            total_secs = lesson.total_duration_seconds
            if total_secs > 0 and lesson_progress.watch_time > 0:
                watch_pct = (lesson_progress.watch_time / total_secs) * 100
                if watch_pct >= 50 or lesson_progress.is_completed:
                    lesson_progress.quiz_unlocked = True
                    lesson_progress.save(update_fields=['quiz_unlocked'])
            elif total_secs == 0 and lesson_progress.watch_time >= 30:
                lesson_progress.quiz_unlocked = True
                lesson_progress.save(update_fields=['quiz_unlocked'])
        # --- End Self-Healing ---

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

        # --- Self-Healing: Auto-complete quiz if all questions are answered ---
        if lesson_progress and not lesson_progress.quiz_completed:
            q_count = mcq_questions.count()
            if q_count > 0 and len(mcq_attempts) >= q_count:
                lesson_progress.quiz_completed = True
                lesson_progress.save(update_fields=['quiz_completed'])
                enrollment.update_scores()  # Reflect new quiz_completed in mastery
                
                # MONOTONIC UNLOCK: If video is also done, unlock next lesson
                if lesson_progress.is_completed:
                    next_lesson = Lesson.objects.filter(course=course, order__gt=lesson.order).order_by('order').first()
                    if next_lesson:
                        nxt_p, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=next_lesson)
                        if not nxt_p.is_unlocked:
                            nxt_p.is_unlocked = True
                            nxt_p.save(update_fields=['is_unlocked'])
        # --- End Self-Healing ---

    
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
@csrf_exempt
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
    
    # Secure Sequential Guard
    if not (request.user.is_staff or request.user.is_superuser):
        # Allow updates if course is completed or lesson is already completed
        if enrollment.is_completed or lesson_progress.is_completed:
            pass
        else:
            prev_lesson = Lesson.objects.filter(course=course, order__lt=lesson.order).order_by('-order').first()
            if prev_lesson:
                prev_p = LessonProgress.objects.filter(enrollment=enrollment, lesson=prev_lesson).first()
                p_v_done = prev_p.is_completed if prev_p else False
                p_q_done = not prev_lesson.mcq_questions.exists() or (prev_p and prev_p.quiz_completed)
                if not p_v_done or not p_q_done:
                     return JsonResponse({'success': False, 'error': 'Complete previous lesson and quiz first.'})

    import json
    newly_completed = False
    try:
        data = json.loads(request.body)
        # Frontend sends segment boundaries [start_time, end_time]
        segment_start = float(data.get('start_time', 0))
        segment_end = float(data.get('end_time', 0))
        # Lesson duration in seconds
        video_duration_seconds = lesson.total_duration_seconds
        
        # Range-merge update and check for completion
        newly_completed = lesson_progress.update_watch_time(
            segment_start, segment_end, video_duration_seconds
        )
    except Exception as e:
        print(f"Error updating watch time: {e}")
        pass

    # MONOTONIC UNLOCK: If this lesson is completed, persistence-unlock the NEXT lesson
    if lesson_progress.is_completed:
        # We need to know if the quiz is also finished for full sequential unlock
        has_quiz = lesson.mcq_questions.exists()
        is_fully_ready = lesson_progress.is_completed and (not has_quiz or lesson_progress.quiz_completed)
        
        if is_fully_ready:
            next_lesson = Lesson.objects.filter(course=course, order__gt=lesson.order).order_by('order').first()
            if next_lesson:
                next_p, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=next_lesson)
                if not next_p.is_unlocked:
                    next_p.is_unlocked = True
                    next_p.save(update_fields=['is_unlocked'])

    return JsonResponse({
        'success': True,
        'unit_progress': enrollment.unit_progress,
        'quiz_score': enrollment.quiz_score,
        'mastery_score': enrollment.mastery_score,
        'mastery_status': "Mastered" if enrollment.mastery_score >= 80 else "In Progress",
        'is_mastered': enrollment.mastery_score >= 80,
        'certificate_unlocked': enrollment.certificate_unlocked,
        'lesson_completed': lesson_progress.is_completed,
        'quiz_unlocked': lesson_progress.quiz_unlocked,
        'quiz_completed': lesson_progress.quiz_completed,  # CRITICAL: prevents JS heartbeat from overwriting True→undefined
        'lesson_unlocked': lesson_progress.is_unlocked,
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
            'mcq_score': enrollment.quiz_score
        })
    
    # Video Threshold Guard (60%)
    progress = LessonProgress.objects.filter(enrollment=enrollment, lesson=lesson).first()
    if not (request.user.is_staff or request.user.is_superuser):
        if not progress or not progress.quiz_unlocked:
            return JsonResponse({'success': False, 'error': 'Watch 50% of the video to unlock this quiz.'})

    attempt, created = MCQAttempt.objects.update_or_create(
        enrollment=enrollment,
        question=question,
        defaults={'selected_option': selected_option}
    )
    
    enrollment.recalculate_progress()
    
    return JsonResponse({
        'success': True,
        'is_correct': attempt.is_correct,
        'correct_option': question.correct_option,
        'explanation': question.explanation,
        'mcq_score': enrollment.quiz_score
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

    # --- Step 1: Build User Interest Profile ---
    enrolled_courses = Course.objects.filter(enrollments__student=user)
    
    if not enrolled_courses.exists():
        # Cold Start: Fallback to global popularity if user has no history
        return get_top_rated_courses(limit)

    # Extract interest signals
    category_ids = enrolled_courses.values_list('category_id', flat=True).distinct()
    
    # We need to import Tag model to query tags associated with enrolled courses
    from .models import Tag
    tag_ids = Tag.objects.filter(courses__in=enrolled_courses).values_list('id', flat=True).distinct()

    # --- Step 2: Database-Level Valid Candidate Selection (Efficient) ---
    recommended = Course.objects.filter(
        status='published'
    ).exclude(
        enrollments__student=user
    ).exclude(
        instructor=user  # Don't recommend own courses if teacher
    ).filter(
        Q(tags__in=tag_ids) |
        Q(category_id__in=category_ids)
    ).annotate(
        # Prioritize courses with more overlapping tags
        tag_match_count=Count('tags', filter=Q(tags__in=tag_ids))
    ).order_by(
        '-tag_match_count', 
        '-created_at'
    ).select_related('category', 'instructor').distinct()[:limit]
    
    # --- Step 3: Fallback Strategy ---
    # If the specialized recommendation yields few results, fill with top-rated
    recommended_list = list(recommended)
    
    if len(recommended_list) < limit:
        top_rated = get_top_rated_courses(limit * 2)
        # Avoid duplicates
        existing_ids = {c.id for c in recommended_list}
        enrolled_ids = set(enrolled_courses.values_list('id', flat=True))
        
        for c in top_rated:
            if len(recommended_list) >= limit:
                break
            if c.id not in existing_ids and c.id not in enrolled_ids and c.instructor != user:
                recommended_list.append(c)
                existing_ids.add(c.id)

    return recommended_list

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
            try:
                course.save()
                messages.success(request, "Step 1: Course details saved.")
                return redirect('courses:course_edit_step2', slug=course.slug)
            except SuspiciousOperation as e:
                messages.error(request, f"File Error: {str(e)}")
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
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
                try:
                    lesson.save()
                    messages.success(request, "Lesson added successfully.")
                    return redirect('courses:course_edit_step2', slug=course.slug)
                except SuspiciousOperation as e:
                    messages.error(request, f"File Error: {str(e)}")
                    # Optionally log the error or redirect back with specific message
                except Exception as e:
                    messages.error(request, f"An unexpected error occurred while saving the lesson: {str(e)}")
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
def get_lesson_data_view(request, lesson_id):
    if request.user.role != 'teacher':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    lesson = get_object_or_404(Lesson, id=lesson_id, course__instructor=request.user)
    data = {
        'id': lesson.id,
        'title': lesson.title,
        'order': lesson.order,
        'duration_minutes': lesson.duration_minutes,
        'duration_seconds': lesson.duration_seconds,
        'description': lesson.description,
        'is_preview': lesson.is_preview,
        'youtube_video_id': lesson.youtube_video_id,
    }
    return JsonResponse(data)

@login_required
def update_lesson_view(request, lesson_id):
    if request.user.role != 'teacher':
        return redirect('core:home')
    
    lesson = get_object_or_404(Lesson, id=lesson_id, course__instructor=request.user)
    from .forms import LessonForm
    
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            # Safe logic: preserve existing video_file if no new file uploaded
            if not request.FILES.get("video_file"):
                form.instance.video_file = lesson.video_file
                
            try:
                form.save()
                messages.success(request, "Lesson updated successfully.")
                return redirect('courses:course_edit_step2', slug=lesson.course.slug)
            except SuspiciousOperation as e:
                messages.error(request, f"File Error: {str(e)}")
            except Exception as e:
                messages.error(request, f"An unexpected error occurred while updating the lesson: {str(e)}")
            return redirect('courses:course_edit_step2', slug=lesson.course.slug)

    return redirect('courses:course_edit_step2', slug=lesson.course.slug)


@login_required
def get_resource_data_view(request, resource_id):
    """Returns JSON data for a LessonResource — used by the Step 3 edit modal."""
    if request.user.role != 'teacher':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    resource = get_object_or_404(LessonResource, id=resource_id, lesson__course__instructor=request.user)
    return JsonResponse({
        'id': resource.id,
        'title': resource.title,
        'resource_type': resource.resource_type,
        'external_url': resource.external_url or '',
        'has_file': bool(resource.file),
        'file_name': resource.file.name.split('/')[-1] if resource.file else '',
    })


@login_required
def update_resource_view(request, resource_id):
    """Updates an existing LessonResource. Preserves existing file if none uploaded."""
    if request.user.role != 'teacher':
        return redirect('core:home')
    resource = get_object_or_404(LessonResource, id=resource_id, lesson__course__instructor=request.user)

    if request.method == 'POST':
        from .forms import LessonResourceForm
        form = LessonResourceForm(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            # Preserve existing file when no new file is uploaded
            if not request.FILES.get('file'):
                form.instance.file = resource.file
            try:
                form.save()
                return JsonResponse({'success': True, 'message': 'Resource updated successfully.'})
            except SuspiciousOperation as e:
                return JsonResponse({'success': False, 'error': f'File Error: {str(e)}'}, status=400)
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
        errors = {field: err[0] for field, err in form.errors.items()}
        return JsonResponse({'success': False, 'error': 'Validation failed.', 'errors': errors}, status=400)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@login_required
def get_mcq_data_view(request, mcq_id):
    """Returns JSON data for an MCQQuestion — used by the Step 4 edit modal."""
    if request.user.role != 'teacher':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    mcq = get_object_or_404(MCQQuestion, id=mcq_id, lesson__course__instructor=request.user)
    return JsonResponse({
        'id': mcq.id,
        'question_text': mcq.question_text,
        'option_a': mcq.option_a,
        'option_b': mcq.option_b,
        'option_c': mcq.option_c,
        'option_d': mcq.option_d,
        'correct_option': mcq.correct_option,
        'explanation': mcq.explanation or '',
        'order': mcq.order,
    })


@login_required
def update_mcq_view(request, mcq_id):
    """Updates an existing MCQQuestion via POST. Returns JSON."""
    if request.user.role != 'teacher':
        return redirect('core:home')
    mcq = get_object_or_404(MCQQuestion, id=mcq_id, lesson__course__instructor=request.user)

    if request.method == 'POST':
        from .forms import MCQQuestionForm
        form = MCQQuestionForm(request.POST, instance=mcq)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True, 'message': 'Question updated successfully.'})
        errors = {field: err[0] for field, err in form.errors.items()}
        return JsonResponse({'success': False, 'error': 'Validation failed.', 'errors': errors}, status=400)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


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
            try:
                resource.save()
                messages.success(request, f"Resource added to {lesson.title}.")
                return redirect('courses:course_edit_step3', slug=course.slug)
            except SuspiciousOperation as e:
                messages.error(request, f"File Error: {str(e)}")
            except Exception as e:
                messages.error(request, f"An unexpected error occurred: {str(e)}")
            
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
    
    if lesson_progress.quiz_completed:
        return JsonResponse({'success': False, 'error': 'Assessment already submitted.'})

    # Self-healing unlock check: use watch_time if quiz_unlocked flag is stale
    if not (request.user.is_staff or request.user.is_superuser):
        total_secs = lesson.total_duration_seconds
        if total_secs > 0:
            watch_pct = (lesson_progress.watch_time / total_secs) * 100
        else:
            watch_pct = 100  # Duration not configured; grant access if any watch time
        is_accessible = (
            lesson_progress.quiz_unlocked
            or lesson_progress.is_completed
            or watch_pct >= 50
            or (total_secs == 0 and lesson_progress.watch_time >= 30)
        )
        if is_accessible and not lesson_progress.quiz_unlocked:
            lesson_progress.quiz_unlocked = True
            lesson_progress.save(update_fields=['quiz_unlocked'])
        if not is_accessible:
            return JsonResponse({'success': False, 'error': 'Watch at least 50% of the video to unlock the quiz.'})
    
    lesson_progress.quiz_completed = True
    lesson_progress.save()
    
    # MONOTONIC UNLOCK: Find next lesson and mark it unlocked in the DB
    if lesson_progress.is_completed:
        next_lesson = Lesson.objects.filter(course=course, order__gt=lesson.order).order_by('order').first()
        if next_lesson:
            next_p, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=next_lesson)
            if not next_p.is_unlocked:
                next_p.is_unlocked = True
                next_p.save(update_fields=['is_unlocked'])

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
    
    # Secure Guard: Video must reach 50% before answering quiz, and quiz must not be completed.
    # Self-healing: If quiz_unlocked flag is stale (old records / missing duration), derive from watch_time.
    progress = LessonProgress.objects.filter(enrollment=enrollment, lesson=question.lesson).first()
    if not (request.user.is_staff or request.user.is_superuser):
        if not progress:
            return JsonResponse({'success': False, 'error': 'Watch the video first to unlock this quiz.'})
        total_secs = question.lesson.total_duration_seconds
        if total_secs > 0:
            watch_pct = (progress.watch_time / total_secs) * 100
        else:
            watch_pct = 100  # Duration not set; grant access if any watch time recorded
        is_accessible = (
            progress.quiz_unlocked
            or progress.is_completed
            or watch_pct >= 50
            or (total_secs == 0 and progress.watch_time >= 30)
        )
        # Self-heal: Persist the flag so future requests skip this computation
        if is_accessible and not progress.quiz_unlocked:
            progress.quiz_unlocked = True
            progress.save(update_fields=['quiz_unlocked'])
        if not is_accessible:
            return JsonResponse({'success': False, 'error': 'Watch at least 50% of the video to unlock this quiz.'})
        if progress.quiz_completed:
            return JsonResponse({'success': False, 'error': 'Quiz already submitted and cannot be modified.'})

    attempt, created = MCQAttempt.objects.update_or_create(
        enrollment=enrollment,
        question=question,
        defaults={'selected_option': selected_option}
    )
    
    # Update progress and scores
    enrollment.update_scores()
    
    # Monotonic auto-completion self-healing
    if progress and not progress.quiz_completed:
        total_questions = MCQQuestion.objects.filter(lesson=question.lesson).count()
        answered = MCQAttempt.objects.filter(enrollment=enrollment, question__lesson=question.lesson).count()
        if answered >= total_questions:
            progress.quiz_completed = True
            progress.save(update_fields=['quiz_completed'])
            
            # If video is also done, unlock next lesson
            if progress.is_completed:
                next_lesson = Lesson.objects.filter(course=course, order__gt=question.lesson.order).order_by('order').first()
                if next_lesson:
                    nxt_p, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=next_lesson)
                    if not nxt_p.is_unlocked:
                        nxt_p.is_unlocked = True
                        nxt_p.save(update_fields=['is_unlocked'])
    
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

def stream_video_view(request, lesson_id):
    """
    Algorithm: High-Performance Native Video Streamer
    -------------------------------------------------
    REASONING:
    - We use FileResponse instead of a custom generator because Django's native 
      implementation in version 3.2+ provides robust support for 'Accept-Ranges'
      and handles '206 Partial Content' automatically.
    - It is more efficient with file handles and handles 'Broken Pipe' errors 
      more gracefully than manual iterators.
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not lesson.video_file:
        raise Http404("No video file found")

    file_path = lesson.video_file.path
    if not os.path.exists(file_path):
        raise Http404("Video file not found on disk")
        
    # Open file in binary mode - FileResponse handles closure automatically
    file_handle = open(file_path, 'rb')
    response = FileResponse(file_handle, content_type='video/mp4')
    
    # Enable seek support
    response['Accept-Ranges'] = 'bytes'
    return response