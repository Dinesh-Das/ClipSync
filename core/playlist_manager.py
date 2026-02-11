"""
Playlist management helpers.

Provides utilities for detecting playlists, selecting subsets of entries,
and creating per-playlist output directories.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core.logger import get_logger
from utils.validators import sanitize_filename

_log = get_logger(__name__)


def is_playlist_result(metadata: Dict[str, Any]) -> bool:
    """Return ``True`` if *metadata* represents a playlist."""
    return bool(metadata.get("is_playlist"))


def get_playlist_entries(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the list of entry dicts from playlist *metadata*."""
    return metadata.get("entries", [])


def select_entries(
    entries: List[Dict[str, Any]],
    indices: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Return a filtered list of playlist entries.

    Args:
        entries: Full list of entries from metadata.
        indices: 0-based indices of entries to keep. ``None`` = keep all.

    Returns:
        Filtered entry list.
    """
    if indices is None:
        return list(entries)
    selected = [entries[i] for i in indices if 0 <= i < len(entries)]
    _log.info("Selected %d / %d playlist entries", len(selected), len(entries))
    return selected


def create_playlist_folder(base_dir: str, playlist_title: str) -> str:
    """
    Create a subfolder under *base_dir* named after the playlist.

    Returns the full path to the created folder.
    """
    folder_name = sanitize_filename(playlist_title) or "playlist"
    folder_path = os.path.join(base_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    _log.info("Playlist folder: %s", folder_path)
    return folder_path


def build_playlist_download_items(
    metadata: Dict[str, Any],
    base_dir: str,
    selected_indices: Optional[List[int]] = None,
    download_options: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Build a list of individual download-item dicts for queuing.

    Each item has ``url`` and ``options`` keys ready for a :class:`DownloadWorker`.

    Args:
        metadata: Playlist metadata from :func:`core.metadata.extract_metadata`.
        base_dir: Root output directory.
        selected_indices: Optional subset of entries.
        download_options: Extra options merged into each item's options.

    Returns:
        List of dicts ``{url, title, options}``.
    """
    entries = get_playlist_entries(metadata)
    if selected_indices is not None:
        entries = select_entries(entries, selected_indices)

    playlist_title = metadata.get("playlist_title", "")
    output_dir = create_playlist_folder(base_dir, playlist_title) if playlist_title else base_dir

    items: List[Dict[str, Any]] = []
    for entry in entries:
        url = entry.get("url", "")
        if not url:
            continue
        opts = dict(download_options or {})
        opts["output_dir"] = output_dir
        items.append({
            "url": url,
            "title": entry.get("title", "Unknown"),
            "options": opts,
        })

    _log.info("Built %d download items for playlist '%s'", len(items), playlist_title)
    return items
