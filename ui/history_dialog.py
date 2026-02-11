from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from utils.history_manager import load_history, clear_history

class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download History")
        self.resize(700, 400)
        
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Date", "Title", "File Path"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.itemDoubleClicked.connect(self._open_file)
        layout.addWidget(self._table)
        
        btns = QHBoxLayout()
        
        open_btn = QPushButton("Open File")
        open_btn.clicked.connect(lambda: self._open_file(None))
        btns.addWidget(open_btn)
        
        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self._clear_data)
        btns.addWidget(clear_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        
        layout.addLayout(btns)

    def _load_data(self):
        data = load_history()
        self._table.setRowCount(len(data))
        for i, item in enumerate(data):
            date_str = item.get("date", "")[:16].replace("T", " ")
            self._table.setItem(i, 0, QTableWidgetItem(date_str))
            
            self._table.setItem(i, 1, QTableWidgetItem(item.get("title", "")))
            
            path_item = QTableWidgetItem(item.get("filepath", ""))
            path_item.setToolTip(item.get("filepath", ""))
            self._table.setItem(i, 2, path_item)
            
            # Store full path in user role
            self._table.item(i, 0).setData(Qt.UserRole, item)

    def _open_file(self, item):
        row = self._table.currentRow()
        if row < 0:
            return
        
        data = self._table.item(row, 0).data(Qt.UserRole)
        filepath = data.get("filepath")
        if filepath:
            QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))

    def _clear_data(self):
        clear_history()
        self._load_data()
