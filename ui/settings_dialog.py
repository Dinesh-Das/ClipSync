"""
Settings dialog for the YouTube Video Downloader.

Tabbed dialog for configuring general, network, and audio preferences.
All values are persisted via :mod:`utils.file_utils`.
"""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from utils.file_utils import load_settings, save_settings, DEFAULT_SETTINGS


class SettingsDialog(QDialog):
    """Modal settings dialog with General / Network / Audio tabs."""

    settings_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 480)
        self._settings: Dict[str, Any] = load_settings()
        self._build_ui()
        self._populate()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # --- General tab ---
        general = QWidget()
        g_layout = QFormLayout(general)
        g_layout.setSpacing(12)
        g_layout.setContentsMargins(16, 16, 16, 16)

        # Download directory
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        dir_row.addWidget(self._dir_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browseBtn")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        g_layout.addRow("Download folder:", dir_row)

        # Naming template
        self._template_edit = QLineEdit()
        self._template_edit.setPlaceholderText("{title}")
        self._template_edit.setToolTip(
            "Placeholders: {title}, {channel}, {resolution}, {date}"
        )
        g_layout.addRow("File naming:", self._template_edit)

        # Preferred format
        self._format_combo = QComboBox()
        self._format_combo.addItems(["mp4", "mkv", "webm"])
        g_layout.addRow("Preferred format:", self._format_combo)

        # Preferred resolution
        self._res_combo = QComboBox()
        self._res_combo.addItems(
            ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "144p"]
        )
        g_layout.addRow("Preferred resolution:", self._res_combo)

        # Auto-download on paste
        self._auto_dl_check = QCheckBox("Start download when URL is pasted")
        g_layout.addRow(self._auto_dl_check)

        # Theme
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["dark", "light"])
        g_layout.addRow("Theme:", self._theme_combo)

        # Retry count
        self._retry_spin = QSpinBox()
        self._retry_spin.setRange(0, 10)
        g_layout.addRow("Retry count:", self._retry_spin)

        self._tabs.addTab(general, "General")

        # --- Network tab ---
        network = QWidget()
        n_layout = QFormLayout(network)
        n_layout.setSpacing(12)
        n_layout.setContentsMargins(16, 16, 16, 16)

        self._concurrent_spin = QSpinBox()
        self._concurrent_spin.setRange(1, 10)
        n_layout.addRow("Max concurrent downloads:", self._concurrent_spin)

        self._speed_edit = QLineEdit()
        self._speed_edit.setPlaceholderText("e.g. 5M  (empty = unlimited)")
        n_layout.addRow("Speed limit:", self._speed_edit)

        self._proxy_edit = QLineEdit()
        self._proxy_edit.setPlaceholderText("http://proxy:port")
        n_layout.addRow("Proxy:", self._proxy_edit)

        self._tabs.addTab(network, "Network")


        # --- Audio tab ---
        audio = QWidget()
        a_layout = QFormLayout(audio)
        a_layout.setSpacing(12)
        a_layout.setContentsMargins(16, 16, 16, 16)

        self._audio_fmt_combo = QComboBox()
        self._audio_fmt_combo.addItems(["mp3", "m4a", "wav", "opus", "flac"])
        a_layout.addRow("Audio format:", self._audio_fmt_combo)

        self._bitrate_combo = QComboBox()
        self._bitrate_combo.addItems(["128", "192", "256", "320"])
        a_layout.addRow("Audio bitrate (kbps):", self._bitrate_combo)

        self._tabs.addTab(audio, "Audio")

        # --- Subtitles tab ---
        subs = QWidget()
        s_layout = QFormLayout(subs)
        s_layout.setSpacing(12)
        s_layout.setContentsMargins(16, 16, 16, 16)

        self._dl_subs_check = QCheckBox("Download Subtitles")
        s_layout.addRow(self._dl_subs_check)

        self._subs_langs_edit = QLineEdit()
        self._subs_langs_edit.setPlaceholderText("en,.*")
        self._subs_langs_edit.setToolTip("Comma-separated language codes (regex supported)")
        s_layout.addRow("Languages:", self._subs_langs_edit)

        self._embed_subs_check = QCheckBox("Embed Subtitles")
        self._embed_subs_check.setToolTip("Embed subtitles into the video file if possible")
        s_layout.addRow(self._embed_subs_check)

        self._tabs.addTab(subs, "Subtitles")

        # --- Button box ---
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ── Data handling ────────────────────────────────────────────────

    def _populate(self) -> None:
        """Fill widgets from current settings dict."""
        s = self._settings
        self._dir_edit.setText(s.get("download_dir", DEFAULT_SETTINGS["download_dir"]))
        self._template_edit.setText(s.get("naming_template", "{title}"))
        self._format_combo.setCurrentText(s.get("preferred_format", "mp4"))
        self._res_combo.setCurrentText(s.get("preferred_resolution", "best"))
        self._auto_dl_check.setChecked(s.get("auto_download_on_paste", False))
        self._theme_combo.setCurrentText(s.get("theme", "dark"))
        self._retry_spin.setValue(s.get("retry_count", 3))
        self._concurrent_spin.setValue(s.get("max_concurrent_downloads", 3))
        self._speed_edit.setText(s.get("speed_limit", ""))
        self._proxy_edit.setText(s.get("proxy", ""))
        self._audio_fmt_combo.setCurrentText(s.get("preferred_audio_format", "mp3"))
        self._bitrate_combo.setCurrentText(s.get("preferred_audio_bitrate", "192"))
        
        # Subtitles
        self._dl_subs_check.setChecked(s.get("download_subtitles", False))
        self._subs_langs_edit.setText(s.get("subtitle_langs", "en,.*"))
        self._embed_subs_check.setChecked(s.get("embed_subtitles", False))

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if path:
            self._dir_edit.setText(path)

    def _save(self) -> None:
        self._settings.update({
            "download_dir": self._dir_edit.text(),
            "naming_template": self._template_edit.text() or "{title}",
            "preferred_format": self._format_combo.currentText(),
            "preferred_resolution": self._res_combo.currentText(),
            "auto_download_on_paste": self._auto_dl_check.isChecked(),
            "theme": self._theme_combo.currentText(),
            "retry_count": self._retry_spin.value(),
            "max_concurrent_downloads": self._concurrent_spin.value(),
            "speed_limit": self._speed_edit.text().strip(),
            "proxy": self._proxy_edit.text().strip(),
            "preferred_audio_format": self._audio_fmt_combo.currentText(),
            "preferred_audio_bitrate": self._bitrate_combo.currentText(),
            "download_subtitles": self._dl_subs_check.isChecked(),
            "subtitle_langs": self._subs_langs_edit.text() or "en,.*",
            "embed_subtitles": self._embed_subs_check.isChecked(),
        })
        save_settings(self._settings)
        self.settings_changed.emit(self._settings)
        self.accept()
