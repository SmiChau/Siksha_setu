from django.contrib import admin
from .models import (
    Category, Course, Lesson, LessonResource, 
    MCQQuestion, Enrollment, LessonProgress, MCQAttempt
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ('title', 'order', 'youtube_video_id', 'video_duration', 'is_preview')


class LessonResourceInline(admin.TabularInline):
    model = LessonResource
    extra = 1


class MCQQuestionInline(admin.TabularInline):
    model = MCQQuestion
    extra = 1
    fields = ('question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'order')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'instructor', 'category', 'level', 'price', 'is_free', 'status', 'enrollment_count', 'created_at')
    list_filter = ('status', 'level', 'is_free', 'category', 'is_featured')
    search_fields = ('title', 'description', 'instructor__email')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('-created_at',)
    inlines = [LessonInline]
    
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'description', 'short_description')}),
        ('Media', {'fields': ('thumbnail', 'thumbnail_url')}),
        ('Details', {'fields': ('instructor', 'category', 'level', 'language')}),
        ('Pricing', {'fields': ('price', 'is_free')}),
        ('Status', {'fields': ('status', 'is_featured')}),
        ('Content', {'fields': ('what_you_learn', 'requirements', 'total_duration')}),
        ('Statistics', {'fields': ('views_count', 'enrollment_count'), 'classes': ('collapse',)}),
    )
    
    actions = ['publish_courses', 'archive_courses', 'feature_courses']
    
    def publish_courses(self, request, queryset):
        queryset.update(status='published')
        self.message_user(request, "Selected courses have been published.")
    publish_courses.short_description = "Publish selected courses"
    
    def archive_courses(self, request, queryset):
        queryset.update(status='archived')
        self.message_user(request, "Selected courses have been archived.")
    archive_courses.short_description = "Archive selected courses"
    
    def feature_courses(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, "Selected courses have been featured.")
    feature_courses.short_description = "Feature selected courses"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'video_duration', 'is_preview', 'created_at')
    list_filter = ('course', 'is_preview')
    search_fields = ('title', 'course__title')
    ordering = ('course', 'order')
    inlines = [LessonResourceInline, MCQQuestionInline]


@admin.register(LessonResource)
class LessonResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'resource_type', 'created_at')
    list_filter = ('resource_type',)
    search_fields = ('title', 'lesson__title')


@admin.register(MCQQuestion)
class MCQQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text_short', 'lesson', 'correct_option', 'order')
    list_filter = ('lesson__course',)
    search_fields = ('question_text', 'lesson__title')
    
    def question_text_short(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Question'


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'unit_progress', 'quiz_score', 'mastery_score', 'certificate_unlocked', 'enrolled_at')
    list_filter = ('is_completed', 'course')
    search_fields = ('student__email', 'course__title')
    ordering = ('-enrolled_at',)
    readonly_fields = ('enrolled_at', 'completed_at')


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'lesson', 'is_completed', 'watch_time', 'started_at')
    list_filter = ('is_completed',)
    search_fields = ('enrollment__student__email', 'lesson__title')


@admin.register(MCQAttempt)
class MCQAttemptAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'question', 'selected_option', 'is_correct', 'attempted_at')
    list_filter = ('is_correct',)
    search_fields = ('enrollment__student__email',)
