"""Pull engagement data for posted content across platforms."""
from datetime import datetime, timezone

import click

from scheduler import production
from scheduler.connections import facebook, instagram, linkedin


def pull_post_analytics(post_id: str) -> dict:
    post = production.load_post(post_id)
    if not post:
        return {}

    platform = post.get("platform")
    platform_post_id = post.get("platform_post_id", "")
    stats = {}

    try:
        if platform == "facebook" and platform_post_id:
            raw = facebook.get_post_insights(platform_post_id)
            stats = {item["name"]: item.get("values", [{}])[0].get("value", 0) for item in raw}

        elif platform == "instagram" and platform_post_id:
            raw = instagram.get_media_insights(platform_post_id)
            stats = {item["name"]: item.get("values", [{}])[0].get("value", 0) for item in raw}

        elif platform == "linkedin":
            cfg_org = production.load_post(post_id)
            from scheduler import config
            org_id = config.get("connections.linkedin_org_id")
            raw = linkedin.get_share_stats(org_id)
            stats = {"raw": raw}

        elif platform == "youtube" and platform_post_id:
            from scheduler.connections import youtube as yt
            stats = yt.get_video_stats(platform_post_id)

    except Exception as e:
        click.echo(f"Could not fetch analytics for {post_id}: {e}")

    production.update_post(post_id, {"analytics": stats, "analytics_pulled_at": datetime.now(tz=timezone.utc).isoformat()})
    return stats


def pull_all_posted() -> list[dict]:
    """Pull analytics for all posts with status 'posted'."""
    posted = production.list_posts(status="posted")
    results = []
    for post in posted:
        pid = post.get("post_id")
        stats = pull_post_analytics(pid)
        results.append({"post_id": pid, "platform": post.get("platform"), "stats": stats})
    return results


def print_engagement_report(results: list[dict]) -> None:
    if not results:
        click.echo("No posted content with analytics yet.")
        return

    click.echo("\n--- Engagement Report ---\n")
    for r in results:
        pid = r["post_id"]
        platform = r["platform"].upper()
        stats = r.get("stats", {})
        click.echo(f"{pid} [{platform}]")
        for k, v in stats.items():
            if k != "raw":
                click.echo(f"  {k}: {v}")
        click.echo()


def thirty_day_summary() -> None:
    """Pull and print a summary of the last 30-day cycle."""
    results = pull_all_posted()
    print_engagement_report(results)

    if not results:
        return

    platform_counts: dict[str, int] = {}
    for r in results:
        p = r.get("platform", "unknown")
        platform_counts[p] = platform_counts.get(p, 0) + 1

    click.echo("Posts by platform:")
    for p, count in platform_counts.items():
        click.echo(f"  {p}: {count}")
    click.echo(f"\nTotal posted: {len(results)}")
