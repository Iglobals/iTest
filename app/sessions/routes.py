from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_auth
from app.utils.mongo import get_collection
from app.utils.access import is_exam_open_now, can_student_access_exam, get_active_class_ids_for_student, parse_dt
from app.utils.grading import compute_score
from app.extensions import db
from app.models import ExamScore
from datetime import datetime, timedelta
from bson import ObjectId
import random

sessions_bp = Blueprint('sessions', __name__, url_prefix='/api/sessions')


def _finalize_session(session, exam, reason="submitted"):
    """Grade whatever is saved on the session and close it out. Used both by
    an explicit student submit and by the timeout guard below - there is only
    one grading code path so the two can't compute different scores."""
    sessions_col = get_collection('exam_sessions')
    tags_col = get_collection('subject_tags')

    questions_to_grade = session.get("question_snapshot") or exam.get("questions", [])
    question_order = session.get("question_order", [])
    answers_dict = {
        a.get("question_id"): a.get("selected_option")
        for a in session.get("answers", []) if a.get("question_id")
    }

    result = compute_score(questions_to_grade, question_order, answers_dict)

    # Grading rules are frozen at attempt-start so a later settings change
    # (pass mark, instant-results toggle, duration) can't retroactively alter
    # an already-taken attempt's outcome.
    settings_snapshot = session.get("settings_snapshot") or {}
    live_settings = exam.get("settings", {}) or {}
    pass_mark = settings_snapshot.get("pass_mark_percent", live_settings.get("pass_mark_percent", 50))
    duration_minutes = settings_snapshot.get("duration_minutes", live_settings.get("duration_minutes", 60))
    show_result_immediately = settings_snapshot.get("show_result_immediately", live_settings.get("show_result_immediately", False))

    passed = result["score_percent"] >= pass_mark

    started_at = session.get("started_at")
    if isinstance(started_at, datetime):
        elapsed = (datetime.utcnow() - started_at).total_seconds()
    else:
        elapsed = duration_minutes * 60
    time_spent = max(0, min(elapsed, duration_minutes * 60))

    subject_name = "General"
    if exam.get("subject_tag_id"):
        tag = tags_col.find_one({"_id": exam["subject_tag_id"]})
        if tag:
            subject_name = tag.get("name", "General")

    class_ids = exam.get("visibility", {}).get("class_ids") or []

    new_score = ExamScore(
        session_id=str(session["_id"]),
        exam_id=str(exam["_id"]),
        student_id=str(session["student_id"]),
        organization_id=str(exam["organization_id"]) if exam.get("organization_id") else None,
        class_id=str(class_ids[0]) if class_ids else None,
        subject_tag_id=str(exam["subject_tag_id"]) if exam.get("subject_tag_id") else None,
        subject_tag_name=subject_name,
        exam_title=exam["title"],
        attempt_number=session["attempt_number"],
        score=result["score"],
        total_marks=result["total_marks"],
        score_percent=result["score_percent"],
        passed=passed,
        time_spent_secs=int(time_spent),
        total_questions=len(question_order),
        correct_count=result["correct_count"],
        incorrect_count=result["incorrect_count"],
        unanswered_count=result["unanswered_count"],
        is_graded=result["is_fully_graded"],
        results_published=(show_result_immediately if result["is_fully_graded"] else False),
        submitted_at=datetime.utcnow()
    )
    db.session.add(new_score)
    db.session.commit()

    sessions_col.update_one(
        {"_id": session["_id"]},
        {"$set": {
            "status": "timed_out" if reason == "timeout" else "submitted",
            "submitted_at": datetime.utcnow(),
        }}
    )
    return result, passed


def ensure_session_not_expired(session, exam):
    """Lazily close out a session once its deadline has passed - checked at
    the top of every route that touches an in-progress session. There's no
    background worker in this app, so this is what actually enforces the
    strict time limit: the first request (sync, submit, or a resume attempt)
    that arrives after the deadline grades and freezes whatever was last
    saved, rather than trusting the client to call submit on time."""
    if session.get("status") != "in_progress":
        return session
    deadline = session.get("deadline")
    if deadline and datetime.utcnow() > deadline:
        _finalize_session(session, exam, reason="timeout")
        session = dict(session)
        session["status"] = "timed_out"
    return session


