from flask import Blueprint, jsonify, request, current_app
from app.auth.decorators import require_auth
import time
import cloudinary
import cloudinary.utils

media_bp = Blueprint('media', __name__, url_prefix='/api/media')

@media_bp.route('/cloudinary-signature', methods=['GET'])
@require_auth()
def get_signature():
    """
    Returns a signed signature and timestamp for Cloudinary client-side uploads.
    """
    timestamp = int(time.time())
    
    cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME')
    api_key = current_app.config.get('CLOUDINARY_API_KEY')
    api_secret = current_app.config.get('CLOUDINARY_API_SECRET')
    
    if not (cloud_name and api_key and api_secret):
        return jsonify({"error": "Cloudinary credentials not configured on the server"}), 500

    params_to_sign = {
        "timestamp": timestamp,
    }
    
    signature = cloudinary.utils.api_sign_request(params_to_sign, api_secret)
    
    return jsonify({
        "success": True,
        "signature": signature,
        "timestamp": timestamp,
        "cloud_name": cloud_name,
        "api_key": api_key
    }), 200
