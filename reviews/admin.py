from django.contrib import admin
from .models import Review, Certificate


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'rating', 'is_approved', 'created_at')
    list_filter = ('rating', 'is_approved')
    search_fields = ('user__email', 'course__title', 'comment')
    ordering = ('-created_at',)
    
    actions = ['approve_reviews', 'disapprove_reviews']
    
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, "Selected reviews have been approved.")
    approve_reviews.short_description = "Approve selected reviews"
    
    def disapprove_reviews(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, "Selected reviews have been disapproved.")
    disapprove_reviews.short_description = "Disapprove selected reviews"


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_id', 'student_name', 'course_title', 'completion_date', 'final_score', 'issued_at')
    search_fields = ('certificate_id', 'student_name', 'course_title')
    ordering = ('-issued_at',)
    readonly_fields = ('certificate_id', 'issued_at')
