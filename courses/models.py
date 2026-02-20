from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
import math


def merge_ranges(ranges):
    """
    Merge overlapping [start, end] ranges into a minimal non-overlapping set.
    Returns sorted, merged list and total unique seconds covered.
    """
    if not ranges:
        return [], 0
    # Sort by start time
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged = [sorted_ranges[0][:]]
    for start, end in sorted_ranges[1:]:
        if start <= merged[-1][1]:
            # Overlapping or adjacent — extend
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    total_seconds = sum(end - start for start, end in merged)
    return merged, total_seconds


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


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

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
    tags = models.ManyToManyField(Tag, blank=True, related_name='courses')
    
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
        # Exclude instructor's own reviews and admin reviews from analytics
        reviews = Review.objects.filter(course=self).exclude(
            Q(user=self.instructor) | Q(user__is_staff=True) | Q(user__is_superuser=True)
        )
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
        completed = Enrollment.objects.filter(
            course=self, 
            is_completed=True,
            student__is_staff=False,
            student__is_superuser=False
        ).count()
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
        
        # Step 1: Engagement Score (Excluding admins)
        # We use real counts to be immune to dummy field manipulation
        actual_enrollments = self.enrollments.filter(student__is_staff=False, student__is_superuser=False).count()
        engagement_score = (actual_enrollments * 3) + (self.views_count * 1) + (self.likes_count * 2)
        
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
    
    def recalculate_progress(self):
        """
        Single source of truth for all progress computation.
        Recomputes from persisted unique watch coverage data.

        Rules:
        - video_progress = floor( (total_unique_seconds / total_course_seconds) * 100 )
        - NEVER decreases (monotonic)
        - mastery_score = (video_progress * 0.6) + (quiz_score * 0.4)
        - mastery_score NEVER decreases
        - certificate_unlocked/is_completed once set is NEVER revoked
        """
        all_lessons = self.course.lessons.all()
        total_course_seconds = sum(l.total_duration_seconds for l in all_lessons)

        # Sum unique watched seconds from all lesson progress records
        progress_records = LessonProgress.objects.filter(enrollment=self)
        total_unique_seconds = sum(lp.watch_time for lp in progress_records)

        # Count completed units
        self.completed_units = progress_records.filter(is_completed=True).count()

        # Compute video progress with 1% floor increments
        if total_course_seconds > 0:
            raw_progress = (total_unique_seconds / total_course_seconds) * 100
            new_progress = float(min(math.floor(raw_progress), 100))
            new_progress = max(new_progress, 0.0)
        else:
            # No lessons or all zero-duration => 100%
            new_progress = 100.0
            self.completed_units = all_lessons.count()

        # All lessons completed => force 100%
        if all_lessons.count() > 0 and self.completed_units == all_lessons.count():
            new_progress = 100.0

        # NEVER DECREASE unit_progress
        if new_progress < self.unit_progress:
            new_progress = self.unit_progress
        self.unit_progress = new_progress

        # Quiz Score: average of all MCQ questions across the course
        total_q = MCQQuestion.objects.filter(lesson__course=self.course).count()
        if total_q > 0:
            correct_attempts = MCQAttempt.objects.filter(
                enrollment=self,
                is_correct=True
            ).count()
            self.quiz_score = round((correct_attempts / total_q) * 100, 1)
        else:
            # No quizzes => full quiz score
            self.quiz_score = 100.0

        # Weighted Mastery Score (60% video + 40% quiz)
        new_mastery = round((self.unit_progress * 0.6) + (self.quiz_score * 0.4), 1)

        # NEVER DECREASE mastery_score
        if new_mastery < self.mastery_score:
            new_mastery = self.mastery_score
        self.mastery_score = new_mastery

        # PERSISTENCE GUARD: Never downgrade completion once reached
        if self.is_completed:
            self.certificate_unlocked = True

        # Certificate Unlock (>= 80) — once unlocked, NEVER relock
        if self.mastery_score >= 80 or self.certificate_unlocked:
            self.certificate_unlocked = True
            self.is_completed = True
            if not self.completed_at:
                self.completed_at = timezone.now()

        self.save(update_fields=["completed_units", "unit_progress", "quiz_score", "mastery_score", "certificate_unlocked", "is_completed", "completed_at"])
        return self.mastery_score

    # Keep backward compat alias
    def update_scores(self):
        return self.recalculate_progress()
    
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
    quiz_unlocked = models.BooleanField(default=False)
    quiz_completed = models.BooleanField(default=False)
    watch_time = models.PositiveIntegerField(default=0, help_text='Total unique covered seconds')
    watched_ranges = models.JSONField(default=list, blank=True, help_text='[[start, end]] unique segments')
    max_position = models.PositiveIntegerField(default=0, help_text='Furthest position watched')

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['enrollment', 'lesson']

    def __str__(self):
        return f"{self.enrollment.student.email} - {self.lesson.title}"

    def update_watch_time(self, segment_start, segment_end, video_duration_seconds):
        """
        Processes a watched segment and updates unique coverage.
        Implements Dual Unlock Model:
        - 50% : Unlocks Quiz
        - 95% OR reached-the-end: Marks Lesson as Completed
        - 3s Tolerance: Treated as reached-the-end
        """
        # If already fully completed, we don't need to re-process for completion, 
        # but we might still track max_position.
        if self.is_completed and self.quiz_unlocked:
            if segment_end > self.max_position:
                self.max_position = int(segment_end)
                self.save(update_fields=['max_position'])
            return True

        if segment_start < 0: segment_start = 0
        if segment_end > video_duration_seconds: segment_end = video_duration_seconds
        if segment_start >= segment_end:
            return self.is_completed

        # Update watched ranges
        ranges = self.watched_ranges or []
        ranges.append([round(segment_start, 1), round(segment_end, 1)])
        
        # Merge overlaps and calculate unique coverage
        # FIX: merge_ranges returns (merged_list, total_seconds)
        merged_list, total_unique = merge_ranges(ranges)
        self.watched_ranges = merged_list
        self.watch_time = int(total_unique)

        if segment_end > self.max_position:
            self.max_position = int(segment_end)

        # Thresholds
        if video_duration_seconds > 0:
            progress_ratio = total_unique / video_duration_seconds
            
            # 50% Threshold: Unlock Quiz
            if progress_ratio >= 0.50:
                self.quiz_unlocked = True

            # Threshold + 3s Tolerance Check: Complete Lesson
            # Tolerance: If they are within 3s of the end, we can be more lenient
            tolerance_threshold = max(0, video_duration_seconds - 3)
            
            # Condition 1: High enough coverage (>95%)
            # Condition 2: Reached the end (within tolerance) AND have significant coverage (>80%)
            if progress_ratio >= 0.95 or (self.max_position >= tolerance_threshold and progress_ratio >= 0.80):
                if not self.is_completed:
                    self.is_completed = True
                    self.watch_time = video_duration_seconds  # Cap at full duration
                    self.completed_at = timezone.now()
                    # If lesson is completed, quiz MUST be unlocked too
                    self.quiz_unlocked = True
        
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