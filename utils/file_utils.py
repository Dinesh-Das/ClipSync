"""
File and path utilities for the YouTube Video Downloader.

Handles default directories, disk‑space checks, and persistent JSON settings.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logger import get_logger

_log = get_logger(__name__)

_APP_DIR: str = os.path.join(os.path.expanduser("~"), ".yt_downloader")
_SETTINGS_FILE: str = os.path.join(_APP_DIR, "settings.json")
_QUEUE_FILE: str = os.path.join(_APP_DIR, "queue.json")

# ── Default settings ──────────────────────────────────────────────────────────
DEFAULT_SETTINGS: Dict[str, Any] = {
    "download_dir": str(Path.home() / "Downloads" / "YTDownloader"),
    "preferred_format": "mp4",
    "preferred_resolution": "best",
    "preferred_audio_format": "mp3",
    "preferred_audio_bitrate": "192",
    # Subtitles
    "download_subtitles": False,
    "subtitle_langs": "en,.*",
    "embed_subtitles": False,
    # Automation
    "auto_download_on_paste": False,
    "max_concurrent_downloads": 3,
    "speed_limit": "",          # e.g. "5M" for 5 MB/s — empty = unlimited
    "proxy": "",
    "theme": "dark",
    "naming_template": "{title}",
    "retry_count": 3,
    "language": "en",
}


def get_app_dir() -> str:
    """Return the application config directory, creating it if needed."""
    os.makedirs(_APP_DIR, exist_ok=True)
    return _APP_DIR

def get_app_data_dir() -> str:
    """Alias for get_app_dir for consistency."""
    return get_app_dir()

def get_default_download_dir() -> str:
    """Return the default download directory from settings."""
    settings = load_settings()
    path = settings.get("download_dir", DEFAULT_SETTINGS["download_dir"])
    os.makedirs(path, exist_ok=True)
    return path


def ensure_dir_exists(path: str) -> str:
    """Create *path* and all parents if they don't exist. Returns *path*."""
    os.makedirs(path, exist_ok=True)
    return path


def check_disk_space(path: str, required_bytes: int = 100 * 1024 * 1024) -> bool:
    """
    Check whether there is enough free disk space at *path*.

    Args:
        path: The target directory.
        required_bytes: Minimum free bytes required (default 100 MB).

    Returns:
        ``True`` if enough space is available.
    """
    try:
        usage = shutil.disk_usage(path)
        has_space = usage.free >= required_bytes
        if not has_space:
            _log.warning(
                "Low disk space at %s: %d MB free, %d MB required",
                path,
                usage.free // (1024 * 1024),
                required_bytes // (1024 * 1024),
            )
        return has_space
    except OSError as exc:
        _log.error("Disk space check failed for %s: %s", path, exc)
        return False


# ── Settings persistence ──────────────────────────────────────────────────────

def load_settings() -> Dict[str, Any]:
    """Load settings from the JSON file, falling back to defaults."""
    settings = dict(DEFAULT_SETTINGS)
    if os.path.isfile(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            settings.update(saved)
            _log.debug("Settings loaded from %s", _SETTINGS_FILE)
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning("Failed to load settings: %s — using defaults", exc)
    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    """Persist *settings* dict to the JSON file."""
    os.makedirs(_APP_DIR, exist_ok=True)
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2, ensure_ascii=False)
        _log.debug("Settings saved to %s", _SETTINGS_FILE)
    except OSError as exc:
        _log.error("Failed to save settings: %s", exc)


def get_thumbnail_cache_dir() -> str:
    """Return the thumbnail cache directory, creating it if needed."""
    cache_dir = os.path.join(_APP_DIR, "cache", "thumbnails")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

# ── Queue persistence ─────────────────────────────────────────────────────────

def save_queue_to_disk(items: List[Dict[str, Any]]) -> None:
    """Save the current queue items to disk."""
    os.makedirs(_APP_DIR, exist_ok=True)
    try:
        with open(_QUEUE_FILE, "w", encoding="utf-8") as fh:
            json.dump(items, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        _log.error("Failed to save queue: %s", exc)

def load_queue_from_disk() -> List[Dict[str, Any]]:
    """Load queue items from disk."""
    if not os.path.isfile(_QUEUE_FILE):
        return []
    try:
        with open(_QUEUE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        _log.error("Failed to load queue: %s", exc)
        return []
