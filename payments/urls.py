from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('initiate/<slug:course_slug>/', views.initiate_payment_view, name='initiate_payment'),
    path('khalti/initiate/', views.khalti_initiate_view, name='khalti_initiate'),
    path('khalti/callback/', views.khalti_callback_view, name='khalti_callback'),
    path('esewa/initiate/', views.esewa_initiate_view, name='esewa_initiate'),
    path('esewa/callback/', views.esewa_callback_view, name='esewa_callback'),
    path('esewa/failure/', views.esewa_failure_view, name='esewa_failure'),
    path('history/', views.payment_history_view, name='payment_history'),
]
