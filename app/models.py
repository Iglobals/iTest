from app.extensions import db
from datetime import datetime

class ExamScore(db.Model):
    __tablename__ = 'exam_scores'
    
    id = db.Column(db.BigInteger, primary_key=True)
    session_id = db.Column(db.Text, nullable=False, unique=True)
    exam_id = db.Column(db.Text, nullable=False, index=True)
    student_id = db.Column(db.Text, nullable=False, index=True)
    organization_id = db.Column(db.Text, index=True)
    class_id = db.Column(db.Text)
    subject_tag_id = db.Column(db.Text, index=True)
    subject_tag_name = db.Column(db.Text)
    exam_title = db.Column(db.Text, nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    score = db.Column(db.Numeric(10, 2), nullable=False)
    total_marks = db.Column(db.Numeric(10, 2), nullable=False)
    score_percent = db.Column(db.Numeric(5, 2), nullable=False)
    passed = db.Column(db.Boolean, nullable=False)
    time_spent_secs = db.Column(db.Integer)
    total_questions = db.Column(db.Integer)
    correct_count = db.Column(db.Integer)
    incorrect_count = db.Column(db.Integer)
    unanswered_count = db.Column(db.Integer)
    is_graded = db.Column(db.Boolean, default=False)
    results_published = db.Column(db.Boolean, default=False)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

class NationalRanking(db.Model):
    __tablename__ = 'national_rankings'
    
    id = db.Column(db.BigInteger, primary_key=True)
    exam_id = db.Column(db.Text, nullable=False, index=True)
    student_id = db.Column(db.Text, nullable=False, index=True)
    student_name = db.Column(db.Text, nullable=False)
    best_score_pct = db.Column(db.Numeric(5, 2), nullable=False)
    attempt_count = db.Column(db.Integer, nullable=False, default=1)
    national_rank = db.Column(db.Integer)
    subject_rank = db.Column(db.Integer)
    period = db.Column(db.Text, nullable=False)
    period_label = db.Column(db.Text)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False, unique=True)
    price_ngn = db.Column(db.Numeric(12, 2), nullable=False)
    price_usd = db.Column(db.Numeric(12, 2))
    billing = db.Column(db.Text, nullable=False)
    limits = db.Column(db.JSON, nullable=False)
    features = db.Column(db.JSON, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.Text, nullable=False, index=True)
    organization_id = db.Column(db.Text, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'))
    provider = db.Column(db.Text, nullable=False)
    provider_ref = db.Column(db.Text, nullable=False, unique=True)
    amount_ngn = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.Text, default='NGN')
    status = db.Column(db.Text, nullable=False)
    payment_metadata = db.Column(db.JSON)
    paid_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
