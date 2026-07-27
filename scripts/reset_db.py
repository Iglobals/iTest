"""
Full data reset for a pre-launch environment.

Wipes every collection in MongoDB and every table in Postgres, in both
databases the app talks to (see app/extensions.py, config.py). This is a
one-off dev/reset utility, not part of the running app.

By default this only prints row/document counts (dry run). Nothing is
deleted unless you pass --yes.

Usage:
    python scripts/reset_db.py            # dry run, prints counts only
    python scripts/reset_db.py --yes      # actually deletes everything
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text

from app import create_app
from app.extensions import db

MONGO_COLLECTIONS = [
    'users',
    'organizations',
    'classes',
    'exams',
    'exam_sessions',
    'notifications',
    'class_broadcasts',
    'class_messages',
    'question_banks',
    'subject_tags',
]

# Order matters: payments references subscription_plans via a foreign key.
POSTGRES_TABLES = [
    'exam_scores',
    'national_rankings',
    'payments',
    'subscription_plans',
]


def main():
    do_delete = '--yes' in sys.argv

    app = create_app()
    with app.app_context():
        mongo = app.mongo
        if mongo is None:
            print('app.mongo is not configured (MONGODB_URI missing) - skipping Mongo.')
        else:
            print('--- MongoDB ---')
            for name in MONGO_COLLECTIONS:
                col = mongo[name]
                count = col.count_documents({})
                print(f'{name:20s} {count:8d} document(s)' + (' -> deleting' if do_delete and count else ''))
                if do_delete and count:
                    result = col.delete_many({})
                    print(f'{"":20s} deleted {result.deleted_count}')

        print()
        print('--- PostgreSQL ---')
        for table in POSTGRES_TABLES:
            count = db.session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
            print(f'{table:20s} {count:8d} row(s)')

        if do_delete:
            db.session.execute(text(
                f'TRUNCATE TABLE {", ".join(POSTGRES_TABLES)} RESTART IDENTITY CASCADE;'
            ))
            db.session.commit()
            print('Postgres tables truncated.')

    print()
    if do_delete:
        print('Reset complete.')
    else:
        print('Dry run only - nothing was deleted. Re-run with --yes to actually reset.')


if __name__ == '__main__':
    main()
