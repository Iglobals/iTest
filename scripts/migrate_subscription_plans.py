"""
One-off schema patch for the `subscription_plans` table.

This project has no Alembic/Flask-Migrate setup - tables are created and
patched by hand via scripts like this one (see reset_db.py). Adds the
tier/interval/paystack_plan_code columns needed for the Paystack subscription
flow, without touching existing rows.

Usage:
    python scripts/migrate_subscription_plans.py
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text

from app import create_app
from app.extensions import db

STATEMENTS = [
    "ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS tier TEXT",
    "ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS interval TEXT",
    "ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS paystack_plan_code TEXT",
]


def main():
    app = create_app()
    with app.app_context():
        for stmt in STATEMENTS:
            print(f"Running: {stmt}")
            db.session.execute(text(stmt))
        db.session.commit()
        print("Done. subscription_plans now has tier / interval / paystack_plan_code.")


if __name__ == '__main__':
    main()
