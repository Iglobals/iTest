"""Shared exam-grading logic.

Used by the session start/submit/grade routes AND by the read-only result/
review pages, so a question's correctness is computed exactly one way -
previously the review pages re-implemented this comparison slightly
differently (case-insensitive vs upper-case matching) from what actually
computed the stored score, so a result page could show an answer as
correct/incorrect that disagreed with the score a student was actually given.
"""


def resolve_option_text(question, option_id):
    """Resolves any option id/key (correct_answer, or a student's submitted
    answer - both are ids, see is_answer_correct) to that option's display
    text/HTML, for review/result pages. Falls back to the raw id string if
    no matching option is found (e.g. options changed after this attempt)."""
    text = str(option_id).strip() if option_id is not None else ""
    options = question.get("options")
    if isinstance(options, list):
        for opt in options:
            if opt.get("id") == option_id or opt.get("key") == option_id:
                text = str(opt.get("text", option_id)).strip()
                break
    return text


def resolve_correct_text(question):
    """Display text for a question's correct_answer (an option id/key)."""
    return resolve_option_text(question, question.get("correct_answer"))


def is_answer_correct(question, student_answer):
    """student_answer is the selected option's id/key (see app/templates/
    exam/take.html's radio value), compared directly against correct_answer -
    both are already the same id/key, so this never touches option TEXT.
    That's deliberate: options can now contain rich HTML (bold, sub/sup,
    Greek symbols), and text-based comparison would break the moment two
    otherwise-identical options differ only in markup, or would require
    comparing entire HTML strings verbatim."""
    if student_answer is None or student_answer == "":
        return False

    question_type = question.get("question_type", question.get("type", "mcq"))
    if question_type == "essay":
        return False

    correct_answer = question.get("correct_answer")
    return str(student_answer).strip().lower() == str(correct_answer).strip().lower()


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
