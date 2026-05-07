"""Push approved posts to their platforms."""
import time
from datetime import datetime, timezone

import click

from scheduler import production
from scheduler.connections import facebook, instagram, linkedin


def schedule_post(post_id: str) -> None:
    """Push an approved post to its platform at the scheduled time."""
    post = production.load_post(post_id)
    if not post:
        raise click.ClickException(f"Post not found: {post_id}")

    if post.get("status") not in ("approved", "pending_approval"):
        click.echo(f"Post {post_id} status is '{post.get('status')}' — only 'approved' posts can be scheduled.")
        return

    platform = post.get("platform")
    copy = post.get("copy", "")
    image_path = post.get("image_path")
    hashtags = post.get("hashtags", [])
    scheduled_for = post.get("scheduled_for")
    link_in_first_comment = post.get("link_in_first_comment")

    full_copy = copy
    if hashtags and platform != "linkedin":
        full_copy = copy + "\n\n" + " ".join(hashtags)

    scheduled_unix = None
    if scheduled_for:
        try:
            dt = datetime.fromisoformat(scheduled_for)
            scheduled_unix = int(dt.timestamp())
            # Facebook requires at least 10 minutes in the future
            if platform == "facebook" and scheduled_unix < int(time.time()) + 600:
                scheduled_unix = int(time.time()) + 900
        except ValueError:
            pass

    platform_post_id = None

    try:
        if platform == "facebook":
            if image_path:
                platform_post_id = facebook.post_with_image(full_copy, _to_url(image_path), scheduled_unix)
            else:
                platform_post_id = facebook.post_text(full_copy, scheduled_unix)

        elif platform == "instagram":
            if not image_path:
                raise click.ClickException("Instagram posts require an image.")
            platform_post_id = instagram.post_image(_to_url(image_path), full_copy)

        elif platform == "linkedin":
            hashtag_str = " ".join(hashtags) if hashtags else ""
            li_copy = copy + ("\n\n" + hashtag_str if hashtag_str else "")
            schedule_ms = scheduled_unix * 1000 if scheduled_unix else None
            platform_post_id = linkedin.post(
                li_copy,
                image_url=_to_url(image_path) if image_path else None,
                schedule_ms=schedule_ms,
            )
            if link_in_first_comment and platform_post_id:
                linkedin.add_first_comment(platform_post_id, link_in_first_comment)
                click.echo(f"LinkedIn link posted in first comment.")

        elif platform == "youtube":
            if not image_path:
                raise click.ClickException("YouTube posts require a video file.")
            from scheduler.connections import youtube as yt_mod
            publish_at = scheduled_for if scheduled_for else None
            platform_post_id = yt_mod.upload_video(
                image_path,
                title=post.get("title", copy[:60]),
                description=copy,
                tags=[h.lstrip("#") for h in hashtags],
                publish_at=publish_at,
            )

        else:
            raise click.ClickException(f"Unknown platform: {platform}")

    except Exception as e:
        click.echo(f"Error scheduling {platform} post: {e}")
        click.echo("Post status unchanged. Fix the error and retry.")
        return

    production.mark_scheduled(post_id, platform_post_id or "")
    date_str = scheduled_for[:16] if scheduled_for else "immediately"
    click.echo(f"Locked in. {platform.title()} post going out {date_str}.")


def _to_url(path: str) -> str:
    """Pass through if it's already a URL, otherwise it's a local path that needs hosting."""
    if path.startswith("http"):
        return path
    raise click.ClickException(
        f"Platform APIs require a public image URL, but got a local path: {path}\n"
        "Upload the image to a public host (like S3 or Cloudinary) and update the post's image_path."
    )


def delete_scheduled_post(post_id: str) -> None:
    post = production.load_post(post_id)
    if not post:
        raise click.ClickException(f"Post not found: {post_id}")

    platform = post.get("platform")
    platform_post_id = post.get("platform_post_id")

    if not platform_post_id:
        click.echo("No platform post ID found — nothing to delete remotely.")
        return

    try:
        if platform == "facebook":
            facebook.delete_post(platform_post_id)
        elif platform == "youtube":
            from scheduler.connections import youtube as yt_mod
            yt = yt_mod._get_youtube_client()
            yt.videos().update(
                part="status",
                body={"id": platform_post_id, "status": {"privacyStatus": "private"}},
            ).execute()
        else:
            click.echo(f"Remote delete not implemented for {platform}. Remove it manually.")
            return
    except Exception as e:
        click.echo(f"Error deleting from {platform}: {e}")
        return

    production.update_post(post_id, {"status": "deleted", "platform_post_id": ""})
    click.echo(f"Post {post_id} deleted from {platform}.")
