import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'siksha_setu.settings')
django.setup()

from courses.models import Enrollment, Course
from reviews.models import Review

def cleanup_instructor_data():
    """
    Surgical cleanup to remove instructor enrollments and reviews from their own courses.
    This ensures analytics are correct after the role-logic fix.
    """
    print("Starting cleanup...")
    
    # 1. Remove enrollments where student == instructor
    instructor_enrollments = Enrollment.objects.filter(student=models.F('course__instructor'))
    count = instructor_enrollments.count()
    if count > 0:
        for enrollment in instructor_enrollments:
            # Manually decrement enrollment_count since we are deleting
            Course.objects.filter(pk=enrollment.course_id).update(
                enrollment_count=models.F('enrollment_count') - 1
            )
        instructor_enrollments.delete()
        print(f"Removed {count} instructor self-enrollments.")
    else:
        print("No instructor self-enrollments found.")

    # 2. Remove reviews where user == instructor of the course
    instructor_reviews = Review.objects.filter(user=models.F('course__instructor'))
    review_count = instructor_reviews.count()
    if review_count > 0:
        instructor_reviews.delete()
        print(f"Removed {review_count} instructor self-reviews.")
    else:
        print("No instructor self-reviews found.")

    print("Cleanup complete.")

if __name__ == "__main__":
    # Fix the missing 'models' import in the script logic context
    from django.db import models
    cleanup_instructor_data()
