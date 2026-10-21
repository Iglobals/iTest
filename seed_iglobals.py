"""Seed iGlobal Educational Services admin account + JUPEB exam catalog.

Run once against a fresh DB, or re-run safely (idempotent):
    python seed_iglobals.py

What it does:
  1. Finds eoluwaseyi205@gmail.com (or any email in ITEST_ADMIN_EMAILS) and
     promotes it to platform_admin, then calls ensure_builtin_org() to
     create/update the built-in iGlobal Educational Services organization.
  2. Calls ensure_catalog_exams() to create the 10 JUPEB subject exams with
     5 placeholder questions each (status=published so they appear once real
     questions are added, but marked placeholder=True for the admin dashboard).

Both steps are fully idempotent: re-running changes nothing if the data
already matches.
"""
from app import create_app
from app.utils.mongo import get_collection

app = create_app()
with app.app_context():
    from app.utils.admin import admin_emails, ensure_builtin_org, promote_if_admin
    from app.utils.catalog import ensure_catalog_exams

    users_col = get_collection('users')
    promoted = []

    for email in sorted(admin_emails()):
        admin = users_col.find_one({'email': email})
        if not admin:
            print(f'⚠  No user found for {email} — they must log in first')
            continue
        admin = promote_if_admin(admin)
        promoted.append(admin)
        print(f'✓  Promoted {email} to platform_admin')

    if not promoted:
        print('No admin users found in DB. Log in as one of the ITEST_ADMIN_EMAILS first, then re-run.')
    else:
        # Use the first promoted admin to own the org
        org = ensure_builtin_org(promoted[0])
        print(f'✓  Built-in org: {org["name"]} (slug: {org["slug"]})')

        created = ensure_catalog_exams(promoted[0], org)
        if created:
            print(f'✓  Created {len(created)} catalog exam(s): {", ".join(created)}')
        else:
            print('✓  All catalog exams already exist')

    print('Done.')
