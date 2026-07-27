from flask import Flask
from config import config
from app.extensions import db, init_mongo

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    init_mongo(app)
    
    # Register blueprints
    from app.landing.routes import landing_bp
    app.register_blueprint(landing_bp)

    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.dashboard.routes import dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    from app.onboarding.routes import onboarding_bp
    app.register_blueprint(onboarding_bp)
    
    from app.organizations.routes import org_bp
    app.register_blueprint(org_bp)
    
    from app.classes.routes import classes_bp
    app.register_blueprint(classes_bp)
    
    from app.media.routes import media_bp
    app.register_blueprint(media_bp)
    
    from app.exams.routes import exams_bp
    app.register_blueprint(exams_bp)
    
    from app.sessions.routes import sessions_bp
    app.register_blueprint(sessions_bp)
    
    from app.api.webhooks import webhooks_bp
    app.register_blueprint(webhooks_bp)
    
    # TODO: Register other blueprints here
    
    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app
