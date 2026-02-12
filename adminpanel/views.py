from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.utils.decorators import method_decorator
from django.db.models import Count, Sum, Q
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy, reverse, NoReverseMatch
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ImproperlyConfigured

from accounts.models import CustomUser, TeacherProfile
from courses.models import Course, Category, Enrollment
from core.models import ContactMessage, InstructorApplication
from payments.models import Payment

def staff_check(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@user_passes_test(staff_check, login_url='accounts:login')
def admin_dashboard(request):
    # Overall Stats
    total_users = CustomUser.objects.filter(is_staff=False, is_superuser=False).count()
    total_courses = Course.objects.count()
    total_enrollments = Enrollment.objects.filter(student__is_staff=False, student__is_superuser=False).count()
    total_messages = ContactMessage.objects.count()
    
    # Trending Courses
    from courses.utils import get_trending_courses as get_global_trending
    trending_courses = get_global_trending(10)
    
    # Recent Messages
    recent_messages = ContactMessage.objects.all().order_by('-created_at')[:5]
    
    context = {
        'total_users': total_users,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
        'total_messages': total_messages,
        'trending_courses': trending_courses,
        'recent_messages': recent_messages,
        'now': timezone.now(),
    }
    return render(request, 'adminpanel/dashboard.html', context)

# --- Base Admin Views ---

class AdminProtectedMixin:
    @method_decorator(user_passes_test(staff_check, login_url='accounts:login'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class BaseAdminListView(AdminProtectedMixin, ListView):
    template_name = 'adminpanel/model_list.html'
    paginate_by = 20

    def get_fields_to_display(self):
        """
        Override this method in child classes to specify which fields to display.
        Returns a list of field names (strings).
        """
        raise ImproperlyConfigured(
            "Subclasses of BaseAdminListView must provide a get_fields_to_display() method "
            "or override get_context_data to provide 'fields_to_display'"
        )

    def get_model_name_plural(self):
        """Return the plural verbose name of the model."""
        return self.model._meta.verbose_name_plural.title()

    def get_url_names(self):
        """Generate URL names for CRUD operations."""
        model_name = self.model._meta.model_name
        return {
            'create_url_name': f'adminpanel:{model_name}_create',
            'admin_update_url': f'adminpanel:{model_name}_update',
            'admin_delete_url': f'adminpanel:{model_name}_delete',
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add fields to display - NO _meta access in template!
        context['fields_to_display'] = self.get_fields_to_display()
        context['model_name'] = self.get_model_name_plural()
        context['search_query'] = self.request.GET.get('q', '')
        
        # Add URL names with safety checks
        url_names = self.get_url_names()
        
        # Verify Create URL
        try:
            reverse(url_names['create_url_name'])
            context['create_url_name'] = url_names['create_url_name']
        except NoReverseMatch:
            context['create_url_name'] = None

        # Verify Update URL (using dummy PK)
        try:
            reverse(url_names['admin_update_url'], kwargs={'pk': 0})
            context['admin_update_url'] = url_names['admin_update_url']
        except NoReverseMatch:
            context['admin_update_url'] = None

        # Verify Delete URL (using dummy PK)
        try:
            reverse(url_names['admin_delete_url'], kwargs={'pk': 0})
            context['admin_delete_url'] = url_names['admin_delete_url']
        except NoReverseMatch:
            context['admin_delete_url'] = None
        
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            # Override this in child classes for specific search fields
            queryset = self.filter_queryset_by_search(queryset, q)
        return queryset

    def filter_queryset_by_search(self, queryset, search_term):
        """Override this method in child classes to implement custom search."""
        # Default implementation - search in string representation
        filtered_ids = []
        for obj in queryset:
            if search_term.lower() in str(obj).lower():
                filtered_ids.append(obj.id)
        return queryset.filter(id__in=filtered_ids)

class BaseAdminCreateView(AdminProtectedMixin, CreateView):
    template_name = 'adminpanel/model_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_name'] = self.model._meta.verbose_name.title()
        context['action'] = 'Create'
        return context

    def form_valid(self, form):
        messages.success(self.request, f"{self.model._meta.verbose_name.title()} created successfully.")
        return super().form_valid(form)

class BaseAdminUpdateView(AdminProtectedMixin, UpdateView):
    template_name = 'adminpanel/model_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_name'] = self.model._meta.verbose_name.title()
        context['action'] = 'Update'
        return context

    def form_valid(self, form):
        messages.success(self.request, f"{self.model._meta.verbose_name.title()} updated successfully.")
        return super().form_valid(form)

class BaseAdminDeleteView(AdminProtectedMixin, DeleteView):
    template_name = 'adminpanel/model_confirm_delete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_name'] = self.model._meta.verbose_name.title()
        return context

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, f"{self.model._meta.verbose_name.title()} deleted successfully.")
        return super().delete(request, *args, **kwargs)

