from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Avg, Sum, Max, Q
from django.db import models
from django.utils.text import slugify
from datetime import timedelta
import random
import string
import json

from .models import CustomUser, OTP, TeacherProfile
from .forms import SignupForm, OTPVerificationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm, TeacherProfileForm
from courses.models import Course, Category, Enrollment, Lesson, LessonResource, MCQQuestion, LessonProgress
from core.models import TeacherMessage
from reviews.models import Review, Certificate
from payments.models import Payment


def generate_otp():
    return ''.join(random.choices(string.digits, k=6))


def send_otp_email(email, otp_code):
    subject = 'Siksha Setu - Email Verification OTP'
    message = f'''
Hello,

Thank you for signing up with Siksha Setu!

Your OTP for email verification is: {otp_code}

This OTP will expire in 10 minutes.

If you did not create an account with Siksha Setu, please ignore this email.

Best regards,
Siksha Setu Team
'''
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_password_reset_otp_email(email, otp_code):
    subject = 'Siksha Setu - Password Reset OTP'
    message = f'''
Hello,

You have requested to reset your password for your Siksha Setu account.

Your OTP for password reset is: {otp_code}

This OTP will expire in 10 minutes.

If you did not request a password reset, please ignore this email.

Best regards,
Siksha Setu Team
'''
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


@never_cache
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    
    if request.method == 'POST':
        form = SignupForm(request.POST)
        role = request.POST.get('role', 'student')
        
        if form.is_valid():
            signup_data = form.cleaned_data.copy()
            signup_data['role'] = role
            request.session['signup_data'] = signup_data
            
            otp_code = generate_otp()
            request.session['signup_otp'] = otp_code
            request.session.set_expiry(600)
            
            email = form.cleaned_data['email']
            email_sent = send_otp_email(email, otp_code)
            
            if email_sent:
                messages.success(
                    request,
                    f'Account details accepted! An OTP has been sent to {email}. '
                    'Please verify your email to complete registration.'
                )
                return redirect('accounts:verify_otp')
            else:
                messages.error(
                    request,
                    'Failed to send OTP email. Please check your email address.'
                )
    else:
        form = SignupForm()
    
    return render(request, 'accounts/auth.html', {'form': form, 'mode': 'signup', 'login_form': LoginForm()})


@never_cache
def verify_otp_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    
    signup_data = request.session.get('signup_data')
    session_otp = request.session.get('signup_otp')
    
    if not signup_data or not session_otp:
        messages.error(request, 'Session expired or invalid. Please sign up again.')
        return redirect('accounts:signup')
    
    email = signup_data.get('email')
    
    if request.method == 'POST':
        otp_input = request.POST.get('otp')
        
        if otp_input == session_otp:
            try:
                if CustomUser.objects.filter(email=email).exists():
                    messages.error(request, 'User with this email already exists.')
                    return redirect('accounts:signup')
                
                role = signup_data.get('role', 'student')
                
                user = CustomUser.objects.create_user(
                    email=email,
                    password=signup_data['password'],
                    first_name=signup_data.get('first_name', ''),
                    last_name=signup_data.get('last_name', ''),
                )
                user.is_verified = True
                user.is_active = True
                user.role = role
                
                if role == 'teacher':
                    user.is_approved = False
                    messages.info(
                        request,
                        'Your teacher account is pending admin approval. '
                        'You will be notified once approved.'
                    )
                else:
                    user.is_approved = True
                
                user.save()
                
                del request.session['signup_data']
                del request.session['signup_otp']
                
                if role == 'student':
                    login(request, user)
                    messages.success(
                        request,
                        'Email verified successfully! Your account has been created.'
                    )
                    return redirect('accounts:student_dashboard')
                else:
                    return redirect('accounts:login')
                    
            except Exception as e:
                messages.error(request, f'Error creating account: {e}')
                print(f"Signup Error: {e}")
        else:
            messages.error(request, 'Invalid OTP. Please check and try again.')
    
    return render(request, 'accounts/verify_otp.html', {'email': email})


def resend_otp_view(request):
    if request.method == 'POST':
        signup_data = request.session.get('signup_data')
        
        if not signup_data:
            messages.error(request, 'Session expired. Please sign up again.')
            return redirect('accounts:signup')
        
        email = signup_data.get('email')
        
        otp_code = generate_otp()
        request.session['signup_otp'] = otp_code
        request.session.set_expiry(600)
        
        if send_otp_email(email, otp_code):
            messages.success(request, f'New OTP has been sent to {email}.')
        else:
            messages.error(request, 'Failed to send OTP email. Please try again later.')
        
        return redirect('accounts:verify_otp')
    
    return redirect('accounts:verify_otp')


