"""Gemini image generation for Ad Zombies posts."""
import base64
import mimetypes
import os
import time
from pathlib import Path

import click
import requests

from scheduler import config

GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"


def set_key():
    key = click.prompt("Gemini API key (from https://aistudio.google.com/app/apikey)", hide_input=True)
    config.set_value("connections.gemini_api_key", key)

    # Quick test
    try:
        result = generate_image("A simple red circle on a white background", "test")
        click.echo(f"Gemini connected and tested. Test image: {result}")
    except Exception as e:
        click.echo(f"Key saved but test failed: {e}")
        click.echo("Check your key at https://aistudio.google.com/app/apikey")


def generate_image(prompt: str, post_id: str, style: str = "retro") -> str:
    """Generate an image via Gemini. Returns local file path."""
    api_key = config.get("connections.gemini_api_key")
    if not api_key:
        raise click.ClickException("Gemini API key not set. Run: az-social connect gemini")

    style_prefixes = {
        "retro": (
            "Vintage advertising aesthetic, 1950s-1970s illustration style, "
            "limited color palette of 3-4 colors, aged texture, classic graphic design, "
            "bold type, no modern UI elements, no text overlays, "
        ),
        "bold": (
            "Strong graphic design, bold typography as visual element, "
            "high contrast backgrounds, poster-style composition, "
            "no generic stock photo lighting, "
        ),
        "editorial": (
            "Dark moody editorial photography aesthetic, cinematic lighting, "
            "dramatic environment, brand-in-crisis visual metaphor, "
            "no cheesy stock photo vibes, "
        ),
    }

    full_prompt = style_prefixes.get(style, "") + prompt
    full_prompt += ". No identifiable real brands. No real people. No logos."

    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }

    r = requests.post(
        f"{GENERATE_URL}?key={api_key}",
        json=payload,
        timeout=60,
    )
    r.raise_for_status()

    data = r.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])

    for part in parts:
        inline = part.get("inlineData", {})
        if inline.get("mimeType", "").startswith("image/"):
            image_data = base64.b64decode(inline["data"])
            ext = mimetypes.guess_extension(inline["mimeType"]) or ".png"
            images_dir = config.IMAGES_DIR
            images_dir.mkdir(exist_ok=True)
            out_path = images_dir / f"{post_id}{ext}"
            out_path.write_bytes(image_data)
            return str(out_path)

    raise ValueError("Gemini returned no image data. Try a different prompt.")


def generate_with_retry(prompt: str, post_id: str, style: str = "retro") -> str | None:
    """Retry once with a simpler prompt on failure."""
    try:
        return generate_image(prompt, post_id, style)
    except Exception as first_err:
        click.echo(f"Image generation failed: {first_err}. Retrying with simplified prompt...")
        time.sleep(2)
        simple_prompt = prompt.split(".")[0]
        try:
            return generate_image(simple_prompt, post_id, style)
        except Exception:
            return None
