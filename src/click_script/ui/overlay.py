from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QDialog

from click_script.domain.models import Rect
from click_script.infrastructure.capture import CapturedFrame


def frame_to_pixmap(frame: CapturedFrame) -> QPixmap:
    height, width, channels = frame.image.shape
    rgb = frame.image[:, :, ::-1].copy()
    image = QImage(
        rgb.data,
        width,
        height,
        channels * width,
        QImage.Format.Format_RGB888,
    )
    return QPixmap.fromImage(image.copy())


class SelectionOverlay(QDialog):
    def __init__(self, frame: CapturedFrame, parent=None) -> None:
        super().__init__(parent)
        self.frame = frame
        self.pixmap = frame_to_pixmap(frame)
        self.start_point: QPoint | None = None
        self.current_point: QPoint | None = None
        self.selected_rect: QRect | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setGeometry(
            frame.bounds.left,
            frame.bounds.top,
            frame.bounds.width,
            frame.bounds.height,
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    def selection_global(self) -> Rect | None:
        if self.selected_rect is None:
            return None
        rect = self.selected_rect.normalized()
        return Rect(
            self.frame.bounds.left + rect.left(),
            self.frame.bounds.top + rect.top(),
            rect.width(),
            rect.height(),
        )

    def selection_image(self):
        if self.selected_rect is None:
            return None
        rect = self.selected_rect.normalized()
        return self.frame.image[
            rect.top() : rect.bottom() + 1,
            rect.left() : rect.right() + 1,
        ].copy()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.position().toPoint()
            self.current_point = self.start_point
            self.selected_rect = None
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.start_point is not None:
            self.current_point = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.start_point is not None
            and self.current_point is not None
        ):
            candidate = QRect(self.start_point, self.current_point).normalized()
            self.start_point = None
            if candidate.width() >= 8 and candidate.height() >= 8:
                self.selected_rect = candidate
                self.accept()
            else:
                self.current_point = None
                self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        rect: QRect | None
        if self.start_point is not None and self.current_point is not None:
            rect = QRect(self.start_point, self.current_point).normalized()
        else:
            rect = self.selected_rect
        if rect is not None:
            painter.drawPixmap(rect, self.pixmap, rect)
            painter.setPen(QPen(QColor("#42a5f5"), 2))
            painter.drawRect(rect)
            painter.setPen(QPen(Qt.GlobalColor.white))
            painter.drawText(
                rect.adjusted(6, 6, -6, -6),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                f"{rect.width()} × {rect.height()}",
            )
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(
            self.rect().adjusted(20, 20, -20, -20),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "拖动选择区域，按 Esc 取消",
        )
