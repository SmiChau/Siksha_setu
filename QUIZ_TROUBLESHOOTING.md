# QUIZ NOT SHOWING - TROUBLESHOOTING STEPS

## 🔍 **Step-by-Step Debugging**

### **Step 1: Hard Refresh Browser**
**CRITICAL:** Old JavaScript may be cached
- Windows: `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`
- Or: `Ctrl + F5`

### **Step 2: Open Browser Console**
1. Press `F12` (or right-click → Inspect)
2. Click on "Console" tab
3. Look for errors (red text)

### **Step 3: Check if lessonsData is Loaded**
In the console, type:
```javascript
lessonsData
```

**Expected Output:**
```javascript
[
  {
    id: 1,
    title: "Introduction",
    has_quiz: true,  // ← Should be true if quiz exists
    questions: [...]
  },
  ...
]
```

**If you see an error:** JavaScript didn't load properly - hard refresh again

### **Step 4: Check if Quizzes are Detected**
In the console, type:
```javascript
lessonsData.filter(l => l.has_quiz)
```

**Expected:** Should show lessons that have quizzes

**If empty array `[]`:** No quizzes configured in database

### **Step 5: Manually Trigger Quiz Rendering**
In the console, type:
```javascript
renderSidebarQuizzes()
```

**Expected:** Console should show:
```
Quiz available for lesson: Introduction
Quiz available for lesson: Getting Started
```

**If no output:** Quizzes don't exist in database

### **Step 6: Check DOM Elements**
In the console, type:
```javascript
document.querySelectorAll('.quiz-subitem')
```

**Expected:** Should show quiz elements

**If empty:** HTML structure is missing

## 🛠️ **Common Issues & Fixes**

### **Issue 1: JavaScript Errors**
**Symptom:** Red errors in console
**Fix:** 
1. Hard refresh (Ctrl+Shift+R)
2. Clear browser cache
3. Check if all template tags are correct

### **Issue 2: No Quizzes in Database**
**Symptom:** `lessonsData.filter(l => l.has_quiz)` returns `[]`
**Fix:**
1. Go to `/admin/courses/lesson/`
2. Click on a lesson
3. Scroll to "MCQ Questions" section
4. Add questions (see guide below)

### **Issue 3: Quiz Items Hidden**
**Symptom:** Elements exist but not visible
**Fix:** In console, run:
```javascript
document.querySelectorAll('.quiz-subitem').forEach(el => {
    el.classList.remove('d-none');
    console.log('Showing:', el);
});
```

### **Issue 4: Wrong Course**
**Symptom:** Viewing a course without quizzes
**Fix:** Check different course or add quizzes to current one

## 📝 **How to Add Quiz Questions**

### **Method 1: Django Admin (Recommended)**
1. Navigate to: `http://localhost:8000/admin/courses/lesson/`
2. Click on a lesson (e.g., "Introduction to HTML")
3. Scroll down to **"MCQ Questions"** section
4. Click **"Add another MCQ Question"**
5. Fill in the form:
   ```
   Question text: What does HTML stand for?
   Option A: Hyper Text Markup Language
   Option B: High Tech Modern Language
   Option C: Home Tool Markup Language
   Option D: Hyperlinks and Text Markup Language
   Correct option: A
   Explanation: HTML stands for Hyper Text Markup Language
   Order: 1
   ```
6. Click **"Save and continue editing"** to add more
7. Click **"Save"** when done

### **Method 2: Django Shell**
```python
python manage.py shell

from courses.models import Lesson, MCQQuestion

# Get a lesson
lesson = Lesson.objects.first()

# Create a question
MCQQuestion.objects.create(
    lesson=lesson,
    question_text="What is Python?",
    option_a="A programming language",
    option_b="A snake",
    option_c="A framework",
    option_d="A database",
    correct_option="A",
    explanation="Python is a high-level programming language",
    order=1
)

print(f"Quiz created for: {lesson.title}")
```

## 🧪 **Quick Test Script**

Copy this into browser console:
```javascript
// Test 1: Check if data loaded
console.log('1. Lessons loaded:', lessonsData ? 'YES' : 'NO');

// Test 2: Count lessons with quizzes
const withQuiz = lessonsData ? lessonsData.filter(l => l.has_quiz).length : 0;
console.log('2. Lessons with quizzes:', withQuiz);

// Test 3: List quiz lessons
if (lessonsData) {
    lessonsData.forEach(l => {
        if (l.has_quiz) {
            console.log(`   ✓ ${l.title} (${l.questions.length} questions)`);
        }
    });
}

// Test 4: Check DOM elements
const quizElements = document.querySelectorAll('.quiz-subitem');
console.log('3. Quiz elements in DOM:', quizElements.length);

// Test 5: Try to show them
console.log('4. Attempting to show quizzes...');
renderSidebarQuizzes();
```

## 📊 **Expected Results**

After running the test script, you should see:
```
1. Lessons loaded: YES
2. Lessons with quizzes: 3
   ✓ Introduction to HTML (2 questions)
   ✓ CSS Basics (3 questions)
   ✓ JavaScript Fundamentals (4 questions)
3. Quiz elements in DOM: 3
4. Attempting to show quizzes...
Quiz available for lesson: Introduction to HTML
Quiz available for lesson: CSS Basics
Quiz available for lesson: JavaScript Fundamentals
```

## ✅ **Success Checklist**

- [ ] Hard refreshed browser (Ctrl+Shift+R)
- [ ] No red errors in console
- [ ] `lessonsData` is defined
- [ ] At least one lesson has `has_quiz: true`
- [ ] Quiz elements exist in DOM
- [ ] `renderSidebarQuizzes()` runs without errors
- [ ] Quiz items visible in Course Content sidebar
- [ ] Can click quiz and see questions

## 🆘 **Still Not Working?**

**Share this info:**
1. What do you see in console when you type `lessonsData`?
2. What does `lessonsData.filter(l => l.has_quiz)` return?
3. Any red errors in console?
4. Which course are you viewing?
5. Screenshot of the Course Content sidebar

**Most likely cause:** No MCQ questions in database for this course
**Solution:** Add questions via Django admin as shown above
