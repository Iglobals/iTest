"""iTest's built-in admin: the iGlobal Educational Services organization.

Admins are whoever's email is listed in ITEST_ADMIN_EMAILS (comma
separated). They get role 'platform_admin', run the built-in org (classes,
folders, performance - like an org_admin) AND create/run exams (like an
examiner), with every plan limit lifted - see effective_plan_type().
"""
import os
from datetime import datetime

from app.utils.mongo import get_collection

DEFAULT_ADMIN_EMAILS = 'eoluwaseyi205@gmail.com'
BUILTIN_ORG_SLUG = 'iglobals-educational-services'
BUILTIN_ORG_NAME = 'iGlobal Educational Services'
UNLIMITED = 10 ** 9


def admin_emails():
    raw = os.environ.get('ITEST_ADMIN_EMAILS', DEFAULT_ADMIN_EMAILS)
    return {e.strip().lower() for e in raw.split(',') if e.strip()}


def is_platform_admin(user):
    return bool(user) and user.get('role') == 'platform_admin'


def effective_plan_type(user):
    """Plan to check limits against. Admins are never limited, whatever
    their personal billing plan says."""
    if is_platform_admin(user):
        return 'enterprise'
    return ((user or {}).get('plan') or {}).get('type', 'free')


def email_variants(email):
    """Exam grants store emails lowercased; older ones were stored as typed.
    Match either, so 'Ada@Mail.com' and 'ada@mail.com' are the same buyer."""
    email = (email or '').strip()
    return list(dict.fromkeys([email, email.lower()])) if email else []


def ensure_builtin_org(admin_user=None):
    """Create/refresh the built-in org (idempotent). Matched by slug so the
    org seed_iglobals.py made earlier (named 'iGlobals ...') is reused."""
    orgs = get_collection('organizations')
    now = datetime.utcnow()
    org = orgs.find_one({'slug': BUILTIN_ORG_SLUG}) or orgs.find_one({'is_builtin': True})
    fields = {
        'name': BUILTIN_ORG_NAME,
        'slug': BUILTIN_ORG_SLUG,
        'is_builtin': True,
        'limits': {'max_classes': UNLIMITED, 'max_teachers': UNLIMITED,
                   'ai_proctoring': True, 'advanced_analytics': True},
        'plan': {'type': 'enterprise', 'expires_at': None},
        'updated_at': now,
    }
    if org:
        if admin_user and not org.get('admin_user_id'):
            fields['admin_user_id'] = admin_user['_id']
        orgs.update_one({'_id': org['_id']}, {'$set': fields})
        return orgs.find_one({'_id': org['_id']})
    fields.update({
        'admin_user_id': admin_user['_id'] if admin_user else None,
        'description': 'Official iGlobals built-in organization - national exam practice (JUPEB, ...).',
        'contact_email': (admin_user or {}).get('email', ''),
        'logo_url': '', 'website': '', 'pending_teacher_requests': [],
        'created_at': now,
    })
    fields['_id'] = orgs.insert_one(fields).inserted_id
    return fields


def promote_if_admin(user):
    """Called on every login: make listed emails admins of the built-in org
    (and skip onboarding/plan selection for them). Returns the user."""
    if not user or (user.get('email') or '').strip().lower() not in admin_emails():
        return user
    org = ensure_builtin_org(user)
    updates = {'role': 'platform_admin', 'onboarded': True, 'plan_selected': True,
               'organization_id': org['_id']}
    if any(user.get(k) != v for k, v in updates.items()):
        get_collection('users').update_one({'_id': user['_id']}, {'$set': updates})
        user.update(updates)
    return user


def get_managed_org(user):
    """The org a user runs: org_admin -> the org they admin; platform_admin
    -> the built-in org."""
    if not user:
        return None
    if is_platform_admin(user):
        return ensure_builtin_org(user)
    if user.get('role') == 'org_admin':
        return get_collection('organizations').find_one({'admin_user_id': user['_id']})
    return None
