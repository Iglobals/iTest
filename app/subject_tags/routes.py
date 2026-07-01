from flask import jsonify, Blueprint

subject_tags_bp = Blueprint('subject_tags_bp', __name__, url_prefix='/api/tags')


@subject_tags_bp.route('/', methods=['GET'])
def list_tags():
    return jsonify({'message': 'Tags placeholder', 'data': []})
