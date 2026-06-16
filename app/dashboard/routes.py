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
        
        # Fetch up to 3 recent exams created by this teacher
        recent_exams = list(exams_col.find({"created_by": user_id}).sort("created_at", -1).limit(3)) if exams_col is not None else []
        
        return render_template('dashboard/teacher.html', classes=teacher_classes, exams=recent_exams)
        
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

@dashboard_bp.route('/exams/manage')
@require_auth()
def manage_exams():
    from flask import request
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return "Unauthorized", 403
        
    exams_col = get_collection('exams')
    
    page = int(request.args.get('page', 1))
    per_page = 10
    
    query = {"created_by": g.current_user['_id']}
    
    status_filter = request.args.get('status')
    if status_filter:
        query['status'] = status_filter
        
    subject_filter = request.args.get('subject')
    if subject_filter:
        query['subject_tag_id'] = subject_filter
        
    total_exams = exams_col.count_documents(query)
    total_pages = (total_exams + per_page - 1) // per_page
    
    teacher_exams = list(exams_col.find(query)
                         .sort("created_at", -1)
                         .skip((page - 1) * per_page)
                         .limit(per_page))
    
    return render_template('dashboard/manage.html', 
                           exams=teacher_exams, 
                           page=page, 
                           total_pages=total_pages,
                           status_filter=status_filter,
                           subject_filter=subject_filter)

@dashboard_bp.route('/exams/<slug>')
@require_auth()
def exam_details(slug):
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return "Unauthorized", 403
        
    exams_col = get_collection('exams')
    exam = exams_col.find_one({"slug": slug})
    
    if not exam:
        from bson import ObjectId
        try:
            exam = exams_col.find_one({"_id": ObjectId(slug)})
        except:
            pass
            
    if not exam:
        return "Exam not found", 404
        
    # Ensure schedule dates are formatted strings for datetime-local
    if exam.get("schedule"):
        for date_field in ["available_from", "available_until"]:
            val = exam["schedule"].get(date_field)
            if val:
                from datetime import datetime
                if isinstance(val, datetime):
                    exam["schedule"][date_field] = val.strftime('%Y-%m-%dT%H:%M')
                elif isinstance(val, str) and len(val) >= 16:
                    exam["schedule"][date_field] = val[:16]
                    
    return render_template('exam/details.html', exam=exam)

@dashboard_bp.route('/exams/<slug>/builder')
@require_auth()
def exam_builder(slug):
    # Route for backward compatibility or direct builder access
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return "Unauthorized", 403
        
    exams_col = get_collection('exams')
    exam = exams_col.find_one({"slug": slug})
    
    if not exam:
        from bson import ObjectId
        try:
            exam = exams_col.find_one({"_id": ObjectId(slug)})
        except:
            pass
            
    if not exam:
        return "Exam not found", 404
        
    # Ensure schedule dates are formatted strings for datetime-local
    if exam.get("schedule"):
        for date_field in ["available_from", "available_until"]:
            val = exam["schedule"].get(date_field)
            if val:
                from datetime import datetime
                if isinstance(val, datetime):
                    exam["schedule"][date_field] = val.strftime('%Y-%m-%dT%H:%M')
                elif isinstance(val, str) and len(val) >= 16:
                    exam["schedule"][date_field] = val[:16]
                    
    return render_template('exam/details.html', exam=exam)

@dashboard_bp.route('/exams/create')
@require_auth()
def create_exam():
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return "Unauthorized", 403
    return render_template('exam/create.html')

@dashboard_bp.route('/exams/<exam_id>/edit')
@require_auth()
def edit_exam(exam_id):
    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        return "Unauthorized", 403
    from bson import ObjectId
    exams_col = get_collection('exams')
    exam = exams_col.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        return "Exam not found", 404
    return render_template('exam/edit.html', exam=exam)

@dashboard_bp.route('/exams/<exam_id>/take')
@require_auth()
def take_exam(exam_id):
    if g.current_user.get('role') != 'student':
        return "Only students can take exams", 403
    return render_template('exam/take.html', exam_id=exam_id)
