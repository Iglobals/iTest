"""Email-based exam access grants (e-library purchases, admin manual adds).

Access itself is still `exam.visibility.student_ids` (emails, lowercased) -
that's what can_student_access_exam and the student dashboards read. Each
grant is ALSO recorded in `exam_access_grants` so the admin can see who got
access, from where, and so a revoke only removes access when no other
active grant (another purchase, a manual add) still covers it.
"""
from datetime import datetime

from app.utils.admin import email_variants
from app.utils.mongo import get_collection


def _norm(email):
    return (email or '').strip().lower()


def grant(email, exam, source, reference=None, event_id=None, granted_by=None):
    email = _norm(email)
    grants = get_collection('exam_access_grants')
    now = datetime.utcnow()
    existing = grants.find_one({'email': email, 'exam_id': exam['_id'], 'source': source,
                                'reference': reference, 'revoked_at': None})
    if not existing:
        grants.insert_one({
            'email': email, 'exam_id': exam['_id'], 'catalog_key': exam.get('catalog_key'),
            'exam_title': exam.get('title'), 'source': source, 'reference': reference,
            'event_id': event_id, 'granted_by': granted_by, 'granted_at': now, 'revoked_at': None,
        })
    get_collection('exams').update_one({'_id': exam['_id']}, {'$addToSet': {'visibility.student_ids': email}})

    # Notify only a real account (case-insensitive) - no placeholder users:
    # the buyer may not have an iTest account yet; the grant is keyed by
    # email, so it applies automatically once they sign up with it.
    user = get_collection('users').find_one({'email': {'$in': email_variants(email)}, 'ica_sub': {'$exists': True}})
    if user and not existing:
        get_collection('notifications').insert_one({
            'recipient_id': user['_id'], 'sender_id': 'system', 'type': 'exam_access',
            'title': 'New Exam Access',
            'body': f"You now have access to {exam.get('title')}. Find it under My Exams.",
            'metadata': {'exam_id': str(exam['_id'])}, 'is_read': False, 'created_at': now,
        })
    return not existing


def revoke(email, exam, source, reference=None):
    """Revoke one grant; only pulls the email off the exam if no other
    active grant still covers it. Returns True if access was removed."""
    email = _norm(email)
    grants = get_collection('exam_access_grants')
    query = {'email': email, 'exam_id': exam['_id'], 'revoked_at': None, 'source': source}
    if reference is not None:
        query['reference'] = reference
    grants.update_many(query, {'$set': {'revoked_at': datetime.utcnow()}})
    if grants.find_one({'email': email, 'exam_id': exam['_id'], 'revoked_at': None}):
        return False
    get_collection('exams').update_one({'_id': exam['_id']},
                                       {'$pull': {'visibility.student_ids': {'$in': email_variants(email)}}})
    return True
