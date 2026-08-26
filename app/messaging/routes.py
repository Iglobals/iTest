from flask import Blueprint, request, jsonify, g
from app.auth.decorators import require_auth
from app.utils.mongo import get_collection
from datetime import datetime
from bson import ObjectId

messaging_bp = Blueprint('messaging', __name__, url_prefix='/api/messages')

# Who is allowed to START a brand-new conversation with whom. Replying inside
# an already-existing thread only requires being one of its two participants -
# this matrix is only consulted when a thread doesn't exist yet, so a student
# can still reply to a teacher-initiated thread even though "student -> teacher"
# is the only direction a student can INITIATE.
ALLOWED_RECEIVER_ROLES = {
    'teacher': {'student', 'teacher', 'org_admin'},
    'student': {'teacher'},
    'org_admin': {'teacher'},
}


def _thread_key(user_id_a, user_id_b):
    a, b = sorted([str(user_id_a), str(user_id_b)])
    return f"{a}_{b}"


def _serialize(msg):
    msg['_id'] = str(msg['_id'])
    msg['sender_id'] = str(msg['sender_id'])
    msg['receiver_id'] = str(msg['receiver_id'])
    if msg.get('related_exam_id'):
        msg['related_exam_id'] = str(msg['related_exam_id'])
    if msg.get('created_at'):
        msg['created_at'] = msg['created_at'].isoformat()
    if msg.get('read_at'):
        msg['read_at'] = msg['read_at'].isoformat()
    return msg


@messaging_bp.route('/contacts', methods=['GET'])
@require_auth()
def list_contacts():
    """Who the current user is allowed to start a NEW conversation with.
    Students aren't given a generic picker here - they message a teacher
    directly from an exam result (see /send's related_session_id path),
    which already supplies the receiver."""
    role = g.current_user.get('role')
    user_id = g.current_user['_id']
    classes_col = get_collection('classes')
    users_col = get_collection('users')
    orgs_col = get_collection('organizations')

    contacts = []

    if role == 'teacher':
        my_classes = list(classes_col.find({"teachers.user_id": user_id, "is_active": {"$ne": False}}))

        student_ids, teacher_ids, org_ids = set(), set(), set()
        for cls in my_classes:
            for s in cls.get('students', []):
                if s.get('status') == 'active':
                    student_ids.add(s['user_id'])
            for t in cls.get('teachers', []):
                if str(t.get('user_id')) != str(user_id) and t.get('status', 'active') == 'active':
                    teacher_ids.add(t['user_id'])
            if cls.get('organization_id'):
                org_ids.add(cls['organization_id'])

        for uid in student_ids:
            u = users_col.find_one({"_id": uid})
            if u:
                contacts.append({"user_id": str(u["_id"]), "name": u.get("full_name") or u.get("email"), "role": "student"})
        for uid in teacher_ids:
            u = users_col.find_one({"_id": uid})
            if u:
                contacts.append({"user_id": str(u["_id"]), "name": u.get("full_name") or u.get("email"), "role": "teacher"})
        for oid in org_ids:
            org = orgs_col.find_one({"_id": oid})
            if org and org.get('admin_user_id'):
                admin = users_col.find_one({"_id": org['admin_user_id']})
                if admin:
                    contacts.append({"user_id": str(admin["_id"]), "name": org.get('name', 'Organization'), "role": "org_admin"})

    elif role == 'org_admin':
        my_org = orgs_col.find_one({"admin_user_id": user_id})
        if my_org:
            org_classes = list(classes_col.find({"organization_id": my_org["_id"]}))
            teacher_ids = set()
            for cls in org_classes:
                for t in cls.get('teachers', []):
                    teacher_ids.add(t['user_id'])
            for uid in teacher_ids:
                u = users_col.find_one({"_id": uid})
                if u:
                    contacts.append({"user_id": str(u["_id"]), "name": u.get("full_name") or u.get("email"), "role": "teacher"})

    return jsonify({"success": True, "data": contacts}), 200


