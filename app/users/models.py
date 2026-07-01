from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict


@dataclass
class UserModel:
    ica_sub: str
    email: str
    full_name: str
    role: str
    avatar_url: Optional[str] = None
    institution: Optional[str] = None
    programme: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    subject_tags_interest: List[str] = None
    notification_preferences: Dict[str, bool] = None
    plan: Dict[str, Optional[str]] = None
    limits: Dict[str, Optional[int]] = None
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()
    last_login_at: datetime = datetime.utcnow()
    is_active: bool = True
    is_email_verified: bool = True
