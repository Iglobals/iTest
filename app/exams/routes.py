from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_role
from app.utils.mongo import get_collection
from datetime import datetime
from bson import ObjectId
import re
import uuid

exams_bp = Blueprint('exams', __name__, url_prefix='/api/exams')

def generate_unique_slug(title, collection):
    base_slug = re.sub(r'[^a-z0-9]+', '-', str(title).lower()).strip('-')
    if not base_slug:
        base_slug = "exam"
    
    short_id = str(uuid.uuid4())[:8]
    slug = f"{base_slug}-{short_id}"
    
    while collection.find_one({"slug": slug}):
        short_id = str(uuid.uuid4())[:8]
        slug = f"{base_slug}-{short_id}"
    return slug

@exams_bp.route('/', methods=['POST'])
@require_role('teacher', 'org_admin', 'platform_admin')
def create_exam():
    data = request.json
    exams_col = get_collection('exams')
    
    exam_type = data.get("exam_type", "private") # private, public, platform_standard - controls WHO can access the exam
    grading_mode = data.get("grading_mode", "hybrid") # objective, essay, hybrid - controls the exam's question composition/grading
    if grading_mode not in ("objective", "essay", "hybrid"):
        grading_mode = "hybrid"

    visibility = data.get("visibility", {})
    # e.g. {"class_ids": [...ObjectId strings], "student_emails": [...raw emails], "excluded_student_emails": [...raw emails]}

    # class_ids reference real Class documents, so they're coerced to ObjectId.
    # Individually-granted students are identified by email (not every invited
    # student necessarily has an account yet), so those are kept as raw strings -
    # matching how update_exam and the visibility queries elsewhere already treat them.
    class_ids = [ObjectId(cid) for cid in visibility.get("class_ids", []) if cid and ObjectId.is_valid(cid)]
    student_ids = [e.strip() for e in visibility.get("student_emails", []) if isinstance(e, str) and e.strip()]
    excluded_student_ids = [e.strip() for e in visibility.get("excluded_student_emails", []) if isinstance(e, str) and e.strip()]

    settings = {
        "duration_minutes": 60,
        "allow_retake": True if exam_type in ['public', 'platform_standard'] else False,
        "max_attempts": 3 if exam_type in ['public', 'platform_standard'] else 1,
        "randomize_questions": True,
        "pass_mark_percent": 50,
        "show_result_immediately": grading_mode == "objective"
    }
    settings.update(data.get("settings", {}))
    # Instant results only ever make sense when there's no essay component to manually grade.
    settings["show_result_immediately"] = grading_mode == "objective" and bool(settings.get("show_result_immediately"))

    # Same plan gate as update_exam() - without this, a free/basic-plan user
    # could turn on AI proctoring from day one simply by including it in the
    # initial create payload, bypassing the gate that only checks the
    # off->on transition on a later edit.
    if settings.get("ai_proctoring_enabled"):
        from app.utils.plans import get_plan_limit
        user_plan = g.current_user.get("plan", {}).get("type", "free")
        if not get_plan_limit(user_plan, "can_use_ai_proctoring"):
            return jsonify({
                "error": "AI proctoring requires a Pro or Enterprise plan.",
                "limit_reached": True,
                "upgrade_url": "/pricing"
            }), 402

    exam = {
        "title": data.get("title", "Untitled Exam"),
        "slug": generate_unique_slug(data.get("title", "Untitled Exam"), exams_col),
        "description": data.get("description", ""),
        "cover_image_url": data.get("cover_image_url", None),
        "created_by": g.current_user["_id"],
        "created_by_type": g.current_user.get("role", "teacher"),
        "exam_type": exam_type,
        "grading_mode": grading_mode,
        "visibility": {
            "type": visibility.get("type", "class"),
            "class_ids": class_ids,
            "student_ids": student_ids,
            "excluded_student_ids": excluded_student_ids
        },
        "subject_tag_id": ObjectId(data["subject_tag_id"]) if data.get("subject_tag_id") and ObjectId.is_valid(data["subject_tag_id"]) else data.get("subject_tag_id"),
        "organization_id": ObjectId(data["organization_id"]) if data.get("organization_id") and ObjectId.is_valid(data["organization_id"]) else None,
        "instructions": data.get("instructions", ""),
        "settings": settings,
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
        "data": {"_id": str(result.inserted_id), "title": exam["title"], "slug": exam["slug"]}
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


@exams_bp.route('/slug/<slug>', methods=['GET'])
def get_exam_by_slug(slug):
    exams_col = get_collection('exams')
    try:
        exam = exams_col.find_one({"slug": slug})
        if not exam:
            return jsonify({"error": "Not found"}), 404
        
        exam["_id"] = str(exam["_id"])
        exam["created_by"] = str(exam["created_by"])
        
        if exam.get("organization_id"):
            exam["organization_id"] = str(exam["organization_id"])
        if exam.get("subject_tag_id"):
            exam["subject_tag_id"] = str(exam["subject_tag_id"])
            
        vis = exam.get("visibility", {})
        vis["class_ids"] = [str(i) for i in vis.get("class_ids", [])]
        vis["student_ids"] = [str(i) for i in vis.get("student_ids", [])]
        vis["excluded_student_ids"] = [str(i) for i in vis.get("excluded_student_ids", [])]
        
        return jsonify({"success": True, "data": exam}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@exams_bp.route('/<exam_id>/questions', methods=['PUT'])
@require_role('teacher', 'org_admin', 'platform_admin')
def update_exam_questions(exam_id):
    data = request.json
    exams_col = get_collection('exams')
    
    try:
        exam_obj_id = ObjectId(exam_id)
        existing_exam = exams_col.find_one({"_id": exam_obj_id})
        
        if not existing_exam:
            return jsonify({"error": "Not found"}), 404
            
        if existing_exam["created_by"] != g.current_user["_id"] and g.current_user.get("role") != "platform_admin":
            return jsonify({"error": "Unauthorized"}), 403
            
        questions = data.get("questions", [])

        # Ensure questions have IDs if missing
        for q in questions:
            if "_id" not in q or not q["_id"]:
                q["_id"] = str(uuid.uuid4())

        # A question's type must match what this exam's grading_mode allows -
        # the builder UI already restricts this, but the API is reachable directly.
        grading_mode = existing_exam.get("grading_mode", "hybrid")
        allowed_types = {"objective": {"mcq"}, "essay": {"essay"}, "hybrid": {"mcq", "essay"}}.get(grading_mode, {"mcq", "essay"})
        invalid_types = sorted({q.get("type") for q in questions if q.get("type") not in allowed_types})
        if invalid_types:
            return jsonify({
                "error": f"This exam is '{grading_mode}' - question type(s) {', '.join(invalid_types)} are not allowed."
            }), 400

        total_questions = len(questions)
        total_marks = sum([float(q.get("marks", 1)) for q in questions])
        
        update_data = {
            "questions": questions,
            "total_questions": total_questions,
            "total_marks": total_marks,
            "updated_at": datetime.utcnow()
        }
        
        exams_col.update_one({"_id": exam_obj_id}, {"$set": update_data})
        return jsonify({
            "success": True, 
            "message": "Questions updated successfully",
            "data": update_data
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


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
            "impact": data.get("impact", existing_exam.get("impact", 1.0)),
            "instructions": data.get("instructions", existing_exam.get("instructions", "")),
            "updated_at": datetime.utcnow()
        }

        if "grading_mode" in data and data["grading_mode"] in ("objective", "essay", "hybrid"):
            update_data["grading_mode"] = data["grading_mode"]

        if "subject_tag_id" in data:
            if data["subject_tag_id"] and ObjectId.is_valid(data["subject_tag_id"]):
                update_data["subject_tag_id"] = ObjectId(data["subject_tag_id"])
            else:
                update_data["subject_tag_id"] = data["subject_tag_id"]
                
        if "settings" in data:
            wants_ai_proctoring = data["settings"].get("ai_proctoring_enabled")
            already_enabled = existing_exam.get("settings", {}).get("ai_proctoring_enabled")
            if wants_ai_proctoring and not already_enabled:
                from app.utils.plans import get_plan_limit
                user_plan = g.current_user.get("plan", {}).get("type", "free")
                if not get_plan_limit(user_plan, "can_use_ai_proctoring"):
                    return jsonify({
                        "error": "AI proctoring requires a Pro or Enterprise plan.",
                        "limit_reached": True,
                        "upgrade_url": "/pricing"
                    }), 402

            update_data["settings"] = existing_exam.get("settings", {})
            update_data["settings"].update(data["settings"])
            effective_grading_mode = update_data.get("grading_mode", existing_exam.get("grading_mode", "hybrid"))
            update_data["settings"]["show_result_immediately"] = (
                effective_grading_mode == "objective" and bool(update_data["settings"].get("show_result_immediately"))
            )

        # Update visibility and schedule if provided
        if "visibility" in data:
            vis = data["visibility"]
            update_data["visibility"] = existing_exam.get("visibility", {})
            update_data["visibility"]["type"] = vis.get("type", update_data["visibility"].get("type"))
            update_data["visibility"]["class_ids"] = [ObjectId(cid) for cid in vis.get("class_ids", []) if cid and ObjectId.is_valid(cid)]
            update_data["visibility"]["student_ids"] = vis.get("student_emails", []) # Store emails directly for MVP or convert to object IDs
            update_data["visibility"]["excluded_student_ids"] = vis.get("excluded_student_emails", [])
            
        if "schedule" in data:
            sched = data["schedule"]
            update_data["schedule"] = existing_exam.get("schedule", {})
            update_data["schedule"]["available_from"] = sched.get("available_from", update_data["schedule"].get("available_from"))
            update_data["schedule"]["available_until"] = sched.get("available_until", update_data["schedule"].get("available_until"))
            if "is_published" in sched:
                update_data["schedule"]["is_published"] = sched["is_published"]
                update_data["status"] = "published" if sched["is_published"] else "draft"
            
        # If General Exam and is_published (post-update), notify students (basic implementation)
        new_is_published = update_data.get("schedule", existing_exam.get("schedule", {})).get("is_published")
        was_is_published = existing_exam.get("schedule", {}).get("is_published")
        if not is_private and new_is_published and not was_is_published:
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
@exams_bp.route('/<exam_id>', methods=['DELETE'])
@require_role('teacher', 'org_admin', 'platform_admin')
def delete_exam(exam_id):
    exams_col = get_collection('exams')
    try:
        # Check permissions
        exam = exams_col.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
            
        if str(exam.get("created_by")) != str(g.current_user["_id"]) and g.current_user.get("role") not in ["org_admin", "platform_admin"]:
            return jsonify({"error": "Unauthorized to delete this exam"}), 403
            
        # Soft delete
        exams_col.update_one({"_id": ObjectId(exam_id)}, {"$set": {"status": "deleted", "updated_at": datetime.utcnow()}})
        
        return jsonify({"success": True, "message": "Exam soft deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@exams_bp.route('/<exam_id>/publish-all-results', methods=['POST'])
@require_role('teacher', 'org_admin', 'platform_admin')
def publish_all_results(exam_id):
    """Bulk publish all graded results for an exam."""
    from app.models import ExamScore
    from app.extensions import db
    
    try:
        # Verify exam exists and user has permission
        exams_col = get_collection('exams')
        exam = exams_col.find_one({"_id": ObjectId(exam_id)})
        
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
            
        if str(exam.get("created_by")) != str(g.current_user["_id"]) and g.current_user.get("role") not in ["org_admin", "platform_admin"]:
            return jsonify({"error": "Unauthorized"}), 403
            
        # Get all scores for this exam that are graded but not published
        scores = ExamScore.query.filter_by(
            exam_id=str(exam["_id"]),
            is_graded=True,
            results_published=False
        ).all()
        
        count = 0
        for score in scores:
            score.results_published = True
            count += 1
            
        db.session.commit()
        
        return jsonify({
            "success": True,
            "count": count,
            "message": f"Published {count} result(s)"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
