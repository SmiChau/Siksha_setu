from django import forms
from .models import TeacherMessage, ContactMessage, InstructorApplication
from django.contrib.auth import get_user_model

User = get_user_model()

class TeacherMessageForm(forms.ModelForm):
    class Meta:
        model = TeacherMessage
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Write your message to the teacher...',
                'rows': 4
            }),
        }


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['enquiry_type', 'full_name', 'email', 'phone', 'subject', 'message', 'teacher']
        widgets = {
            'enquiry_type': forms.Select(attrs={'class': 'form-control-custom', 'id': 'purpose'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control-custom', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control-custom', 'placeholder': 'Email Address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control-custom', 'placeholder': 'Phone Number (Optional)'}),
            'subject': forms.TextInput(attrs={'class': 'form-control-custom', 'placeholder': 'Subject'}),
            'message': forms.Textarea(attrs={'class': 'form-control-custom', 'placeholder': 'Your Message', 'rows': 4}),
            'teacher': forms.Select(attrs={'class': 'form-control-custom', 'id': 'teacher_select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter teacher queryset to only include teachers
        self.fields['teacher'].queryset = User.objects.filter(role='teacher', is_approved=True)
        
        # If user is authenticated, pre-fill
        if self.user and self.user.is_authenticated:
            self.fields['full_name'].initial = self.user.get_full_name()
            self.fields['email'].initial = self.user.email
            if self.user.phone:
                self.fields['phone'].initial = self.user.phone

        # Add is-invalid class if field has errors
        for field_name, field in self.fields.items():
            if self.errors.get(field_name):
                classes = field.widget.attrs.get('class', '')
                if 'is-invalid' not in classes:
                    field.widget.attrs['class'] = f"{classes} is-invalid".strip()

    def clean(self):
        cleaned_data = super().clean()
        enquiry_type = cleaned_data.get('enquiry_type')
        teacher = cleaned_data.get('teacher')

        if enquiry_type == 'TEACHER' and not teacher:
            self.add_error('teacher', "Please select a teacher for this enquiry.")

        return cleaned_data


class InstructorApplicationForm(forms.ModelForm):
    class Meta:
        model = InstructorApplication
        fields = ['full_name', 'email', 'phone', 'expertise', 'experience', 'cv']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control-custom', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control-custom', 'placeholder': 'Email Address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control-custom', 'placeholder': 'Phone Number'}),
            'expertise': forms.TextInput(attrs={'class': 'form-control-custom', 'placeholder': 'e.g. Python, Data Science'}),
            'experience': forms.NumberInput(attrs={'class': 'form-control-custom', 'placeholder': 'Years of Experience'}),
            'cv': forms.FileInput(attrs={'class': 'form-control-custom'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user and self.user.is_authenticated:
            self.fields['full_name'].initial = self.user.get_full_name()
            self.fields['email'].initial = self.user.email
            if self.user.phone:
                self.fields['phone'].initial = self.user.phone

        # Add is-invalid class if field has errors
        for field_name, field in self.fields.items():
            if self.errors.get(field_name):
                classes = field.widget.attrs.get('class', '')
                if 'is-invalid' not in classes:
                    field.widget.attrs['class'] = f"{classes} is-invalid".strip()
