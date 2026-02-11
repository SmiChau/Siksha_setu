from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import transaction
import json
import requests
import logging
from datetime import datetime
import hmac
import base64
import hashlib
import uuid

from .models import Payment
from courses.models import Course, Enrollment

# Set up logger
logger = logging.getLogger(__name__)

# Get Khalti configuration from settings
KHALTI_PUBLIC_KEY = getattr(settings, 'KHALTI_PUBLIC_KEY', '')
KHALTI_SECRET_KEY = getattr(settings, 'KHALTI_SECRET_KEY', '')
KHALTI_INITIATE_URL = getattr(settings, 'KHALTI_INITIATE_URL', 'https://a.khalti.com/api/v2/epayment/initiate/')
KHALTI_VERIFY_URL = getattr(settings, 'KHALTI_VERIFY_URL', 'https://a.khalti.com/api/v2/epayment/lookup/')

# Get eSewa configuration
ESEWA_MERCHANT_CODE = getattr(settings, 'ESEWA_MERCHANT_CODE', 'EPAYTEST')
ESEWA_SECRET_KEY = getattr(settings, 'ESEWA_SECRET_KEY', '8gBm/:&EnhH.1/q')  # Default test secret
ESEWA_FORM_URL = getattr(settings, 'ESEWA_FORM_URL', 'https://rc-epay.esewa.com.np/api/epay/main/v2/form')

@login_required
def initiate_payment_view(request, course_slug):
    """
    Main payment initiation view - shows payment options
    """
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Admin Guard
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot enroll in courses. Please use a student account for enrollment.")
        return redirect('courses:course_detail', slug=course_slug)
    
    # Check if already enrolled
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, 'You are already enrolled in this course.')
        return redirect('courses:course_detail', slug=course_slug)
    
    # Handle free courses
    if course.is_free:
        Enrollment.objects.create(student=request.user, course=course)
        messages.success(request, f'Successfully enrolled in {course.title}!')
        return redirect('courses:course_detail', slug=course_slug)
    
    context = {
        'course': course,
        'khalti_public_key': KHALTI_PUBLIC_KEY,
        'amount': int(course.price),
        'amount_paisa': int(course.price * 100),
    }
    return render(request, 'payments/checkout.html', context)

@login_required
def khalti_checkout_view(request, course_slug):
    """
    Shows Khalti checkout summary page
    """
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Admin Guard
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot enroll in courses. Please use a student account for enrollment.")
        return redirect('courses:course_detail', slug=course_slug)
        
    # Check if already enrolled
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, 'You are already enrolled in this course.')
        return redirect('courses:course_detail', slug=course_slug)
        
    context = {
        'course': course,
        'total_amount': course.price,
        'amount': course.price,
        'student_name': request.user.get_full_name() or request.user.email,
    }
    return render(request, 'payments/khalti_checkout.html', context)


