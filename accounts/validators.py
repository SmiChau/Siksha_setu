from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import re

def validate_genuine_email(value):
    """
    Validator to check for genuine email addresses.
    Blocks common disposable email providers and ensures valid format.
    """
    # 1. Basic Regex Check (already done by EmailField, but being double sure)
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, value):
        raise ValidationError(
            _('Enter a valid email address.'),
            code='invalid_format'
        )

    domain = value.split('@')[1].lower()

    # 2. Block Common Disposable/Temp Email Domains
    # This is a small list; for production, use a large maintained list or API.
    # For an academic project, a representative list is sufficient.
    disposable_domains = [
        'tempmail.com', 'throwawaymail.com', 'mailinator.com', 'guerrillamail.com',
        'yopmail.com', '10minutemail.com', 'sharklasers.com', 'getnada.com',
        'dispostable.com', 'grr.la', 'mailvh.com', 'incognitomail.com', 'guerrillamail.net',
        'guerrillamail.org', 'guerrillamail.biz', 'guerrillamailblock.com',
        'spam4.me', 'maildrop.cc', 'harakirimail.com'
    ]


    if domain in disposable_domains:
        raise ValidationError(
            _('Please use a genuine email address (e.g., Gmail, Yahoo, Outlook). Disposable emails are not allowed.'),
            code='disposable_email'
        )

    # 3. Block "example.com" or "test.com"
    if domain in ['example.com', 'test.com', 'sample.com']:
        raise ValidationError(
             _('Please use a real email address.'),
             code='invalid_domain'
        )
