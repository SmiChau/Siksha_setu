from django.db import models
from django.conf import settings
import uuid


class Payment(models.Model):
    PAYMENT_GATEWAY_CHOICES = [
        ('khalti', 'Khalti'),
        ('esewa', 'eSewa'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    transaction_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='payments'
    )
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_gateway = models.CharField(max_length=20, choices=PAYMENT_GATEWAY_CHOICES)
    
    gateway_transaction_id = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['course', 'status']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.course.title} - {self.status}"
    
    def mark_completed(self, gateway_transaction_id, gateway_response):
        from django.utils import timezone
        self.status = 'completed'
        self.gateway_transaction_id = gateway_transaction_id
        self.gateway_response = gateway_response
        self.completed_at = timezone.now()
        self.save()
        
        from courses.models import Enrollment
        # Safety Guard: Do not enroll admin users even if payment somehow completes
        if self.user.is_staff or self.user.is_superuser:
            return

        Enrollment.objects.update_or_create(
            student=self.user,
            course=self.course,
            defaults={'is_paid': True}
        )
    
    def mark_failed(self, gateway_response=None):
        self.status = 'failed'
        if gateway_response:
            self.gateway_response = gateway_response
        self.save()


class KhaltiConfig(models.Model):
    public_key = models.CharField(max_length=100)
    secret_key = models.CharField(max_length=100)
    is_test_mode = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Khalti Configuration'
        verbose_name_plural = 'Khalti Configurations'
    
    def __str__(self):
        mode = "Test" if self.is_test_mode else "Live"
        return f"Khalti Config ({mode})"


class EsewaConfig(models.Model):
    merchant_id = models.CharField(max_length=100)
    secret_key = models.CharField(max_length=100)
    is_test_mode = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'eSewa Configuration'
        verbose_name_plural = 'eSewa Configurations'
    
    def __str__(self):
        mode = "Test" if self.is_test_mode else "Live"
        return f"eSewa Config ({mode})"
