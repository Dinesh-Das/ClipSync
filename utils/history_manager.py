import json
import os
from datetime import datetime
from typing import List, Dict, Any

from utils.file_utils import get_app_data_dir

_HISTORY_FILE = "history.json"

def get_history_file() -> str:
    return os.path.join(get_app_data_dir(), _HISTORY_FILE)

def load_history() -> List[Dict[str, Any]]:
    path = get_history_file()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

def append_history(title: str, filepath: str, url: str) -> None:
    history = load_history()
    entry = {
        "title": title,
        "filepath": filepath,
        "url": url,
        "date": datetime.now().isoformat(),
        "exists": os.path.exists(filepath)
    }
    history.insert(0, entry)  # Newest first
    # Limit to last 1000?
    if len(history) > 1000:
        history = history[:1000]
        
    try:
        with open(get_history_file(), "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except OSError:
        pass

def clear_history() -> None:
    try:
        with open(get_history_file(), "w", encoding="utf-8") as f:
            json.dump([], f)
    except OSError:
        pass
