from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('home/', views.home, name='home_public'),
    path('about/', views.about, name='about'),
    path('teachers/', views.teachers, name='teachers'),
    path('teacher/<int:teacher_id>/', views.teacher_profile, name='teacher_profile'),
    path('teacher/<int:teacher_id>/message/', views.send_teacher_message, name='send_teacher_message'),
    path('contact/', views.contact_view, name='contact'),
    path('mission/', views.mission, name='mission'),
    path('faq/', views.faq, name='faq'),
    path('help-center/', views.help_center, name='help_center'),
    path('terms/', views.terms_conditions, name='terms_conditions'),
    path('privacy/', views.privacy_policy, name='privacy_policy'),
    path('refund/', views.refund_policy, name='refund_policy'),
]
