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
