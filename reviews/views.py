from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa
import io
import traceback

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
    try:
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
        
        # Prepare context with cleaned data
        context = {
            'certificate': {
                'student_name': certificate.student_name,
                'course_title': certificate.course_title,
                'instructor_name': certificate.instructor_name,
                'completion_date': certificate.issued_at,  # Use issued_at from Certificate model
                'final_score': float(certificate.final_score),  # Ensure it's float
                'certificate_id': certificate.certificate_id,
                'enrollment_id': enrollment.id,
                'ceo_name': 'Siksha Setu Director',
            }
        }
        
        # Generate HTML
        html = render_to_string('reviews/certificate_template.html', context)
        
        # Check for preview mode
        action = request.GET.get('action')
        
        if action == 'preview':
            # Return HTML directly for preview (better for Tailwind/Modern CSS)
            return HttpResponse(html)
            
        # Create PDF response
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="certificate_{certificate.certificate_id}.pdf"'
        
        # Link callback to prevent network requests
        def link_callback(uri, rel):
            return None

        # Create PDF in memory first
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(
            html, 
            dest=pdf_buffer,
            link_callback=link_callback,
            encoding='UTF-8'
        )
        
        if pisa_status.err:
            error_msg = f"PDF generation error: {pisa_status.err}"
            print(error_msg)
            messages.error(request, 'Error generating PDF. Please try again.')
            return redirect('reviews:my_certificates')
        
        # Write PDF to response
        pdf_buffer.seek(0)
        response.write(pdf_buffer.read())
        pdf_buffer.close()
        
        return response
        
    except Exception as e:
        print(f"Certificate download error: {str(e)}")
        print(traceback.format_exc())
        messages.error(request, 'An error occurred while generating the certificate.')
        return redirect('reviews:my_certificates')


@login_required
def my_certificates_view(request):
    certificates = Certificate.objects.filter(
        enrollment__student=request.user
    ).select_related('enrollment__course').order_by('-issued_at')
    
    context = {
        'certificates': certificates
    }
    return render(request, 'reviews/my_certificates.html', context)