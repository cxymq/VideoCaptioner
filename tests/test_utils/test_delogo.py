"""Tests for watermark removal (delogo) during video synthesis."""

import shutil
import subprocess
from pathlib import Path

import pytest

from videocaptioner.cli.main import _build_cli_overrides, build_parser
from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import SubtitleLayoutEnum
from videocaptioner.core.utils.delogo import build_delogo_filter, parse_delogo_regions

# 测试视频：320x180 黑底，(200,20) 处有一块 80x30 的白色"水印"
WIDTH, HEIGHT = 320, 180
WATERMARK = (200, 20, 80, 30)
REGION_SPEC = "195,15,90,40"

ASS_STYLE = """[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,40,1
Style: Secondary,Arial,32,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,8,10,10,40,1
"""


def _ffmpeg_has_filter(name: str) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


requires_delogo = pytest.mark.skipif(not _ffmpeg_has_filter("delogo"), reason="ffmpeg without delogo filter")
requires_libass = pytest.mark.skipif(not _ffmpeg_has_filter("ass"), reason="ffmpeg without libass")


class TestParseRegions:
    def test_empty(self):
        assert parse_delogo_regions("") == []
        assert parse_delogo_regions(None) == []
        assert parse_delogo_regions("  ") == []

    def test_single_and_multiple(self):
        assert parse_delogo_regions("1560,25,345,80") == [(1560, 25, 345, 80)]
        assert parse_delogo_regions(" 1, 2, 3, 4 ; 5,6,7,8; ") == [(1, 2, 3, 4), (5, 6, 7, 8)]

    @pytest.mark.parametrize("spec", ["1,2,3", "a,b,c,d", "-1,2,3,4", "1,2,0,4", "1,2,3,0"])
    def test_invalid(self, spec):
        with pytest.raises(ValueError):
            parse_delogo_regions(spec)


class TestBuildFilter:
    def test_no_regions(self):
        assert build_delogo_filter([], 1280, 720) == ""
        assert build_delogo_filter(None, 1280, 720) == ""

    def test_inside_frame_unchanged(self):
        assert build_delogo_filter([(100, 50, 200, 80)], 1280, 720) == "delogo=x=100:y=50:w=200:h=80"

    def test_clamped_to_one_pixel_margin(self):
        # FFmpeg rejects regions touching the frame edge
        assert build_delogo_filter([(0, 0, 1280, 720)], 1280, 720) == "delogo=x=1:y=1:w=1278:h=718"
        assert build_delogo_filter([(1200, 10, 200, 60)], 1280, 720) == "delogo=x=1200:y=10:w=79:h=60"

    def test_outside_frame_skipped(self):
        assert build_delogo_filter([(2000, 10, 50, 50), (10, 10, 20, 20)], 1280, 720) == (
            "delogo=x=10:y=10:w=20:h=20"
        )

    def test_multiple_regions_chained(self):
        vf = build_delogo_filter([(10, 10, 20, 20), (100, 100, 30, 30)], 1280, 720)
        assert vf == "delogo=x=10:y=10:w=20:h=20,delogo=x=100:y=100:w=30:h=30"

    @requires_delogo
    def test_clamped_filter_accepted_by_ffmpeg(self):
        vf = build_delogo_filter([(0, 0, WIDTH, HEIGHT)], WIDTH, HEIGHT)
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=s={WIDTH}x{HEIGHT}:d=0.04",
             "-vf", vf, "-f", "null", "-"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr


class TestCliOption:
    def test_repeatable_delogo_joined_into_config(self):
        args = build_parser().parse_args(
            ["synthesize", "in.mp4", "-s", "in.srt", "--delogo", "1,2,3,4", "--delogo", "5,6,7,8"]
        )
        assert _build_cli_overrides(args)["synthesize"]["delogo"] == "1,2,3,4;5,6,7,8"

    def test_process_accepts_delogo(self):
        args = build_parser().parse_args(["process", "in.mp4", "--delogo", "1,2,3,4"])
        assert _build_cli_overrides(args)["synthesize"]["delogo"] == "1,2,3,4"

    def test_invalid_region_is_usage_error(self, tmp_path):
        from videocaptioner.cli import exit_codes as EXIT
        from videocaptioner.cli.main import main

        video = tmp_path / "in.mp4"
        sub = tmp_path / "in.srt"
        video.write_bytes(b"")
        sub.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        assert main(["synthesize", str(video), "-s", str(sub), "--delogo", "bad"]) in (
            EXIT.USAGE_ERROR,
            EXIT.FILE_NOT_FOUND,  # validate_video_input may reject the empty file first
        )


# ---------------------------------------------------------------------------
# End-to-end: render with real FFmpeg and check the watermark pixels are gone
# ---------------------------------------------------------------------------


@pytest.fixture
def watermarked_video(tmp_path: Path) -> Path:
    path = tmp_path / "watermarked.mp4"
    x, y, w, h = WATERMARK
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:d=1:r=10",
         "-vf", f"drawbox=x={x}:y={y}:w={w}:h={h}:color=white:t=fill",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


