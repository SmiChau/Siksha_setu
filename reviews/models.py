from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class Review(models.Model):
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='Rating from 1 to 5'
    )
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField()
    
    is_approved = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['course', 'user']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.course.title} ({self.rating}/5)"


class Certificate(models.Model):
    certificate_id = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    enrollment = models.OneToOneField(
        'courses.Enrollment',
        on_delete=models.CASCADE,
        related_name='certificate'
    )
    
    student_name = models.CharField(max_length=200)
    course_title = models.CharField(max_length=255)
    instructor_name = models.CharField(max_length=200)
    
    completion_date = models.DateField()
    final_score = models.FloatField()
    
    issued_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-issued_at']
    
    def __str__(self):
        return f"Certificate: {self.student_name} - {self.course_title}"
    
    def save(self, *args, **kwargs):
        if not self.certificate_id:
            self.certificate_id = f"SS-{uuid.uuid4().hex[:8].upper()}-{self.enrollment.course_id}"
        super().save(*args, **kwargs)
    
    @classmethod
    def generate_for_enrollment(cls, enrollment):
        from django.utils import timezone
        
        if not enrollment.is_completed:
            return None
        
        has_review = Review.objects.filter(
            course=enrollment.course,
            user=enrollment.student
        ).exists()
        
        if not has_review:
            return None
        
        if hasattr(enrollment, 'certificate'):
            return enrollment.certificate
        
        certificate = cls.objects.create(
            enrollment=enrollment,
            student_name=enrollment.student.get_full_name(),
            course_title=enrollment.course.title,
            instructor_name=enrollment.course.instructor.get_full_name(),
            completion_date=timezone.now().date(),
            final_score=enrollment.overall_score
        )
        return certificate
    
    @classmethod
    def verify_certificate(cls, certificate_id):
        try:
            return cls.objects.select_related(
                'enrollment__student',
                'enrollment__course',
                'enrollment__course__instructor'
            ).get(certificate_id=certificate_id)
        except cls.DoesNotExist:
            return None
