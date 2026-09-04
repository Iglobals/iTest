from flask import Blueprint, render_template, g
from app.auth.decorators import require_auth
from app.utils.mongo import get_collection
from app.utils.grading import is_answer_correct, resolve_correct_text, resolve_option_text

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
        teacher_classes = list(classes_col.find({"teachers.user_id": user_id, "is_active": {"$ne": False}})) if classes_col is not None else []
        
        # Fetch up to 3 recent exams created by this teacher
        recent_exams = list(exams_col.find({"created_by": user_id}).sort("created_at", -1).limit(3)) if exams_col is not None else []
        
        return render_template('dashboard/teacher.html', classes=teacher_classes, exams=recent_exams)
        
    elif role == 'org_admin':
        orgs_col = get_collection('organizations')
        org = orgs_col.find_one({"admin_user_id": user_id}) if orgs_col is not None else None

        if org:
            org_classes = list(classes_col.find({"organization_id": org['_id'], "is_active": {"$ne": False}})) if classes_col is not None else []

            # Real counts instead of the old hardcoded 0s - distinct people,
            # not a sum of memberships (one teacher/student can be on several
            # of the org's classes).
            teacher_ids = set()
            student_ids = set()
            for cls in org_classes:
                for t in cls.get("teachers", []):
                    if t.get("status", "active") == "active":
                        teacher_ids.add(str(t.get("user_id")))
                for s in cls.get("students", []):
                    if s.get("status", "active") == "active":
                        student_ids.add(str(s.get("user_id")))

            return render_template(
                'dashboard/org_admin.html', org=org, classes=org_classes,
                total_teachers=len(teacher_ids), total_students=len(student_ids),
            )
        return render_template('dashboard/org_admin.html', org=None, classes=[], total_teachers=0, total_students=0)
        
    else:
        # Student Dashboard
        enrolled_classes = list(classes_col.find({"students.user_id": user_id, "students.status": "active", "is_active": {"$ne": False}})) if classes_col is not None else []
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

@dashboard_bp.route('/classes')
@require_auth()
def classes():
    from flask import request
    role = g.current_user.get('role')
    if role not in ['teacher', 'org_admin', 'student']:
        return "Unauthorized", 403
        
    classes_col = get_collection('classes')
    user_id = g.current_user['_id']
    user_id_str = str(user_id)
    
    if role == 'org_admin':
        # An org_admin manages classes by ORGANIZATION, not by personally
        # sitting in a class's teachers[] array - a class an examiner made
        # and later attached to the org should show here even though the
        # org_admin was never individually added as one of its teachers.
        # (Previously this branch reused the teacher query above, so it only
        # ever showed classes the org_admin happened to be a personal member
        # of - i.e. almost always empty, always falling back to the "Create
        # Class" empty state even for an org with real classes.)
        orgs_col = get_collection('organizations')
        org = orgs_col.find_one({"admin_user_id": user_id}) if orgs_col is not None else None
        if not org:
            return render_template('dashboard/org_classes.html', org=None, classes_json='[]')

        org_classes = list(classes_col.find({"organization_id": org['_id'], "is_active": {"$ne": False}})) if classes_col is not None else []
        import json as _json
        classes_json = _json.dumps([{
            "_id": str(c["_id"]),
            "name": c.get("name", "Untitled"),
            "folder_id": str(c["folder_id"]) if c.get("folder_id") else None,
            "student_count": len([s for s in c.get("students", []) if s.get("status", "active") not in ("removed",)]),
        } for c in org_classes])
        return render_template('dashboard/org_classes.html', org=org, classes_json=classes_json)

    if role == 'teacher':
        teacher_classes = list(classes_col.find({"teachers.user_id": user_id, "is_active": {"$ne": False}})) if classes_col is not None else []
        active_classes = []
        invitations = []
        for cls in teacher_classes:
            for t in cls.get('teachers', []):
                if str(t.get('user_id')) == user_id_str:
                    status = t.get('status', 'active')
                    cls['current_user_status'] = status
                    if status == 'pending':
                        invitations.append(cls)
                    elif status == 'active':
                        active_classes.append(cls)
                    break
        return render_template('dashboard/classes.html', classes=active_classes, invitations=invitations)
    else:
        student_classes = list(classes_col.find({"students.user_id": user_id, "is_active": {"$ne": False}})) if classes_col is not None else []
        active_classes = []
        invitations = []
        for cls in student_classes:
            for s in cls.get('students', []):
                if str(s.get('user_id')) == user_id_str:
                    status = s.get('status', 'pending')
                    cls['current_student_status'] = status
                    cls['current_user_status'] = status
                    if status == 'pending':
                        invitations.append(cls)
                    elif status == 'active':
                        active_classes.append(cls)
                    break
        return render_template('dashboard/student_classes.html', classes=active_classes, invitations=invitations)

