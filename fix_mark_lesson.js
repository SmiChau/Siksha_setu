function markLessonComplete(lessonId) {
    if (!isEnrolled) return;

    fetch(`/courses/${courseSlug}/lesson/${lessonId}/complete/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '{{ csrf_token }}'
        },
        body: JSON.stringify({
            watch_time: Math.round(effectiveWatchTime)
        })
    })
        .then(res => {
            if (!res.ok) {
                throw new Error(`HTTP error! status: ${res.status}`);
            }
            return res.json();
        })
        .then(data => {
            if (data.success) {
                const lesson = lessonsData.find(l => l.id === lessonId);
                lesson.is_completed = data.lesson_completed;

                if (data.newly_completed) {
                    const quizItem = document.getElementById(`quiz-item-${lessonId}`);
                    if (quizItem) quizItem.classList.remove('locked');
                    console.log('✓ Lesson completed! Progress updated.');
                }
                updateDashboard(data);
            } else {
                console.error('Progress update failed:', data.error);
            }
        })
        .catch(error => {
            console.error('Watch time sync error:', error);
        });
}
