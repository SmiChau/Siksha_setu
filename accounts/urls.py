from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('resend-password-reset-otp/', views.resend_password_reset_otp_view, name='resend_password_reset_otp'),
    
    path('student/dashboard/', views.student_dashboard_view, name='student_dashboard'),
    path('teacher/dashboard/', views.teacher_dashboard_view, name='teacher_dashboard'),
    path('teacher/pending-approval/', views.pending_approval_view, name='pending_approval'),
    
    path('teacher/course/create/', views.create_course_view, name='create_course'),
    path('teacher/course/<int:course_id>/edit/', views.edit_course_view, name='edit_course'),
    path('teacher/course/<int:course_id>/add-lesson/', views.add_lesson_view, name='add_lesson'),
    path('teacher/course/<int:course_id>/publish/', views.publish_course_view, name='publish_course'),
    
    path('profile/', views.profile_view, name='profile'),
    path('message/<int:message_id>/read/', views.mark_message_read, name='mark_message_read'),
]
