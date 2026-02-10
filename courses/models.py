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
    likes_count = models.PositiveIntegerField(default=0)
    
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
        # Exclude instructor's own reviews from analytics
        reviews = Review.objects.filter(course=self).exclude(user=self.instructor)
        if reviews.exists():
            return round(reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return 0
    
    def get_total_lessons(self):
        return self.lessons.count()
    
    @property
    def total_duration_display(self):
        from django.db.models import Sum, F
        # Calculate total seconds from all lessons
        total_seconds = sum(lesson.total_duration_seconds for lesson in self.lessons.all())
        
        if total_seconds == 0:
            return "0m"
            
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    
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
        """
        Algorithm 2: Hacker News Gravity Algorithm
        -----------------------------------------
        ACADEMIC JUSTIFICATION:
        1.  **Superiority to Raw Popularity**: Raw popularity (total counts) favors old items. 
            Gravity ensures that a course with 100 enrollments today ranks higher than one 
            with 1000 enrollments from last year.
        2.  **Time Decay**: Prevents dashboard stagnation. It forces new, high-momentum content 
             to the top, reflecting what is trending 'now'.
        3.  **Real-World use**: Platforms like Reddit and Hacker News use this to maintain a 
            fresh front page.
        4.  **Analytics Reliability**: Helps instructors see which of their content is currently 
            gaining traction rather than just lifetime totals.

        FORMULA: score = engagement_score / (time_since_posted_in_hours + 2) ^ 1.5
        ENGAGEMENT_SCORE: (enrollments * 3) + (views * 1) + (likes * 2)
        """
        from django.utils import timezone
        import math
        
        # Calculate time since publish in hours
        # published_at fallback to created_at if not set
        start_time = self.published_at or self.created_at
        age_hours = (timezone.now() - start_time).total_seconds() / 3600
        
        # Step 1: Engagement Score
        engagement_score = (self.enrollment_count * 3) + (self.views_count * 1) + (self.likes_count * 2)
        
        # Step 2 & 3: Gravity Calculation
        # Gravity constant 1.5 ensures moderate time-based decay
        gravity = 1.5
        score = engagement_score / math.pow(age_hours + 2, gravity)
        
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
        help_text='YouTube video ID (e.g., dQw4w9WgXcQ) or full URL'
    )
    video_file = models.FileField(upload_to='lesson_videos/', null=True, blank=True)
    video_duration = models.PositiveIntegerField(default=0, help_text='Duration in minutes (Legacy)')
    duration_minutes = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    
    is_preview = models.BooleanField(default=False, help_text='Can be viewed without enrollment')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_duration_seconds(self):
        calculated = (self.duration_minutes * 60) + self.duration_seconds
        if calculated == 0 and self.video_duration > 0:
            return self.video_duration * 60
        return calculated
    
    class Meta:
        ordering = ['order']
        unique_together = ['course', 'order']
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"

    def clean(self):
        """Sanitize YouTube ID before saving."""
        if self.youtube_video_id:
            import re
            # Regex to catch:
            # - youtube.com/watch?v=ID
            # - youtube.com/embed/ID
            # - youtu.be/ID
            # - youtube.com/v/ID
            # - youtube.com/shorts/ID
            pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
            match = re.search(pattern, self.youtube_video_id)
            if match:
                self.youtube_video_id = match.group(1)
            # If no match but it's 11 chars, assume it's already an ID
            # If not 11 chars and no match, it might be invalid, but we'll leave it 
            # for the frontend error handler or admin validation to catch strictly if needed.
        super().clean()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def get_youtube_embed_url(self):
        if self.youtube_video_id:
            # Using youtube-nocookie.com for privacy and adding enablejsapi=1 for error handling
            return f"https://www.youtube-nocookie.com/embed/{self.youtube_video_id}?rel=0&modestbranding=1&enablejsapi=1"
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
    
    is_paid = models.BooleanField(default=False)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    
    # Simple Mastery Algorithm Fields
    completed_units = models.PositiveIntegerField(default=0, help_text='Number of fully watched videos')
    unit_progress = models.FloatField(default=0.0, help_text='(completed_units / total_units) * 100')
    quiz_score = models.FloatField(default=0.0, help_text='Average quiz performance (0-100)')
    mastery_score = models.FloatField(default=0.0, help_text='(unit_progress * 0.6) + (quiz_score * 0.4)')
    certificate_unlocked = models.BooleanField(default=False)
    
    # Legacy / Compatibility Fields
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']
    
    def __str__(self):
        return f"{self.student.email} - {self.course.title}"
    
    def update_scores(self):
        """
        Implements Time-Based Progress Logic
        1. video_progress = (total_watched_seconds / total_course_seconds) * 100
        2. quantized into 5% steps
        3. mastery_score = (video_progress * 0.6) + (quiz_score * 0.4)
        """
        all_lessons = self.course.lessons.all()
        # Sum duration (minutes + seconds to total seconds) - total course length
        total_seconds = sum([l.total_duration_seconds for l in all_lessons])
        
        # Sum actual cumulative watch time from all lesson progress records
        watched_seconds = LessonProgress.objects.filter(enrollment=self).aggregate(
            total=models.Sum('watch_time'))['total'] or 0
        
        if total_seconds > 0:
            raw_progress = (watched_seconds / total_seconds) * 100
            # 5% Increments Logic: 0%, 5%, 10%, 15%...
            self.unit_progress = (raw_progress // 5) * 5
            self.unit_progress = min(max(self.unit_progress, 0.0), 100.0)
            
            # Count completed videos for UI listing
            self.completed_units = LessonProgress.objects.filter(
                enrollment=self, is_completed=True).count()
        else:
            self.unit_progress = 100.0
            self.completed_units = all_lessons.count()

        # Quiz Score Logic: Average of all questions across the course
        total_q = MCQQuestion.objects.filter(lesson__course=self.course).count()
        if total_q > 0:
            correct_attempts = MCQAttempt.objects.filter(
                enrollment=self,
                is_correct=True
            ).count()
            self.quiz_score = round((correct_attempts / total_q) * 100, 1)
        else:
            self.quiz_score = 100.0
            
        # Weighted Scoring Model
        self.mastery_score = round((self.unit_progress * 0.6) + (self.quiz_score * 0.4), 1)
        
        # Certificate Unlock Logic (>= 80%)
        if self.mastery_score >= 80:
            self.certificate_unlocked = True
            self.is_completed = True
            if not self.completed_at:
                self.completed_at = timezone.now()
        else:
            self.certificate_unlocked = False
            self.is_completed = False

        self.save()
        return self.mastery_score
    
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
    quiz_completed = models.BooleanField(default=False)
    watch_time = models.PositiveIntegerField(default=0, help_text='Total cumulative watch time in seconds')
    max_position = models.PositiveIntegerField(default=0, help_text='Furthest position watched')
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['enrollment', 'lesson']
    
    def __str__(self):
        return f"{self.enrollment.student.email} - {self.lesson.title}"
    
    def update_watch_time(self, current_watch_time, video_duration_seconds):
        """
        Server-side validation and incremental watch time update.
        Unlocks quiz when watch threshold (95%) is met for this lesson.
        """
        # Ensure we don't decrease watch time (prevent tracking reset abuse)
        if current_watch_time > self.watch_time:
            # Clamp to duration
            self.watch_time = min(current_watch_time, video_duration_seconds)
            
        # check for completion (95%)
        if not self.is_completed and video_duration_seconds > 0:
            if (self.watch_time / video_duration_seconds) >= 0.95:
                self.is_completed = True
                self.completed_at = timezone.now()
        
        self.save()
        return self.is_completed


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