@dashboard_bp.route('/classes/create', methods=['GET'])
@require_auth()
def create_class_page():
    if g.current_user.get('role') not in ['teacher', 'org_admin']:
        return "Unauthorized", 403
        
    return render_template('dashboard/create_class.html')

@dashboard_bp.route('/exams/manage')
@require_auth()
def manage_exams():
    # org_admin never creates exams (they only view their org's class/exam
    # performance - see the org_performance view) so this teacher-only,
    # "exams I created" page doesn't apply to them.
    from flask import request
    if g.current_user.get('role') not in ['teacher', 'platform_admin']:
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


def _class_student_ids(cls):
    """Active (non-removed) student user_ids on a class, as strings - matches
    how ExamScore.student_id is stored in Postgres (Text, not ObjectId)."""
    return [str(s.get('user_id')) for s in cls.get('students', []) if s.get('status', 'active') != 'removed']


def _class_exam_ids(exams_col, class_obj_id):
    """Exam ids (as strings) visible to a class - exams reference classes via
    visibility.class_ids (a list of ObjectId), never the other way round."""
    exams = list(exams_col.find({"visibility.class_ids": class_obj_id}, {"_id": 1})) if exams_col is not None else []
    return [str(e['_id']) for e in exams]


def _aggregate_scores(exam_ids, student_ids):
    """Collective pass/fail/average stats for a set of exams x students.
    Mirrors the same score_percent/passed columns view_result()/grades() use -
    see ExamScore in app/models.py - so these numbers agree with what
    students/teachers see on their own results pages."""
    from app.models import ExamScore
    if not exam_ids or not student_ids:
        return {"attempts": 0, "passed": 0, "failed": 0, "avg_percent": 0}
    scores = ExamScore.query.filter(
        ExamScore.exam_id.in_(exam_ids),
        ExamScore.student_id.in_(student_ids),
    ).all()
    if not scores:
        return {"attempts": 0, "passed": 0, "failed": 0, "avg_percent": 0}
    passed = sum(1 for s in scores if s.passed)
    avg_percent = sum(float(s.score_percent) for s in scores) / len(scores)
    return {
        "attempts": len(scores),
        "passed": passed,
        "failed": len(scores) - passed,
        "avg_percent": round(avg_percent, 1),
    }


@dashboard_bp.route('/organizations/performance')
@require_auth()
def org_performance():
    """Read-only, folder-organized view of exam/performance stats across the
    org's classes - this is what replaced "Manage Exams" for org_admin, since
    the org doesn't create exams, only looks at how its classes are doing."""
    if g.current_user.get('role') != 'org_admin':
        return "Unauthorized", 403

    from bson import ObjectId
    import json as _json

    orgs_col = get_collection('organizations')
    classes_col = get_collection('classes')
    exams_col = get_collection('exams')
    org = orgs_col.find_one({"admin_user_id": g.current_user['_id']}) if orgs_col is not None else None
    if not org:
        return render_template('dashboard/org_performance.html', org=None, classes_json='[]')

    org_classes = list(classes_col.find({"organization_id": org['_id'], "is_active": {"$ne": False}})) if classes_col is not None else []

    classes_data = []
    for cls in org_classes:
        student_ids = _class_student_ids(cls)
        exam_ids = _class_exam_ids(exams_col, cls['_id'])
        stats = _aggregate_scores(exam_ids, student_ids)
        classes_data.append({
            "_id": str(cls["_id"]),
            "name": cls.get("name", "Untitled"),
            "folder_id": str(cls["folder_id"]) if cls.get("folder_id") else None,
            "student_count": len(student_ids),
            "exam_count": len(exam_ids),
            **stats,
        })

    return render_template('dashboard/org_performance.html', org=org, classes_json=_json.dumps(classes_data))