@sessions_bp.route('/start', methods=['POST'])
@require_auth()
def start_session():
    data = request.json or {}
    exam_id = data.get("exam_id")

    if not exam_id:
        return jsonify({"error": "exam_id required"}), 400

    exams_col = get_collection('exams')
    sessions_col = get_collection('exam_sessions')

    try:
        exam_obj_id = ObjectId(exam_id)
    except Exception:
        return jsonify({"error": "Invalid exam_id"}), 400

    exam = exams_col.find_one({"_id": exam_obj_id})
    if not exam or exam.get("status") == "deleted":
        return jsonify({"error": "Exam not found"}), 404

    student_id = g.current_user["_id"]

    # Resume an in-progress session if one exists (closing it out first if its
    # deadline already passed, then falling through to start a fresh attempt).
    existing_session = sessions_col.find_one({
        "exam_id": exam_obj_id,
        "student_id": student_id,
        "status": "in_progress"
    })

    if existing_session:
        existing_session = ensure_session_not_expired(existing_session, exam)
        if existing_session["status"] == "in_progress":
            existing_session["_id"] = str(existing_session["_id"])
            existing_session["exam_id"] = str(existing_session["exam_id"])
            existing_session["student_id"] = str(existing_session["student_id"])
            return jsonify({"success": True, "message": "Resumed existing session", "data": existing_session}), 200

    # A brand new attempt requires: the exam is published, we're inside its
    # scheduling window, and the student is actually granted access (public,
    # class membership, or a direct email grant) - not just that it happens
    # to appear on their dashboard listing.
    if exam.get("status") != "published":
        return jsonify({"error": "This exam is not currently available."}), 403

    if not is_exam_open_now(exam):
        return jsonify({"error": "This exam is not open at this time."}), 403

    user_email = g.current_user.get("email", "")
    class_ids = get_active_class_ids_for_student(student_id)
    if not can_student_access_exam(exam, user_email, class_ids):
        return jsonify({"error": "You do not have access to this exam."}), 403

    # Check max attempts
    settings = exam.get("settings", {})
    allow_retake = settings.get("allow_retake", False)
    max_attempts = settings.get("max_attempts", 1)

    previous_attempts = sessions_col.count_documents({
        "exam_id": exam_obj_id,
        "student_id": student_id,
        "status": {"$in": ["submitted", "timed_out"]}
    })

    if not allow_retake and previous_attempts >= max_attempts:
        return jsonify({"error": f"Max attempts ({max_attempts}) reached"}), 403

    duration = settings.get("duration_minutes", 60)

    # Generate randomized question order
    # CRITICAL: Only include published questions (exclude drafts)
    all_questions = exam.get("questions", [])
    questions = [q for q in all_questions if q.get("status") != "draft"]

    if not questions:
        return jsonify({"error": "This exam has no published questions yet"}), 400

    if settings.get("randomize_questions", False):
        random.shuffle(questions)

    # CRITICAL: Create a deep copy/snapshot of questions at the time of taking
    # This ensures results can be viewed even if exam questions change later
    question_snapshot = []
    for q in questions:
        question_snapshot.append({
            "_id": str(q.get("_id")),
            "text": q.get("text"),
            "question_type": q.get("question_type", q.get("type", "mcq")),
            "options": q.get("options", []),
            "correct_answer": q.get("correct_answer"),
            "explanation": q.get("explanation", ""),
            "marks": q.get("marks", 1),
            "image_url": q.get("image_url")
        })

    question_order = [str(q.get("_id", i)) for i, q in enumerate(questions)]

    started_at = datetime.utcnow()
    deadline = started_at + timedelta(minutes=duration)
    available_until = parse_dt(exam.get("schedule", {}).get("available_until"))
    if available_until and available_until < deadline:
        deadline = available_until

    new_session = {
        "exam_id": exam_obj_id,
        "student_id": student_id,
        "attempt_number": previous_attempts + 1,
        "status": "in_progress",
        "started_at": started_at,
        "deadline": deadline,
        "submitted_at": None,
        "time_remaining_seconds": duration * 60,
        "answers": [],
        "proctoring_flags": [],
        "question_order": question_order,
        "question_snapshot": question_snapshot,  # Store questions at time of taking
        # Grading rules frozen at attempt-start - see _finalize_session.
        "settings_snapshot": {
            "duration_minutes": duration,
            "pass_mark_percent": settings.get("pass_mark_percent", 50),
            "show_result_immediately": settings.get("show_result_immediately", False),
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    result = sessions_col.insert_one(new_session)
    new_session["_id"] = str(result.inserted_id)
    new_session["exam_id"] = str(exam_id)
    new_session["student_id"] = str(student_id)

    return jsonify({"success": True, "data": new_session}), 201


# Each violation "type" has its own independent count and threshold, so an AI
# proctoring warning never contributes to (or is diluted by) the tab-switch
# count and vice versa. A type in HARD_FLAG_TYPES force-submits on its very
# first occurrence, no threshold needed.
FLAG_THRESHOLDS = {
    "tab_switch": 3,
    "ai_vision_warning": 5,
    "ai_audio_flag": 5,
}
HARD_FLAG_TYPES = {"ai_vision_cheating"}


def _push_flag(session_obj_id, flag_type, extra=None):
    """Record one violation of `flag_type` on the session and report back
    whether this type has now crossed its own threshold. Shared by the
    student-reported /flag endpoint and the AI proctoring routes below so
    there is exactly one counting rule, not two copies of it."""
    sessions_col = get_collection('exam_sessions')
    flag_entry = {
        "type": flag_type,
        "timestamp": datetime.utcnow().isoformat(),
        "logged_at": datetime.utcnow(),
        **(extra or {}),
    }
    sessions_col.update_one(
        {"_id": session_obj_id},
        {"$push": {"proctoring_flags": flag_entry}}
    )
    updated_session = sessions_col.find_one({"_id": session_obj_id})
    all_flags = updated_session.get("proctoring_flags", [])
    type_count = sum(1 for f in all_flags if f.get("type") == flag_type)
    max_flags = FLAG_THRESHOLDS.get(flag_type, 3)
    force_submit = flag_type in HARD_FLAG_TYPES or type_count >= max_flags
    return {"flag_count": type_count, "max_flags": max_flags, "force_submit": force_submit}


@sessions_bp.route('/<session_id>/flag', methods=['POST'])
@require_auth()
def flag_violation(session_id):
    """Log proctoring violations like tab switches."""
    data = request.json or {}
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')

    try:
        session_obj_id = ObjectId(session_id)
        session = sessions_col.find_one({"_id": session_obj_id})

        if not session or session["student_id"] != g.current_user["_id"]:
            return jsonify({"error": "Session not found or unauthorized"}), 404

        exam = exams_col.find_one({"_id": session["exam_id"]})
        session = ensure_session_not_expired(session, exam) if exam else session

        if session["status"] != "in_progress":
            return jsonify({"error": "Session is already closed"}), 400

        outcome = _push_flag(session_obj_id, data.get("type", "tab_switch"))
        return jsonify({"success": True, **outcome}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@sessions_bp.route('/<session_id>/proctor/vision', methods=['POST'])
@require_auth()
def proctor_vision(session_id):
    """Receives one webcam frame, forwards it to the anticheat service, and
    turns the classification into a session flag when warranted. A single
    'cheating' verdict force-submits immediately; 'might_be_cheating' counts
    toward the 5-warning cap; 'not_cheating' is a no-op."""
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')

    try:
        session_obj_id = ObjectId(session_id)
    except Exception:
        return jsonify({"error": "Invalid session_id"}), 400

    session = sessions_col.find_one({"_id": session_obj_id})
    if not session or session["student_id"] != g.current_user["_id"]:
        return jsonify({"error": "Session not found or unauthorized"}), 404

    exam = exams_col.find_one({"_id": session["exam_id"]})
    session = ensure_session_not_expired(session, exam) if exam else session
    if session["status"] != "in_progress":
        return jsonify({"error": "Session is already closed", "expired": True}), 400

    image = request.files.get('image')
    if not image or not image.filename:
        return jsonify({"error": "image file required"}), 400

    from app.utils.proctoring_client import classify_frame, ProctoringServiceError
    try:
        result = classify_frame(session_id, image.read(), image.filename)
    except ProctoringServiceError:
        # Fail open: the AI service being unreachable should never block or
        # penalize a student mid-exam.
        return jsonify({"classification": "unavailable", "force_submit": False}), 200

    classification = result.get("frame_classification")

    if classification == "cheating":
        outcome = _push_flag(session_obj_id, "ai_vision_cheating", {"confidence": result.get("confidence")})
    elif classification == "might_be_cheating":
        outcome = _push_flag(session_obj_id, "ai_vision_warning", {"confidence": result.get("confidence")})
    else:
        outcome = {"flag_count": 0, "max_flags": FLAG_THRESHOLDS["ai_vision_warning"], "force_submit": False}

    return jsonify({"classification": classification, **outcome}), 200


@sessions_bp.route('/<session_id>/proctor/audio', methods=['POST'])
@require_auth()
def proctor_audio(session_id):
    """Receives one audio slice (only sent by the client when it detected a
    sustained loud sound, not every flimsy noise), forwards it to the
    anticheat service, and flags the session if the transcript matched a
    known answer-leakage phrase."""
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')

    try:
        session_obj_id = ObjectId(session_id)
    except Exception:
        return jsonify({"error": "Invalid session_id"}), 400

    session = sessions_col.find_one({"_id": session_obj_id})
    if not session or session["student_id"] != g.current_user["_id"]:
        return jsonify({"error": "Session not found or unauthorized"}), 404

    exam = exams_col.find_one({"_id": session["exam_id"]})
    session = ensure_session_not_expired(session, exam) if exam else session
    if session["status"] != "in_progress":
        return jsonify({"error": "Session is already closed", "expired": True}), 400

    audio = request.files.get('audio')
    if not audio or not audio.filename:
        return jsonify({"error": "audio file required"}), 400

    from app.utils.proctoring_client import classify_audio, ProctoringServiceError
    try:
        result = classify_audio(session_id, audio.read(), audio.filename)
    except ProctoringServiceError:
        return jsonify({"speech_detected": False, "force_submit": False}), 200

    keyword_flags = result.get("keyword_flags") or []

    if keyword_flags:
        outcome = _push_flag(session_obj_id, "ai_audio_flag", {"keyword_flags": keyword_flags})
    else:
        outcome = {"flag_count": 0, "max_flags": FLAG_THRESHOLDS["ai_audio_flag"], "force_submit": False}

    return jsonify({
        "speech_detected": result.get("speech_detected", False),
        "keyword_flags": keyword_flags,
        **outcome
    }), 200


@sessions_bp.route('/<session_id>/sync', methods=['PUT'])
@require_auth()
def sync_session(session_id):
    """Called periodically by frontend to save answers and flags without submitting."""
    data = request.json or {}
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')

    try:
        session_obj_id = ObjectId(session_id)
        session = sessions_col.find_one({"_id": session_obj_id})

        if not session or session["student_id"] != g.current_user["_id"]:
            return jsonify({"error": "Session not found or unauthorized"}), 404

        exam = exams_col.find_one({"_id": session["exam_id"]})
        session = ensure_session_not_expired(session, exam) if exam else session

        if session["status"] != "in_progress":
            return jsonify({"error": "Session has ended (time expired)", "expired": True}), 400

        update_data = {
            "updated_at": datetime.utcnow()
        }

        # The client's countdown is informational only - the authoritative
        # deadline lives server-side, so a tampered client can't buy extra
        # time by syncing an inflated value.
        server_remaining = None
        if session.get("deadline"):
            server_remaining = max(0, int((session["deadline"] - datetime.utcnow()).total_seconds()))

        if "time_remaining_seconds" in data:
            remaining = max(0, int(data["time_remaining_seconds"]))
            if server_remaining is not None:
                remaining = min(remaining, server_remaining)
            update_data["time_remaining_seconds"] = remaining

        if "answers" in data:
            # We overwrite the answers array with the synced state from client
            update_data["answers"] = data["answers"]

        if "new_flags" in data:
            sessions_col.update_one(
                {"_id": session_obj_id},
                {"$push": {"proctoring_flags": {"$each": data["new_flags"]}}}
            )

        sessions_col.update_one({"_id": session_obj_id}, {"$set": update_data})
        response = {"success": True}
        if server_remaining is not None:
            response["time_remaining_seconds"] = server_remaining
        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


def _exam_owned_by(exam, user):
    return str(exam.get("created_by")) == str(user["_id"]) or user.get("role") in ("org_admin", "platform_admin")


@sessions_bp.route('/<session_id>/grade', methods=['POST'])
@require_auth()
def grade_session(session_id):
    """Manual grading endpoint for essay/AC questions."""
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json or {}
    grades = data.get('grades', [])
    publish = data.get('publish', False)

    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')

    try:
        session_obj_id = ObjectId(session_id)
        session = sessions_col.find_one({"_id": session_obj_id})

        if not session:
            return jsonify({"error": "Session not found"}), 404

        exam = exams_col.find_one({"_id": session["exam_id"]})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404

        if not _exam_owned_by(exam, g.current_user):
            return jsonify({"error": "Unauthorized"}), 403

        # Store manual grades in session
        manual_grades = {}
        for grade_item in grades:
            q_id = grade_item.get('question_id')
            manual_grades[q_id] = {
                'score': float(grade_item.get('score', 0) or 0),
                'feedback': grade_item.get('feedback', ''),
                'graded_at': datetime.utcnow(),
                'graded_by': str(g.current_user['_id'])
            }

        sessions_col.update_one(
            {"_id": session_obj_id},
            {"$set": {
                "manual_grades": manual_grades,
                "graded_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }}
        )

        # Recalculate total score, reusing the exact same resolver/weighting
        # logic as the initial auto-grade so an MCQ that graded correct at
        # submission time can't silently flip just because essays got scored.
        questions_to_grade = session.get('question_snapshot') or exam.get('questions', [])
        answers_dict = {
            a.get('question_id'): a.get('selected_option')
            for a in session.get('answers', []) if a.get('question_id')
        }
        result = compute_score(questions_to_grade, session.get('question_order', []), answers_dict, manual_grades)

        settings_snapshot = session.get("settings_snapshot") or {}
        pass_mark = settings_snapshot.get("pass_mark_percent", exam.get('settings', {}).get('pass_mark_percent', 50))
        passed = result["score_percent"] >= pass_mark

        sessions_col.update_one(
            {"_id": session_obj_id},
            {"$set": {"is_graded": result["is_fully_graded"]}}
        )

        # Update PostgreSQL score record
        score_record = ExamScore.query.filter_by(session_id=session_id).first()
        if score_record:
            score_record.score = result["score"]
            score_record.total_marks = result["total_marks"]
            score_record.score_percent = result["score_percent"]
            score_record.passed = passed
            score_record.correct_count = result["correct_count"]
            score_record.incorrect_count = result["incorrect_count"]
            score_record.unanswered_count = result["unanswered_count"]
            score_record.is_graded = result["is_fully_graded"]

            if publish:
                score_record.results_published = True

            db.session.commit()

        return jsonify({
            "success": True,
            "score": result["score"],
            "total_marks": result["total_marks"],
            "score_percent": result["score_percent"],
            "passed": passed
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/<session_id>/publish-results', methods=['POST'])
@require_auth()
def publish_results(session_id):
    """Publish results for a single session."""
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        score_record = ExamScore.query.filter_by(session_id=session_id).first()
        if not score_record:
            return jsonify({"error": "Score record not found"}), 404

        exams_col = get_collection('exams')
        exam = exams_col.find_one({"_id": ObjectId(score_record.exam_id)}) if score_record.exam_id else None
        if exam and not _exam_owned_by(exam, g.current_user):
            return jsonify({"error": "Unauthorized"}), 403

        score_record.results_published = True
        db.session.commit()

        return jsonify({"success": True}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/<session_id>/submit', methods=['POST'])
@require_auth()
def submit_session(session_id):
    data = request.json or {}
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')

    try:
        session_obj_id = ObjectId(session_id)
        session = sessions_col.find_one({"_id": session_obj_id})

        if not session or session["student_id"] != g.current_user["_id"]:
            return jsonify({"error": "Session not found or unauthorized"}), 404

        exam = exams_col.find_one({"_id": session["exam_id"]})
        if not exam:
            return jsonify({"error": "Exam data missing"}), 500

        # If the deadline already passed before this request arrived, this
        # closes the session using whatever was last synced - the client's
        # answers below are irrelevant at that point (session is no longer
        # in_progress), which is what prevents "keep answering after time's
        # up, then submit" from working.
        session = ensure_session_not_expired(session, exam)

        if session["status"] != "in_progress":
            score_record = ExamScore.query.filter_by(session_id=session_id).first()
            if score_record:
                return jsonify({
                    "success": True,
                    "score_percent": float(score_record.score_percent),
                    "passed": bool(score_record.passed),
                    "auto_submitted": session["status"] == "timed_out"
                }), 200
            return jsonify({"error": "Session is already closed"}), 400

        # Final answer sync
        final_answers = data.get("answers", session.get("answers", []))
        sessions_col.update_one({"_id": session_obj_id}, {"$set": {"answers": final_answers}})
        session["answers"] = final_answers

        result, passed = _finalize_session(session, exam, reason="submitted")

        return jsonify({"success": True, "score_percent": result["score_percent"], "passed": passed}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
