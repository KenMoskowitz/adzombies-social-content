"""Produced post storage and retrieval."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scheduler import config
from scheduler import calendar_manager


def save_post(post: dict) -> Path:
    post_id = post.get("post_id") or post.get("id")
    if not post_id:
        raise ValueError("Post must have a post_id")

    post["produced_at"] = post.get("produced_at") or datetime.now(tz=timezone.utc).isoformat()
    post["status"] = post.get("status") or "pending_approval"

    path = config.PRODUCED_DIR / f"{post_id}.json"
    with open(path, "w") as f:
        json.dump(post, f, indent=2)

    calendar_manager.update_post_status(post_id, "produced")
    return path


def load_post(post_id: str) -> dict | None:
    path = config.PRODUCED_DIR / f"{post_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_posts(status: str | None = None) -> list[dict]:
    posts = []
    for path in sorted(config.PRODUCED_DIR.glob("*.json")):
        with open(path) as f:
            post = json.load(f)
        if status is None or post.get("status") == status:
            posts.append(post)
    return posts


def update_post(post_id: str, updates: dict) -> bool:
    post = load_post(post_id)
    if not post:
        return False
    post.update(updates)
    path = config.PRODUCED_DIR / f"{post_id}.json"
    with open(path, "w") as f:
        json.dump(post, f, indent=2)
    if "status" in updates:
        calendar_manager.update_post_status(post_id, updates["status"])
    return True


def approve_post(post_id: str) -> bool:
    return update_post(post_id, {"status": "approved"})


def skip_post(post_id: str) -> bool:
    return update_post(post_id, {"status": "skipped"})


def mark_scheduled(post_id: str, platform_post_id: str) -> bool:
    return update_post(post_id, {"status": "scheduled", "platform_post_id": platform_post_id})


def mark_posted(post_id: str) -> bool:
    return update_post(post_id, {
        "status": "posted",
        "posted_at": datetime.now(tz=timezone.utc).isoformat(),
    })


def print_post_preview(post: dict) -> None:
    platform = post.get("platform", "").upper()
    scheduled = post.get("scheduled_for", "not scheduled")[:16]
    status = post.get("status", "")

    print(f"\n{'='*60}")
    print(f"Post ID:   {post.get('post_id')}")
    print(f"Platform:  {platform}")
    print(f"Scheduled: {scheduled}")
    print(f"Status:    {status}")
    print(f"{'─'*60}")
    print(post.get("copy", ""))
    if post.get("hashtags"):
        print("\n" + " ".join(post["hashtags"]))
    if post.get("image_path"):
        print(f"\nImage: {post['image_path']}")
    if post.get("link_in_first_comment"):
        print(f"Link (first comment): {post['link_in_first_comment']}")
    print(f"{'='*60}\n")
