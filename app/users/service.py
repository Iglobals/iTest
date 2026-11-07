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


# ---------------------------------------------------------------- Didit KYC
# liveness_verification doubles as the Didit record so the proctoring gate
# (exam_rules.liveness_completed -> status == 'completed') needs no change:
#   {status: not_started|pending|under_review|completed|rejected|expired,
#    provider: 'didit', didit_session_id, verification_url, reason, ...}

def start_didit_verification(user: dict, callback_url: str) -> dict:
    """Create (or resume) a Didit session for this user. Returns
    {'verification_url', 'status'}; raises ValueError if already verified."""
    from app.utils import didit_client
    users = get_collection('users')
    current = user.get('liveness_verification') or {}
    if current.get('status') == 'completed':
        raise ValueError('Your identity is already verified.')

    # Resume an unfinished session rather than creating duplicates (same as
    # HelpSend's initiateKYC) - Didit sessions stay usable until they expire.
    # Check if we have a valid session ID and try to get its current status.
    if current.get('provider') == 'didit' and current.get('didit_session_id'):
        session_id = current.get('didit_session_id')
        try:
            # Poll Didit to check if the existing session is still valid
            session_info = didit_client.get_session(session_id)
            didit_status = session_info.get('status')
            # Reuse if session is active (not in a terminal state)
            if didit_status not in ('Approved', 'Declined', 'Expired', 'Kyc Expired'):
                if current.get('verification_url'):
                    return {'verification_url': current['verification_url'], 'status': current.get('status', 'pending')}
        except Exception:
            # Session lookup failed - create a new one below
            pass

    # Create new session since none exists or the old one expired
    session = didit_client.create_session(user['_id'], user.get('email'), user.get('full_name'), callback_url)
    users.update_one({'_id': user['_id']}, {'$set': {
        'liveness_verification.provider': 'didit',
        'liveness_verification.status': 'pending',
        'liveness_verification.didit_session_id': session['session_id'],
        'liveness_verification.verification_url': session['verification_url'],
        'liveness_verification.reason': None,
        'liveness_verification.started_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }})
    return {'verification_url': session['verification_url'], 'status': 'pending'}


def apply_didit_result(parsed: dict) -> dict:
    """Apply a parsed Didit result (didit_client.parse_result) to the
    matching user - looked up by session id first, then vendor_data (our
    user id), like HelpSend's handleProviderWebhook. Returns the user (or
    None if no match). A completed verification is never downgraded."""
    users = get_collection('users')
    user = None
    if parsed.get('session_id'):
        user = users.find_one({'liveness_verification.didit_session_id': parsed['session_id']})
    if not user and parsed.get('user_id'):
        user = users.find_one({'_id': build_object_id(parsed['user_id'])})
    if not user:
        return None

    current = user.get('liveness_verification') or {}
    if not parsed.get('update') or current.get('status') == 'completed':
        return user

    now = datetime.utcnow()
    fields = {
        'liveness_verification.provider': 'didit',
        'liveness_verification.status': parsed['status'],
        'liveness_verification.didit_status': parsed.get('didit_status'),
        'liveness_verification.reason': parsed.get('reason'),
        'updated_at': now,
    }
    if parsed.get('session_id'):
        fields['liveness_verification.didit_session_id'] = parsed['session_id']
    if parsed['status'] == 'completed':
        fields['liveness_verification.completed_at'] = now
    if parsed['status'] in ('rejected', 'expired'):
        # Let them start over with a fresh session next time.
        fields['liveness_verification.verification_url'] = None
    users.update_one({'_id': user['_id']}, {'$set': fields})
    return users.find_one({'_id': user['_id']})


def refresh_didit_status(user: dict) -> dict:
    """Ask Didit directly - backstop for a late/missed webhook, used by the
    return page and the status endpoint. Never raises; returns the user."""
    from app.utils import didit_client
    lv = user.get('liveness_verification') or {}
    if lv.get('provider') != 'didit' or lv.get('status') not in ('pending', 'under_review') or not lv.get('didit_session_id'):
        return user
    try:
        data = didit_client.get_session(lv['didit_session_id'])
    except didit_client.DiditError as e:
        print(f"[DIDIT] status refresh failed: {e}")
        return user
    data.setdefault('session_id', lv['didit_session_id'])
    data.setdefault('vendor_data', str(user['_id']))
    return apply_didit_result(didit_client.parse_result(data)) or user
