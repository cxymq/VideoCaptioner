# -*- coding: utf-8 -*-
from typing import List, Optional

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from videocaptioner.core.utils.delogo import DelogoRegion

# 小于这个尺寸（视频像素）的框选视为误触
_MIN_REGION_SIZE = 4


class DelogoRegionSelector(QWidget):
    """在视频帧上拖动鼠标框选水印区域

    坐标统一换算为原视频像素，通过 regionsChanged 信号发出。
    """

    regionsChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._video_w = 0
        self._video_h = 0
        self._regions: List[DelogoRegion] = []
        self._drag_start: Optional[QPoint] = None
        self._drag_end: Optional[QPoint] = None
        self._placeholder = self.tr("暂无画面")
        self.setMinimumSize(640, 360)
        self.setCursor(Qt.CrossCursor)  # type: ignore

    # ------------------------------------------------------------------ API
    def setFrame(self, pixmap: Optional[QPixmap], video_w: int, video_h: int) -> None:
        self._pixmap = pixmap if pixmap and not pixmap.isNull() else None
        self._video_w, self._video_h = video_w, video_h
        self.update()

    def setPlaceholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def regions(self) -> List[DelogoRegion]:
        return list(self._regions)

    def setRegions(self, regions: List[DelogoRegion]) -> None:
        """外部设置区域（不发出信号，避免与输入框互相触发）"""
        self._regions = list(regions)
        self.update()

    def undo(self) -> None:
        if self._regions:
            self._regions.pop()
            self._emit()

    def clear(self) -> None:
        if self._regions:
            self._regions.clear()
            self._emit()

    # ------------------------------------------------------------ 坐标换算
    def _image_rect(self) -> QRectF:
        """帧图像在控件中的显示区域（保持宽高比居中）"""
        if not self._pixmap or not self._video_w or not self._video_h:
            return QRectF()
        scale = min(self.width() / self._video_w, self.height() / self._video_h)
        w, h = self._video_w * scale, self._video_h * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _to_video(self, p: QPoint) -> QPointF:
        rect = self._image_rect()
        x = (p.x() - rect.x()) / rect.width() * self._video_w
        y = (p.y() - rect.y()) / rect.height() * self._video_h
        return QPointF(min(max(x, 0), self._video_w), min(max(y, 0), self._video_h))

    def _to_widget(self, region: DelogoRegion) -> QRectF:
        rect = self._image_rect()
        sx, sy = rect.width() / self._video_w, rect.height() / self._video_h
        x, y, w, h = region
        return QRectF(rect.x() + x * sx, rect.y() + y * sy, w * sx, h * sy)

    def _drag_region(self) -> Optional[DelogoRegion]:
        if self._drag_start is None or self._drag_end is None:
            return None
        a, b = self._to_video(self._drag_start), self._to_video(self._drag_end)
        x0, y0 = int(min(a.x(), b.x())), int(min(a.y(), b.y()))
        x1, y1 = int(round(max(a.x(), b.x()))), int(round(max(a.y(), b.y())))
        return (x0, y0, x1 - x0, y1 - y0)

    # ---------------------------------------------------------------- 事件
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._image_rect().contains(QPointF(event.pos())):  # type: ignore
            self._drag_start = self._drag_end = event.pos()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None:
            self._drag_end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton or self._drag_start is None:  # type: ignore
            return
        self._drag_end = event.pos()
        region = self._drag_region()
        self._drag_start = self._drag_end = None
        if region and region[2] >= _MIN_REGION_SIZE and region[3] >= _MIN_REGION_SIZE:
            self._regions.append(region)
            self._emit()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 40))

        image_rect = self._image_rect()
        if self._pixmap is None or image_rect.isEmpty():
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)  # type: ignore
            return

        painter.drawPixmap(image_rect.toRect(), self._pixmap)

        pen = QPen(QColor(255, 80, 80), 2)
        painter.setPen(pen)
        painter.setBrush(QColor(255, 80, 80, 60))
        for index, region in enumerate(self._regions, start=1):
            r = self._to_widget(region)
            painter.drawRect(r)
            painter.drawText(r.adjusted(4, 2, 0, 0), Qt.AlignLeft | Qt.AlignTop, str(index))  # type: ignore

        drag = self._drag_region()
        if drag:
            pen = QPen(QColor(80, 200, 255), 2, Qt.DashLine)  # type: ignore
            painter.setPen(pen)
            painter.setBrush(QColor(80, 200, 255, 50))
            painter.drawRect(self._to_widget(drag))

    def _emit(self) -> None:
        self.update()
        self.regionsChanged.emit(self.regions())


def format_regions(regions: List[DelogoRegion]) -> str:
    return ";".join(",".join(str(v) for v in region) for region in regions)

