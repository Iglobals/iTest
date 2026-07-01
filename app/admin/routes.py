from flask import jsonify, Blueprint

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/api/admin')


@admin_bp.route('/stats', methods=['GET'])
def platform_stats():
    return jsonify({'message': 'Admin stats placeholder'})
