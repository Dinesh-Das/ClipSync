import re

# YouTube video/playlist regex
YT_VIDEO_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
YT_PLAYLIST_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/playlist\?list=([^&=%\?]+)')

def is_valid_url(url: str) -> bool:
    """Check if the given string is a valid URL."""
    # Simple check for now
    return url.startswith("http://") or url.startswith("https://")

def is_playlist_url(url: str) -> bool:
    """Check if the given URL is a playlist."""
    return bool(YT_PLAYLIST_REGEX.search(url))

def sanitize_filename(filename: str) -> str:
    """Remove illegal characters from filename."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)
