import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'hard to guess string'
    
    # MongoDB setup (primary data storage)
    MONGO_URI = os.environ.get('MONGODB_URI')
    
    # PostgreSQL setup (for reporting, scoring, ranking)
    SQLALCHEMY_DATABASE_URI = os.environ.get('POSTGRES_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'connect_args': {
            'sslmode': 'prefer'  # Options: disable, allow, prefer, require, verify-ca, verify-full
        } if os.environ.get('POSTGRES_URI') and 'postgres' in os.environ.get('POSTGRES_URI', '') else {}
    }
    
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
