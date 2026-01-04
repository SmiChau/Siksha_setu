from django.db import models
from django.conf import settings

class TeacherMessage(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='sent_teacher_messages'
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='received_teacher_messages'
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Message from {self.sender.email} to {self.teacher.email}"


class ContactMessage(models.Model):
    ENQUIRY_CHOICES = [
        ('GENERAL', 'General Enquiry'),
        ('TEACHER', 'Teacher Enquiry'),
    ]

    enquiry_type = models.CharField(max_length=10, choices=ENQUIRY_CHOICES, default='GENERAL')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contact_messages'
    )
    full_name = models.CharField(max_length=255, default='')
    email = models.EmailField(default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    subject = models.CharField(max_length=255, default='')
    message = models.TextField(default='')
    
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'teacher'},
        related_name='contact_teacher_enquiries'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.enquiry_type}: {self.subject} by {self.email}"


class InstructorApplication(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instructor_applications'
    )
    full_name = models.CharField(max_length=255, default='')
    email = models.EmailField(default='')
    phone = models.CharField(max_length=20, default='')
    expertise = models.CharField(max_length=255, default='')
    experience = models.PositiveIntegerField(help_text="Years of experience", default=0)
    cv = models.FileField(upload_to='instructor_cvs/')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Application: {self.full_name} ({self.status})"
