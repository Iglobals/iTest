from flask import Blueprint, render_template, g
from app.auth.decorators import require_auth

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@require_auth()
def index():
    role = g.current_user.get('role', 'student')
    if role == 'teacher':
        return render_template('dashboard/teacher.html')
    elif role == 'org_admin':
        return render_template('dashboard/org_admin.html')
    else:
        return render_template('dashboard/student.html')
