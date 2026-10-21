"""Shared exam-eligibility rules.

Used both by the dashboard listing queries (what a student sees) and by the
session/take routes (what a student is actually allowed to do) so the two
can't silently drift apart - visibility/scheduling used to only be enforced
in the former.
"""
from datetime import datetime
from app.utils.mongo import get_collection


def parse_dt(value):
    """Best-effort parse of a schedule datetime that may be a real datetime,
    an ISO-ish string (e.g. from a <input type="datetime-local">), or empty."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def is_exam_open_now(exam, now=None):
    """Whether the exam's availability window (if any) currently includes `now`."""
    now = now or datetime.utcnow()
    schedule = exam.get("schedule", {}) or {}
    available_from = parse_dt(schedule.get("available_from"))
    available_until = parse_dt(schedule.get("available_until"))
    if available_from and now < available_from:
        return False
    if available_until and now > available_until:
        return False
    return True


def can_student_access_exam(exam, user_email, class_ids):
    """Whether this student is granted access via public/platform_standard type,
    class membership, or a direct email grant - and isn't explicitly excluded."""
    visibility = exam.get("visibility", {}) or {}
    # Emails compare case-insensitively: e-library grants are stored
    # lowercased, while the login email may carry capitals.
    email = (user_email or "").strip().lower()
    excluded = {str(e).strip().lower() for e in (visibility.get("excluded_student_ids", []) or [])}
    if email and email in excluded:
        return False

    if exam.get("exam_type") in ("public", "platform_standard"):
        return True

    exam_class_ids = visibility.get("class_ids", []) or []
    if any(cid in exam_class_ids for cid in (class_ids or [])):
        return True

    if email and email in {str(e).strip().lower() for e in (visibility.get("student_ids", []) or [])}:
        return True

    return False


def get_active_class_ids_for_student(student_id):
    """Every class this student is an active member of (soft-deleted classes excluded)."""
    classes_col = get_collection("classes")
    if classes_col is None:
        return []
    classes = classes_col.find(
        {"students.user_id": student_id, "students.status": "active", "is_active": {"$ne": False}},
        {"_id": 1}
    )
    return [c["_id"] for c in classes]
