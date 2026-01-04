import os
import django
from django.core.mail import send_mail
from django.conf import settings

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'siksha_setu.settings')
django.setup()

def test_email():
    print(f"Testing email configuration...")
    print(f"HOST: {settings.EMAIL_HOST}")
    print(f"PORT: {settings.EMAIL_PORT}")
    print(f"USER: {settings.EMAIL_HOST_USER}")
    
    # Hide password in output
    pwd_masked = '*' * len(settings.EMAIL_HOST_PASSWORD) if settings.EMAIL_HOST_PASSWORD else "EMPTY"
    print(f"PASSWORD (len): {len(settings.EMAIL_HOST_PASSWORD) if settings.EMAIL_HOST_PASSWORD else 0}")

    if not settings.EMAIL_HOST_PASSWORD or "CHANGE_THIS" in settings.EMAIL_HOST_PASSWORD:
        print("\n[ERROR] Please update EMAIL_HOST_PASSWORD in settings.py with your Gmail App Password!")
        return

    recipient = settings.EMAIL_HOST_USER # Send to self for test
    
    try:
        print(f"\nAttempting to send email to {recipient}...")
        send_mail(
            subject='Siksha Setu - SMTP Test',
            message='If you are reading this, your Django email configuration is CORRECT!',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        print("\n[SUCCESS] Email sent successfully!")
        print("Check your inbox (and spam folder) for the test email.")
    except Exception as e:
        print(f"\n[FAILURE] Error sending email:\n{e}")
        print("\nTroubleshooting Tips:")
        print("1. Did you use an App Password? (Not your regular Gmail password)")
        print("2. Is 2-Step Verification enabled on your Google Account? (Required for App Passwords)")
        print("3. Check firewall/internet settings.")


if __name__ == "__main__":
    test_email()
