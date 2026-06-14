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
    client = get_ica_client()
    # 1. Generate PKCE
    pkce = client.generate_pkce()
    state = str(uuid.uuid4())
    
    # 2. Store verifier and state in session
    session['oauth_state'] = state
    session['code_verifier'] = pkce['code_verifier']
    
    # 3. Redirect to get_authorization_url
    url = client.get_authorization_url(state, pkce['code_challenge'])
    return redirect(url)

@auth_bp.route('/callback')
def callback():
    client = get_ica_client()
    
    # 1. Validate state matches session['oauth_state']
    state = request.args.get('state')
    if state != session.get('oauth_state'):
        return "Invalid state parameter", 400
        
    code = request.args.get('code')
    code_verifier = session.get('code_verifier')
    if not code or not code_verifier:
        return "Missing code or code verifier", 400
        
    try:
        # 2. exchange_code
        tokens = client.exchange_code(code, code_verifier)
        
        # 3. get_user_info
        # Wait, from INTEGRATION_GUIDE it says tokens.access_token not tokens['access_token'] if it's an object?
        # Let's check INTEGRATION_GUIDE.md: "tokens.access_token"
        access_token = tokens.access_token
        
        user_info = client.get_user_info(access_token)
        
        # 4. get_or_create_user
        users_col = get_collection('users')
        if users_col is not None:
            # user_info is a dict
            sub = user_info.get('sub')
            user = users_col.find_one({"ica_sub": sub})
            if not user:
                user = {
                    "ica_sub": sub,
                    "email": user_info.get('email'),
                    "full_name": f"{user_info.get('given_name', '')} {user_info.get('family_name', '')}".strip() or "Unknown User",
                    "role": "student", # Default
                    "avatar_url": user_info.get('picture', ''),
                    "created_at": datetime.utcnow(),
                    "last_login_at": datetime.utcnow(),
                    "is_active": True
                }
                users_col.insert_one(user)
            else:
                users_col.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"last_login_at": datetime.utcnow()}}
                )
        
        # 5. Store token in session
        session['access_token'] = access_token
        session['refresh_token'] = tokens.refresh_token
        
        # 6. Redirect to dashboard
        return redirect(url_for('dashboard.index'))
    except Exception as e:
        return f"Authentication failed: {str(e)}", 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('landing.index'))
