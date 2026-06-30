import os
import uuid
from flask import Blueprint, request, redirect, url_for, session, current_app
from iglobals_auth import IGlobalsAuth
from app.utils.mongo import get_collection
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

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
    from flask import session
    session.permanent = True  # Make session persistent
    
    client = get_ica_client()
    # 1. Generate PKCE
    pkce = client.generate_pkce()
    state = str(uuid.uuid4())
    
    # 2. Store verifier and state in session
    session['oauth_state'] = state
    session['code_verifier'] = pkce['code_verifier']
    
    print(f"[AUTH DEBUG] Login - Setting state: {state}")
    print(f"[AUTH DEBUG] Login - Setting code_verifier: {pkce['code_verifier'][:20]}...")
    
    # 3. Redirect to get_authorization_url
    url = client.get_authorization_url(state, pkce['code_challenge'])
    return redirect(url)

@auth_bp.route('/callback')
def callback():
    client = get_ica_client()
    
    # 1. Validate state matches session['oauth_state']
    state = request.args.get('state')
    stored_state = session.get('oauth_state')
    
    print(f"[AUTH DEBUG] Received state: {state}")
    print(f"[AUTH DEBUG] Stored state: {stored_state}")
    
    if state != stored_state:
        print(f"[AUTH ERROR] State mismatch!")
        return f"Invalid state parameter. Received: {state}, Expected: {stored_state}", 400
        
    code = request.args.get('code')
    code_verifier = session.get('code_verifier')
    
    print(f"[AUTH DEBUG] Code: {code[:20] if code else None}...")
    print(f"[AUTH DEBUG] Code verifier: {code_verifier[:20] if code_verifier else None}...")
    
    if not code:
        return "Missing authorization code", 400
    
    if not code_verifier:
        return "Missing code verifier. Please try logging in again.", 400
        
    try:
        # 2. exchange_code
        print(f"[AUTH DEBUG] Exchanging code...")
        tokens = client.exchange_code(code, code_verifier)
        print(f"[AUTH DEBUG] Tokens received successfully")
        
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
        
        # 5. Store token in session
        session['access_token'] = access_token
        session['refresh_token'] = tokens.refresh_token
        
        # Store basic user info for UI rendering
        session['user_info'] = {
            'name': user.get('full_name', 'Unknown User'),
            'avatar_url': user.get('avatar_url', '')
        }
        
        # Clear OAuth state/verifier after successful auth
        session.pop('oauth_state', None)
        session.pop('code_verifier', None)
        
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
