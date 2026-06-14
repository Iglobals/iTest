from flask import jsonify, Blueprint

results_bp = Blueprint('results_bp', __name__, url_prefix='/api/results')


@results_bp.route('/student/<student_id>', methods=['GET'])
def get_results(student_id):
    return jsonify({'message': 'Results placeholder', 'student_id': student_id})
