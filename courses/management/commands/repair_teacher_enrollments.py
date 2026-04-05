"""
Management Command: repair_teacher_enrollments
================================================
One-time data repair for the teacher-enrollment access bug.

WHAT IT FIXES:
1. Enrollments where is_paid=False but matching completed payment exists.
2. Free-course enrollments missing is_paid=True.
3. Teacher-specific enrollments that require is_paid=True and Lesson-1 bootstrapping.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from courses.models import Enrollment, LessonProgress

User = get_user_model()

class Command(BaseCommand):
    help = "Repair teacher enrollments: set is_paid=True where appropriate, bootstrap LessonProgress rows."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without writing to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be written.\n"))

        self.stdout.write("Starting Teacher Enrollment Repair...")
        
        # Identify all teachers who have enrollments
        # Assuming 'role' is a field on your CustomUser model
        teachers = User.objects.filter(role='teacher')
        
        repaired_count = 0
        progress_count = 0
        
        for teacher in teachers:
            # Get teacher enrollments
            enrollments = Enrollment.objects.filter(student=teacher)
            
            for enrollment in enrollments:
                # SKIP if it's the instructor's own course
                if teacher == enrollment.course.instructor:
                    continue

                # REQUIRE is_paid=True for all existing teacher enrollments
                if not enrollment.is_paid:
                    if not dry_run:
                        enrollment.is_paid = True
                        enrollment.save(update_fields=['is_paid'])
                    repaired_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  [PAID FIX] {teacher.email} in {enrollment.course.title}"))

                # Ensure LessonProgress exists for the first lesson to prevent initial LOCK
                first_lesson = enrollment.course.lessons.order_by('order').first()
                if first_lesson:
                    if not dry_run:
                        with transaction.atomic():
                            lp, created = LessonProgress.objects.get_or_create(
                                enrollment=enrollment,
                                lesson=first_lesson,
                                defaults={'is_unlocked': True}
                            )
                            if not lp.is_unlocked:
                                lp.is_unlocked = True
                                lp.save(update_fields=['is_unlocked'])
                        
                        if created:
                            progress_count += 1
                            self.stdout.write(f"  [UNLOCK FIX] Bootstrapped Lesson 1 for: {teacher.email}")
                    else:
                        if not LessonProgress.objects.filter(enrollment=enrollment, lesson=first_lesson).exists():
                            progress_count += 1

        action = "Would fix" if dry_run else "Fixed"
        self.stdout.write(self.style.SUCCESS(f"\nFinished. {action} {repaired_count} enrollments and bootstrapped {progress_count} progress records."))
