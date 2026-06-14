from flask import jsonify, Blueprint

notifications_bp = Blueprint('notifications_bp', __name__, url_prefix='/api/notifications')


@notifications_bp.route('/', methods=['GET'])
def list_notifications():
    return jsonify({'message': 'Notifications placeholder', 'data': []})
