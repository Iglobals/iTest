from flask import jsonify, request, g, Blueprint
from app.auth.decorators import require_auth
from app.users.service import update_profile, upload_avatar, save_liveness_photos

users_bp = Blueprint('users_bp', __name__, url_prefix='/api/users')


def _jsonable(value):
    """Raw Mongo documents hold ObjectId/datetime values that Flask's
    jsonify can't serialize - returning one directly raised mid-response
    (a 500 / Vercel FUNCTION_INVOCATION_FAILED *after* the DB write had
    already succeeded), which is what broke the liveness and avatar saves."""
    from bson import ObjectId
    from datetime import datetime, date
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


@users_bp.route('/me', methods=['GET'])
@require_auth(redirect_on_fail=False)
def get_me():
    return jsonify(_jsonable(g.current_user))


@users_bp.route('/me', methods=['PATCH'])
@require_auth(redirect_on_fail=False)
def patch_me():
    data = request.get_json(force=True)
    updated = update_profile(str(g.current_user['_id']), data)
    return jsonify(_jsonable(updated))


@users_bp.route('/me/avatar', methods=['POST'])
@require_auth(redirect_on_fail=False)
def post_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'Missing avatar file'}), 400
    file = request.files['avatar']
    if not (file.mimetype or '').startswith('image/'):
        return jsonify({'error': 'Please choose an image file.'}), 400
    from app.uploads.cloudinary_client import upload_image
    try:
        upload_result = upload_image(file)
    except Exception as e:
        print(f"[AVATAR] Cloudinary upload failed: {e}")
        return jsonify({'error': 'Could not upload the image. Please try again.'}), 502
    updated = upload_avatar(str(g.current_user['_id']), upload_result['url'])
    return jsonify(_jsonable(updated))


@users_bp.route('/me/liveness', methods=['POST'])
@require_auth(redirect_on_fail=False)
def post_liveness():
    """One-time liveness verification - see save_liveness_photos(). Expects
    the 4 photos already uploaded (client uploads to Cloudinary directly,
    same pattern as exam question images - see app/templates/exam/builder.html),
    just their URLs here."""
    data = request.get_json(force=True) or {}
    photos = {
        'front': data.get('front'),
        'left': data.get('left'),
        'right': data.get('right'),
        'mouth_open': data.get('mouth_open'),
    }
    if not all(photos.values()):
        return jsonify({'error': 'All four photos (front, left, right, mouth_open) are required.'}), 400

    try:
        updated = save_liveness_photos(str(g.current_user['_id']), photos)
    except ValueError as e:
        return jsonify({'error': str(e)}), 409

    return jsonify(_jsonable(updated))


def _safe_next(value):
    value = value or ''
    return value if value.startswith('/') and not value.startswith('//') else None


@users_bp.route('/me/kyc/didit', methods=['POST'])
@require_auth(redirect_on_fail=False)
def start_didit():
    """Start (or resume) Didit identity verification. Returns the URL to send
    the student to; Didit redirects back to /dashboard/verification/complete."""
    from flask import url_for
    from app.utils import didit_client
    from app.users.service import start_didit_verification
    if not didit_client.is_configured():
        return jsonify({'error': 'Automatic verification is not available yet.'}), 503
    body = request.get_json(silent=True) or {}
    nxt = _safe_next(body.get('next'))
    force_new = bool(body.get('force_new'))
    callback = url_for('dashboard.verification_complete', _external=True, **({'next': nxt} if nxt else {}))
    try:
        result = start_didit_verification(g.current_user, callback, force_new=force_new)
    except ValueError as e:
        return jsonify({'error': str(e)}), 409
    except didit_client.DiditError as e:
        print(f"[DIDIT] start failed for {g.current_user['_id']}: {e}")
        return jsonify({'error': 'The verification service is unavailable right now. Please try again shortly.'}), 502
    return jsonify({'success': True, **result})


@users_bp.route('/me/kyc', methods=['GET'])
@require_auth(redirect_on_fail=False)
def kyc_status():
    from app.users.service import refresh_didit_status
    user = refresh_didit_status(g.current_user)
    lv = user.get('liveness_verification') or {}
    return jsonify({'status': lv.get('status', 'not_started'), 'provider': lv.get('provider', 'manual'),
                    'reason': lv.get('reason')})
