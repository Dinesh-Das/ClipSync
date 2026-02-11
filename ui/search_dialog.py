"""
Search dialog for YouTube video search.

Provides a search input, displays results with thumbnails/duration/views,
and allows selecting a video URL to paste into the main window.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QSize, Slot
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLineEdit,
    QAbstractItemView,
    QProgressBar,
    QWidget,
)
from PySide6.QtGui import QIcon, QPixmap, QFont


def _format_duration(seconds: Optional[int]) -> str:
    """Convert seconds to a nice string."""
    if not seconds:
        return ""
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_views(count: Optional[int]) -> str:
    """Convert view count to human-readable string."""
    if not count:
        return ""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B views"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M views"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K views"
    return f"{count} views"


class SearchDialog(QDialog):
    """Dialog to search for videos and select one."""

    video_selected = Signal(str)  # Emits the selected URL

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍  Search YouTube")
        self.resize(700, 550)
        self.setModal(True)
        
        self._results: List[Dict[str, Any]] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("Search YouTube")
        header.setObjectName("titleLabel")
        layout.addWidget(header)
        
        # Search Bar
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        self._search_input = QLineEdit()
        self._search_input.setObjectName("urlInput")
        self._search_input.setPlaceholderText("Enter search query...")
        self._search_input.setMinimumHeight(40)
        self._search_input.returnPressed.connect(self._on_search)
        top_layout.addWidget(self._search_input)
        
        self._search_btn = QPushButton("🔍  Search")
        self._search_btn.setObjectName("fetchBtn")
        self._search_btn.clicked.connect(self._on_search)
        top_layout.addWidget(self._search_btn)
        layout.addLayout(top_layout)
        
        # Loading bar
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)  # indeterminate
        self._loading_bar.setMaximumHeight(4)
        self._loading_bar.setTextVisible(False)
        self._loading_bar.hide()
        layout.addWidget(self._loading_bar)
        
        # Status
        self._status_label = QLabel("")
        self._status_label.setObjectName("subtitleLabel")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)
        
        # Results List
        self._list_view = QListWidget()
        self._list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list_view.setIconSize(QSize(120, 68))
        self._list_view.setSpacing(4)
        self._list_view.itemDoubleClicked.connect(self._on_item_selected)
        layout.addWidget(self._list_view)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._select_btn = QPushButton("✓  Select")
        self._select_btn.setObjectName("downloadBtn")
        self._select_btn.setEnabled(False)
        self._select_btn.clicked.connect(self._on_select_clicked)
        btn_layout.addWidget(self._select_btn)
        
        self._close_btn = QPushButton("Close")
        self._close_btn.setObjectName("secondaryBtn")
        self._close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._close_btn)
        
        layout.addLayout(btn_layout)
        
        # Handle selection change
        self._list_view.itemSelectionChanged.connect(self._on_selection_changed)

    def set_query(self, query: str):
        self._search_input.setText(query)
        self._on_search()

    def _on_search(self):
        query = self._search_input.text().strip()
        if not query:
            return
            
        self._list_view.clear()
        self._results.clear()
        self._status_label.setText("Searching...")
        self._search_btn.setEnabled(False)
        self._select_btn.setEnabled(False)
        self._loading_bar.show()
        
        from core.metadata import SearchWorker
        
        self._worker = SearchWorker(query, self)
        self._worker.signals.finished.connect(self._on_results)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    @Slot(list)
    def _on_results(self, results):
        self._search_btn.setEnabled(True)
        self._loading_bar.hide()
        self._status_label.setText(f"Found {len(results)} results")
        self._results = results
        
        for item in results:
            title = item.get("title", "Unknown")
            channel = item.get("channel", "Unknown")
            duration = _format_duration(item.get("duration"))
            views = _format_views(item.get("view_count"))
            
            # Build rich label text
            parts = [title]
            meta_parts = []
            if channel:
                meta_parts.append(channel)
            if duration:
                meta_parts.append(f"⏱ {duration}")
            if views:
                meta_parts.append(f"👁 {views}")
            
            label = f"{title}\n{'  •  '.join(meta_parts)}"
            
            list_item = QListWidgetItem(label)
            list_item.setToolTip(item.get("url", ""))
            
            # Set a size hint for better spacing
            list_item.setSizeHint(QSize(0, 56))
            
            self._list_view.addItem(list_item)

    @Slot(str)
    def _on_error(self, msg):
        self._search_btn.setEnabled(True)
        self._loading_bar.hide()
        self._status_label.setText(f"Error: {msg}")

    def _on_selection_changed(self):
        self._select_btn.setEnabled(len(self._list_view.selectedItems()) > 0)

    def _on_item_selected(self, item):
        self._on_select_clicked()

    def _on_select_clicked(self):
        row = self._list_view.currentRow()
        if row >= 0 and row < len(self._results):
            url = self._results[row].get("url")
            if url:
                self.video_selected.emit(url)
                self.accept()
