from flask import jsonify, Blueprint

analytics_bp = Blueprint('analytics_bp', __name__, url_prefix='/api/analytics')


@analytics_bp.route('/student/<student_id>', methods=['GET'])
def student_analytics(student_id):
    return jsonify({'message': 'Analytics placeholder', 'student_id': student_id})
