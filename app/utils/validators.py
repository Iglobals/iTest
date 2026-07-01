import re
from bson import ObjectId


def validate_email(email: str) -> bool:
    return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


def validate_object_id(value: str) -> bool:
    try:
        ObjectId(value)
        return True
    except Exception:
        return False
