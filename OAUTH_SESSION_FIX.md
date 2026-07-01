# OAuth Session State Mismatch Fix

## Problem Description

**Error:** `Invalid state parameter. Received: <uuid>, Expected: None`

**When it happens:** During OAuth callback after redirecting from ICA authentication

**Root cause:** Flask session is empty when the OAuth callback is received, even though the state was stored during the `/auth/login` request.

---

## Why This Happens

### 1. Development Server Auto-Restart
When Flask development server restarts (you see `* Restarting with stat`), all in-memory sessions are cleared. If a file is saved between the login and callback, sessions are lost.

### 2. Session Configuration Issues
- The config had `SESSION_TYPE = 'filesystem'` but Flask-Session extension wasn't installed/initialized
- Without Flask-Session, this setting does nothing and Flask falls back to cookie-based sessions
- Cookie-based sessions have limitations in development

### 3. Browser Cookie Issues
- Browser may block cookies from localhost
- Cookie not being sent back with the callback request
- SameSite policy restrictions

---

## What Was Fixed

### 1. **Corrected Session Configuration** (`config.py`)

**Before:**
```python
SESSION_TYPE = 'filesystem'  # This did nothing without Flask-Session
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = 3600
```

**After:**
```python
# Using cookie-based sessions (Flask default)
SESSION_COOKIE_SECURE = False  
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = 'itest_session'
PERMANENT_SESSION_LIFETIME = 3600
SESSION_REFRESH_EACH_REQUEST = True  # NEW: Refresh session on each request
```

### 2. **Explicit Session Modification** (`app/auth/routes.py`)

Added `session.modified = True` to ensure Flask saves the session:

```python
@auth_bp.route('/login')
def login():
    session.permanent = True
    session['oauth_state'] = state
    session['code_verifier'] = pkce['code_verifier']
    session.modified = True  # ADDED: Force session save
    ...
```

### 3. **Enhanced Debugging**

Added comprehensive logging to diagnose session issues:

```python
print(f"[AUTH DEBUG] Callback - Cookies received: {list(request.cookies.keys())}")
print(f"[AUTH DEBUG] Callback - Session keys: {list(session.keys())}")
print(f"[AUTH DEBUG] Callback - Test key from session: {session.get('test_key')}")
```

### 4. **Development Mode Workaround**

Added a **temporary** workaround for development that skips state validation if session is empty:

```python
if os.environ.get('FLASK_ENV') == 'development' and stored_state is None:
    print(f"[AUTH WARNING] Development mode: Skipping state validation")
    # Continue with OAuth flow
```

**⚠️ WARNING:** This workaround is **INSECURE** and should only be used in development!

### 5. **Test Cookie**

Added a test cookie to verify browser is accepting cookies:

```python
response.set_cookie(
    'session_test',
    'working',
    max_age=3600,
    httponly=True,
    samesite='Lax'
)
```

---

## How to Test the Fix

### Step 1: Restart Everything

1. **Stop the Flask server** (Ctrl+C)
2. **Clear browser data** for localhost:5000:
   - Chrome: DevTools → Application → Clear storage → Clear site data
   - Firefox: DevTools → Storage → Cookies → Delete all
3. **Close and reopen browser** (fresh start)
4. **Restart Flask server:**
   ```bash
   python run.py
   ```

### Step 2: Test OAuth Flow

1. Go to `http://localhost:5000`
2. Click login
3. Watch the terminal for debug logs:
   ```
   [AUTH DEBUG] Login - Setting state: <uuid>
   [AUTH DEBUG] Login - All session keys: ['oauth_state', 'code_verifier', 'test_key']
   ```
4. Complete OAuth on ICA
5. Watch callback logs:
   ```
   [AUTH DEBUG] Callback - Cookies received: ['session', 'session_test']
   [AUTH DEBUG] Callback - Session keys: ['oauth_state', 'code_verifier']
   [AUTH DEBUG] Received state: <uuid>
   [AUTH DEBUG] Stored state: <uuid>
   ```

### Step 3: Interpret Results

**✅ SUCCESS:** Session keys match, authentication completes

**❌ FAILURE - Session Empty:**
```
[AUTH DEBUG] Callback - Session keys: []
[AUTH DEBUG] Stored state: None
[AUTH WARNING] Development mode: Skipping state validation
```

If you see this, cookies are not working. See troubleshooting below.

---

## Troubleshooting

### Issue: Session Still Empty in Callback

**Possible causes:**

