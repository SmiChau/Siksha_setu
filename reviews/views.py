from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_sameorigin
import traceback

from .models import Review, Certificate
from courses.models import Enrollment


def certificate_verify_view(request):
    certificate_id = request.GET.get('id', '')
    certificate = None
    
    if certificate_id:
        certificate = Certificate.verify_certificate(certificate_id)
    
    context = {
        'certificate': certificate,
        'certificate_id': certificate_id,
    }
    return render(request, 'reviews/certificate_verify.html', context)


@login_required
@xframe_options_sameorigin
def certificate_download_view(request, enrollment_id):
    try:
        # 1. Safeguards - Verify Enrollment and Eligibility
        enrollment = Enrollment.objects.select_related(
            'course', 'course__instructor', 'student'
        ).filter(id=enrollment_id, student=request.user).first()

        if not enrollment:
            messages.error(request, "Enrollment record not found.")
            return redirect('reviews:my_certificates')
        
        if request.user.is_staff or request.user.is_superuser:
            messages.warning(request, "Admin accounts cannot generate certificates.")
            return redirect('courses:course_detail', slug=enrollment.course.slug)
        
        if request.user == enrollment.course.instructor:
            messages.error(request, "Instructors cannot generate certificates for their own courses.")
            return redirect('courses:course_detail', slug=enrollment.course.slug)

        if not enrollment.is_completed:
            messages.error(request, 'You must complete the course to download the certificate.')
            return redirect('courses:course_detail', slug=enrollment.course.slug)
        
        has_review = Review.objects.filter(
            course=enrollment.course,
            user=request.user
        ).exists()
        
        if not has_review:
            messages.error(request, 'Please submit a review before downloading your certificate.')
            return redirect('courses:course_detail', slug=enrollment.course.slug)
        
        # 2. Get or Generate Certificate
        certificate = Certificate.generate_for_enrollment(enrollment)
        if not certificate:
            messages.error(request, 'You are not yet eligible for this certificate.')
            return redirect('courses:course_detail', slug=enrollment.course.slug)
        
        # 3. Get action parameter
        action = request.GET.get('action', '')
        auto = request.GET.get('auto') == '1'
        
        # 4. Context Preparation
        context = {
            'student_name': certificate.student_name,
            'course_name': certificate.course_title,
            'course_title': certificate.course_title,
            'instructor_name': certificate.instructor_name,
            'completion_date': certificate.completion_date,
            'final_score': float(certificate.final_score),
            'certificate_id': certificate.certificate_id,
            'platform_name': 'SIKSHA SETU',
            'signature_name': 'Siksha Setu Team',
            'is_preview': (action == 'preview'),
            'auto_print': auto
        }
        
        # 5. Handle different actions
        if action == 'preview':
            html = render_to_string('reviews/certificate_template.html', context, request=request)
            return HttpResponse(html)
        
        if action == 'pdf':
            html = render_to_string('reviews/certificate_print.html', context, request=request)
            return HttpResponse(html)
        
        # Default - show certificate page with download button
        html = render_to_string('reviews/certificate_print.html', context, request=request)
        return HttpResponse(html)
        
    except Exception as e:
        print(f"Certificate download error: {str(e)}")
        print(traceback.format_exc())
        messages.error(request, 'An error occurred while generating the certificate.')
        return redirect('reviews:my_certificates')


@login_required
def my_certificates_view(request):
    if request.user.is_staff or request.user.is_superuser:
        return render(request, 'reviews/my_certificates.html', {'certificates': []})

    certificates = Certificate.objects.filter(
        enrollment__student=request.user
    ).select_related('enrollment__course').order_by('-issued_at')
    
    context = {
        'certificates': certificates
    }
    return render(request, 'reviews/my_certificates.html', context)