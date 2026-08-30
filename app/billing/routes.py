"""
Plan selection + Paystack subscription billing.

Flow: select-plan (Free applies immediately; a paid tier redirects to
Paystack's hosted checkout) -> Paystack redirects back to callback/ (fast
path, verified server-side) while the webhook/ endpoint is the authoritative
source of truth for the same event (Paystack's own recommendation - a user
can close the tab before the callback fires, but the webhook still lands).
Both paths funnel through _apply_successful_charge(), keyed by Paystack's
transaction reference, so processing the same charge twice is a no-op.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.auth.decorators import require_auth
from app.extensions import db
from app.models import Payment, SubscriptionPlan
from app.utils import paystack_client
from app.utils.mongo import build_object_id, get_collection
from app.utils.paystack_client import PaystackError

logger = logging.getLogger(__name__)

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

INTERVAL_TO_DAYS = {"monthly": 30, "annual": 365}


@billing_bp.route('/select-plan', methods=['GET', 'POST'])
@require_auth()
def select_plan():
    if request.method == 'POST':
        tier = request.form.get('tier')
        interval = request.form.get('interval') or None

        if tier == 'free':
            users_col = get_collection('users')
            users_col.update_one({"_id": g.current_user["_id"]}, {"$set": {
                "plan_selected": True,
                "plan.type": "free",
                "plan.interval": None,
                "plan.subscription_status": None,
            }})
            flash("You're on the Free plan.", "success")
            return redirect(url_for('dashboard.index'))

        plan_row = SubscriptionPlan.query.filter_by(tier=tier, interval=interval, is_active=True).first()
        if not plan_row or not plan_row.paystack_plan_code:
            flash("That plan isn't available right now.", "error")
            return redirect(url_for('billing.select_plan'))

        try:
            data = paystack_client.initialize_transaction(
                email=g.current_user['email'],
                amount_kobo=int(plan_row.price_ngn * 100),
                plan_code=plan_row.paystack_plan_code,
                callback_url=url_for('billing.callback', _external=True),
                metadata={"user_id": str(g.current_user['_id']), "tier": tier, "interval": interval},
            )
        except PaystackError as exc:
            logger.error("Paystack initialize failed for user=%s: %s", g.current_user['_id'], exc)
            flash("Couldn't start checkout - please try again shortly.", "error")
            return redirect(url_for('billing.select_plan'))

        return redirect(data["authorization_url"])

    plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    by_tier = {}
    for p in plans:
        by_tier.setdefault(p.tier, {})[p.interval] = p

    return render_template('billing/select_plan.html', plans_by_tier=by_tier)


@billing_bp.route('/callback')
@require_auth()
def callback():
    reference = request.args.get('reference')
    if not reference:
        flash("No payment reference received.", "error")
        return redirect(url_for('billing.select_plan'))

    try:
        data = paystack_client.verify_transaction(reference)
    except PaystackError as exc:
        logger.error("Paystack verify failed for reference=%s: %s", reference, exc)
        flash("Couldn't confirm your payment - if you were charged, it'll be applied shortly via webhook.", "error")
        return redirect(url_for('billing.select_plan'))

    if data.get("status") == "success":
        _apply_successful_charge(data)
        flash("Subscription active - welcome aboard!", "success")
        return redirect(url_for('dashboard.index'))

    flash("Payment was not successful.", "error")
    return redirect(url_for('billing.select_plan'))


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    """No @require_auth - Paystack calls this directly. Trust is established
    via the signature, not a session."""
    secret_key = current_app.config.get('PAYSTACK_SECRET_KEY', '').encode()
    signature = request.headers.get('x-paystack-signature', '')
    computed = hmac.new(secret_key, request.get_data(), hashlib.sha512).hexdigest()

    if not hmac.compare_digest(computed, signature):
        logger.warning("Rejected webhook call with invalid Paystack signature.")
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        _apply_successful_charge(data)
    elif event == "subscription.create":
        _attach_subscription_credentials(data)
    elif event in ("subscription.disable", "subscription.not_renew"):
        _mark_subscription_cancelled(data)
    elif event == "invoice.payment_failed":
        logger.warning("Paystack invoice payment failed: %s", data.get("subscription", {}).get("subscription_code"))
    else:
        logger.info("Unhandled Paystack webhook event: %s", event)

    # Acknowledge quickly regardless - Paystack retries on non-200.
    return jsonify({"received": True}), 200


@billing_bp.route('/manage')
@require_auth()
def manage():
    plan = g.current_user.get('plan', {})
    last_payment = (
        Payment.query
        .filter_by(user_id=str(g.current_user['_id']))
        .order_by(Payment.paid_at.desc())
        .first()
    )
    plan_row = None
    if plan.get('type') and plan.get('type') != 'free':
        plan_row = SubscriptionPlan.query.filter_by(tier=plan['type'], interval=plan.get('interval')).first()

    return render_template('billing/manage.html', plan=plan, last_payment=last_payment, plan_row=plan_row)


@billing_bp.route('/cancel', methods=['POST'])
@require_auth()
def cancel():
    plan = g.current_user.get('plan', {})
    subscription_code = plan.get('paystack_subscription_code')
    email_token = plan.get('paystack_email_token')

    if not subscription_code or not email_token:
        flash("No active subscription to cancel.", "error")
        return redirect(url_for('billing.manage'))

    try:
        paystack_client.disable_subscription(subscription_code, email_token)
    except PaystackError as exc:
        logger.error("Paystack disable_subscription failed for user=%s: %s", g.current_user['_id'], exc)
        flash("Couldn't cancel right now - please try again shortly.", "error")
        return redirect(url_for('billing.manage'))

    # Access continues until plan.expires_at - _downgrade_if_expired()
    # (auth/decorators.py) reverts to Free once that date passes.
    users_col = get_collection('users')
    users_col.update_one({"_id": g.current_user["_id"]}, {"$set": {"plan.subscription_status": "cancelled"}})
    flash("Subscription cancelled - you'll keep access until the current period ends.", "success")
    return redirect(url_for('billing.manage'))


def _find_user_for_event(data: dict):
    users_col = get_collection('users')
    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")
    if user_id:
        user = users_col.find_one({"_id": build_object_id(user_id)})
        if user:
            return user

    email = (data.get("customer") or {}).get("email")
    if email:
        return users_col.find_one({"email": email})
    return None


def _apply_successful_charge(data: dict):
    reference = data.get("reference")
    if not reference:
        return

    # Idempotency: provider_ref is unique, so a second delivery of the same
    # event (callback AND webhook both firing, or a Paystack retry) hits the
    # existing row and stops here instead of double-applying the plan.
    if Payment.query.filter_by(provider_ref=reference).first():
        return

    user = _find_user_for_event(data)
    if not user:
        logger.error("Paystack charge.success for reference=%s matched no user.", reference)
        return

    metadata = data.get("metadata") or {}
    tier = metadata.get("tier")
    interval = metadata.get("interval")
    if not tier:
        logger.error("Paystack charge.success for reference=%s had no tier in metadata.", reference)
        return

    plan_row = SubscriptionPlan.query.filter_by(tier=tier, interval=interval).first()
    expires_at = datetime.utcnow() + timedelta(days=INTERVAL_TO_DAYS.get(interval, 30))
    customer_code = (data.get("customer") or {}).get("customer_code")

    users_col = get_collection('users')
    users_col.update_one({"_id": user["_id"]}, {"$set": {
        "plan_selected": True,
        "plan.type": tier,
        "plan.interval": interval,
        "plan.expires_at": expires_at,
        "plan.subscription_status": "active",
        "plan.paystack_customer_code": customer_code,
    }})

    db.session.add(Payment(
        user_id=str(user["_id"]),
        plan_id=plan_row.id if plan_row else None,
        provider="paystack",
        provider_ref=reference,
        amount_ngn=data.get("amount", 0) / 100,
        currency=data.get("currency", "NGN"),
        status="success",
        payment_metadata=data,
        paid_at=datetime.utcnow(),
    ))
    try:
        db.session.commit()
    except IntegrityError:
        # The webhook and the callback redirect both reached here for the
        # same reference at nearly the same time - provider_ref's unique
        # constraint caught the second one. The Mongo update above already
        # ran twice harmlessly (same values both times), so there's nothing
        # left to do but drop this duplicate insert attempt.
        db.session.rollback()


def _attach_subscription_credentials(data: dict):
    """subscription.create is the only event carrying email_token, which
    /billing/cancel needs alongside the subscription_code to cancel later."""
    user = _find_user_for_event(data)
    if not user:
        logger.error("Paystack subscription.create matched no user (subscription_code=%s).", data.get("subscription_code"))
        return

    users_col = get_collection('users')
    users_col.update_one({"_id": user["_id"]}, {"$set": {
        "plan.paystack_subscription_code": data.get("subscription_code"),
        "plan.paystack_email_token": data.get("email_token"),
    }})


def _mark_subscription_cancelled(data: dict):
    user = _find_user_for_event(data)
    if not user:
        return
    users_col = get_collection('users')
    users_col.update_one({"_id": user["_id"]}, {"$set": {"plan.subscription_status": "cancelled"}})
