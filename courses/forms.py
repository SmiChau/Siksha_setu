from django import forms
from django.utils.text import slugify
from .models import Course, Lesson, LessonResource, MCQQuestion

class CourseDetailsForm(forms.ModelForm):
    what_you_learn_raw = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'One point per line...'}),
        required=False,
        label='What you will learn',
        help_text='Enter each learning outcome on a new line.'
    )
    requirements_raw = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'One requirement per line...'}),
        required=False,
        label='Requirements',
        help_text='Enter each requirement on a new line.'
    )

    tags_field = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'python, beginner, webdev'}),
        required=False,
        label='Tags',
        help_text='Comma-separated tags (e.g. python, beginner)'
    )

    class Meta:
        model = Course
        fields = ['title', 'category', 'level', 'description', 'short_description', 'thumbnail', 'is_free', 'price']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'short_description': forms.Textarea(attrs={'rows': 2}),
            'price': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'is_free': forms.RadioSelect(choices=[(True, 'Free'), (False, 'Paid')]),
        }

    def clean_price(self):
        is_free = self.cleaned_data.get('is_free')
        price = self.cleaned_data.get('price')
        
        if not is_free and (price is None or price < 1):
            raise forms.ValidationError("Paid courses must have a price of at least 1 NPR.")
        
        if is_free:
            return 0
        return price

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.what_you_learn:
                self.initial['what_you_learn_raw'] = '\n'.join(self.instance.what_you_learn)
            if self.instance.requirements:
                self.initial['requirements_raw'] = '\n'.join(self.instance.requirements)
            # Populate tags
            self.initial['tags_field'] = ', '.join([t.name for t in self.instance.tags.all()])

        # Add form-control class and is-invalid if field has errors
        for field_name, field in self.fields.items():
            classes = field.widget.attrs.get('class', '')
            if 'form-control' not in classes and 'form-check-input' not in classes and 'form-select' not in classes:
                if isinstance(field.widget, (forms.Select, forms.RadioSelect)):
                    if not isinstance(field.widget, forms.RadioSelect):
                        field.widget.attrs['class'] = f"{classes} form-select".strip()
                else:
                    field.widget.attrs['class'] = f"{classes} form-control".strip()
            
            if self.errors.get(field_name):
                classes = field.widget.attrs.get('class', '')
                if 'is-invalid' not in classes:
                    field.widget.attrs['class'] = f"{classes} is-invalid".strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.slug:
            slug = slugify(instance.title)
            unique_slug = slug
            counter = 1
            while Course.objects.filter(slug=unique_slug).exists():
                unique_slug = f"{slug}-{counter}"
                counter += 1
            instance.slug = unique_slug
        
        # Process what_you_learn
        learn_raw = self.cleaned_data.get('what_you_learn_raw', '')
        instance.what_you_learn = [line.strip() for line in learn_raw.split('\n') if line.strip()]
        
        # Process requirements
        req_raw = self.cleaned_data.get('requirements_raw', '')
        instance.requirements = [line.strip() for line in req_raw.split('\n') if line.strip()]
        
        if commit:
            instance.save()
            # Process Tags
            from .models import Tag
            tags_raw = self.cleaned_data.get('tags_field', '')
            if tags_raw:
                tag_names = [t.strip() for t in tags_raw.split(',') if t.strip()]
                tags = []
                for name in tag_names:
                    tag, created = Tag.objects.get_or_create(name=name)
                    tags.append(tag)
                instance.tags.set(tags)
            else:
                instance.tags.clear()
                
        return instance

class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['title', 'description', 'video_file', 'youtube_video_id', 'duration_minutes', 'duration_seconds', 'order', 'is_preview']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'duration_minutes': forms.NumberInput(attrs={'min': '0'}),
            'duration_seconds': forms.NumberInput(attrs={'min': '0', 'max': '59'}),
        }
        help_texts = {
            'youtube_video_id': 'Only the 11-character ID from the YouTube URL (e.g., dQw4w9WgXcQ).',
            'video_file': 'Upload a local video file (MP4, WebM, etc).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add is-invalid class if field has errors
        for field_name, field in self.fields.items():
            if self.errors.get(field_name):
                classes = field.widget.attrs.get('class', '')
                if 'is-invalid' not in classes:
                    field.widget.attrs['class'] = f"{classes} is-invalid".strip()

    def clean(self):
        cleaned_data = super().clean()
        video_file = cleaned_data.get('video_file')
        youtube_id = cleaned_data.get('youtube_video_id')
        seconds = cleaned_data.get('duration_seconds')

        if not video_file and not youtube_id:
            raise forms.ValidationError("Please provide either a Video File or a YouTube Video ID.")
        
        # Note: We allow both if the user wants to fallback, but the prompt says "Ensure one is required".
        # It doesn't say "only one allowed". However, usually it's one or the other.
        # "Instructor can choose: Upload a local video OR provide a video URL" 
        # I'll stick to 'at least one'.

        if seconds is not None and seconds > 59:
            self.add_error('duration_seconds', "Seconds cannot exceed 59.")
        
        return cleaned_data

    def clean_youtube_video_id(self):
        video_id = self.cleaned_data.get('youtube_video_id')
        if not video_id:
            return video_id
        
        # Extract ID from various YouTube URL formats
        import re
        patterns = [
            r'(?:v=|\/embed\/|\/1\/|\/v\/|youtu\.be\/|\/v=)([a-zA-Z0-9_-]{11})',
            r'(?:^|[\/|=])([a-zA-Z0-9_-]{11})(?:$|[?&])', # 11-char ID surrounded by separators
        ]
        
        for pattern in patterns:
            match = re.search(pattern, video_id)
            if match:
                return match.group(1)
        
        return video_id

class LessonResourceForm(forms.ModelForm):
    class Meta:
        model = LessonResource
        fields = ['title', 'resource_type', 'file', 'external_url']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add is-invalid class if field has errors
        for field_name, field in self.fields.items():
            if self.errors.get(field_name):
                classes = field.widget.attrs.get('class', '')
                if 'is-invalid' not in classes:
                    field.widget.attrs['class'] = f"{classes} is-invalid".strip()

class MCQQuestionForm(forms.ModelForm):
    class Meta:
        model = MCQQuestion
        fields = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'explanation', 'order']
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 3}),
            'explanation': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add is-invalid class if field has errors
        for field_name, field in self.fields.items():
            if self.errors.get(field_name):
                classes = field.widget.attrs.get('class', '')
                if 'is-invalid' not in classes:
                    field.widget.attrs['class'] = f"{classes} is-invalid".strip()