@dashboard_bp.route('/organizations/classes/<class_id>/performance')
@require_auth()
def class_performance(class_id):
    """Drill-down from org_performance: one class's exams and every student's
    individual results, plus the collective pass/fail numbers for it."""
    if g.current_user.get('role') != 'org_admin':
        return "Unauthorized", 403

    from bson import ObjectId
    from flask import flash, redirect, url_for
    from app.organizations.routes import _is_org_admin
    from app.models import ExamScore

    classes_col = get_collection('classes')
    exams_col = get_collection('exams')
    users_col = get_collection('users')

    try:
        cls = classes_col.find_one({"_id": ObjectId(class_id)}) if classes_col is not None else None
    except Exception:
        cls = None
    if not cls:
        flash("Class not found.", "error")
        return redirect(url_for('dashboard.org_performance'))
    if not cls.get("organization_id") or not _is_org_admin(cls["organization_id"], g.current_user):
        flash("That class isn't part of your organization.", "error")
        return redirect(url_for('dashboard.org_performance'))

    student_ids = _class_student_ids(cls)
    exams = list(exams_col.find({"visibility.class_ids": cls['_id']})) if exams_col is not None else []
    exam_ids = [str(e['_id']) for e in exams]
    overall = _aggregate_scores(exam_ids, student_ids)

    exam_rows = []
    for exam in exams:
        stats = _aggregate_scores([str(exam['_id'])], student_ids)
        exam_rows.append({"name": exam.get("title", "Untitled Exam"), "slug": exam.get("slug"), **stats})

    scores = []
    if exam_ids and student_ids:
        scores = ExamScore.query.filter(
            ExamScore.exam_id.in_(exam_ids),
            ExamScore.student_id.in_(student_ids),
        ).order_by(ExamScore.submitted_at.desc()).all()

    students_by_id = {}
    if users_col is not None and student_ids:
        valid_ids = [ObjectId(sid) for sid in student_ids if ObjectId.is_valid(sid)]
        students_by_id = {str(u['_id']): u for u in users_col.find({"_id": {"$in": valid_ids}})}

    student_rows = {}
    for sid in student_ids:
        user = students_by_id.get(sid)
        student_rows[sid] = {
            "name": user.get("full_name", "Unknown") if user else "Unknown",
            "attempts": 0, "passed": 0, "failed": 0, "best_percent": 0,
        }
    for score in scores:
        row = student_rows.get(score.student_id)
        if not row:
            continue
        row["attempts"] += 1
        if score.passed:
            row["passed"] += 1
        else:
            row["failed"] += 1
        row["best_percent"] = max(row["best_percent"], float(score.score_percent))

    return render_template(
        'dashboard/class_performance.html', cls=cls, overall=overall,
        exam_rows=exam_rows, student_rows=list(student_rows.values()),
    )


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
                    try:
                        exam["schedule"][date_field] = val.strftime('%Y-%m-%dT%H:%M')
                    except Exception:
                        exam["schedule"][date_field] = ""
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
                    try:
                        exam["schedule"][date_field] = val.strftime('%Y-%m-%dT%H:%M')
                    except Exception:
                        exam["schedule"][date_field] = ""
                elif isinstance(val, str) and len(val) >= 16:
                    exam["schedule"][date_field] = val[:16]
                    
    return render_template('exam/builder.html', exam=exam)

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
    from flask import flash, redirect, url_for
    from bson import ObjectId
    from app.utils.access import is_exam_open_now, can_student_access_exam, get_active_class_ids_for_student

    if g.current_user.get('role') != 'student':
        return "Only students can take exams", 403

    exams_col = get_collection('exams')
    exam = exams_col.find_one({"_id": ObjectId(exam_id)})

    if not exam or exam.get('status') == 'deleted':
        flash("This exam has been deleted and is no longer available.", "error")
        return redirect(url_for('dashboard.index'))

    if exam.get('status') != 'published':
        flash("This exam is not currently available.", "error")
        return redirect(url_for('dashboard.index'))

    if not is_exam_open_now(exam):
        flash("This exam is not open at this time.", "error")
        return redirect(url_for('dashboard.index'))

    user_email = g.current_user.get('email', '')
    class_ids = get_active_class_ids_for_student(g.current_user['_id'])
    if not can_student_access_exam(exam, user_email, class_ids):
        flash("You do not have access to this exam.", "error")
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

    from app.sessions.routes import ensure_session_not_expired
    session = ensure_session_not_expired(session, exam)
    if session.get('status') != 'in_progress':
        from flask import flash, redirect, url_for
        flash("This exam session has ended.", "error")
        return redirect(url_for('dashboard.my_exams'))

    # Use question_snapshot if available (preserves exam state at time of taking)
    # This ensures students see the same questions even if exam is updated
    if session.get('question_snapshot'):
        ordered_questions = []
        questions_dict = {str(q.get('_id')): q for q in session['question_snapshot']}
        for qid in session.get('question_order', []):
            if qid in questions_dict:
                ordered_questions.append(questions_dict[qid])
    else:
        # Fallback for old sessions without snapshot
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

    try:
        classes_col = get_collection('classes')
        exams_col = get_collection('exams')

        # 1. Find all exams student has taken (using postgres ExamScore model)
        from app.models import ExamScore
        from bson import ObjectId

        taken_scores = ExamScore.query.filter_by(student_id=str(user_id)).order_by(ExamScore.submitted_at.desc()).all()
        taken_exam_ids = [score.exam_id for score in taken_scores if score.exam_id]

        # Get the actual exam documents for taken exams
        taken_exams_cursor = []
        if taken_exam_ids and exams_col is not None:
            valid_exam_ids = [ObjectId(eid) for eid in set(taken_exam_ids) if eid and ObjectId.is_valid(eid)]
            if valid_exam_ids:
                taken_exams_cursor = exams_col.find({"_id": {"$in": valid_exam_ids}})

        taken_exams_dict = {str(e['_id']): e for e in taken_exams_cursor}

        taken_exams = []
        for score in taken_scores:
            exam_info = taken_exams_dict.get(str(score.exam_id))
            if exam_info:
                # Ensure _id is string for template
                exam_info['_id'] = str(exam_info['_id'])
                taken_exams.append({
                    "score": score,
                    "exam": exam_info
                })

        # 2. Find all available exams
        enrolled_classes = []
        if classes_col is not None:
            enrolled_classes = list(classes_col.find({
                "students.user_id": user_id,
                "students.status": "active",
                "is_active": {"$ne": False}
            }))

        class_ids = [c['_id'] for c in enrolled_classes]

        available_exams = []
        if exams_col is not None:
            query = {
                "status": "published",
                "visibility.excluded_student_ids": {"$ne": user_email}
            }

            # Build OR condition if there are class_ids or student can access public exams
            or_conditions = [
                {"exam_type": {"$in": ["public", "platform_standard"]}}
            ]

            if class_ids:
                or_conditions.append({"visibility.class_ids": {"$in": class_ids}})

            if user_email:
                or_conditions.append({"visibility.student_ids": user_email})

            query["$or"] = or_conditions
            available_exams = list(exams_col.find(query).sort("created_at", -1))

        # Filter out exams where max attempts have been reached
        filtered_available = []
        for exam in available_exams:
            exam_id_str = str(exam['_id'])
            exam['_id'] = exam_id_str  # Ensure _id is string for template

            attempts = sum(1 for sid in taken_exam_ids if sid == exam_id_str)
            max_attempts = exam.get('settings', {}).get('max_attempts', 1)
            allow_retake = exam.get('settings', {}).get('allow_retake', False)

            # Show exam if:
            # 1. Student hasn't taken it yet (attempts == 0), OR
            # 2. Retakes are allowed (allow_retake=True means unlimited, max_attempts is just a guideline)
            # 3. If retakes NOT allowed, only show if attempts < max_attempts
            if attempts == 0:
                # Never taken - always show
                exam['attempts_made'] = attempts
                filtered_available.append(exam)
            elif allow_retake:
                # Retakes allowed - show regardless of max_attempts (it's just a counter)
                exam['attempts_made'] = attempts
                filtered_available.append(exam)
            elif attempts < max_attempts:
                # Retakes not allowed - only show if under limit
                exam['attempts_made'] = attempts
                filtered_available.append(exam)

        return render_template('dashboard/my_exams.html', available_exams=filtered_available, taken_exams=taken_exams)

    except Exception as e:
        # Log the error and show user-friendly message
        import traceback
        print(f"[MY_EXAMS ERROR] Exception occurred:")
        print(traceback.format_exc())
        return render_template('dashboard/my_exams.html', available_exams=[], taken_exams=[], error=str(e))

