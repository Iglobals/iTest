# Grading System Implementation

## Overview

This document describes the comprehensive grading system implementation for iTEST, including teacher grading interfaces, manual essay grading, result publishing controls, and responsive UI design.

---

## New Features Implemented

### 1. **Exam Submissions Page** (`/dashboard/exams/<slug>/submissions`)

Teachers can view all student submissions for an exam:

**Features:**
- Grid view of all submissions with student info
- Filter by status: All, Pending Grading, Graded, Published
- Display score percentage for each submission
- Quick actions: Grade and View buttons
- Bulk action: Publish All Results button
- Responsive layout using CSS Grid with `auto-fit`

**File:** `app/templates/dashboard/mark_exams.html`

**Route:** `app/dashboard/routes.py::exam_submissions(slug)`

---

### 2. **Manual Grading Interface** (`/dashboard/sessions/<session_id>/grade`)

Teachers can manually grade essay questions and provide feedback:

**Features:**
- Student banner with avatar and info
- Score overview showing current results
- Auto-graded questions displayed with correct/incorrect status
- Essay questions with grading form:
  - Score input (with max marks validation)
  - Feedback textarea
- Save Grades button (saves without publishing)
- Save & Publish button (saves and makes results visible to student)
- Responsive design with `clamp()` for spacing and font sizes

**File:** `app/templates/dashboard/grade_submission.html`

**Route:** `app/dashboard/routes.py::grade_submission(session_id)`

---

### 3. **Backend API Endpoints**

#### **POST `/api/sessions/<session_id>/grade`**
- Accepts manual grades for essay questions
- Recalculates total score including essay marks
- Updates PostgreSQL `exam_scores` table
- Optionally publishes results

**Request Body:**
```json
{
  "grades": [
    {
      "question_id": "q_id_1",
      "score": 8.5,
      "feedback": "Great analysis! Could improve conclusion."
    }
  ],
  "publish": true
}
```

**Implementation:** `app/sessions/routes.py::grade_session()`

#### **POST `/api/sessions/<session_id>/publish-results`**
- Publishes results for a single session
- Makes results visible to student

**Implementation:** `app/sessions/routes.py::publish_results()`

#### **POST `/api/exams/<exam_id>/publish-all-results`**
- Bulk publishes all graded submissions for an exam
- Only publishes submissions where `is_graded=True` and `results_published=False`

**Implementation:** `app/exams/routes.py::publish_all_results()`

---

### 4. **Database Schema Updates**

#### **New Columns in `exam_scores` Table:**

```sql
is_graded BOOLEAN DEFAULT FALSE
results_published BOOLEAN DEFAULT FALSE
```

**Purpose:**
- `is_graded`: Indicates whether manual grading is complete for essay questions
- `results_published`: Controls whether student can view their results

#### **New Field in MongoDB `exam_sessions` Collection:**

```javascript
manual_grades: {
  "question_id_1": {
    "score": 8.5,
    "feedback": "Great work!",
    "graded_at": ISODate,
    "graded_by": ObjectId
  }
}
```

**Migration File:** `migrations/add_grading_fields.sql`

---

### 5. **Updated Results Display**

Students can now see:
- Overall score (only if results are published)
- Question-by-question breakdown
- For essay questions: Awarded marks and teacher feedback
- "Results pending" message if not yet published

**Updated File:** `app/templates/exam/result.html`

**Updated Route:** `app/dashboard/routes.py::view_result()`

**Changes:**
- Added check for `results_published` before showing results to students
- Display manual grades and feedback for essay questions
- Teachers can always view results regardless of publish status

---

### 6. **Auto-Publish Logic**

**On Exam Submission:**
- If exam has `show_result_immediately=true` AND all questions are auto-gradable (MCQ/True-False):
  - Set `results_published=true`
  - Student sees results immediately

- If exam has essay questions:
  - Set `results_published=false`
  - Student sees "Results pending manual grading" message
  - Teacher must grade and publish

**Updated:** `app/sessions/routes.py::submit_session()`

---

## Responsive Design Implementation

All grading interfaces follow the three CSS responsive techniques requested:

### 1. **Auto-Fit Grid**
```css
.submissions-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: clamp(1rem, 3vw, 1.5rem);
}
```

### 2. **Flexible Widths**
```css
.form-input {
    width: 100%;
    max-width: 100%;
    padding: clamp(0.5rem, 1.5vw, 0.75rem);
}
```

### 3. **Clamp for Scaling**
```css
.grading-header {
    padding: clamp(1rem, 3vw, 1.5rem);
    margin-bottom: clamp(1rem, 3vw, 2rem);
}

.student-details h4 {
    font-size: clamp(0.95rem, 2.5vw, 1.05rem);
}
```

---

## Workflows

### A. **Purely MCQ Exam (Auto-Grade Only)**

1. **Teacher:** Creates exam with MCQ/True-False questions, enables `show_result_immediately`
2. **Student:** Takes exam and submits
3. **System:** Auto-grades, sets `results_published=true`
4. **Student:** Sees results immediately
5. **Teacher:** Can view submissions but no manual grading needed

---

### B. **Essay-Only Exam (Manual Grading Required)**

1. **Teacher:** Creates exam with essay questions, disables `show_result_immediately`
2. **Student:** Takes exam and submits
3. **System:** Sets `results_published=false`, `is_graded=false`
4. **Student:** Sees "Results pending manual grading" message
5. **Teacher:**
   - Goes to Submissions page
   - Clicks "Grade" button
   - Reviews essay responses
   - Assigns scores and feedback
   - Clicks "Save & Publish"
