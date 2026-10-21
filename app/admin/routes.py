"""iGlobal Educational Services admin pages (role platform_admin, see
app/utils/admin.py). The dashboard home for admins: the e-library exam
catalog, who has access and from where, manual grants/revokes."""
from datetime import datetime

from bson import ObjectId
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from app.auth.decorators import require_auth
from app.utils.mongo import get_collection

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/dashboard/admin')


def _guard():
    if g.current_user.get('role') != 'platform_admin':
        return "Unauthorized", 403
    return None


def catalog_overview():
    """Rows for the catalog table, in catalog order, missing ones included."""
    from app.utils.catalog import JUPEB_SUBJECTS
    exams = get_collection('exams')
    grants = get_collection('exam_access_grants')
    rows = []
    for key, subject, _ in JUPEB_SUBJECTS:
        exam = exams.find_one({'catalog_key': key, 'status': {'$ne': 'deleted'}})
        row = {'key': key, 'subject': subject, 'exam': exam}
        if exam:
            qs = exam.get('questions') or []
            row.update(
                questions=len(qs),
                placeholders=sum(1 for q in qs if q.get('placeholder')),
                buyers=len(grants.distinct('email', {'exam_id': exam['_id'], 'revoked_at': None})),
            )
        rows.append(row)
    return rows


@admin_bp.route('/')
@require_auth()
def home():
    denied = _guard()
    if denied:
        return denied
    from app.utils.admin import get_managed_org
    org = get_managed_org(g.current_user)
    rows = catalog_overview()
    grants = get_collection('exam_access_grants')
    recent = list(grants.find({}).sort('granted_at', -1).limit(30))
    stats = {
        'catalog_ready': sum(1 for r in rows if r['exam']),
        'catalog_total': len(rows),
        'active_grants': grants.count_documents({'revoked_at': None}),
        'buyers': len(grants.distinct('email', {'revoked_at': None})),
        'classes': get_collection('classes').count_documents({'organization_id': org['_id'], 'is_active': {'$ne': False}}) if org else 0,
        'placeholder_exams': sum(1 for r in rows if r.get('placeholders')),
    }
    return render_template('dashboard/admin.html', org=org, rows=rows, recent=recent, stats=stats,
                           webhook_configured=bool(current_app.config.get('IGS_WEBHOOK_SECRET')),
                           webhook_url=url_for('webhooks.igs_exam_access', _external=True))


@admin_bp.route('/catalog/ensure', methods=['POST'])
@require_auth()
def ensure_catalog():
    denied = _guard()
    if denied:
        return denied
    from app.utils.admin import get_managed_org
    from app.utils.catalog import ensure_catalog_exams
    created = ensure_catalog_exams(g.current_user, get_managed_org(g.current_user))
    flash(f"Created {len(created)} catalog exam(s)." if created else "All catalog exams already exist.", 'success')
    return redirect(url_for('admin_bp.home'))


@admin_bp.route('/grants', methods=['POST'])
@require_auth()
def add_grant():
    denied = _guard()
    if denied:
        return denied
    from app.utils import exam_grants
    emails = [e.strip().lower() for e in (request.form.get('emails') or '').replace(';', ',').replace('\n', ',').split(',') if e.strip()]
    keys = request.form.getlist('exam_keys')
    bad = [e for e in emails if '@' not in e or '.' not in e.split('@')[-1]]
    if not emails or not keys or bad:
        flash(f"Enter valid email(s) and pick at least one exam{(' (invalid: ' + ', '.join(bad) + ')') if bad else ''}.", 'error')
        return redirect(url_for('admin_bp.home'))
    exams = list(get_collection('exams').find({'catalog_key': {'$in': keys}, 'status': {'$ne': 'deleted'}}))
    count = 0
    for email in emails:
        for exam in exams:
            exam_grants.grant(email, exam, source='admin', reference=f"manual:{g.current_user['_id']}", granted_by=g.current_user['_id'])
            count += 1
    flash(f"Granted {count} exam access(es) to {len(emails)} email(s).", 'success')
    return redirect(url_for('admin_bp.home'))


@admin_bp.route('/grants/<grant_id>/revoke', methods=['POST'])
@require_auth()
def revoke_grant(grant_id):
    denied = _guard()
    if denied:
        return denied
    from app.utils import exam_grants
    grants = get_collection('exam_access_grants')
    grant = grants.find_one({'_id': ObjectId(grant_id)}) if ObjectId.is_valid(grant_id) else None
    if not grant or grant.get('revoked_at'):
        flash("Grant not found or already revoked.", 'error')
        return redirect(url_for('admin_bp.home'))
    exam = get_collection('exams').find_one({'_id': grant['exam_id']})
    if exam:
        removed = exam_grants.revoke(grant['email'], exam, source=grant['source'], reference=grant.get('reference'))
        flash(f"Revoked {grant['email']} from {exam.get('title')}." if removed
              else f"Revoked that grant, but {grant['email']} still has access through another purchase/grant.", 'success')
    else:
        grants.update_one({'_id': grant['_id']}, {'$set': {'revoked_at': datetime.utcnow()}})
        flash("Revoked (the exam no longer exists).", 'success')
    return redirect(url_for('admin_bp.home'))
