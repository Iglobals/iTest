# Exam Versioning & Grading System

## Overview

The iTEST platform now implements a comprehensive exam versioning system that ensures students can always view their results accurately, even if the examiner modifies the exam after they've taken it.

---

## Key Features

### 1. **Exam Versioning (Question Snapshots)**

When a student starts an exam session, the system creates a **deep copy** of all exam questions at that moment and stores it in the session as `question_snapshot`.

**Why this matters:**
- Examiners can update public exams (add/remove/modify questions)
- Students who took the old version can still view their correct results
- New students taking the exam see the updated version
- No data loss or result corruption

**Implementation:**
```python
# In /api/sessions/start
question_snapshot = []
for q in questions:
    question_snapshot.append({
        "_id": str(q.get("_id")),
        "text": q.get("text"),
        "question_type": q.get("question_type"),
        "options": q.get("options", []),
        "correct_answer": q.get("correct_answer"),
        "explanation": q.get("explanation"),
        "marks": q.get("marks", 1),
        "image_url": q.get("image_url")
    })

new_session = {
    ...
    "question_snapshot": question_snapshot,  # Frozen at time of taking
    ...
}
```

---

### 2. **Grading System**

#### **Automatic Grading (MCQ, True/False, Short Answer)**

When a student submits an exam, the system:
1. Uses the `question_snapshot` (not live exam questions)
2. Compares student answers with correct answers
3. Calculates score, percentage, pass/fail
4. Stores result in PostgreSQL `exam_scores` table

**Question Types Handled:**
- **MCQ**: Exact match (case-insensitive)
- **True/False**: Exact match
- **Short Answer**: Trimmed, case-insensitive match
- **Numerical**: Exact match
- **Essay/AC**: Flagged for manual grading

#### **Manual Grading (Essay/AC Questions)**

Essays are marked as "requires manual grading" and:
- Show as "Pending Review" in student results
- Teacher must manually review and score
- Once graded, teacher can publish results

---

### 3. **Retake Logic**

#### **Configuration Options:**
- `allow_retake`: Boolean - if true, unlimited retakes
- `max_attempts`: Number - guideline counter (not enforced if retakes allowed)

#### **Logic:**
```python
if attempts == 0:
    # Never taken - always show
    show_exam = True
elif allow_retake:
    # Retakes allowed - show regardless of max_attempts
    show_exam = True
elif attempts < max_attempts:
    # Retakes not allowed - only show if under limit
    show_exam = True
```

**Example Scenarios:**
- **Public Exam** (`allow_retake=true`, `max_attempts=1`): Student can retake unlimited times
- **Private Exam** (`allow_retake=false`, `max_attempts=3`): Student can take max 3 times
- **Quiz** (`allow_retake=true`, `max_attempts=999`): Unlimited practice

---

### 4. **Results Display**

Students viewing results will see:
- Overall score (percentage, pass/fail)
- Question-by-question breakdown
- Their answer vs correct answer
- Whether each answer was correct/incorrect/pending
- Explanation for each question (if provided)

**Data Source:** `session.question_snapshot` (NOT `exam.questions`)

---

## Database Schema

### MongoDB: `exam_sessions`

```javascript
{
  "_id": ObjectId,
  "exam_id": ObjectId,
  "student_id": ObjectId,
  "attempt_number": 1,
  "status": "in_progress | submitted | timed_out",
  "started_at": ISODate,
  "submitted_at": ISODate,
  "time_remaining_seconds": 3600,
  "answers": [
    {
      "question_id": "string",
      "selected_option": "A",
      "answered_at": ISODate
    }
  ],
  "question_order": ["q_id_1", "q_id_2", ...],
  "question_snapshot": [  // ⭐ NEW: Frozen questions
    {
      "_id": "q_id_1",
      "text": "What is 2+2?",
      "question_type": "mcq",
      "options": [{"key": "A", "text": "4"}, ...],
      "correct_answer": "A",
      "explanation": "Basic arithmetic",
      "marks": 1
    }
  ],
  "proctoring_flags": [],
  "created_at": ISODate,
  "updated_at": ISODate
}
```

### PostgreSQL: `exam_scores`

```sql
CREATE TABLE exam_scores (
  id              BIGSERIAL PRIMARY KEY,
  session_id      TEXT NOT NULL UNIQUE,
  exam_id         TEXT NOT NULL,
  student_id      TEXT NOT NULL,
  score           NUMERIC(10, 2) NOT NULL,
  total_marks     NUMERIC(10, 2) NOT NULL,
  score_percent   NUMERIC(5, 2) NOT NULL,
  passed          BOOLEAN NOT NULL,
  correct_count   INT,
  incorrect_count INT,
  unanswered_count INT,
  submitted_at    TIMESTAMPTZ NOT NULL
);
```

---

## Exam Types & Workflows

### A. **Purely MCQ Exams**

