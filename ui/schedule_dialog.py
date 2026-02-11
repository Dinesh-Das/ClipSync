from PySide6.QtWidgets import QDialog, QVBoxLayout, QDateTimeEdit, QPushButton, QLabel, QHBoxLayout
from PySide6.QtCore import QDateTime, Qt

class ScheduleDialog(QDialog):
    """Dialog to pick a date and time for scheduling."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule Download")
        self.resize(300, 150)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Start download at:"))
        
        self.dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_edit.setCalendarPopup(True)
        layout.addWidget(self.dt_edit)
        
        btns = QHBoxLayout()
        ok_btn = QPushButton("Schedule")
        ok_btn.clicked.connect(self.accept)
        btns.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        
        layout.addLayout(btns)
        
    def get_datetime(self) -> QDateTime:
        return self.dt_edit.dateTime()
