from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('certificates/', views.my_certificates_view, name='my_certificates'),
    path('certificates/download/<int:enrollment_id>/', views.certificate_download_view, name='certificate_download'),
    path('certificates/verify/', views.certificate_verify_view, name='certificate_verify'),
]
