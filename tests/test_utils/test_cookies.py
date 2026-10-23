"""Tests for reading download cookies from a browser or cookies.txt."""

import sys
from argparse import Namespace

import pytest

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli.config import build_config
from videocaptioner.cli.main import _build_cli_overrides, build_parser
from videocaptioner.core.entities import CookieBrowserEnum
from videocaptioner.core.utils.cookies import (
    SUPPORTED_BROWSERS,
    apply_cookie_options,
    is_cookie_error,
)

DOUYIN_ERROR = "ERROR: [Douyin] 7625868392309820687: Fresh cookies (not necessarily logged in) are needed"


class TestApplyCookieOptions:
    def test_browser_selected(self):
        opts = apply_cookie_options({}, browser="Chrome")
        assert opts["cookiesfrombrowser"] == ("chrome", None, None, None)

    def test_browser_wins_over_file_and_file_not_passed(self, tmp_path):
        # yt-dlp 退出时会把全部 Cookie 回写到 cookiefile，不能和浏览器同时设置
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        opts = apply_cookie_options({}, browser="safari", cookie_file=cookie_file)
        assert opts["cookiesfrombrowser"][0] == "safari"
        assert "cookiefile" not in opts

    def test_file_used_when_no_browser(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        assert apply_cookie_options({}, browser="", cookie_file=cookie_file) == {"cookiefile": str(cookie_file)}

    def test_nothing_when_no_browser_and_missing_file(self, tmp_path):
        assert apply_cookie_options({}, browser=None, cookie_file=tmp_path / "missing.txt") == {}

    def test_unsupported_browser(self):
        with pytest.raises(ValueError):
            apply_cookie_options({}, browser="netscape")


def test_gui_enum_maps_to_supported_browsers():
    assert CookieBrowserEnum.NONE.ytdlp_name() == ""
    for browser in CookieBrowserEnum:
        if browser is not CookieBrowserEnum.NONE:
            assert browser.ytdlp_name() in SUPPORTED_BROWSERS.values()


def test_is_cookie_error():
    assert is_cookie_error(DOUYIN_ERROR)
    assert is_cookie_error("Sign in to confirm you're not a bot")
    assert not is_cookie_error("HTTP Error 412: Precondition Failed")


class _FakeYDL:
    """记录传给 yt-dlp 的选项，download 时抛出给定错误"""

    opts = None
    error = None

    def __init__(self, opts):
        type(self).opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        if self.error:
            raise Exception(self.error)

    def extract_info(self, url, download=True):
        raise Exception(self.error or "stop")


@pytest.fixture
def fake_ydl(monkeypatch):
    import yt_dlp

    _FakeYDL.opts, _FakeYDL.error = None, None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)
    return _FakeYDL


class TestCli:
    def test_cookies_from_browser_option(self):
        args = build_parser().parse_args(["download", "https://x", "--cookies-from-browser", "chrome"])
        assert _build_cli_overrides(args)["download"]["cookies_browser"] == "chrome"

    def test_browser_and_file_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["download", "u", "--cookies-from-browser", "chrome", "--cookies", "c.txt"])

    def test_download_passes_browser_to_ytdlp(self, fake_ydl, tmp_path):
        from videocaptioner.cli.commands.download import run

        config = build_config({"download": {"cookies_browser": "edge"}})
        args = Namespace(url="https://x", output=str(tmp_path), quiet=True)
        assert run(args, config) == EXIT.SUCCESS
        assert fake_ydl.opts["cookiesfrombrowser"][0] == "edge"

    def test_invalid_browser_is_usage_error(self, fake_ydl, tmp_path):
        from videocaptioner.cli.commands.download import run

        config = build_config({"download": {"cookies_browser": "ie"}})
        assert run(Namespace(url="u", output=str(tmp_path), quiet=True), config) == EXIT.USAGE_ERROR
        assert fake_ydl.opts is None

    def test_missing_cookie_file(self, fake_ydl, tmp_path):
        from videocaptioner.cli.commands.download import run

        config = build_config({"download": {"cookies_file": str(tmp_path / "nope.txt")}})
        assert run(Namespace(url="u", output=str(tmp_path), quiet=True), config) == EXIT.FILE_NOT_FOUND

    def test_douyin_with_browser_explains_upstream_limit(self, fake_ydl, tmp_path, capsys):
        from videocaptioner.cli.commands.download import run

        fake_ydl.error = DOUYIN_ERROR
        config = build_config({"download": {"cookies_browser": "chrome"}})
        assert run(Namespace(url="u", output=str(tmp_path), quiet=True), config) == EXIT.RUNTIME_ERROR
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "9667" in out and "--cookies-from-browser" not in out

    def test_cookie_error_shows_hint(self, fake_ydl, tmp_path, capsys):
        from videocaptioner.cli.commands.download import run

        fake_ydl.error = DOUYIN_ERROR
        assert run(Namespace(url="u", output=str(tmp_path), quiet=True), build_config({})) == EXIT.RUNTIME_ERROR
        captured = capsys.readouterr()
        assert "--cookies-from-browser" in captured.out + captured.err


_QT_APP = None


class TestGuiDownloadThread:
    @pytest.fixture(autouse=True)
    def app(self):
        # 全局保留 Qt 应用实例：被回收后，cfg 里的配置项 QObject 也会被一起销毁
        global _QT_APP
        from PyQt5.QtWidgets import QApplication

        _QT_APP = QApplication.instance() or QApplication(sys.argv)
        yield _QT_APP

    @pytest.fixture
    def browser_setting(self):
        from videocaptioner.ui.common.config import cfg

        old = cfg.cookies_browser.value
        yield cfg
        cfg.cookies_browser.value = old  # 只改内存，不写入 settings.json

    def test_thread_uses_configured_browser_and_adds_hint(self, fake_ydl, browser_setting, tmp_path):
        from videocaptioner.ui.thread.video_download_thread import VideoDownloadThread

        browser_setting.cookies_browser.value = CookieBrowserEnum.CHROME
        fake_ydl.error = DOUYIN_ERROR
        thread = VideoDownloadThread("https://www.douyin.com/video/1", str(tmp_path))
        errors = []
        thread.error.connect(errors.append)
        thread.run()  # 同步执行，不启动线程

        assert fake_ydl.opts["cookiesfrombrowser"][0] == "chrome"
        assert "cookiefile" not in fake_ydl.opts
        # 已经选了浏览器，不应再提示去设置里选；抖音要说明是上游限制
        assert errors and "设置 → 视频下载" not in errors[0]
        assert "抖音" in errors[0]

    def test_thread_suggests_setting_when_no_browser(self, fake_ydl, browser_setting, tmp_path):
        from videocaptioner.ui.thread.video_download_thread import VideoDownloadThread

        browser_setting.cookies_browser.value = CookieBrowserEnum.NONE
        fake_ydl.error = DOUYIN_ERROR
        thread = VideoDownloadThread("https://www.douyin.com/video/1", str(tmp_path))
        errors = []
        thread.error.connect(errors.append)
        thread.run()
        assert errors and "设置 → 视频下载" in errors[0]
