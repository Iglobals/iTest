import os
import base64
import hashlib
import secrets
import requests
from flask import current_app

def generate_pkce():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return {"code_verifier": verifier, "code_challenge": challenge}

def get_authorization_url(state: str, code_challenge: str) -> str:
    params = {
        "client_id": current_app.config['ICA_CLIENT_ID'],
        "redirect_uri": current_app.config['ICA_REDIRECT_URI'],
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    base_url = current_app.config['ICA_BASE_URL']
    return f"{base_url}/oauth/authorize?{query}"

def exchange_code(code: str, code_verifier: str) -> dict:
    base_url = current_app.config['ICA_BASE_URL']
    resp = requests.post(f"{base_url}/oauth/token", data={
        "grant_type": "authorization_code",
        "client_id": current_app.config['ICA_CLIENT_ID'],
        "client_secret": current_app.config['ICA_CLIENT_SECRET'],
        "redirect_uri": current_app.config['ICA_REDIRECT_URI'],
        "code": code,
        "code_verifier": code_verifier
    })
    resp.raise_for_status()
    return resp.json()

def verify_token(access_token: str) -> dict:
    base_url = current_app.config['ICA_BASE_URL']
    resp = requests.get(f"{base_url}/oauth/userinfo",
                        headers={"Authorization": f"Bearer {access_token}"})
    resp.raise_for_status()
    return resp.json()

def refresh_access_token(refresh_token: str) -> dict:
    base_url = current_app.config['ICA_BASE_URL']
    resp = requests.post(f"{base_url}/oauth/token", data={
        "grant_type": "refresh_token",
        "client_id": current_app.config['ICA_CLIENT_ID'],
        "client_secret": current_app.config['ICA_CLIENT_SECRET'],
        "refresh_token": refresh_token
    })
    resp.raise_for_status()
    return resp.json()
