from flask import jsonify, request, g, Blueprint
from app.auth.decorators import require_auth
from app.users.service import update_profile, upload_avatar, save_liveness_photos

users_bp = Blueprint('users_bp', __name__, url_prefix='/api/users')


@users_bp.route('/me', methods=['GET'])
@require_auth(redirect_on_fail=False)
def get_me():
    return jsonify(g.current_user)


@users_bp.route('/me', methods=['PATCH'])
@require_auth(redirect_on_fail=False)
def patch_me():
    data = request.get_json(force=True)
    updated = update_profile(str(g.current_user['_id']), data)
    return jsonify(updated)


@users_bp.route('/me/avatar', methods=['POST'])
@require_auth(redirect_on_fail=False)
def post_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'Missing avatar file'}), 400
    file = request.files['avatar']
    from app.uploads.cloudinary_client import upload_image
    upload_result = upload_image(file)
    updated = upload_avatar(str(g.current_user['_id']), upload_result['url'])
    return jsonify(updated)


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

    return jsonify(updated)
