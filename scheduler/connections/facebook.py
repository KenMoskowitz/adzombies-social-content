"""Facebook Graph API: OAuth setup and page posting."""
import http.server
import threading
import urllib.parse
import webbrowser
import time
from datetime import datetime, timezone

import click
import requests

from scheduler import config

GRAPH = "https://graph.facebook.com/v21.0"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "pages_read_user_content",
    "instagram_basic",
    "instagram_content_publish",
    "business_management",
]

_auth_code = None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Connected. You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code received. Try again.</h2>")

    def log_message(self, *args):
        pass


def connect_manual(app_id: str, app_secret: str, short_token: str):
    """Connect using a short-lived token from Graph API Explorer."""
    # Exchange short-lived user token for long-lived token
    r = requests.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
    )
    r.raise_for_status()
    long_token = r.json()["access_token"]
    expires_in = r.json().get("expires_in", 5184000)

    # Get pages
    r = requests.get(f"{GRAPH}/me/accounts", params={"access_token": long_token})
    r.raise_for_status()
    pages = r.json().get("data", [])

    if not pages:
        click.echo("No Facebook Pages found. Make sure your Page is linked to this account.")
        return

    click.echo("\nFound Pages:")
    for i, page in enumerate(pages):
        click.echo(f"  {i+1}. {page['name']} ({page['id']})")

    # Auto-select if only one page
    if len(pages) == 1:
        page = pages[0]
        click.echo(f"Using: {page['name']}")
    else:
        idx = int(input("Which page number is Ad Zombies? ")) - 1
        page = pages[idx]

    page_token = page["access_token"]
    page_id = page["id"]

    expires_at = datetime.fromtimestamp(
        time.time() + expires_in, tz=timezone.utc
    ).isoformat()

    cfg = config.load()
    cfg["connections"]["facebook_app_id"] = app_id
    cfg["connections"]["facebook_app_secret"] = app_secret
    cfg["connections"]["facebook_page_id"] = page_id
    cfg["connections"]["facebook_access_token"] = page_token
    cfg["connections"]["facebook_token_expires"] = expires_at
    config.save(cfg)

    click.echo(f"\nFacebook connected. Page: {page['name']} ({page_id})")
    click.echo(f"Token good until: {expires_at[:10]}")


def connect():
    cfg = config.load()
    conn = cfg["connections"]

    click.echo("\n--- Facebook / Instagram Connection ---\n")
    click.echo("You need a Facebook Developer App. If you don't have one:")
    click.echo("  1. Go to https://developers.facebook.com/apps")
    click.echo("  2. Create a new app (Business type)")
    click.echo("  3. Add 'Facebook Login' and 'Instagram Graph API' as products")
    click.echo("  4. Under Facebook Login > Settings, add this Redirect URI:")
    click.echo(f"     {REDIRECT_URI}")
    click.echo("")

    app_id = click.prompt("App ID", default=conn.get("facebook_app_id") or "")
    app_secret = click.prompt("App Secret", default=conn.get("facebook_app_secret") or "", hide_input=True)

    cfg["connections"]["facebook_app_id"] = app_id
    cfg["connections"]["facebook_app_secret"] = app_secret
    config.save(cfg)

    auth_url = (
        f"https://www.facebook.com/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={','.join(SCOPES)}"
        f"&response_type=code"
    )

    click.echo("\nOpening your browser for Facebook authorization...")
    click.echo(f"If it doesn't open, go to:\n  {auth_url}\n")

    global _auth_code
    _auth_code = None

    server = http.server.HTTPServer(("localhost", 8080), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.daemon = True
    thread.start()

    webbrowser.open(auth_url)

    click.echo("Waiting for authorization (60s timeout)...")
    for _ in range(60):
        if _auth_code:
            break
        time.sleep(1)

    server.server_close()

    if not _auth_code:
        click.echo("No authorization code received. Try again.")
        return

    # Exchange code for short-lived token
    r = requests.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": REDIRECT_URI,
            "code": _auth_code,
        },
    )
    r.raise_for_status()
    short_token = r.json()["access_token"]

    connect_manual(app_id, app_secret, short_token)


def post_text(message: str, scheduled_unix: int | None = None) -> str:
    cfg = config.load()
    token = cfg["connections"]["facebook_access_token"]
    page_id = cfg["connections"]["facebook_page_id"]

    params = {"message": message, "access_token": token}
    if scheduled_unix:
        params["published"] = "false"
        params["scheduled_publish_time"] = str(scheduled_unix)

    r = requests.post(f"{GRAPH}/{page_id}/feed", data=params)
    r.raise_for_status()
    return r.json()["id"]


def post_with_image(message: str, image_url: str, scheduled_unix: int | None = None) -> str:
    cfg = config.load()
    token = cfg["connections"]["facebook_access_token"]
    page_id = cfg["connections"]["facebook_page_id"]

    params = {"url": image_url, "caption": message, "access_token": token}
    if scheduled_unix:
        params["published"] = "false"
        params["scheduled_publish_time"] = str(scheduled_unix)

    r = requests.post(f"{GRAPH}/{page_id}/photos", data=params)
    r.raise_for_status()
    return r.json()["post_id"]


def delete_post(post_id: str) -> bool:
    cfg = config.load()
    token = cfg["connections"]["facebook_access_token"]
    r = requests.delete(f"{GRAPH}/{post_id}", params={"access_token": token})
    return r.ok


def pull_recent_posts(limit: int = 30) -> list[dict]:
    cfg = config.load()
    token = cfg["connections"]["facebook_access_token"]
    page_id = cfg["connections"]["facebook_page_id"]

    r = requests.get(
        f"{GRAPH}/{page_id}/posts",
        params={
            "fields": "message,created_time,attachments,reactions.summary(true),comments.summary(true),shares",
            "limit": limit,
            "access_token": token,
        },
    )
    r.raise_for_status()
    return r.json().get("data", [])


def get_post_insights(post_id: str) -> dict:
    cfg = config.load()
    token = cfg["connections"]["facebook_access_token"]
    r = requests.get(
        f"{GRAPH}/{post_id}/insights",
        params={
            "metric": "post_impressions,post_engaged_users,post_clicks,post_reactions_by_type_total",
            "access_token": token,
        },
    )
    r.raise_for_status()
    return r.json().get("data", [])
