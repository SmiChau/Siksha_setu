# FIXED: Quiz, Progress, and Certificate Issues

## 1. Quiz Answer Submission (Fixed)
**Root Cause:**
1. **Frontend:** `courseSlug` variable was missing in JavaScript, causing 404 errors on API calls (`/courses/undefined/submit-mcq/`).
2. **Backend:** URL/View mismatch. `urls.py` routed to a view that expected URL parameters (`lesson_id`, `question_id`), but the frontend sent them in the JSON body.
3. **Missing Method:** The old view called `enrollment.check_completion()` which does not exist in the model (`update_scores` is the correct method).

**Fixes Applied:**
- **Frontend:** Restored `const courseSlug = "{{ course.slug }}";` in `course_detail.html`.
- **Backend:** Created `submit_mcq_answer` view in `courses/views.py` that properly parses JSON body, validates input, updates scores, and returns JSON.

## 2. Progress Bar 5% Increments (Fixed)
**Root Cause:**
- **UI:** The progress circle was displaying `mastery_score` (weighted average of video + quiz), which changes slowly.
- **Requirement:** User wanted to see progress based on *watch time* increments (5% steps).

**Fixes Applied:**
- **Frontend:** Updated progress circle to display `unit_progress` instead of `mastery_score`.
- **Backend:** `unit_progress` is strictly calculated as `(video_progress // 5) * 5` in `Enrollment.update_scores()`.

## 3. Certificate Unlocking (Fixed)
**Root Cause:**
- **Dependency:** Certificate unlocking occurs inside `Enrollment.update_scores()`.
- **Failure Chain:** Since quiz submission was failing (Issue 1), `update_scores()` was never called upon quiz completion.
- **Visuals:** Frontend `updateDashboard` function correctly checks `data.certificate_unlocked`, so fixing the backend trigger automatically fixes the UI.

**Fixes Applied:**
- **Backend:** The new `submit_mcq_answer` view explicitly calls `enrollment.update_scores()`, ensuring certificate status is re-evaluated after every quiz attempt.

## 🧪 Verification Steps
1. **Hard Refresh** browser (Ctrl+Shift+R) to load new JS.
2. **Submit a Quiz:** Click "Check Answer". You should receive immediate feedback (Correct/Incorrect).
3. **Check Progress:** The circular progress bar should update in 5% increments as you watch videos.
4. **Unlock Certificate:** Complete enough videos/quizzes to reach 80% mastery. The certificate badge will appear automatically.