@dashboard_bp.route('/grades')
@require_auth()
def grades():
    if g.current_user.get('role') != 'student':
        return "Unauthorized", 403

    user_id = g.current_user.get('_id')
    exams_col = get_collection('exams')

    from app.models import ExamScore
    from bson import ObjectId

    taken_scores = ExamScore.query.filter_by(student_id=str(user_id)).order_by(ExamScore.submitted_at.desc()).all()
    taken_exam_ids = [score.exam_id for score in taken_scores if score.exam_id]

    exams_dict = {}
    if taken_exam_ids and exams_col is not None:
        valid_exam_ids = [ObjectId(eid) for eid in set(taken_exam_ids) if eid and ObjectId.is_valid(eid)]
        if valid_exam_ids:
            exams_dict = {str(e['_id']): e for e in exams_col.find({"_id": {"$in": valid_exam_ids}})}

    grades_list = []
    for score in taken_scores:
        exam_info = exams_dict.get(str(score.exam_id))
        if exam_info:
            grades_list.append({"score": score, "exam": exam_info})

    return render_template('dashboard/grades.html', grades=grades_list)


@dashboard_bp.route('/messages')
@require_auth()
def messages():
    return render_template('dashboard/messages.html')


@dashboard_bp.route('/settings')
@require_auth()
def settings():
    from flask import current_app
    ica_account_url = current_app.config.get('ICA_ACCOUNT_URL', '#')
    return render_template('dashboard/settings.html', user=g.current_user, ica_account_url=ica_account_url)