@login_required
def khalti_initiate_view(request, course_slug):
    print(f"DEBUG: Khalti initiate request received for course: {course_slug}")
    """
    Initiate Khalti payment using ePayment API v2 and redirect to Khalti's payment page
    """
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Admin Guard
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot enroll in courses. Please use a student account for enrollment.")
        return redirect('courses:course_detail', slug=course_slug)
    
    # Check if already enrolled
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, "You are already enrolled in this course.")
        return redirect('courses:course_detail', slug=course.slug)
    
    # Create payment record
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        amount=course.price,
        payment_gateway='khalti'
    )
    
    # Prepare Khalti ePayment API request
    return_url = request.build_absolute_uri(reverse('payments:khalti_callback'))
    website_url = request.build_absolute_uri('/')
    
    payload = {
        "return_url": return_url,
        "website_url": website_url,
        "amount": int(course.price * 100),  # Convert to paisa
        "purchase_order_id": str(payment.transaction_id),  # Fix: Convert UUID to string
        "purchase_order_name": str(course.title)[:99],  # Ensure string and limit length
        "customer_info": {
            "name": request.user.get_full_name() or request.user.email,
            "email": request.user.email,
        }
    }
    
    headers = {
        "Authorization": f"Key {KHALTI_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        # Make API call to Khalti
        response = requests.post(
            KHALTI_INITIATE_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        resp_data = response.json()
        
        # Extract payment URL and pidx
        payment_url = resp_data.get('payment_url')
        pidx = resp_data.get('pidx')
        
        if not payment_url or not pidx:
            logger.error(f"Invalid response from Khalti: {resp_data}")
            messages.error(request, "Failed to initiate payment. Please try again.")
            return redirect('courses:course_detail', slug=course.slug)
        
        # Store pidx in payment record for verification
        payment.gateway_transaction_id = pidx
        payment.gateway_response = resp_data
        payment.save()
        
        logger.info(f"Khalti payment initiated: {payment.transaction_id}, pidx: {pidx}")
        
        # Redirect user to Khalti's payment page
        return redirect(payment_url)
        
    except requests.Timeout:
        logger.error(f"Khalti API timeout for payment: {payment.transaction_id}")
        payment.mark_failed({'error': 'API timeout'})
        messages.error(request, "Payment gateway timeout. Please try again.")
        return redirect('courses:course_detail', slug=course.slug)
        
    except requests.RequestException as e:
        logger.error(f"Khalti API error: {e}")
        payment.mark_failed({'error': str(e)})
        messages.error(request, "Failed to connect to payment gateway. Please try again.")
        return redirect('courses:course_detail', slug=course.slug)
        
    except Exception as e:
        logger.exception(f"Unexpected error during Khalti initiation: {e}")
        payment.mark_failed({'error': str(e)})
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('courses:course_detail', slug=course.slug)

@login_required
def khalti_callback_view(request):
    """
    Handle callback from Khalti after payment
    """
    pidx = request.GET.get('pidx')
    transaction_id = request.GET.get('transaction_id')
    tidx = request.GET.get('tidx')
    amount = request.GET.get('amount')
    mobile = request.GET.get('mobile')
    purchase_order_id = request.GET.get('purchase_order_id')
    purchase_order_name = request.GET.get('purchase_order_name')
    status = request.GET.get('status')
    
    logger.info(f"Khalti callback received: pidx={pidx}, status={status}")
    
    if not pidx:
        messages.error(request, "Invalid payment callback.")
        return redirect('core:home')
    
    # Admin Guard
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot enroll in courses. Please use a student account for enrollment.")
        return redirect('core:home')
    
    try:
        # Find payment by pidx
        payment = Payment.objects.get(
            gateway_transaction_id=pidx,
            user=request.user,
            payment_gateway='khalti'
        )
    except Payment.DoesNotExist:
        logger.error(f"Payment not found for pidx: {pidx}")
        messages.error(request, "Payment record not found.")
        return redirect('core:home')
    
    # If payment already completed, redirect to course
    if payment.status == 'completed':
        messages.info(request, "Payment already processed.")
        return redirect('courses:course_detail', slug=payment.course.slug)
    
    # Verify payment with Khalti
    verification_result = verify_khalti_payment(pidx, payment)
    
    if verification_result['success']:
        return redirect('payments:khalti_success', transaction_id=payment.transaction_id)
    else:
        messages.error(request, f"Payment verification failed: {verification_result.get('error', 'Unknown error')}")
        return redirect('courses:course_detail', slug=payment.course.slug)

@login_required
def khalti_success_view(request, transaction_id):
    """
    Shows Khalti specific success page
    """
    payment = get_object_or_404(Payment, transaction_id=transaction_id, user=request.user, payment_gateway='khalti')
    return render(request, 'payments/khalti_success.html', {'payment': payment})


def verify_khalti_payment(pidx, payment):
    """
    Helper function to verify Khalti payment using lookup API
    """
    headers = {
        "Authorization": f"Key {KHALTI_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "pidx": pidx
    }
    
    try:
        response = requests.post(
            KHALTI_VERIFY_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        resp_data = response.json()
        
        logger.info(f"Khalti verification response: {resp_data}")
        
        # Check payment status
        khalti_status = resp_data.get('status', '').lower()
        
        if khalti_status == 'completed':
            # Verify amount
            khalti_amount = resp_data.get('total_amount', 0)
            expected_amount = int(payment.amount * 100)  # Convert to paisa
            
            if khalti_amount != expected_amount:
                logger.error(f"Amount mismatch: expected {expected_amount}, got {khalti_amount}")
                payment.mark_failed(resp_data)
                return {'success': False, 'error': 'Amount mismatch'}
            
            # Mark payment as completed and create enrollment
            payment.mark_completed(
                gateway_transaction_id=resp_data.get('transaction_id'),
                gateway_response=resp_data
            )
            
            logger.info(f"Payment completed successfully: {payment.transaction_id}")
            return {'success': True}
            
        else:
            # Payment not completed
            payment.status = khalti_status if khalti_status in ['pending', 'failed', 'refunded'] else 'failed'
            payment.gateway_response = resp_data
            payment.save()
            
            return {'success': False, 'error': f'Payment status: {khalti_status}'}
            
    except requests.RequestException as e:
        logger.error(f"Khalti verification API error: {e}")
        return {'success': False, 'error': 'Failed to verify payment'}
        
    except Exception as e:
        logger.exception(f"Unexpected error during verification: {e}")
        return {'success': False, 'error': 'Verification error'}


# Esewa Payment
@login_required
def esewa_initiate_view(request, course_slug):
    """
    Strict eSewa v2 implementation. 
    A 400 Bad Request usually means the amount format or required field is invalid.
    """
    course = get_object_or_404(Course, slug=course_slug)
    
    # Admin Guard
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot enroll in courses. Please use a student account for enrollment.")
        return redirect('courses:course_detail', slug=course_slug)
        
    # Pre-payment enrollment check
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, "You are already enrolled in this course.")
        return redirect('courses:course_detail', slug=course.slug)
        
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        amount=course.price,
        payment_gateway='esewa'
    )
    
    # Force strict sandbox defaults if not configured
    merchant_code = getattr(settings, 'ESEWA_MERCHANT_CODE', 'EPAYTEST')
    secret_key = getattr(settings, 'ESEWA_SECRET_KEY', '8gBm/:&EnhH.1/q')
    esewa_url = getattr(settings, 'ESEWA_FORM_URL', 'https://rc-epay.esewa.com.np/api/epay/main/v2/form')
    
    # eSewa v2 is extremely picky. 
    # Use EXACTLY one decimal place for ALL numerical fields as per dev docs (e.g. 100.0, 0.0)
    principal_amount = "{:.1f}".format(float(course.price))
    tax_amount = "0.0"
    psc = "0.0"
    pdc = "0.0"
    total_amount = principal_amount  # Since tax and charges are 0
    
    transaction_uuid = str(payment.transaction_id)
    
    # Signature Generation
    # Order: total_amount,transaction_uuid,product_code
    message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={merchant_code}"
    
    logger.info(f"DEBUG: eSewa Message: {message}")
    
    signature_bytes = hmac.new(
        secret_key.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')
    
    context = {
        'payment': payment,
        'course': course,
        'esewa_url': esewa_url,
        'amount': principal_amount,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'transaction_uuid': transaction_uuid,
        'product_code': merchant_code,
        'product_service_charge': psc,
        'product_delivery_charge': pdc,
        'success_url': request.build_absolute_uri(reverse('payments:esewa_callback')),
        'failure_url': request.build_absolute_uri(reverse('payments:esewa_failure')),
        'signed_field_names': "total_amount,transaction_uuid,product_code",
        'signature': signature_b64,
    }
    
    return render(request, 'payments/esewa_checkout.html', context)


@require_GET
@csrf_exempt
def esewa_callback_view(request):
    """
    Handle eSewa v2 Success Callback
    """
    data = request.GET.get('data')
    if not data:
        messages.error(request, "No data received from eSewa.")
        return redirect('payments:payment_failed')
    
    # Admin Guard
    if request.user.is_staff or request.user.is_superuser:
        messages.warning(request, "Admin accounts cannot enroll in courses. Please use a student account for enrollment.")
        return redirect('core:home')
        
    try:
        # 1. Decode JSON response from Base64
        decoded_bytes = base64.b64decode(data)
        decoded_str = decoded_bytes.decode('utf-8')
        resp = json.loads(decoded_str)
        
        logger.info(f"eSewa v2 Callback Data: {resp}")
        
        status = resp.get('status')
        transaction_uuid = resp.get('transaction_uuid')
        transaction_code = resp.get('transaction_code')
        total_amount = resp.get('total_amount')
        
        if status != 'COMPLETE':
            messages.error(request, f"Payment failed with status: {status}")
            return redirect('payments:payment_failed')
            
        # 2. Verify Internal Record
        payment = get_object_or_404(Payment, transaction_id=transaction_uuid)
        
        # 3. Verify Amount
        # Removing commas if eSewa sends formatted strings
        clean_total = str(total_amount).replace(',', '')
        if float(clean_total) != float(payment.amount):
            logger.error(f"Amount Mismatch! Gateway: {clean_total}, Expected: {payment.amount}")
            messages.error(request, "Payment verification failed: Amount mismatch.")
            return redirect('payments:payment_failed')
            
        # 4. Finalize Payment
        if payment.status != 'completed':
            with transaction.atomic():
                payment.mark_completed(
                    gateway_transaction_id=transaction_code,
                    gateway_response=resp
                )
                # Ensure Enrollment
                Enrollment.objects.get_or_create(student=payment.user, course=payment.course)
                
            messages.success(request, f"Successfully enrolled in {payment.course.title}!")
            
        return render(request, 'payments/esewa_success.html', {'payment': payment})
        
    except Exception as e:
        logger.exception("eSewa Callback Error")
        messages.error(request, "An error occurred during payment verification.")
        return redirect('payments:payment_failed')


@require_GET
def esewa_failure_view(request):
    """
    Redirected here by eSewa if user cancels or payment fails.
    """
    messages.warning(request, "Payment was cancelled or failed by eSewa.")
    return redirect('payments:payment_failed')


def payment_failed_view(request):
    return render(request, 'payments/payment_failed.html')


@login_required
def payment_success_view(request, transaction_id):
    payment = get_object_or_404(Payment, transaction_id=transaction_id, user=request.user)
    return render(request, 'payments/esewa_success.html', {'payment': payment})


@login_required
def payment_history_view(request):
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')
    context = {'payments': payments}
    return render(request, 'payments/payment_history.html', context)