"""
Diagnostic script to test progress tracking logic
Run with: python manage.py shell < test_progress.py
"""

from courses.models import Course, Enrollment, LessonProgress

# Get a sample enrollment
enrollment = Enrollment.objects.first()

if not enrollment:
    print("❌ No enrollments found. Create a test enrollment first.")
else:
    print(f"📚 Testing enrollment: {enrollment.student.email} - {enrollment.course.title}")
    print(f"=" * 60)
    
    # Get course lessons
    lessons = enrollment.course.lessons.all()
    total_duration_minutes = sum([l.video_duration for l in lessons])
    total_duration_seconds = total_duration_minutes * 60
    
    print(f"📹 Total lessons: {lessons.count()}")
    print(f"⏱️  Total course duration: {total_duration_minutes} minutes ({total_duration_seconds} seconds)")
    print(f"=" * 60)
    
    # Get watch progress
    progress_records = LessonProgress.objects.filter(enrollment=enrollment)
    total_watched = sum([p.watch_time for p in progress_records])
    
    print(f"👁️  Watch records: {progress_records.count()}")
    print(f"⏰  Total watched: {total_watched} seconds ({total_watched/60:.1f} minutes)")
    print(f"=" * 60)
    
    # Calculate progress
    if total_duration_seconds > 0:
        raw_progress = (total_watched / total_duration_seconds) * 100
        quantized_progress = (raw_progress // 5) * 5
        
        print(f"📊 Raw progress: {raw_progress:.2f}%")
        print(f"📊 Quantized (5% steps): {quantized_progress:.0f}%")
    else:
        print("⚠️  WARNING: Total duration is 0! Set video_duration for lessons.")
    
    print(f"=" * 60)
    
    # Trigger update
    print("🔄 Triggering update_scores()...")
    enrollment.update_scores()
    enrollment.refresh_from_db()
    
    print(f"✅ Unit Progress: {enrollment.unit_progress}%")
    print(f"✅ Quiz Score: {enrollment.quiz_score}%")
    print(f"✅ Mastery Score: {enrollment.mastery_score}%")
    print(f"✅ Certificate Unlocked: {enrollment.certificate_unlocked}")
    print(f"=" * 60)
    
    # Show per-lesson breakdown
    print("\n📋 Per-Lesson Breakdown:")
    for lesson in lessons:
        prog = progress_records.filter(lesson=lesson).first()
        if prog:
            print(f"  • {lesson.title[:40]}: {prog.watch_time}s watched, Completed: {prog.is_completed}")
        else:
            print(f"  • {lesson.title[:40]}: Not started")
