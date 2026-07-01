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
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
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
    
    # Parse sslmode from URI if present, otherwise use default settings
    engine_options = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Only add connect_args if sslmode is NOT already in the URI
    if postgres_uri and 'sslmode=' not in postgres_uri:
        engine_options['connect_args'] = {'sslmode': 'prefer'}
    
    SQLALCHEMY_ENGINE_OPTIONS = engine_options
    
    # ICA Integration
    ICA_BASE_URL = os.environ.get('ICA_BASE_URL')
    ICA_CLIENT_ID = os.environ.get('ICA_CLIENT_ID')
    ICA_CLIENT_SECRET = os.environ.get('ICA_CLIENT_SECRET')
    ICA_REDIRECT_URI = os.environ.get('ICA_REDIRECT_URI', 'http://localhost:5000/auth/callback')
    
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
