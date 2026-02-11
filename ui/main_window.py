"""
Main application window for the YouTube Video Downloader.

Assembles the URL input, metadata display, format selectors, download controls,
progress indicators, and the queue panel into a single cohesive window.
"""

from __future__ import annotations

import os
import sys
import json
from typing import Any, Dict, List, Optional, cast

from PySide6.QtCore import Qt, QSize, Slot, QEvent, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap, QClipboard, QCursor, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.downloader import DownloadWorker
from core.logger import get_logger
from core.metadata import MetadataWorker
from core.playlist_manager import build_playlist_download_items
from ui.queue_view import QueueView
from ui.settings_dialog import SettingsDialog
from ui.search_dialog import SearchDialog
from ui.history_dialog import HistoryDialog
from utils.file_utils import load_settings, save_settings, get_default_download_dir
from utils.validators import is_valid_url, is_playlist_url
from utils.history_manager import append_history


_log = get_logger(__name__)

# Resolve project root for asset paths
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
_THEMES_DIR = os.path.join(_PROJECT_ROOT, "assets", "themes")


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ClipSync")
        self.setMinimumSize(640, 480)
        self.resize(1080, 780)

        self._settings: Dict[str, Any] = load_settings()
        self._current_metadata: Optional[Dict[str, Any]] = None
        self._download_workers: List[DownloadWorker] = []
        self._active_downloads: int = 0
        self._current_worker: Optional[DownloadWorker] = None
        self._metadata_worker: Optional[MetadataWorker] = None
        self._original_thumbnail: Optional[QPixmap] = None

        self._build_menu_bar()
        self._build_central_ui()
        self._build_status_bar()
        self._apply_theme(self._settings.get("theme", "dark"))
        
        # Load persisted queue
        self._load_queue()

        # Clipboard monitor
        self._last_clipboard_text = ""
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        # Drag & Drop
        self.setAcceptDrops(True)

        # Scheduler Timer (check every 10 seconds)
        self._scheduler_timer = QTimer(self)
        self._scheduler_timer.timeout.connect(self._check_schedule)
        self._scheduler_timer.start(10000)

    def _load_queue(self) -> None:
        """Load queue items from disk and populate the view."""
        from utils.file_utils import load_queue_from_disk
        items = load_queue_from_disk()
        if items:
            self._queue_view.load_items(items)
            self._status_bar.showMessage(f"Loaded {len(items)} items from queue", 5000)

    # ══════════════════════════════════════════════════════════════════
    #  Menu bar
    # ══════════════════════════════════════════════════════════════════

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # ── File ──
        file_menu = menu_bar.addMenu("&File")

        settings_action = QAction("⚙  Settings", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # ── View ──
        view_menu = menu_bar.addMenu("&View")

        self._theme_action = QAction("🌙  Switch to Light Theme", self)
        self._theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._theme_action)
        
        history_action = QAction("🕒  Download History", self)
        history_action.triggered.connect(self._show_history)
        view_menu.addAction(history_action)

        # ── Help ──
        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ══════════════════════════════════════════════════════════════════
    #  Central widget  —  fully responsive layout
    # ══════════════════════════════════════════════════════════════════

    def _build_central_ui(self) -> None:
        # Scroll area so content is always reachable on small windows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setSpacing(10)
        root.setContentsMargins(16, 12, 16, 12)

        # ── 1) URL input ──────────────────────────────────────────────
        url_group = QGroupBox("Enter Video URL")
        url_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        url_lay = QHBoxLayout(url_group)
        url_lay.setSpacing(8)

        self._url_edit = QLineEdit()
        self._url_edit.setObjectName("urlInput")
        self._url_edit.setPlaceholderText("https://www.youtube.com/watch?v=... or search query")
        self._url_edit.setMinimumHeight(40)
        self._url_edit.returnPressed.connect(self._on_fetch_info)
        url_lay.addWidget(self._url_edit, 1)

        paste_btn = QPushButton("📋  Paste")
        paste_btn.setObjectName("pasteBtn")
        paste_btn.setToolTip("Paste URL from clipboard and fetch info")
        paste_btn.clicked.connect(self._paste_url)
        url_lay.addWidget(paste_btn)

        self._fetch_btn = QPushButton("🔍  Fetch Info")
        self._fetch_btn.setObjectName("fetchBtn")
        self._fetch_btn.clicked.connect(self._on_fetch_info)
        url_lay.addWidget(self._fetch_btn)

        root.addWidget(url_group)

        # ── 2) Metadata + Options (side-by-side, both stretchable) ───
        mid_row = QHBoxLayout()
        mid_row.setSpacing(12)

        # ── Left: Video Info ──
        meta_group = QGroupBox("Video Info")
        meta_group.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        meta_lay = QVBoxLayout(meta_group)
        meta_lay.setSpacing(6)

        self._thumbnail_label = QLabel("No thumbnail")
        self._thumbnail_label.setObjectName("thumbnailLabel")
        self._thumbnail_label.setMinimumSize(160, 90)
        self._thumbnail_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                            QSizePolicy.Policy.Expanding)
        self._thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnail_label.setScaledContents(False)
        meta_lay.addWidget(self._thumbnail_label, 1)

        self._title_label = QLabel("Video title will appear here")
        self._title_label.setObjectName("titleLabel")
        self._title_label.setWordWrap(True)
        self._title_label.setMinimumHeight(22)
        self._title_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Preferred)
        meta_lay.addWidget(self._title_label)

        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        self._channel_label = QLabel("Channel: —")
        self._channel_label.setObjectName("subtitleLabel")
        self._channel_label.setWordWrap(True)
        self._channel_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                          QSizePolicy.Policy.Preferred)
        info_row.addWidget(self._channel_label, 1)
        self._duration_label = QLabel("Duration: —")
        self._duration_label.setObjectName("subtitleLabel")
        info_row.addWidget(self._duration_label)
        meta_lay.addLayout(info_row)

        mid_row.addWidget(meta_group, 3)          # 60 % of width

        # ── Right: Download Options (grid form) ──
        opts_group = QGroupBox("Download Options")
        opts_group.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        opts_group.setMinimumWidth(200)
        form = QGridLayout(opts_group)
        form.setSpacing(8)
        form.setColumnStretch(0, 0)               # labels — fixed
        form.setColumnStretch(1, 1)               # combos — stretch

        r = 0
        form.addWidget(QLabel("Type:"), r, 0, Qt.AlignmentFlag.AlignRight)
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Video + Audio", "Video Only", "Audio Only"])
        self._type_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Fixed)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addWidget(self._type_combo, r, 1)

        r += 1
        self._format_label = QLabel("Format:")
        form.addWidget(self._format_label, r, 0, Qt.AlignmentFlag.AlignRight)
        self._format_combo = QComboBox()
        self._format_combo.addItems(["mp4", "mkv", "webm"])
        self._format_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                         QSizePolicy.Policy.Fixed)
        form.addWidget(self._format_combo, r, 1)

        r += 1
        self._res_label = QLabel("Resolution:")
        form.addWidget(self._res_label, r, 0, Qt.AlignmentFlag.AlignRight)
        self._res_combo = QComboBox()
        self._res_combo.addItems(
            ["Best Quality", "2160p (4K)", "1440p", "1080p",
             "720p", "480p", "360p", "144p"]
        )
        self._res_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Fixed)
        form.addWidget(self._res_combo, r, 1)

        r += 1
        self._codec_label = QLabel("Codec:")
        form.addWidget(self._codec_label, r, 0, Qt.AlignmentFlag.AlignRight)
        self._codec_combo = QComboBox()
        self._codec_combo.addItems(["Auto", "H.264 (avc1)", "VP9", "AV1"])
        self._codec_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Fixed)
        form.addWidget(self._codec_combo, r, 1)

        r += 1
        self._audio_fmt_row_label = QLabel("Audio format:")
        form.addWidget(self._audio_fmt_row_label, r, 0,
                       Qt.AlignmentFlag.AlignRight)
        self._audio_fmt_combo = QComboBox()
        self._audio_fmt_combo.addItems(["mp3", "m4a", "wav", "opus", "flac"])
        self._audio_fmt_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                            QSizePolicy.Policy.Fixed)
        form.addWidget(self._audio_fmt_combo, r, 1)

        r += 1
        self._audio_br_label = QLabel("Bitrate:")
        form.addWidget(self._audio_br_label, r, 0, Qt.AlignmentFlag.AlignRight)
        self._audio_br_combo = QComboBox()
        self._audio_br_combo.addItems(
            ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]
        )
        self._audio_br_combo.setCurrentIndex(1)
        self._audio_br_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                           QSizePolicy.Policy.Fixed)
        form.addWidget(self._audio_br_combo, r, 1)

        self._set_audio_options_visible(False)
        form.setRowStretch(r + 1, 1)              # push rows to top

        # ── Trim Options ──
        r += 2
        self._trim_cb = QGroupBox("Trim / Cut (Optional)")
        self._trim_cb.setCheckable(True)
        self._trim_cb.setChecked(False)
        trim_lay = QHBoxLayout(self._trim_cb)
        
        trim_lay.addWidget(QLabel("Start:"))
        self._trim_start = QLineEdit("00:00:00")
        self._trim_start.setPlaceholderText("HH:MM:SS")
        trim_lay.addWidget(self._trim_start)
        
        trim_lay.addWidget(QLabel("End:"))
        self._trim_end = QLineEdit("00:01:00")
        self._trim_end.setPlaceholderText("HH:MM:SS")
        trim_lay.addWidget(self._trim_end)
        
        form.addWidget(self._trim_cb, r, 0, 1, 2)

        mid_row.addWidget(opts_group, 2)           # 40 % of width

        root.addLayout(mid_row, 1)                 # stretches vertically

        # ── 3) Output & Controls ──────────────────────────────────────
        ctrl_group = QGroupBox("Output && Controls")
        ctrl_group.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Fixed)
        ctrl_lay = QVBoxLayout(ctrl_group)
        ctrl_lay.setSpacing(8)

        # Directory row
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Save to:"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setText(get_default_download_dir())
        self._dir_edit.setMinimumHeight(34)
        dir_row.addWidget(self._dir_edit, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browseBtn")
        browse_btn.clicked.connect(self._browse_output)
        dir_row.addWidget(browse_btn)
        ctrl_lay.addLayout(dir_row)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._download_btn = QPushButton("⬇  Download")
        self._download_btn.setObjectName("downloadBtn")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download)
        btn_row.addWidget(self._download_btn)

        self._add_queue_btn = QPushButton("＋  Add to Queue")
        self._add_queue_btn.setObjectName("secondaryBtn")
        self._add_queue_btn.setEnabled(False)
        self._add_queue_btn.clicked.connect(self._on_add_to_queue)
        btn_row.addWidget(self._add_queue_btn)

        btn_row.addStretch(1)

        self._pause_btn = QPushButton("⏸  Pause")
        self._pause_btn.setObjectName("pauseBtn")
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self._on_pause_resume)
        btn_row.addWidget(self._pause_btn)

        self._cancel_btn = QPushButton("✕  Cancel")
        self._cancel_btn.setObjectName("cancelBtn")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)

        ctrl_lay.addLayout(btn_row)

        # Progress
        prog_row = QHBoxLayout()
        prog_row.setSpacing(12)

        prog_info = QVBoxLayout()
        self._progress_label = QLabel("Ready")
        self._progress_label.setObjectName("progressLabel")
        self._progress_label.setMinimumWidth(70)
        self._progress_label.setWordWrap(True)
        prog_info.addWidget(self._progress_label)

        self._speed_label = QLabel("")
        self._speed_label.setObjectName("statusLabel")
        prog_info.addWidget(self._speed_label)
        prog_row.addLayout(prog_info)

        bars = QVBoxLayout()
        self._file_progress = QProgressBar()
        self._file_progress.setRange(0, 100)
        self._file_progress.setValue(0)
        self._file_progress.setFormat("File: %p%")
        self._file_progress.setMinimumHeight(18)
        bars.addWidget(self._file_progress)

        self._overall_progress = QProgressBar()
        self._overall_progress.setRange(0, 100)
        self._overall_progress.setValue(0)
        self._overall_progress.setFormat("Overall: %p%")
        self._overall_progress.setMinimumHeight(18)
        bars.addWidget(self._overall_progress)
        prog_row.addLayout(bars, 1)

        ctrl_lay.addLayout(prog_row)
        root.addWidget(ctrl_group)

        # ── 4) Queue ──────────────────────────────────────────────────
        self._queue_view = QueueView()
        self._queue_view.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Expanding)
        self._queue_view.retry_requested.connect(self._process_queue)
        self._queue_view.start_queue_requested.connect(self._process_queue)
        root.addWidget(self._queue_view, 1)

        # ── Developer ────────────────────────────────────────────────
        dev_label = QLabel(
            "<a href='https://github.com/Dinesh-Das' style='text-decoration: none; color: inherit;'>Developed by Dinesh Das</a>"
        )
        dev_label.setObjectName("subtitleLabel")
        dev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_label.setOpenExternalLinks(True)
        root.addWidget(dev_label)

    # ══════════════════════════════════════════════════════════════════
    #  Status bar
    # ══════════════════════════════════════════════════════════════════

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    # ══════════════════════════════════════════════════════════════════
    #  Theme management
    # ══════════════════════════════════════════════════════════════════

    def _apply_theme(self, theme: str) -> None:
        filename = "dark_theme.qss" if theme == "dark" else "light_theme.qss"
        path = os.path.join(_THEMES_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                qss = fh.read()
            QApplication.instance().setStyleSheet(qss)
            is_dark = theme == "dark"
            self._theme_action.setText(
                "☀  Switch to Light Theme" if is_dark else "🌙  Switch to Dark Theme"
            )
            self._settings["theme"] = theme
            save_settings(self._settings)
        except OSError as exc:
            _log.error("Failed to load theme %s: %s", path, exc)

    def _toggle_theme(self) -> None:
        current = self._settings.get("theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        self._apply_theme(new_theme)

    # ══════════════════════════════════════════════════════════════════
    #  URL input handlers
    # ══════════════════════════════════════════════════════════════════

    def _paste_url(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self._url_edit.setText(text)
            # Find closest match to a URL if mixed text? For now just simple check
            if is_valid_url(text):
                self._on_fetch_info()

    @Slot()
    def _on_fetch_info(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            self._show_error("Please enter a Video URL or Search Query.")
            return

        # If it's NOT a valid URL, treat it as a search query
        if not is_valid_url(url):
            self._open_search_dialog(url)
            return

        self._fetch_btn.setEnabled(False)
        self._progress_label.setText("Fetching video info…")
        self._status_bar.showMessage("Fetching metadata…")
        self._reset_metadata_display()
        
        # Loading animation
        self._file_progress.setRange(0, 0)  # Indeterminate
        self._file_progress.setTextVisible(False)

        self._metadata_worker = MetadataWorker(url, parent=self)
        self._metadata_worker.signals.finished.connect(self._on_metadata_received)
        self._metadata_worker.signals.error.connect(self._on_metadata_error)
        self._metadata_worker.start()

    @Slot()
    def _on_clipboard_changed(self) -> None:
        """Monitor clipboard for new valid URLs."""
        text = QApplication.clipboard().text().strip()
        if not text or text == self._last_clipboard_text:
            return
        
        self._last_clipboard_text = text
        
        if is_valid_url(text):
            # If auto-download is ON, or if we just want to be helpful
            auto = self._settings.get("auto_download_on_paste", False)
            if auto:
                self._url_edit.setText(text)
                self._status_bar.showMessage("URL detected from clipboard! Fetching info...")
                self._on_fetch_info()
            else:
                if not self._url_edit.text():
                    self._url_edit.setText(text)
                    self._status_bar.showMessage("URL pasted from clipboard", 3000)

    @Slot(dict)
    def _on_metadata_received(self, data: Dict[str, Any]) -> None:
        self._current_metadata = data
        self._fetch_btn.setEnabled(True)
        self._download_btn.setEnabled(True)
        self._add_queue_btn.setEnabled(True)

        # Stop loading animation
        self._file_progress.setRange(0, 100)
        self._file_progress.setValue(0)
        self._file_progress.setTextVisible(True)

        # Title
        self._title_label.setText(data.get("title", "Unknown"))

        # Channel & duration
        self._channel_label.setText(f"Channel: {data.get('channel', '—')}")
        self._duration_label.setText(f"Duration: {data.get('duration_str', '—')}")

        # Thumbnail
        thumb_path = data.get("thumbnail_path")
        if thumb_path and os.path.isfile(thumb_path):
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                self._original_thumbnail = pixmap
                self._rescale_thumbnail()

        # ── Populate Resolutions ──
        self._res_combo.clear()
        formats = data.get("formats", [])
        
        # Gather unique resolutions
        resolutions = set()
        for f in formats:
            res = f.get("resolution")
            if res and res != "unknown" and res != "audio only":
                resolutions.add(res)
        
        # Sort them numerically descending (e.g. 2160p, 1080p, 720p...)
        def res_sort_key(r):
            try:
                return -int(r.replace("p", "").replace(" (4K)", ""))
            except ValueError:
                return 0
                
        sorted_res = sorted(resolutions, key=res_sort_key)
        
        if not sorted_res:
            # Fallback if no specific formats found (or playlist)
            sorted_res = ["Best Quality", "1080p", "720p", "480p", "360p"]
        else:
            # Always add "Best Quality" at top
            if "Best Quality" not in sorted_res:
                sorted_res.insert(0, "Best Quality")

        self._res_combo.addItems(sorted_res)

        # Apply preferred resolution/format from settings if possible
        pref_res = self._settings.get("preferred_resolution", "best")
        if pref_res == "best":
            self._res_combo.setCurrentIndex(0)
        else:
            # Try to match e.g. "1080p"
            idx = self._res_combo.findText(pref_res, Qt.MatchFlag.MatchContains)
            if idx >= 0:
                self._res_combo.setCurrentIndex(idx)
        
        pref_fmt = self._settings.get("preferred_format", "mp4")
        idx_fmt = self._format_combo.findText(pref_fmt, Qt.MatchFlag.MatchContains)
        if idx_fmt >= 0:
            self._format_combo.setCurrentIndex(idx_fmt)

        # Playlist info
        if data.get("is_playlist"):
            count = len(data.get("entries", []))
            self._progress_label.setText(
                f"Playlist detected: {count} video(s). Add to queue to download."
            )
            self._title_label.setText(f"📂 {data.get('playlist_title', data.get('title', ''))}")
        else:
            self._progress_label.setText("Ready to download")

        self._status_bar.showMessage("Metadata loaded", 5000)
        _log.info("Metadata displayed for: %s", data.get("title"))

        # Auto-download trigger
        if self._settings.get("auto_download_on_paste"):
             self._status_bar.showMessage("Auto-starting download...", 3000)
             self._on_download()

    @Slot(str)
    def _on_metadata_error(self, error_msg: str) -> None:
        self._fetch_btn.setEnabled(True)
        
        # Stop loading animation
        self._file_progress.setRange(0, 100)
        self._file_progress.setValue(0)
        self._file_progress.setTextVisible(True)
        
        self._progress_label.setText("")
        self._show_error(f"Failed to fetch info: {error_msg}")
        self._status_bar.showMessage("Metadata fetch failed", 5000)

    # ══════════════════════════════════════════════════════════════════
    #  Download actions
    # ══════════════════════════════════════════════════════════════════

    def _build_download_options(self) -> Dict[str, Any]:
        """Assemble a download options dict from current UI state."""
        opts: Dict[str, Any] = {
            "output_dir": self._dir_edit.text(),
            "retries": self._settings.get("retry_count", 3),
            "speed_limit": self._settings.get("speed_limit", ""),
            "proxy": self._settings.get("proxy", ""),
            "embed_metadata": True,
            # Subtitles
            "download_subtitles": self._settings.get("download_subtitles", False),
            "subtitle_langs": self._settings.get("subtitle_langs", "en,.*"),
            "embed_subtitles": self._settings.get("embed_subtitles", False),
        }

        dl_type = self._type_combo.currentText()
        if dl_type == "Audio Only":
            opts["audio_only"] = True
            opts["audio_format"] = self._audio_fmt_combo.currentText()
            bitrate = self._audio_br_combo.currentText().replace(" kbps", "")
            opts["audio_bitrate"] = bitrate
            opts["embed_thumbnail"] = True
        else:
            # Format
            opts["merge_output_format"] = self._format_combo.currentText()

            # Resolution filter
            res_text = self._res_combo.currentText()
            codec_text = self._codec_combo.currentText()

            fmt_selector = self._build_format_selector(res_text, codec_text, dl_type)
            opts["format"] = fmt_selector

        template = self._settings.get("naming_template", "{title}")
        yt_template = template.replace("{title}", "%(title)s") \
                              .replace("{channel}", "%(uploader)s") \
                              .replace("{resolution}", "%(height)sp") \
                              .replace("{date}", "%(upload_date)s")
        yt_template += ".%(ext)s"
        opts["output_template"] = yt_template

        # Trim options
        if self._trim_cb.isChecked():
            start_t = self._trim_start.text().strip()
            end_t = self._trim_end.text().strip()
            if start_t and end_t:
                opts["trim_start"] = start_t
                opts["trim_end"] = end_t
                opts["force_keyframes_at_cuts"] = True

        return opts

    @staticmethod
    def _build_format_selector(resolution: str, codec: str, dl_type: str) -> str:
        """Build a yt-dlp format selector string."""
        if resolution in ("Best Quality", ""):
            height_filter = ""
        else:
            h = resolution.replace("p", "").replace(" (4K)", "").strip()
            height_filter = f"[height<={h}]"

        codec_filter = ""
        if codec == "H.264 (avc1)":
            codec_filter = "[vcodec^=avc1]"
        elif codec == "VP9":
            codec_filter = "[vcodec^=vp9]"
        elif codec == "AV1":
            codec_filter = "[vcodec^=av01]"

        if dl_type == "Video Only":
            return f"bestvideo{height_filter}{codec_filter}"
        else:
            return (
                f"bestvideo{height_filter}{codec_filter}+bestaudio/best{height_filter}"
            )

    @Slot()
    def _on_download(self) -> None:
        try:
            if self._current_metadata is None:
                self._show_error("Fetch video info first.")
                return

            # Playlist → add all to queue and process
            if self._current_metadata.get("is_playlist"):
                self._on_add_to_queue()
                self._process_queue()
                return

            opts = self._build_download_options()
            url = self._current_metadata.get("url", self._url_edit.text().strip())
            self._start_download(url, opts)
        except Exception as exc:
            _log.exception("Error starting download")
            self._show_error(f"Error starting download: {exc}")

    @Slot()
    def _on_add_to_queue(self) -> None:
        try:
            if self._current_metadata is None:
                self._show_error("Fetch video info first.")
                return

            opts = self._build_download_options()

            if self._current_metadata.get("is_playlist"):
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                self._status_bar.showMessage("Processing playlist items...")
                try:
                    items = build_playlist_download_items(
                        self._current_metadata,
                        base_dir=self._dir_edit.text(),
                        download_options=opts,
                    )
                    if not items:
                        self._show_error("No videos found in playlist.")
                        return
                    self._queue_view.add_items(items)
                    self._status_bar.showMessage(
                        f"Added {len(items)} videos to queue", 3000
                    )
                finally:
                    QApplication.restoreOverrideCursor()
            else:
                url = self._current_metadata.get("url", self._url_edit.text().strip())
                title = self._current_metadata.get("title", url)
                self._queue_view.add_item(url=url, title=title, options=opts)
                self._status_bar.showMessage(f"Added to queue: {title}", 3000)
        except Exception as exc:
            _log.exception("Error adding to queue")
            self._show_error(f"Error adding to queue: {exc}")
        finally:
            QApplication.restoreOverrideCursor()

    def _start_download(self, url: str, opts: Dict[str, Any], queue_row: int = -1) -> None:
        """Start a single download worker."""
        worker = DownloadWorker(url, opts, parent=self)
        worker.signals.progress.connect(
            lambda d, r=queue_row: self._on_download_progress(d, r)
        )
        worker.signals.finished.connect(
            lambda path, r=queue_row: self._on_download_finished(path, r)
        )
        worker.signals.error.connect(
            lambda msg, r=queue_row: self._on_download_error(msg, r)
        )
        worker.signals.status_changed.connect(
            lambda s, r=queue_row: self._on_status_changed(s, r)
        )

        self._current_worker = worker
        self._download_workers.append(worker)
        self._active_downloads += 1

        self._download_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._file_progress.setValue(0)

        if queue_row >= 0:
            self._queue_view.set_status(queue_row, "Downloading")

        worker.start()
        self._status_bar.showMessage("Downloading…")

    def _process_queue(self) -> None:
        """Start the next queued item if concurrency allows."""
        max_conc = self._settings.get("max_concurrent_downloads", 3)
        while self._active_downloads < max_conc:
            row = self._queue_view.get_next_queued_row()
            if row is None:
                break
            item = self._queue_view.get_item(row)
            if item is None:
                break
            self._queue_view.set_status(row, "Starting")
            self._start_download(item.url, item.options, queue_row=row)

    # ── Progress / status callbacks ───────────────────────────────────

    @Slot(dict)
    def _on_download_progress(self, data: Dict[str, Any], queue_row: int) -> None:
        percent = data.get("percent", 0)
        speed = data.get("speed", 0)
        eta = data.get("eta", 0)

        self._file_progress.setValue(int(percent))

        # Speed string
        if speed and speed > 0:
            if speed >= 1_048_576:
                speed_str = f"{speed / 1_048_576:.1f} MB/s"
            else:
                speed_str = f"{speed / 1024:.0f} KB/s"
        else:
            speed_str = "—"

        # ETA string
        if eta and eta > 0:
            eta_m, eta_s = divmod(int(eta), 60)
            eta_str = f"{eta_m}:{eta_s:02d}"
        else:
            eta_str = "—"

        self._speed_label.setText(f"Speed: {speed_str}  |  ETA: {eta_str}")
        self._progress_label.setText(f"Downloading… {percent:.1f}%")

        # Update overall progress
        overall = self._queue_view.get_overall_progress()
        self._overall_progress.setValue(int(overall))

        if queue_row >= 0:
            self._queue_view.update_progress(queue_row, percent, "Downloading")

    @Slot(str)
    def _on_download_finished(self, filepath: str, queue_row: int) -> None:
        self._active_downloads = max(0, self._active_downloads - 1)
        self._file_progress.setValue(100)
        self._progress_label.setText("✓  Download complete!")
        self._speed_label.setText("")
        self._status_bar.showMessage(f"Saved: {filepath}", 8000)
        self._reset_controls()
        
        # Log to history
        title = "Unknown"
        # Try to get title from metadata or queue
        if self._current_metadata:
             title = self._current_metadata.get("title", "Unknown")
        elif queue_row >= 0:
             item = self._queue_view.get_item(queue_row)
             if item: title = item.title
             
        append_history(title, filepath, self._url_edit.text())

        if queue_row >= 0:
            self._queue_view.update_progress(queue_row, 100, "Complete")

        # Process next in queue
        self._process_queue()

    @Slot(str)
    def _on_download_error(self, msg: str, queue_row: int) -> None:
        self._active_downloads = max(0, self._active_downloads - 1)
        self._show_error(msg)
        self._progress_label.setText("Download failed")
        self._reset_controls()

        if queue_row >= 0:
            self._queue_view.set_status(queue_row, "Error")

        self._process_queue()

    @Slot(str)
    def _on_status_changed(self, status: str, queue_row: int) -> None:
        if status == "merging":
            self._progress_label.setText("Merging audio and video…")
        elif status == "paused":
            self._progress_label.setText("Paused")
        elif status == "cancelled":
            self._active_downloads = max(0, self._active_downloads - 1)
            self._progress_label.setText("Cancelled")
            self._file_progress.setValue(0)
            self._speed_label.setText("")
            self._reset_controls()
            if queue_row >= 0:
                self._queue_view.set_status(queue_row, "Cancelled")

    # ── Pause / Cancel ───────────────────────────────────────────────

    @Slot()
    def _on_pause_resume(self) -> None:
        if self._current_worker is None:
            return
        if self._pause_btn.text().startswith("⏸"):
            self._current_worker.pause()
            self._pause_btn.setText("▶  Resume")
        else:
            self._current_worker.resume()
            self._pause_btn.setText("⏸  Pause")

    @Slot()
    def _on_cancel(self) -> None:
        if self._current_worker is not None:
            self._current_worker.cancel()
            self._current_worker = None

    # ── Helpers
    
    def _reset_controls(self) -> None:
        self._download_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._pause_btn.setText("⏸  Pause")

    def _reset_metadata_display(self) -> None:
        self._current_metadata = None
        self._title_label.setText("Video title will appear here")
        self._channel_label.setText("Channel: —")
        self._duration_label.setText("Duration: —")
        self._thumbnail_label.setText("No thumbnail")
        self._thumbnail_label.setPixmap(QPixmap())  # clear
        self._res_combo.clear()

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec():
            # Reload settings
            self._settings = load_settings()
            self._apply_theme(self._settings.get("theme", "dark"))
            
    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self._dir_edit.setText(path)

    def _open_search_dialog(self, query: str) -> None:
        """Open search dialog with the given query."""
        dlg = SearchDialog(self)
        dlg.video_selected.connect(self._on_search_selection)
        dlg.set_query(query)
        dlg.exec()

    def _on_search_selection(self, url: str) -> None:
        self._url_edit.setText(url)
        # Auto-fetch info for the selected URL
        self._on_fetch_info()
    
    # ── Scheduler ────────────────────────────────────────────────────

    def _check_schedule(self) -> None:
        """Check for due downloads in the queue."""
        due_indices = self._queue_view.get_due_items_indices()
        if due_indices:
            _log.info("Scheduler found %d items due.", len(due_indices))
            for idx in due_indices:
                # Reset status to queued/ready so process_queue picks it up
                self._queue_view.clear_schedule(idx)
            
            # Trigger processing
            self._process_queue()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About ClipSync",
            "<h2>ClipSync</h2>"
            "<p>A modern desktop video downloader powered by "
            "<b>yt-dlp</b> and <b>PySide6</b>.</p>"
            "<p>Supports YouTube, Instagram, TikTok, Twitch, and many more.</p>"
            "<p>Developed with ❤️ using Python.</p>"
        )

    def _show_history(self) -> None:
        dlg = HistoryDialog(self)
        dlg.exec()

    # ── Drag & Drop ──────────────────────────────────────────────────

    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:  # noqa: N802
        url = ""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                url = urls[0].toString()
        elif event.mimeData().hasText():
            url = event.mimeData().text()
            
        if url:
            # Clean up potential file:// prefix or whitespace
            url = url.strip()
            if url.startswith("file:///"):
                pass
            
            if is_valid_url(url):
                self._url_edit.setText(url)
                self._status_bar.showMessage("URL dropped! Fetching info...")
                
                # Auto-fetch
                if self._settings.get("auto_download_on_paste"):
                    self._on_fetch_info()
                else:
                    self._on_fetch_info()
            else:
                 self._show_error("Dropped content is not a valid video URL.")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle application closure: cancel downloads and stop threads."""
        _log.info("Application closing...")
        self._scheduler_timer.stop()
        
        # Cancel all active workers
        running_workers = [w for w in self._download_workers if w.isRunning()]
        if running_workers:
            # Signal cancellation
            for worker in running_workers:
                worker.cancel()
            
            # Give them a moment to exit gracefully? 
            # Blocking UI for too long is bad, but "QThread Destroyed" is also bad.
            # We'll wait a brief moment. 
            # Ideally, we would hide the window and wait in background, but simple wait is safer for now.
            for worker in running_workers:
                worker.wait(1000) 

        event.accept()
    
    # ── Dynamic resize handling ──────────────────────────────────────

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Re-scale thumbnail when the window is resized."""
        super().resizeEvent(event)
        self._rescale_thumbnail()

    def _rescale_thumbnail(self) -> None:
        """Scale the stored original thumbnail to fit the current label size."""
        if self._original_thumbnail is None or self._original_thumbnail.isNull():
            return
        label_size = self._thumbnail_label.size()
        scaled = self._original_thumbnail.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumbnail_label.setPixmap(scaled)

    def _set_audio_options_visible(self, visible: bool) -> None:
        self._audio_fmt_combo.setVisible(visible)
        self._audio_fmt_row_label.setVisible(visible)
        self._audio_br_combo.setVisible(visible)
        self._audio_br_label.setVisible(visible)
        # Hide video-specific widgets when audio only
        self._format_label.setVisible(not visible)
        self._format_combo.setVisible(not visible)
        self._res_label.setVisible(not visible)
        self._res_combo.setVisible(not visible)
        self._codec_label.setVisible(not visible)
        self._codec_combo.setVisible(not visible)

    @Slot(str)
    def _on_type_changed(self, text: str) -> None:
        is_audio = text == "Audio Only"
        self._set_audio_options_visible(is_audio)

    def _show_about(self) -> None:
        """Show the About dialog."""
        QMessageBox.about(
            self,
            "About ClipSync",
            """<h3>ClipSync v1.1.0</h3>
            <p><b>Developed by Dinesh Das</b><br>
            Senior Software Engineer at Asian Paints</p>
            <p>
                <a href='https://github.com/Dinesh-Das'>GitHub</a> &nbsp;|&nbsp; 
                <a href='https://www.linkedin.com/in/dineshdas1016/'>LinkedIn</a> &nbsp;|&nbsp; 
                <a href='https://x.com/DineshDas_'>Twitter</a>
            </p>
            <p>A premium YouTube video downloader built with Python & PySide6.</p>
            <p>Icons by <a href='https://icons8.com'>Icons8</a></p>"""
        )
