from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_auth
from app.utils.mongo import get_collection
from app.extensions import db
from app.models import ExamScore
from datetime import datetime, timedelta
from bson import ObjectId
import random

sessions_bp = Blueprint('sessions', __name__, url_prefix='/api/sessions')

@sessions_bp.route('/start', methods=['POST'])
@require_auth()
def start_session():
    data = request.json
    exam_id = data.get("exam_id")
    
    if not exam_id:
        return jsonify({"error": "exam_id required"}), 400
        
    exams_col = get_collection('exams')
    sessions_col = get_collection('exam_sessions')
    qb_col = get_collection('question_banks')
    
    exam = exams_col.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        return jsonify({"error": "Exam not found"}), 404
        
    student_id = g.current_user["_id"]
    
    # Check max attempts
    allow_retake = exam.get("settings", {}).get("allow_retake", False)
    max_attempts = exam.get("settings", {}).get("max_attempts", 1)
    
    previous_attempts = sessions_col.count_documents({
        "exam_id": ObjectId(exam_id),
        "student_id": student_id,
        "status": {"$in": ["submitted", "timed_out"]}
    })
    
    if not allow_retake and previous_attempts >= max_attempts:
        return jsonify({"error": f"Max attempts ({max_attempts}) reached"}), 403
        
    # Check if there is already an in_progress session
    existing_session = sessions_col.find_one({
        "exam_id": ObjectId(exam_id),
        "student_id": student_id,
        "status": "in_progress"
    })
    
    if existing_session:
        # Return existing session to resume
        existing_session["_id"] = str(existing_session["_id"])
        existing_session["exam_id"] = str(existing_session["exam_id"])
        existing_session["student_id"] = str(existing_session["student_id"])
        return jsonify({"success": True, "message": "Resumed existing session", "data": existing_session}), 200
        
    duration = exam.get("settings", {}).get("duration_minutes", 60)
    
    # Generate randomized question order
    questions = exam.get("questions", [])
    if exam.get("settings", {}).get("randomize_questions", False):
        random.shuffle(questions)
        
    question_order = [str(q.get("_id", i)) for i, q in enumerate(questions)]
    
    new_session = {
        "exam_id": ObjectId(exam_id),
        "student_id": student_id,
        "attempt_number": previous_attempts + 1,
        "status": "in_progress",
        "started_at": datetime.utcnow(),
        "submitted_at": None,
        "time_remaining_seconds": duration * 60,
        "answers": [],
        "proctoring_flags": [],
        "question_order": question_order,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = sessions_col.insert_one(new_session)
    new_session["_id"] = str(result.inserted_id)
    new_session["exam_id"] = str(exam_id)
    new_session["student_id"] = str(student_id)
    
    return jsonify({"success": True, "data": new_session}), 201


@sessions_bp.route('/<session_id>/flag', methods=['POST'])
@require_auth()
def flag_violation(session_id):
    """Log proctoring violations like tab switches."""
    data = request.json
    sessions_col = get_collection('exam_sessions')
    
    try:
        session_obj_id = ObjectId(session_id)
        session = sessions_col.find_one({"_id": session_obj_id})
        
        if not session or session["student_id"] != g.current_user["_id"]:
            return jsonify({"error": "Session not found or unauthorized"}), 404
            
        if session["status"] != "in_progress":
            return jsonify({"error": "Session is already closed"}), 400
            
        flag_entry = {
            "type": data.get("type", "tab_switch"),
            "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
            "logged_at": datetime.utcnow()
        }
        
        sessions_col.update_one(
            {"_id": session_obj_id},
            {"$push": {"proctoring_flags": flag_entry}}
        )
        
        # Get updated flag count
        updated_session = sessions_col.find_one({"_id": session_obj_id})
        flag_count = len(updated_session.get("proctoring_flags", []))
        
        # If 3 or more flags, auto-submit
        max_flags = 3
        force_submit = flag_count >= max_flags
        
        return jsonify({
            "success": True,
            "flag_count": flag_count,
            "max_flags": max_flags,
            "force_submit": force_submit
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@sessions_bp.route('/<session_id>/sync', methods=['PUT'])
@require_auth()
def sync_session(session_id):
    """Called periodically by frontend to save answers and flags without submitting."""
    data = request.json
    sessions_col = get_collection('exam_sessions')
    
    try:
        session_obj_id = ObjectId(session_id)
        session = sessions_col.find_one({"_id": session_obj_id})
        
        if not session or session["student_id"] != g.current_user["_id"]:
            return jsonify({"error": "Session not found or unauthorized"}), 404
            
        if session["status"] != "in_progress":
            return jsonify({"error": "Session is already closed"}), 400
            
        update_data = {
            "updated_at": datetime.utcnow()
        }
        
        if "time_remaining_seconds" in data:
            update_data["time_remaining_seconds"] = max(0, data["time_remaining_seconds"])
            
        if "answers" in data:
            # We overwrite the answers array with the synced state from client
            update_data["answers"] = data["answers"]
            
        if "new_flags" in data:
            sessions_col.update_one(
                {"_id": session_obj_id},
                {"$push": {"proctoring_flags": {"$each": data["new_flags"]}}}
            )
            
        sessions_col.update_one({"_id": session_obj_id}, {"$set": update_data})
        return jsonify({"success": True}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@sessions_bp.route('/<session_id>/submit', methods=['POST'])
@require_auth()
def submit_session(session_id):
    data = request.json or {}
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')
    tags_col = get_collection('subject_tags')
    
    try:
        session_obj_id = ObjectId(session_id)
        session = sessions_col.find_one({"_id": session_obj_id})
        
        if not session or session["student_id"] != g.current_user["_id"]:
            return jsonify({"error": "Session not found or unauthorized"}), 404
            
        if session["status"] != "in_progress":
            return jsonify({"error": "Session is already closed"}), 400
            
        exam = exams_col.find_one({"_id": session["exam_id"]})
        if not exam:
            return jsonify({"error": "Exam data missing"}), 500
            
        # Final answer sync
        final_answers = data.get("answers", session.get("answers", []))
        
        # Build answers lookup
        answers_dict = {ans.get("question_id"): ans.get("selected_option") for ans in final_answers if ans.get("question_id")}
        
        # Real grading logic - compare with actual correct answers
        correct_count = 0
        incorrect_count = 0
        unanswered_count = 0
        
        # Get all questions from exam
        questions_dict = {str(q.get("_id")): q for q in exam.get("questions", [])}
        
        total_questions = len(session.get("question_order", []))
        
        for q_id in session.get("question_order", []):
            student_answer = answers_dict.get(q_id)
            question = questions_dict.get(q_id)
            
            if not student_answer:
                unanswered_count += 1
                continue
                
            if not question:
                # Question not found, skip
                continue
                
            # Get correct answer
            correct_answer = question.get("correct_answer")
            
            # Compare based on question type
            question_type = question.get("question_type", question.get("type", "mcq"))
            
            if question_type in ["mcq", "true_false"]:
                # Exact match for MCQ and True/False
                if str(student_answer).strip().upper() == str(correct_answer).strip().upper():
                    correct_count += 1
                else:
                    incorrect_count += 1
            elif question_type in ["short_answer", "numerical"]:
                # Case-insensitive trim match for short answer
                if str(student_answer).strip().lower() == str(correct_answer).strip().lower():
                    correct_count += 1
                else:
                    incorrect_count += 1
            elif question_type == "essay":
                # Essay questions need manual grading - count as unanswered for now
                unanswered_count += 1
            else:
                # Unknown type - treat as incorrect
                incorrect_count += 1
        
        score_percent = (correct_count / total_questions * 100) if total_questions > 0 else 0
        pass_mark = exam.get("settings", {}).get("pass_mark_percent", 50)
        passed = score_percent >= pass_mark
        
        time_spent = (exam.get("settings", {}).get("duration_minutes", 60) * 60) - session.get("time_remaining_seconds", 0)
        
        # Get subject tag name if possible
        subject_name = "General"
        if exam.get("subject_tag_id"):
            tag = tags_col.find_one({"_id": exam["subject_tag_id"]})
            if tag:
                subject_name = tag.get("name", "General")
                
        # 1. Update PostgreSQL
        new_score = ExamScore(
            session_id=str(session["_id"]),
            exam_id=str(exam["_id"]),
            student_id=str(session["student_id"]),
            organization_id=str(exam.get("organization_id")),
            class_id=str(exam.get("visibility", {}).get("class_ids", [None])[0]) if exam.get("visibility", {}).get("class_ids") else None,
            subject_tag_id=str(exam.get("subject_tag_id")),
            subject_tag_name=subject_name,
            exam_title=exam["title"],
            attempt_number=session["attempt_number"],
            score=correct_count,
            total_marks=total_questions, # Assuming 1 mark per question
            score_percent=score_percent,
            passed=passed,
            time_spent_secs=int(time_spent),
            total_questions=total_questions,
            correct_count=correct_count,
            incorrect_count=incorrect_count,
            unanswered_count=unanswered_count,
            submitted_at=datetime.utcnow()
        )
        
        db.session.add(new_score)
        db.session.commit()
        
        # 2. Update MongoDB Session
        sessions_col.update_one(
            {"_id": session_obj_id},
            {"$set": {
                "status": "submitted",
                "submitted_at": datetime.utcnow(),
                "answers": final_answers
            }}
        )
        
        return jsonify({"success": True, "score_percent": score_percent, "passed": passed}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
