"""yt-dlp 解析 YouTube 所需的 JS 运行时（deno）检测"""

import shutil
import sys
from urllib.parse import urlparse

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


def is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS)


def has_deno() -> bool:
    return shutil.which("deno") is not None


def deno_install_command() -> str:
    if sys.platform == "darwin":
        return "brew install deno"
    if sys.platform == "win32":
        return "winget install DenoLand.Deno"
    return "curl -fsSL https://deno.land/install.sh | sh"


def needs_deno(url: str) -> bool:
    """YouTube 链接且本机没有 deno 时返回 True"""
    return is_youtube_url(url) and not has_deno()
