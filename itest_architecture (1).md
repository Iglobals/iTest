# iTEST — Full System Architecture Guide
**Product:** iTEST by iGlobals Technology Inc.  
**Stack:** Flask (Python) + MongoDB (primary) + PostgreSQL (scores/rankings) + ICA OAuth  
**Version:** MVP 1.0  

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Database Design](#2-database-design)
   - 2a. MongoDB Collections (Document Store)
   - 2b. PostgreSQL Schema (Relational Store)
3. [Folder & File Structure](#3-folder--file-structure)
4. [ICA OAuth Integration](#4-ica-oauth-integration)
5. [API Reference — Phase by Phase](#5-api-reference)
   - Phase 1: Auth & User Onboarding
   - Phase 2: Classes, Organizations & Membership
   - Phase 3: Exam Creation & Question Management
   - Phase 4: Exam Taking (CBT Engine)
   - Phase 5: Results, Analytics & Rankings
   - Phase 6: Admin & Platform Management
   - Phase 7: Payments & Subscriptions
6. [Build Phases & Execution Order](#6-build-phases--execution-order)
7. [Environment & Configuration](#7-environment--configuration)
8. [PWA Configuration](#8-pwa-configuration)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                               │
│  Browser (PWA) / Mobile (Installed PWA) / Desktop (Installed PWA)  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────▼─────────────────────────────────────────┐
│                        FLASK APP (itest/)                           │
│  Jinja2 Templates (HTML/CSS/JS)  |  Blueprints  |  Middleware       │
└──────┬────────────────────┬──────────────────────┬──────────────────┘
       │                    │                      │
┌──────▼──────┐   ┌─────────▼──────────┐  ┌───────▼────────────────┐
│  ICA OAuth  │   │  MongoDB (Atlas)    │  │ PostgreSQL (Neon)       │
│ (External)  │   │  Primary Store:     │  │ Relational Store:       │
│             │   │  - users            │  │ - exam_scores           │
│  SSO/JWT    │   │  - classes          │  │ - national_rankings     │
│             │   │  - organizations    │  │ - subject_rankings      │
└─────────────┘   │  - exams            │  │ - subscription_plans    │
                  │  - questions        │  │ - payments              │
                  │  - exam_sessions    │  │ - invoices              │
                  │  - notifications    │  └────────────────────────┘
                  │  - subject_tags     │
                  └────────────────────┘
                            │
               ┌────────────▼────────────┐
               │     External Services   │
               │  Cloudinary (media)     │
               │  Flutterwave (payment)  │
               │  Pusher/SSE (realtime)  │
               └────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Auth | ICA OAuth 2.0 + PKCE | SSO across all iGlobals apps |
| Primary DB | MongoDB | Flexible schema for exams, classes, questions |
| Rankings/Scores | PostgreSQL | Aggregations, leaderboard queries, joins |
| Media | Cloudinary | Profile images, org logos, question images |
| Realtime | Server-Sent Events (SSE) | Proctoring flags, exam submission alerts |
| Question Import | JSON / CSV upload | Bulk question ingestion |
| Exam Answers | localStorage + periodic sync | Offline resilience during exam |

---

## 2. Database Design

### 2a. MongoDB Collections

#### Collection: `users`

```json
{
  "_id": "ObjectId",
  "ica_sub": "string (ICA user ID — primary link)",
  "email": "string",
  "full_name": "string",
  "role": "student | teacher | org_admin | platform_admin",
  "avatar_url": "string (Cloudinary URL)",
  "institution": "string",
  "programme": "string",
  "phone": "string",
  "date_of_birth": "ISODate",
  "subject_tags_interest": ["tag_id"],
  "notification_preferences": {
    "email": true,
    "in_app": true
  },
  "plan": {
    "type": "free | basic | pro | enterprise",
    "expires_at": "ISODate | null",
    "stripe_customer_id": "string | null"
  },
  "limits": {
    "max_classes": 2,
    "max_students_per_class": 30,
    "max_total_students": 60,
    "ai_proctoring": false,
    "analytics_advanced": false
  },
  "created_at": "ISODate",
  "updated_at": "ISODate",
  "last_login_at": "ISODate",
  "is_active": true,
  "is_email_verified": true
}
```

#### Collection: `organizations`

```json
{
  "_id": "ObjectId",
  "name": "string",
  "slug": "string (unique)",
  "logo_url": "string (Cloudinary)",
  "admin_user_id": "ObjectId (ref: users)",
  "description": "string",
  "website": "string",
  "contact_email": "string",
  "plan": {
    "type": "free | pro | enterprise",
    "expires_at": "ISODate | null"
  },
  "limits": {
    "max_classes": 5,
    "max_teachers": 10,
    "ai_proctoring": false,
    "advanced_analytics": false
  },
  "pending_teacher_requests": [
    {
      "teacher_id": "ObjectId",
      "class_id": "ObjectId",
      "status": "pending | accepted | rejected",
      "requested_at": "ISODate",
      "attempts": 1
    }
  ],
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

#### Collection: `classes`

```json
{
  "_id": "ObjectId",
  "name": "string",
  "description": "string",
  "cover_image_url": "string",
  "organization_id": "ObjectId | null",
  "organization_status": "none | pending | approved | rejected",
  "teachers": [
    {
      "user_id": "ObjectId",
      "role": "owner | collaborator",
      "added_at": "ISODate"
    }
  ],
  "students": [
    {
      "user_id": "ObjectId",
      "status": "pending | active | declined | removed",
      "invited_at": "ISODate",
      "joined_at": "ISODate | null"
    }
  ],
  "join_requests": [
    {
      "student_id": "ObjectId",
      "status": "pending | accepted | rejected",
      "attempt_count": 1,
      "max_attempts": 3,
      "last_requested_at": "ISODate"
    }
  ],
  "subject_tags": ["tag_id"],
  "is_active": true,
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

#### Collection: `subject_tags`

```json
{
  "_id": "ObjectId",
  "name": "string",
  "slug": "string",
  "category": "general | science | arts | commerce | technology | music | language",
  "icon": "string",
  "created_at": "ISODate"
}
```

#### Collection: `question_banks`

```json
{
  "_id": "ObjectId",
  "owner_id": "ObjectId (ref: users)",
  "owner_type": "teacher | admin",
  "organization_id": "ObjectId | null",
  "name": "string",
  "description": "string",
  "subject_tag_id": "ObjectId",
  "visibility": "private | organization | public",
  "questions": [
    {
      "_id": "ObjectId",
      "text": "string",
      "image_url": "string | null",
      "type": "mcq | true_false | short_answer | essay | numerical",
      "difficulty": "easy | medium | hard",
      "options": [
        {
          "key": "A",
          "text": "string",
          "image_url": "string | null"
        }
      ],
      "correct_answer": "A | true | string | number",
      "explanation": "string | null",
      "marks": 1,
      "tags": ["string"],
      "created_at": "ISODate"
    }
  ],
  "total_questions": 0,
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

#### Collection: `exams`

```json
{
  "_id": "ObjectId",
  "title": "string",
  "description": "string",
  "cover_image_url": "string | null",
  "created_by": "ObjectId (ref: users)",
  "created_by_type": "teacher | admin",
  "exam_type": "public | private | platform_standard",
  "visibility": {
    "type": "public | class | students_list",
    "class_ids": ["ObjectId"],
    "student_emails": ["string"],
    "student_ids": ["ObjectId"]
  },
  "subject_tag_id": "ObjectId",
  "organization_id": "ObjectId | null",
  "instructions": "string",
  "settings": {
    "duration_minutes": 60,
    "allow_retake": true,
    "max_attempts": 3,
    "randomize_questions": true,
    "randomize_options": false,
    "show_result_immediately": true,
    "pass_mark_percent": 50,
    "question_per_page": 1,
    "ai_proctoring_enabled": false,
    "allow_review_before_submit": true,
    "auto_submit_on_timeout": true
  },
  "schedule": {
    "available_from": "ISODate | null",
    "available_until": "ISODate | null",
    "is_published": false
  },
  "questions": [
    {
      "question_id": "ObjectId (ref: question in question_bank)",
      "bank_id": "ObjectId",
      "order": 1,
      "marks": 1
    }
  ],
  "total_questions": 0,
  "total_marks": 0,
  "platform_tags": ["JUPEB", "IJMB", "Pre-Degree", "Foundation"],
  "status": "draft | published | archived | suspended",
  "statistics": {
    "total_attempts": 0,
    "avg_score_percent": 0,
    "pass_rate_percent": 0
  },
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

#### Collection: `exam_sessions`

```json
{
  "_id": "ObjectId",
  "exam_id": "ObjectId",
  "student_id": "ObjectId",
  "attempt_number": 1,
  "status": "in_progress | submitted | timed_out | abandoned",
  "started_at": "ISODate",
  "submitted_at": "ISODate | null",
  "time_remaining_seconds": 3600,
  "answers": [
    {
      "question_id": "ObjectId",
      "selected_option": "A | true | string | null",
      "time_spent_seconds": 45,
      "flagged": false,
      "answered_at": "ISODate"
    }
  ],
  "proctoring_flags": [
    {
      "type": "tab_switch | camera_off | screenshot_attempt | face_not_detected | multiple_faces",
      "flagged_at": "ISODate",
      "screenshot_url": "string | null"
    }
  ],
  "question_order": ["ObjectId"],
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

#### Collection: `notifications`

```json
{
  "_id": "ObjectId",
  "recipient_id": "ObjectId (ref: users)",
  "sender_id": "ObjectId | null",
  "type": "class_invite | join_request | org_request | exam_published | result_ready | system",
  "title": "string",
  "body": "string",
  "metadata": {
    "class_id": "ObjectId | null",
    "exam_id": "ObjectId | null",
    "org_id": "ObjectId | null",
    "action_url": "string | null"
  },
  "is_read": false,
  "created_at": "ISODate"
}
```

---

### 2b. PostgreSQL Schema (Relational Store)

```sql
-- Scores table: one row per exam attempt
CREATE TABLE exam_scores (
  id              BIGSERIAL PRIMARY KEY,
  session_id      TEXT NOT NULL UNIQUE,       -- MongoDB exam_session _id as string
  exam_id         TEXT NOT NULL,              -- MongoDB exam _id
  student_id      TEXT NOT NULL,              -- MongoDB user _id
  organization_id TEXT,                       -- MongoDB org _id (nullable)
  class_id        TEXT,                       -- MongoDB class _id (nullable)
  subject_tag_id  TEXT,
  subject_tag_name TEXT,
  exam_title      TEXT NOT NULL,
  attempt_number  INT NOT NULL DEFAULT 1,
  score           NUMERIC(10, 2) NOT NULL,
  total_marks     NUMERIC(10, 2) NOT NULL,
  score_percent   NUMERIC(5, 2) NOT NULL,
  passed          BOOLEAN NOT NULL,
  time_spent_secs INT,
  total_questions INT,
  correct_count   INT,
  incorrect_count INT,
  unanswered_count INT,
  submitted_at    TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scores_student   ON exam_scores(student_id);
CREATE INDEX idx_scores_exam      ON exam_scores(exam_id);
CREATE INDEX idx_scores_subject   ON exam_scores(subject_tag_id);
CREATE INDEX idx_scores_org       ON exam_scores(organization_id);
CREATE INDEX idx_scores_submitted ON exam_scores(submitted_at DESC);

-- National Rankings (materialised per exam)
CREATE TABLE national_rankings (
  id              BIGSERIAL PRIMARY KEY,
  exam_id         TEXT NOT NULL,
  student_id      TEXT NOT NULL,
  student_name    TEXT NOT NULL,
  best_score_pct  NUMERIC(5,2) NOT NULL,
  attempt_count   INT NOT NULL DEFAULT 1,
  national_rank   INT,
  subject_rank    INT,
  period          TEXT NOT NULL,             -- 'all_time' | 'weekly' | 'monthly'
  period_label    TEXT,                      -- e.g. '2025-W03' | '2025-06'
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(exam_id, student_id, period)
);

CREATE INDEX idx_rankings_exam    ON national_rankings(exam_id);
CREATE INDEX idx_rankings_student ON national_rankings(student_id);
CREATE INDEX idx_rankings_period  ON national_rankings(period, period_label);

-- Subscription plans
CREATE TABLE subscription_plans (
  id           SERIAL PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,         -- 'free' | 'basic' | 'pro' | 'enterprise'
  price_ngn    NUMERIC(12,2) NOT NULL,
  price_usd    NUMERIC(12,2),
  billing      TEXT NOT NULL,               -- 'monthly' | 'annual' | 'one_time'
  limits       JSONB NOT NULL,
  features     JSONB NOT NULL,
  is_active    BOOLEAN DEFAULT TRUE,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Payments
CREATE TABLE payments (
  id               BIGSERIAL PRIMARY KEY,
  user_id          TEXT NOT NULL,
  organization_id  TEXT,
  plan_id          INT REFERENCES subscription_plans(id),
  provider         TEXT NOT NULL,            -- 'flutterwave' | 'paystack'
  provider_ref     TEXT NOT NULL UNIQUE,     -- provider transaction ID
  amount_ngn       NUMERIC(12,2) NOT NULL,
  currency         TEXT DEFAULT 'NGN',
  status           TEXT NOT NULL,            -- 'pending' | 'success' | 'failed' | 'refunded'
  metadata         JSONB,
  paid_at          TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_payments_user ON payments(user_id);
CREATE INDEX idx_payments_org  ON payments(organization_id);
```

---

## 3. Folder & File Structure

```
itest/
├── run.py                          # App entry point: creates and runs Flask app
├── config.py                       # Config classes: DevelopmentConfig, ProductionConfig
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
│
├── app/
│   ├── __init__.py                 # create_app() factory, registers blueprints, extensions
│   ├── extensions.py               # PyMongo, SQLAlchemy, Mail, Limiter initialised here
│   │
│   ├── auth/                       # ICA OAuth integration
│   │   ├── __init__.py             # Blueprint definition
│   │   ├── routes.py               # /auth/login, /auth/callback, /auth/logout
│   │   ├── ica_client.py           # ICAClient class: PKCE gen, token exchange, verify JWT
│   │   └── decorators.py           # @require_auth, @require_role("teacher"), @require_plan("pro")
│   │
│   ├── users/
│   │   ├── __init__.py
│   │   ├── routes.py               # /api/users/me, /api/users/me/avatar
│   │   ├── service.py              # get_or_create_user(), update_profile(), upload_avatar()
│   │   └── models.py               # Pydantic/dataclass schema for user document
│   │
│   ├── organizations/
│   │   ├── __init__.py
│   │   ├── routes.py               # CRUD org, logo upload, teacher invites, class registration
│   │   ├── service.py              # create_org(), request_class_registration(), respond_to_teacher_request()
│   │   └── models.py
│   │
│   ├── classes/
│   │   ├── __init__.py
│   │   ├── routes.py               # CRUD class, student invites, join requests, bulk invite
│   │   ├── service.py              # create_class(), invite_student(), accept_join_request()
│   │   └── models.py
│   │
│   ├── exams/
│   │   ├── __init__.py
│   │   ├── routes.py               # Create, edit, publish, list, delete exams
│   │   ├── service.py              # create_exam(), publish_exam(), clone_exam(), import_questions_from_file()
│   │   ├── question_import.py      # parse_json_upload(), parse_csv_upload(), parse_excel_upload()
│   │   └── models.py
│   │
│   ├── question_banks/
│   │   ├── __init__.py
│   │   ├── routes.py               # CRUD question banks, add/edit/delete individual questions
│   │   ├── service.py              # create_bank(), add_question(), bulk_add_questions(), search_questions()
│   │   └── models.py
│   │
│   ├── sessions/                   # CBT exam-taking engine
│   │   ├── __init__.py
│   │   ├── routes.py               # Start session, get question, save answer, submit, get status
│   │   ├── service.py              # start_session(), get_next_question(), save_answer(), submit_session()
│   │   ├── grader.py               # grade_session(): auto-grade MCQ/T-F/numerical, flag essays
│   │   └── models.py
│   │
│   ├── results/
│   │   ├── __init__.py
│   │   ├── routes.py               # Get result for session, list student results, class results
│   │   ├── service.py              # get_result(), compute_analytics(), export_report()
│   │   └── models.py
│   │
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── routes.py               # Student dashboard analytics, org analytics, class analytics
│   │   └── service.py              # aggregate_student_performance(), subject_trend(), readiness_score()
│   │
│   ├── rankings/
│   │   ├── __init__.py
│   │   ├── routes.py               # Get national/subject/institutional rankings for an exam
│   │   ├── service.py              # compute_rankings(), get_student_rank(), refresh_leaderboard()
│   │   └── scheduler.py           # APScheduler jobs: rebuild rankings weekly/monthly
│   │
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── routes.py               # List notifs, mark read, SSE stream endpoint
│   │   └── service.py              # send_notification(), mark_read(), get_unread_count()
│   │
│   ├── payments/
│   │   ├── __init__.py
│   │   ├── routes.py               # Initiate payment, webhook, get invoice history
│   │   ├── service.py              # initiate_payment(), verify_payment(), apply_plan()
│   │   └── webhook.py              # handle_flutterwave_webhook()
│   │
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── routes.py               # Admin: manage users, orgs, approve exams, platform stats
│   │   └── service.py              # platform_stats(), suspend_user(), approve_exam()
│   │
│   ├── uploads/
│   │   ├── __init__.py
│   │   ├── routes.py               # /api/uploads/image — Cloudinary upload proxy
│   │   └── cloudinary_client.py    # upload_image(), delete_image()
│   │
│   ├── subject_tags/
│   │   ├── __init__.py
│   │   └── routes.py               # GET /api/tags — list all subject tags
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── mongo.py                # get_collection(), build_object_id(), paginate_cursor()
│   │   ├── postgres.py             # get_pg_session(), exec_query()
│   │   ├── response.py             # success_response(), error_response() helpers
│   │   ├── pagination.py           # paginate() helper: page, per_page, total
│   │   ├── validators.py           # validate_email(), validate_object_id()
│   │   ├── file_parser.py          # parse_csv_questions(), parse_json_questions(), parse_excel_questions()
│   │   └── email.py                # send_email() wrapper (SMTP or Mailgun)
│   │
│   ├── templates/                  # Jinja2 HTML templates
│   │   ├── base.html               # Root layout: head, nav, footer, PWA manifest link
│   │   ├── landing/
│   │   │   ├── index.html          # Public landing page
│   │   │   └── about.html
│   │   ├── auth/
│   │   │   └── loading.html        # OAuth redirect holding page
│   │   ├── dashboard/
│   │   │   ├── student.html
│   │   │   ├── teacher.html
│   │   │   └── org_admin.html
│   │   ├── exam/
│   │   │   ├── create.html
│   │   │   ├── edit.html
│   │   │   ├── detail.html
│   │   │   └── take.html           # CBT engine UI
│   │   ├── results/
│   │   │   └── detail.html
│   │   ├── classes/
│   │   │   ├── list.html
│   │   │   └── detail.html
│   │   ├── admin/
│   │   │   └── dashboard.html
│   │   └── errors/
│   │       ├── 403.html
│   │       ├── 404.html
│   │       └── 500.html
│   │
│   └── static/
│       ├── manifest.json           # PWA manifest
│       ├── sw.js                   # Service worker
│       ├── icons/                  # PWA icons (192x192, 512x512)
│       ├── css/
│       │   ├── main.css            # Purple-gold design system variables
│       │   ├── auth.css
│       │   ├── dashboard.css
│       │   └── exam.css
│       └── js/
│           ├── app.js              # Global: notifications SSE, nav, toasts
│           ├── cbt_engine.js       # Exam taking: answer save to localStorage, timer, submit
│           ├── proctoring.js       # Camera access, tab-switch detection, flag posting
│           └── charts.js           # Analytics chart renderers (Chart.js)
│
├── migrations/
│   ├── mongo/
│   │   ├── 001_create_indexes.js   # MongoDB index creation scripts
│   │   ├── 002_seed_subject_tags.js
│   │   └── 003_seed_admin_user.js
│   └── postgres/
│       ├── 001_initial_schema.sql
│       └── 002_seed_plans.sql
│
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_exams.py
    ├── test_sessions.py
    └── test_results.py
```

---

## 4. ICA OAuth Integration

### `app/auth/ica_client.py`

```python
# What it does: wraps the ICA OAuth 2.0 + PKCE flow for Flask
# Functions:
#   generate_pkce() -> dict[code_verifier, code_challenge]
#   get_authorization_url(state, code_challenge) -> str
#   exchange_code(code, code_verifier) -> dict[access_token, refresh_token, id_token]
#   verify_token(access_token) -> dict (JWT payload: sub, email, name, ...)
#   refresh_access_token(refresh_token) -> dict[access_token]

import os, base64, hashlib, secrets
import requests
from flask import current_app

ICA_BASE_URL = os.environ.get("ICA_BASE_URL", "https://auth.iglobals.com")
CLIENT_ID    = os.environ.get("ICA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ICA_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("ICA_REDIRECT_URI")

def generate_pkce():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return {"code_verifier": verifier, "code_challenge": challenge}

def get_authorization_url(state: str, code_challenge: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{ICA_BASE_URL}/oauth/authorize?{query}"

def exchange_code(code: str, code_verifier: str) -> dict:
    resp = requests.post(f"{ICA_BASE_URL}/oauth/token", data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "code_verifier": code_verifier
    })
    resp.raise_for_status()
    return resp.json()

def verify_token(access_token: str) -> dict:
    # Calls ICA's userinfo endpoint to get the authenticated user profile
    resp = requests.get(f"{ICA_BASE_URL}/oauth/userinfo",
                        headers={"Authorization": f"Bearer {access_token}"})
    resp.raise_for_status()
    return resp.json()

def refresh_access_token(refresh_token: str) -> dict:
    resp = requests.post(f"{ICA_BASE_URL}/oauth/token", data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token
    })
    resp.raise_for_status()
    return resp.json()
```

### `app/auth/decorators.py`

```python
# @require_auth          — validates session token; injects g.current_user
# @require_role(*roles)  — checks g.current_user["role"] is in roles
# @require_plan(*plans)  — checks g.current_user["plan"]["type"] is in plans

from functools import wraps
from flask import session, redirect, url_for, jsonify, g, request
from app.users.service import get_user_by_ica_sub
from .ica_client import verify_token

def require_auth(redirect_on_fail=True):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = session.get("access_token")
            if not token:
                if redirect_on_fail:
                    return redirect(url_for("auth.login"))
                return jsonify({"error": "Unauthorized"}), 401
            try:
                ica_payload = verify_token(token)
                user = get_user_by_ica_sub(ica_payload["sub"])
                if not user:
                    return redirect(url_for("auth.login"))
                g.current_user = user
                g.ica_payload = ica_payload
            except Exception:
                session.clear()
                if redirect_on_fail:
                    return redirect(url_for("auth.login"))
                return jsonify({"error": "Token invalid"}), 401
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @require_auth()
        def decorated(*args, **kwargs):
            if g.current_user.get("role") not in roles:
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_plan(*plans):
    def decorator(f):
        @wraps(f)
        @require_auth()
        def decorated(*args, **kwargs):
            user_plan = g.current_user.get("plan", {}).get("type", "free")
            if user_plan not in plans:
                return jsonify({"error": "Upgrade required", "upgrade_url": "/pricing"}), 402
            return f(*args, **kwargs)
        return decorated
    return decorator
```

### `app/auth/routes.py`

```python
# GET  /auth/login     -> redirect to ICA authorize URL
# GET  /auth/callback  -> exchange code, store tokens, create/update user, redirect to dashboard
# POST /auth/logout    -> clear session, redirect to ICA logout

# login():
#   1. generate_pkce()
#   2. store code_verifier + random state in session
#   3. redirect to get_authorization_url(state, challenge)

# callback():
#   1. validate state matches session["oauth_state"]
#   2. exchange_code(request.args["code"], session["code_verifier"])
#   3. verify_token(access_token) -> ica_payload
#   4. users.service.get_or_create_user(ica_payload)
#   5. store access_token, refresh_token in session
#   6. redirect to appropriate dashboard based on role

# logout():
#   1. session.clear()
#   2. redirect to ICA logout URL
```

---

## 5. API Reference

### Conventions

All `/api/*` routes return JSON. Page-rendered routes return HTML templates.

**Standard success envelope:**
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 100
  }
}
```

**Standard error envelope:**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": { "field": "reason" }
  }
}
```

---

### Phase 1: Auth & User Onboarding

#### `GET /auth/login`
Redirects browser to ICA authorization URL.  
No request body. Session writes: `oauth_state`, `code_verifier`.

---

#### `GET /auth/callback`
| | |
|---|---|
| Query Params | `code`, `state` |
| Session Reads | `oauth_state`, `code_verifier` |
| Actions | Exchange code → get ICA profile → upsert user in MongoDB → set session |
| Redirect (success) | `/dashboard` (role-appropriate) |
| Redirect (failure) | `/auth/login?error=auth_failed` |

---

#### `POST /auth/logout`
Clears session. Redirects to ICA logout endpoint.

---

#### `GET /api/users/me`
**Auth:** `@require_auth`

**Success 200:**
```json
{
  "success": true,
  "data": {
    "_id": "...",
    "email": "...",
    "full_name": "...",
    "role": "student",
    "avatar_url": "...",
    "institution": "...",
    "programme": "...",
    "plan": { "type": "free", "expires_at": null },
    "limits": { "max_classes": 2, "ai_proctoring": false }
  }
}
```

---

#### `PATCH /api/users/me`
**Auth:** `@require_auth`

**Request Body:**
```json
{
  "full_name": "string",
  "institution": "string",
  "programme": "string",
  "phone": "string",
  "date_of_birth": "YYYY-MM-DD",
  "notification_preferences": { "email": true, "in_app": true }
}
```

**Success 200:** Updated user object.  
**Error 400:** Validation failure with field details.

---

#### `POST /api/users/me/avatar`
**Auth:** `@require_auth`  
**Content-Type:** `multipart/form-data`

**Request:** `file` (image, max 5MB, jpg/png/webp)

**Service:** `upload_avatar(file)` → uploads to Cloudinary → updates `users.avatar_url`

**Success 200:**
```json
{ "success": true, "data": { "avatar_url": "https://res.cloudinary.com/..." } }
```

**Error 400:** `{ "error": { "code": "INVALID_FILE", "message": "Only jpg, png, webp under 5MB" } }`

---

### Phase 2: Classes, Organizations & Membership

#### `POST /api/classes`
**Auth:** `@require_role("teacher")`

**Request Body:**
```json
{
  "name": "SS3 Mathematics Class",
  "description": "string",
  "subject_tags": ["tag_id_1"],
  "cover_image_url": "string (optional)"
}
```

**Service:** `create_class(teacher_id, data)` → checks `limits.max_classes` → inserts into `classes`

**Success 201:**
```json
{ "success": true, "data": { "_id": "...", "name": "...", "teachers": [...] } }
```

**Error 402:** `{ "error": { "code": "LIMIT_REACHED", "message": "Upgrade to create more classes" } }`

---

#### `GET /api/classes`
**Auth:** `@require_auth`  
**Query Params:** `page=1`, `per_page=20`, `search=string`

Returns classes where `g.current_user._id` is a teacher (owner/collaborator) or active student.

---

#### `GET /api/classes/:class_id`
**Auth:** `@require_auth` (must be member or teacher)

Returns full class document including student list (statuses), teacher list, pending requests.

---

#### `PATCH /api/classes/:class_id`
**Auth:** `@require_role("teacher")` + must be class owner

**Request Body:** Same fields as POST (partial allowed).

---

#### `DELETE /api/classes/:class_id`
**Auth:** `@require_role("teacher")` + must be class owner  
Soft-deletes: sets `is_active: false`.

---

#### `POST /api/classes/:class_id/invite`
**Auth:** `@require_role("teacher")` (must be teacher of class)

**Request Body:**
```json
{
  "emails": ["student1@email.com", "student2@email.com"]
}
```

**Service:** `invite_students_by_email(class_id, emails)`:
1. Look up users by email in MongoDB
2. For found users: add to `class.students` with `status: "pending"` + send notification
3. For not-found: optionally send email invite to register

**Success 200:**
```json
{
  "success": true,
  "data": {
    "invited": ["student1@email.com"],
    "not_found": ["student2@email.com"],
    "already_member": []
  }
}
```

---

#### `POST /api/classes/:class_id/invite/bulk`
**Auth:** `@require_role("teacher")`  
**Content-Type:** `multipart/form-data`

**Request:** `file` (.xlsx or .csv) — columns: `email`, `full_name` (optional)

**Service:** `bulk_invite_from_file(class_id, file)` → `parse_excel_or_csv(file)` → same flow as single invite

**Success 200:** Same as invite endpoint with counts per category.

---

#### `POST /api/classes/:class_id/invite/:invite_id/respond`
**Auth:** `@require_role("student")`

**Request Body:**
```json
{ "action": "accept | decline" }
```

**Service:** `respond_to_invite(class_id, student_id, action)`:
- Updates `class.students[].status`
- Sends notification to class teachers
- Checks `limits.max_students_per_class` and `limits.max_total_students` before accepting

**Error 409:** `{ "error": { "code": "CLASS_FULL", "message": "..." } }`

---

#### `POST /api/classes/:class_id/join-request`
**Auth:** `@require_role("student")`

**Service:** `send_join_request(class_id, student_id)`:
- Checks `join_requests[student_id].attempt_count < max_attempts (3)`
- Adds/increments join request
- Sends notification to class teachers

**Error 429:** `{ "error": { "code": "MAX_ATTEMPTS_REACHED", "message": "Max join requests sent" } }`

---

#### `POST /api/classes/:class_id/join-request/:request_id/respond`
**Auth:** `@require_role("teacher")`

**Request Body:** `{ "action": "accept | reject" }`

**Service:** `respond_to_join_request(class_id, student_id, action)` → updates request status → notifies student

---

#### `POST /api/classes/:class_id/register-org`
**Auth:** `@require_role("teacher")`

**Request Body:** `{ "organization_id": "string" }`

**Service:** `request_org_registration(class_id, org_id, teacher_id)`:
- Class must have `organization_status: "none"`
- Adds to `org.pending_teacher_requests`
- Sends notification to org admin

---

#### `POST /api/organizations/:org_id/class-requests/:request_id/respond`
**Auth:** `@require_role("org_admin")` (must admin of org)

**Request Body:** `{ "action": "accept | reject" }`

**Service:** `respond_to_class_request(org_id, class_id, action)`:
- Updates `org.pending_teacher_requests[].status`
- Updates `class.organization_id` and `class.organization_status`
- Notifies teacher

---

#### `POST /api/organizations`
**Auth:** `@require_auth`

**Request Body:**
```json
{
  "name": "Sunrise Tutorial Centre",
  "slug": "sunrise-tc",
  "description": "string",
  "website": "string",
  "contact_email": "string"
}
```

**Service:** `create_organization(user_id, data)` → sets `admin_user_id`, updates user role to `org_admin`

---

#### `POST /api/organizations/:org_id/logo`
**Auth:** `@require_role("org_admin")`  
**Content-Type:** `multipart/form-data`  
**Request:** `file` (image)  
**Service:** uploads to Cloudinary, updates `org.logo_url`

---

### Phase 3: Exam Creation & Question Management

#### `POST /api/question-banks`
**Auth:** `@require_role("teacher", "platform_admin")`

**Request Body:**
```json
{
  "name": "JUPEB Mathematics Bank",
  "description": "string",
  "subject_tag_id": "ObjectId",
  "visibility": "private | organization | public"
}
```

---

#### `POST /api/question-banks/:bank_id/questions`
**Auth:** `@require_role("teacher", "platform_admin")` + must own bank

**Request Body:**
```json
{
  "text": "What is the derivative of x²?",
  "image_url": null,
  "type": "mcq",
  "difficulty": "medium",
  "options": [
    { "key": "A", "text": "2x" },
    { "key": "B", "text": "x" },
    { "key": "C", "text": "x²" },
    { "key": "D", "text": "2" }
  ],
  "correct_answer": "A",
  "explanation": "Power rule: d/dx(xⁿ) = nxⁿ⁻¹",
  "marks": 1,
  "tags": ["calculus", "differentiation"]
}
```

**Service:** `add_question(bank_id, question_data)` → pushes into `question_banks.questions[]` → increments `total_questions`

---

#### `POST /api/question-banks/:bank_id/questions/bulk`
**Auth:** `@require_role("teacher", "platform_admin")`  
**Content-Type:** `multipart/form-data`

**Request:** `file` (.json, .csv, or .xlsx), `format` ("json" | "csv" | "excel")

**JSON format spec:**
```json
[
  {
    "text": "Question text",
    "type": "mcq",
    "options": { "A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D" },
    "correct": "A",
    "difficulty": "easy",
    "explanation": "optional",
    "marks": 1
  }
]
```

**CSV format spec (columns):**
`question_text, type, option_a, option_b, option_c, option_d, correct_answer, difficulty, marks, explanation`

**Service:** `parse_and_bulk_add(bank_id, file, format)` → `file_parser.parse_*(file)` → batch insert

**Success 200:**
```json
{ "success": true, "data": { "added": 45, "skipped": 2, "errors": [] } }
```

---

#### `POST /api/exams`
**Auth:** `@require_role("teacher", "platform_admin")`

**Request Body:**
```json
{
  "title": "JUPEB Chemistry Mock — Session 1",
  "description": "string",
  "exam_type": "public | private | platform_standard",
  "visibility": {
    "type": "public",
    "class_ids": [],
    "student_emails": []
  },
  "subject_tag_id": "ObjectId",
  "instructions": "string",
  "settings": {
    "duration_minutes": 60,
    "allow_retake": true,
    "max_attempts": 5,
    "randomize_questions": true,
    "randomize_options": false,
    "show_result_immediately": true,
    "pass_mark_percent": 50,
    "question_per_page": 1,
    "ai_proctoring_enabled": false,
    "allow_review_before_submit": true,
    "auto_submit_on_timeout": true
  },
  "schedule": {
    "available_from": "2025-07-01T08:00:00Z",
    "available_until": "2025-12-31T23:59:59Z"
  },
  "platform_tags": ["JUPEB"],
  "question_ids": [
    { "bank_id": "ObjectId", "question_id": "ObjectId", "order": 1, "marks": 1 }
  ]
}
```

**Service:** `create_exam(teacher_id, data)`:
- Validates question_ids exist in given banks
- Checks `ai_proctoring_enabled` against user plan
- Sets `status: "draft"`, `total_questions`, `total_marks`

**Success 201:** Full exam document.

---

#### `POST /api/exams/:exam_id/publish`
**Auth:** `@require_role("teacher", "platform_admin")`

Sets `status: "published"`, `schedule.is_published: true`.  
For `platform_standard` exams: admin-only, or sets `status: "pending_approval"` if teacher.

**Service:** `publish_exam(exam_id, user)`:
- Validates exam has ≥1 question
- Sends notification to invited students/classes

---

#### `GET /api/exams`
**Auth:** `@require_auth`  
**Query Params:** `type=public|private|mine`, `tag=ObjectId`, `search=string`, `page=1`, `per_page=20`

For students: returns public exams + private exams they are eligible for.  
For teachers: returns exams they created.  
For admins: returns all.

---

#### `GET /api/exams/:exam_id`
**Auth:** `@require_auth` (with eligibility check for private)

---

#### `PATCH /api/exams/:exam_id`
**Auth:** `@require_role("teacher", "platform_admin")` + must own  
Only allowed when `status: "draft"`.

---

#### `DELETE /api/exams/:exam_id`
**Auth:** `@require_role("teacher", "platform_admin")` + must own  
Sets `status: "archived"`.

---

### Phase 4: Exam Taking (CBT Engine)

#### `POST /api/sessions/start`
**Auth:** `@require_role("student")`

**Request Body:**
```json
{ "exam_id": "ObjectId" }
```

**Service:** `start_session(student_id, exam_id)`:
1. Check exam `status == "published"` and within schedule window
2. Check student eligibility (public, or in class/email list)
3. Count previous attempts — enforce `max_attempts`
4. Generate question order (randomise if enabled)
5. Insert `exam_sessions` document with `status: "in_progress"`
6. Return session with first question

**Success 201:**
```json
{
  "success": true,
  "data": {
    "session_id": "ObjectId",
    "exam_id": "ObjectId",
    "attempt_number": 1,
    "total_questions": 40,
    "duration_seconds": 3600,
    "current_question": {
      "index": 1,
      "question_id": "ObjectId",
      "text": "...",
      "type": "mcq",
      "options": [{ "key": "A", "text": "..." }],
      "marks": 1,
      "image_url": null
    }
  }
}
```

Note: `correct_answer` is **never** returned to the client during an active session.

**Error 403:** `{ "error": { "code": "NOT_ELIGIBLE", "message": "..." } }`  
**Error 429:** `{ "error": { "code": "MAX_ATTEMPTS_REACHED", "message": "..." } }`

---

#### `GET /api/sessions/:session_id/question/:index`
**Auth:** `@require_role("student")` + must own session  
**Path Params:** `index` (1-based question number)

**Service:** `get_question(session_id, index)` → returns question at position without answer

**Success 200:**
```json
{
  "success": true,
  "data": {
    "index": 3,
    "total": 40,
    "question_id": "ObjectId",
    "text": "...",
    "type": "mcq",
    "options": [...],
    "image_url": null,
    "marks": 1,
    "flagged": false,
    "answered": true,
    "selected_answer": "B"
  }
}
```

---

#### `POST /api/sessions/:session_id/answer`
**Auth:** `@require_role("student")` + must own session

**Request Body:**
```json
{
  "question_id": "ObjectId",
  "selected_option": "A",
  "time_spent_seconds": 45,
  "flagged": false
}
```

**Service:** `save_answer(session_id, answer_data)`:
- Upserts answer in `exam_sessions.answers[]`
- Updates `time_remaining_seconds`

**Success 200:** `{ "success": true, "data": { "saved": true } }`

---

#### `GET /api/sessions/:session_id/status`
**Auth:** `@require_role("student")` + must own session

Returns session status for tab-reconnect (answer resume).

**Success 200:**
```json
{
  "success": true,
  "data": {
    "session_id": "...",
    "status": "in_progress",
    "time_remaining_seconds": 2100,
    "answered_count": 15,
    "flagged_count": 2,
    "total_questions": 40,
    "answered_question_ids": ["...", "..."]
  }
}
```

---

#### `POST /api/sessions/:session_id/submit`
**Auth:** `@require_role("student")` + must own session

**Request Body:** (optional, for any last-minute local answers to sync)
```json
{
  "final_answers": [
    { "question_id": "ObjectId", "selected_option": "C" }
  ]
}
```

**Service:** `submit_session(session_id)`:
1. Set `status: "submitted"`, `submitted_at: now`
2. Call `grader.grade_session(session_id)` → compute score
3. Insert into PostgreSQL `exam_scores`
4. Update `exams.statistics`
5. Trigger ranking refresh job
6. Return immediate result if `show_result_immediately: true`

**Success 200:**
```json
{
  "success": true,
  "data": {
    "session_id": "...",
    "score": 32,
    "total_marks": 40,
    "score_percent": 80,
    "passed": true,
    "time_spent_seconds": 3150,
    "correct_count": 32,
    "incorrect_count": 7,
    "unanswered_count": 1,
    "result_url": "/results/session_id"
  }
}
```

---

#### `POST /api/sessions/:session_id/proctor-flag`
**Auth:** `@require_role("student")` + must own session  
**Note:** Called from client-side `proctoring.js` automatically

**Request Body:**
```json
{
  "type": "tab_switch | camera_off | screenshot_attempt | face_not_detected | multiple_faces",
  "screenshot_url": "string (Cloudinary URL, optional)"
}
```

**Service:** Appends to `exam_sessions.proctoring_flags[]`. Teachers/admins can review these.

---

### Phase 5: Results, Analytics & Rankings

#### `GET /api/results/:session_id`
**Auth:** `@require_auth` (student must own, teacher must teach class, admin)

**Success 200:**
```json
{
  "success": true,
  "data": {
    "session_id": "...",
    "exam_title": "...",
    "attempt_number": 1,
    "score": 32,
    "total_marks": 40,
    "score_percent": 80,
    "passed": true,
    "time_spent_seconds": 3150,
    "correct_count": 32,
    "incorrect_count": 7,
    "unanswered_count": 1,
    "submitted_at": "ISO8601",
    "question_review": [
      {
        "question_id": "...",
        "text": "...",
        "student_answer": "B",
        "correct_answer": "A",
        "is_correct": false,
        "explanation": "...",
        "marks_earned": 0,
        "marks_possible": 1
      }
    ],
    "proctoring_flags": [...],
    "subject_tag": { "name": "Mathematics" }
  }
}
```

---

#### `GET /api/analytics/me`
**Auth:** `@require_role("student")`  
**Query Params:** `period=30d|90d|all`, `tag_id=ObjectId (optional)`

**Service:** `aggregate_student_performance(student_id, period, tag_id)`:
- Queries PostgreSQL `exam_scores` for the student
- Groups by `subject_tag_name`, computes avg, trend
- Computes readiness score

**Success 200:**
```json
{
  "success": true,
  "data": {
    "overall_avg_percent": 72.5,
    "total_exams_taken": 14,
    "total_passed": 11,
    "readiness_score": 74,
    "readiness_label": "Good",
    "subject_breakdown": [
      {
        "subject": "Mathematics",
        "avg_percent": 80,
        "exams_taken": 5,
        "trend": "improving"
      }
    ],
    "recent_exams": [
      {
        "exam_title": "...",
        "score_percent": 78,
        "submitted_at": "...",
        "subject": "Physics"
      }
    ],
    "performance_over_time": [
      { "date": "2025-06-01", "score_percent": 65 },
      { "date": "2025-06-08", "score_percent": 72 }
    ]
  }
}
```

---

#### `GET /api/analytics/class/:class_id`
**Auth:** `@require_role("teacher")` (must be teacher of class)  
**Query Params:** `exam_id=ObjectId (optional)`

**Service:** `aggregate_class_performance(class_id, exam_id)`:
- Gets all student_ids in class
- Queries PostgreSQL for their scores

**Success 200:** Aggregated stats per student + subject breakdown.

---

#### `GET /api/analytics/org/:org_id`
**Auth:** `@require_role("org_admin", "platform_admin")`

**Service:** `aggregate_org_performance(org_id)` — requires advanced_analytics plan feature.

---

#### `GET /api/rankings/exam/:exam_id`
**Auth:** `@require_auth`  
**Query Params:** `period=all_time|weekly|monthly`, `scope=national|subject|institutional`, `page=1`, `per_page=50`

**Service:** `get_rankings(exam_id, period, scope)` — queries `national_rankings` table

**Success 200:**
```json
{
  "success": true,
  "data": {
    "exam_title": "...",
    "period": "all_time",
    "scope": "national",
    "my_rank": 142,
    "my_score_percent": 80,
    "rankings": [
      {
        "rank": 1,
        "student_name": "Adaeze O.",
        "score_percent": 98,
        "attempt_count": 2
      }
    ]
  },
  "meta": { "page": 1, "per_page": 50, "total": 5024 }
}
```

---

### Phase 6: Admin & Platform Management

#### `GET /api/admin/stats`
**Auth:** `@require_role("platform_admin")`

**Success 200:**
```json
{
  "success": true,
  "data": {
    "total_users": 12400,
    "total_students": 11800,
    "total_teachers": 540,
    "total_orgs": 62,
    "total_exams": 3200,
    "total_sessions_today": 840,
    "active_sessions_now": 23
  }
}
```

---

#### `GET /api/admin/users`
**Auth:** `@require_role("platform_admin")`  
**Query Params:** `role=student|teacher|org_admin`, `search=string`, `page=1`

---

#### `PATCH /api/admin/users/:user_id/suspend`
**Auth:** `@require_role("platform_admin")`

**Request Body:** `{ "reason": "string" }`  
Sets `is_active: false`, sends notification to user.

---

#### `GET /api/admin/exams/pending`
**Auth:** `@require_role("platform_admin")`  
Returns exams with `status: "pending_approval"` (platform_standard type, submitted by teachers)

---

#### `POST /api/admin/exams/:exam_id/approve`
**Auth:** `@require_role("platform_admin")`  
Sets `status: "published"`.

---

#### `POST /api/admin/exams/:exam_id/reject`
**Auth:** `@require_role("platform_admin")`

**Request Body:** `{ "reason": "string" }`  
Sets `status: "draft"`, notifies teacher.

---

#### `GET /api/admin/question-banks`
**Auth:** `@require_role("platform_admin")`  
Lists all question banks with visibility controls.

---

### Phase 7: Payments & Subscriptions

#### `GET /api/pricing`
**Auth:** public

Returns all active plans from PostgreSQL `subscription_plans`.

---

#### `POST /api/payments/initiate`
**Auth:** `@require_auth`

**Request Body:**
```json
{
  "plan_id": 2,
  "billing_type": "monthly | annual",
  "target_type": "user | organization",
  "target_id": "string (org ObjectId if org)"
}
```

**Service:** `initiate_payment(user, data)`:
- Creates `payments` row with `status: "pending"`
- Calls Flutterwave API to get payment link
- Returns redirect URL

**Success 200:**
```json
{
  "success": true,
  "data": {
    "payment_id": 123,
    "payment_url": "https://checkout.flutterwave.com/v3/hosted/pay/...",
    "expires_at": "ISO8601"
  }
}
```

---

#### `POST /api/payments/webhook`
**Auth:** Verified via Flutterwave signature header `verif-hash`

**Actions:** `handle_flutterwave_webhook()`:
1. Validate signature
2. Find payment by `provider_ref`
3. Update `payments.status = "success"`
4. Call `apply_plan(user_id, plan_id)` → updates `users.plan` and `users.limits`
5. Send confirmation notification

---

#### `GET /api/payments/history`
**Auth:** `@require_auth`  
Returns paginated list of user's payment records.

---

### Notifications

#### `GET /api/notifications`
**Auth:** `@require_auth`  
**Query Params:** `is_read=true|false`, `page=1`

---

#### `POST /api/notifications/:notif_id/read`
**Auth:** `@require_auth` + must be recipient  
Sets `is_read: true`.

---

#### `POST /api/notifications/read-all`
**Auth:** `@require_auth`  
Marks all unread notifications for user as read.

---

#### `GET /api/notifications/stream`
**Auth:** `@require_auth`  
**Response:** `text/event-stream` (SSE)

Server-Sent Events stream for real-time notification delivery. Client subscribes on page load; server pushes new notification events.

```
event: notification
data: {"type": "class_invite", "title": "...", "body": "..."}

event: heartbeat
data: {}
```

---

### Subject Tags

#### `GET /api/tags`
**Auth:** public

Returns all subject tags. Used to populate dropdowns in exam creation and profile setup.

---

### File Uploads (Cloudinary Proxy)

#### `POST /api/uploads/image`
**Auth:** `@require_auth`  
**Content-Type:** `multipart/form-data`  
**Request:** `file` (image), `purpose` ("avatar" | "exam_cover" | "org_logo" | "question_image")

**Service:** `cloudinary_client.upload_image(file, folder=purpose)` → returns Cloudinary URL

**Success 200:** `{ "success": true, "data": { "url": "https://res.cloudinary.com/..." } }`

---

## 6. Build Phases & Execution Order

### Phase 0 — Environment & Scaffolding (Day 1–2)

**Goal:** Working Flask app boots, connects to both DBs, ICA OAuth login works end-to-end.

Tasks:
1. Clone ExamZen codebase, rename to `itest/`, update branding tokens (purple `#6B21A8`, gold `#F59E0B`)
2. Set up `config.py` with `DevelopmentConfig` / `ProductionConfig`
3. Initialize `app/__init__.py` with `create_app()` factory
4. Register `extensions.py`: PyMongo, SQLAlchemy (for Postgres), Flask-Limiter
5. Create `.env.example` with all required variables (see Section 7)
6. Run `migrations/postgres/001_initial_schema.sql` against Neon
7. Run `migrations/mongo/001_create_indexes.js` + `002_seed_subject_tags.js`
8. Implement `app/auth/` fully: ICA client, PKCE flow, decorators, routes
9. Verify: `/auth/login` → ICA → callback → session set → `/dashboard` redirect
10. Update PWA manifest, `sw.js`, icons

---

### Phase 1 — Users & Profiles (Day 3–4)

**Goal:** Authenticated users can view and edit their profile, upload avatars.

Tasks:
1. `app/users/service.py`: `get_or_create_user(ica_payload)`, `update_profile()`, `get_user_by_ica_sub()`
2. `app/users/routes.py`: `GET /api/users/me`, `PATCH /api/users/me`, `POST /api/users/me/avatar`
3. `app/uploads/cloudinary_client.py`: `upload_image()`, `delete_image()`
4. `app/uploads/routes.py`: `/api/uploads/image`
5. `app/subject_tags/routes.py`: `GET /api/tags`
6. Dashboard templates: student, teacher, org_admin (reuse ExamZen layouts, update nav)

---

### Phase 2 — Classes & Organizations (Day 5–8)

**Goal:** Teachers can create classes, invite students; orgs can accept class registrations; notifications work.

Tasks:
1. `app/classes/` full implementation (service + routes)
2. `app/organizations/` full implementation
3. `app/notifications/service.py`: `send_notification()`, `get_unread_count()`
4. `app/notifications/routes.py`: list, mark read, SSE stream
5. `app/static/js/app.js`: SSE connection, toast on new notification
6. Bulk invite (CSV/Excel parser): `app/utils/file_parser.py`

---

### Phase 3 — Question Banks & Exam Creation (Day 9–13)

**Goal:** Teachers can create question banks, add questions manually or via file upload, and build exams.

Tasks:
1. `app/question_banks/` full implementation
2. `app/utils/file_parser.py`: `parse_json_questions()`, `parse_csv_questions()`, `parse_excel_questions()`
3. `app/exams/question_import.py`: orchestrates parse + validate + insert
4. `app/exams/` full implementation (service + routes)
5. Exam creation UI: paginated question selector, settings panel, schedule picker, visibility controls
6. Seed platform standard exam questions (JUPEB, IJMB samples) via admin bulk upload

---

### Phase 4 — CBT Engine (Day 14–19)

**Goal:** Students can start, take, and submit exams. Answers persist to localStorage and sync to DB.

Tasks:
1. `app/sessions/service.py`: start, get_question, save_answer, submit
2. `app/sessions/grader.py`: auto-grade MCQ/True-False/Numerical; mark essays for manual review
3. `app/sessions/routes.py`: all session endpoints
4. `app/static/js/cbt_engine.js`:
   - Timer countdown (syncs with `time_remaining_seconds` from server)
   - localStorage answer buffer (key: `itest_session_{session_id}`)
   - Periodic sync (every 30s or on answer change) to `POST /api/sessions/:id/answer`
   - Tab/window visibility API: detect tab switch, post proctor flag
   - Submit: flush localStorage → POST `/api/sessions/:id/submit`
5. `app/static/js/proctoring.js`:
   - Camera access via `getUserMedia`
   - Face detection (basic: check video stream active)
   - Screenshot attempt detection via `visibilitychange` / `keydown` (PrintScreen)
   - All flags posted to `/api/sessions/:id/proctor-flag`
6. Exam taking template: modal question layout, progress tracker, flag button, timer bar

---

### Phase 5 — Results & Analytics (Day 20–24)

**Goal:** Students see instant results; analytics dashboard with subject breakdown and trend charts.

Tasks:
1. `app/results/service.py`: `get_result()`, question review builder
2. `app/results/routes.py`: `GET /api/results/:session_id`
3. `app/analytics/service.py`: student performance aggregation (Postgres queries)
4. `app/analytics/routes.py`: me, class, org endpoints
5. `app/rankings/service.py`: `compute_rankings()`, `get_student_rank()`
6. `app/rankings/scheduler.py`: APScheduler weekly/monthly rebuild
7. `app/static/js/charts.js`: Chart.js line charts (score over time), bar (subject avg), doughnut (pass rate)
8. Result detail template: score card, question-by-question review, flag summary
9. Analytics dashboard template: charts panel, subject cards, recent exams table

---

### Phase 6 — Admin Panel (Day 25–27)

**Goal:** Platform admins can manage users, orgs, approve/reject standard exams, view platform stats.

Tasks:
1. `app/admin/service.py`: `platform_stats()`, `suspend_user()`, `approve_exam()`, `reject_exam()`
2. `app/admin/routes.py`: all admin endpoints
3. Admin dashboard template: stats cards, user table, pending exams queue, org overview

---

### Phase 7 — Payments (Day 28–30)

**Goal:** Users can upgrade their plan; webhooks correctly apply limits.

Tasks:
1. `app/payments/service.py`: `initiate_payment()`, `verify_payment()`, `apply_plan()`
2. `app/payments/webhook.py`: signature validation, status update, plan application
3. `app/payments/routes.py`: initiate, webhook, history
4. PostgreSQL seed: `002_seed_plans.sql` with free/basic/pro/enterprise plan definitions
5. Pricing page template (public)
6. Post-upgrade: user `limits` document updated in MongoDB

---

## 7. Environment & Configuration

### `.env.example`

```env
# Flask
FLASK_ENV=development
FLASK_SECRET_KEY=your-secret-key-here
FLASK_APP=run.py

# ICA OAuth
ICA_BASE_URL=https://auth.iglobals.com
ICA_CLIENT_ID=itest-app
ICA_CLIENT_SECRET=your-ica-client-secret
ICA_REDIRECT_URI=http://localhost:5000/auth/callback

# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/itest?retryWrites=true
MONGODB_DB_NAME=itest

# PostgreSQL (Neon)
POSTGRES_URI=postgresql://user:pass@neon.host/itest

# Cloudinary
CLOUDINARY_CLOUD_NAME=your-cloud
CLOUDINARY_API_KEY=your-key
CLOUDINARY_API_SECRET=your-secret

# Flutterwave
FLUTTERWAVE_SECRET_KEY=FLWSECK_TEST-...
FLUTTERWAVE_PUBLIC_KEY=FLWPUBK_TEST-...
FLUTTERWAVE_WEBHOOK_HASH=your-webhook-verif-hash

# Email (optional SMTP)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=noreply@iglobals.com
MAIL_PASSWORD=...

# Pusher/SSE (if using Pusher for prod)
PUSHER_APP_ID=
PUSHER_KEY=
PUSHER_SECRET=
PUSHER_CLUSTER=

# App
MAX_CONTENT_LENGTH_MB=10
ALLOWED_IMAGE_EXTENSIONS=jpg,jpeg,png,webp
```

### `config.py`

```python
import os

class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
    MONGO_URI = os.environ.get("MONGODB_URI")
    SQLALCHEMY_DATABASE_URI = os.environ.get("POSTGRES_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 10)) * 1024 * 1024
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}
```

---

## 8. PWA Configuration

### `app/static/manifest.json`

```json
{
  "name": "iTEST by iGlobals",
  "short_name": "iTEST",
  "description": "Take and create examinations anywhere",
  "start_url": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#1A0533",
  "theme_color": "#6B21A8",
  "icons": [
    { "src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/static/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "categories": ["education"],
  "screenshots": [
    { "src": "/static/screenshots/desktop.png", "sizes": "1280x720", "type": "image/png", "form_factor": "wide" },
    { "src": "/static/screenshots/mobile.png", "sizes": "390x844", "type": "image/png", "form_factor": "narrow" }
  ]
}
```

### `app/static/sw.js` (Service Worker Strategy)

```javascript
const CACHE_NAME = "itest-v1";
const STATIC_ASSETS = ["/static/css/main.css", "/static/js/app.js", "/static/manifest.json", "/offline"];

// Install: cache static assets
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)));
});

// Fetch: network-first for API, cache-first for static
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) {
    // Network first; fall back to cached response if offline
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
  } else {
    // Cache first for static assets
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request))
    );
  }
});
```

### `base.html` — PWA registration snippet

```html
<!-- In <head> -->
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#6B21A8">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="/static/icons/icon-192.png">

<!-- Before </body> -->
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js');
  }
</script>
```

---

## Appendix A: MongoDB Index Creation Script

```javascript
// migrations/mongo/001_create_indexes.js
// Run with: mongosh <connection-string> --file 001_create_indexes.js

const db = connect(process.env.MONGODB_URI);

// users
db.users.createIndex({ "ica_sub": 1 }, { unique: true });
db.users.createIndex({ "email": 1 }, { unique: true });
db.users.createIndex({ "role": 1 });

// classes
db.classes.createIndex({ "teachers.user_id": 1 });
db.classes.createIndex({ "students.user_id": 1 });
db.classes.createIndex({ "organization_id": 1 });

// exams
db.exams.createIndex({ "created_by": 1 });
db.exams.createIndex({ "exam_type": 1, "status": 1 });
db.exams.createIndex({ "subject_tag_id": 1 });
db.exams.createIndex({ "visibility.class_ids": 1 });
db.exams.createIndex({ "platform_tags": 1 });

// exam_sessions
db.exam_sessions.createIndex({ "student_id": 1, "exam_id": 1 });
db.exam_sessions.createIndex({ "exam_id": 1, "status": 1 });

// question_banks
db.question_banks.createIndex({ "owner_id": 1 });
db.question_banks.createIndex({ "subject_tag_id": 1, "visibility": 1 });

// notifications
db.notifications.createIndex({ "recipient_id": 1, "is_read": 1, "created_at": -1 });

print("✅ Indexes created.");
```

---

## Appendix B: Plan Limits Seed

```sql
-- migrations/postgres/002_seed_plans.sql

INSERT INTO subscription_plans (name, price_ngn, billing, limits, features) VALUES
('free', 0, 'monthly', 
  '{"max_classes": 2, "max_students_per_class": 30, "max_total_students": 60, "ai_proctoring": false, "advanced_analytics": false}',
  '{"public_exams": true, "private_exams": true, "bulk_invite": false, "export_reports": false}'
),
('basic', 5000, 'monthly',
  '{"max_classes": 5, "max_students_per_class": 60, "max_total_students": 300, "ai_proctoring": false, "advanced_analytics": false}',
  '{"public_exams": true, "private_exams": true, "bulk_invite": true, "export_reports": true}'
),
('pro', 15000, 'monthly',
  '{"max_classes": 20, "max_students_per_class": 200, "max_total_students": 4000, "ai_proctoring": true, "advanced_analytics": true}',
  '{"public_exams": true, "private_exams": true, "bulk_invite": true, "export_reports": true}'
),
('enterprise', 50000, 'monthly',
  '{"max_classes": 999, "max_students_per_class": 999, "max_total_students": 999999, "ai_proctoring": true, "advanced_analytics": true}',
  '{"public_exams": true, "private_exams": true, "bulk_invite": true, "export_reports": true}'
);
```

---

## Appendix C: Key Utility Functions

### `app/utils/response.py`
```python
from flask import jsonify

def success_response(data=None, status=200, meta=None):
    body = {"success": True, "data": data}
    if meta:
        body["meta"] = meta
    return jsonify(body), status

def error_response(code, message, status=400, details=None):
    body = {"success": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status
```

### `app/utils/mongo.py`
```python
from bson import ObjectId
from flask import g
from app.extensions import mongo

def get_collection(name: str):
    return mongo.db[name]

def build_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise ValueError(f"Invalid ObjectId: {id_str}")

def paginate_cursor(cursor, page: int, per_page: int) -> dict:
    total = cursor.count()
    items = list(cursor.skip((page - 1) * per_page).limit(per_page))
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page
    }
```

### `app/sessions/grader.py`
```python
# grade_session(session_id: str) -> dict
#   Accepts: session_id (string, MongoDB ObjectId)
#   Reads:   exam_sessions (answers[], exam.questions[])
#   Computes: score, correct_count, incorrect_count, unanswered_count
#   Writes:  exam_scores (PostgreSQL INSERT)
#   Returns: dict with score breakdown

# For each answer in session.answers:
#   - match to question via question_id
#   - compare selected_option to question.correct_answer
#   - MCQ/True-False/Numerical: exact match
#   - Short answer: lowercased trim match
#   - Essay: marks = 0, flagged for manual review
# Total score = sum of marks_earned across all questions
# Insert into PostgreSQL exam_scores table
```
