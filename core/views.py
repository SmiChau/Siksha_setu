from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Sum

from courses.models import Course, Category, Enrollment
from courses.views import get_top_rated_courses, get_trending_courses, get_recommended_courses
from accounts.models import CustomUser, TeacherProfile
from .models import TeacherMessage, ContactMessage
from .forms import TeacherMessageForm, ContactForm
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
        course_count=Count('courses_created')
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
    total_students = CustomUser.objects.filter(role='student', is_active=True).count()
    total_teachers = CustomUser.objects.filter(role='teacher', is_approved=True, is_active=True).count()
    total_courses = Course.objects.filter(status='published').count()
    total_enrollments = Enrollment.objects.count()
    
    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
    }
    return render(request, 'core/about.html', context)


def teachers(request):
    teachers = CustomUser.objects.filter(
        role='teacher',
        is_approved=True,
        is_active=True
    ).select_related('teacher_profile').annotate(
        course_count=Count('courses_created'),
        student_count=Count('courses_created__enrollments'),
        avg_rating=Avg('courses_created__reviews__rating')
    ).order_by('-course_count')
    
    context = {
        'teachers': teachers
    }
    return render(request, 'core/teachers.html', context)


def course_detail(request, slug=None):
    from courses.views import course_detail_view
    if slug:
        return course_detail_view(request, slug)
    return redirect('core:course_list')


def contact_view(request):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.warning(request, "Please login to send a message.")
            return redirect(f"{reverse('accounts:login')}?next={reverse('core:contact')}")
            
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_msg = form.save(commit=False)
            contact_msg.user = request.user
            contact_msg.save()
            messages.success(request, "Your message has been sent to the admin. We will get back to you soon.")
            return redirect('core:home')
    else:
        form = ContactForm()
    
    return render(request, 'core/contact.html', {'form': form})

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
    teacher = get_object_or_404(
        CustomUser.objects.annotate(
            course_count=Count('courses_created'),
            student_count=Count('courses_created__enrollments'),
            avg_rating=Avg('courses_created__reviews__rating')
        ),
        id=teacher_id,
        role='teacher',
        is_approved=True,
        is_active=True
    )
    
    # Get or create TeacherProfile if it doesn't exist (safety check)
    profile, created = TeacherProfile.objects.get_or_create(user=teacher)
    
    courses = Course.objects.filter(
        instructor=teacher,
        status='published'
    ).annotate(
        avg_rating=Avg('reviews__rating')
    )
    
    message_form = TeacherMessageForm()
    
    context = {
        'teacher': teacher,
        'profile': profile,
        'courses': courses,
        'message_form': message_form,
    }
    return render(request, 'core/teacher_profile.html', context)
