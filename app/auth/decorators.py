from functools import wraps
from flask import session, redirect, url_for, jsonify, g, request
from app.auth.routes import get_ica_client
from app.utils.mongo import get_collection

def get_user_by_ica_sub(sub):
    users = get_collection('users')
    if users is None:
        return None
    return users.find_one({"ica_sub": sub})


def _downgrade_if_expired(user):
    """If a paid plan's expires_at has passed, revert to free in the DB and
    in the in-memory `user` dict (so the rest of this request sees it too).
    Catches the case where Paystack's cancel/renewal-failure webhook never
    arrived or was missed - access still ends on schedule either way."""
    from datetime import datetime

    plan = user.get("plan") or {}
    expires_at = plan.get("expires_at")
    if plan.get("type") in (None, "free") or not expires_at:
        return
    if expires_at > datetime.utcnow():
        return

    users = get_collection('users')
    users.update_one({"_id": user["_id"]}, {"$set": {
        "plan.type": "free",
        "plan.interval": None,
        "plan.subscription_status": "expired",
    }})
    plan["type"] = "free"
    plan["interval"] = None
    plan["subscription_status"] = "expired"
    user["plan"] = plan

_refresh_memory = {}  # fallback when Redis isn't configured (single-process dev)


def _refresh_session_tokens():
    """Swap the session's refresh_token for a new access/refresh pair.

    ICA rotates refresh tokens and treats re-use of an old one as theft
    (revokes every token for the user). A page often fires several API calls
    at once, all carrying the same expired cookie, so only one of them may
    actually hit ICA: it takes a short Redis lock, and the result is cached
    under the OLD token's hash for 2 minutes so the concurrent requests pick
    up the same new pair instead of replaying the old token.
    Returns the new access token, or None if refresh isn't possible."""
    import hashlib
    import json
    import time
    from app.auth.routes import get_redis

    old_refresh = session.get("refresh_token")
    if not old_refresh:
        return None

    key = "itest_refresh:" + hashlib.sha256(old_refresh.encode()).hexdigest()
    redis_client = get_redis()

    def cached():
        if redis_client:
            raw = redis_client.get(key)
            return json.loads(raw) if raw else None
        entry = _refresh_memory.get(key)
        return entry["tokens"] if entry and entry["exp"] > time.time() else None

    def apply(tokens):
        session["access_token"] = tokens["access_token"]
        session["refresh_token"] = tokens["refresh_token"]
        session.modified = True
        return tokens["access_token"]

    hit = cached()
    if hit:
        return apply(hit)

    got_lock = True
    if redis_client:
        got_lock = bool(redis_client.set(key + ":lock", "1", nx=True, ex=10))
        if not got_lock:
            # Another request is refreshing this exact token - wait for it.
            for _ in range(40):
                time.sleep(0.25)
                hit = cached()
                if hit:
                    return apply(hit)
            return None

    try:
        new = get_ica_client().refresh_access_token(old_refresh)
    except Exception as e:
        print(f"[AUTH] Token refresh failed: {e}")
        return None

    tokens = {"access_token": new.access_token, "refresh_token": new.refresh_token}
    if redis_client:
        redis_client.setex(key, 120, json.dumps(tokens))
        redis_client.delete(key + ":lock")
    else:
        _refresh_memory[key] = {"tokens": tokens, "exp": time.time() + 120}
        for k in [k for k, v in _refresh_memory.items() if v["exp"] < time.time()]:
            _refresh_memory.pop(k, None)
    return apply(tokens)


def _token_expired(token, leeway=30):
    """True if the JWT's exp has passed (or will within `leeway` seconds)."""
    import time
    import jwt
    try:
        exp = jwt.decode(token, options={"verify_signature": False}).get("exp")
    except Exception:
        return True
    return bool(exp) and exp - leeway < time.time()


def _verify_with_refresh(token):
    """Verify the access token, refreshing it once first if it has expired
    (or if verification fails for any other reason), so an expired access
    token never surfaces as a login redirect / failed API call while the
    refresh token is still valid."""
    client = get_ica_client()
    if _token_expired(token):
        token = _refresh_session_tokens() or token
    try:
        return client.verify_token(token)
    except Exception:
        new_token = _refresh_session_tokens()
        if not new_token or new_token == token:
            raise
        return client.verify_token(new_token)


def _is_api_request():
    return (request.path.startswith("/api/")
            or request.is_json
            or "application/json" in (request.headers.get("Accept") or "")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest")


def require_auth(redirect_on_fail=True):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # fetch() calls must get a JSON 401 (the page then sends the user
            # to login) rather than a redirect to the login HTML, which made
            # res.json() blow up as an "unexpected error".
            redirect_on_fail = redirect_on_fail and not _is_api_request()
            token = session.get("access_token")
            if not token:
                if redirect_on_fail:
                    return redirect(url_for("auth.login"))
                return jsonify({"error": "Unauthorized", "login_required": True}), 401
            try:
                ica_payload = _verify_with_refresh(token)
                user = get_user_by_ica_sub(ica_payload.get("sub"))
                if not user:
                    if redirect_on_fail:
                        return redirect(url_for("auth.login"))
                    return jsonify({"error": "User not found"}), 401
                g.current_user = user
                g.ica_payload = ica_payload
                
                # Enforce onboarding
                if not user.get("onboarded", False):
                    endpoint = request.endpoint or ""
                    if not endpoint.startswith("onboarding.") and not endpoint.startswith("auth.logout") and not endpoint.startswith("static"):
                        if redirect_on_fail:
                            return redirect(url_for("onboarding.index"))
                        return jsonify({"error": "Onboarding required"}), 403
                else:
                    # A subscription that lapsed (cancelled and its paid
                    # period ended, or a renewal charge failed) should not
                    # silently keep granting paid-tier access forever just
                    # because no webhook happened to fire - check on read
                    # instead of relying solely on Paystack's callbacks.
                    _downgrade_if_expired(user)

                    # Enforce plan selection (teachers only - see
                    # onboarding/routes.py, students and org admins have
                    # plan_selected=True from onboarding).
                    if not user.get("plan_selected", True):
                        endpoint = request.endpoint or ""
                        if not endpoint.startswith("billing.") and not endpoint.startswith("auth.logout") and not endpoint.startswith("static"):
                            if redirect_on_fail:
                                return redirect(url_for("billing.select_plan"))
                            return jsonify({"error": "Plan selection required"}), 403

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Exception in verify_token: {e}")
                session.clear()
                if redirect_on_fail:
                    return redirect(url_for("auth.login"))
                return jsonify({"error": "Your session has expired. Please log in again.", "login_required": True}), 401
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @require_auth()
        def decorated(*args, **kwargs):
            if g.current_user.get("role") not in roles:
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_plan(*plans):
    def decorator(f):
        @wraps(f)
        @require_auth()
        def decorated(*args, **kwargs):
            user_plan = g.current_user.get("plan", {}).get("type", "free")
            if user_plan not in plans:
                return jsonify({"error": "Upgrade required", "upgrade_url": "/pricing"}), 402
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_feature(feature_key):
    def decorator(f):
        @wraps(f)
        @require_auth()
        def decorated(*args, **kwargs):
            from app.utils.plans import get_plan_limit
            user_plan = g.current_user.get("plan", {}).get("type", "free")
            has_feature = get_plan_limit(user_plan, feature_key)
            if not has_feature:
                return jsonify({"error": f"This feature requires a premium plan", "limit_reached": True, "upgrade_url": "/pricing"}), 402
            return f(*args, **kwargs)
        return decorated
    return decorator