@dashboard_bp.route('/sessions/<session_id>/result')
@require_auth()
def view_result(session_id):
    user_id = g.current_user.get('_id')
    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')
    
    from bson import ObjectId
    from flask import flash, redirect, request, url_for
    # Send a failed view-result attempt back to wherever the link was clicked
    # from (Taken Exams tab, a grading page, etc.) rather than a hardcoded
    # page - the error shows as a toast there, so there's no reason to lose
    # the student's/teacher's place to show it.
    back = request.referrer or url_for('dashboard.index')

    try:
        session = sessions_col.find_one({"_id": ObjectId(session_id)})
    except:
        flash("Invalid session ID.", "error")
        return redirect(back)

    if not session:
        flash("Session not found.", "error")
        return redirect(back)

    # Security: Only the student or a teacher/admin can view
    is_student = str(session.get("student_id")) == str(user_id)
    is_admin = g.current_user.get('role') in ['teacher', 'org_admin', 'platform_admin']
    if not is_student and not is_admin:
        flash("Unauthorized to view this result.", "error")
        return redirect(back)

    exam = exams_col.find_one({"_id": session["exam_id"]})
    if not exam:
        flash("Exam not found.", "error")
        return redirect(back)

    from app.models import ExamScore
    score_record = ExamScore.query.filter_by(session_id=session_id).first()

    if is_student:
        # Check if results are published for student
        if score_record and not score_record.results_published:
            flash("Results are not yet published. Please check back later.", "info")
            return redirect(back)
        
    # Map questions to answers for detailed review
    # Use question_snapshot from session if available (preserves questions at time of taking)
    questions_to_display = session.get('question_snapshot', exam.get('questions', []))
    questions_dict = {str(q.get('_id')): q for q in questions_to_display}
    answers_dict = {ans.get('question_id'): ans for ans in session.get('answers', [])}
    
    # Get manual grades if available
    manual_grades = session.get('manual_grades', {})
    
    review_data = []
    for q_id in session.get('question_order', []):
        question = questions_dict.get(q_id)
        if not question:
            continue
            
        answer = answers_dict.get(q_id, {})
        student_answer = answer.get('selected_option', '')

        correct_answer_text = resolve_correct_text(question)
        question_type = question.get('question_type', question.get('type', 'mcq'))

        # Determine if correct - reuses the exact same resolver that computed
        # the actual score, so this review can never disagree with it.
        is_correct = None
        awarded_marks = None
        feedback = None

        essay_graded = False
        if question_type != 'essay':
            is_correct = is_answer_correct(question, student_answer)
            # student_answer is the selected option's id (see take.html) -
            # resolve it to display text/HTML for the template, same as the
            # correct answer already is via resolve_correct_text above.
            student_answer = resolve_option_text(question, student_answer) if student_answer else student_answer
        else:
            # Check for manual grading
            if q_id in manual_grades:
                awarded_marks = manual_grades[q_id].get('score', 0)
                feedback = manual_grades[q_id].get('feedback', '')
                is_correct = None  # Essays don't have true/false
                essay_graded = True

        review_data.append({
            "question": {
                "_id": q_id,
                "text": question.get('text', ''),
                "type": question_type,
                "options": question.get('options', [])
            },
            "student_response": student_answer,
            "correct_response": correct_answer_text if question_type != 'essay' else 'Manual grading required',
            "is_correct": is_correct,
            # Lets the template tell "essay not graded yet" apart from
            # "essay graded" without overloading is_correct (which is
            # meaningless for essays - see docs on the Pending Review bug).
            "essay_graded": essay_graded,
            "explanation": question.get('explanation', ''),
            "marks": question.get('marks', 1),
            "awarded_marks": awarded_marks,
            "feedback": feedback
        })
        
    teacher_name = None
    if is_student and exam.get('created_by'):
        teacher = get_collection('users').find_one({"_id": exam['created_by']})
        teacher_name = teacher.get('full_name') if teacher else None

    return render_template('exam/result.html',
                         session=session,
                         exam=exam,
                         score_record=score_record,
                         review_data=review_data,
                         is_admin=is_admin,
                         teacher_name=teacher_name)