# --- Concrete Model Views ---

# User Management
class UserListView(BaseAdminListView):
    model = CustomUser
    
    def get_fields_to_display(self):
        return ['id', 'email', 'first_name', 'last_name', 'role', 'is_active', 'is_verified', 'is_approved', 'date_joined']
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(email__icontains=search_term) | 
            Q(first_name__icontains=search_term) | 
            Q(last_name__icontains=search_term)
        )

class UserCreateView(BaseAdminCreateView):
    model = CustomUser
    fields = ['first_name', 'last_name', 'email', 'role', 'is_active', 'is_verified', 'is_approved']
    success_url = reverse_lazy('adminpanel:user_list')
    
    def form_valid(self, form):
        user = form.save(commit=False)
        if not user.password:
            user.set_unusable_password()
        return super().form_valid(form)

class UserUpdateView(BaseAdminUpdateView):
    model = CustomUser
    fields = ['first_name', 'last_name', 'role', 'is_active', 'is_verified', 'is_approved']
    success_url = reverse_lazy('adminpanel:user_list')

class UserDeleteView(BaseAdminDeleteView):
    model = CustomUser
    success_url = reverse_lazy('adminpanel:user_list')

# Instructor Application Management
class InstructorApplicationListView(BaseAdminListView):
    model = InstructorApplication
    
    def get_fields_to_display(self):
        return ['id', 'user', 'full_name', 'email', 'expertise', 'experience', 'status', 'created_at']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(full_name__icontains=search_term) | 
            Q(email__icontains=search_term) |
            Q(expertise__icontains=search_term)
        )

class InstructorApplicationUpdateView(BaseAdminUpdateView):
    model = InstructorApplication
    fields = ['status']
    success_url = reverse_lazy('adminpanel:instructor_application_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        application = self.get_object()
        if application.status == 'APPROVED' and application.user:
            user = application.user
            user.role = 'teacher'
            user.is_approved = True
            user.save()
            messages.success(self.request, f"User {user.email} has been promoted to Teacher and approved.")
        elif application.status == 'REJECTED' and application.user:
            user = application.user
            user.is_approved = False
            user.save()
        return response

# Course Management
class CourseListView(BaseAdminListView):
    model = Course
    
    def get_fields_to_display(self):
        return ['id', 'title', 'category', 'instructor', 'level', 'status', 'price', 'is_featured', 'created_at']
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(title__icontains=search_term) | 
            Q(slug__icontains=search_term)
        )

class CourseCreateView(BaseAdminCreateView):
    model = Course
    fields = ['title', 'slug', 'category', 'instructor', 'level', 'status', 'is_featured', 'price', 'description', 'thumbnail', 'total_duration']
    success_url = reverse_lazy('adminpanel:course_list')

class CourseUpdateView(BaseAdminUpdateView):
    model = Course
    fields = ['title', 'category', 'instructor', 'level', 'status', 'is_featured', 'price', 'description', 'thumbnail', 'total_duration']
    success_url = reverse_lazy('adminpanel:course_list')

    def form_valid(self, form):
        if 'status' in form.changed_data and form.cleaned_data['status'] == 'published':
            course = form.save(commit=False)
            if not course.published_at:
                course.published_at = timezone.now()
        return super().form_valid(form)

class CourseDeleteView(BaseAdminDeleteView):
    model = Course
    success_url = reverse_lazy('adminpanel:course_list')

# Category Management
class CategoryListView(BaseAdminListView):
    model = Category
    
    def get_fields_to_display(self):
        return ['id', 'name', 'slug', 'description', 'created_at']
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(name__icontains=search_term) | 
            Q(slug__icontains=search_term) | 
            Q(description__icontains=search_term)
        )

