from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    path('', views.course_list_view, name='course_list'),
    path('<slug:slug>/', views.course_detail_view, name='course_detail'),
    path('<slug:slug>/enroll/', views.enroll_course_view, name='enroll_course'),
    path('<slug:course_slug>/lesson/<int:lesson_id>/', views.lesson_view, name='lesson_view'),
    path('<slug:course_slug>/lesson/<int:lesson_id>/complete/', views.mark_lesson_complete_view, name='mark_lesson_complete'),
    path('<slug:course_slug>/lesson/<int:lesson_id>/mcq/<int:question_id>/submit/', views.submit_mcq_answer_view, name='submit_mcq_answer'),
    path('<slug:course_slug>/review/', views.submit_review_view, name='submit_review'),
    path('my-courses/', views.my_courses_view, name='my_courses'),
    
    # Teacher Management
    path('manage/', views.teacher_dashboard_view, name='teacher_dashboard'),
    path('manage/create/', views.course_create_step1_view, name='course_create_start'),
    path('manage/course/<slug:slug>/step/1/', views.course_create_step1_view, name='course_edit_step1'),
    path('manage/course/<slug:slug>/step/2/', views.course_create_step2_view, name='course_edit_step2'),
    path('manage/course/<slug:slug>/step/3/', views.course_create_step3_view, name='course_edit_step3'),
    path('manage/course/<slug:slug>/step/4/', views.course_create_step4_view, name='course_edit_step4'),
    path('manage/course/<slug:slug>/step/5/', views.course_create_step5_view, name='course_edit_step5'),
    path('manage/course/<slug:slug>/publish/', views.course_publish_view, name='course_publish'),
    path('manage/course/<slug:slug>/delete/', views.course_delete_view, name='course_delete'),
]
