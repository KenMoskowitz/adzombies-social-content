from pathlib import Path
import json

CONFIG_DIR = Path.home() / ".az-social"
CONFIG_PATH = CONFIG_DIR / "config.json"
CALENDARS_DIR = CONFIG_DIR / "calendars"
PRODUCED_DIR = CONFIG_DIR / "produced"
IMAGES_DIR = CONFIG_DIR / "images"

DEFAULT_CONFIG = {
    "business": {
        "name": "Ad Zombies",
        "founder": "Ken Moskowitz",
        "website": "adzombies.com",
        "workshop_site": "workshop.adzombies.com",
        "active_offerings": [
            "Brand Reanimation Consulting",
            "Jingles",
            "Campaign Creation",
            "Fractional CMO",
            "Emergency Hotline",
            "BAM Mastermind",
            "BAM Lab",
            "The Store / Course Crypt",
            "Workshops",
            "Podcast",
            "Blog",
        ],
        "current_promotions": [],
        "upcoming_events": [],
    },
    "voice": {
        "tone_descriptors": ["punchy", "irreverent", "direct", "funny without trying too hard"],
        "do_words": ["BAM", "reanimation", "boring messages", "Spanky", "zombie", "brand"],
        "avoid_words": [
            "game changer", "leverage", "synergy", "level up", "cutting-edge",
            "copywriting", "seamless", "holistic", "in today's world", "at the end of the day",
        ],
        "sample_voice_excerpts": [],
    },
    "connections": {
        "facebook_app_id": "",
        "facebook_app_secret": "",
        "facebook_page_id": "",
        "facebook_access_token": "",
        "facebook_token_expires": "",
        "instagram_business_id": "",
        "linkedin_client_id": "",
        "linkedin_client_secret": "",
        "linkedin_org_id": "",
        "linkedin_access_token": "",
        "linkedin_token_expires": "",
        "youtube_channel_id": "",
        "youtube_refresh_token": "",
        "youtube_client_secrets": {},
        "gemini_api_key": "",
    },
    "preferences": {
        "platforms_active": ["facebook", "instagram", "linkedin"],
        "posting_cadence": {
            "facebook": 4,
            "instagram": 5,
            "linkedin": 3,
            "youtube": 1,
        },
        "weeks_ahead": 4,
        "use_real_photos": False,
        "photo_library_path": "",
    },
    "calendars": {
        "current": "",
        "approved_at": "",
    },
}


def ensure_dirs():
    CONFIG_DIR.mkdir(exist_ok=True)
    CALENDARS_DIR.mkdir(exist_ok=True)
    PRODUCED_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)


def _deep_merge(base, override):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def load():
    ensure_dirs()
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    _deep_merge(merged, data)
    return merged


def save(cfg):
    ensure_dirs()
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get(key_path, default=None):
    cfg = load()
    val = cfg
    for k in key_path.split("."):
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


def set_value(key_path, value):
    cfg = load()
    keys = key_path.split(".")
    target = cfg
    for k in keys[:-1]:
        if k not in target or not isinstance(target[k], dict):
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value
    save(cfg)
