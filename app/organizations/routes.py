from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_role
from app.utils.mongo import get_collection
from datetime import datetime
from bson import ObjectId

org_bp = Blueprint('organizations', __name__, url_prefix='/api/organizations')

@org_bp.route('/', methods=['POST'])
@require_role('org_admin', 'platform_admin')
def create_org():
    data = request.json
    orgs_col = get_collection('organizations')
    
    if orgs_col is None:
        return jsonify({"error": "Database error"}), 500
        
    org = {
        "name": data.get("name"),
        "slug": data.get("slug"),
        "logo_url": data.get("logo_url", ""),
        "admin_user_id": g.current_user["_id"],
        "description": data.get("description", ""),
        "website": data.get("website", ""),
        "contact_email": data.get("contact_email", ""),
        "plan": {
            "type": "free",
            "expires_at": None
        },
        "limits": {
            "max_classes": 5,
            "max_teachers": 10,
            "ai_proctoring": False,
            "advanced_analytics": False
        },
        "pending_teacher_requests": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = orgs_col.insert_one(org)
    return jsonify({
        "success": True,
        "data": {"_id": str(result.inserted_id), "name": org["name"], "slug": org["slug"]}
    }), 201

@org_bp.route('/<org_id>', methods=['GET'])
def get_org(org_id):
    orgs_col = get_collection('organizations')
    try:
        org = orgs_col.find_one({"_id": ObjectId(org_id)})
        if not org:
            return jsonify({"error": "Not found"}), 404
        org["_id"] = str(org["_id"])
        org["admin_user_id"] = str(org["admin_user_id"])
        return jsonify({"success": True, "data": org}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400

@org_bp.route('/<org_id>/teachers/request', methods=['POST'])
@require_role('teacher')
def request_to_join(org_id):
    orgs_col = get_collection('organizations')
    try:
        result = orgs_col.update_one(
            {"_id": ObjectId(org_id)},
            {"$push": {
                "pending_teacher_requests": {
                    "teacher_id": g.current_user["_id"],
                    "status": "pending",
                    "requested_at": datetime.utcnow(),
                    "attempts": 1
                }
            }}
        )
        if result.modified_count == 0:
            return jsonify({"error": "Not found or already requested"}), 400
        return jsonify({"success": True, "message": "Request sent"}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
