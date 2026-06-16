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
        user_email = g.current_user.get('email', '')
        
        # Build query for accessible exams
        # 1. Not deleted and published
        # 2. Not in excluded_student_ids
        # 3. Matches one of: exam_type='public' OR class_id in classes OR user_email in student_ids
        upcoming_exams = list(exams_col.find({
            "status": "published",
            "visibility.excluded_student_ids": {"$ne": user_email},
            "$or": [
                {"exam_type": {"$in": ["public", "platform_standard"]}},
                {"visibility.class_ids": {"$in": class_ids}},
                {"visibility.student_ids": user_email}
            ]
        }).sort("schedule.available_from", 1).limit(3)) if exams_col is not None else []
        
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
    else:
        # Default: hide deleted exams
        query['status'] = {"$ne": "deleted"}
        
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
    
    from bson import ObjectId
    exams_col = get_collection('exams')
    exam = exams_col.find_one({"_id": ObjectId(exam_id)})
    
    if not exam or exam.get('status') == 'deleted':
        from flask import flash, redirect, url_for
        flash("This exam has been deleted and is no longer available.", "error")
        return redirect(url_for('dashboard.index'))
        
    return render_template('exam/pre_exam.html', exam_id=exam_id, exam=exam)

@dashboard_bp.route('/sessions/<session_id>/take')
@require_auth()
def session_take(session_id):
    if g.current_user.get('role') != 'student':
        return "Only students can take exams", 403
    
    from bson import ObjectId
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')
    
    user_id = g.current_user['_id']
    user_id_str = str(user_id)
    try:
        user_id_obj = ObjectId(user_id_str)
    except:
        user_id_obj = user_id_str

    session = sessions_col.find_one({
        "_id": ObjectId(session_id), 
        "student_id": {"$in": [user_id_str, user_id_obj]}
    })
    if not session:
        return "Session not found", 404
        
    exam = exams_col.find_one({"_id": ObjectId(session['exam_id'])})
    if not exam:
        return "Exam not found", 404
        
    # Map questions based on session order
    questions_dict = {str(q.get('_id', i)): q for i, q in enumerate(exam.get('questions', []))}
    ordered_questions = []
    for qid in session.get('question_order', []):
        if qid in questions_dict:
            q = questions_dict[qid]
            q['_id'] = qid
            ordered_questions.append(q)
            
    # Default to original questions if no order found (legacy sessions)
    if not ordered_questions:
        ordered_questions = exam.get('questions', [])
        for i, q in enumerate(ordered_questions):
            if not q.get('_id'): q['_id'] = str(q.get('_id', i))
            
    return render_template('exam/take.html', 
                           exam=exam, 
                           session_id=session_id, 
                           questions=ordered_questions,
                           time_remaining=session.get('time_remaining_seconds', 3600))

@dashboard_bp.route('/my-exams')
@require_auth()
def my_exams():
    if g.current_user.get('role') != 'student':
        return "Unauthorized", 403
        
    user_id = g.current_user.get('_id')
    user_email = g.current_user.get('email', '')
    
    classes_col = get_collection('classes')
    exams_col = get_collection('exams')
    scores_col = get_collection('exam_scores')
    
    # 1. Find all exams student has taken (using postgres ExamScore model but we can't easily query it here, wait...)
    # Oh wait! In models.py ExamScore is a PostgreSQL table!
    from app.models import ExamScore
    from app.extensions import db
    
    taken_scores = ExamScore.query.filter_by(student_id=str(user_id)).order_by(ExamScore.submitted_at.desc()).all()
    taken_exam_ids = [score.exam_id for score in taken_scores]
    
    # Get the actual exam documents for taken exams
    from bson import ObjectId
    taken_exams_cursor = exams_col.find({"_id": {"$in": [ObjectId(eid) for eid in set(taken_exam_ids) if ObjectId.is_valid(eid)]}}) if exams_col is not None else []
    taken_exams_dict = {str(e['_id']): e for e in taken_exams_cursor}
    
    taken_exams = []
    for score in taken_scores:
        exam_info = taken_exams_dict.get(str(score.exam_id))
        if exam_info:
            taken_exams.append({
                "score": score,
                "exam": exam_info
            })
            
    # 2. Find all available exams
    enrolled_classes = list(classes_col.find({"students.user_id": user_id, "students.status": "active"})) if classes_col is not None else []
    class_ids = [c['_id'] for c in enrolled_classes]
    
    available_exams = list(exams_col.find({
        "status": "published",
        "visibility.excluded_student_ids": {"$ne": user_email},
        "$or": [
            {"exam_type": {"$in": ["public", "platform_standard"]}},
            {"visibility.class_ids": {"$in": class_ids}},
            {"visibility.student_ids": user_email}
        ]
    }).sort("schedule.available_from", 1)) if exams_col is not None else []
    
    # Filter out exams where max attempts have been reached
    filtered_available = []
    for exam in available_exams:
        exam_id_str = str(exam['_id'])
        attempts = sum(1 for sid in taken_exam_ids if sid == exam_id_str)
        max_attempts = exam.get('settings', {}).get('max_attempts', 1)
        if attempts < max_attempts:
            exam['attempts_made'] = attempts
            filtered_available.append(exam)
            
    return render_template('dashboard/my_exams.html', available_exams=filtered_available, taken_exams=taken_exams)

