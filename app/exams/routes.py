from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_role
from app.utils.mongo import get_collection
from datetime import datetime
from bson import ObjectId

exams_bp = Blueprint('exams', __name__, url_prefix='/api/exams')

@exams_bp.route('/', methods=['POST'])
@require_role('teacher', 'org_admin', 'platform_admin')
def create_exam():
    data = request.json
    exams_col = get_collection('exams')
    
    exam_type = data.get("exam_type", "private") # private, public, platform_standard
    
    visibility = data.get("visibility", {})
    # e.g. {"class_ids": [], "student_ids": [], "excluded_student_ids": []}
    
    # Ensure IDs are ObjectIds where applicable
    class_ids = [ObjectId(cid) for cid in visibility.get("class_ids", []) if cid]
    student_ids = [ObjectId(sid) for sid in visibility.get("student_ids", []) if sid]
    excluded_student_ids = [ObjectId(esid) for esid in visibility.get("excluded_student_ids", []) if esid]
    
    exam = {
        "title": data.get("title", "Untitled Exam"),
        "description": data.get("description", ""),
        "cover_image_url": data.get("cover_image_url", None),
        "created_by": g.current_user["_id"],
        "created_by_type": g.current_user.get("role", "teacher"),
        "exam_type": exam_type,
        "visibility": {
            "type": visibility.get("type", "class"),
            "class_ids": class_ids,
            "student_ids": student_ids,
            "excluded_student_ids": excluded_student_ids
        },
        "subject_tag_id": ObjectId(data["subject_tag_id"]) if data.get("subject_tag_id") else None,
        "organization_id": ObjectId(data["organization_id"]) if data.get("organization_id") else None,
        "instructions": data.get("instructions", ""),
        "settings": data.get("settings", {
            "duration_minutes": 60,
            "allow_retake": True if exam_type in ['public', 'platform_standard'] else False,
            "max_attempts": 3 if exam_type in ['public', 'platform_standard'] else 1,
            "randomize_questions": True,
            "show_result_immediately": True
        }),
        "schedule": data.get("schedule", {
            "available_from": None,
            "available_until": None,
            "is_published": False
        }),
        "questions": data.get("questions", []), # Usually added later or via question bank references
        "total_questions": len(data.get("questions", [])),
        "total_marks": sum([q.get("marks", 1) for q in data.get("questions", [])]),
        "status": "draft",
        "statistics": {"total_attempts": 0, "avg_score_percent": 0, "pass_rate_percent": 0},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = exams_col.insert_one(exam)
    return jsonify({
        "success": True, 
        "data": {"_id": str(result.inserted_id), "title": exam["title"]}
    }), 201


@exams_bp.route('/<exam_id>', methods=['GET'])
def get_exam(exam_id):
    exams_col = get_collection('exams')
    try:
        exam = exams_col.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Not found"}), 404
        
        exam["_id"] = str(exam["_id"])
        exam["created_by"] = str(exam["created_by"])
        
        # Convert all ObjectIds to string for JSON serialization
        if exam.get("organization_id"):
            exam["organization_id"] = str(exam["organization_id"])
        if exam.get("subject_tag_id"):
            exam["subject_tag_id"] = str(exam["subject_tag_id"])
            
        vis = exam.get("visibility", {})
        vis["class_ids"] = [str(i) for i in vis.get("class_ids", [])]
        vis["student_ids"] = [str(i) for i in vis.get("student_ids", [])]
        vis["excluded_student_ids"] = [str(i) for i in vis.get("excluded_student_ids", [])]
        
        return jsonify({"success": True, "data": exam}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400


@exams_bp.route('/<exam_id>', methods=['PUT'])
@require_role('teacher', 'org_admin', 'platform_admin')
def update_exam(exam_id):
    data = request.json
    exams_col = get_collection('exams')
    sessions_col = get_collection('exam_sessions')
    notif_col = get_collection('notifications')
    
    try:
        exam_obj_id = ObjectId(exam_id)
        existing_exam = exams_col.find_one({"_id": exam_obj_id})
        
        if not existing_exam:
            return jsonify({"error": "Not found"}), 404
            
        # Check permissions
        if existing_exam["created_by"] != g.current_user["_id"] and g.current_user.get("role") != "platform_admin":
            return jsonify({"error": "Unauthorized"}), 403
            
        # BUSINESS LOGIC: Private exams cannot be edited if a student has already taken it
        is_private = existing_exam.get("exam_type") == "private"
        
        if is_private:
            session_exists = sessions_col.find_one({"exam_id": exam_obj_id})
            if session_exists:
                return jsonify({
                    "error": "Cannot edit a private exam after students have started taking it. This preserves grading records."
                }), 403
                
        # Safe to update
        update_data = {
            "title": data.get("title", existing_exam.get("title")),
            "description": data.get("description", existing_exam.get("description")),
            "updated_at": datetime.utcnow()
        }
        
        # Update visibility and schedule if provided
        if "visibility" in data:
            vis = data["visibility"]
            update_data["visibility"] = {
                "type": vis.get("type", existing_exam["visibility"]["type"]),
                "class_ids": [ObjectId(cid) for cid in vis.get("class_ids", []) if cid],
                "student_ids": [ObjectId(sid) for sid in vis.get("student_ids", []) if sid],
                "excluded_student_ids": [ObjectId(esid) for esid in vis.get("excluded_student_ids", []) if esid]
            }
            
        if "schedule" in data:
            sched = data["schedule"]
            update_data["schedule"] = {
                "available_from": sched.get("available_from", existing_exam["schedule"]["available_from"]),
                "available_until": sched.get("available_until", existing_exam["schedule"]["available_until"]),
                "is_published": sched.get("is_published", existing_exam["schedule"]["is_published"])
            }
            
        # If General Exam and is_published, notify students (basic implementation)
        if not is_private and existing_exam.get("schedule", {}).get("is_published"):
            # Insert notification record for general exam update
            notif_col.insert_one({
                "recipient_id": "broadcast", # In a real system, you'd target specific users
                "sender_id": g.current_user["_id"],
                "type": "system",
                "title": f"Exam Updated: {update_data['title']}",
                "body": "A general exam you have access to has been updated.",
                "metadata": {"exam_id": exam_obj_id},
                "is_read": False,
                "created_at": datetime.utcnow()
            })

        exams_col.update_one({"_id": exam_obj_id}, {"$set": update_data})
        return jsonify({"success": True, "message": "Exam updated successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400
