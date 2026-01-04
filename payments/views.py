from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
import requests
import hashlib
import base64
import hmac

from .models import Payment, KhaltiConfig, EsewaConfig
from courses.models import Course, Enrollment


KHALTI_TEST_SECRET_KEY = "test_secret_key_dc74e0fd57cb46cd93832aee0a390234"
KHALTI_TEST_PUBLIC_KEY = "test_public_key_dc74e0fd57cb46cd93832aee0a507234"

ESEWA_TEST_MERCHANT_CODE = "EPAYTEST"
ESEWA_TEST_SECRET = "8gBm/:&EnhH.1/q"


@login_required
def initiate_payment_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, 'You are already enrolled in this course.')
        return redirect('courses:course_detail', slug=course_slug)
    
    if course.is_free:
        Enrollment.objects.create(student=request.user, course=course)
        messages.success(request, f'Successfully enrolled in {course.title}!')
        return redirect('courses:course_detail', slug=course_slug)
    
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        amount=course.price,
        payment_gateway='khalti'
    )
    
    context = {
        'course': course,
        'payment': payment,
        'khalti_public_key': KHALTI_TEST_PUBLIC_KEY,
        'amount_paisa': int(course.price * 100),
    }
    return render(request, 'payments/payment_options.html', context)


@login_required
@require_POST
def khalti_initiate_view(request):
    data = json.loads(request.body)
    course_slug = data.get('course_slug')
    
    course = get_object_or_404(Course, slug=course_slug)
    
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        amount=course.price,
        payment_gateway='khalti'
    )
    
    return_url = request.build_absolute_uri(f'/payments/khalti/callback/')
    
    payload = {
        "return_url": return_url,
        "website_url": request.build_absolute_uri('/'),
        "amount": int(course.price * 100),
        "purchase_order_id": str(payment.transaction_id),
        "purchase_order_name": course.title,
        "customer_info": {
            "name": request.user.get_full_name() or request.user.email,
            "email": request.user.email,
        }
    }
    
    headers = {
        "Authorization": f"Key {KHALTI_TEST_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            "https://a.khalti.com/api/v2/epayment/initiate/",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            resp_data = response.json()
            return JsonResponse({
                'success': True,
                'payment_url': resp_data.get('payment_url'),
                'pidx': resp_data.get('pidx')
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Payment initiation failed'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def khalti_callback_view(request):
    pidx = request.GET.get('pidx')
    transaction_id = request.GET.get('transaction_id')
    purchase_order_id = request.GET.get('purchase_order_id')
    status = request.GET.get('status')
    
    if status == 'Completed':
        headers = {
            "Authorization": f"Key {KHALTI_TEST_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                "https://a.khalti.com/api/v2/epayment/lookup/",
                json={"pidx": pidx},
                headers=headers
            )
            
            if response.status_code == 200:
                resp_data = response.json()
                
                if resp_data.get('status') == 'Completed':
                    try:
                        payment = Payment.objects.get(transaction_id=purchase_order_id)
                        payment.mark_completed(
                            gateway_transaction_id=transaction_id,
                            gateway_response=resp_data
                        )
                        messages.success(request, 'Payment successful! You are now enrolled.')
                        return redirect('courses:course_detail', slug=payment.course.slug)
                    except Payment.DoesNotExist:
                        messages.error(request, 'Payment record not found.')
        except Exception as e:
            messages.error(request, f'Payment verification failed: {str(e)}')
    else:
        messages.error(request, 'Payment was not completed.')
    
    return redirect('core:course_list')


@login_required
@require_POST
def esewa_initiate_view(request):
    data = json.loads(request.body)
    course_slug = data.get('course_slug')
    
    course = get_object_or_404(Course, slug=course_slug)
    
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        amount=course.price,
        payment_gateway='esewa'
    )
    
    total_amount = str(course.price)
    tax_amount = "0"
    product_service_charge = "0"
    product_delivery_charge = "0"
    
    message = f"total_amount={total_amount},transaction_uuid={payment.transaction_id},product_code={ESEWA_TEST_MERCHANT_CODE}"
    
    signature = hmac.new(
        ESEWA_TEST_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode()
    
    success_url = request.build_absolute_uri('/payments/esewa/callback/')
    failure_url = request.build_absolute_uri('/payments/esewa/failure/')
    
    form_data = {
        'amount': total_amount,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'transaction_uuid': str(payment.transaction_id),
        'product_code': ESEWA_TEST_MERCHANT_CODE,
        'product_service_charge': product_service_charge,
        'product_delivery_charge': product_delivery_charge,
        'success_url': success_url,
        'failure_url': failure_url,
        'signed_field_names': 'total_amount,transaction_uuid,product_code',
        'signature': signature_b64,
    }
    
    return JsonResponse({
        'success': True,
        'form_data': form_data,
        'esewa_url': 'https://rc-epay.esewa.com.np/api/epay/main/v2/form'
    })


def esewa_callback_view(request):
    data = request.GET.get('data')
    
    if data:
        try:
            decoded = base64.b64decode(data).decode()
            response_data = json.loads(decoded)
            
            transaction_uuid = response_data.get('transaction_uuid')
            status = response_data.get('status')
            
            if status == 'COMPLETE':
                try:
                    payment = Payment.objects.get(transaction_id=transaction_uuid)
                    payment.mark_completed(
                        gateway_transaction_id=response_data.get('transaction_code', ''),
                        gateway_response=response_data
                    )
                    messages.success(request, 'Payment successful! You are now enrolled.')
                    return redirect('courses:course_detail', slug=payment.course.slug)
                except Payment.DoesNotExist:
                    messages.error(request, 'Payment record not found.')
        except Exception as e:
            messages.error(request, f'Payment verification failed: {str(e)}')
    
    messages.error(request, 'Payment verification failed.')
    return redirect('core:course_list')


def esewa_failure_view(request):
    messages.error(request, 'Payment was cancelled or failed.')
    return redirect('core:course_list')


@login_required
def payment_history_view(request):
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'payments': payments
    }
    return render(request, 'payments/payment_history.html', context)
