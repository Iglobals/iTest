from flask import Blueprint, request, jsonify
from app.uploads.cloudinary_client import upload_image

uploads_bp = Blueprint('uploads_bp', __name__, url_prefix='/api/uploads')


@uploads_bp.route('/image', methods=['POST'])
def upload_image_route():
    if 'image' not in request.files:
        return jsonify({'error': 'Missing image file'}), 400
    result = upload_image(request.files['image'])
    return jsonify({'url': result.get('secure_url')})
