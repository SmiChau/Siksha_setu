from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # General
    path('initiate/<slug:course_slug>/', views.initiate_payment_view, name='initiate_payment'),
    
    # Khalti ePayment API v2
    path('khalti/initiate/<slug:course_slug>/', views.khalti_initiate_view, name='khalti_initiate'),
    path('khalti/callback/', views.khalti_callback_view, name='khalti_callback'),
    
    # eSewa
    path('esewa/initiate/<slug:course_slug>/', views.esewa_initiate_view, name='esewa_checkout'),
    path('esewa/callback/', views.esewa_callback_view, name='esewa_callback'),
    path('esewa/failure/', views.esewa_failure_view, name='esewa_failure'),
    
    # General
    path('failed/', views.payment_failed_view, name='payment_failed'),
    path('history/', views.payment_history_view, name='payment_history'),
    path('success/<str:transaction_id>/', views.payment_success_view, name='payment_success'),
]
