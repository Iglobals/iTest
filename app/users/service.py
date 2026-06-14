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
        'plan': {'type': 'free', 'expires_at': None, 'stripe_customer_id': None},
        'limits': {'max_classes': 2, 'max_students_per_class': 30, 'max_total_students': 60, 'ai_proctoring': False, 'analytics_advanced': False},
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
    users = get_collection('users')
    _id = build_object_id(user_id)
    update_fields = {k: v for k, v in data.items() if k in ['full_name', 'institution', 'programme', 'phone', 'date_of_birth']}
    update_fields['updated_at'] = datetime.utcnow()
    users.update_one({'_id': _id}, {'$set': update_fields})
    return users.find_one({'_id': _id})


def upload_avatar(user_id: str, avatar_url: str) -> dict:
    users = get_collection('users')
    _id = build_object_id(user_id)
    users.update_one({'_id': _id}, {'$set': {'avatar_url': avatar_url, 'updated_at': datetime.utcnow()}})
    return users.find_one({'_id': _id})
