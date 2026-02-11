from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Sum
from accounts.models import CustomUser
from courses.models import Course, Enrollment
from core.models import ContactMessage
# from courses.utils import calculate_gravity_score # Removed in favor of global utility

@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request):
    # Overall Stats
    total_users = CustomUser.objects.filter(is_staff=False, is_superuser=False).count()
    total_courses = Course.objects.count()
    total_enrollments = Enrollment.objects.filter(student__is_staff=False, student__is_superuser=False).count()
    total_messages = ContactMessage.objects.count()
    
    # Trending Courses (Algorithm 2 - Global)
    from courses.utils import get_trending_courses as get_global_trending
    trending_courses = get_global_trending(10)
    
    # Recent Messages
    recent_messages = ContactMessage.objects.all().order_by('-created_at')[:5]
    
    # Global Engagement Metrics (Algorithm 2 Analytics)
    # Using aggregation to get real sums across all courses
    engagement_stats = Course.objects.aggregate(
        total_views=Sum('views_count'),
        total_likes=Sum('likes_count')
    )
    total_views = engagement_stats['total_views'] or 0
    total_likes = engagement_stats['total_likes'] or 0
    
    # Engagement Score = (enrollments * 3) + (views * 1) + (likes * 2)
    # This represents the total "energy" on the platform
    global_engagement_score = (total_enrollments * 3) + (total_views * 1) + (total_likes * 2)

    context = {
        'total_users': total_users,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
        'total_messages': total_messages,
        'total_views': total_views,
        'total_likes': total_likes,
        'global_engagement_score': global_engagement_score,
        'trending_courses': trending_courses,
        'recent_messages': recent_messages,
    }
    return render(request, 'adminpanel/dashboard.html', context)
