from django import forms
from django.core.exceptions import ValidationError
from .models import CustomUser, TeacherProfile
from .validators import validate_genuine_email


class SignupForm(forms.ModelForm):
    """
    Form for user signup with email, password, confirm password, and role.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter password'
        }),
        min_length=8,
        help_text='Password must be at least 8 characters long.'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password'
        }),
        label='Confirm Password',
        help_text='Enter the same password as before, for verification.'
    )
    
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email address'
            }),
        }
        help_texts = {
            'email': 'We will send an OTP to this email address for verification.',
        }
    
    def clean_email(self):
        """Validate email is unique and genuine."""
        email = self.cleaned_data.get('email')
        
        # Run custom validator
        if email:
            validate_genuine_email(email)
            
        if email and CustomUser.objects.filter(email=email).exists():
            raise ValidationError('A user with this email already exists.')
        return email
    
    def clean(self):
        """Validate that password and confirm_password match."""
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password:
            if password != confirm_password:
                raise ValidationError({
                    'confirm_password': 'Passwords do not match.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the user with hashed password."""
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.is_active = False  # User inactive until OTP verification
        user.is_verified = False
        if commit:
            user.save()
        return user


class OTPVerificationForm(forms.Form):
    """
    Form for OTP verification.
    """
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        }),
        help_text='Enter the email address you used for signup.'
    )
    otp = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 6-digit OTP',
            'maxlength': '6',
            'pattern': '[0-9]{6}'
        }),
        label='OTP Code',
        min_length=6,
        max_length=6,
        help_text='Enter the 6-digit OTP sent to your email.'
    )
    
    def clean_otp(self):
        """Validate OTP format (must be 6 digits)."""
        otp = self.cleaned_data.get('otp')
        if otp and not otp.isdigit():
            raise ValidationError('OTP must contain only numbers.')
        return otp


class LoginForm(forms.Form):
    """
    Form for user login with email and password.
    """
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        }),
        help_text='Enter the email address you used for signup.'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password'
        }),
        help_text='Enter your account password.'
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'rememberMe'
        }),
        label='Remember Me'
    )


class ForgotPasswordForm(forms.Form):
    """
    Form for requesting password reset - user enters email.
    """
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        }),
        help_text='Enter the email address associated with your account.'
    )


class ResetPasswordForm(forms.Form):
    """
    Form for resetting password with OTP verification.
    """
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        }),
        help_text='Enter the email address you used for password reset request.'
    )
    otp = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 6-digit OTP',
            'maxlength': '6',
            'pattern': '[0-9]{6}'
        }),
        label='OTP Code',
        min_length=6,
        max_length=6,
        help_text='Enter the 6-digit OTP sent to your email.'
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password'
        }),
        label='New Password',
        min_length=8,
        help_text='Password must be at least 8 characters long.'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        }),
        label='Confirm New Password',
        help_text='Enter the same password as before, for verification.'
    )
    
    def clean_otp(self):
        """Validate OTP format (must be 6 digits)."""
        otp = self.cleaned_data.get('otp')
        if otp and not otp.isdigit():
            raise ValidationError('OTP must contain only numbers.')
        return otp
    
    def clean(self):
        """Validate that new_password and confirm_password match."""
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password:
            if new_password != confirm_password:
                raise ValidationError({
                    'confirm_password': 'Passwords do not match.'
                })
        
        return cleaned_data

class TeacherProfileForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ['education', 'experience', 'location', 'languages']
        widgets = {
            'education': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'e.g. B.Sc in Computer Science, Tribhuvan University'
            }),
            'experience': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'e.g. 5+ years in Web Development'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Kathmandu, Nepal'
            }),
            'languages': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g. English, Nepali, Hindi'
            }),
        }
        help_texts = {
            'education': 'Mention your highest degree and the institution.',
            'experience': 'Briefly describe your professional journey and years of experience.',
            'location': 'Your current city and country.',
            'languages': 'List languages you are proficient in, separated by commas.',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # languages is now a CharField, so we don't need to join anything
    
    def clean_languages(self):
        languages = self.cleaned_data.get('languages', '')
        if languages is None:
            return ""
        return languages.strip()
