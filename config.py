import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'hard to guess string'
    
    # Session configuration for OAuth flow
    # Using cookie-based sessions (Flask default) for simplicity
    # For production with high traffic, consider Flask-Session with Redis
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_NAME = 'itest_session'
    # Sliding window: each request pushes expiry forward. Must outlive the
    # 15-min ICA access token by a lot, otherwise the cookie (and with it the
    # refresh_token) disappears after an hour idle and the user has to log in
    # again even though their refresh token is still good for 30 days.
    PERMANENT_SESSION_LIFETIME = 7 * 24 * 3600  # 7 days
    SESSION_REFRESH_EACH_REQUEST = True
    
    # MongoDB setup (primary data storage)
    MONGO_URI = os.environ.get('MONGODB_URI')
    
    # PostgreSQL setup (for reporting, scoring, ranking)
    # Force pg8000 driver (works on Vercel, psycopg2 doesn't)
    postgres_uri = os.environ.get('POSTGRES_URI', '')
    if postgres_uri.startswith('postgresql://'):
        # Replace postgresql:// with postgresql+pg8000://
        postgres_uri = postgres_uri.replace('postgresql://', 'postgresql+pg8000://', 1)
    
    SQLALCHEMY_DATABASE_URI = postgres_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Engine options - NO connect_args for pg8000
    # pg8000 handles SSL parameters from the URI itself
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # ICA Integration
    ICA_BASE_URL = os.environ.get('ICA_BASE_URL')
    ICA_CLIENT_ID = os.environ.get('ICA_CLIENT_ID')
    ICA_CLIENT_SECRET = os.environ.get('ICA_CLIENT_SECRET')
    ICA_REDIRECT_URI = os.environ.get('ICA_REDIRECT_URI', 'http://localhost:5000/auth/callback')
    # Where iTest's own Settings page links out to for identity/account
    # edits (name, email, password) - deliberately a separate env var rather
    # than guessing/hardcoding the exact public domain spelling.
    ICA_ACCOUNT_URL = os.environ.get('ICA_ACCOUNT_URL', '#')
    
    # AI Proctoring (anticheat-system-roboflow FastAPI service)
    PROCTOR_API_BASE_URL = os.environ.get('PROCTOR_API_BASE_URL', 'http://localhost:8000')
    PROCTOR_API_KEY = os.environ.get('PROCTOR_API_KEY', '')

    # Paystack (subscription billing - see app/billing/routes.py). This is the
    # ONE shared IGLOBALS HUB Paystack account's key - same value across every
    # client app - used only for OUTBOUND calls (verify/create-plan/disable).
    PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
    PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '')

    # ICA centralized Paystack webhook relay - the secret ICA generated for
    # iTest specifically (Settings > Clients > iTest > Payment webhooks in
    # the ICA admin panel), NOT the shared Paystack key above. Verifies
    # inbound calls to /billing/webhook, which now come from ICA, not Paystack.
    ICA_WEBHOOK_RELAY_SECRET = os.environ.get('ICA_WEBHOOK_RELAY_SECRET', '')

    # Bearer secret for /api/webhooks/grant-access (one email -> one exam id).
    # Empty = that endpoint refuses every call (it used to fall back to a
    # hard-coded test secret).
    WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')
    # HMAC secret shared with the iGlobal e-library (its ITEST_WEBHOOK_SECRET)
    # for /api/webhooks/igs/exam-access - book + exam purchases.
    IGS_WEBHOOK_SECRET = os.environ.get('IGS_WEBHOOK_SECRET', '')

    # Flutterwave
    FLUTTERWAVE_PUBLIC_KEY = os.environ.get('FLUTTERWAVE_PUBLIC_KEY')
    FLUTTERWAVE_SECRET_KEY = os.environ.get('FLUTTERWAVE_SECRET_KEY')
    FLUTTERWAVE_PUBLIC_KEY_LIVE = os.environ.get('LIVE_FLUTTERWAVE_PUBLIC_KEY') or os.environ.get('FLUTTERWAVE_PUBLIC_KEY')
    FLUTTERWAVE_SECRET_KEY_LIVE = os.environ.get('LIVE_FLUTTERWAVE_SECRET_KEY') or os.environ.get('FLUTTERWAVE_SECRET_KEY')

    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    # Cloudinary fallback
    CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL')

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True

class ProductionConfig(Config):
    pass

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
