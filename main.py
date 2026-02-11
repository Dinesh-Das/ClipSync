"""
YT Video Downloader — Entry Point

Launch the PySide6 application, apply the saved theme, and show the main window.
Includes auto-detection for FFmpeg to handle PATH issues.
"""

import sys
import os
import shutil
import glob
from typing import List

# Ensure project root is on the path so relative imports work when run
# directly via ``python main.py``.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from core.logger import setup_logging
from ui.main_window import MainWindow


def _ensure_ffmpeg() -> None:
    """
    Check if ffmpeg is in PATH. If not, try to find it in common locations
    and add it to PATH for this process.
    """
    if shutil.which("ffmpeg"):
        return

    # Potential locations to search
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    user_profile = os.environ.get("USERPROFILE", "")
    
    search_patterns = []
    
    # Check bundled paths if frozen (PyInstaller)
    if getattr(sys, 'frozen', False):
        # Onedir: ffmpeg is in the same folder as the exe
        search_patterns.append(os.path.dirname(sys.executable))
        # Onefile: unpacks to _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            search_patterns.append(sys._MEIPASS)

    search_patterns.extend([
        # Standard installs
        r"C:\Program Files\ffmpeg\bin",
        r"C:\ffmpeg\bin",
        # Winget packages (recursive search pattern)
        os.path.join(local_app_data, r"Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin"),
        os.path.join(local_app_data, r"Microsoft\WinGet\Links"), 
        # User local bin
        os.path.join(user_profile, "bin"),
    ])

    print("Searching for FFmpeg...")
    for pattern in search_patterns:
        # Resolve globs (e.g. for versioned folders)
        found_dirs = glob.glob(pattern)
        for d in found_dirs:
            exe_path = os.path.join(d, "ffmpeg.exe")
            if os.path.isfile(exe_path):
                print(f"Found ffmpeg at {d}, adding to PATH...")
                os.environ["PATH"] += os.pathsep + d
                return

    print("WARNING: FFmpeg not found. Video merging and audio conversion may fail.")


def main() -> None:
    """Application entry point."""
    setup_logging()
    _ensure_ffmpeg()

    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ClipSync")
    app.setOrganizationName("ClipSync")
    app.setApplicationVersion("1.1.0")
    
    # Set App Icon
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "OP.jpg")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
