from flask import jsonify, Blueprint

payments_bp = Blueprint('payments_bp', __name__, url_prefix='/api/payments')


@payments_bp.route('/plans', methods=['GET'])
def list_plans():
    return jsonify({'message': 'Plans placeholder', 'data': []})
