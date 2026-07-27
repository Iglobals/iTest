import os
import uuid
from flask import Blueprint, request, redirect, url_for, session, current_app, make_response
from iglobals_auth import IGlobalsAuth
from app.utils.mongo import get_collection
from datetime import datetime, timedelta
import json

auth_bp = Blueprint('auth', __name__)

# Redis client for OAuth state storage (works across serverless functions)
_redis_client = None
_memory_store = {}

def get_redis():
    """Get or create Redis client"""
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get('REDIS_URL')
        if redis_url:
            try:
                import redis
                _redis_client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                _redis_client.ping()
                print(f"[AUTH DEBUG] Redis connected successfully")
            except Exception as e:
                print(f"[AUTH ERROR] Redis connection failed: {e}")
                _redis_client = False  # Mark as failed
        else:
            print(f"[AUTH ERROR] REDIS_URL not set in environment variables")
            _redis_client = False
    
    return _redis_client if _redis_client else None

def store_oauth_state(state, code_verifier):
    """Store OAuth state in Redis or memory"""
    redis_client = get_redis()
    
    if redis_client:
        # Redis: Store with 10 minute expiration
        redis_client.setex(
            f"oauth_state:{state}",
            timedelta(minutes=10),
            code_verifier
        )
        print(f"[AUTH DEBUG] Stored state in Redis with 10min TTL")
    else:
        _memory_store[state] = {
            'code_verifier': code_verifier,
            'expires_at': datetime.utcnow() + timedelta(minutes=10)
        }
        print(f"[AUTH DEBUG] Stored state in Memory with 10min TTL")

def get_oauth_state(state):
    """Retrieve OAuth state from Redis or memory"""
    redis_client = get_redis()
    
    if redis_client:
        code_verifier = redis_client.get(f"oauth_state:{state}")
        if code_verifier:
            print(f"[AUTH DEBUG] Retrieved state from Redis")
            return {'code_verifier': code_verifier}
        return None
    else:
        data = _memory_store.get(state)
        if data and data['expires_at'] > datetime.utcnow():
            print(f"[AUTH DEBUG] Retrieved state from Memory")
            return {'code_verifier': data['code_verifier']}
        return None

def delete_oauth_state(state):
    """Delete OAuth state after use"""
    redis_client = get_redis()
    
    if redis_client:
        redis_client.delete(f"oauth_state:{state}")
        print(f"[AUTH DEBUG] Deleted state from Redis")
    else:
        if state in _memory_store:
            del _memory_store[state]
            print(f"[AUTH DEBUG] Deleted state from Memory")

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
    
    # 2. Store state (uses MongoDB in production, memory in development)
    store_oauth_state(state, pkce['code_verifier'])
    
    print(f"[AUTH DEBUG] Login - Generated state: {state}")
    print(f"[AUTH DEBUG] Login - Generated code_verifier: {pkce['code_verifier'][:20]}...")
    
    # 3. Redirect to get_authorization_url
    url = client.get_authorization_url(state, pkce['code_challenge'])
    return redirect(url)

@auth_bp.route('/callback')
def callback():
    client = get_ica_client()
    
    # Get state from query params
    state = request.args.get('state')
    
    print(f"[AUTH DEBUG] Callback - Received state: {state}")
    
    # 1. Validate state exists in our store (MongoDB or memory)
    state_data = get_oauth_state(state)
    
    if not state_data:
        print(f"[AUTH ERROR] State not found in store!")
        return "Invalid or expired state. Please try logging in again.", 400
    
    print(f"[AUTH DEBUG] Callback - State found in store")
    
    # 2. Get code_verifier from store
    code_verifier = state_data['code_verifier']
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
        delete_oauth_state(state)
        
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
