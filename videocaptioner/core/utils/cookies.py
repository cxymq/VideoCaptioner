"""视频下载 Cookie 配置：从 cookies.txt 文件或直接从浏览器读取"""

from pathlib import Path
from typing import Any, Dict, Optional

from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("cookies")

# yt-dlp 支持从这些浏览器读取 Cookie（显示名 -> yt-dlp 名称）
SUPPORTED_BROWSERS = {
    "Chrome": "chrome",
    "Edge": "edge",
    "Firefox": "firefox",
    "Safari": "safari",
    "Brave": "brave",
    "Chromium": "chromium",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
}

COOKIE_ERROR_KEYWORDS = ("cookie", "sign in", "login", "登录")


def apply_cookie_options(
    ydl_opts: Dict[str, Any],
    browser: Optional[str] = None,
    cookie_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """把 Cookie 配置写入 yt-dlp 选项

    选了浏览器时只从浏览器读取，不再传 cookie_file：yt-dlp 退出时会把
    内存中的全部 Cookie 回写到 cookiefile，两者同时设置会把浏览器里
    所有网站的 Cookie 写进 cookies.txt。
    """
    browser_name = (browser or "").strip().lower()
    if browser_name:
        if browser_name not in SUPPORTED_BROWSERS.values():
            raise ValueError(
                f"Unsupported browser '{browser}', choose from: {', '.join(SUPPORTED_BROWSERS.values())}"
            )
        logger.info(f"Reading cookies from browser: {browser_name}")
        ydl_opts["cookiesfrombrowser"] = (browser_name, None, None, None)
    elif cookie_file and Path(cookie_file).exists():
        logger.info(f"Using cookie file: {cookie_file}")
        ydl_opts["cookiefile"] = str(cookie_file)
    return ydl_opts


def is_cookie_error(message: str) -> bool:
    """判断下载错误是否与 Cookie / 登录有关"""
    text = message.lower()
    return any(k in text for k in COOKIE_ERROR_KEYWORDS)
