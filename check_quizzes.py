"""
Quiz Diagnostic Script
Run with: python manage.py shell < check_quizzes.py
"""

from courses.models import Course, Lesson, MCQQuestion

print("=" * 60)
print("QUIZ DIAGNOSTIC REPORT")
print("=" * 60)

courses = Course.objects.filter(status='published')

if not courses.exists():
    print("❌ No published courses found!")
else:
    for course in courses:
        print(f"\n📚 Course: {course.title}")
        print(f"   Slug: {course.slug}")
        print("-" * 60)
        
        lessons = course.lessons.all()
        total_lessons = lessons.count()
        lessons_with_quiz = 0
        total_questions = 0
        
        for lesson in lessons:
            quiz_count = lesson.mcq_questions.count()
            total_questions += quiz_count
            
            if quiz_count > 0:
                lessons_with_quiz += 1
                print(f"   ✅ {lesson.title}")
                print(f"      └─ {quiz_count} question(s)")
            else:
                print(f"   ❌ {lesson.title}")
                print(f"      └─ NO QUIZ (add questions in admin)")
        
        print("-" * 60)
        print(f"   Summary:")
        print(f"   • Total Lessons: {total_lessons}")
        print(f"   • Lessons with Quiz: {lessons_with_quiz}")
        print(f"   • Total Questions: {total_questions}")
        
        if lessons_with_quiz == 0:
            print(f"\n   ⚠️  WARNING: No quizzes configured for this course!")
            print(f"   👉 Add questions at: /admin/courses/lesson/")

print("\n" + "=" * 60)
print("RECOMMENDATIONS:")
print("=" * 60)

if MCQQuestion.objects.count() == 0:
    print("❌ NO QUIZZES FOUND IN ENTIRE SYSTEM")
    print("\n📝 To add quizzes:")
    print("   1. Go to /admin/courses/lesson/")
    print("   2. Click on a lesson")
    print("   3. Scroll to 'MCQ Questions' section")
    print("   4. Click 'Add another MCQ Question'")
    print("   5. Fill in question, options, correct answer")
    print("   6. Save")
else:
    total_q = MCQQuestion.objects.count()
    print(f"✅ {total_q} quiz question(s) found in system")
    print("   Quizzes should appear in Course Content sidebar")
    print("   If not visible, hard refresh browser (Ctrl+Shift+R)")

print("=" * 60)