@dashboard_bp.route('/sessions/<session_id>/grade')
@require_auth()
def grade_submission(session_id):
    from flask import flash, redirect, request, url_for
    back = request.referrer or url_for('dashboard.index')

    if g.current_user.get('role') not in ['teacher', 'org_admin', 'platform_admin']:
        flash("Unauthorized.", "error")
        return redirect(back)

    sessions_col = get_collection('exam_sessions')
    exams_col = get_collection('exams')
    users_col = get_collection('users')

    from bson import ObjectId
    try:
        session = sessions_col.find_one({"_id": ObjectId(session_id)})
    except:
        flash("Invalid session ID.", "error")
        return redirect(back)

    if not session:
        flash("Session not found.", "error")
        return redirect(back)

    exam = exams_col.find_one({"_id": session["exam_id"]})
    if not exam:
        flash("Exam not found.", "error")
        return redirect(back)
        
    # Get student info
    student_id = session.get("student_id")
    student = users_col.find_one({"_id": ObjectId(student_id)}) if ObjectId.is_valid(str(student_id)) else None
    student_name = student.get("full_name", "Unknown Student") if student else "Unknown Student"
    student_email = student.get("email", "") if student else ""
    
    from app.models import ExamScore
    score_record = ExamScore.query.filter_by(session_id=session_id).first()
    
    # Map questions to answers for grading
    questions_to_display = session.get('question_snapshot', exam.get('questions', []))
    questions_dict = {str(q.get('_id')): q for q in questions_to_display}
    answers_dict = {ans.get('question_id'): ans for ans in session.get('answers', [])}
    
    # Get manual grades if available
    manual_grades = session.get('manual_grades', {})
    
    review_data = []
    for q_id in session.get('question_order', []):
        question = questions_dict.get(q_id)
        if not question:
            continue
            
        answer = answers_dict.get(q_id, {})
        student_answer = answer.get('selected_option', '')

        correct_answer_text = resolve_correct_text(question)
        question_type = question.get('question_type', question.get('type', 'mcq'))

        # Determine if correct - reuses the exact same resolver that computed
        # the actual score, so this review can never disagree with it.
        is_correct = None
        awarded_marks = None
        feedback = None

        if question_type != 'essay':
            is_correct = is_answer_correct(question, student_answer)
            student_answer = resolve_option_text(question, student_answer) if student_answer else student_answer
        else:
            # Check for manual grading
            if q_id in manual_grades:
                awarded_marks = manual_grades[q_id].get('score', 0)
                feedback = manual_grades[q_id].get('feedback', '')

        review_data.append({
            "question": {
                "_id": q_id,
                "text": question.get('text', ''),
                "type": question_type,
                "options": question.get('options', [])
            },
            "student_response": student_answer,
            "correct_response": correct_answer_text if question_type != 'essay' else 'Manual grading required',
            "is_correct": is_correct,
            "explanation": question.get('explanation', ''),
            "marks": question.get('marks', 1),
            "awarded_marks": awarded_marks,
            "feedback": feedback
        })
        
    return render_template('dashboard/grade_submission.html',
                         session_id=session_id,
                         session=session,
                         exam=exam,
                         student_name=student_name,
                         student_email=student_email,
                         score_record=score_record,
                         review_data=review_data)

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

