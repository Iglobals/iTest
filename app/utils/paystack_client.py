"""
Thin HTTP client for the Paystack API.

Handles: creating recurring Plans (one-off, from the seed script), starting a
checkout (Initialize Transaction - Paystack's hosted page collects the card
and, for a plan-linked transaction, sets up the recurring authorization),
verifying a transaction server-side, and cancelling a subscription. We never
touch raw card numbers - Paystack's hosted page does that and hands back a
plan/subscription/customer code, which is all we store.
"""
import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

BASE_URL = "https://api.paystack.co"
DEFAULT_TIMEOUT = 15


class PaystackError(Exception):
    """A Paystack API call failed or returned status: false."""
    pass


def _headers():
    secret_key = current_app.config.get('PAYSTACK_SECRET_KEY', '')
    return {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }


def _request(method, path, **kwargs):
    try:
        resp = requests.request(method, f"{BASE_URL}{path}", headers=_headers(), timeout=DEFAULT_TIMEOUT, **kwargs)
        payload = resp.json()
    except requests.RequestException as exc:
        logger.error("Paystack request failed: %s %s - %s", method, path, exc)
        raise PaystackError(str(exc)) from exc

    if not resp.ok or not payload.get("status"):
        message = payload.get("message", "Unknown Paystack error")
        logger.error("Paystack API error: %s %s - %s", method, path, message)
        raise PaystackError(message)

    return payload["data"]


def create_plan(name: str, amount_kobo: int, interval: str) -> dict:
    """Creates a recurring Plan on Paystack. `interval` is 'monthly' or
    'annually' (Paystack's own vocabulary - note the 'annually', not
    'annual'). Returns the created plan's data, including its `plan_code`."""
    return _request("POST", "/plan", json={
        "name": name,
        "amount": amount_kobo,
        "interval": interval,
        "currency": "NGN",
    })


def get_plan(plan_code: str) -> dict:
    """Fetches plan details from Paystack to verify it exists."""
    return _request("GET", f"/plan/{plan_code}")


def initialize_transaction(email: str, amount_kobo: int, plan_code: str, callback_url: str, metadata: dict) -> dict:
    """Starts a checkout. Returns data including `authorization_url` (redirect
    the user here) and `reference` (used to verify the result later)."""
    return _request("POST", "/transaction/initialize", json={
        "email": email,
        "amount": amount_kobo,
        "plan": plan_code,
        "callback_url": callback_url,
        "metadata": metadata,
    })


def verify_transaction(reference: str) -> dict:
    """Server-side confirmation of a transaction's real outcome - never trust
    the callback redirect alone, since a client can hit that URL without
    actually having paid."""
    return _request("GET", f"/transaction/verify/{reference}")


def disable_subscription(subscription_code: str, email_token: str) -> dict:
    """Stops future charges. Paystack does not revoke access retroactively -
    the caller decides whether to keep access until the current period ends."""
    return _request("POST", "/subscription/disable", json={
        "code": subscription_code,
        "token": email_token,
    })


def fetch_subscription(subscription_code: str) -> dict:
    return _request("GET", f"/subscription/{subscription_code}")