def get_role_redirect_url(user):
    if user.role == 'student':
        return 'accounts:student_dashboard'
    elif user.role == 'teacher':
        if user.is_approved:
            return 'accounts:teacher_dashboard'
        else:
            return 'accounts:pending_approval'
    elif user.role == 'admin' or user.is_staff:
        return 'admin:index'
    else:
        return 'core:home'


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect(get_role_redirect_url(request.user))
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                if not user.is_verified:
                    messages.error(
                        request,
                        'Your email address has not been verified. Please verify your email before logging in.'
                    )
                    return render(request, 'accounts/auth.html', {'login_form': form, 'mode': 'login', 'form': SignupForm()})
                
                if not user.is_active:
                    messages.error(
                        request,
                        'Your account is currently inactive. Please contact support for assistance.'
                    )
                    return render(request, 'accounts/auth.html', {'login_form': form, 'mode': 'login', 'form': SignupForm()})
                
                if user.role == 'teacher' and not user.is_approved:
                    messages.warning(
                        request,
                        'Your teacher account is pending admin approval. Please wait for approval.'
                    )
                    login(request, user)
                    return redirect('accounts:pending_approval')
                
                login(request, user)
                
                remember_me = form.cleaned_data.get('remember_me')
                if remember_me:
                    request.session.set_expiry(1209600)
                else:
                    request.session.set_expiry(0)
                
                messages.success(request, f'Welcome back, {user.get_short_name()}!')
                return redirect(get_role_redirect_url(user))
            else:
                messages.error(
                    request,
                    'Invalid email or password. Please check your credentials and try again.'
                )
    else:
        form = LoginForm()
    
    return render(request, 'accounts/auth.html', {'login_form': form, 'mode': 'login', 'form': SignupForm()})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('core:home')


@login_required
def pending_approval_view(request):
    if request.user.role != 'teacher':
        return redirect(get_role_redirect_url(request.user))
    
    if request.user.is_approved:
        return redirect('accounts:teacher_dashboard')
    
    return render(request, 'accounts/pending_approval.html', {'user': request.user})


@login_required
def student_dashboard_view(request):
    if request.user.role != 'student':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect(get_role_redirect_url(request.user))
    
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course', 'course__instructor', 'course__category').order_by('-enrolled_at')
    
    in_progress = enrollments.filter(is_completed=False)
    completed = enrollments.filter(is_completed=True)
    
    from courses.views import get_recommended_courses
    recommended = get_recommended_courses(request.user, 4)
    
    certificates = Certificate.objects.filter(
        enrollment__student=request.user
    ).select_related('enrollment__course').order_by('-issued_at')[:5]
    
    recent_payments = Payment.objects.filter(
        user=request.user,
        status='completed'
    ).order_by('-completed_at')[:5]
    
    context = {
        'user': request.user,
        'enrollments': enrollments,
        'in_progress': in_progress,
        'completed': completed,
        'recommended_courses': recommended,
        'certificates': certificates,
        'recent_payments': recent_payments,
        'total_courses': enrollments.count(),
        'completed_courses': completed.count(),
    }
    return render(request, 'accounts/student_dashboard.html', context)


