from flask import Blueprint, request, jsonify, current_app
from app.utils.mongo import get_collection
from bson import ObjectId
from datetime import datetime

webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/api/webhooks')

@webhooks_bp.route('/grant-access', methods=['POST'])
def grant_access():
    """
    Webhook to grant a user access to a specific exam.
    Expected JSON payload:
    {
        "email": "user@example.com",
        "exam_id": "60d5ec49..."
    }
    Header:
        Authorization: Bearer <WEBHOOK_SECRET>
    """
    # 1. Verify Authorization
    auth_header = request.headers.get('Authorization')
    expected_secret = current_app.config.get('WEBHOOK_SECRET', 'test_secret_key_123')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized. Missing or invalid Authorization header"}), 401
    
    token = auth_header.split(' ')[1]
    if token != expected_secret:
        return jsonify({"error": "Unauthorized. Invalid token"}), 401

    data = request.json
    if not data or 'email' not in data or 'exam_id' not in data:
        return jsonify({"error": "Bad request. Missing email or exam_id"}), 400

    email = data['email'].strip().lower()
    exam_id_str = data['exam_id']

    users_col = get_collection('users')
    exams_col = get_collection('exams')
    notif_col = get_collection('notifications')

    try:
        exam_id = ObjectId(exam_id_str)
    except Exception:
        return jsonify({"error": "Invalid exam_id format"}), 400

    exam = exams_col.find_one({"_id": exam_id})
    if not exam:
        return jsonify({"error": "Exam not found"}), 404

    # 2. Find or Create User
    user = users_col.find_one({"email": email})
    if not user:
        # Create a placeholder user
        new_user = {
            "email": email,
            "full_name": email.split('@')[0],
            "role": "student",
            "is_active": True,
            "onboarded": False,
            "placeholder": True,
            "created_at": datetime.utcnow()
        }
        result = users_col.insert_one(new_user)
        user_id = result.inserted_id
        user = new_user
        user["_id"] = user_id
    else:
        user_id = user["_id"]

    # 3. Grant Access to the Exam
    # Make sure we don't duplicate
    current_student_ids = exam.get("visibility", {}).get("student_ids", [])
    
    # Store ObjectIds or emails? The existing exam codebase uses ObjectIds for student_ids in some places, 
    # but the routes code uses emails for student_ids string sometimes. We should push the email string if that's standard,
    # or the user ObjectId. Wait, `app/exams/routes.py` expects ObjectIds inside class_ids, student_ids.
    # In my previous check: `vis["student_ids"] = [str(i) for i in vis.get("student_ids", [])]` shows they are typically ObjectId or strings.
    # We will just append the string email to student_ids to be safe, because the access query checks `{'visibility.student_ids': email}` or `ObjectId`.
    # Let's push both the email and the ObjectId to be absolutely sure, or let's push the email string as that's what dashboard my_exams queries.
    
    # Let's check dashboard/routes.py my_exams query: 
    # `{'visibility.student_ids': g.current_user['email']}`
    # Yes, it queries by email!
    
    if email not in current_student_ids:
        exams_col.update_one(
            {"_id": exam_id},
            {"$addToSet": {"visibility.student_ids": email}}
        )

    # 4. Notify User
    notif_col.insert_one({
        "recipient_id": user_id,
        "sender_id": "system",
        "type": "exam_access",
        "title": "New Exam Access",
        "body": f"You have been granted access to the exam: {exam.get('title')}",
        "metadata": {"exam_id": str(exam_id)},
        "is_read": False,
        "created_at": datetime.utcnow()
    })

    return jsonify({
        "success": True, 
        "message": f"Access granted for {email} to exam {exam_id_str}",
        "user_created": user.get('placeholder', False)
    }), 200


@webhooks_bp.route('/didit', methods=['POST'])
def didit_webhook():
    """Didit verification results. Signature-checked against
    DIDIT_WEBHOOK_SECRET (see app/utils/didit_client.verify_webhook); after
    that, always 200 so Didit doesn't retry on our own processing errors -
    same policy as HelpSend's handleDiditWebhook."""
    from app.utils import didit_client
    from app.users.service import apply_didit_result

    raw = request.get_data()
    if not didit_client.verify_webhook(raw, request.headers):
        return jsonify({"error": "Invalid signature"}), 401
    try:
        import json as _json
        payload = _json.loads(raw or b'{}')
        parsed = didit_client.parse_result(payload)
        user = apply_didit_result(parsed)
        if not user:
            print(f"[DIDIT] webhook: no user for session={parsed.get('session_id')} vendor={parsed.get('user_id')}")
        return jsonify({"success": bool(user)}), 200
    except Exception as e:
        print(f"[DIDIT] webhook processing failed: {e}")
        return jsonify({"success": False}), 200
