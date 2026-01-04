from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Sum
from accounts.models import CustomUser
from courses.models import Course, Enrollment
from core.models import ContactMessage
from courses.utils import calculate_gravity_score

@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request):
    # Overall Stats
    total_users = CustomUser.objects.count()
    total_courses = Course.objects.count()
    total_enrollments = Enrollment.objects.count()
    total_messages = ContactMessage.objects.count()
    
    # Trending Courses
    courses = Course.objects.filter(status='published')
    trending_courses = []
    for course in courses:
        score = calculate_gravity_score(course)
        trending_courses.append({
            'course': course,
            'score': score
        })
    
    # Sort by score descending
    trending_courses = sorted(trending_courses, key=lambda x: x['score'], reverse=True)[:10]
    
    # Recent Messages
    recent_messages = ContactMessage.objects.all().order_by('-created_at')[:5]
    
    context = {
        'total_users': total_users,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
        'total_messages': total_messages,
        'trending_courses': trending_courses,
        'recent_messages': recent_messages,
    }
    return render(request, 'adminpanel/dashboard.html', context)
