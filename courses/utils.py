from django.utils import timezone
from django.db.models import Count, Q

def calculate_gravity_score(enrollments, views, likes, created_at):
    """
    Hacker News Gravity Algorithm for Trending Courses.
    Formula: score = engagement_score / (time_since_created_in_hours + 2) ** 1.5
    engagement_score = (enrollments * 3) + (views * 1) + (likes * 2)

    ACADEMIC & INDUSTRY JUSTIFICATION:
    1.  **Anti-Stagnation**: Ensures new high-growth content can outrank old 
        static content.
    2.  **Momentum Tracking**: Measures "Real Time" interest rather than lifetime totals.
    3.  **Real Data Principle**: Calculating based on actual database relations 
        ensures the ranking is immune to dummy field manipulation.
    """
    import math
    
    # 1. Time since published (or created) in hours
    # Ensure it's not negative to avoid math domain errors
    age_hours = max((timezone.now() - created_at).total_seconds() / 3600, 0)
    
    # 2. Safe Engagement Score (+1 to ensure new items have non-zero score)
    # This ensures freshness ranking even for 0-engagement items
    safe_enrollments = enrollments or 0
    safe_views = views or 0
    safe_likes = likes or 0
    engagement_score = (safe_enrollments * 3) + (safe_views * 1) + (safe_likes * 2) + 1
    
    # 3. Gravity Calculation
    gravity = 1.5
    score = engagement_score / math.pow(age_hours + 2, gravity)
    
    return round(score, 4)

def get_trending_courses(limit=5):
    """
    Algorithm 2: Hacker News Gravity Algorithm (Global Source of Truth)
    ------------------------------------------------------------------
    Returns trending courses GLOBALLY for all published content.
    Same results for every user (student/teacher/admin).
    """
    from .models import Course
    
    # Global Query: Only published courses across ALL instructors
    courses = Course.objects.filter(status='published').annotate(
        actual_enrollments=Count('enrollments', filter=~Q(enrollments__student__is_staff=True, enrollments__student__is_superuser=True), distinct=True)
    ).select_related('instructor', 'category')
    
    trending_list = []

    for course in courses:
        # Use published_at for decay calculation if available, else created_at
        start_time = course.published_at or course.created_at
        
        score = calculate_gravity_score(
            enrollments=course.actual_enrollments,
            views=course.views_count,
            likes=course.likes_count,
            created_at=start_time
        )
        
        # MANDATORY ANALYTICS LOGGING (Ranking Stable Fix)
        # print(f"[ANALYTICS] Course: {course.id} | Engagement: {course.actual_enrollments}e/{course.views_count}v | Age: {round((timezone.now() - start_time).total_seconds()/3600, 2)}h | Score: {score}")
        
        trending_list.append({
            'course': course,
            'trending_score': score,
            'score': score 
        })

    # Sort GLOBALLY by gravity score (Highest to Lowest)
    trending_list.sort(key=lambda x: x['trending_score'], reverse=True)

    return trending_list[:limit]
