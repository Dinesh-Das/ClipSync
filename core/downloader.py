"""
Download engine powered by yt-dlp.

Provides a QThread-based ``DownloadWorker`` that reports progress via Qt signals
and supports pause / resume / cancel.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal

import yt_dlp

from core.logger import get_logger
from utils.file_utils import ensure_dir_exists, check_disk_space

_log = get_logger(__name__)


# ── Signal definitions ────────────────────────────────────────────────────────

class DownloadSignals(QObject):
    """Signals emitted by :class:`DownloadWorker`."""

    progress = Signal(dict)       # {percent, speed, eta, filename, downloaded, total}
    finished = Signal(str)        # final file path
    error = Signal(str)           # error message
    status_changed = Signal(str)  # "downloading", "paused", "cancelled", "merging"


# ── Worker ────────────────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    """
    Background download worker wrapping ``yt-dlp``.

    Parameters
    ----------
    url : str
        The YouTube URL to download.
    options : dict
        A dict of download options built by the UI. Recognised keys:

        - ``output_dir`` (str)
        - ``output_template`` (str) — yt-dlp output template
        - ``format`` (str) — yt-dlp format selector, e.g. ``"bestvideo+bestaudio/best"``
        - ``merge_output_format`` (str) — ``"mp4"``, ``"mkv"``, etc.
        - ``audio_only`` (bool)
        - ``audio_format`` (str) — ``"mp3"``, ``"m4a"``, ``"wav"``
        - ``audio_bitrate`` (str) — ``"192"``
        - ``embed_thumbnail`` (bool)
        - ``embed_metadata`` (bool)
        - ``speed_limit`` (str) — e.g. ``"5M"``
        - ``proxy`` (str)
        - ``speed_limit`` (str) — e.g. ``"5M"``
        - ``proxy`` (str)
        - ``retries`` (int)
        - ``download_subtitles`` (bool)
        - ``subtitle_langs`` (str)
        - ``embed_subtitles`` (bool)
    """

    signals: DownloadSignals

    def __init__(
        self,
        url: str,
        options: Optional[Dict[str, Any]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.options = options or {}
        self.signals = DownloadSignals()

        # Control flags
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused
        self._cancelled = False

    # ── Public control API ────────────────────────────────────────────────

    def pause(self) -> None:
        """Pause the download (blocks the progress-hook callback)."""
        self._pause_event.clear()
        self.signals.status_changed.emit("paused")
        _log.info("Download paused: %s", self.url)

    def resume(self) -> None:
        """Resume a paused download."""
        self._pause_event.set()
        self.signals.status_changed.emit("downloading")
        _log.info("Download resumed: %s", self.url)

    def cancel(self) -> None:
        """Cancel the download at the next progress callback."""
        self._cancelled = True
        self._pause_event.set()  # unblock if paused
        self.signals.status_changed.emit("cancelled")
        _log.info("Download cancelled: %s", self.url)

    # ── Internal ─────────────────────────────────────────────────────────

    def _build_ydl_opts(self) -> Dict[str, Any]:
        """Translate high-level *options* into a ``yt-dlp`` options dict."""
        opts = self.options
        output_dir = opts.get("output_dir", os.path.expanduser("~/Downloads"))
        output_template = opts.get("output_template", "%(title)s.%(ext)s")
        outtmpl = os.path.join(output_dir, output_template)

        ydl_opts: Dict[str, Any] = {
            "outtmpl": outtmpl,
            "progress_hooks": [self._progress_hook],
            "retries": opts.get("retries", 3),
            "fragment_retries": 10,
            "file_access_retries": 5,
            "noresumeonerror": True,       # Prevents HTTP 416 on corrupt partial files
            "continuedl": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }

        # Format selection
        if opts.get("audio_only"):
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": opts.get("audio_format", "mp3"),
                "preferredquality": opts.get("audio_bitrate", "192"),
            }]
            if opts.get("embed_thumbnail", True):
                ydl_opts["postprocessors"].append({"key": "EmbedThumbnail"})
                ydl_opts["writethumbnail"] = True
            if opts.get("embed_metadata", True):
                ydl_opts["postprocessors"].append({"key": "FFmpegMetadata"})
        else:
            fmt = opts.get("format", "bestvideo+bestaudio/best")
            ydl_opts["format"] = fmt
            merge_ext = opts.get("merge_output_format", "mp4")
            if merge_ext:
                ydl_opts["merge_output_format"] = merge_ext
            if opts.get("embed_metadata", True):
                ydl_opts.setdefault("postprocessors", []).append(
                    {"key": "FFmpegMetadata"}
                )

        # Subtitles configuration
        if opts.get("download_subtitles"):
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True  # Also grab auto-generated subs
            # Parse languages
            langs = opts.get("subtitle_langs", "en,.*")
            ydl_opts["subtitleslangs"] = [l.strip() for l in langs.split(",") if l.strip()]
            
            if opts.get("embed_subtitles"):
                ydl_opts.setdefault("postprocessors", []).append({
                    "key": "FFmpegEmbedSubtitle"    # Correct key for yt-dlp
                })

        # Speed limit
        speed_limit = opts.get("speed_limit", "")
        if speed_limit:
            ydl_opts["ratelimit"] = _parse_speed_limit(speed_limit)

        # Proxy
        proxy = opts.get("proxy", "")
        if proxy:
            ydl_opts["proxy"] = proxy

        # Trimming
        if opts.get("trim_start") or opts.get("trim_end"):
            start_str = opts.get("trim_start", "0")
            end_str = opts.get("trim_end", "")
            
            start_sec = _parse_time_to_seconds(start_str)
            end_sec = _parse_time_to_seconds(end_str) if end_str else None
            
            def ranges_callback(info, ydl):
                return [{'start_time': start_sec, 'end_time': end_sec}]
            
            ydl_opts["download_ranges"] = ranges_callback
            
            if opts.get("force_keyframes_at_cuts"):
                ydl_opts["force_keyframes_at_cuts"] = True

        return ydl_opts

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """Called by yt-dlp on each progress update chunk."""
        # pause gate
        self._pause_event.wait()

        if self._cancelled:
            raise yt_dlp.utils.DownloadCancelled("User cancelled download")

        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            percent = (downloaded / total * 100) if total else 0

            self.signals.progress.emit({
                "percent": round(percent, 1),
                "speed": speed,
                "eta": eta,
                "filename": d.get("filename", ""),
                "downloaded": downloaded,
                "total": total,
            })
        elif status == "finished":
            self.signals.status_changed.emit("merging")

    def run(self) -> None:
        """Execute the download in the background thread."""
        self.signals.status_changed.emit("downloading")
        output_dir = self.options.get("output_dir", os.path.expanduser("~/Downloads"))
        ensure_dir_exists(output_dir)

        if not check_disk_space(output_dir):
            self.signals.error.emit(
                "Not enough disk space in the selected output directory."
            )
            return

        ydl_opts = self._build_ydl_opts()
        _log.info("Starting download: %s with opts: %s", self.url, ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
            if info is None:
                self.signals.error.emit("Download returned no info — URL may be invalid.")
                return
            filepath = ydl.prepare_filename(info)
            self.signals.finished.emit(filepath)
            _log.info("Download complete: %s", filepath)
        except yt_dlp.utils.DownloadCancelled:
            _log.info("Download cancelled by user: %s", self.url)
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            _log.error("yt-dlp DownloadError: %s", msg)
            self.signals.error.emit(_friendly_error(msg))
        except Exception as exc:
            _log.exception("Unexpected download error")
            self.signals.error.emit(f"Unexpected error: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_speed_limit(value: str) -> Optional[int]:
    """Convert a human speed string like ``'5M'`` to bytes/s."""
    value = value.strip().upper()
    if not value:
        return None
    multipliers = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
    if value[-1] in multipliers:
        try:
            return int(float(value[:-1]) * multipliers[value[-1]])
        except ValueError:
            return None
    try:
        return int(value)
    except ValueError:
        return None



def _parse_time_to_seconds(time_str: str) -> int:
    """Convert 'HH:MM:SS' or 'MM:SS' string to total seconds."""
    time_str = time_str.strip()
    if not time_str:
        return 0
    parts = time_str.split(':')
    parts.reverse()  # Seconds, Minutes, Hours
    total = 0
    try:
        for i, part in enumerate(parts):
            total += int(part) * (60 ** i)
    except ValueError:
        return 0
    return total


def _friendly_error(msg: str) -> str:
    """Convert yt-dlp error messages into user-friendly text."""
    lower = msg.lower()
    if "private" in lower:
        return "This video is private and cannot be downloaded."
    if "age" in lower:
        return "This video is age-restricted. Try logging in or using cookies."
    if "unavailable" in lower or "not available" in lower:
        return "This video is unavailable in your region or has been removed."
    if "urlopen" in lower or "connection" in lower or "network" in lower:
        return "Network error — please check your internet connection and try again."
    return f"Download error: {msg}"
