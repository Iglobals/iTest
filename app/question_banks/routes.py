from flask import jsonify, Blueprint

question_banks_bp = Blueprint('question_banks_bp', __name__, url_prefix='/api/question-banks')


@question_banks_bp.route('/', methods=['GET'])
def list_banks():
    return jsonify({'message': 'Question bank listing placeholder', 'data': []})