class CategoryCreateView(BaseAdminCreateView):
    model = Category
    fields = ['name', 'slug', 'description', 'icon']
    success_url = reverse_lazy('adminpanel:category_list')

class CategoryUpdateView(BaseAdminUpdateView):
    model = Category
    fields = ['name', 'slug', 'description', 'icon']
    success_url = reverse_lazy('adminpanel:category_list')

class CategoryDeleteView(BaseAdminDeleteView):
    model = Category
    success_url = reverse_lazy('adminpanel:category_list')

# Enrollment Management
class EnrollmentListView(BaseAdminListView):
    model = Enrollment
    
    def get_fields_to_display(self):
        return ['id', 'student', 'course', 'enrolled_at', 'is_completed', 'is_paid', 'mastery_score']
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(student__email__icontains=search_term) | 
            Q(course__title__icontains=search_term)
        )

class EnrollmentCreateView(BaseAdminCreateView):
    model = Enrollment
    fields = ['student', 'course', 'is_paid']
    success_url = reverse_lazy('adminpanel:enrollment_list')

class EnrollmentUpdateView(BaseAdminUpdateView):
    model = Enrollment
    fields = ['is_paid', 'is_completed', 'mastery_score']
    success_url = reverse_lazy('adminpanel:enrollment_list')

class EnrollmentDeleteView(BaseAdminDeleteView):
    model = Enrollment
    success_url = reverse_lazy('adminpanel:enrollment_list')

# Payment Management
class PaymentListView(BaseAdminListView):
    model = Payment
    
    def get_fields_to_display(self):
        return ['id', 'user', 'course', 'amount', 'status', 'payment_gateway', 'created_at']
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(user__email__icontains=search_term) | 
            Q(course__title__icontains=search_term) | 
            Q(transaction_id__icontains=search_term) |
            Q(gateway_transaction_id__icontains=search_term)
        )

class PaymentCreateView(BaseAdminCreateView):
    model = Payment
    fields = ['user', 'course', 'amount', 'status', 'payment_gateway']
    success_url = reverse_lazy('adminpanel:payment_list')

class PaymentUpdateView(BaseAdminUpdateView):
    model = Payment
    fields = ['status', 'payment_gateway']
    success_url = reverse_lazy('adminpanel:payment_list')

class PaymentDeleteView(BaseAdminDeleteView):
    model = Payment
    success_url = reverse_lazy('adminpanel:payment_list')

# Contact Message Management
class ContactListView(BaseAdminListView):
    model = ContactMessage
    template_name = 'adminpanel/model_list.html'
    
    def get_fields_to_display(self):
        return ['id', 'full_name', 'email', 'subject', 'enquiry_type', 'created_at']
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(full_name__icontains=search_term) | 
            Q(email__icontains=search_term) | 
            Q(subject__icontains=search_term) | 
            Q(message__icontains=search_term)
        )

class ContactCreateView(BaseAdminCreateView):
    model = ContactMessage
    fields = ['full_name', 'email', 'subject', 'message', 'enquiry_type']
    success_url = reverse_lazy('adminpanel:contact_list')

class ContactUpdateView(BaseAdminUpdateView):
    model = ContactMessage
    fields = ['full_name', 'email', 'phone', 'subject', 'message', 'enquiry_type']
    success_url = reverse_lazy('adminpanel:contact_list')

class ContactDeleteView(BaseAdminDeleteView):
    model = ContactMessage
    success_url = reverse_lazy('adminpanel:contact_list')

# Teacher Profile Management
class TeacherProfileListView(BaseAdminListView):
    model = TeacherProfile
    
    def get_fields_to_display(self):
        return ['id', 'user', 'education', 'experience', 'location', 'languages']
    
    def filter_queryset_by_search(self, queryset, search_term):
        return queryset.filter(
            Q(user__email__icontains=search_term) | 
            Q(user__first_name__icontains=search_term) | 
            Q(user__last_name__icontains=search_term) | 
            Q(education__icontains=search_term) |
            Q(experience__icontains=search_term)
        )

class TeacherProfileUpdateView(BaseAdminUpdateView):
    model = TeacherProfile
    fields = ['education', 'experience', 'location', 'languages']
    success_url = reverse_lazy('adminpanel:teacher_profile_list')