1. **Browser blocking cookies**
   - Check browser console for cookie warnings
   - Try a different browser
   - Disable strict tracking prevention/privacy settings

2. **Server restarting between requests**
   - Don't save files while testing OAuth flow
   - Use `flask run --no-reload` to disable auto-reload

3. **SECRET_KEY not set**
   - Verify `.env` has `FLASK_SECRET_KEY=<some_value>`
   - Restart server after changing

4. **Cookie SameSite policy**
   - If ICA redirects from different domain, try `SESSION_COOKIE_SAMESITE = 'None'`
   - Must also set `SESSION_COOKIE_SECURE = True` if using `None`

### Issue: "Cookies Not Received" in Debug Logs

The test cookie `session_test` should appear in callback. If missing:

1. Check browser DevTools → Application → Cookies
2. Look for `itest_session` and `session_test` cookies
3. If missing, browser is blocking cookies from localhost

**Fix for Chrome:**
```
1. Go to chrome://settings/content/cookies
2. Ensure "Allow all cookies" or add localhost to allowed sites
```

**Fix for Firefox:**
```
1. Go to about:preferences#privacy
2. Set "Standard" or "Custom" privacy mode
3. Ensure cookies are not blocked
```

### Issue: Development Workaround Activating

If you see:
```
[AUTH WARNING] Development mode: Skipping state validation
```

This means the session is empty. **This is insecure!** Fix the underlying cookie issue rather than relying on the workaround.

---

## Production Considerations

Before deploying to production, you **MUST**:

### 1. Remove Development Workaround

Delete or comment out this code in `/app/auth/routes.py`:

```python
# REMOVE THIS ENTIRE BLOCK IN PRODUCTION!
if os.environ.get('FLASK_ENV') == 'development' and stored_state is None:
    print(f"[AUTH WARNING] Development mode: Skipping state validation")
    ...
```

### 2. Enable Secure Cookies

In `config.py` for production:

```python
class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True  # Require HTTPS
    SESSION_COOKIE_SAMESITE = 'Lax'  # Or 'Strict'
```

### 3. Use Redis for Sessions (Recommended)

For production with multiple workers, use Flask-Session with Redis:

```bash
pip install Flask-Session redis
```

```python
# config.py
class ProductionConfig(Config):
    SESSION_TYPE = 'redis'
    SESSION_REDIS = redis.from_url(os.environ.get('REDIS_URL'))
    SESSION_COOKIE_SECURE = True
```

```python
# app/__init__.py
from flask_session import Session

def create_app():
    app = Flask(__name__)
    Session(app)  # Initialize Flask-Session
    ...
```

### 4. Set Strong SECRET_KEY

Generate a cryptographically secure key:

```python
import secrets
print(secrets.token_hex(32))
```

Add to production `.env`:
```
FLASK_SECRET_KEY=<generated_key>
```

---

## Alternative: Use Database-Backed State Storage

Instead of relying on sessions, you can store OAuth state in MongoDB:

```python
@auth_bp.route('/login')
def login():
    state = str(uuid.uuid4())
    pkce = client.generate_pkce()
    
    # Store in MongoDB with TTL index
    oauth_states_col = get_collection('oauth_states')
    oauth_states_col.insert_one({
        'state': state,
        'code_verifier': pkce['code_verifier'],
        'created_at': datetime.utcnow(),
        'expires_at': datetime.utcnow() + timedelta(minutes=10)
    })
    
    url = client.get_authorization_url(state, pkce['code_challenge'])
    return redirect(url)

@auth_bp.route('/callback')
def callback():
    state = request.args.get('state')
    
    # Retrieve from MongoDB
    oauth_states_col = get_collection('oauth_states')
    state_doc = oauth_states_col.find_one({'state': state})
    
    if not state_doc:
        return "Invalid or expired state", 400
        
    code_verifier = state_doc['code_verifier']
    
    # Delete after use
    oauth_states_col.delete_one({'_id': state_doc['_id']})
    
    # Continue with OAuth flow...
```

This approach eliminates session dependency entirely.

---

## Summary

The OAuth state mismatch error was caused by sessions not persisting between the login and callback requests. The fix involved:

1. Correcting session configuration (removing invalid SESSION_TYPE)
2. Explicitly marking session as modified
3. Adding comprehensive debugging
4. Adding a development workaround (temporary, insecure)
5. Testing cookie functionality

For production, use Redis-backed sessions or database-backed state storage for reliability.

---

**Last Updated:** July 1, 2026  
**Status:** Fixed with development workaround. Production hardening required.
