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
ESEWA_SECRET_KEY = getattr(settings, 'ESEWA_SECRET_KEY', '')
ESEWA_FORM_URL = getattr(settings, 'ESEWA_FORM_URL', 'https://rc-epay.esewa.com.np/api/epay/main/v2/form')

@login_required
def initiate_payment_view(request, course_slug):
    """
    Main payment initiation view - shows payment options
    """
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
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
def khalti_initiate_view(request, course_slug):
    print(f"DEBUG: Khalti initiate request received for course: {course_slug}")
    """
    Initiate Khalti payment using ePayment API v2 and redirect to Khalti's payment page
    """
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
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
        messages.success(request, f"Payment successful! You are now enrolled in {payment.course.title}.")
        return redirect('courses:course_detail', slug=payment.course.slug)
    else:
        messages.error(request, f"Payment verification failed: {verification_result.get('error', 'Unknown error')}")
        return redirect('courses:course_detail', slug=payment.course.slug)

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


@login_required
def esewa_initiate_view(request, course_slug):
    """
    Initiate eSewa payment
    """
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Check if already enrolled
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, "You are already enrolled in this course.")
        return redirect('courses:course_detail', slug=course.slug)
    
    # Create payment record
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        amount=course.price,
        payment_gateway='esewa'
    )
    
    # Prepare eSewa parameters
    import hmac
    import hashlib
    import base64
    
    total_amount = str(int(course.price))
    transaction_uuid = payment.transaction_id
    product_code = ESEWA_MERCHANT_CODE
    
    # Generate signature for eSewa v2
    message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
    signature = hmac.new(
        ESEWA_SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode()
    
    context = {
        'payment': payment,
        'course': course,
        'esewa_url': ESEWA_FORM_URL,
        'amount': total_amount,
        'tax_amount': "0",
        'product_service_charge': "0",
        'product_delivery_charge': "0",
        'total_amount': total_amount,
        'transaction_uuid': transaction_uuid,
        'product_code': product_code,
        'success_url': request.build_absolute_uri(reverse('payments:esewa_callback')),
        'failure_url': request.build_absolute_uri(reverse('payments:esewa_failure')),
        'signed_field_names': "total_amount,transaction_uuid,product_code",
        'signature': signature_b64,
    }
    
    return render(request, 'payments/esewa_checkout.html', context)

@require_GET
def esewa_callback_view(request):
    """
    Handle eSewa payment callback
    """
    data = request.GET.get('data')
    if not data:
        messages.error(request, "Invalid callback data from eSewa.")
        return redirect("payments:payment_failed")
    
    try:
        import base64
        import json
        
        # Decode base64 response
        decoded_bytes = base64.b64decode(data)
        decoded_str = decoded_bytes.decode('utf-8')
        response_data = json.loads(decoded_str)
        
        status = response_data.get('status')
        transaction_uuid = response_data.get('transaction_uuid')
        total_amount = response_data.get('total_amount')
        
        logger.info(f"eSewa callback received: {response_data}")
        
        if status != 'COMPLETE':
            messages.error(request, f"Payment failed with status: {status}")
            return redirect("payments:payment_failed")
        
        # Get payment record
        payment = get_object_or_404(Payment, transaction_id=transaction_uuid)
        
        # Verify amount
        amount_str = str(total_amount).replace(',', '')
        if float(amount_str) != float(payment.amount):
            payment.mark_failed({'error': 'Amount mismatch', 'response': response_data})
            messages.error(request, "Payment amount mismatch.")
            return redirect("payments:payment_failed")
        
        # Check if already processed
        if payment.status == 'completed':
            messages.info(request, "Payment already processed.")
            return redirect('courses:course_detail', slug=payment.course.slug)
        
        # Mark payment as completed
        with transaction.atomic():
            payment.mark_completed(
                gateway_transaction_id=response_data.get('transaction_code', ''),
                gateway_response=response_data
            )
            
            # Create enrollment
            Enrollment.objects.get_or_create(
                student=payment.user,
                course=payment.course,
                defaults={'enrolled_at': datetime.now()}
            )
        
        messages.success(request, f"Payment successful! You are now enrolled in {payment.course.title}.")
        return render(request, 'payments/esewa_success.html', {'payment': payment})
        
    except Exception as e:
        logger.exception(f"eSewa callback error: {e}")
        messages.error(request, "Error processing payment callback.")
        return redirect("payments:payment_failed")

@require_GET
def esewa_failure_view(request):
    """
    Handle eSewa payment failure
    """
    messages.error(request, "Payment was cancelled or failed.")
    return redirect("payments:payment_failed")

@require_GET
def payment_failed_view(request):
    """
    Display payment failure page
    """
    return render(request, 'payments/payment_failed.html')

@login_required
def payment_history_view(request):
    """
    Display user's payment history
    """
    payments = Payment.objects.filter(user=request.user).select_related('course').order_by('-created_at')
    context = {'payments': payments}
    return render(request, 'payments/payment_history.html', context)

@login_required
def payment_success_view(request, transaction_id):
    """
    Display payment success page
    """
    payment = get_object_or_404(Payment, transaction_id=transaction_id, user=request.user)
    
    if payment.status != 'completed':
        messages.warning(request, "This payment is not marked as completed.")
        return redirect('payments:payment_history')
    
    context = {
        'payment': payment,
        'course': payment.course
    }
    return render(request, 'payments/payment_success.html', context)