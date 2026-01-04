from django import forms
from .models import TeacherMessage, ContactMessage

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
        fields = ['subject', 'message']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter subject'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your message',
                'rows': 5
            }),
        }
