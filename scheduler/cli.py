"""Az-social CLI — Ad Zombies Social Media Scheduler."""
import json
import sys
from pathlib import Path

import click

from scheduler import config, calendar_manager, production, analytics
from scheduler.connections import facebook, instagram, linkedin, gemini
from scheduler import poster


@click.group()
def main():
    """Ad Zombies social media scheduler."""
    config.ensure_dirs()


# ─── init ────────────────────────────────────────────────────────────────────

@main.command()
def init():
    """Initialize config. Safe to run multiple times."""
    config.ensure_dirs()
    if not config.CONFIG_PATH.exists():
        config.save(config.load())
        click.echo(f"Config created at {config.CONFIG_PATH}")
    else:
        click.echo(f"Config already exists at {config.CONFIG_PATH}")
    click.echo(f"Calendars:    {config.CALENDARS_DIR}")
    click.echo(f"Produced:     {config.PRODUCED_DIR}")
    click.echo(f"Images:       {config.IMAGES_DIR}")
    click.echo("\nNext: az-social connect gemini")


# ─── status ──────────────────────────────────────────────────────────────────

@main.command()
def status():
    """Show current connection status and config summary."""
    cfg = config.load()
    conn = cfg["connections"]
    prefs = cfg["preferences"]

    click.echo("\n--- Ad Zombies Social Status ---\n")

    click.echo("Connections:")
    click.echo(f"  Facebook:  {'connected' if conn.get('facebook_page_id') else 'not connected'}")
    if conn.get("facebook_token_expires"):
        click.echo(f"             expires {conn['facebook_token_expires'][:10]}")
    click.echo(f"  Instagram: {'connected' if conn.get('instagram_business_id') else 'not connected'}")
    click.echo(f"  LinkedIn:  {'connected' if conn.get('linkedin_access_token') else 'not connected'}")
    if conn.get("linkedin_token_expires"):
        click.echo(f"             expires {conn['linkedin_token_expires'][:10]}")
    click.echo(f"  YouTube:   {'connected' if conn.get('youtube_refresh_token') else 'not connected'}")
    click.echo(f"  Gemini:    {'connected' if conn.get('gemini_api_key') else 'not connected'}")

    click.echo(f"\nActive platforms: {', '.join(prefs.get('platforms_active', []))}")
    click.echo(f"Weeks ahead: {prefs.get('weeks_ahead', 4)}")

    cal = calendar_manager.load_current()
    if cal:
        posts = cal.get("posts", [])
        pending = sum(1 for p in posts if p["status"] == "pending_production")
        produced = sum(1 for p in posts if p["status"] == "produced")
        approved = sum(1 for p in posts if p["status"] == "approved")
        scheduled = sum(1 for p in posts if p["status"] == "scheduled")
        click.echo(f"\nCurrent calendar: {cal.get('start_date')} to {cal.get('end_date')}")
        click.echo(f"  pending:   {pending}")
        click.echo(f"  produced:  {produced}")
        click.echo(f"  approved:  {approved}")
        click.echo(f"  scheduled: {scheduled}")
    else:
        click.echo("\nNo active calendar.")

    click.echo()


# ─── connect ─────────────────────────────────────────────────────────────────

@main.group()
def connect():
    """Connect a platform or API key."""


@connect.command(name="gemini")
def connect_gemini():
    """Set Gemini API key (image generation)."""
    gemini.set_key()


@connect.command(name="facebook")
def connect_facebook():
    """Authorize Facebook Page access."""
    facebook.connect()


@connect.command(name="instagram")
def connect_instagram():
    """Link Instagram Business Account (requires Facebook connected first)."""
    instagram.connect()


@connect.command(name="linkedin")
def connect_linkedin():
    """Authorize LinkedIn Company Page access."""
    linkedin.connect()


@connect.command(name="youtube")
def connect_youtube():
    """Authorize YouTube channel upload access."""
    from scheduler.connections import youtube as yt_mod
    yt_mod.connect()


@connect.command(name="all")
def connect_all():
    """Walk through all connections in order."""
    from scheduler.connections import youtube as yt_mod
    click.echo("Starting full connection setup...\n")
    gemini.set_key()
    facebook.connect()
    instagram.connect()
    linkedin.connect()
    yt_mod.connect()
    click.echo("\nAll platforms connected.")


# ─── voice ───────────────────────────────────────────────────────────────────

@main.group()
def voice():
    """Pull and manage voice analysis data."""


