import base64
import hashlib
import http.server
import json
import secrets
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .. import store
from . import client

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TOKEN_SETTING_KEY = "gmail_token"
EXPIRY_SKEW_SECONDS = 60


class GmailAuthError(Exception):
    pass


class NotConnected(GmailAuthError):
    pass


class ReconnectRequired(GmailAuthError):
    pass


def load_client_secret(path):
    file = Path(path)
    if not file.exists():
        raise GmailAuthError(
            "Gmail client secret not found at " + str(file) + " -- download it from"
            " Google Cloud Console (OAuth client, Desktop app type)"
        )
    try:
        data = json.loads(file.read_text())["installed"]
        return data["client_id"], data["client_secret"]
    except (KeyError, ValueError) as exc:
        raise GmailAuthError("Could not read client id/secret from " + str(file)) from exc


def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        self.server.auth_code = params.get("code", [None])[0]
        self.server.auth_error = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        message = (
            "Gmail connected. You can close this tab."
            if self.server.auth_code
            else "Something went wrong: " + str(self.server.auth_error)
        )
        self.wfile.write(("<html><body>" + message + "</body></html>").encode("utf-8"))

    def log_message(self, format, *args):
        pass


def _build_auth_url(client_id, redirect_uri, challenge, state):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return AUTH_URI + "?" + urllib.parse.urlencode(params)


def _exchange_code(client_id, client_secret, code, redirect_uri, verifier):
    resp = httpx.post(TOKEN_URI, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _refresh(client_id, client_secret, refresh_token):
    resp = httpx.post(TOKEN_URI, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=20)
    if resp.status_code == 400 and resp.json().get("error") == "invalid_grant":
        raise ReconnectRequired(
            "Gmail's refresh token has expired -- this app's OAuth consent screen"
            " runs in Testing mode, so Google expires it after about a week. Run"
            " `python cli.py gmail-auth` again to reconnect."
        )
    resp.raise_for_status()
    return resp.json()


def _expiry(expires_in):
    return (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    ).isoformat(timespec="seconds")


def save_token(conn, record):
    store.set_setting(conn, TOKEN_SETTING_KEY, json.dumps(record))
    return record


def load_token(conn):
    raw = store.get_setting(conn, TOKEN_SETTING_KEY)
    return json.loads(raw) if raw else None


def connect(conn, client_secret_path, timeout=180):
    client_id, client_secret = load_client_secret(client_secret_path)
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.timeout = timeout
    server.auth_code = None
    server.auth_error = None
    port = server.server_address[1]
    redirect_uri = "http://127.0.0.1:" + str(port) + "/"

    url = _build_auth_url(client_id, redirect_uri, challenge, state)
    webbrowser.open(url)
    server.handle_request()
    server.server_close()

    if server.auth_error:
        raise GmailAuthError("Google returned an error: " + server.auth_error)
    if not server.auth_code:
        raise GmailAuthError("Timed out waiting for the browser redirect -- try again")

    token_response = _exchange_code(
        client_id, client_secret, server.auth_code, redirect_uri, verifier
    )
    profile = client.get_profile(token_response["access_token"])

    record = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "expires_at": _expiry(token_response.get("expires_in", 3600)),
        "scope": token_response.get("scope"),
        "account_email": profile.get("emailAddress"),
    }
    save_token(conn, record)
    return record


def get_valid_access_token(conn, client_id, client_secret):
    token = load_token(conn)
    if not token or not token.get("refresh_token"):
        raise NotConnected("Gmail is not connected yet -- run `python cli.py gmail-auth`")

    expires_at = datetime.fromisoformat(token["expires_at"])
    if datetime.now(timezone.utc) < expires_at - timedelta(seconds=EXPIRY_SKEW_SECONDS):
        return token["access_token"]

    refreshed = _refresh(client_id, client_secret, token["refresh_token"])
    token = {
        "access_token": refreshed["access_token"],
        "refresh_token": refreshed.get("refresh_token") or token["refresh_token"],
        "expires_at": _expiry(refreshed.get("expires_in", 3600)),
        "scope": refreshed.get("scope", token.get("scope")),
        "account_email": token.get("account_email"),
    }
    save_token(conn, token)
    return token["access_token"]