@dashboard_bp.route('/sessions/<session_id>/result')
@require_auth()
def view_result(session_id):
    user_id = g.current_user.get('_id')
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')
    
    from bson import ObjectId
    try:
        session = sessions_col.find_one({"_id": ObjectId(session_id)})
    except:
        return "Invalid session ID", 400
        
    if not session:
        return "Session not found", 404
        
    # Security: Only the student or a teacher/admin can view
    is_student = session["student_id"] == str(user_id)
    is_admin = g.current_user.get('role') in ['teacher', 'org_admin', 'platform_admin']
    if not is_student and not is_admin:
        return "Unauthorized", 403
        
    exam = exams_col.find_one({"_id": session["exam_id"]})
    if not exam:
        return "Exam not found", 404
        
    from app.models import ExamScore
    score_record = ExamScore.query.filter_by(session_id=session_id).first()
    
    # Map questions to answers
    questions = exam.get('questions', [])
    answers = session.get('answers', [])
    answer_dict = {ans.get('question_id'): ans for ans in answers}
    
    review_data = []
    for q in questions:
        q_id = q.get('_id')
        ans = answer_dict.get(q_id, {})
        student_response = ans.get('selected_option', ans.get('essay_answer', ''))
        
        is_correct = False
        correct_response = ""
        
        if q.get('type') == 'multiple_choice':
            correct_opt = next((opt for opt in q.get('options', []) if opt.get('is_correct')), None)
            if correct_opt:
                correct_response = correct_opt.get('text')
                is_correct = (student_response == correct_response)
        else:
            correct_response = "Pending Manual Grading"
            is_correct = None
            
        review_data.append({
            "question": q,
            "student_response": student_response,
            "is_correct": is_correct,
            "correct_response": correct_response
        })
        
    return render_template('exam/result.html', session=session, exam=exam, score_record=score_record, review_data=review_data, is_admin=is_admin)

@dashboard_bp.route('/exams/<slug>/submissions')
@require_auth()
def exam_submissions(slug):
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
        
    from app.models import ExamScore
    from app.extensions import db
    
    # Query all scores for this exam
    scores = ExamScore.query.filter_by(exam_id=str(exam['_id'])).order_by(ExamScore.submitted_at.desc()).all()
    
    # To get user details, we can look up from MongoDB users collection
    users_col = get_collection('users')
    from bson import ObjectId
    student_ids = [ObjectId(s.student_id) for s in scores if ObjectId.is_valid(s.student_id)]
    students = list(users_col.find({"_id": {"$in": student_ids}})) if student_ids else []
    student_dict = {str(s['_id']): s for s in students}
    
    submissions = []
    for s in scores:
        student_info = student_dict.get(s.student_id, {})
        submissions.append({
            "score_record": s,
            "student_name": student_info.get("full_name", "Unknown Student"),
            "student_email": student_info.get("email", "")
        })
        
    return render_template('dashboard/mark_exams.html', exam=exam, submissions=submissions)
