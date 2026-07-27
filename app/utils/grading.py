"""Shared exam-grading logic.

Used by the session start/submit/grade routes AND by the read-only result/
review pages, so a question's correctness is computed exactly one way -
previously the review pages re-implemented this comparison slightly
differently (case-insensitive vs upper-case matching) from what actually
computed the stored score, so a result page could show an answer as
correct/incorrect that disagreed with the score a student was actually given.
"""


def resolve_correct_text(question):
    """A question's correct_answer is an option id/key (for mcq-style
    questions) - resolve it to the option's display text for comparison
    against the student's submitted answer (which is also option text, per
    the take-exam UI)."""
    correct_answer = question.get("correct_answer")
    correct_text = str(correct_answer).strip() if correct_answer is not None else ""
    options = question.get("options")
    if isinstance(options, list):
        for opt in options:
            if opt.get("id") == correct_answer or opt.get("key") == correct_answer:
                correct_text = str(opt.get("text", correct_answer)).strip()
                break
    return correct_text


def is_answer_correct(question, student_answer):
    if student_answer is None or student_answer == "":
        return False

    question_type = question.get("question_type", question.get("type", "mcq"))
    if question_type == "essay":
        return False

    correct_text = resolve_correct_text(question)
    return str(student_answer).strip().lower() == correct_text.lower()


def compute_score(questions_to_grade, question_order, answers_dict, manual_grades=None):
    """Marks-weighted scoring shared by the initial auto-grade at submit/timeout
    time and the manual essay-grading recompute. A question worth 5 marks
    contributes 5 points when correct, not 1 - fixing the earlier "1 mark per
    question" placeholder that ignored configured weights."""
    manual_grades = manual_grades or {}
    questions_dict = {str(q.get("_id")): q for q in questions_to_grade}

    score = 0.0
    total_marks = 0.0
    correct_count = 0
    incorrect_count = 0
    unanswered_count = 0
    has_essay = False
    all_essays_graded = True

    for q_id in question_order:
        question = questions_dict.get(q_id)
        if not question:
            continue

        marks = float(question.get("marks", 1) or 1)
        total_marks += marks
        question_type = question.get("question_type", question.get("type", "mcq"))
        student_answer = answers_dict.get(q_id)

        if question_type == "essay":
            has_essay = True
            if q_id in manual_grades:
                grade = float(manual_grades[q_id].get("score", 0) or 0)
                score += grade
                if grade > 0:
                    correct_count += 1
                else:
                    incorrect_count += 1
            else:
                all_essays_graded = False
                if not student_answer:
                    unanswered_count += 1
            continue

        if not student_answer:
            unanswered_count += 1
            continue

        if is_answer_correct(question, student_answer):
            score += marks
            correct_count += 1
        else:
            incorrect_count += 1

    score_percent = (score / total_marks * 100) if total_marks > 0 else 0
    return {
        "score": score,
        "total_marks": total_marks,
        "score_percent": score_percent,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "unanswered_count": unanswered_count,
        "has_essay": has_essay,
        "is_fully_graded": not has_essay or all_essays_graded,
    }