@login_required
def teacher_dashboard_view(request):
    if request.user.role != 'teacher':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect(get_role_redirect_url(request.user))
    
    if not request.user.is_approved:
        return redirect('accounts:pending_approval')
    
    courses = Course.objects.filter(
        instructor=request.user
    ).annotate(
        total_students=Count('enrollments'),
        avg_rating=Avg('reviews__rating'),
        total_revenue=Sum('payments__amount', filter=Q(payments__status='completed'))
    ).order_by('-created_at')
    
    total_students = Enrollment.objects.filter(course__instructor=request.user).count()
    total_revenue = Payment.objects.filter(
        course__instructor=request.user,
        status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    avg_rating = Review.objects.filter(
        course__instructor=request.user
    ).aggregate(avg=Avg('rating'))['avg'] or 0
    
    recent_enrollments = Enrollment.objects.filter(
        course__instructor=request.user
    ).select_related('student', 'course').order_by('-enrolled_at')[:10]
    
    recent_reviews = Review.objects.filter(
        course__instructor=request.user
    ).select_related('user', 'course').order_by('-created_at')[:5]
    
    messages_received = TeacherMessage.objects.filter(teacher=request.user).order_by('-created_at')
    unread_count = messages_received.filter(is_read=False).count()
    
    context = {
        'user': request.user,
        'courses': courses,
        'total_courses': courses.count(),
        'total_students': total_students,
        'total_revenue': total_revenue,
        'avg_rating': round(avg_rating, 1),
        'recent_enrollments': recent_enrollments,
        'recent_reviews': recent_reviews,
        'messages_received': messages_received,
        'unread_count': unread_count,
    }
    return render(request, 'accounts/teacher_dashboard.html', context)

@login_required
@require_POST
def mark_message_read(request, message_id):
    message = get_object_or_404(TeacherMessage, id=message_id, teacher=request.user)
    message.is_read = True
    message.save()
    return JsonResponse({'status': 'success'})


@login_required
def create_course_view(request):
    if request.user.role != 'teacher' or not request.user.is_approved:
        messages.error(request, 'You do not have permission to create courses.')
        return redirect(get_role_redirect_url(request.user))
    
    categories = Category.objects.all()
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        short_description = request.POST.get('short_description', '')
        category_id = request.POST.get('category')
        level = request.POST.get('level', 'beginner')
        price = request.POST.get('price', 0)
        thumbnail_url = request.POST.get('thumbnail_url', '')
        
        what_you_learn = request.POST.getlist('what_you_learn[]')
        requirements = request.POST.getlist('requirements[]')
        
        if not title or not description:
            messages.error(request, 'Title and description are required.')
            return render(request, 'accounts/create_course.html', {'categories': categories})
        
        slug = slugify(title)
        counter = 1
        original_slug = slug
        while Course.objects.filter(slug=slug).exists():
            slug = f"{original_slug}-{counter}"
            counter += 1
        
        course = Course.objects.create(
            title=title,
            slug=slug,
            description=description,
            short_description=short_description,
            instructor=request.user,
            category_id=category_id if category_id else None,
            level=level,
            price=float(price) if price else 0,
            thumbnail_url=thumbnail_url,
            what_you_learn=what_you_learn,
            requirements=requirements,
            status='draft'
        )
        
        if 'thumbnail' in request.FILES:
            course.thumbnail = request.FILES['thumbnail']
            course.save()
        
        messages.success(request, f'Course "{title}" created successfully!')
        return redirect('accounts:edit_course', course_id=course.id)
    
    return render(request, 'accounts/create_course.html', {'categories': categories})


@login_required
def edit_course_view(request, course_id):
    course = get_object_or_404(Course, id=course_id, instructor=request.user)
    categories = Category.objects.all()
    lessons = course.lessons.all().order_by('order')
    
    if request.method == 'POST':
        course.title = request.POST.get('title', course.title)
        course.description = request.POST.get('description', course.description)
        course.short_description = request.POST.get('short_description', course.short_description)
        course.category_id = request.POST.get('category') or None
        course.level = request.POST.get('level', course.level)
        course.price = float(request.POST.get('price', 0))
        course.thumbnail_url = request.POST.get('thumbnail_url', course.thumbnail_url)
        
        what_you_learn = request.POST.getlist('what_you_learn[]')
        requirements = request.POST.getlist('requirements[]')
        course.what_you_learn = [item for item in what_you_learn if item]
        course.requirements = [item for item in requirements if item]
        
        if 'thumbnail' in request.FILES:
            course.thumbnail = request.FILES['thumbnail']
        
        course.save()
        messages.success(request, 'Course updated successfully!')
        return redirect('accounts:edit_course', course_id=course.id)
    
    context = {
        'course': course,
        'categories': categories,
        'lessons': lessons,
    }
    return render(request, 'accounts/edit_course.html', context)


@login_required
@require_POST
def add_lesson_view(request, course_id):
    course = get_object_or_404(Course, id=course_id, instructor=request.user)
    
    title = request.POST.get('title')
    description = request.POST.get('description', '')
    youtube_video_id = request.POST.get('youtube_video_id', '')
    video_duration = request.POST.get('video_duration', 0)
    is_preview = request.POST.get('is_preview') == 'on'
    
    max_order = course.lessons.aggregate(Max('order'))['order__max'] or 0
    
    lesson = Lesson.objects.create(
        course=course,
        title=title,
        description=description,
        youtube_video_id=youtube_video_id,
        video_duration=int(video_duration) if video_duration else 0,
        is_preview=is_preview,
        order=max_order + 1
    )
    
    course.total_duration = course.lessons.aggregate(total=Sum('video_duration'))['total'] or 0
    course.save()
    
    messages.success(request, f'Lesson "{title}" added successfully!')
    return redirect('accounts:edit_course', course_id=course.id)


@login_required
@require_POST
def publish_course_view(request, course_id):
    course = get_object_or_404(Course, id=course_id, instructor=request.user)
    
    if course.lessons.count() == 0:
        messages.error(request, 'Please add at least one lesson before publishing.')
        return redirect('accounts:edit_course', course_id=course.id)
    
    course.status = 'published'
    course.save()
    
    messages.success(request, f'Course "{course.title}" published successfully!')
    return redirect('accounts:teacher_dashboard')


@login_required
def profile_view(request):
    user = request.user
    profile = None
    profile_form = None
    
    if user.role == 'teacher':
        # Safely get or create the profile instance
        profile, created = TeacherProfile.objects.get_or_create(user=user)
        profile_form = TeacherProfileForm(instance=profile)

    if request.method == 'POST':
        # Update User model fields
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.bio = request.POST.get('bio', user.bio)
        user.phone = request.POST.get('phone', user.phone)
        
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
        
        user.save()
        
        success = True
        if user.role == 'teacher':
            # Bind form to POST data and current profile instance
            profile_form = TeacherProfileForm(request.POST, request.FILES, instance=profile)
            if profile_form.is_valid():
                # Save using commit=False as requested
                profile_obj = profile_form.save(commit=False)
                profile_obj.user = user
                # Safety guard: ensure languages is never None
                if profile_obj.languages is None:
                    profile_obj.languages = ""
                profile_obj.save()
            else:
                success = False
                messages.error(request, 'Please correct the errors in the professional information section.')
        
        if success:
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    
    context = {
        'user': user,
        'profile_form': profile_form
    }
    return render(request, 'accounts/profile.html', context)


def forgot_password_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                messages.success(
                    request,
                    'If an account exists with this email, a password reset OTP has been sent.'
                )
                return redirect('accounts:forgot_password')
            
            if not user.is_verified:
                messages.error(
                    request,
                    'Your email address has not been verified. Please verify your email first.'
                )
                return render(request, 'accounts/forgot_password.html', {'form': form})
            
            otp_code = generate_otp()
            
            OTP.objects.filter(email=email, is_used=False).update(is_used=True)
            
            otp_obj = OTP.objects.create(
                email=user.email,
                otp_code=otp_code,
                otp_type='password_reset',
                expires_at=timezone.now() + timedelta(minutes=10)
            )
            
            if send_password_reset_otp_email(user.email, otp_code):
                messages.success(
                    request,
                    f'Password reset OTP has been sent to {user.email}. Please check your email.'
                )
                return redirect('accounts:reset_password')
            else:
                messages.error(
                    request,
                    'Failed to send OTP email. Please try again later.'
                )
    else:
        form = ForgotPasswordForm()
    
    return render(request, 'accounts/forgot_password.html', {'form': form})


def reset_password_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            otp_code = form.cleaned_data['otp']
            new_password = form.cleaned_data['new_password']
            
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                messages.error(request, 'No account found with this email address.')
                return render(request, 'accounts/reset_password.html', {'form': form})
            
            if not user.is_verified:
                messages.error(
                    request,
                    'Your email address has not been verified. Please verify your email first.'
                )
                return render(request, 'accounts/reset_password.html', {'form': form})
            
            try:
                otp_obj = OTP.objects.filter(
                    email=email,
                    is_used=False,
                    otp_type='password_reset'
                ).order_by('-created_at').first()
                
                if not otp_obj:
                    messages.error(request, 'No valid OTP found. Please request a new OTP.')
                    return render(request, 'accounts/reset_password.html', {'form': form})
                
                if otp_obj.is_expired():
                    messages.error(request, 'OTP has expired. Please request a new OTP.')
                    return render(request, 'accounts/reset_password.html', {'form': form})
                
                if otp_obj.otp_code == otp_code:
                    otp_obj.is_used = True
                    otp_obj.save()
                    
                    user.set_password(new_password)
                    user.save()
                    
                    sessions = Session.objects.filter(expire_date__gte=timezone.now())
                    for session in sessions:
                        session_data = session.get_decoded()
                        if session_data.get('_auth_user_id') == str(user.id):
                            session.delete()
                    
                    messages.success(
                        request,
                        'Your password has been reset successfully! Please login with your new password.'
                    )
                    return redirect('accounts:login')
                else:
                    messages.error(request, 'Invalid OTP. Please check and try again.')
            
            except Exception as e:
                messages.error(request, 'An error occurred during password reset. Please try again.')
                print(f"Error in password reset: {e}")
    else:
        form = ResetPasswordForm()
    
    return render(request, 'accounts/reset_password.html', {'form': form})


def resend_password_reset_otp_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        if not email:
            messages.error(request, 'Email address is required.')
            return redirect('accounts:reset_password')
        
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return redirect('accounts:reset_password')
        
        if not user.is_verified:
            messages.error(
                request,
                'Your email address has not been verified. Please verify your email first.'
            )
            return redirect('accounts:reset_password')
        
        otp_code = generate_otp()
        
        OTP.objects.filter(email=email, is_used=False).update(is_used=True)
        
        otp_obj = OTP.objects.create(
            email=user.email,
            otp_code=otp_code,
            otp_type='password_reset',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        
        if send_password_reset_otp_email(user.email, otp_code):
            messages.success(request, f'New password reset OTP has been sent to {user.email}.')
        else:
            messages.error(request, 'Failed to send OTP email. Please try again later.')
        
        return redirect('accounts:reset_password')
    
    return redirect('accounts:reset_password')
