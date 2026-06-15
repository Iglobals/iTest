from flask import Blueprint, render_template, g
from app.auth.decorators import require_auth
from app.utils.mongo import get_collection

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@require_auth()
def index():
    role = g.current_user.get('role', 'student')
    user_id = g.current_user.get('_id')
    
    classes_col = get_collection('classes')
    exams_col = get_collection('exams')
    
    if role == 'teacher':
        # Fetch classes where teacher is the owner/collaborator
        teacher_classes = list(classes_col.find({"teachers.user_id": user_id})) if classes_col is not None else []
        class_ids = [c['_id'] for c in teacher_classes]
        upcoming_exams = list(exams_col.find({"class_id": {"$in": class_ids}, "status": "published"})) if exams_col is not None else []
        
        return render_template('dashboard/teacher.html', classes=teacher_classes, exams=upcoming_exams)
        
    elif role == 'org_admin':
        orgs_col = get_collection('organizations')
        org = orgs_col.find_one({"admin_user_id": user_id}) if orgs_col is not None else None
        
        if org:
            org_classes = list(classes_col.find({"organization_id": org['_id']})) if classes_col is not None else []
            return render_template('dashboard/org_admin.html', org=org, classes=org_classes)
        return render_template('dashboard/org_admin.html', org=None, classes=[])
        
    else:
        # Student Dashboard
        enrolled_classes = list(classes_col.find({"students.user_id": user_id, "students.status": "active"})) if classes_col is not None else []
        class_ids = [c['_id'] for c in enrolled_classes]
        upcoming_exams = list(exams_col.find({"class_id": {"$in": class_ids}, "status": "published"})) if exams_col is not None else []
        
        return render_template('dashboard/student.html', classes=enrolled_classes, exams=upcoming_exams)

@dashboard_bp.route('/exams/create')
@require_auth()
def create_exam():
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return "Unauthorized", 403
    return render_template('exam/create.html')

@dashboard_bp.route('/exams/<exam_id>/take')
@require_auth()
def take_exam(exam_id):
    if g.current_user.get('role') != 'student':
        return "Only students can take exams", 403
    return render_template('exam/take.html', exam_id=exam_id)
