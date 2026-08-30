from flask import Blueprint, render_template

from app.models import SubscriptionPlan

landing_bp = Blueprint('landing', __name__)

@landing_bp.route('/')
def index():
    return render_template('landing/index.html')

@landing_bp.route('/pricing')
def pricing():
    # Sourced from the same subscription_plans rows billing/select-plan uses,
    # so the marketing page and the actual checkout never disagree on price.
    plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    by_tier = {}
    for p in plans:
        by_tier.setdefault(p.tier, {})[p.interval] = p
    return render_template('landing/pricing.html', plans_by_tier=by_tier)