@dashboard_bp.route('/classes/<class_id>/manage')
@require_auth()
def manage_class(class_id):
    from bson import ObjectId
    classes_col = get_collection('classes')
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return "Class not found", 404
            
        # is_teacher now means "can manage this class" (owner, org, or a
        # collaborator explicitly granted edit access) - not just "is a
        # member of teachers[]" like before. See _can_manage_class()'s
        # docstring in app/classes/routes.py for why plain membership no
        # longer implies management rights.
        from app.classes.routes import _can_manage_class
        is_teacher = _can_manage_class(class_obj, g.current_user)
        # require_owner=True's check already covers org_admin-of-this-org too
        # (see _can_manage_class - that branch isn't gated by require_owner),
        # so this alone is exactly "owner or org", the set allowed to grant
        # teacher edit-access.
        is_owner_or_org = _can_manage_class(class_obj, g.current_user, require_owner=True)

        from app.utils.plans import get_plan_limit
        user_plan = g.current_user.get("plan", {}).get("type", "free")
        can_message = get_plan_limit(user_plan, "can_message_1on1")
        can_see_reactions = get_plan_limit(user_plan, "can_see_broadcast_reactions")

        # Same "Get organization name" lookup class_chat() does below - was
        # missing here, so this page only ever showed the "Remove
        # Organization" button with no name to say which org it was.
        org_name = None
        if class_obj.get("organization_id"):
            orgs_col = get_collection("organizations")
            org = orgs_col.find_one({"_id": class_obj["organization_id"]}) if orgs_col is not None else None
            if org:
                org_name = org.get("name")

        return render_template('dashboard/manage_class.html',
                               class_obj=class_obj,
                               is_teacher=is_teacher,
                               is_owner_or_org=is_owner_or_org,
                               can_message=can_message,
                               can_see_reactions=can_see_reactions,
                               org_name=org_name)
    except Exception as e:
        return str(e), 400

