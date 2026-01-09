from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Sum, Q

from courses.models import Course, Category, Enrollment
from courses.views import get_top_rated_courses, get_trending_courses, get_recommended_courses
from accounts.models import CustomUser, TeacherProfile
from .models import TeacherMessage, ContactMessage, InstructorApplication
from .forms import TeacherMessageForm, ContactForm, InstructorApplicationForm
from django.contrib import messages


def home(request):
    top_courses = get_top_rated_courses(3)
    trending_courses = get_trending_courses(3)
    categories = Category.objects.annotate(course_count=Count('courses')).order_by('-course_count')[:6]
    
    teachers = CustomUser.objects.filter(
        role='teacher',
        is_approved=True,
        is_active=True
    ).select_related('teacher_profile').annotate(
        course_count=Count('courses_created', filter=Q(courses_created__status='published'), distinct=True)
    ).order_by('-course_count')[:4]
    
    context = {
        'top_courses': top_courses,
        'trending_courses': trending_courses,
        'categories': categories,
        'teachers': teachers,
        'total_students': CustomUser.objects.filter(role='student', is_active=True).count(),
        'total_courses': Course.objects.filter(status='published').count(),
    }
    return render(request, 'core/home_public.html', context)


def course_list(request):
    from courses.views import course_list_view
    return course_list_view(request)


def about(request):
    from reviews.models import Review
    
    total_students = CustomUser.objects.filter(role='student', is_active=True).count()
    total_teachers = CustomUser.objects.filter(role='teacher', is_approved=True, is_active=True).count()
    total_courses = Course.objects.filter(status='published').count()
    total_enrollments = Enrollment.objects.count()
    
    # Fetch real reviews
    active_reviews = Review.objects.filter(
        is_approved=True,
        comment__isnull=False
    ).exclude(
        comment__exact=''
    ).select_related(
        'user', 
        'course'
    ).order_by('-created_at')[:3]
    
    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
        'active_reviews': active_reviews,
    }
    return render(request, 'core/about.html', context)


def teachers(request):
    """
    Public listing of all approved instructors.
    
    ACADEMIC JUSTIFICATION:
    1. **Domain-Specific Discovery**: Allowing users to filter teachers by the 
       category they teach ensures students find specialized mentors quickly.
    2. **Data-Driven UI**: Only categories with active courses are shown to 
       maintain a high-quality user experience.
    """
    category_slug = request.GET.get('category')
    
    # Base query for approved teachers
    teachers_queryset = CustomUser.objects.filter(
        role='teacher',
        is_approved=True,
        is_active=True
    ).select_related('teacher_profile').annotate(
        course_count=Count('courses_created', filter=Q(courses_created__status='published'), distinct=True),
        student_count=Count('courses_created__enrollments'),
        avg_rating=Avg('courses_created__reviews__rating')
    )

    # Fetch categories that have AT LEAST ONE published course by an approved teacher
    categories = Category.objects.filter(
        courses__status='published',
        courses__instructor__is_approved=True,
        courses__instructor__is_active=True
    ).distinct()

    # Apply Category Filter
    selected_category_obj = None
    if category_slug:
        teachers_queryset = teachers_queryset.filter(
            courses_created__category__slug=category_slug,
            courses_created__status='published'
        ).distinct()
        selected_category_obj = Category.objects.filter(slug=category_slug).first()

    teachers_queryset = teachers_queryset.order_by('-course_count')
    
    context = {
        'teachers': teachers_queryset,
        'categories': categories,
        'selected_category': category_slug,
        'selected_category_obj': selected_category_obj,
    }
    return render(request, 'core/teachers.html', context)


def course_detail(request, slug=None):
    from courses.views import course_detail_view
    if slug:
        return course_detail_view(request, slug)
    return redirect('core:course_list')


def contact_view(request):
    # Initialize both forms with basic user context
    form = ContactForm(user=request.user)
    instructor_form = InstructorApplicationForm(user=request.user)
    
    if request.method == 'POST':
        enquiry_type = request.POST.get('enquiry_type')
        
        if enquiry_type == 'instructor':
            instructor_form = InstructorApplicationForm(request.POST, request.FILES, user=request.user)
            # form remains an empty/initial ContactForm
            if instructor_form.is_valid():
                application = instructor_form.save(commit=False)
                if request.user.is_authenticated:
                    application.user = request.user
                application.save()
                messages.success(request, "Your instructor application has been submitted and is under review.")
                return redirect('core:contact')
            else:
                messages.error(request, "Please correct the errors in the instructor application form.")
        else:
            form = ContactForm(request.POST, user=request.user)
            if form.is_valid():
                message = form.save(commit=False)
                if request.user.is_authenticated:
                    message.user = request.user
                message.save()
                messages.success(request, "Your message has been sent successfully!")
                return redirect('core:contact')
            else:
                messages.error(request, "Please correct the errors in the contact form.")
    else:
        # GET logic: handle pre-selected teacher
        teacher_id = request.GET.get('teacher')
        if teacher_id:
            form = ContactForm(user=request.user, initial={
                'teacher': teacher_id,
                'enquiry_type': 'TEACHER'
            })
    
    return render(request, 'core/contact.html', {
        'form': form,
        'instructor_form': instructor_form
    })

@login_required
def send_teacher_message(request, teacher_id):
    if request.method == 'POST':
        teacher = get_object_or_404(CustomUser, id=teacher_id, role='teacher')
        form = TeacherMessageForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.teacher = teacher
            msg.save()
            messages.success(request, f"Message sent to {teacher.get_full_name()} successfully!")
            return redirect('core:teacher_profile', teacher_id=teacher.id)
    return redirect('core:home')


def teacher_profile(request, teacher_id):
    """
    Public profile for a specific instructor.
    
    ACADEMIC JUSTIFICATION:
    1. **Dynamic Content Discovery**: Fetching categories specific to the instructor's 
       body of work ensures that the filter UI is contextually accurate.
    2. **State Persistence**: Using query parameters allows instructors to share 
       links to specific "Collections" of their courses (e.g., all their Marketing courses).
    """
    teacher = get_object_or_404(
        CustomUser.objects.annotate(
            course_count=Count('courses_created', filter=Q(courses_created__status='published'), distinct=True),
            student_count=Count('courses_created__enrollments'),
            avg_rating=Avg('courses_created__reviews__rating')
        ),
        id=teacher_id,
        role='teacher',
        is_approved=True,
        is_active=True
    )
    
    # Get categories where this teacher HAS published courses
    teacher_categories = Category.objects.filter(
        courses__instructor=teacher,
        courses__status='published'
    ).distinct()

    # Filter & Sort Logic
    category_slug = request.GET.get('category')
    sort = request.GET.get('sort', 'newest')
    
    courses = Course.objects.filter(
        instructor=teacher,
        status='published'
    ).select_related('category').annotate(
        avg_rating=Avg('reviews__rating')
    )
    
    if category_slug:
        courses = courses.filter(category__slug=category_slug)
    
    # Sorting
    if sort == 'rating':
        courses = courses.order_by('-avg_rating')
    elif sort == 'price_low':
        courses = courses.order_by('price')
    else:
        courses = courses.order_by('-created_at') # Default to newest
    
    profile, created = TeacherProfile.objects.get_or_create(user=teacher)
    message_form = TeacherMessageForm()
    
    context = {
        'teacher': teacher,
        'profile': profile,
        'courses': courses,
        'categories': teacher_categories,
        'selected_category': category_slug,
        'sort': sort,
        'message_form': message_form,
    }
    return render(request, 'core/teacher_profile.html', context)
