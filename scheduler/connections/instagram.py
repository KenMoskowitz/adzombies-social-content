"""Instagram Business API via Meta Graph API."""
import click
import requests

from scheduler import config

GRAPH = "https://graph.facebook.com/v21.0"


def connect():
    """Pull Instagram Business Account ID from the linked Facebook Page."""
    cfg = config.load()
    page_id = cfg["connections"]["facebook_page_id"]
    token = cfg["connections"]["facebook_access_token"]

    if not page_id or not token:
        click.echo("Connect Facebook first: az-social connect facebook")
        return

    click.echo("\n--- Instagram Connection ---\n")
    click.echo("Fetching Instagram Business Account linked to your Facebook Page...")

    r = requests.get(
        f"{GRAPH}/{page_id}",
        params={"fields": "instagram_business_account", "access_token": token},
    )
    r.raise_for_status()
    data = r.json()

    ig = data.get("instagram_business_account")
    if not ig:
        click.echo("\nNo Instagram Business Account linked to this Page.")
        click.echo("Fix it in Instagram: Settings > Account > Linked Accounts > Facebook.")
        click.echo("Make sure your IG account is a Business account, not Personal.")
        return

    ig_id = ig["id"]
    cfg = config.load()
    cfg["connections"]["instagram_business_id"] = ig_id
    config.save(cfg)

    click.echo(f"Instagram connected. Business ID: {ig_id}")


def post_image(image_url: str, caption: str) -> str:
    """Two-step Instagram publish: create container, then publish."""
    cfg = config.load()
    ig_id = cfg["connections"]["instagram_business_id"]
    token = cfg["connections"]["facebook_access_token"]

    # Step 1: create media container
    r = requests.post(
        f"{GRAPH}/{ig_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
    )
    r.raise_for_status()
    container_id = r.json()["id"]

    # Step 2: publish
    r = requests.post(
        f"{GRAPH}/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
    )
    r.raise_for_status()
    return r.json()["id"]


def post_reel(video_url: str, caption: str) -> str:
    """Upload a Reel. video_url must be publicly accessible."""
    cfg = config.load()
    ig_id = cfg["connections"]["instagram_business_id"]
    token = cfg["connections"]["facebook_access_token"]

    r = requests.post(
        f"{GRAPH}/{ig_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": token,
        },
    )
    r.raise_for_status()
    container_id = r.json()["id"]

    r = requests.post(
        f"{GRAPH}/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
    )
    r.raise_for_status()
    return r.json()["id"]


def pull_recent_posts(limit: int = 30) -> list[dict]:
    cfg = config.load()
    ig_id = cfg["connections"]["instagram_business_id"]
    token = cfg["connections"]["facebook_access_token"]

    r = requests.get(
        f"{GRAPH}/{ig_id}/media",
        params={
            "fields": "caption,media_type,media_url,timestamp,like_count,comments_count",
            "limit": limit,
            "access_token": token,
        },
    )
    r.raise_for_status()
    return r.json().get("data", [])


def get_media_insights(media_id: str) -> dict:
    cfg = config.load()
    token = cfg["connections"]["facebook_access_token"]
    r = requests.get(
        f"{GRAPH}/{media_id}/insights",
        params={
            "metric": "engagement,impressions,reach,saved,video_views",
            "access_token": token,
        },
    )
    r.raise_for_status()
    return r.json().get("data", [])
