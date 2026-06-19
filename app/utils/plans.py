PLAN_LIMITS = {
    "free": {
        "max_classes": 3,
        "max_students_per_class": 100,
        "max_exams": 5,
        "max_questions_per_bank": 50,
        "can_use_images": False,
        "can_message_1on1": False,
        "can_see_broadcast_reactions": False
    },
    "basic": {
        "max_classes": 5,
        "max_students_per_class": 200,
        "max_exams": 20,
        "max_questions_per_bank": 100,
        "can_use_images": True,
        "can_message_1on1": False,
        "can_see_broadcast_reactions": False
    },
    "pro": {
        "max_classes": 15,
        "max_students_per_class": 500,
        "max_exams": 100,
        "max_questions_per_bank": 500,
        "can_use_images": True,
        "can_message_1on1": True,
        "can_see_broadcast_reactions": True
    },
    "enterprise": {
        "max_classes": float('inf'),
        "max_students_per_class": float('inf'),
        "max_exams": float('inf'),
        "max_questions_per_bank": float('inf'),
        "can_use_images": True,
        "can_message_1on1": True,
        "can_see_broadcast_reactions": True
    }
}

def get_plan_limit(plan_type, limit_key):
    plan = PLAN_LIMITS.get(plan_type, PLAN_LIMITS["free"])
    return plan.get(limit_key, 0)
