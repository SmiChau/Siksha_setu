from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .models import Review, Certificate
from courses.models import Course, Enrollment


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
def certificate_download_view(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('course', 'course__instructor', 'student'),
        id=enrollment_id,
        student=request.user
    )
    
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
    
    certificate = Certificate.generate_for_enrollment(enrollment)
    
    if not certificate:
        messages.error(request, 'Unable to generate certificate.')
        return redirect('courses:course_detail', slug=enrollment.course.slug)
    
    html_content = render_to_string('reviews/certificate_template.html', {
        'certificate': certificate
    })
    
    response = HttpResponse(html_content, content_type='text/html')
    response['Content-Disposition'] = f'inline; filename="certificate_{certificate.certificate_id}.html"'
    return response


@login_required
def my_certificates_view(request):
    certificates = Certificate.objects.filter(
        enrollment__student=request.user
    ).select_related('enrollment__course').order_by('-issued_at')
    
    context = {
        'certificates': certificates
    }
    return render(request, 'reviews/my_certificates.html', context)