@dashboard_bp.route('/classes/<class_id>/chat')
@require_auth()
def class_chat(class_id):
    from bson import ObjectId
    classes_col = get_collection('classes')
    try:
        class_obj = classes_col.find_one({"_id": ObjectId(class_id)})
        if not class_obj:
            return "Class not found", 404
            
        role = g.current_user.get('role', 'student')
        user_id = str(g.current_user['_id'])
        
        is_teacher = False
        if role in ['teacher', 'org_admin']:
            for t in class_obj.get("teachers", []):
                if str(t.get("user_id")) == user_id:
                    is_teacher = True
                    break
        
        from app.utils.plans import get_plan_limit
        user_plan = g.current_user.get("plan", {}).get("type", "free")
        can_message = get_plan_limit(user_plan, "can_message_1on1")
        can_see_reactions = get_plan_limit(user_plan, "can_see_broadcast_reactions")
        
        # Calculate members count
        total_examiners = sum(1 for t in class_obj.get("teachers", []) if t.get("status") == "active")
        total_students = sum(1 for s in class_obj.get("students", []) if s.get("status") == "active")
        members_count = total_examiners + total_students
        
        # Get organization name if any
        org_name = None
        if class_obj.get("organization_id") and class_obj.get("organization_status") == "active":
            orgs_col = get_collection("organizations")
            org = orgs_col.find_one({"_id": class_obj["organization_id"]})
            if org:
                org_name = org.get("name")
                    
        return render_template('dashboard/class_chat.html', 
                               class_obj=class_obj, 
                               is_teacher=is_teacher,
                               can_message=can_message,
                               can_see_reactions=can_see_reactions,
                               members_count=members_count,
                               org_name=org_name)
    except Exception as e:
        return str(e), 400

@dashboard_bp.route('/join/<token>')
@require_auth()
def join_class(token):
    from bson import ObjectId
    from datetime import datetime
    classes_col = get_collection('classes')
    
    # Find the class and role by matching the token in links
    class_obj = classes_col.find_one({"$or": [
        {"links.student": token},
        {"links.teacher": token},
        {"links.org": token} # if org links are generated
    ]})
    
    if not class_obj:
        from flask import flash, redirect, url_for
        flash("Invalid or expired join link.", "error")
        return redirect(url_for('dashboard.index'))
        
    link_type = None
    if class_obj.get("links", {}).get("student") == token:
        link_type = "student"
    elif class_obj.get("links", {}).get("teacher") == token:
        link_type = "teacher"
    elif class_obj.get("links", {}).get("org") == token:
        link_type = "org"
        
    user_role = g.current_user.get('role', 'student')
    user_id = g.current_user['_id']
    
    from flask import flash, redirect, url_for
    
    if user_role == 'org_admin':
        # org admin joins the class, meaning we set organization_id
        orgs_col = get_collection('organizations')
        org = orgs_col.find_one({"admin_user_id": ObjectId(user_id)}) if orgs_col is not None else None
        if org:
            classes_col.update_one(
                {"_id": class_obj["_id"]},
                {"$set": {"organization_id": ObjectId(org["_id"]) if isinstance(org["_id"], str) else org["_id"], "organization_status": "active"}}
            )
            flash("Class successfully added to your organization.", "success")
        else:
            flash("You do not have an active organization.", "error")
    else:
        # Check if already in class (a removed student's record is kept, not deleted,
        # specifically so this still blocks them from rejoining via the shareable link)
        existing_student_entry = next((s for s in class_obj.get("students", []) if str(s.get("user_id")) == str(user_id)), None)
        is_existing_teacher = any(str(t.get("user_id")) == str(user_id) for t in class_obj.get("teachers", []))

        if existing_student_entry or is_existing_teacher:
            if existing_student_entry and existing_student_entry.get("status") == "removed":
                flash("You were removed from this class. Ask the teacher to send you a direct invitation to rejoin.", "error")
            else:
                flash("You are already a member of this class.", "info")
            return redirect(url_for('dashboard.classes'))
            
        target_role = link_type if link_type in ['student', 'teacher'] else user_role
        if target_role == 'teacher' and user_role == 'student':
            flash("Students cannot join as examiners.", "error")
            return redirect(url_for('dashboard.index'))
            
        if target_role == 'teacher' or user_role in ['teacher', 'org_admin']:
            classes_col.update_one(
                {"_id": class_obj["_id"]}, 
                {"$push": {"teachers": {"user_id": user_id, "role": "collaborator", "status": "active", "added_at": datetime.utcnow()}}}
            )
        else:
            classes_col.update_one(
                {"_id": class_obj["_id"]}, 
                {"$push": {"students": {"user_id": user_id, "status": "active", "joined_at": datetime.utcnow()}}}
            )
        flash("You have successfully joined the class.", "success")
        
    return redirect(url_for('dashboard.classes'))
