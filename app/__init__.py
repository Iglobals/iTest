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

    from app.billing.routes import billing_bp
    app.register_blueprint(billing_bp)
    
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

    from app.messaging.routes import messaging_bp
    app.register_blueprint(messaging_bp)

    from app.api.webhooks import webhooks_bp
    app.register_blueprint(webhooks_bp)

    from app.users.routes import users_bp
    app.register_blueprint(users_bp)

    # TODO: Register other blueprints here
    
    @app.route('/health')
    def health():
        return {'status': 'ok'}

    from app.utils import exam_rules
    app.add_template_filter(exam_rules.attempt_limit_label, 'attempt_limit_label')
    app.add_template_filter(exam_rules.is_proctored, 'is_proctored')
    app.add_template_filter(exam_rules.is_ai_proctored, 'is_ai_proctored')
    app.add_template_filter(exam_rules.liveness_completed, 'liveness_completed')

    @app.context_processor
    def _plan_flags():
        # Lets exam create/edit pages gate the AI proctoring checkbox (send
        # the user to upgrade instead of letting them tick it) - the API
        # enforces the same rule in exams/routes.py.
        from flask import g
        user = getattr(g, 'current_user', None)
        if not user:
            return {}
        from app.utils.plans import get_plan_limit
        plan = (user.get('plan') or {}).get('type', 'free')
        from app.utils import didit_client
        return {
            'can_use_ai_proctoring': bool(get_plan_limit(plan, 'can_use_ai_proctoring')),
            # Didit replaces the manual photo flow once its env vars are set.
            'didit_enabled': didit_client.is_configured(),
        }

    return app
