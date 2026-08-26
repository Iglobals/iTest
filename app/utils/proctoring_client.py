"""
Thin HTTP client for the anticheat-system-roboflow FastAPI service.

This must never be called from the browser directly - the service's own
X-API-Key has to stay server-side (see that project's app/core/security.py,
which explicitly documents it as service-to-service auth, not end-user
auth). app/sessions/routes.py proxies every call through here.
"""
import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 12  # seconds - vision/audio inference is not instant


class ProctoringServiceError(Exception):
    """The anticheat service couldn't be reached or returned an error.
    Callers should fail open - never block an exam because the AI service
    happens to be down or cold-starting."""
    pass


def _headers():
    return {"X-API-Key": current_app.config.get('PROCTOR_API_KEY', '')}


def _base_url():
    return (current_app.config.get('PROCTOR_API_BASE_URL') or 'http://localhost:8000').rstrip('/')


def classify_frame(session_id, image_bytes, filename="frame.jpg"):
    """POST a webcam frame to /process-vision. Returns the parsed JSON response
    (frame_classification, confidence, session_status, consecutive_flags, escalated)."""
    try:
        resp = requests.post(
            f"{_base_url()}/process-vision",
            headers=_headers(),
            data={"user_id": session_id},
            files={"image": (filename, image_bytes, "image/jpeg")},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Proctoring vision call failed for session=%s: %s", session_id, exc)
        raise ProctoringServiceError(str(exc)) from exc


def classify_audio(session_id, audio_bytes, filename="slice.webm"):
    """POST an audio slice to /process-audio. Returns the parsed JSON response
    (speech_detected, transcript, keyword_flags, ...)."""
    try:
        resp = requests.post(
            f"{_base_url()}/process-audio",
            headers=_headers(),
            data={"user_id": session_id},
            files={"audio": (filename, audio_bytes, "audio/webm")},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Proctoring audio call failed for session=%s: %s", session_id, exc)
        raise ProctoringServiceError(str(exc)) from exc
