"""Single source of truth for per-exam attempt limits and proctoring rules -
used by session start (sessions/routes.py), the student's My Exams listing
(dashboard/routes.py) and the exam pages, so they can't disagree."""


def attempt_limit(settings):
    """Max attempts a student gets, or None for unlimited.

    - allow_retake off -> exactly 1 attempt.
    - allow_retake on  -> settings.max_attempts if it's 2+, otherwise
      unlimited. (Exams created before the limit input existed stored
      allow_retake=True with max_attempts=1 and meant "unlimited", so 0/1
      keep meaning unlimited.)"""
    settings = settings or {}
    if not settings.get("allow_retake"):
        return 1
    try:
        limit = int(settings.get("max_attempts") or 0)
    except (TypeError, ValueError):
        limit = 0
    return limit if limit >= 2 else None


def attempt_limit_label(settings):
    limit = attempt_limit(settings)
    return "Unlimited" if limit is None else str(limit)


def is_proctored(settings):
    """Basic proctoring (tab-switch flags + camera/mic) is on for either
    setting - AI proctoring is a superset of it."""
    settings = settings or {}
    return bool(settings.get("proctoring_enabled") or settings.get("ai_proctoring_enabled"))


def is_ai_proctored(settings):
    return bool((settings or {}).get("ai_proctoring_enabled"))


def liveness_completed(user):
    return ((user or {}).get("liveness_verification") or {}).get("status") == "completed"


def normalize_attempt_settings(settings):
    """Coerce what the create/edit forms send into consistent stored values."""
    if "max_attempts" in settings:
        try:
            settings["max_attempts"] = max(0, int(settings.get("max_attempts") or 0))
        except (TypeError, ValueError):
            settings["max_attempts"] = 0
    if "allow_retake" in settings and not settings.get("allow_retake"):
        settings["max_attempts"] = 1
    for key in ("proctoring_enabled", "ai_proctoring_enabled"):
        if key in settings:
            settings[key] = bool(settings[key])
    if settings.get("ai_proctoring_enabled"):
        settings["proctoring_enabled"] = True
    return settings
