"""Calendar JSON management for the 30-day content schedule."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scheduler import config


def save_calendar(calendar: dict) -> Path:
    start = calendar.get("start_date", datetime.now(tz=timezone.utc).date().isoformat())
    path = config.CALENDARS_DIR / f"{start}.json"
    calendar["approved_at"] = datetime.now(tz=timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(calendar, f, indent=2)

    cfg = config.load()
    cfg["calendars"]["current"] = str(path)
    cfg["calendars"]["approved_at"] = calendar["approved_at"]
    config.save(cfg)

    return path


def load_current() -> dict | None:
    current_path = config.get("calendars.current")
    if not current_path or not Path(current_path).exists():
        return None
    with open(current_path) as f:
        return json.load(f)


def load_calendar(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def list_calendars() -> list[Path]:
    return sorted(config.CALENDARS_DIR.glob("*.json"))


def update_post_status(post_id: str, status: str) -> bool:
    """Update a post's status in the current calendar."""
    cal = load_current()
    if not cal:
        return False

    for post in cal.get("posts", []):
        if post.get("id") == post_id:
            post["status"] = status
            path = config.get("calendars.current")
            with open(path, "w") as f:
                json.dump(cal, f, indent=2)
            return True

    return False


def get_posts_by_status(status: str) -> list[dict]:
    cal = load_current()
    if not cal:
        return []
    return [p for p in cal.get("posts", []) if p.get("status") == status]


def get_pending_posts(limit: int = 5) -> list[dict]:
    return get_posts_by_status("pending_production")[:limit]


def print_calendar_summary(cal: dict) -> None:
    posts = cal.get("posts", [])
    print(f"\nCalendar: {cal.get('start_date')} to {cal.get('end_date')}")
    print(f"Approved: {cal.get('approved_at', 'not yet')[:10]}")
    print(f"Total posts: {len(posts)}\n")

    by_week: dict[str, list[dict]] = {}
    for post in posts:
        date = post.get("date", "")
        dt = datetime.fromisoformat(date) if date else None
        week = f"Week of {dt.strftime('%b %d')}" if dt else "Unknown"
        by_week.setdefault(week, []).append(post)

    for week, week_posts in by_week.items():
        print(f"  {week}")
        for p in week_posts:
            platform = p.get("platform", "").upper()[:2]
            topic = p.get("topic", "")[:60]
            status = p.get("status", "")
            print(f"    {p.get('date', '')} [{platform}] {topic} ({status})")
        print()