@voice.command(name="pull")
@click.option("--platform", "-p", default="all", help="facebook, instagram, linkedin, youtube, or all")
def voice_pull(platform):
    """Pull recent posts for voice analysis."""
    cfg = config.load()

    if platform in ("facebook", "all") and cfg["connections"].get("facebook_access_token"):
        click.echo("Pulling Facebook posts...")
        try:
            posts = facebook.pull_recent_posts(30)
            click.echo(f"  Got {len(posts)} Facebook posts")
            _show_voice_sample(posts, "message")
        except Exception as e:
            click.echo(f"  Facebook error: {e}")

    if platform in ("instagram", "all") and cfg["connections"].get("instagram_business_id"):
        click.echo("Pulling Instagram posts...")
        try:
            posts = instagram.pull_recent_posts(30)
            click.echo(f"  Got {len(posts)} Instagram posts")
            _show_voice_sample(posts, "caption")
        except Exception as e:
            click.echo(f"  Instagram error: {e}")

    if platform in ("linkedin", "all") and cfg["connections"].get("linkedin_access_token"):
        click.echo("Pulling LinkedIn posts...")
        try:
            posts = linkedin.pull_recent_posts(20)
            click.echo(f"  Got {len(posts)} LinkedIn posts")
        except Exception as e:
            click.echo(f"  LinkedIn error: {e}")

    if platform in ("youtube", "all") and cfg["connections"].get("youtube_refresh_token"):
        click.echo("Pulling YouTube videos...")
        try:
            from scheduler.connections import youtube as yt_mod
            videos = yt_mod.pull_recent_videos(10)
            click.echo(f"  Got {len(videos)} YouTube videos")
        except Exception as e:
            click.echo(f"  YouTube error: {e}")


def _show_voice_sample(posts: list, text_field: str) -> None:
    top = [p for p in posts if p.get(text_field)][:5]
    for p in top:
        text = p[text_field][:120].replace("\n", " ")
        click.echo(f"    > {text}...")


# ─── calendar ────────────────────────────────────────────────────────────────

@main.group()
def calendar():
    """Manage the content calendar."""


@calendar.command(name="show")
def calendar_show():
    """Display the current calendar."""
    cal = calendar_manager.load_current()
    if not cal:
        click.echo("No active calendar. Build one with the Ad Zombies skill.")
        return
    calendar_manager.print_calendar_summary(cal)


@calendar.command(name="save")
@click.argument("file", type=click.Path(exists=True))
def calendar_save(file):
    """Save an approved calendar JSON file."""
    with open(file) as f:
        cal = json.load(f)
    path = calendar_manager.save_calendar(cal)
    click.echo(f"Calendar saved to {path}")
    click.echo(f"Total posts: {len(cal.get('posts', []))}")


@calendar.command(name="list")
def calendar_list():
    """List all saved calendars."""
    cals = calendar_manager.list_calendars()
    if not cals:
        click.echo("No calendars saved yet.")
        return
    current = config.get("calendars.current", "")
    for path in cals:
        marker = " (current)" if str(path) == current else ""
        click.echo(f"  {path.stem}{marker}")


# ─── post ────────────────────────────────────────────────────────────────────

@main.group()
def post():
    """Manage individual produced posts."""


@post.command(name="list")
@click.option("--status", "-s", default=None, help="Filter by status (pending_approval, approved, scheduled, posted)")
def post_list(status):
    """List produced posts."""
    posts = production.list_posts(status)
    if not posts:
        click.echo(f"No posts{' with status ' + status if status else ''}.")
        return
    for p in posts:
        click.echo(
            f"  {p.get('post_id')} [{p.get('platform', '').upper()[:2]}] "
            f"{p.get('scheduled_for', '')[:10]} {p.get('status', '')} — "
            f"{p.get('copy', '')[:50]}..."
        )


@post.command(name="show")
@click.argument("post_id")
def post_show(post_id):
    """Show a produced post in full."""
    p = production.load_post(post_id)
    if not p:
        click.echo(f"Post not found: {post_id}")
        return
    production.print_post_preview(p)


@post.command(name="save")
@click.argument("file", type=click.Path(exists=True))
def post_save(file):
    """Save a produced post from a JSON file."""
    with open(file) as f:
        post_data = json.load(f)
    path = production.save_post(post_data)
    click.echo(f"Post saved: {path}")


@post.command(name="approve")
@click.argument("post_id")
def post_approve(post_id):
    """Mark a post as approved."""
    if production.approve_post(post_id):
        click.echo(f"Post {post_id} approved.")
    else:
        click.echo(f"Post not found: {post_id}")


@post.command(name="skip")
@click.argument("post_id")
def post_skip(post_id):
    """Skip a post (won't be scheduled)."""
    if production.skip_post(post_id):
        click.echo(f"Post {post_id} skipped.")
    else:
        click.echo(f"Post not found: {post_id}")


