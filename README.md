# iTest

Exam creation, taking, grading, and AI proctoring app. Flask + MongoDB (exam/question/session content) + PostgreSQL (`ExamScore`/`Payment` ledger, via SQLAlchemy). Authentication is via [iGlobals Central Auth (ICA)](../Iglobals-CAuth), not a local password.

## Running locally

1. **Databases**: you need a Postgres instance (`POSTGRES_URI`) and a MongoDB instance (`MONGODB_URI`) reachable - either local installs or free-tier hosted ones (Neon for Postgres, MongoDB Atlas both work fine for dev). Redis (`REDIS_URL`) is used for rate limiting.
2. **ICA**: get [Iglobals-CAuth](../Iglobals-CAuth) running first (see its own `web/README.md`), then register iTest as a client there - see `CLIENT_REGISTRATION_GUIDE.md` in that repo. You'll get a `client_id`/`client_secret` to put in this app's `.env`.
3. **Copy env file**: `cp .env.example .env` and fill in `POSTGRES_URI`, `MONGODB_URI`, `REDIS_URL`, and the `ICA_*` vars from step 2. `.env.example` has inline comments on every var, including where each one is actually consumed in the code - Paystack, `PROCTOR_API_*` (the sibling `anticheat-system-roboflow` service), and Cloudinary vars are only needed if you're testing those specific features.
4. **Install and run**:
   ```bash
   pip install -r requirements.txt
   python run.py
   ```
5. Open [http://localhost:5000](http://localhost:5000). New accounts are created automatically on first ICA login - there's no local signup form or password.

Note: iGlobal_edu also defaults to port 5000. If you need both running locally against the same ICA instance at once, change one app's port (and its registered `redirect_uri` in ICA to match).

## Payments

Paystack webhooks are **not** sent to iTest directly - they go through ICA's centralized relay (one shared Paystack account across the whole iGlobals ecosystem). See `app/billing/routes.py` for the receiving/dispatch logic, and `Iglobals-CAuth/CLIENT_REGISTRATION_GUIDE.md` for how to register this app's webhook URL and get its `ICA_WEBHOOK_RELAY_SECRET`.

## AI Proctoring

`PROCTOR_API_BASE_URL`/`PROCTOR_API_KEY` point at the sibling `anticheat-system-roboflow` service. Run it locally with `uvicorn app.main:app --reload` (default `http://localhost:8000`) while testing proctored exams.
