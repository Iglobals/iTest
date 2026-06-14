from flask import Blueprint

payments_bp = Blueprint('payments_bp', __name__, url_prefix='/api/payments')
