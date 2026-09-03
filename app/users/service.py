from datetime import datetime
from app.utils.mongo import get_collection, build_object_id


def get_or_create_user(ica_payload: dict) -> dict:
    users = get_collection('users')
    ica_sub = ica_payload.get('sub') or ica_payload.get('user_id')
    if not ica_sub:
        raise ValueError('Missing ICA subject')

    existing = users.find_one({'ica_sub': ica_sub})
    now = datetime.utcnow()
    if existing:
        users.update_one({'_id': existing['_id']}, {'$set': {
            'email': ica_payload.get('email'),
            'full_name': ica_payload.get('name') or ica_payload.get('preferred_username'),
            'updated_at': now,
            'last_login_at': now,
        }})
        existing.update({'email': ica_payload.get('email'), 'full_name': ica_payload.get('name') or ica_payload.get('preferred_username'), 'updated_at': now, 'last_login_at': now})
        return existing

    user = {
        'ica_sub': ica_sub,
        'email': ica_payload.get('email'),
        'full_name': ica_payload.get('name') or ica_payload.get('preferred_username'),
        'role': 'student',
        'avatar_url': None,
        'institution': None,
        'programme': None,
        'phone': None,
        'date_of_birth': None,
        'subject_tags_interest': [],
        'notification_preferences': {'email': True, 'in_app': True},
        'plan': {
            'type': 'free',
            'interval': None,
            'expires_at': None,
            'subscription_status': None,
            'paystack_customer_code': None,
            'paystack_subscription_code': None,
            # Required (alongside the subscription code) by Paystack's
            # Disable Subscription API - only available from the
            # subscription.create webhook, not from the charge itself.
            'paystack_email_token': None,
        },
        # Teachers/org admins must explicitly pick a plan (even Free) before
        # reaching the dashboard - see require_auth() in auth/decorators.py.
        # Role is always 'student' at this point (onboarding sets the real
        # role later), so this can't be conditioned on role yet - onboarding
        # itself flips this to True immediately for students, since they
        # never see the plan-selection screen.
        'plan_selected': False,
        'limits': {'max_classes': 2, 'max_students_per_class': 30, 'max_total_students': 60, 'ai_proctoring': False, 'analytics_advanced': False},
        # One-time identity check (front/left/right/mouth-open photos) -
        # enforced before starting any AI-proctored exam, see
        # app/sessions/routes.py. 'status' moves not_started -> completed
        # only; save_liveness_photos() below refuses to overwrite a
        # completed one, matching the "one-time step" requirement.
        'liveness_verification': {
            'status': 'not_started',
            'photos': {'front': None, 'left': None, 'right': None, 'mouth_open': None},
            'completed_at': None,
        },
        'created_at': now,
        'updated_at': now,
        'last_login_at': now,
        'is_active': True,
        'is_email_verified': True,
    }
    result = get_collection('users').insert_one(user)
    user['_id'] = result.inserted_id
    return user


def update_profile(user_id: str, data: dict) -> dict:
    # full_name is deliberately NOT editable here - get_or_create_user()
    # overwrites it from the ICA identity payload on every login, so a local
    # edit would silently vanish on the user's next sign-in. Name changes
    # belong on ICA's own settings page, which is exactly why iTest's
    # settings page links out there for identity fields and only exposes
    # iTest-specific ones here.
    users = get_collection('users')
    _id = build_object_id(user_id)
    update_fields = {k: v for k, v in data.items() if k in ['institution', 'programme', 'phone', 'date_of_birth']}
    update_fields['updated_at'] = datetime.utcnow()
    users.update_one({'_id': _id}, {'$set': update_fields})
    return users.find_one({'_id': _id})


def upload_avatar(user_id: str, avatar_url: str) -> dict:
    users = get_collection('users')
    _id = build_object_id(user_id)
    users.update_one({'_id': _id}, {'$set': {'avatar_url': avatar_url, 'updated_at': datetime.utcnow()}})
    return users.find_one({'_id': _id})


def save_liveness_photos(user_id: str, photos: dict) -> dict:
    """One-time only - refuses if already completed, per the requirement
    that this step (unlike the rest of the profile) can't be redone."""
    users = get_collection('users')
    _id = build_object_id(user_id)
    user = users.find_one({'_id': _id})
    if user and user.get('liveness_verification', {}).get('status') == 'completed':
        raise ValueError('Liveness verification was already completed and cannot be redone.')

    users.update_one({'_id': _id}, {'$set': {
        'liveness_verification': {
            'status': 'completed',
            'photos': photos,
            'completed_at': datetime.utcnow(),
        },
        'updated_at': datetime.utcnow(),
    }})
    return users.find_one({'_id': _id})