@post.command(name="edit")
@click.argument("post_id")
@click.option("--copy", "-c", default=None, help="New copy text")
@click.option("--image", "-i", default=None, help="New image path or URL")
@click.option("--time", "-t", "schedule_time", default=None, help="New scheduled time (ISO 8601)")
def post_edit(post_id, copy, image, schedule_time):
    """Edit a produced post's copy, image, or schedule time."""
    updates = {}
    if copy:
        updates["copy"] = copy
    if image:
        updates["image_path"] = image
    if schedule_time:
        updates["scheduled_for"] = schedule_time

    if not updates:
        click.echo("Nothing to update. Use --copy, --image, or --time.")
        return

    if production.update_post(post_id, updates):
        click.echo(f"Post {post_id} updated.")
        p = production.load_post(post_id)
        production.print_post_preview(p)
    else:
        click.echo(f"Post not found: {post_id}")


# ─── schedule ────────────────────────────────────────────────────────────────

@main.command()
@click.argument("post_id")
def schedule(post_id):
    """Push an approved post to its platform."""
    p = production.load_post(post_id)
    if not p:
        click.echo(f"Post not found: {post_id}")
        return
    production.print_post_preview(p)
    if not click.confirm("Schedule this post?"):
        return
    poster.schedule_post(post_id)


@main.command(name="schedule-batch")
@click.option("--limit", "-n", default=5, help="Number of posts to review (default 5)")
def schedule_batch(limit):
    """Review and schedule a batch of approved posts."""
    posts = production.list_posts(status="approved")[:limit]
    if not posts:
        click.echo("No approved posts to schedule.")
        return

    click.echo(f"Reviewing {len(posts)} approved posts...\n")
    scheduled = 0
    held = 0

    for p in posts:
        production.print_post_preview(p)
        action = click.prompt(
            "Action",
            type=click.Choice(["schedule", "skip", "stop"], case_sensitive=False),
            default="schedule",
        )
        if action == "schedule":
            poster.schedule_post(p["post_id"])
            scheduled += 1
        elif action == "skip":
            production.skip_post(p["post_id"])
            held += 1
        elif action == "stop":
            break

    click.echo(f"\nDone. {scheduled} scheduled, {held} skipped.")
    remaining = production.list_posts(status="approved")
    if remaining:
        click.echo(f"{len(remaining)} approved posts still in queue.")


# ─── image ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("post_id")
@click.argument("prompt")
@click.option("--style", "-s", default="retro", type=click.Choice(["retro", "bold", "editorial"]))
def generate_image(post_id, prompt, style):
    """Generate an image for a post using Gemini."""
    click.echo(f"Generating {style} image for {post_id}...")
    result = gemini.generate_with_retry(prompt, post_id, style)
    if result:
        production.update_post(post_id, {"image_path": result})
        click.echo(f"Image saved: {result}")
    else:
        click.echo("Image generation failed. Add a photo manually or retry with a different prompt.")


# ─── analytics ───────────────────────────────────────────────────────────────

@main.group()
def pull_analytics():
    """Pull and display engagement analytics."""


@pull_analytics.command(name="post")
@click.argument("post_id")
def analytics_post(post_id):
    """Pull analytics for a specific post."""
    stats = analytics.pull_post_analytics(post_id)
    if stats:
        click.echo(f"\nAnalytics for {post_id}:")
        for k, v in stats.items():
            if k != "raw":
                click.echo(f"  {k}: {v}")
    else:
        click.echo("No analytics data returned.")


@pull_analytics.command(name="summary")
def analytics_summary():
    """Pull and print a summary across all posted content."""
    analytics.thirty_day_summary()


# ─── config ──────────────────────────────────────────────────────────────────

@main.command(name="config")
@click.option("--show", is_flag=True, help="Show full config")
@click.option("--set", "set_kv", nargs=2, metavar="KEY VALUE", help="Set a config value (dot notation)")
def config_cmd(show, set_kv):
    """View or update config values."""
    if set_kv:
        key, value = set_kv
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass
        config.set_value(key, value)
        click.echo(f"Set {key} = {value}")
    elif show:
        cfg = config.load()
        # Mask sensitive values
        for field in ("facebook_access_token", "facebook_app_secret", "linkedin_access_token",
                      "linkedin_client_secret", "youtube_refresh_token", "gemini_api_key"):
            if cfg["connections"].get(field):
                cfg["connections"][field] = "***"
        if cfg["connections"].get("youtube_client_secrets"):
            cfg["connections"]["youtube_client_secrets"] = {"...": "..."}
        click.echo(json.dumps(cfg, indent=2))
    else:
        click.echo("Use --show to display config or --set KEY VALUE to update it.")


if __name__ == "__main__":
    main()
