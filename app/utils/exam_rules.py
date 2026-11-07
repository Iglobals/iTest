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


def check_ai_proctoring_allowed(user, exam_payload):
    """
    Validates whether `user` is allowed to enable AI proctoring on an exam.
    Rules:
      1. An examiner can enable proctoring if they subscribe personally (Pro/Enterprise)
         or are a platform_admin.
      2. If not personally subscribed, they can ONLY enable AI proctoring through an
         organization they belong to, AND only for class/classes they are assigned to
         under that organization.
    Returns: (allowed: bool, error_message: str | None)
    """
    from app.utils.plans import get_plan_limit
    from app.utils.admin import effective_plan_type
    from app.utils.mongo import get_collection, build_object_id

    # 1. Personal subscription check
    user_plan = effective_plan_type(user)
    if get_plan_limit(user_plan, "can_use_ai_proctoring"):
        return True, None

    # 2. Organization check
    org_id = (exam_payload or {}).get("organization_id")
    if not org_id:
        return False, "An examiner cannot enable AI proctoring without a personal Pro subscription, or through an authorized organization."

    orgs_col = get_collection("organizations")
    classes_col = get_collection("classes")
    if orgs_col is None or classes_col is None:
        return False, "Database error verifying organization proctoring permissions."

    org_obj = orgs_col.find_one({"_id": build_object_id(org_id)})
    if not org_obj:
        return False, "Organization not found."

    org_plan = (org_obj.get("plan") or {}).get("type", "free")
    org_ai_allowed = (
        get_plan_limit(org_plan, "can_use_ai_proctoring")
        or bool((org_obj.get("limits") or {}).get("ai_proctoring"))
        or bool(org_obj.get("is_builtin"))
    )
    if not org_ai_allowed:
        return False, "The selected organization does not have an active plan with AI proctoring enabled."

    # Must be scoped to class/classes where this examiner is a teacher
    visibility = (exam_payload or {}).get("visibility") or {}
    vis_type = visibility.get("type", "class")
    class_ids = visibility.get("class_ids") or []

    if vis_type != "class" or not class_ids:
        return False, "Without a personal Pro subscription, AI-proctored exams through an organization must be assigned to specific classes you teach."

    user_id = user.get("_id")
    for cid in class_ids:
        class_obj = classes_col.find_one({"_id": build_object_id(cid)})
        if not class_obj:
            return False, f"Class {cid} not found."

        if str(class_obj.get("organization_id")) != str(org_obj["_id"]):
            return False, f"Class '{class_obj.get('name', cid)}' does not belong to the selected organization."

        is_teacher = False
        if str(class_obj.get("created_by")) == str(user_id):
            is_teacher = True
        else:
            for t in class_obj.get("teachers", []):
                if str(t.get("user_id")) == str(user_id):
                    is_teacher = True
                    break

        if not is_teacher:
            return False, f"You can only enable AI proctoring for classes where you are an assigned teacher ('{class_obj.get('name', cid)}')."

    return True, None
