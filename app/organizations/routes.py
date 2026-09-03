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

MAX_FOLDER_DEPTH = 4


def _is_org_admin(org_id, user):
    if user.get("role") == "platform_admin":
        return True
    if user.get("role") != "org_admin":
        return False
    org = get_collection("organizations").find_one({"_id": ObjectId(org_id)})
    return bool(org and str(org.get("admin_user_id")) == str(user["_id"]))


def _folder_depth(folder_id):
    """1 for a top-level folder, up to MAX_FOLDER_DEPTH. None (no parent) = 0,
    so a new top-level folder is depth 1."""
    folders_col = get_collection('org_folders')
    depth = 0
    current_id = folder_id
    seen = set()  # guards against a corrupted cycle, not expected in normal use
    while current_id:
        if str(current_id) in seen:
            break
        seen.add(str(current_id))
        folder = folders_col.find_one({"_id": ObjectId(current_id)})
        if not folder:
            break
        depth += 1
        current_id = folder.get("parent_folder_id")
    return depth


@org_bp.route('/<org_id>/folders', methods=['GET'])
@require_role('org_admin', 'platform_admin')
def list_folders(org_id):
    if not _is_org_admin(org_id, g.current_user):
        return jsonify({"error": "Not your organization"}), 403
    folders_col = get_collection('org_folders')
    folders = list(folders_col.find({"organization_id": ObjectId(org_id)}))
    for f in folders:
        f["_id"] = str(f["_id"])
        f["organization_id"] = str(f["organization_id"])
        f["parent_folder_id"] = str(f["parent_folder_id"]) if f.get("parent_folder_id") else None
    return jsonify({"success": True, "data": folders}), 200


@org_bp.route('/<org_id>/folders', methods=['POST'])
@require_role('org_admin', 'platform_admin')
def create_folder(org_id):
    """Free-form named folders, like a file explorer - classes get assigned
    into these (moved or copied in), up to MAX_FOLDER_DEPTH levels. Purely
    an org-side organizational lens: examiners/students never see this,
    their classes look exactly the same either way."""
    if not _is_org_admin(org_id, g.current_user):
        return jsonify({"error": "Not your organization"}), 403

    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Folder name is required"}), 400

    parent_folder_id = data.get("parent_folder_id")
    folders_col = get_collection('org_folders')

    if parent_folder_id:
        parent = folders_col.find_one({"_id": ObjectId(parent_folder_id), "organization_id": ObjectId(org_id)})
        if not parent:
            return jsonify({"error": "Parent folder not found"}), 404
        if _folder_depth(parent_folder_id) >= MAX_FOLDER_DEPTH:
            return jsonify({"error": f"Folders can only be nested {MAX_FOLDER_DEPTH} levels deep"}), 400

    folder = {
        "organization_id": ObjectId(org_id),
        "parent_folder_id": ObjectId(parent_folder_id) if parent_folder_id else None,
        "name": name,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = folders_col.insert_one(folder)
    return jsonify({"success": True, "data": {"_id": str(result.inserted_id), "name": name}}), 201


@org_bp.route('/<org_id>/folders/<folder_id>', methods=['PATCH'])
@require_role('org_admin', 'platform_admin')
def update_folder(org_id, folder_id):
    """Rename and/or move (re-parent) a folder."""
    if not _is_org_admin(org_id, g.current_user):
        return jsonify({"error": "Not your organization"}), 403

    folders_col = get_collection('org_folders')
    folder = folders_col.find_one({"_id": ObjectId(folder_id), "organization_id": ObjectId(org_id)})
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    data = request.json or {}
    update = {"updated_at": datetime.utcnow()}

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Folder name cannot be empty"}), 400
        update["name"] = name

    if "parent_folder_id" in data:
        new_parent_id = data.get("parent_folder_id")
        if new_parent_id:
            if str(new_parent_id) == str(folder_id):
                return jsonify({"error": "A folder cannot be its own parent"}), 400
            parent = folders_col.find_one({"_id": ObjectId(new_parent_id), "organization_id": ObjectId(org_id)})
            if not parent:
                return jsonify({"error": "Parent folder not found"}), 404
            if _folder_depth(new_parent_id) >= MAX_FOLDER_DEPTH:
                return jsonify({"error": f"Folders can only be nested {MAX_FOLDER_DEPTH} levels deep"}), 400
            update["parent_folder_id"] = ObjectId(new_parent_id)
        else:
            update["parent_folder_id"] = None

    folders_col.update_one({"_id": ObjectId(folder_id)}, {"$set": update})
    return jsonify({"success": True}), 200


@org_bp.route('/<org_id>/folders/<folder_id>', methods=['DELETE'])
@require_role('org_admin', 'platform_admin')
def delete_folder(org_id, folder_id):
    """Refuses to delete a non-empty folder (child folders or assigned
    classes) rather than cascading - avoids silently orphaning/losing track
    of classes a folder was organizing."""
    if not _is_org_admin(org_id, g.current_user):
        return jsonify({"error": "Not your organization"}), 403

    folders_col = get_collection('org_folders')
    folder = folders_col.find_one({"_id": ObjectId(folder_id), "organization_id": ObjectId(org_id)})
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    if folders_col.count_documents({"parent_folder_id": ObjectId(folder_id)}) > 0:
        return jsonify({"error": "Move or delete this folder's sub-folders first"}), 400
    if get_collection('classes').count_documents({"folder_id": ObjectId(folder_id)}) > 0:
        return jsonify({"error": "Move the classes out of this folder first"}), 400

    folders_col.delete_one({"_id": ObjectId(folder_id)})
    return jsonify({"success": True}), 200


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
