from functools import wraps
from flask import session, redirect, url_for, jsonify, g, request
from app.auth.routes import get_ica_client
from app.utils.mongo import get_collection

def get_user_by_ica_sub(sub):
    users = get_collection('users')
    if users is None:
        return None
    return users.find_one({"ica_sub": sub})

def require_auth(redirect_on_fail=True):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = session.get("access_token")
            if not token:
                if redirect_on_fail:
                    return redirect(url_for("auth.login"))
                return jsonify({"error": "Unauthorized"}), 401
            try:
                import jwt
                unverified_payload = jwt.decode(token, options={"verify_signature": False})
                print(f"Token issuer is: {unverified_payload.get('iss')}")
                client = get_ica_client()
                ica_payload = client.verify_token(token)
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

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Exception in verify_token: {e}")
                session.clear()
                if redirect_on_fail:
                    return redirect(url_for("auth.login"))
                return jsonify({"error": "Token invalid"}), 401
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