**Teacher Setup:**
1. Create exam with only MCQ/True-False questions
2. Set `show_result_immediately = true`
3. Publish exam

**Student Flow:**
1. Takes exam
2. Submits
3. **Immediately sees results** (auto-graded)

**Teacher:** Can review submissions but results already published

---

### B. **Purely Essay/AC Exams**

**Teacher Setup:**
1. Create exam with only essay questions
2. Set `show_result_immediately = false`
3. Publish exam

**Student Flow:**
1. Takes exam
2. Submits
3. Sees "Results pending manual grading" message

**Teacher Flow:**
1. Goes to Exam Submissions page
2. Reads each essay response
3. Assigns score for each essay
4. Marks as "graded"
5. Publishes results

**Student:** Can now view results

---

### C. **Mixed (MCQ + Essay) Exams**

**Teacher Setup:**
1. Create exam with both MCQ and essay questions
2. Set `show_result_immediately = false`
3. Publish exam

**Student Flow:**
1. Takes exam
2. Submits
3. Sees "Results pending review" message

**System:**
- Auto-grades MCQ portion
- Flags essays as "needs manual grading"

**Teacher Flow:**
1. Goes to Exam Submissions page
2. Sees MCQ score already calculated
3. Reviews and grades essay portions
4. Marks overall exam as "graded"
5. Publishes results

**Student:** Can now view complete results

---

## API Endpoints

### Start Session
```http
POST /api/sessions/start
Body: { "exam_id": "..." }
Response: { "success": true, "data": { "session_id": "...", ... } }
```
- Creates session with `question_snapshot`
- Randomizes if enabled
- Returns first question

### Submit Session
```http
POST /api/sessions/<session_id>/submit
Body: { "answers": [...] }
Response: { "success": true, "score_percent": 80, "passed": true }
```
- Uses `question_snapshot` for grading
- Auto-grades MCQ/True-False/Short Answer
- Flags essays for manual grading
- Stores in PostgreSQL `exam_scores`

### View Results
```http
GET /dashboard/sessions/<session_id>/result
Response: Renders result.html with breakdown
```
- Uses `session.question_snapshot` for display
- Shows correct/incorrect for each question
- Shows explanations

---

## Future Enhancements

### 1. **Manual Grading Interface**
- Teacher dashboard to review essay submissions
- Inline grading with rubrics
- Bulk actions (grade all, publish all)

### 2. **Question Draft Status**
- Questions marked as "draft" excluded from published exams
- Only "published" questions appear in exams
- Prevents accidental inclusion of unfinished questions

### 3. **Weighted Scoring**
- Different marks per question
- Partial credit for essay questions
- Score normalization

### 4. **Analytics**
- Question difficulty analysis
- Student performance trends
- Subject-wise breakdown

---

## Testing Checklist

### Exam Versioning
- [ ] Student takes exam v1
- [ ] Teacher updates exam (adds/modifies questions)
- [ ] Student views old result → sees v1 questions
- [ ] New student takes exam → sees v2 questions
- [ ] Both results display correctly

### Grading
- [ ] MCQ auto-graded correctly
- [ ] True/False auto-graded correctly
- [ ] Essay flagged for manual grading
- [ ] Mixed exam: MCQ auto-graded, essay pending
- [ ] Score calculation matches expected

### Retakes
- [ ] `allow_retake=false`, `max_attempts=1` → student cannot retake
- [ ] `allow_retake=true`, `max_attempts=1` → student can retake unlimited
- [ ] Exam shows in "Available" after retake
- [ ] All attempts tracked separately

### Submit Button
- [ ] Shows "Submitting..." spinner
- [ ] Button disabled during submit
- [ ] Re-enables on error
- [ ] Shows success message on completion

---

## Troubleshooting

### Results show wrong questions
**Cause:** Using `exam.questions` instead of `session.question_snapshot`  
**Fix:** Always use `session.question_snapshot` in grading and results

### Retake not showing despite allow_retake=true
**Cause:** Logic checking `attempts < max_attempts` when retakes allowed  
**Fix:** If `allow_retake=true`, show regardless of attempts

### Submit button can be clicked multiple times
**Cause:** No disabled state or loading indicator  
**Fix:** Add `pendingSubmit` flag and disable button during submission

### Essay questions auto-graded incorrectly
**Cause:** System trying to match essay text to "correct_answer"  
**Fix:** Check `question_type == 'essay'` and flag for manual grading

---

## Code References

- **Session Start:** `app/sessions/routes.py:start_session()`
- **Grading Logic:** `app/sessions/routes.py:submit_session()`
- **Results Display:** `app/dashboard/routes.py:view_result()`
- **Retake Logic:** `app/dashboard/routes.py:my_exams()`
- **Submit UI:** `app/templates/exam/take.html` (JavaScript section)

---

**Last Updated:** June 30, 2026  
**Version:** 1.0.0
