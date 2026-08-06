from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_auth, require_role, require_feature
from app.utils.mongo import get_collection
from datetime import datetime
from bson import ObjectId
import uuid

classes_bp = Blueprint('classes', __name__, url_prefix='/api/classes')


def _teacher_entry(class_obj, user_id):
    user_id_str = str(user_id)
    for t in class_obj.get("teachers", []):
        if str(t.get("user_id")) == user_id_str:
            return t
    return None


def _is_org_admin_of(class_obj, user):
    if not class_obj.get("organization_id"):
        return False
    org = get_collection("organizations").find_one({"_id": class_obj["organization_id"]})
    return bool(org and str(org.get("admin_user_id")) == str(user["_id"]))


def _can_manage_class(class_obj, user, require_owner=False):
    """Whether `user` may edit/delete this class or act on its join requests."""
    if user.get("role") == "platform_admin":
        return True
    t = _teacher_entry(class_obj, user["_id"])
    if t and t.get("status", "active") == "active":
        if not require_owner or t.get("role") == "owner":
            return True
    if user.get("role") == "org_admin" and _is_org_admin_of(class_obj, user):
        return True
    return False


@classes_bp.route('/', methods=['GET'])
@require_auth(redirect_on_fail=False)
def list_classes():
    classes_col = get_collection('classes')
    try:
        role = g.current_user.get('role')
        query = {"is_active": {"$ne": False}}
        if role == 'platform_admin':
            pass
        elif role == 'org_admin':
            orgs_col = get_collection('organizations')
            org = orgs_col.find_one({"admin_user_id": g.current_user["_id"]})
            or_clauses = [{"teachers.user_id": g.current_user["_id"]}]
            if org:
                or_clauses.append({"organization_id": org["_id"]})
            query["$or"] = or_clauses
        else:
            # Teachers (and any other authenticated role) only see classes they belong to.
            query["teachers.user_id"] = g.current_user["_id"]

        classes = list(classes_col.find(query))
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
        
    from app.utils.plans import get_plan_limit
    user_plan = g.current_user.get("plan", {}).get("type", "free")
    max_classes = get_plan_limit(user_plan, "max_classes")
    
    current_count = classes_col.count_documents({"teachers.user_id": g.current_user["_id"]})
    if current_count >= max_classes:
        return jsonify({"error": f"Plan limit reached: Max {max_classes} classes allowed.", "limit_reached": True}), 403
        
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
        "links": {},
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
            
        for teacher in class_obj.get("teachers", []):
            if "user_id" in teacher: teacher["user_id"] = str(teacher["user_id"])
        for student in class_obj.get("students", []):
            if "user_id" in student: student["user_id"] = str(student["user_id"])
        
        return jsonify({"success": True, "data": class_obj}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400

@classes_bp.route('/<class_id>', methods=['PUT'])
@require_role('teacher', 'org_admin', 'platform_admin')
def update_class(class_id):
    data = request.json or {}
    classes_col = get_collection('classes')
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Not found"}), 404
        if not _can_manage_class(class_obj, g.current_user):
            return jsonify({"error": "Forbidden"}), 403

        update_data = {"updated_at": datetime.utcnow()}
        for field in ["name", "description", "cover_image_url"]:
            if field in data:
                update_data[field] = data[field]

        classes_col.update_one({"_id": ObjectId(class_id)}, {"$set": update_data})
        return jsonify({"success": True, "message": "Class updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@classes_bp.route('/<class_id>', methods=['DELETE'])
@require_role('teacher', 'org_admin', 'platform_admin')
def delete_class(class_id):
    classes_col = get_collection('classes')
    try:
        class_obj_id = ObjectId(class_id)
        class_obj = classes_col.find_one({"_id": class_obj_id})
        if not class_obj:
            return jsonify({"error": "Not found"}), 404
        if not _can_manage_class(class_obj, g.current_user, require_owner=True):
            return jsonify({"error": "Only the class owner can delete this class"}), 403

        # Strip this class out of every exam's visibility - the exam itself survives.
        get_collection('exams').update_many(
            {"visibility.class_ids": class_obj_id},
            {"$pull": {"visibility.class_ids": class_obj_id}}
        )
        get_collection('class_broadcasts').delete_many({"class_id": str(class_id)})
        get_collection('class_messages').delete_many({"class_id": str(class_id)})
        get_collection('notifications').delete_many({"metadata.class_id": str(class_id)})

        classes_col.update_one(
            {"_id": class_obj_id},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        return jsonify({"success": True, "message": "Class deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

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

@classes_bp.route('/<class_id>/join_requests/<student_id>/respond', methods=['POST'])
@require_role('teacher', 'org_admin')
def respond_join_request(class_id, student_id):
    data = request.json or {}
    action = data.get("action")
    if action not in ["approve", "reject"]:
        return jsonify({"error": "Invalid action"}), 400

    classes_col = get_collection('classes')
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Not found"}), 404
        if not _can_manage_class(class_obj, g.current_user):
            return jsonify({"error": "Forbidden"}), 403

        student_obj_id = ObjectId(student_id)
        request_entry = next(
            (r for r in class_obj.get("join_requests", []) if str(r.get("student_id")) == str(student_obj_id)),
            None
        )
        if not request_entry:
            return jsonify({"error": "Join request not found"}), 404

        classes_col.update_one(
            {"_id": ObjectId(class_id)},
            {"$pull": {"join_requests": {"student_id": student_obj_id}}}
        )

        if action == "approve":
            existing_student_entry = next((s for s in class_obj.get("students", []) if str(s.get("user_id")) == str(student_obj_id)), None)
            if not existing_student_entry:
                classes_col.update_one(
                    {"_id": ObjectId(class_id)},
                    {"$push": {"students": {
                        "user_id": student_obj_id,
                        "status": "active",
                        "invited_at": datetime.utcnow(),
                        "joined_at": datetime.utcnow()
                    }}}
                )
            elif existing_student_entry.get("status") == "removed":
                # Approving a join request from a previously-removed student reactivates them.
                classes_col.update_one(
                    {"_id": ObjectId(class_id), "students.user_id": student_obj_id},
                    {
                        "$set": {
                            "students.$.status": "active",
                            "students.$.joined_at": datetime.utcnow(),
                        },
                        "$unset": {"students.$.removed_at": ""},
                    }
                )
            message = "Join request approved"
        else:
            message = "Join request rejected"

        return jsonify({"success": True, "message": message}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@classes_bp.route('/<class_id>/invite', methods=['POST'])
@require_role('teacher', 'org_admin')
def invite(class_id):
    data = request.json
    emails = data.get("emails", [])
    role = data.get("role", "student") # 'student' or 'teacher'
    
    classes_col = get_collection('classes')
    users_col = get_collection('users')
    notif_col = get_collection('notifications')
    
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Not found"}), 404
            
        if role == 'student':
            from app.utils.plans import get_plan_limit
            user_plan = g.current_user.get("plan", {}).get("type", "free")
            max_students = get_plan_limit(user_plan, "max_students_per_class")
            
            current_students = sum(1 for s in class_obj.get("students", []) if s.get("status") != "removed")
            if current_students + len(emails) > max_students:
                return jsonify({"error": f"Plan limit reached: Max {max_students} students allowed.", "limit_reached": True}), 403
        
        invited_users = []
        skipped_users = []
        
        for email in emails:
            user = users_col.find_one({"email": email})
            if user:
                user_id = user["_id"]

                # Check if user is already in the class. A "removed" student doesn't
                # count as a member here - that's exactly the record a direct re-invite
                # should be allowed to reactivate.
                existing_student_entry = next((s for s in class_obj.get("students", []) if str(s.get("user_id")) == str(user_id)), None)
                is_blocked_student = existing_student_entry is not None and existing_student_entry.get("status") != "removed"
                is_existing_teacher = any(str(t.get("user_id")) == str(user_id) for t in class_obj.get("teachers", []))

                if is_blocked_student or is_existing_teacher:
                    skipped_users.append({"email": email, "reason": "already_member"})
                    continue # Skip already invited or existing members

                if role == 'student':
                    if existing_student_entry:
                        # Reactivate their previously-removed record instead of pushing a duplicate.
                        classes_col.update_one(
                            {"_id": ObjectId(class_id), "students.user_id": user_id},
                            {
                                "$set": {
                                    "students.$.status": "pending",
                                    "students.$.invited_at": datetime.utcnow(),
                                    "students.$.joined_at": None,
                                },
                                "$unset": {"students.$.removed_at": ""},
                            }
                        )
                    else:
                        classes_col.update_one({"_id": ObjectId(class_id)}, {"$push": {"students": {"user_id": user_id, "status": "pending", "invited_at": datetime.utcnow(), "joined_at": None}}})
                else:
                    classes_col.update_one({"_id": ObjectId(class_id)}, {"$push": {"teachers": {"user_id": user_id, "role": "collaborator", "status": "pending", "added_at": datetime.utcnow()}}})
                
                notif_col.insert_one({
                    "recipient_id": user_id,
                    "sender_id": g.current_user["_id"],
                    "type": "class_invite",
                    "title": f"Class Invitation: {class_obj.get('name')}",
                    "body": f"You have been invited to join {class_obj.get('name')} as an examiner." if role == 'teacher' else f"You have been invited to join {class_obj.get('name')} as a student.",
                    "metadata": {"class_id": class_id, "role": role},
                    "is_read": False,
                    "created_at": datetime.utcnow()
                })
                invited_users.append(email)
            else:
                skipped_users.append({"email": email, "reason": "user_not_found"})
                
        message = f"Invited {len(invited_users)} new users."
        if skipped_users:
            message += f" Skipped {len(skipped_users)} users (already members or not found)."
            
        return jsonify({"success": True, "message": message, "invited": invited_users, "skipped": skipped_users}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@classes_bp.route('/<class_id>/uninvite', methods=['POST'])
@require_role('teacher', 'org_admin')
def uninvite(class_id):
    """Uninvite a user (remove pending invitation) and optionally reinvite with correct role."""
    data = request.json
    user_id = data.get("user_id")
    reinvite_as = data.get("reinvite_as")  # Optional: 'student' or 'teacher'
    
    classes_col = get_collection('classes')
    users_col = get_collection('users')
    notif_col = get_collection('notifications')
    
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Class not found"}), 404
            
        user_obj_id = ObjectId(user_id)
        user = users_col.find_one({"_id": user_obj_id})
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Remove from both students and teachers arrays
        classes_col.update_one(
            {"_id": ObjectId(class_id)},
            {"$pull": {
                "students": {"user_id": user_obj_id},
                "teachers": {"user_id": user_obj_id}
            }}
        )
        
        # Delete related notification
        notif_col.delete_many({
            "recipient_id": user_obj_id,
            "type": "class_invite",
            "metadata.class_id": class_id
        })
        
        message = f"Uninvited {user.get('email', 'user')} successfully."
        
        # Reinvite with correct role if specified
        if reinvite_as in ['student', 'teacher']:
            if reinvite_as == 'student':
                classes_col.update_one(
                    {"_id": ObjectId(class_id)},
                    {"$push": {"students": {"user_id": user_obj_id, "status": "pending", "invited_at": datetime.utcnow(), "joined_at": None}}}
                )
            else:
                classes_col.update_one(
                    {"_id": ObjectId(class_id)},
                    {"$push": {"teachers": {"user_id": user_obj_id, "role": "collaborator", "status": "pending", "added_at": datetime.utcnow()}}}
                )
            
            # Send new notification
            notif_col.insert_one({
                "recipient_id": user_obj_id,
                "sender_id": g.current_user["_id"],
                "type": "class_invite",
                "title": f"Class Invitation: {class_obj.get('name')}",
                "body": f"You have been invited to join {class_obj.get('name')} as {'an examiner' if reinvite_as == 'teacher' else 'a student'}.",
                "metadata": {"class_id": class_id, "role": reinvite_as},
                "is_read": False,
                "created_at": datetime.utcnow()
            })
            
            message = f"Reinvited {user.get('email', 'user')} as {reinvite_as}."
            
        return jsonify({"success": True, "message": message}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400



@classes_bp.route('/<class_id>/members', methods=['GET'])
@require_auth()
def get_members(class_id):
    classes_col = get_collection('classes')
    users_col = get_collection('users')
    
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Not found"}), 404
            
        members = []
        invitations = []
        
        # Org info cache
        org_cache = {}
        
        for t in class_obj.get("teachers", []):
            u = users_col.find_one({"_id": t["user_id"]})
            if u:
                org_name = ""
                if u.get("organization_id"):
                    org_id = str(u["organization_id"])
                    if org_id not in org_cache:
                        org = get_collection("organizations").find_one({"_id": ObjectId(org_id)})
                        org_cache[org_id] = org.get("name") if org else ""
                    org_name = org_cache[org_id]
                    
                status = t.get("status", "active")
                data = {"user_id": str(u["_id"]), "name": u.get("full_name"), "email": u.get("email"), "role": "examiner", "status": status, "organization": org_name}
                if status in ["pending", "rejected"]:
                    invitations.append(data)
                else:
                    members.append(data)
                
        for s in class_obj.get("students", []):
            if s.get("status") == "removed":
                continue
            u = users_col.find_one({"_id": s["user_id"]})
            if u:
                org_name = ""
                if u.get("organization_id"):
                    org_id = str(u["organization_id"])
                    if org_id not in org_cache:
                        org = get_collection("organizations").find_one({"_id": ObjectId(org_id)})
                        org_cache[org_id] = org.get("name") if org else ""
                    org_name = org_cache[org_id]
                    
                status = s.get("status", "pending")
                data = {"user_id": str(u["_id"]), "name": u.get("full_name"), "email": u.get("email"), "role": "student", "status": status, "organization": org_name}
                if status in ["pending", "declined"]:
                    invitations.append(data)
                else:
                    members.append(data)
                
        join_requests = []
        for r in class_obj.get("join_requests", []):
            u = users_col.find_one({"_id": r["student_id"]})
            if u:
                join_requests.append({
                    "student_id": str(u["_id"]),
                    "name": u.get("full_name"),
                    "email": u.get("email"),
                    "status": r.get("status", "pending"),
                    "last_requested_at": r.get("last_requested_at").isoformat() if r.get("last_requested_at") else None
                })

        return jsonify({"success": True, "data": {"members": members, "invitations": invitations, "join_requests": join_requests}}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400

@classes_bp.route('/<class_id>/remove_org', methods=['POST'])
@require_role('teacher')
def remove_org(class_id):
    classes_col = get_collection('classes')
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Not found"}), 404
            
        classes_col.update_one(
            {"_id": ObjectId(class_id)},
            {"$set": {"organization_id": None, "organization_status": "none"}}
        )
        return jsonify({"success": True, "message": "Organization removed from class"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@classes_bp.route('/<class_id>/remove_member', methods=['POST'])
@require_role('teacher')
def remove_member(class_id):
    data = request.json
    member_id = data.get("user_id")
    role = data.get("role")
    
    classes_col = get_collection('classes')
    try:
        if role == 'student':
            # Soft-delete: keep the record (status: "removed") instead of $pull-ing it,
            # so the join-link handler still recognizes this user_id and blocks rejoin.
            # A teacher can still bring them back via a direct re-invite (see invite()).
            classes_col.update_one(
                {"_id": ObjectId(class_id), "students.user_id": ObjectId(member_id)},
                {"$set": {
                    "students.$.status": "removed",
                    "students.$.removed_at": datetime.utcnow()
                }}
            )
        else:
            classes_col.update_one(
                {"_id": ObjectId(class_id)},
                {"$pull": {"teachers": {"user_id": ObjectId(member_id)}}}
            )
        return jsonify({"success": True, "message": "Member removed successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@classes_bp.route('/<class_id>/respond_invite', methods=['POST'])
@require_auth()
def respond_invite(class_id):
    data = request.json
    action = data.get("action")
    if action not in ["accept", "decline", "reject"]:
        return jsonify({"error": "Invalid action"}), 400
        
    status_map = {"accept": "active", "decline": "declined", "reject": "declined"}
    new_status = status_map[action]
    
    classes_col = get_collection('classes')
    user_id = g.current_user['_id']
    
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return jsonify({"error": "Class not found"}), 404
            
        # Check students array
        student_entry = next((s for s in class_obj.get("students", []) if str(s.get("user_id")) == str(user_id)), None)
        if student_entry:
            # A removed student has no live invitation to respond to - block self-service
            # reactivation here so it can only happen through a teacher-initiated re-invite.
            if student_entry.get("status") == "removed":
                return jsonify({"error": "No invitation found"}), 404
            classes_col.update_one(
                {"_id": ObjectId(class_id), "students.user_id": user_id},
                {"$set": {"students.$.status": new_status}}
            )
            return jsonify({"success": True}), 200
            
        # Check teachers array
        is_teacher = any(str(t.get("user_id")) == str(user_id) for t in class_obj.get("teachers", []))
        if is_teacher:
            classes_col.update_one(
                {"_id": ObjectId(class_id), "teachers.user_id": user_id},
                {"$set": {"teachers.$.status": new_status}}
            )
            return jsonify({"success": True}), 200
            
        return jsonify({"error": "No invitation found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@classes_bp.route('/<class_id>/links/generate', methods=['POST'])
@require_role('teacher', 'org_admin')
def generate_link(class_id):
    data = request.json
    link_type = data.get("type", "student") # 'student', 'teacher', 'org'
    
    classes_col = get_collection('classes')
    try:
        token = str(uuid.uuid4())
        classes_col.update_one(
            {"_id": ObjectId(class_id)},
            {"$set": {f"links.{link_type}": token}}
        )
        return jsonify({"success": True, "token": token}), 200
    except Exception:
        return jsonify({"error": "Error generating link"}), 400

@classes_bp.route('/<class_id>/broadcast', methods=['POST'])
@require_role('teacher')
def broadcast_message(class_id):
    data = request.json
    broadcasts_col = get_collection('class_broadcasts')
    
    new_msg = {
        "class_id": str(class_id),
        "sender_id": str(g.current_user["_id"]),
        "sender_name": g.current_user.get("full_name"),
        "message": data.get("message"),
        "created_at": datetime.utcnow(),
        "reactions": []
    }
    
    result = broadcasts_col.insert_one(new_msg)
    new_msg["_id"] = str(result.inserted_id)
    return jsonify({"success": True, "data": new_msg}), 201

@classes_bp.route('/<class_id>/broadcasts', methods=['GET'])
@require_auth()
def get_broadcasts(class_id):
    broadcasts_col = get_collection('class_broadcasts')
    msgs = list(broadcasts_col.find({"class_id": str(class_id)}).sort("created_at", -1))
    for m in msgs:
        m["_id"] = str(m["_id"])
        
    return jsonify({"success": True, "data": msgs}), 200

@classes_bp.route('/<class_id>/broadcast/<msg_id>', methods=['PUT', 'DELETE'])
@require_role('teacher')
def manage_broadcast(class_id, msg_id):
    broadcasts_col = get_collection('class_broadcasts')
    try:
        msg = broadcasts_col.find_one({"_id": ObjectId(msg_id), "class_id": str(class_id)})
        if not msg:
            return jsonify({"error": "Not found"}), 404
            
        # Only sender can edit/delete
        if msg.get("sender_id") != str(g.current_user["_id"]):
            return jsonify({"error": "Unauthorized"}), 403
            
        if request.method == 'DELETE':
            broadcasts_col.delete_one({"_id": ObjectId(msg_id)})
            return jsonify({"success": True, "message": "Deleted"}), 200
            
        if request.method == 'PUT':
            new_text = request.json.get("message")
            broadcasts_col.update_one(
                {"_id": ObjectId(msg_id)},
                {"$set": {"message": new_text, "updated_at": datetime.utcnow()}}
            )
            return jsonify({"success": True, "message": "Updated"}), 200
            
    except Exception as e:
        return jsonify({"error": "Invalid ID"}), 400

@classes_bp.route('/<class_id>/broadcast/<msg_id>/react', methods=['POST'])
@require_auth()
def react_broadcast(class_id, msg_id):
    data = request.json
    icon = data.get("icon", "thumbs-up")
    broadcasts_col = get_collection('class_broadcasts')
    
    try:
        broadcasts_col.update_one(
            {"_id": ObjectId(msg_id)},
            {"$push": {
                "reactions": {
                    "user_id": str(g.current_user["_id"]),
                    "name": g.current_user.get("full_name"),
                    "icon": icon,
                    "created_at": datetime.utcnow()
                }
            }}
        )
        return jsonify({"success": True}), 200
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400

@classes_bp.route('/<class_id>/messages', methods=['POST'])
@require_feature('can_message_1on1')
def send_message(class_id):
    data = request.json
    messages_col = get_collection('class_messages')
    
    new_msg = {
        "class_id": str(class_id),
        "sender_id": str(g.current_user["_id"]),
        "receiver_id": data.get("receiver_id"),
        "message": data.get("message"),
        "created_at": datetime.utcnow()
    }
    
    result = messages_col.insert_one(new_msg)
    new_msg["_id"] = str(result.inserted_id)
    return jsonify({"success": True, "data": new_msg}), 201

@classes_bp.route('/<class_id>/messages', methods=['GET'])
@require_feature('can_message_1on1')
def get_messages(class_id):
    messages_col = get_collection('class_messages')
    user_id = str(g.current_user["_id"])
    
    msgs = list(messages_col.find({
        "class_id": str(class_id),
        "$or": [{"sender_id": user_id}, {"receiver_id": user_id}]
    }).sort("created_at", -1))
    
    for m in msgs:
        m["_id"] = str(m["_id"])
        
    return jsonify({"success": True, "data": msgs}), 200
