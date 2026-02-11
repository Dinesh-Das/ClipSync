"""
Queue management widget.
Displays a list of downloads with progress bars and status.
"""

from __future__ import annotations

import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QByteArray, QDateTime
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QProgressBar,
)

from ui.schedule_dialog import ScheduleDialog
from utils.file_utils import save_queue_to_disk, load_queue_from_disk


class QueueItem:
    """Represents a single download task in the queue."""
    def __init__(self, url: str, title: str, options: Dict[str, Any], status: str = "Queued", progress: float = 0.0):
        self.url = url
        self.title = title
        self.options = options
        self.status = status
        self.progress = progress
        self.scheduled_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "options": self.options,
            "status": self.status,
            "progress": self.progress,
            "scheduled_time": self.scheduled_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QueueItem:
        item = cls(
            url=data["url"],
            title=data.get("title", ""),
            options=data.get("options", {}),
            status=data.get("status", "Queued"),
            progress=data.get("progress", 0.0),
        )
        item.scheduled_time = data.get("scheduled_time")
        return item


class QueueView(QWidget):
    """Widget managing the download queue table."""

    retry_requested = Signal()        # Emitted when retry action triggered
    start_queue_requested = Signal()  # "Start All"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items: List[QueueItem] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Controls row
        controls = QHBoxLayout()
        
        self._start_queue_btn = QPushButton("▶ Start All")
        self._start_queue_btn.clicked.connect(self.start_queue_requested.emit)
        controls.addWidget(self._start_queue_btn)
        
        self._schedule_btn = QPushButton("🕓 Schedule")
        self._schedule_btn.setObjectName("secondaryBtn")
        self._schedule_btn.clicked.connect(self._schedule_selected)
        controls.addWidget(self._schedule_btn)

        self._retry_failed_btn = QPushButton("⟳ Retry Failed")
        self._retry_failed_btn.setObjectName("secondaryBtn")
        self._retry_failed_btn.clicked.connect(self._retry_all_failed)
        controls.addWidget(self._retry_failed_btn)
        
        controls.addSpacing(12)

        self._move_up_btn = QPushButton("▲ Move Up")
        self._move_up_btn.clicked.connect(self._move_up)
        controls.addWidget(self._move_up_btn)

        self._move_down_btn = QPushButton("▼ Move Down")
        self._move_down_btn.clicked.connect(self._move_down)
        controls.addWidget(self._move_down_btn)

        self._remove_btn = QPushButton("✕ Remove")
        self._remove_btn.clicked.connect(self._remove_selected)
        controls.addWidget(self._remove_btn)
        
        controls.addStretch()

        self._clear_completed_btn = QPushButton("Clear Completed")
        self._clear_completed_btn.clicked.connect(self._clear_completed)
        self._clear_completed_btn.setObjectName("secondaryBtn")
        controls.addWidget(self._clear_completed_btn)

        layout.addLayout(controls)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Title", "Status", "Progress"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self._table)

    def add_item(self, url: str, title: str, options: Dict[str, Any]) -> None:
        item = QueueItem(url, title, options)
        self._items.append(item)
        self._rebuild_table()
        self._save_queue()

    def add_items(self, items_data: List[Dict[str, Any]]) -> None:
        for d in items_data:
            self._items.append(QueueItem(d["url"], d["title"], d["options"]))
        self._rebuild_table()
        self._save_queue()

    def get_next_queued_row(self) -> Optional[int]:
        """Find the first item with 'Queued' status."""
        for i, item in enumerate(self._items):
            if item.status == "Queued":
                return i
        return None

    def get_item(self, row: int) -> Optional[QueueItem]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def update_progress(self, row: int, percent: float, status: Optional[str] = None) -> None:
        if 0 <= row < len(self._items):
            item = self._items[row]
            item.progress = percent
            if status:
                item.status = status
            
            # Update UI directly to avoid full rebuild
            self._table.setItem(row, 1, QTableWidgetItem(item.status))
            pb = self._table.cellWidget(row, 2)
            if isinstance(pb, QProgressBar):
                pb.setValue(int(percent))
            else:
                # Fallback if widget missing
                self._rebuild_table()

    def set_status(self, row: int, status: str) -> None:
        if 0 <= row < len(self._items):
            item = self._items[row]
            item.status = status
            self._table.setItem(row, 1, QTableWidgetItem(status))
            self._save_queue()

    def get_overall_progress(self) -> float:
        if not self._items:
            return 0.0
        total = sum(it.progress for it in self._items)
        return total / len(self._items)

    def load_items(self, items_dicts: List[Dict[str, Any]]) -> None:
        self._items = [QueueItem.from_dict(d) for d in items_dicts]
        self._rebuild_table()

    def get_items_dicts(self) -> List[Dict[str, Any]]:
        return [it.to_dict() for it in self._items]

    # ── Internal ──────────────────────────────────────────────────────

    def _rebuild_table(self) -> None:
        self._table.setRowCount(0)
        for i, item in enumerate(self._items):
            self._table.insertRow(i)
            self._table.setItem(i, 0, QTableWidgetItem(item.title))
            self._table.setItem(i, 1, QTableWidgetItem(item.status))
            
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setValue(int(item.progress))
            # Text visible?
            pb.setTextVisible(True)
            self._table.setCellWidget(i, 2, pb)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu()
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(self._remove_selected)
        menu.addAction(remove_action)
        
        retry_action = QAction("Retry", self)
        retry_action.triggered.connect(self._retry_selected)
        menu.addAction(retry_action)
        
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _remove_selected(self) -> None:
        rows = self._get_selected_rows()
        if not rows:
            return
        # Removed in reverse order to keep indices valid
        for r in sorted(rows, reverse=True):
            del self._items[r]
        self._rebuild_table()
        self._save_queue()

    def _retry_selected(self) -> None:
        rows = self._get_selected_rows()
        for r in rows:
            self.set_status(r, "Queued")
            self.update_progress(r, 0.0)
        
        if rows:
            self.retry_requested.emit()

    def _move_up(self) -> None:
        rows = self._get_selected_rows()
        if not rows or len(rows) > 1: 
            return # Simple single-item move for now
        
        row = rows[0]
        if row > 0:
            self._items[row], self._items[row-1] = self._items[row-1], self._items[row]
            self._rebuild_table()
            self._table.selectRow(row - 1)
            self._save_queue()

    def _move_down(self) -> None:
        rows = self._get_selected_rows()
        if not rows or len(rows) > 1:
            return
        
        row = rows[0]
        if row < len(self._items) - 1:
            self._items[row], self._items[row+1] = self._items[row+1], self._items[row]
            self._rebuild_table()
            self._table.selectRow(row + 1)
            self._save_queue()

    def _get_selected_rows(self) -> List[int]:
        return [idx.row() for idx in self._table.selectionModel().selectedRows()]

    def _save_queue(self) -> None:
        save_queue_to_disk(self.get_items_dicts())

    def _clear_completed(self) -> None:
        self._items = [it for it in self._items if it.status not in ("Complete", "Error", "Cancelled")]
        self._rebuild_table()
        self._save_queue()

    def _retry_all_failed(self) -> None:
        """Retry all items with Error or Cancelled status."""
        any_retried = False
        for i, item in enumerate(self._items):
            if item.status in ("Error", "Cancelled"):
                item.status = "Queued"
                item.progress = 0.0
                self.update_progress(i, 0.0, "Queued")
                any_retried = True
        
        if any_retried:
            self.retry_requested.emit()

    def _schedule_selected(self) -> None:
        """Schedule the selected item."""
        rows = self._get_selected_rows()
        if not rows:
            return
        
        # Taking the first one for simplicity or we could schedule batch
        row = rows[0]
        item = self._items[row]
        
        dlg = ScheduleDialog(self)
        if dlg.exec():
            dt = dlg.get_datetime()
            # Must be in future
            if dt < QDateTime.currentDateTime():
                QMessageBox.warning(self, "Invalid Time", "Please select a time in the future.")
                return
            
            timestamp = dt.toMSecsSinceEpoch() / 1000.0
            item.scheduled_time = timestamp
            item.status = f"Scheduled: {dt.toString('HH:mm')}"
            self.set_status(row, item.status)
            self._save_queue()

    def get_due_items_indices(self) -> List[int]:
        """Return indices of items that are scheduled and due."""
        now = datetime.now().timestamp()
        indices = []
        for i, item in enumerate(self._items):
            if item.scheduled_time and item.scheduled_time <= now:
                if "Scheduled" in item.status:
                     indices.append(i)
        return indices

    def clear_schedule(self, index: int) -> None:
        if 0 <= index < len(self._items):
            item = self._items[index]
            item.scheduled_time = None
            item.status = "Queued"  # Ready to run now
            self.set_status(index, "Queued")
            # We don't save here to avoid excessive writes, caller handles
