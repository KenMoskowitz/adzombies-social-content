"""YouTube Data API v3: OAuth setup and video upload/scheduling."""
import json
import os
import tempfile
from datetime import datetime, timezone

import click
import requests

from scheduler import config

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    _GOOGLE_AVAILABLE = True
except BaseException:
    _GOOGLE_AVAILABLE = False

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _require_google():
    if not _GOOGLE_AVAILABLE:
        raise click.ClickException(
            "Google API libraries not installed. Run: pip install google-auth-oauthlib google-api-python-client"
        )


def connect():
    _require_google()

    click.echo("\n--- YouTube Connection ---\n")
    click.echo("You need a Google Cloud project with YouTube Data API v3 enabled.")
    click.echo("  1. Go to https://console.cloud.google.com")
    click.echo("  2. Create or select a project")
    click.echo("  3. Enable YouTube Data API v3")
    click.echo("  4. Create OAuth 2.0 credentials (Desktop app type)")
    click.echo("  5. Download the JSON credentials file")
    click.echo("")

    creds_path = click.prompt("Path to your downloaded credentials JSON file")
    creds_path = os.path.expanduser(creds_path)

    if not os.path.exists(creds_path):
        click.echo(f"File not found: {creds_path}")
        return

    with open(creds_path) as f:
        client_secrets = json.load(f)

    cfg = config.load()
    cfg["connections"]["youtube_client_secrets"] = client_secrets
    config.save(cfg)

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=8081, prompt="consent")

    cfg = config.load()
    cfg["connections"]["youtube_refresh_token"] = creds.refresh_token
    config.save(cfg)

    # Get channel ID
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="id,snippet", mine=True).execute()
    channels = resp.get("items", [])

    if not channels:
        click.echo("No YouTube channel found for this account.")
        return

    channel = channels[0]
    channel_id = channel["id"]
    channel_name = channel["snippet"]["title"]

    cfg = config.load()
    cfg["connections"]["youtube_channel_id"] = channel_id
    config.save(cfg)

    click.echo(f"\nYouTube connected. Channel: {channel_name} ({channel_id})")


def _get_youtube_client():
    _require_google()
    cfg = config.load()
    conn = cfg["connections"]

    client_secrets = conn.get("youtube_client_secrets", {})
    refresh_token = conn.get("youtube_refresh_token", "")

    if not client_secrets or not refresh_token:
        raise click.ClickException("YouTube not connected. Run: az-social connect youtube")

    ci = client_secrets.get("installed", client_secrets.get("web", {}))
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=ci.get("client_id"),
        client_secret=ci.get("client_secret"),
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "22",
    publish_at: str | None = None,
) -> str:
    """Upload a video or Short. publish_at is ISO 8601, schedules the upload."""
    youtube = _get_youtube_client()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "private" if publish_at else "public",
        },
    }

    if publish_at:
        body["status"]["publishAt"] = publish_at
        body["status"]["selfDeclaredMadeForKids"] = False

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    return response["id"]


def pull_recent_videos(max_results: int = 10) -> list[dict]:
    youtube = _get_youtube_client()
    cfg = config.load()
    channel_id = cfg["connections"]["youtube_channel_id"]

    resp = youtube.search().list(
        part="id,snippet",
        channelId=channel_id,
        order="date",
        maxResults=max_results,
        type="video",
    ).execute()

    video_ids = [item["id"]["videoId"] for item in resp.get("items", [])]
    if not video_ids:
        return []

    details = youtube.videos().list(
        part="snippet,statistics,status",
        id=",".join(video_ids),
    ).execute()

    return details.get("items", [])


def get_video_stats(video_id: str) -> dict:
    youtube = _get_youtube_client()
    resp = youtube.videos().list(part="statistics", id=video_id).execute()
    items = resp.get("items", [])
    return items[0]["statistics"] if items else {}
