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
from .models import (
    Category, Course, Lesson, LessonResource, 
    MCQQuestion, Enrollment, LessonProgress, MCQAttempt
)
from reviews.models import Review, Certificate
from payments.models import Payment
from django.db.models import OuterRef, Subquery, DecimalField, Sum, Value
from django.db.models.functions import Coalesce


def course_list_view(request):
    courses = Course.objects.filter(status='published').select_related('instructor', 'category')
    categories = Category.objects.all()
    
    category_slug = request.GET.get('category')
    level = request.GET.get('level')
    price_filter = request.GET.get('price')
    search = request.GET.get('search')
    sort = request.GET.get('sort', 'popular')
    
    if category_slug:
        courses = courses.filter(category__slug=category_slug)
    if level:
        courses = courses.filter(level=level)
    if price_filter == 'free':
        courses = courses.filter(is_free=True)
    elif price_filter == 'paid':
        courses = courses.filter(is_free=False)
    if search:
        courses = courses.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(instructor__first_name__icontains=search)
        )
    
    if sort == 'newest':
        courses = courses.order_by('-created_at')
    elif sort == 'rating':
        courses = courses.annotate(avg_rating=Avg('reviews__rating')).order_by('-avg_rating')
    elif sort == 'price_low':
        courses = courses.order_by('price')
    elif sort == 'price_high':
        courses = courses.order_by('-price')
    else:
        courses = sorted(courses, key=lambda c: c.calculate_weighted_score(), reverse=True)
    
    paginator = Paginator(courses, 12)
    page = request.GET.get('page', 1)
    courses = paginator.get_page(page)
    
    context = {
        'courses': courses,
        'categories': categories,
        'selected_category': category_slug,
        'selected_level': level,
        'selected_price': price_filter,
        'search_query': search,
        'sort': sort,
    }
    return render(request, 'core/course_list.html', context)