6. **System:** Sets `is_graded=true`, `results_published=true`
7. **Student:** Can now view results with teacher feedback

---

### C. **Mixed Exam (MCQ + Essay)**

1. **Teacher:** Creates exam with both MCQ and essay questions
2. **Student:** Takes exam and submits
3. **System:**
   - Auto-grades MCQ portion
   - Sets `results_published=false` (essays need grading)
4. **Student:** Sees "Results pending review" message
5. **Teacher:**
   - Goes to Submissions page
   - Sees partial score from auto-graded questions
   - Clicks "Grade" button
   - Reviews essay responses only
   - Assigns scores for essays
   - Clicks "Save & Publish"
6. **System:**
   - Recalculates total score (MCQ + essay marks)
   - Updates percentage and pass/fail status
   - Sets `is_graded=true`, `results_published=true`
7. **Student:** Can now view complete results

---

## Theme Compliance

All UI elements match the existing iTEST theme:

**Colors:**
- Primary Purple: `#6B21A8` (var(--purple))
- Gold/Accent: `#F59E0B` (var(--gold))
- Success: Green tones
- Danger: Red tones
- Gray scale: `var(--gray-50)` through `var(--gray-900)`

**Reused Components:**
- `.btn-primary`, `.btn-outline` button styles
- `.form-input` text input styles
- `.status-badge` for status indicators
- `.card` style for containers
- Lucide icons for consistency

**No Emojis:** All icons use Lucide icon library

---

## File Structure

```
app/
├── templates/
│   └── dashboard/
│       ├── mark_exams.html          # Submissions list page
│       └── grade_submission.html     # Manual grading interface
├── dashboard/
│   └── routes.py                     # Added exam_submissions() and grade_submission()
├── sessions/
│   └── routes.py                     # Added grade_session() and publish_results()
├── exams/
│   └── routes.py                     # Added publish_all_results()
└── models.py                         # Updated ExamScore model

migrations/
└── add_grading_fields.sql            # Database migration for new columns
```

---

## Testing Checklist

### Manual Grading
- [ ] Teacher can access submissions page from exam details
- [ ] Submissions page shows all student attempts
- [ ] Filter by status works (All, Pending, Graded, Published)
- [ ] Grade button opens grading interface
- [ ] Auto-graded questions show correct/incorrect status
- [ ] Essay questions show grading form
- [ ] Score input validates max marks
- [ ] Save Grades button saves without publishing
- [ ] Save & Publish button saves and publishes results
- [ ] Bulk Publish All button works

### Result Publishing
- [ ] Student cannot see unpublished results
- [ ] Student sees "pending grading" message before publish
- [ ] Student can view published results
- [ ] Results show manual grades and feedback for essays
- [ ] Teacher can always view results regardless of publish status

### Responsive Design
- [ ] Submissions grid adapts to screen size
- [ ] Grading interface readable on mobile
- [ ] All spacing scales smoothly
- [ ] Font sizes use clamp() and are readable on all devices
- [ ] No horizontal scrolling on narrow screens

### Backward Compatibility
- [ ] Old exam sessions without `manual_grades` still display
- [ ] Existing scores display correctly
- [ ] Migration adds fields without breaking existing data

---

## Migration Instructions

1. **Run Database Migration:**
```bash
psql -U your_user -d itest_db -f migrations/add_grading_fields.sql
```

2. **Restart Application:**
```bash
# On Windows
python run.py

# On Linux/Mac
python3 run.py
```

3. **Verify:**
- Check that existing exam results still display
- Create a test exam with essay questions
- Grade a submission and verify publish works

---

## Future Enhancements

### 1. **Rubric-Based Grading**
- Define scoring rubrics for essay questions
- Structured grading with criteria breakdown
- Partial credit assignment

### 2. **Question Draft Status**
- Add `status` field to questions (draft/published)
- Filter out draft questions when starting exam
- UI toggle in exam builder to mark questions as published

### 3. **Grading Analytics**
- Average time to grade per essay
- Inter-rater reliability if multiple graders
- Question difficulty based on scores

### 4. **Batch Grading**
- Grade same question across all submissions
- Copy feedback to similar answers
- Keyboard shortcuts for faster grading

### 5. **Student Notifications**
- Email/push notification when results published
- Notification badge in dashboard
- Grade improvement suggestions

---

## API Documentation

### Grade Session
```http
POST /api/sessions/<session_id>/grade
Content-Type: application/json
Authorization: Bearer <token>

{
  "grades": [
    {
      "question_id": "string",
      "score": number,
      "feedback": "string"
    }
  ],
  "publish": boolean
}

Response 200:
{
  "success": true,
  "score": number,
  "total_marks": number,
  "score_percent": number,
  "passed": boolean
}
```

### Publish Results
```http
POST /api/sessions/<session_id>/publish-results
Authorization: Bearer <token>

Response 200:
{
  "success": true
}
```

### Bulk Publish
```http
POST /api/exams/<exam_id>/publish-all-results
Authorization: Bearer <token>

Response 200:
{
  "success": true,
  "count": number,
  "message": "Published X result(s)"
}
```

---

## Security Considerations

1. **Authorization:**
   - Only teachers/admins can access grading interfaces
   - Students can only view their own published results
   - Session ownership verified before grading

2. **Data Validation:**
   - Score must be between 0 and max marks
   - Feedback length limited (server-side validation recommended)
   - Question IDs validated against session

3. **Audit Trail:**
   - `graded_by` field stores teacher ID
   - `graded_at` timestamp for accountability
   - All grade changes logged in session updates

---

**Implementation Date:** June 30, 2026  
**Version:** 1.0.0  
**Status:** Complete and Ready for Testing
