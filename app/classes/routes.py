from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_auth, require_role
from app.utils.mongo import get_collection
from datetime import datetime
from bson import ObjectId

classes_bp = Blueprint('classes', __name__, url_prefix='/api/classes')

@classes_bp.route('/', methods=['GET'])
@require_auth(redirect_on_fail=False)
def list_classes():
    classes_col = get_collection('classes')
    try:
        classes = list(classes_col.find({}))
        for cls in classes:
            cls["_id"] = str(cls["_id"])
            if cls.get("organization_id"):
                cls["organization_id"] = str(cls["organization_id"])
            for teacher in cls.get("teachers", []):
                if "user_id" in teacher: teacher["user_id"] = str(teacher["user_id"])
            for student in cls.get("students", []):
                if "user_id" in student: student["user_id"] = str(student["user_id"])
        return jsonify({"success": True, "data": classes}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@classes_bp.route('/', methods=['POST'])
@require_role('teacher', 'org_admin')
def create_class():
    data = request.json
    classes_col = get_collection('classes')
    
    if classes_col is None:
        return jsonify({"error": "Database error"}), 500
        
    new_class = {
        "name": data.get("name"),
        "description": data.get("description", ""),
        "cover_image_url": data.get("cover_image_url", ""),
        "organization_id": ObjectId(data["organization_id"]) if data.get("organization_id") else None,
        "organization_status": "pending" if data.get("organization_id") else "none",
        "teachers": [
            {
                "user_id": g.current_user["_id"],
                "role": "owner",
                "added_at": datetime.utcnow()
            }
        ],
        "students": [],
        "join_requests": [],
        "subject_tags": data.get("subject_tags", []),
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = classes_col.insert_one(new_class)
    return jsonify({
        "success": True,
        "data": {"_id": str(result.inserted_id), "name": new_class["name"]}
    }), 201

@classes_bp.route('/<class_id>', methods=['GET'])
@require_auth(redirect_on_fail=False)
def get_class(class_id):
    classes_col = get_collection('classes')
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Not found"}), 404
        class_obj["_id"] = str(class_obj["_id"])
        if class_obj.get("organization_id"):
            class_obj["organization_id"] = str(class_obj["organization_id"])
            
        # Convert all nested object IDs
        for teacher in class_obj["teachers"]:
            teacher["user_id"] = str(teacher["user_id"])
        for student in class_obj["students"]:
            student["user_id"] = str(student["user_id"])
        
        return jsonify({"success": True, "data": class_obj}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400

@classes_bp.route('/<class_id>/join', methods=['POST'])
@require_role('student')
def request_join(class_id):
    classes_col = get_collection('classes')
    try:
        result = classes_col.update_one(
            {"_id": ObjectId(class_id)},
            {"$push": {
                "join_requests": {
                    "student_id": g.current_user["_id"],
                    "status": "pending",
                    "attempt_count": 1,
                    "max_attempts": 3,
                    "last_requested_at": datetime.utcnow()
                }
            }}
        )
        if result.modified_count == 0:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"success": True, "message": "Join request sent"}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
