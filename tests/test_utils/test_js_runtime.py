import pytest

from videocaptioner.core.utils import js_runtime


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/2KlEkQ30beo?si=x7k0TXdS2s6jo3VD",
        "https://www.youtube.com/watch?v=2KlEkQ30beo",
        "https://m.youtube.com/watch?v=2KlEkQ30beo",
        "https://www.youtube-nocookie.com/embed/2KlEkQ30beo",
    ],
)
def test_is_youtube_url(url):
    assert js_runtime.is_youtube_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/video/BV1xx411c7mD",
        "https://notyoutube.com/watch?v=1",
        "not a url",
    ],
)
def test_is_not_youtube_url(url):
    assert not js_runtime.is_youtube_url(url)


def test_needs_deno_only_for_youtube_without_deno(monkeypatch):
    youtube = "https://youtu.be/2KlEkQ30beo"
    bilibili = "https://www.bilibili.com/video/BV1xx411c7mD"

    monkeypatch.setattr(js_runtime.shutil, "which", lambda name: None)
    assert js_runtime.needs_deno(youtube)
    assert not js_runtime.needs_deno(bilibili)

    monkeypatch.setattr(js_runtime.shutil, "which", lambda name: "/opt/homebrew/bin/deno")
    assert not js_runtime.needs_deno(youtube)


@pytest.mark.parametrize(
    "platform, expected",
    [("darwin", "brew install deno"), ("win32", "winget install DenoLand.Deno"), ("linux", "deno.land/install.sh")],
)
def test_deno_install_command(monkeypatch, platform, expected):
    monkeypatch.setattr(js_runtime.sys, "platform", platform)
    assert expected in js_runtime.deno_install_command()
