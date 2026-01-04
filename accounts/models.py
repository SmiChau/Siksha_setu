from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone
from datetime import timedelta
from .managers import CustomUserManager


class CustomUser(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Admin'),
    ]
    
    email = models.EmailField(
        unique=True,
        verbose_name='Email Address',
        help_text='Required. Must be a valid email address.'
    )
    first_name = models.CharField(max_length=100, verbose_name='First Name')
    last_name = models.CharField(max_length=100, verbose_name='Last Name')
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True,
        verbose_name='Profile Picture'
    )
    bio = models.TextField(blank=True, verbose_name='Biography')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Phone Number')
    
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='student',
        verbose_name='User Role'
    )
    is_verified = models.BooleanField(
        default=False,
        verbose_name='Email Verified',
        help_text='Designates whether the user has verified their email address.'
    )
    is_approved = models.BooleanField(
        default=True,
        verbose_name='Approved',
        help_text='For teachers: requires admin approval. Students are auto-approved.'
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='Active',
        help_text='Designates whether this user should be treated as active.'
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name='Staff Status',
        help_text='Designates whether the user can log into the admin site.'
    )
    date_joined = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date Joined'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Last Updated'
    )
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email
    
    def get_short_name(self):
        return self.first_name if self.first_name else self.email.split('@')[0]
    
    def save(self, *args, **kwargs):
        if self.role == 'teacher' and not self.pk:
            self.is_approved = False
        elif self.role == 'student':
            self.is_approved = True
        super().save(*args, **kwargs)


class OTP(models.Model):
    OTP_TYPE_CHOICES = [
        ('signup', 'Signup Verification'),
        ('password_reset', 'Password Reset'),
    ]
    
    email = models.EmailField(
        verbose_name='Email Address',
        db_index=True
    )
    otp_code = models.CharField(
        max_length=6,
        verbose_name='OTP Code'
    )
    otp_type = models.CharField(
        max_length=20,
        choices=OTP_TYPE_CHOICES,
        default='signup'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created At'
    )
    expires_at = models.DateTimeField(
        verbose_name='Expires At'
    )
    is_used = models.BooleanField(
        default=False,
        verbose_name='Is Used',
        help_text='Designates whether this OTP has been used for verification.'
    )
    
    class Meta:
        verbose_name = 'OTP'
        verbose_name_plural = 'OTPs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'is_used']),
        ]
    
    def __str__(self):
        return f'OTP for {self.email}'
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return not self.is_used and not self.is_expired()
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)
class TeacherProfile(models.Model):
    user = models.OneToOneField(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='teacher_profile'
    )
    education = models.TextField(blank=True, verbose_name='Education')
    experience = models.TextField(blank=True, verbose_name='Experience')
    location = models.CharField(max_length=255, blank=True, verbose_name='Location')
    languages = models.CharField(max_length=255, default="", blank=True, verbose_name='Languages')
    
    class Meta:
        verbose_name = 'Teacher Profile'
        verbose_name_plural = 'Teacher Profiles'
    
    def __str__(self):
        return f"Profile of {self.user.email}"