@messaging_bp.route('/threads', methods=['GET'])
@require_auth()
def list_threads():
    messages_col = get_collection('direct_messages')
    users_col = get_collection('users')
    user_id = g.current_user['_id']

    msgs = list(messages_col.find({
        "$or": [{"sender_id": user_id}, {"receiver_id": user_id}]
    }).sort("created_at", -1))

    threads = {}
    for m in msgs:
        key = m['thread_key']
        if key in threads:
            continue
        other_id = m['receiver_id'] if str(m['sender_id']) == str(user_id) else m['sender_id']
        other = users_col.find_one({"_id": other_id})
        unread = messages_col.count_documents({
            "thread_key": key, "receiver_id": user_id, "is_read": False
        })
        threads[key] = {
            "thread_key": key,
            "other_user": {
                "user_id": str(other_id),
                "name": (other.get('full_name') or other.get('email')) if other else 'Unknown user',
            },
            "last_message": m.get('body'),
            "last_message_at": m.get('created_at').isoformat() if m.get('created_at') else None,
            "unread_count": unread,
            "related_exam_id": str(m['related_exam_id']) if m.get('related_exam_id') else None,
            "related_exam_title": m.get('related_exam_title'),
            "related_session_id": m.get('related_session_id'),
        }

    return jsonify({"success": True, "data": list(threads.values())}), 200


@messaging_bp.route('/threads/<thread_key>', methods=['GET'])
@require_auth()
def get_thread(thread_key):
    messages_col = get_collection('direct_messages')
    user_id = str(g.current_user['_id'])

    if user_id not in thread_key.split('_'):
        return jsonify({"error": "Unauthorized"}), 403

    msgs = list(messages_col.find({"thread_key": thread_key}).sort("created_at", 1))

    messages_col.update_many(
        {"thread_key": thread_key, "receiver_id": g.current_user['_id'], "is_read": False},
        {"$set": {"is_read": True, "read_at": datetime.utcnow()}}
    )

    return jsonify({"success": True, "data": [_serialize(m) for m in msgs]}), 200


@messaging_bp.route('/send', methods=['POST'])
@require_auth()
def send_message():
    data = request.json or {}
    receiver_id_raw = data.get('receiver_id')
    body = (data.get('body') or '').strip()

    if not receiver_id_raw or not body:
        return jsonify({"error": "receiver_id and body are required"}), 400

    try:
        receiver_id = ObjectId(receiver_id_raw)
    except Exception:
        return jsonify({"error": "Invalid receiver_id"}), 400

    if receiver_id == g.current_user['_id']:
        return jsonify({"error": "You cannot message yourself"}), 400

    users_col = get_collection('users')
    receiver = users_col.find_one({"_id": receiver_id})
    if not receiver:
        return jsonify({"error": "Recipient not found"}), 404

    sender_role = g.current_user.get('role')
    receiver_role = receiver.get('role')
    thread_key = _thread_key(g.current_user['_id'], receiver_id)

    messages_col = get_collection('direct_messages')
    thread_exists = messages_col.find_one({"thread_key": thread_key}) is not None

    if not thread_exists:
        allowed_targets = ALLOWED_RECEIVER_ROLES.get(sender_role, set())
        if receiver_role not in allowed_targets:
            sender_label = (sender_role or 'user').replace('_', ' ').title()
            receiver_label = (receiver_role or 'this user').replace('_', ' ')
            return jsonify({
                "error": f"{sender_label}s cannot start a conversation with a {receiver_label}."
            }), 403

    related_exam_id = None
    related_exam_title = None
    related_session_id = data.get('related_session_id') or None
    if data.get('related_exam_id'):
        try:
            related_exam_id = ObjectId(data['related_exam_id'])
            exam = get_collection('exams').find_one({"_id": related_exam_id})
            related_exam_title = exam.get('title') if exam else None
        except Exception:
            related_exam_id = None

    # Once a thread has exam context, every later reply carries it forward too -
    # otherwise the thread list (which reads context off the MOST RECENT
    # message) would lose the "grade this exam" link the moment either side
    # replies without re-attaching it.
    if not related_exam_id and not related_session_id and thread_exists:
        prior = messages_col.find_one({"thread_key": thread_key, "related_exam_id": {"$ne": None}})
        if prior:
            related_exam_id = prior.get('related_exam_id')
            related_exam_title = prior.get('related_exam_title')
            related_session_id = prior.get('related_session_id')

    new_msg = {
        "thread_key": thread_key,
        "sender_id": g.current_user['_id'],
        "receiver_id": receiver_id,
        "body": body,
        "related_exam_id": related_exam_id,
        "related_exam_title": related_exam_title,
        "related_session_id": related_session_id,
        "created_at": datetime.utcnow(),
        "is_read": False,
        "read_at": None,
    }
    result = messages_col.insert_one(new_msg)
    new_msg['_id'] = result.inserted_id
    return jsonify({"success": True, "data": _serialize(new_msg)}), 201