@pytest.fixture
def asr_data() -> ASRData:
    # 字幕放在画面底部，不与水印区域重叠
    return ASRData([ASRDataSeg(start_time=0, end_time=1000, text="hello")])


def _watermark_brightness(video: Path) -> float:
    """取水印中心 20x10 区域的平均亮度（0-255）"""
    x, y, w, h = WATERMARK
    cx, cy = x + w // 2 - 10, y + h // 2 - 5
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(video), "-frames:v", "1",
         "-vf", f"crop=20:10:{cx}:{cy},format=gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    assert raw, "no frame decoded"
    return sum(raw) / len(raw)


@requires_delogo
def test_fixture_watermark_is_visible(watermarked_video):
    assert _watermark_brightness(watermarked_video) > 200


@requires_delogo
@requires_libass
def test_ass_render_removes_watermark(watermarked_video, asr_data, tmp_path):
    from videocaptioner.core.subtitle.ass_renderer import render_ass_video

    out = tmp_path / "ass.mp4"
    render_ass_video(
        video_path=str(watermarked_video),
        asr_data=asr_data,
        output_path=str(out),
        style_str=ASS_STYLE,
        layout=SubtitleLayoutEnum.ONLY_ORIGINAL,
        preset="ultrafast",
        delogo_regions=parse_delogo_regions(REGION_SPEC),
    )
    assert _watermark_brightness(out) < 60


@requires_delogo
def test_rounded_render_removes_watermark(watermarked_video, asr_data, tmp_path):
    from videocaptioner.core.subtitle.rounded_renderer import render_rounded_video

    out = tmp_path / "rounded.mp4"
    render_rounded_video(
        video_path=str(watermarked_video),
        asr_data=asr_data,
        output_path=str(out),
        layout=SubtitleLayoutEnum.ONLY_ORIGINAL,
        preset="ultrafast",
        delogo_regions=parse_delogo_regions(REGION_SPEC),
    )
    assert _watermark_brightness(out) < 60


@requires_delogo
def test_soft_subtitle_removes_watermark_and_keeps_track(watermarked_video, tmp_path):
    from videocaptioner.core.utils.video_utils import add_subtitles

    srt = tmp_path / "sub.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    out = tmp_path / "soft.mp4"
    add_subtitles(
        str(watermarked_video),
        str(srt),
        str(out),
        preset="ultrafast",
        soft_subtitle=True,
        delogo_regions=parse_delogo_regions(REGION_SPEC),
    )
    assert _watermark_brightness(out) < 60
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "subtitle" in streams


@requires_delogo
def test_ass_resolution_ignores_digits_in_path(tmp_path):
    """路径里的 "60x35" 之类字样不能被当成视频分辨率"""
    from videocaptioner.core.subtitle.ass_renderer import _get_video_resolution

    folder = tmp_path / "abc60x35def"
    folder.mkdir()
    video = folder / "clip_1280x720.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=s={WIDTH}x{HEIGHT}:d=0.2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )
    assert _get_video_resolution(str(video)) == (WIDTH, HEIGHT)


# ---------------------------------------------------------------------------
# GUI: 框选控件把鼠标位置换算成原视频像素
# ---------------------------------------------------------------------------


@pytest.fixture
def selector():
    import sys

    from PyQt5.QtGui import QPixmap
    from PyQt5.QtWidgets import QApplication

    from videocaptioner.ui.components.DelogoRegionSelector import DelogoRegionSelector

    app = QApplication.instance() or QApplication(sys.argv)
    widget = DelogoRegionSelector()
    # 控件 800x450，视频 1920x1080 → 缩放 0.416，无黑边
    widget.resize(800, 450)
    pixmap = QPixmap(1920, 1080)
    widget.setFrame(pixmap, 1920, 1080)
    yield widget
    widget.deleteLater()
    app.processEvents()


def _drag(widget, start, end):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest

    QTest.mousePress(widget, Qt.LeftButton, pos=QPoint(*start))
    QTest.mouseMove(widget, QPoint(*end))
    QTest.mouseRelease(widget, Qt.LeftButton, pos=QPoint(*end))


def test_selector_maps_drag_to_video_pixels(selector):
    emitted = []
    selector.regionsChanged.connect(emitted.append)
    # 拖动方向反过来也应得到同一个区域
    _drag(selector, (793, 87), (650, 10))
    assert len(emitted) == 1
    x, y, w, h = emitted[0][0]
    # 650/800*1920=1560, 10/450*1080=24, 宽 143→343, 高 77→185（允许 ±3 像素取整误差）
    assert abs(x - 1560) <= 3 and abs(y - 24) <= 3
    assert abs(w - 343) <= 3 and abs(h - 185) <= 3


def test_selector_ignores_tiny_drag_and_supports_undo(selector):
    from videocaptioner.ui.components.DelogoRegionSelector import format_regions

    _drag(selector, (100, 100), (101, 101))
    assert selector.regions() == []
    _drag(selector, (10, 10), (110, 60))
    _drag(selector, (300, 300), (400, 350))
    assert len(selector.regions()) == 2
    selector.undo()
    assert len(selector.regions()) == 1
    assert parse_delogo_regions(format_regions(selector.regions())) == selector.regions()
