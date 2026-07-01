import os
import uuid
from flask import Blueprint, request, redirect, url_for, session, current_app, make_response
from iglobals_auth import IGlobalsAuth
from app.utils.mongo import get_collection
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)

# Temporary in-memory store for OAuth state (works around cookie/session issues in dev)
# In production, use Redis or database
_oauth_states = {}

def get_ica_client():
    return IGlobalsAuth(
        base_url=current_app.config['ICA_BASE_URL'],
        client_id=current_app.config['ICA_CLIENT_ID'],
        client_secret=current_app.config['ICA_CLIENT_SECRET'],
        redirect_uri=current_app.config['ICA_REDIRECT_URI'],
        scopes=['openid', 'profile', 'email']
    )

@auth_bp.route('/login')
def login():
    from flask import session, make_response
    session.permanent = True  # Make session persistent
    
    client = get_ica_client()
    # 1. Generate PKCE
    pkce = client.generate_pkce()
    state = str(uuid.uuid4())
    
    # 2. Store in memory (fallback for when sessions don't work)
    _oauth_states[state] = {
        'code_verifier': pkce['code_verifier'],
        'created_at': datetime.utcnow()
    }
    
    # Clean up old states (older than 10 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    _oauth_states.clear()  # Simple: clear all on each login for development
    _oauth_states[state] = {
        'code_verifier': pkce['code_verifier'],
        'created_at': datetime.utcnow()
    }
    
    print(f"[AUTH DEBUG] Login - Setting state: {state}")
    print(f"[AUTH DEBUG] Login - Setting code_verifier: {pkce['code_verifier'][:20]}...")
    print(f"[AUTH DEBUG] Login - Stored in memory: {state in _oauth_states}")
    
    # 3. Redirect to get_authorization_url
    url = client.get_authorization_url(state, pkce['code_challenge'])
    return redirect(url)

@auth_bp.route('/callback')
def callback():
    client = get_ica_client()
    
    # Get state from query params
    state = request.args.get('state')
    
    print(f"[AUTH DEBUG] Callback - Received state: {state}")
    print(f"[AUTH DEBUG] Callback - State in memory: {state in _oauth_states}")
    
    # 1. Validate state exists in our memory store
    if state not in _oauth_states:
        print(f"[AUTH ERROR] State not found in memory store!")
        return "Invalid or expired state. Please try logging in again.", 400
    
    # 2. Get code_verifier from memory
    code_verifier = _oauth_states[state]['code_verifier']
    code = request.args.get('code')
    
    print(f"[AUTH DEBUG] Code: {code[:20] if code else None}...")
    print(f"[AUTH DEBUG] Code verifier retrieved: {code_verifier[:20] if code_verifier else None}...")
    
    if not code:
        return "Missing authorization code", 400
        
    try:
        # 2. exchange_code
        print(f"[AUTH DEBUG] Exchanging code...")
        tokens = client.exchange_code(code, code_verifier)
        print(f"[AUTH DEBUG] Tokens received successfully")
        
        # Clean up used state
        del _oauth_states[state]
        
        # 3. get_user_info
        access_token = tokens.access_token
        print(f"[AUTH DEBUG] Getting user info...")
        user_info = client.get_user_info(access_token)
        print(f"[AUTH DEBUG] User info: {user_info.get('email')}")
        
        # 4. get_or_create_user
        users_col = get_collection('users')
        if users_col is None:
            return "Database connection error", 500
            
        sub = user_info.get('sub')
        user = users_col.find_one({"ica_sub": sub})
        
        if not user:
            print(f"[AUTH DEBUG] Creating new user for {user_info.get('email')}")
            user = {
                "ica_sub": sub,
                "email": user_info.get('email'),
                "full_name": f"{user_info.get('given_name', '')} {user_info.get('family_name', '')}".strip() or "Unknown User",
                "role": None, # Will be set during onboarding
                "avatar_url": user_info.get('picture', ''),
                "onboarded": False,
                "created_at": datetime.utcnow(),
                "last_login_at": datetime.utcnow(),
                "is_active": True
            }
            result = users_col.insert_one(user)
            user['_id'] = result.inserted_id
            print(f"[AUTH DEBUG] User created with ID: {user['_id']}")
        else:
            print(f"[AUTH DEBUG] Existing user found: {user.get('email')}")
            users_col.update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login_at": datetime.utcnow()}}
            )
        
        # 5. Store token in session (still needed for auth decorator)
        session['access_token'] = access_token
        session['refresh_token'] = tokens.refresh_token
        
        # Store basic user info for UI rendering
        session['user_info'] = {
            'name': user.get('full_name', 'Unknown User'),
            'avatar_url': user.get('avatar_url', '')
        }
        
        print(f"[AUTH DEBUG] Authentication successful! Redirecting to dashboard...")
        
        # 6. Redirect to dashboard
        return redirect(url_for('dashboard.index'))
        
    except Exception as e:
        import traceback
        print(f"[AUTH ERROR] Authentication failed:")
        print(traceback.format_exc())
        return f"Authentication failed: {str(e)}", 500

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect(url_for('landing.index'))
