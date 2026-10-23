"""download command — download online video via yt-dlp."""

from argparse import Namespace
from pathlib import Path
from typing import Any

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.cli.config import get
from videocaptioner.core.utils.cookies import apply_cookie_options, is_cookie_error
from videocaptioner.core.utils.js_runtime import deno_install_command, needs_deno


def run(args: Namespace, config: dict) -> int:
    url = args.url
    out_dir = getattr(args, "output", None) or "."
    quiet = getattr(args, "quiet", False)

    try:
        import yt_dlp
    except ImportError:
        output.error("yt-dlp is not available")
        output.hint("Install the official package with: pip install videocaptioner")
        return EXIT.DEPENDENCY_MISSING

    cookies_browser = get(config, "download.cookies_browser", "")
    cookies_file = get(config, "download.cookies_file", "")
    if cookies_file and not Path(cookies_file).exists():
        output.error(f"Cookies file not found: {cookies_file}")
        return EXIT.FILE_NOT_FOUND

    ydl_opts: dict[str, Any] = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": f"{out_dir}/%(title)s.%(ext)s",
        "noplaylist": True,
        "quiet": quiet,
        "no_warnings": quiet,
    }
    try:
        apply_cookie_options(ydl_opts, browser=cookies_browser, cookie_file=Path(cookies_file) if cookies_file else None)
    except ValueError as e:
        output.error(str(e))
        return EXIT.USAGE_ERROR

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    progress = None if quiet else output.ProgressLine(f"Downloading {url}").start()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
            ydl.download([url])

        if progress:
            progress.finish(f"Downloaded to {out_dir}/")
        return EXIT.SUCCESS

    except Exception as e:
        if progress:
            progress.fail(str(e))
        else:
            output.error(str(e))
        if needs_deno(url):
            output.hint(f"YouTube downloads require deno, which was not found. Install it with: {deno_install_command()}")
        if is_cookie_error(str(e)) and not cookies_browser:
            output.hint("Try --cookies-from-browser chrome (or edge/firefox/safari)")
        return EXIT.RUNTIME_ERROR
