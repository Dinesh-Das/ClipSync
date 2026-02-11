"""
Logging configuration for the YouTube Video Downloader.

Provides a rotating file logger and console output with configurable levels.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


_LOG_DIR: str = os.path.join(os.path.expanduser("~"), ".yt_downloader", "logs")
_LOG_FILE: str = os.path.join(_LOG_DIR, "app.log")
_MAX_BYTES: int = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT: int = 3
_initialized: bool = False


def _ensure_log_dir() -> None:
    """Create the log directory if it doesn't exist."""
    os.makedirs(_LOG_DIR, exist_ok=True)


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Initialize the root logger with a rotating file handler and a console handler.

    Args:
        level: The logging level for the file handler.
    """
    global _initialized
    if _initialized:
        return

    _ensure_log_dir()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Formatter
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — captures everything at DEBUG level
    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    # Console handler — only WARNING and above to keep terminal clean
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)
    root_logger.addHandler(console_handler)

    _initialized = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Return a named logger. Initializes logging on first call.

    Args:
        name: Logger name (usually ``__name__`` of the calling module).

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
