from django.contrib import admin

from .models import TeacherMessage, ContactMessage, InstructorApplication

@admin.register(TeacherMessage)
class TeacherMessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'teacher', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('sender__email', 'teacher__email', 'message')

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('enquiry_type', 'full_name', 'email', 'subject', 'created_at')
    list_filter = ('enquiry_type', 'created_at')
    search_fields = ('full_name', 'email', 'subject', 'message')

@admin.register(InstructorApplication)
class InstructorApplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('full_name', 'email', 'expertise')
    readonly_fields = ('created_at',)
