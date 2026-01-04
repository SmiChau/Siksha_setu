from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text='FontAwesome icon class')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Course(models.Model):
    LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('all', 'All Levels'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Review'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField()
    short_description = models.CharField(max_length=500, blank=True)
    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)
    thumbnail_url = models.URLField(blank=True, help_text='External thumbnail URL')
    
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courses_created'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='courses'
    )
    
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='beginner')
    language = models.CharField(max_length=50, default='English')
    
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_free = models.BooleanField(default=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False)
    
    total_duration = models.PositiveIntegerField(default=0, help_text='Total duration in minutes')
    
    views_count = models.PositiveIntegerField(default=0)
    enrollment_count = models.PositiveIntegerField(default=0)
    
    what_you_learn = models.JSONField(default=list, blank=True, help_text='List of learning outcomes')
    requirements = models.JSONField(default=list, blank=True, help_text='List of requirements')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_featured']),
            models.Index(fields=['category', 'level']),
        ]
    
    def __str__(self):
        return self.title
    
    def get_thumbnail(self):
        if self.thumbnail:
            return self.thumbnail.url
        return self.thumbnail_url or '/static/core/img/default-course.jpg'
    
    def get_average_rating(self):
        from reviews.models import Review
        reviews = Review.objects.filter(course=self)
        if reviews.exists():
            return round(reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return 0
    
    def get_total_lessons(self):
        return self.lessons.count()
    
    def get_completion_rate(self):
        if self.enrollment_count == 0:
            return 0
        completed = Enrollment.objects.filter(course=self, is_completed=True).count()
        return round((completed / self.enrollment_count) * 100, 1)
    
    def calculate_weighted_score(self):
        rating = self.get_average_rating()
        enrollments = self.enrollment_count
        completion_rate = self.get_completion_rate()
        
        w_rating = 0.4
        w_enrollments = 0.3
        w_completion = 0.3
        
        normalized_enrollments = min(enrollments / 1000, 1)
        normalized_completion = completion_rate / 100
        normalized_rating = rating / 5
        
        score = (w_rating * normalized_rating + 
                 w_enrollments * normalized_enrollments + 
                 w_completion * normalized_completion)
        return round(score * 100, 2)
    
    def calculate_trending_score(self):
        from datetime import datetime
        age_hours = (timezone.now() - self.created_at).total_seconds() / 3600
        gravity = 1.8
        
        interactions = self.views_count + (self.enrollment_count * 5)
        
        if age_hours < 1:
            age_hours = 1
        
        score = interactions / pow(age_hours + 2, gravity)
        return round(score, 4)
    
    def save(self, *args, **kwargs):
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        if self.price > 0:
            self.is_free = False
        else:
            self.is_free = True
        super().save(*args, **kwargs)


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    
    youtube_video_id = models.CharField(
        max_length=20,
        blank=True,
        help_text='YouTube video ID (e.g., dQw4w9WgXcQ)'
    )
    video_duration = models.PositiveIntegerField(default=0, help_text='Duration in minutes')
    
    is_preview = models.BooleanField(default=False, help_text='Can be viewed without enrollment')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order']
        unique_together = ['course', 'order']
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    def get_youtube_embed_url(self):
        if self.youtube_video_id:
            return f"https://www.youtube.com/embed/{self.youtube_video_id}?rel=0&modestbranding=1"
        return None


class LessonResource(models.Model):
    RESOURCE_TYPE_CHOICES = [
        ('pdf', 'PDF Document'),
        ('doc', 'Word Document'),
        ('link', 'External Link'),
        ('other', 'Other'),
    ]
    
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='resources')
    title = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPE_CHOICES, default='pdf')
    file = models.FileField(upload_to='lesson_resources/', blank=True, null=True)
    external_url = models.URLField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.lesson.title} - {self.title}"
    
    def get_resource_url(self):
        if self.file:
            return self.file.url
        return self.external_url


class MCQQuestion(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='mcq_questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_option = models.CharField(
        max_length=1,
        choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')]
    )
    explanation = models.TextField(blank=True, help_text='Explanation for the correct answer')
    order = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"Q: {self.question_text[:50]}..."


class Enrollment(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    progress_percentage = models.FloatField(default=0.0)
    
    mcq_score = models.FloatField(default=0.0, help_text='MCQ score percentage')
    overall_score = models.FloatField(default=0.0, help_text='Overall course score')
    
    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']
    
    def __str__(self):
        return f"{self.student.email} - {self.course.title}"
    
    def calculate_progress(self):
        total_lessons = self.course.lessons.count()
        if total_lessons == 0:
            return 0
        
        completed_lessons = LessonProgress.objects.filter(
            enrollment=self,
            is_completed=True
        ).count()
        
        return round((completed_lessons / total_lessons) * 100, 1)
    
    def calculate_mcq_score(self):
        from django.db.models import Avg
        lesson_ids = self.course.lessons.values_list('id', flat=True)
        
        attempts = MCQAttempt.objects.filter(
            enrollment=self,
            question__lesson_id__in=lesson_ids
        )
        
        if not attempts.exists():
            return 0
        
        correct = attempts.filter(is_correct=True).count()
        total = attempts.count()
        
        return round((correct / total) * 100, 1) if total > 0 else 0
    
    def calculate_overall_score(self):
        video_progress = self.progress_percentage
        mcq_score = self.mcq_score
        
        overall = (video_progress * 0.5) + (mcq_score * 0.5)
        return round(overall, 1)
    
    def check_completion(self):
        self.progress_percentage = self.calculate_progress()
        self.mcq_score = self.calculate_mcq_score()
        self.overall_score = self.calculate_overall_score()
        
        if (self.progress_percentage >= 100 and 
            self.mcq_score >= 60 and 
            self.overall_score >= 80):
            self.is_completed = True
            self.completed_at = timezone.now()
        
        self.save()
        return self.is_completed
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            Course.objects.filter(pk=self.course_id).update(
                enrollment_count=models.F('enrollment_count') + 1
            )


class LessonProgress(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='lesson_progress'
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='progress_records'
    )
    
    is_completed = models.BooleanField(default=False)
    watch_time = models.PositiveIntegerField(default=0, help_text='Watch time in seconds')
    last_position = models.PositiveIntegerField(default=0, help_text='Last video position in seconds')
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['enrollment', 'lesson']
    
    def __str__(self):
        return f"{self.enrollment.student.email} - {self.lesson.title}"
    
    def mark_completed(self):
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = timezone.now()
            self.save()
            self.enrollment.check_completion()


class MCQAttempt(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='mcq_attempts'
    )
    question = models.ForeignKey(
        MCQQuestion,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    selected_option = models.CharField(max_length=1)
    is_correct = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['enrollment', 'question']
    
    def __str__(self):
        return f"{self.enrollment.student.email} - Q{self.question.id}"
    
    def save(self, *args, **kwargs):
        self.is_correct = self.selected_option.upper() == self.question.correct_option
        super().save(*args, **kwargs)
