from flask import jsonify, request, session, Blueprint
from app.auth.decorators import require_auth
from app.users.service import update_profile, upload_avatar

users_bp = Blueprint('users_bp', __name__, url_prefix='/api/users')


@users_bp.route('/me', methods=['GET'])
@require_auth
def get_me():
    return jsonify(session.get('user'))


@users_bp.route('/me', methods=['PATCH'])
@require_auth
def patch_me():
    data = request.get_json(force=True)
    user = session.get('user')
    updated = update_profile(str(user.get('_id')), data)
    session['user'] = updated
    return jsonify(updated)


@users_bp.route('/me/avatar', methods=['POST'])
@require_auth
def post_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'Missing avatar file'}), 400
    file = request.files['avatar']
    from app.uploads.cloudinary_client import upload_image
    upload_result = upload_image(file)
    user = session.get('user')
    updated = upload_avatar(str(user.get('_id')), upload_result['url'])
    session['user'] = updated
    return jsonify(updated)
