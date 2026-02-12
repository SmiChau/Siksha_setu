from django.urls import path
from . import views

app_name = 'adminpanel'

urlpatterns = [
    path('', views.admin_dashboard, name='dashboard'),
    
    # User Management
    path('user/', views.UserListView.as_view(), name='user_list'),
    path('user/create/', views.UserCreateView.as_view(), name='customuser_create'),
    path('user/<int:pk>/edit/', views.UserUpdateView.as_view(), name='customuser_update'),
    path('user/<int:pk>/delete/', views.UserDeleteView.as_view(), name='customuser_delete'),
    
    # Application Management
    path('application/', views.InstructorApplicationListView.as_view(), name='instructor_application_list'),
    path('application/<int:pk>/edit/', views.InstructorApplicationUpdateView.as_view(), name='instructorapplication_update'),
    
    # Course Management
    path('course/', views.CourseListView.as_view(), name='course_list'),
    path('course/create/', views.CourseCreateView.as_view(), name='course_create'),
    path('course/<int:pk>/edit/', views.CourseUpdateView.as_view(), name='course_update'),
    path('course/<int:pk>/delete/', views.CourseDeleteView.as_view(), name='course_delete'),
    
    # Category Management
    path('category/', views.CategoryListView.as_view(), name='category_list'),
    path('category/create/', views.CategoryCreateView.as_view(), name='category_create'),
    path('category/<int:pk>/edit/', views.CategoryUpdateView.as_view(), name='category_update'),
    path('category/<int:pk>/delete/', views.CategoryDeleteView.as_view(), name='category_delete'),
    
    # Enrollment Management
    path('enrollment/', views.EnrollmentListView.as_view(), name='enrollment_list'),
    path('enrollment/create/', views.EnrollmentCreateView.as_view(), name='enrollment_create'),
    path('enrollment/<int:pk>/edit/', views.EnrollmentUpdateView.as_view(), name='enrollment_update'),
    path('enrollment/<int:pk>/delete/', views.EnrollmentDeleteView.as_view(), name='enrollment_delete'),
    
    # Payment Management
    path('payment/', views.PaymentListView.as_view(), name='payment_list'),
    path('payment/create/', views.PaymentCreateView.as_view(), name='payment_create'),
    path('payment/<int:pk>/edit/', views.PaymentUpdateView.as_view(), name='payment_update'),
    path('payment/<int:pk>/delete/', views.PaymentDeleteView.as_view(), name='payment_delete'),
    
    # Contact Message Management
    path('contact/', views.ContactListView.as_view(), name='contact_list'),
    path('contact/create/', views.ContactCreateView.as_view(), name='contactmessage_create'),
    path('contact/<int:pk>/edit/', views.ContactUpdateView.as_view(), name='contactmessage_update'),
    path('contact/<int:pk>/delete/', views.ContactDeleteView.as_view(), name='contactmessage_delete'),
    
    # Teacher Profile Management
    path('teacher-profile/', views.TeacherProfileListView.as_view(), name='teacher_profile_list'),
    path('teacher-profile/<int:pk>/edit/', views.TeacherProfileUpdateView.as_view(), name='teacherprofile_update'),
]
