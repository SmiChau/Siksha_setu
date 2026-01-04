from django.utils import timezone
from .models import Course

def calculate_gravity_score(course):
    """
    Hacker News Gravity Algorithm for Trending Courses.
    Formula: score = interactions / (time_since_upload_in_hours + 2) ** 1.5
    Interactions: Views (1), Enrollments (5), Reviews (3)
    """
    now = timezone.now()
    age_hours = (now - course.created_at).total_seconds() / 3600
    
    # Interactions
    views = course.views_count
    enrollments = course.enrollment_count
    reviews = course.reviews.count()
    
    interactions = views + (enrollments * 5) + (reviews * 3)
    
    # Gravity Algorithm
    gravity = 1.5
    score = interactions / pow(age_hours + 2, gravity)
    
    return round(score, 4)