def course_detail_view(request, slug):
    if slug in ["manage", "my-courses"]:
        raise Http404("Invalid course slug")

    # If owner, they can see drafts
    if request.user.is_authenticated and request.user.role == 'teacher':
        course = get_object_or_404(
            Course.objects.select_related('instructor', 'category').prefetch_related('lessons', 'reviews'),
            slug=slug,
            instructor=request.user
        )
    else:
        # Students or public only see published
        course = get_object_or_404(
            Course.objects.select_related('instructor', 'category').prefetch_related('lessons', 'reviews'),
            slug=slug,
            status='published'
        )
    
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
            enrollment.check_completion() 
            unit_progress = enrollment.progress_percentage
            quiz_score = enrollment.mcq_score
            mastery_score = enrollment.overall_score
            is_mastered = enrollment.overall_score >= 80
            mastery_status = "Mastered" if is_mastered else "In Progress"
            
    # Determine current lesson
    if can_access:
        for lesson in lessons:
            if lesson.id not in lesson_progress or not lesson_progress[lesson.id].is_completed:
                current_lesson = lesson
                break
    if not current_lesson and lessons.exists():
        current_lesson = lessons.first()

    what_you_learn = course.what_you_learn if isinstance(course.what_you_learn, list) else []
    requirements = course.requirements if isinstance(course.requirements, list) else []
    
    # Pre-serialize lessons for JS to avoid AJAX calls for simple switching
    # We need resources too
    lessons_data = []
    for lesson in lessons:
        resources = lesson.resources.all()
        res_data = [{'title': r.title, 'url': r.get_resource_url(), 'type': r.resource_type} for r in resources]
        
        is_completed = False
        if enrollment and lesson.id in lesson_progress:
            is_completed = lesson_progress[lesson.id].is_completed
            
        lessons_data.append({
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description,
            'video_id': lesson.youtube_video_id,
            'duration': lesson.video_duration,
            'is_preview': lesson.is_preview,
            'resources': res_data,
            'is_completed': is_completed,
            'has_quiz': lesson.mcq_questions.exists(),
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

    
    import json
    lessons_json = json.dumps(lessons_data)

    context = {
        'course': course,
        'lessons': lessons,
        'lessons_json': lessons_json, # FOR JS
        'user_review': user_review,
        'other_reviews': other_reviews,
        'enrollment': enrollment,
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
    }
    return render(request, 'core/course_detail.html', context)


@login_required
def enroll_course_view(request, slug):
    course = get_object_or_404(Course, slug=slug, status='published')
    
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
    lesson_progress.mark_completed()
    
    return JsonResponse({
        'success': True,
        'progress': enrollment.calculate_progress()
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
    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)
    
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
    courses = Course.objects.filter(status='published')
    sorted_courses = sorted(courses, key=lambda c: c.calculate_trending_score(), reverse=True)
    return sorted_courses[:limit]


def get_recommended_courses(user, limit=6):
    if not user.is_authenticated:
        return get_top_rated_courses(limit)
    
    enrolled_courses = Enrollment.objects.filter(student=user).values_list('course_id', flat=True)
    
    if not enrolled_courses:
        return get_top_rated_courses(limit)
    
    enrolled_categories = Course.objects.filter(
        id__in=enrolled_courses
    ).values_list('category_id', flat=True).distinct()
    
    recommended = Course.objects.filter(
        status='published',
        category_id__in=enrolled_categories
    ).exclude(
        id__in=enrolled_courses
    ).annotate(
        avg_rating=Avg('reviews__rating')
    ).order_by('-avg_rating', '-enrollment_count')[:limit]
    
    if recommended.count() < limit:
        additional = Course.objects.filter(
            status='published'
        ).exclude(
            id__in=enrolled_courses
        ).exclude(
            id__in=[c.id for c in recommended]
        ).order_by('-enrollment_count')[:limit - recommended.count()]
        recommended = list(recommended) + list(additional)
    
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
        enrolled_students=Count('enrollments__student', distinct=True),
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
    # We can't easily aggregate the model method get_average_rating in DB
    # So we do it in python for consistency with the displayed cards if needed, 
    # OR we can keep the separate aggregation if it was working.
    # For now, let's trust the existing aggregation if it exists, or add one.
    # The previous view simplified this. Let's add a robust average rating calculation.
    
    from django.db.models import Avg
    # Re-querying for rating to be safe or iterating. Iterating is fine for dashboard scale.
    # But wait, courses doesn't have rating annotated.
    # Let's annotate rating too for efficiency if we want to display it or sum it?
    # Actually, the table uses course.get_average_rating.
    # The card uses... we need to see what the card used.
    # The template used {{ avg_rating }} but it wasn't passed in context in the snippet I saw!
    # Let's calculate it.
    
    total_rating_sum = 0
    rated_courses_count = 0
    for course in courses:
        r = course.get_average_rating()
        if r > 0:
            total_rating_sum += r
            rated_courses_count += 1
            
    avg_rating = round(total_rating_sum / rated_courses_count, 1) if rated_courses_count > 0 else 0.0

    context = {
        'courses': courses,
        'published_count': published_count,
        'draft_count': draft_count,
        'total_students': total_students,
        'total_revenue': total_revenue,
        'avg_rating': avg_rating,
    }
    return render(request, 'courses/teacher_dashboard.html', context)

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
    if request.method == 'POST':
        if 'delete_lesson' in request.POST:
            lesson_id = request.POST.get('delete_lesson')
            lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
            lesson.delete()
            messages.success(request, "Lesson deleted.")
            return redirect('courses:course_edit_step2', slug=course.slug)
        
        form = LessonForm(request.POST)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.course = course
            lesson.save()
            messages.success(request, "Lesson added successfully.")
            return redirect('courses:course_edit_step2', slug=course.slug)
    else:
        form = LessonForm()
    
    lessons = course.lessons.all()
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
def submit_mcq_answer(request, course_slug):
    import json
    try:
        data = json.loads(request.body)
        question_id = data.get('question_id')
        selected_option = data.get('selected_option')
        
        course = get_object_or_404(Course, slug=course_slug)
        question = get_object_or_404(MCQQuestion, id=question_id, lesson__course=course)
        enrollment = get_object_or_404(Enrollment, student=request.user, course=course)
        
        # Save or update attempt
        attempt, created = MCQAttempt.objects.update_or_create(
            enrollment=enrollment,
            question=question,
            defaults={'selected_option': selected_option}
        )
        
        # Recalculate Course MCQ Score
        total_questions = MCQQuestion.objects.filter(lesson__course=course).count()
        correct_attempts = MCQAttempt.objects.filter(
            enrollment=enrollment, 
            question__lesson__course=course,
            is_correct=True
        ).count()
        
        if total_questions > 0:
            new_mcq_score = (correct_attempts / total_questions) * 100
        else:
            new_mcq_score = 100.0
            
        enrollment.mcq_score = round(new_mcq_score, 1)
        enrollment.save()
        
        enrollment.check_completion()
        
        return JsonResponse({
            'success': True,
            'is_correct': attempt.is_correct,
            'explanation': question.explanation,
            'correct_option': question.correct_option,
            'new_mcq_score': enrollment.mcq_score,
            'mastery_score': enrollment.overall_score,
            'is_mastered': enrollment.overall_score >= 80,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
