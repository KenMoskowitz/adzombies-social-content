"""LinkedIn OAuth and company page posting."""
import http.server
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone

import click
import requests

from scheduler import config

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API = "https://api.linkedin.com/v2"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = ["w_member_social", "w_organization_social", "r_organization_social", "r_liteprofile"]

_auth_code = None
_state = None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>LinkedIn connected. You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code received. Try again.</h2>")

    def log_message(self, *args):
        pass


def connect():
    cfg = config.load()
    conn = cfg["connections"]

    click.echo("\n--- LinkedIn Connection ---\n")
    click.echo("You need a LinkedIn Developer App. If you don't have one:")
    click.echo("  1. Go to https://www.linkedin.com/developers/apps")
    click.echo("  2. Create an app, select Ad Zombies as the company")
    click.echo("  3. Under Products, request 'Marketing Developer Platform'")
    click.echo("  4. Under Auth, add this redirect URL:")
    click.echo(f"     {REDIRECT_URI}")
    click.echo("")

    client_id = click.prompt("Client ID", default=conn.get("linkedin_client_id") or "")
    client_secret = click.prompt("Client Secret", default=conn.get("linkedin_client_secret") or "", hide_input=True)

    cfg["connections"]["linkedin_client_id"] = client_id
    cfg["connections"]["linkedin_client_secret"] = client_secret
    config.save(cfg)

    global _auth_code, _state
    _auth_code = None
    _state = secrets.token_urlsafe(16)

    auth_url = (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(' '.join(SCOPES))}"
        f"&state={_state}"
    )

    click.echo("\nOpening browser for LinkedIn authorization...")
    click.echo(f"If it doesn't open:\n  {auth_url}\n")

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

    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": _auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    r.raise_for_status()
    token_data = r.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 5184000)
    expires_at = datetime.fromtimestamp(
        time.time() + expires_in, tz=timezone.utc
    ).isoformat()

    # Get org ID
    headers = {"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"}
    r = requests.get(
        f"{API}/organizationAcls",
        params={"q": "roleAssignee", "role": "ADMINISTRATOR"},
        headers=headers,
    )
    r.raise_for_status()
    orgs = r.json().get("elements", [])

    if not orgs:
        click.echo("No organizations found where you're an admin. Check LinkedIn app permissions.")
        return

    click.echo("\nOrganizations found:")
    for i, org in enumerate(orgs):
        org_urn = org.get("organization", "")
        click.echo(f"  {i+1}. {org_urn}")

    idx = click.prompt("Which organization is Ad Zombies?", type=int, default=1) - 1
    org_urn = orgs[idx]["organization"]
    org_id = org_urn.split(":")[-1]

    cfg = config.load()
    cfg["connections"]["linkedin_org_id"] = org_id
    cfg["connections"]["linkedin_access_token"] = access_token
    cfg["connections"]["linkedin_token_expires"] = expires_at
    config.save(cfg)

    click.echo(f"\nLinkedIn connected. Org ID: {org_id}")
    click.echo(f"Token good until: {expires_at[:10]}")
    click.echo("\nNote: Marketing Developer Platform access may need LinkedIn approval.")
    click.echo("If posts fail, check your app's product approval status.")


def post(copy: str, image_url: str | None = None, link_url: str | None = None, schedule_ms: int | None = None) -> str:
    cfg = config.load()
    token = cfg["connections"]["linkedin_access_token"]
    org_id = cfg["connections"]["linkedin_org_id"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    body = {
        "owner": f"urn:li:organization:{org_id}",
        "text": {"text": copy},
        "distribution": {
            "linkedInDistributionTarget": {"visibleToGuest": True}
        },
    }

    if image_url or link_url:
        content: dict = {}
        if link_url:
            content["entityLocation"] = link_url
        if image_url:
            content["thumbnails"] = [{"resolvedUrl": image_url}]
        body["content"] = {
            "contentEntities": [content],
            "title": "",
        }

    if schedule_ms:
        body["lifecycleState"] = "PUBLISHED"
        body["scheduledPublishTime"] = schedule_ms
    else:
        body["lifecycleState"] = "PUBLISHED"

    r = requests.post(f"{API}/shares", headers=headers, json=body)
    r.raise_for_status()
    return r.headers.get("x-restli-id", "")


def add_first_comment(share_urn: str, link_url: str) -> None:
    cfg = config.load()
    token = cfg["connections"]["linkedin_access_token"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    body = {
        "actor": f"urn:li:organization:{cfg['connections']['linkedin_org_id']}",
        "message": {"text": link_url},
    }

    encoded_urn = urllib.parse.quote(share_urn, safe="")
    r = requests.post(
        f"{API}/socialActions/{encoded_urn}/comments",
        headers=headers,
        json=body,
    )
    r.raise_for_status()


def pull_recent_posts(count: int = 20) -> list[dict]:
    cfg = config.load()
    token = cfg["connections"]["linkedin_access_token"]
    org_id = cfg["connections"]["linkedin_org_id"]

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    r = requests.get(
        f"{API}/shares",
        params={"q": "owners", "owners": f"urn:li:organization:{org_id}", "count": count},
        headers=headers,
    )
    r.raise_for_status()
    return r.json().get("elements", [])


def get_share_stats(org_id: str) -> dict:
    cfg = config.load()
    token = cfg["connections"]["linkedin_access_token"]

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    r = requests.get(
        f"{API}/organizationalEntityShareStatistics",
        params={
            "q": "organizationalEntity",
            "organizationalEntity": f"urn:li:organization:{org_id}",
        },
        headers=headers,
    )
    r.raise_for_status()
    return r.json()
