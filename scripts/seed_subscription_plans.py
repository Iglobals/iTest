"""
Seeds/updates the `subscription_plans` table and creates the matching
recurring Plans on Paystack.

Run scripts/migrate_subscription_plans.py first (adds the columns this needs).
Requires PAYSTACK_SECRET_KEY in .env - uses whichever key is set there (test
or live), same as the rest of the app.

Prices below are NGN>1339.05 (rate fetched 2026-08-30) used only to seed the
usd column - everything here is stored in the DB and meant to be edited
there (or re-run this script after changing PRICING_NGN below) rather than
hardcoded elsewhere in the app.

Usage:
    python scripts/seed_subscription_plans.py
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import SubscriptionPlan
from app.utils.plans import PLAN_LIMITS
from app.utils import paystack_client

# Approximate rate used only to seed price_usd - not a live conversion.
NGN_PER_USD = 1339.05

# The only numbers that matter here. Change these and re-run to update
# pricing (existing rows are upserted by name, Paystack plans are created
# once and then reused).
PRICING_NGN = {
    "pro": 11500,
    "enterprise": 25000,
}

def ngn_to_usd(amount_ngn):
    return round(amount_ngn / NGN_PER_USD, 2)


def json_safe_limits(tier):
    """PLAN_LIMITS uses float('inf') for unlimited, which Python's json module
    happily renders as the bare token `Infinity` - valid to Python/JS, but
    rejected by Postgres's strict JSON parser. This column is descriptive
    only (actual gating always reads PLAN_LIMITS directly, never this row),
    so unlimited is just stored as null here."""
    limits = PLAN_LIMITS.get(tier, {})
    return {k: (None if v == float('inf') else v) for k, v in limits.items()}


def upsert_plan(name, tier, interval, price_ngn, paystack_plan_code):
    plan = SubscriptionPlan.query.filter_by(name=name).first()
    if plan is None:
        plan = SubscriptionPlan(name=name)

    plan.tier = tier
    plan.interval = interval
    plan.price_ngn = price_ngn
    plan.price_usd = ngn_to_usd(price_ngn) if price_ngn else 0
    plan.billing = interval or "free"
    plan.paystack_plan_code = paystack_plan_code
    plan.limits = json_safe_limits(tier)
    plan.features = json_safe_limits(tier)
    plan.is_active = True

    db.session.add(plan)
    return plan


def get_or_create_paystack_plan(name, amount_ngn, paystack_interval):
    existing = SubscriptionPlan.query.filter_by(name=name).first()
    if existing and existing.paystack_plan_code:
        print(f"  {name}: reusing existing Paystack plan {existing.paystack_plan_code}")
        return existing.paystack_plan_code

    data = paystack_client.create_plan(
        name=name,
        amount_kobo=int(amount_ngn * 100),
        interval=paystack_interval,
    )
    print(f"  {name}: created Paystack plan {data['plan_code']}")
    return data["plan_code"]


def main():
    app = create_app()
    with app.app_context():
        print("--- Free ---")
        upsert_plan("Free", tier="free", interval=None, price_ngn=0, paystack_plan_code=None)

        for tier, monthly_ngn in PRICING_NGN.items():
            annual_ngn = monthly_ngn * 12  # no discount applied yet - edit in DB once pricing is finalized
            label = tier.capitalize()

            print(f"--- {label} ---")
            monthly_code = get_or_create_paystack_plan(f"{label} Monthly", monthly_ngn, "monthly")
            annual_code = get_or_create_paystack_plan(f"{label} Annual", annual_ngn, "annually")

            upsert_plan(f"{label} Monthly", tier=tier, interval="monthly", price_ngn=monthly_ngn, paystack_plan_code=monthly_code)
            upsert_plan(f"{label} Annual", tier=tier, interval="annual", price_ngn=annual_ngn, paystack_plan_code=annual_code)

        db.session.commit()
        print("\nDone. subscription_plans is seeded.")


if __name__ == '__main__':
    main()
