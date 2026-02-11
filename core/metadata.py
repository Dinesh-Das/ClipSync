"""
Video / playlist metadata fetching via yt-dlp.

Runs extraction in a QThread worker so the UI stays responsive.
"""

from __future__ import annotations

import os
import hashlib
from typing import Any, Dict, List, Optional

import requests
from PySide6.QtCore import QObject, QThread, Signal

import yt_dlp

from core.logger import get_logger
from utils.file_utils import get_thumbnail_cache_dir

_log = get_logger(__name__)


# ── Data helpers ──────────────────────────────────────────────────────────────

def _format_duration(seconds: Optional[int]) -> str:
    """Convert seconds to ``HH:MM:SS`` or ``MM:SS``."""
    if seconds is None:
        return "Unknown"
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _parse_formats(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract a user-friendly list of available formats from yt-dlp info dict.

    Returns a list of dicts with keys:
        format_id, ext, resolution, fps, vcodec, acodec, filesize, note
    """
    raw_formats: List[Dict[str, Any]] = info.get("formats") or []
    parsed: List[Dict[str, Any]] = []
    seen: set = set()

    for f in raw_formats:
        fmt_id = f.get("format_id", "")
        ext = f.get("ext", "")
        height = f.get("height")
        width = f.get("width")
        fps = f.get("fps")
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        filesize = f.get("filesize") or f.get("filesize_approx")

        # Build a human-readable resolution string
        if height:
            resolution = f"{height}p"
        elif width:
            resolution = f"{width}p"
        else:
            resolution = "audio only" if vcodec == "none" else "unknown"

        # Build a note
        note = f.get("format_note", "")

        key = (resolution, ext, vcodec, acodec)
        if key in seen:
            continue
        seen.add(key)

        parsed.append({
            "format_id": fmt_id,
            "ext": ext,
            "resolution": resolution,
            "fps": fps,
            "vcodec": vcodec if vcodec != "none" else None,
            "acodec": acodec if acodec != "none" else None,
            "filesize": filesize,
            "note": note,
        })

    # Sort: highest resolution first, then by ext
    def _sort_key(item: Dict[str, Any]) -> tuple:
        res = item["resolution"]
        try:
            num = int(res.replace("p", ""))
        except ValueError:
            num = 0
        return (-num, item["ext"])

    parsed.sort(key=_sort_key)
    return parsed


def _download_thumbnail(url: str) -> Optional[str]:
    """Download thumbnail and cache it locally. Returns the local path."""
    try:
        cache_dir = get_thumbnail_cache_dir()
        url_hash = hashlib.md5(url.encode()).hexdigest()
        ext = "jpg"
        path = os.path.join(cache_dir, f"{url_hash}.{ext}")
        if os.path.isfile(path):
            return path
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        with open(path, "wb") as fh:
            fh.write(resp.content)
        return path
    except Exception as exc:
        _log.warning("Thumbnail download failed: %s", exc)
        return None


# ── Public extraction function ────────────────────────────────────────────────

def extract_metadata(url: str) -> Dict[str, Any]:
    """
    Fetch metadata for a YouTube URL without downloading.

    Returns a dict with keys:
        url, title, channel, duration, duration_str, thumbnail_url,
        thumbnail_path, formats, is_playlist, playlist_title, entries
    """
    _log.info("Extracting metadata for %s", url)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise ValueError(f"Could not extract info from URL: {url}")

    is_playlist = info.get("_type") == "playlist" or "entries" in info

    # For playlists, gather entries
    entries: List[Dict[str, Any]] = []
    if is_playlist:
        for entry in (info.get("entries") or []):
            if entry is None:
                continue
            entries.append({
                "url": entry.get("webpage_url") or entry.get("url", ""),
                "title": entry.get("title", "Unknown"),
                "duration": entry.get("duration"),
                "duration_str": _format_duration(entry.get("duration")),
                "thumbnail_url": entry.get("thumbnail"),
            })

    thumbnail_url = info.get("thumbnail") or ""
    thumbnail_path = _download_thumbnail(thumbnail_url) if thumbnail_url else None

    result: Dict[str, Any] = {
        "url": url,
        "title": info.get("title", "Unknown"),
        "channel": info.get("uploader") or info.get("channel", "Unknown"),
        "duration": info.get("duration"),
        "duration_str": _format_duration(info.get("duration")),
        "thumbnail_url": thumbnail_url,
        "thumbnail_path": thumbnail_path,
        "formats": _parse_formats(info) if not is_playlist else [],
        "is_playlist": is_playlist,
        "playlist_title": info.get("title", "") if is_playlist else "",
        "entries": entries,
    }
    _log.info("Metadata extracted: %s (playlist=%s, entries=%d)",
              result["title"], is_playlist, len(entries))
    return result


# ── QThread worker ────────────────────────────────────────────────────────────

class MetadataWorkerSignals(QObject):
    """Signals emitted by :class:`MetadataWorker`."""
    finished = Signal(dict)
    error = Signal(str)


class MetadataWorker(QThread):
    """
    Background worker that fetches video metadata.

    Usage::

        worker = MetadataWorker(url)
        worker.signals.finished.connect(on_metadata)
        worker.signals.error.connect(on_error)
        worker.start()
    """

    def __init__(self, url: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.url = url
        self.signals = MetadataWorkerSignals()

    def run(self) -> None:  # noqa: D401
        try:
            data = extract_metadata(self.url)
            self.signals.finished.emit(data)
        except Exception as exc:
            _log.exception("Metadata extraction failed for %s", self.url)
            self.signals.error.emit(str(exc))

def search_videos(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search YouTube for *query* and return a list of simplified metadata dicts.
    
    Uses full extraction (not flat) to get title, channel, duration, views.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "extract_flat": False,     # Full extraction for rich metadata
        "noplaylist": True,
        "default_search": f"ytsearch{limit}",
        "skip_download": True,
    }
    
    results = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(query, download=False)
            if data and "entries" in data:
                results = [e for e in data["entries"] if e is not None]
            elif data:
                results = [data]
    except Exception as e:
        _log.error("Search failed: %s", e)
        return []

    # Clean up results into a simple format
    cleaned = []
    for item in results:
        if not item:
            continue
        url = item.get("webpage_url") or item.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
            
        cleaned.append({
            "title": item.get("title", "Unknown"),
            "url": url,
            "channel": item.get("uploader") or item.get("channel", "Unknown"),
            "duration": item.get("duration"),
            "thumbnail": item.get("thumbnail"),
            "view_count": item.get("view_count"),
        })
    return cleaned


class SearchWorker(QThread):
    """Worker thread to perform search without freezing UI."""
    
    class Signals(QObject):
        finished = Signal(list)
        error = Signal(str)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self.query = query
        self.signals = self.Signals()

    def run(self):
        try:
            results = search_videos(self.query)
            self.signals.finished.emit(results)
        except Exception as e:
            self.signals.error.emit(str(e))
