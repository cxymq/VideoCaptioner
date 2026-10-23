# -*- coding: utf-8 -*-
from pathlib import Path

from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    LineEdit,
    MessageBoxBase,
    PushButton,
    SubtitleLabel,
    SwitchButton,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.config import CACHE_PATH
from videocaptioner.core.utils.delogo import parse_delogo_regions
from videocaptioner.core.utils.video_utils import _extract_thumbnail, get_video_info
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.DelogoRegionSelector import DelogoRegionSelector, format_regions

# "换一帧"依次截取的时间点（占视频时长的比例），水印可能只在部分片段出现
_FRAME_POSITIONS = [0.3, 0.5, 0.7, 0.9, 0.1]


class DelogoSettingDialog(MessageBoxBase):
    """去水印设置对话框：在视频画面上框选水印区域"""

    def __init__(self, video_path: str = "", parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.video_w = self.video_h = 0
        self.duration = 0.0
        self.frame_index = 0
        self.frame_path = CACHE_PATH / "delogo_frame.jpg"

        self.titleLabel = SubtitleLabel(self.tr("去水印"), self)
        self.descLabel = CaptionLabel(
            self.tr("在画面上按住鼠标拖动，框住水印，可以框选多个。开启后会重新编码画面，合成会慢一些。"),
            self,
        )
        self.descLabel.setWordWrap(True)

        self.selector = DelogoRegionSelector(self)

        # 画面操作按钮
        tool_layout = QHBoxLayout()
        self.nextFrameButton = PushButton(FIF.SYNC, self.tr("换一帧"), self)
        self.undoButton = PushButton(FIF.RETURN, self.tr("撤销"), self)
        self.clearButton = PushButton(FIF.DELETE, self.tr("清空"), self)
        self.infoLabel = CaptionLabel("", self)
        tool_layout.addWidget(self.nextFrameButton)
        tool_layout.addWidget(self.undoButton)
        tool_layout.addWidget(self.clearButton)
        tool_layout.addStretch(1)
        tool_layout.addWidget(self.infoLabel)

        switch_layout = QHBoxLayout()
        switch_layout.addWidget(BodyLabel(self.tr("启用去水印"), self))
        switch_layout.addStretch(1)
        self.enableSwitch = SwitchButton(self)
        self.enableSwitch.setOnText(self.tr("开"))
        self.enableSwitch.setOffText(self.tr("关"))
        self.enableSwitch.setChecked(cfg.delogo_enabled.value)
        switch_layout.addWidget(self.enableSwitch)

        # 坐标输入框：框选后自动填写，也可以手动微调
        self.regionsInput = LineEdit(self)
        self.regionsInput.setPlaceholderText(self.tr("框选后自动填写坐标 x,y,宽,高，也可手动修改"))
        self.regionsInput.setClearButtonEnabled(True)

        self.errorLabel = CaptionLabel("", self)
        self.errorLabel.setTextColor("#cf1010", "#ff6b6b")
        self.errorLabel.hide()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.descLabel)
        self.viewLayout.addWidget(self.selector, 1)
        self.viewLayout.addLayout(tool_layout)
        self.viewLayout.addLayout(switch_layout)
        self.viewLayout.addWidget(self.regionsInput)
        self.viewLayout.addWidget(self.errorLabel)
        self.viewLayout.setSpacing(10)

        self.widget.setMinimumWidth(720)
        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("取消"))
        self.setWindowTitle(self.tr("去水印"))

        self.selector.regionsChanged.connect(self._on_regions_selected)
        self.regionsInput.textEdited.connect(self._on_text_edited)
        self.nextFrameButton.clicked.connect(self._next_frame)
        self.undoButton.clicked.connect(self.selector.undo)
        self.clearButton.clicked.connect(self.selector.clear)

        self._set_regions_text(cfg.delogo_regions.value)
        self._load_video()

    # ---------------------------------------------------------------- 画面
    def _load_video(self) -> None:
        if not self.video_path or not Path(self.video_path).is_file():
            self.selector.setPlaceholder(self.tr("请先在合成页选择视频文件，再来框选水印"))
            self.nextFrameButton.setEnabled(False)
            return
        info = get_video_info(self.video_path)
        if not info or not info.width or not info.height:
            self.selector.setPlaceholder(self.tr("无法读取视频画面"))
            self.nextFrameButton.setEnabled(False)
            return
        self.video_w, self.video_h = info.width, info.height
        self.duration = info.duration_seconds
        self.infoLabel.setText(self.tr("视频分辨率：") + f"{self.video_w} x {self.video_h}")
        self._show_frame()

    def _show_frame(self) -> None:
        seek = self.duration * _FRAME_POSITIONS[self.frame_index % len(_FRAME_POSITIONS)]
        pixmap = None
        if _extract_thumbnail(self.video_path, seek, str(self.frame_path)):
            pixmap = QPixmap(str(self.frame_path))
        if pixmap is None or pixmap.isNull():
            self.selector.setPlaceholder(self.tr("截取视频画面失败"))
        self.selector.setFrame(pixmap, self.video_w, self.video_h)

    def _next_frame(self) -> None:
        self.frame_index += 1
        self._show_frame()

    # ------------------------------------------------------------ 区域同步
    def _on_regions_selected(self, regions) -> None:
        self.regionsInput.setText(format_regions(regions))
        self.errorLabel.hide()
        # 框选了区域通常就是要去水印，自动打开开关
        if regions:
            self.enableSwitch.setChecked(True)

    def _on_text_edited(self, text: str) -> None:
        try:
            self.selector.setRegions(parse_delogo_regions(text))
            self.errorLabel.hide()
        except ValueError:
            pass  # 输入过程中格式不完整，保存时再提示

    def _set_regions_text(self, text: str) -> None:
        self.regionsInput.setText(text)
        try:
            self.selector.setRegions(parse_delogo_regions(text))
        except ValueError:
            pass

    # ---------------------------------------------------------------- 保存
    def validate(self) -> bool:
        """保存前校验区域格式，校验通过后写入配置"""
        text = self.regionsInput.text().strip()
        enabled = self.enableSwitch.isChecked()
        try:
            regions = parse_delogo_regions(text)
        except ValueError as e:
            self._show_error(self.tr("格式错误：") + str(e))
            return False
        if enabled and not regions:
            self._show_error(self.tr("请先在画面上框选水印区域"))
            return False

        cfg.set(cfg.delogo_enabled, enabled)
        cfg.set(cfg.delogo_regions, text)
        return True

    def _show_error(self, message: str) -> None:
        self.errorLabel.setText(message)
        self.errorLabel.show()
