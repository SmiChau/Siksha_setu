# QUIZ SYSTEM - SETUP & TROUBLESHOOTING GUIDE

## 🎯 **How Quizzes Work**

Quizzes appear **below each lesson** in the Course Content sidebar (right side).

### **Visual Structure:**
```
Course Content
├── 📹 Lesson 1: Introduction
│   └── ❓ Quiz: Introduction        ← Appears here if quiz exists
├── 📹 Lesson 2: Getting Started
│   └── ❓ Quiz: Getting Started     ← Appears here if quiz exists
└── 📹 Lesson 3: Advanced Topics
    └── ❓ Quiz: Advanced Topics     ← Appears here if quiz exists
```

## ✅ **Fixes Applied**

### **1. Quiz Rendering on Page Load**
**Before:** Quizzes only showed if a lesson was selected
**After:** Quizzes render immediately when page loads

```javascript
// Now runs on every page load
document.addEventListener('DOMContentLoaded', () => {
    renderSidebarQuizzes();  // ✅ Always called
});
```

### **2. Error Handling**
Added null check to prevent crashes:
```javascript
if (quizItem && l.has_quiz) {  // ✅ Checks if element exists
    quizItem.classList.remove('d-none');
}
```

### **3. Debug Logging**
Added console messages to show which lessons have quizzes:
```javascript
console.log(`Quiz available for lesson: ${l.title}`);
```

## 🔍 **How to Check if Quizzes Exist**

### **Method 1: Browser Console**
1. Open browser (F12)
2. Go to Console tab
3. Look for messages like: `Quiz available for lesson: Introduction`
4. If you see these messages, quizzes are configured correctly

### **Method 2: Django Admin**
1. Go to `/admin/courses/mcqquestion/`
2. Check if questions exist for your lessons
3. Each lesson should have at least 1 question to show a quiz

### **Method 3: Check Database**
```bash
python manage.py shell
>>> from courses.models import Lesson, MCQQuestion
>>> for lesson in Lesson.objects.all():
...     quiz_count = lesson.mcq_questions.count()
...     print(f"{lesson.title}: {quiz_count} questions")
```

## 🛠️ **If Quizzes Still Don't Appear**

### **Problem: No quizzes in sidebar**

**Solution 1: Add Quiz Questions**
1. Go to Django admin: `/admin/courses/lesson/`
2. Click on a lesson
3. Scroll to "MCQ Questions" section at bottom
4. Click "Add another MCQ Question"
5. Fill in:
   - Question text
   - Options A, B, C, D
   - Correct option (A/B/C/D)
   - Order (1, 2, 3...)
6. Save

**Solution 2: Check Lesson Data**
Open browser console and run:
```javascript
console.log(lessonsData);
```
Look for `has_quiz: true` in the output. If all show `has_quiz: false`, no quizzes are configured.

**Solution 3: Hard Refresh**
- Windows: `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`

## 📝 **Creating Quizzes (Step-by-Step)**

### **Option A: Via Django Admin**
1. Navigate to `/admin/courses/lesson/`
2. Click on the lesson you want to add quiz to
3. Scroll to bottom - see "MCQ Questions" inline section
4. Click "Add another MCQ Question"
5. Fill in the form:
   ```
   Question text: What is Python?
   Option A: A programming language
   Option B: A snake
   Option C: A framework
   Option D: A database
   Correct option: A
   Explanation: Python is a high-level programming language
   Order: 1
   ```
6. Click "Save and continue editing" to add more questions
7. Click "Save" when done

### **Option B: Via Teacher Dashboard**
1. Go to `/courses/manage/`
2. Click "Edit" on your course
3. Navigate to "Step 4: Add Questions"
4. Add MCQ questions for each lesson
5. Save

## 🎨 **Quiz UI Behavior**

### **In Sidebar:**
- **Before watching:** Quiz appears below lesson (unlocked)
- **Icon:** ❓ Question mark icon
- **Text:** "Quiz: [Lesson Name]"
- **Click:** Opens quiz interface in main area

### **In Main Area:**
- **Title:** "Quiz" at top
- **Questions:** Numbered list (1, 2, 3...)
- **Options:** Radio buttons (A, B, C, D)
- **Button:** "Check Answer" for each question
- **Feedback:** 
  - ✓ Correct! [explanation]
  - ✗ Incorrect. Correct answer: [X]

## 🧪 **Testing Checklist**

1. ✅ **Hard refresh browser** (Ctrl+Shift+R)
2. ✅ **Open console** (F12) - check for "Quiz available" messages
3. ✅ **Look at Course Content sidebar** (right side)
4. ✅ **See quiz items** below lessons with questions
5. ✅ **Click on a quiz** - should open in main area
6. ✅ **Select an answer** and click "Check Answer"
7. ✅ **See feedback** (✓ or ✗)
8. ✅ **Check progress** updates after correct answers

## 📊 **Expected Console Output**

When page loads, you should see:
```
Quiz available for lesson: Introduction to Python
Quiz available for lesson: Variables and Data Types
Quiz available for lesson: Control Flow
```

If you see NO messages, it means:
- No MCQ questions are configured for any lessons
- Need to add questions via Django admin

## 🚀 **Quick Fix Summary**

**If quizzes don't appear:**
1. Check console for "Quiz available" messages
2. If none, add MCQ questions in Django admin
3. Hard refresh browser
4. Quizzes should appear below lessons in sidebar
5. Click quiz to open, select answer, click "Check Answer"
6. Progress updates automatically

**Everything is now configured to work!** Just need to ensure MCQ questions exist in the database.
