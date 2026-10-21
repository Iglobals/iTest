"""Didit identity verification (KYC) - ported from HelpSend's
src/modules/kyc/providers/didit.js so both products talk to Didit the same way.

Flow: create a session (vendor_data = our user id) -> send the student to
https://verify.didit.me/session/<session_token> -> Didit calls our webhook
(and we can also poll the session) -> "Approved" marks the user's
liveness_verification as completed, which is what proctored exams check
(see app/utils/exam_rules.py liveness_completed).

Config (env): DIDIT_API_KEY, DIDIT_WORKFLOW_ID, DIDIT_WEBHOOK_SECRET,
optional DIDIT_API_URL. When the key/workflow aren't set, is_configured()
is False and the app keeps using the manual photo verification.
"""
import hashlib
import hmac
import json
import os
import time

import requests

DEFAULT_API_URL = 'https://verification.didit.me/v2'
VERIFY_BASE_URL = 'https://verify.didit.me/session/'


class DiditError(Exception):
    pass


def _cfg():
    return {
        'api_key': os.environ.get('DIDIT_API_KEY', ''),
        'workflow_id': os.environ.get('DIDIT_WORKFLOW_ID', ''),
        'webhook_secret': os.environ.get('DIDIT_WEBHOOK_SECRET', ''),
        'api_url': (os.environ.get('DIDIT_API_URL') or DEFAULT_API_URL).rstrip('/'),
    }


def is_configured():
    c = _cfg()
    return bool(c['api_key'] and c['workflow_id'])


def verification_url(session_token):
    # Always the direct session URL - the workflow URL would start a brand
    # new session whose id our webhook can't match (same note as HelpSend).
    return VERIFY_BASE_URL + session_token


def create_session(user_id, email, full_name, callback_url):
    c = _cfg()
    if not is_configured():
        raise DiditError('Didit is not configured (DIDIT_API_KEY / DIDIT_WORKFLOW_ID).')
    first, _, last = (full_name or '').strip().partition(' ')
    payload = {
        'workflow_id': c['workflow_id'],
        'vendor_data': str(user_id),
        'callback': callback_url,
        'contact': {'email': email, 'first_name': first or 'User', 'last_name': last or 'User'},
    }
    try:
        res = requests.post(f"{c['api_url']}/session/", json=payload,
                            headers={'x-api-key': c['api_key'], 'Content-Type': 'application/json'},
                            timeout=30)
    except requests.RequestException as e:
        raise DiditError(f'Could not reach Didit: {e}')
    if not res.ok:
        raise DiditError(f'Didit session creation failed ({res.status_code}): {res.text[:300]}')
    data = res.json()
    return {
        'session_id': data.get('session_id'),
        'session_token': data.get('session_token'),
        'verification_url': verification_url(data.get('session_token')),
        'status': data.get('status') or 'Not Started',
    }


def get_session(session_id):
    c = _cfg()
    try:
        res = requests.get(f"{c['api_url']}/session/{session_id}/",
                           headers={'x-api-key': c['api_key']}, timeout=20)
    except requests.RequestException as e:
        raise DiditError(f'Could not reach Didit: {e}')
    if not res.ok:
        raise DiditError(f'Didit session lookup failed ({res.status_code})')
    return res.json()


def _feature_warnings(decision):
    if not decision:
        return None
    keys = ['id_verifications', 'liveness_checks', 'face_matches', 'aml_screenings', 'poa_verifications',
            'phone_verifications', 'email_verifications', 'nfc_verifications', 'ip_analyses', 'database_validations']
    warnings = []
    for key in keys:
        for item in decision.get(key) or []:
            for w in (item or {}).get('warnings') or []:
                if w.get('short_description'):
                    warnings.append(w['short_description'])
    return '; '.join(warnings) or None


def parse_result(payload):
    """Map Didit's status to ours. Same mapping as HelpSend's
    parseWebhookResult(); `update` is False for transient statuses so they
    never overwrite a real result."""
    status = payload.get('status')
    decision = payload.get('decision')
    reason = None
    update = True
    if status == 'Approved':
        ours = 'completed'
    elif status == 'Declined':
        ours = 'rejected'
        reviews = (decision or {}).get('reviews') or []
        reason = (reviews[0].get('comment') if reviews else None) or _feature_warnings(decision) or 'Verification declined'
    elif status == 'In Review':
        ours = 'under_review'
        reason = _feature_warnings(decision)
    elif status == 'Resubmitted':
        ours = 'pending'
    elif status in ('Expired', 'Kyc Expired'):
        ours = 'expired'
    else:  # Not Started / In Progress / Abandoned / unknown
        ours = 'pending'
        update = False
    return {
        'session_id': payload.get('session_id'),
        'user_id': payload.get('vendor_data'),
        'status': ours,
        'didit_status': status,
        'reason': reason,
        'update': update,
    }


def verify_webhook(raw_body, headers, max_age_seconds=300):
    """HMAC-SHA256 of the raw request body with DIDIT_WEBHOOK_SECRET, sent by
    Didit in X-Signature (hex), plus an X-Timestamp freshness check. Also
    accepts X-Signature-V2 (HMAC over the canonical, key-sorted JSON) since
    proxies can re-serialize bodies. Returns False whenever the secret is
    missing, so an unconfigured server never trusts webhooks."""
    secret = _cfg()['webhook_secret']
    if not secret:
        return False

    ts = headers.get('X-Timestamp')
    if ts:
        try:
            if abs(time.time() - int(ts)) > max_age_seconds:
                return False
        except ValueError:
            return False

    def _ok(sig, message):
        if not sig:
            return False
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig.strip())

    if _ok(headers.get('X-Signature'), raw_body):
        return True
    try:
        canonical = json.dumps(json.loads(raw_body or b'{}'), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    except ValueError:
        return False
    return _ok(headers.get('X-Signature-V2'), canonical)
