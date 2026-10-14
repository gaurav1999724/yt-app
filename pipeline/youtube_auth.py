"""YouTube Data API OAuth (desktop installed-app flow)."""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from pipeline.config import Config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def get_credentials(cfg: Config) -> Credentials:
    token_path = cfg.youtube_token_path
    secrets = cfg.youtube_client_secrets
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    if not creds or not creds.valid:
        if not secrets.exists():
            raise FileNotFoundError(
                f"Missing OAuth client secrets at {secrets}. "
                "Create a Desktop OAuth client in Google Cloud Console, "
                "enable YouTube Data API v3, and save the JSON there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def youtube_service(cfg: Config):
    creds = get_credentials(cfg)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)
