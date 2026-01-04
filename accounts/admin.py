from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, OTP


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_verified', 'is_approved', 'is_active', 'date_joined')
    list_filter = ('role', 'is_verified', 'is_approved', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'profile_picture', 'bio', 'phone')}),
        ('Role & Status', {'fields': ('role', 'is_verified', 'is_approved', 'is_active', 'is_staff', 'is_superuser')}),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login',)}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role', 'first_name', 'last_name'),
        }),
    )
    
    actions = ['approve_teachers', 'disapprove_users', 'activate_users', 'deactivate_users']
    
    def approve_teachers(self, request, queryset):
        queryset.filter(role='teacher').update(is_approved=True)
        self.message_user(request, "Selected teachers have been approved.")
    approve_teachers.short_description = "Approve selected teachers"
    
    def disapprove_users(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, "Selected users have been disapproved.")
    disapprove_users.short_description = "Disapprove selected users"
    
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Selected users have been activated.")
    activate_users.short_description = "Activate selected users"
    
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Selected users have been deactivated.")
    deactivate_users.short_description = "Deactivate selected users"


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ('email', 'otp_code', 'otp_type', 'is_used', 'created_at', 'expires_at')
    list_filter = ('otp_type', 'is_used')
    search_fields = ('email',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
