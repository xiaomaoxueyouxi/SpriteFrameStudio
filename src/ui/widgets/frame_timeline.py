"""帧时间轴控件"""
from typing import Optional, Tuple
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QDoubleSpinBox, QVBoxLayout
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QCursor


class RangeSelector(QWidget):
    """Time range selector with draggable handles."""

    range_changed = Signal(float, float)
    seek_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0.0
        self._start = 0.0
        self._end = 0.0
        self._current = 0.0
        self._fps = 0.0
        self._min_range = 0.0

        self._drag_mode = None  # "left", "right", "range", "create"
        self._drag_anchor_time = 0.0
        self._drag_start = 0.0
        self._drag_end = 0.0
        self._is_dragging = False
        self._emit_seek_on_release = False

        self.setMinimumHeight(32)
        self.setMouseTracking(True)

    def set_duration(self, duration: float):
        self._duration = max(0.0, duration)
        self._start = 0.0
        self._end = self._duration
        self.update()

    def set_fps(self, fps: float):
        self._fps = max(0.0, fps)
        self._min_range = (1.0 / self._fps) if self._fps > 0 else 0.0

    def set_range(self, start: float, end: float):
        """设置时间范围"""
        start, end = self._normalize_range(start, end)
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.start_spin.setValue(start)
        self.end_spin.setValue(end)
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)

        self.range_selector.set_range(start, end, emit=False)
        self._update_duration_label()

    def set_current_position(self, position: float):
        self._current = max(0.0, min(position, self._duration)) if self._duration > 0 else 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()
        if track.width() <= 0:
            return

        # Track background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2a2a2a"))
        painter.drawRoundedRect(track, 3, 3)

        if self._duration <= 0:
            return

        # Selection range
        start_x = self._time_to_x(self._start)
        end_x = self._time_to_x(self._end)
        sel_rect = QRectF(min(start_x, end_x), track.top(), abs(end_x - start_x), track.height())
        painter.setBrush(QColor("#0078d4"))
        painter.drawRoundedRect(sel_rect, 3, 3)

        # Handles
        handle_w = 6
        handle_h = track.height() + 10
        handle_y = track.center().y() - handle_h / 2
        painter.setBrush(QColor("#e6e6e6"))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(start_x - handle_w / 2, handle_y, handle_w, handle_h))
        painter.drawRect(QRectF(end_x - handle_w / 2, handle_y, handle_w, handle_h))

        # Current position marker
        cur_x = self._time_to_x(self._current)
        pen = QPen(QColor("#ffffff"))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(int(cur_x), int(track.top() - 4), int(cur_x), int(track.bottom() + 4))

    def mousePressEvent(self, event):
        if self._duration <= 0 or event.button() != Qt.LeftButton:
            return

        pos_x = event.position().x()
        
        # 首先检查是否点击了滑块
        start_x = self._time_to_x(self._start)
        end_x = self._time_to_x(self._end)
        handle_hit = 12

        # 检查滑块点击
        if abs(pos_x - start_x) <= handle_hit:
            self._drag_mode = "left"
            self._current = self._start
            self.update()
            self._emit_seek_on_release = False
            self._is_dragging = True
            return
        elif abs(pos_x - end_x) <= handle_hit:
            self._drag_mode = "right"
            self._current = self._end
            self.update()
            self._emit_seek_on_release = False
            self._is_dragging = True
            return
        
        # 然后检查轨道区域
        track = self._track_rect()
        if not track.contains(event.position()):
            return

        t = self._x_to_time(pos_x)
        self._current = t
        self.update()

        # 检查其他模式
        if min(start_x, end_x) <= pos_x <= max(start_x, end_x):
            self._drag_mode = "range"
            self._drag_anchor_time = t
            self._drag_start = self._start
            self._drag_end = self._end
        else:
            self._drag_mode = "create"
            self._drag_anchor_time = t
            self.set_range(self._drag_anchor_time, self._drag_anchor_time, emit=True)

        self._emit_seek_on_release = (self._drag_mode == "create")
        self._is_dragging = True

    def mouseMoveEvent(self, event):
        if self._duration <= 0:
            return

        pos_x = event.position().x()
        if not self._is_dragging:
            # Update cursor
            start_x = self._time_to_x(self._start)
            end_x = self._time_to_x(self._end)
            handle_hit = 12
            if abs(pos_x - start_x) <= handle_hit or abs(pos_x - end_x) <= handle_hit:
                self.setCursor(QCursor(Qt.SizeHorCursor))
            elif min(start_x, end_x) <= pos_x <= max(start_x, end_x):
                self.setCursor(QCursor(Qt.SizeAllCursor))
            else:
                self.unsetCursor()
            return

        t = self._x_to_time(pos_x)
        if self._drag_mode == "left":
            self._set_start(t)
            self._current = self._start
            self.seek_requested.emit(self._current)
        elif self._drag_mode == "right":
            self._set_end(t)
            self._current = self._end
            self.seek_requested.emit(self._current)
        elif self._drag_mode == "range":
            offset = t - self._drag_anchor_time
            self._move_range(offset)
        elif self._drag_mode == "create":
            self._set_range_create(self._drag_anchor_time, t)

    def mouseReleaseEvent(self, event):
        if self._is_dragging and event.button() == Qt.LeftButton:
            self._is_dragging = False
            if self._emit_seek_on_release:
                self.seek_requested.emit(self._current)
            self._emit_seek_on_release = False
            self._drag_mode = None

    def _track_rect(self) -> QRectF:
        margin = 8
        height = 8
        y = (self.height() - height) / 2
        return QRectF(margin, y, max(0.0, self.width() - margin * 2), height)

    def _time_to_x(self, t: float) -> float:
        track = self._track_rect()
        if self._duration <= 0 or track.width() <= 0:
            return track.left()
        ratio = max(0.0, min(1.0, t / self._duration))
        return track.left() + ratio * track.width()

    def _x_to_time(self, x: float) -> float:
        track = self._track_rect()
        if self._duration <= 0 or track.width() <= 0:
            return 0.0
        ratio = (x - track.left()) / track.width()
        t = ratio * self._duration
        return self._snap_time(t)

    def _snap_time(self, t: float) -> float:
        if self._fps > 0:
            step = 1.0 / self._fps
            t = round(t / step) * step
        return max(0.0, min(t, self._duration))

    def _normalize_range(self, start: float, end: float) -> Tuple[float, float]:
        start = self._snap_time(start)
        end = self._snap_time(end)
        if start > end:
            start, end = end, start
        # Enforce minimum range
        if self._min_range > 0 and (end - start) < self._min_range:
            if start + self._min_range <= self._duration:
                end = start + self._min_range
            else:
                end = self._duration
                start = max(0.0, end - self._min_range)
        return start, end

    def _set_start(self, start: float):
        start = self._snap_time(start)
        max_start = self._end - self._min_range if self._min_range > 0 else self._end
        start = max(0.0, min(start, max_start))
        self._start = start
        self.range_changed.emit(self._start, self._end)
        self.update()

    def _set_end(self, end: float):
        end = self._snap_time(end)
        min_end = self._start + self._min_range if self._min_range > 0 else self._start
        end = max(min_end, min(end, self._duration))
        self._end = end
        self.range_changed.emit(self._start, self._end)
        self.update()

    def _move_range(self, offset: float):
        length = self._end - self._start
        if length < 0:
            length = 0.0
        new_start = self._snap_time(self._drag_start + offset)
        # Clamp so range stays within duration
        if new_start + length > self._duration:
            new_start = self._duration - length
        if new_start < 0:
            new_start = 0.0
        new_end = new_start + length
        self._start = new_start
        self._end = new_end
        self.range_changed.emit(self._start, self._end)
        self.update()

    def _set_range_create(self, anchor: float, t: float):
        start, end = self._normalize_range(anchor, t)
        self._start = start
        self._end = end
        self._current = self._snap_time(t)
        self.range_changed.emit(self._start, self._end)
        self.update()


class FrameTimeline(QWidget):
    """帧时间轴控件 - 用于选择时间范围"""
    
    range_changed = Signal(float, float)  # start_time, end_time
    seek_requested = Signal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0.0
        self._fps = 0.0
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 开始时间
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("开始时间:"))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0, 0)
        self.start_spin.setDecimals(3)
        self.start_spin.setSuffix(" 秒")
        self.start_spin.valueChanged.connect(self._on_start_changed)
        self.start_spin.setEnabled(False)  # 禁用输入，使用范围选择器
        start_layout.addWidget(self.start_spin, 1)
        layout.addLayout(start_layout)
        
        # 结束时间
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("结束时间:"))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0, 0)
        self.end_spin.setDecimals(3)
        self.end_spin.setSuffix(" 秒")
        self.end_spin.valueChanged.connect(self._on_end_changed)
        self.end_spin.setEnabled(False)  # 禁用输入，使用范围选择器
        end_layout.addWidget(self.end_spin, 1)
        layout.addLayout(end_layout)
        
        # Range selector
        self.range_selector = RangeSelector()
        self.range_selector.range_changed.connect(self._on_selector_range_changed)
        self.range_selector.seek_requested.connect(self.seek_requested.emit)
        layout.addWidget(self.range_selector)

        # Duration display
        self.duration_label = QLabel("选中时长: 0.000 秒")
        self.duration_label.setStyleSheet("color: #888;")
        layout.addWidget(self.duration_label)
    
    def set_duration(self, duration: float):
        """设置视频总时长"""
        self._duration = duration
        self.range_selector.set_duration(duration)
        
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        
        self.start_spin.setRange(0, duration)
        self.end_spin.setRange(0, duration)
        self.start_spin.setValue(0)
        self.end_spin.setValue(duration)
        
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        
        self._update_duration_label()

    def set_fps(self, fps: float):
        self._fps = max(0.0, fps)
        self.range_selector.set_fps(self._fps)
    
    def get_range(self) -> Tuple[float, float]:
        """获取时间范围"""
        return (self.start_spin.value(), self.end_spin.value())
    
    def set_range(self, start: float, end: float):
        """设置时间范围"""
        start, end = self._normalize_range(start, end)
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.start_spin.setValue(start)
        self.end_spin.setValue(end)
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)

        self.range_selector.set_range(start, end, emit=False)
        self._update_duration_label()

    def set_current_position(self, position: float):
        self.range_selector.set_current_position(position)

    def _on_start_changed(self, value):
        # 确保开始时间不大于结束时间
        start = self._snap_time(value)
        end = self.end_spin.value()
        if end < start:
            end = start
        self.set_range(start, end)
        self.range_changed.emit(self.start_spin.value(), self.end_spin.value())

    def _on_end_changed(self, value):
        # 确保结束时间不小于开始时间
        end = self._snap_time(value)
        start = self.start_spin.value()
        if end < start:
            start = end
        self.set_range(start, end)
        self.range_changed.emit(self.start_spin.value(), self.end_spin.value())

    def _on_selector_range_changed(self, start: float, end: float):
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.start_spin.setValue(start)
        self.end_spin.setValue(end)
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        self._update_duration_label()
        self.range_changed.emit(start, end)

    def _snap_time(self, t: float) -> float:
        if self._fps > 0:
            step = 1.0 / self._fps
            t = round(t / step) * step
        return max(0.0, min(t, self._duration))

    def _normalize_range(self, start: float, end: float) -> Tuple[float, float]:
        start = self._snap_time(start)
        end = self._snap_time(end)
        if start > end:
            start, end = end, start
        if self._fps > 0:
            min_range = 1.0 / self._fps
            if (end - start) < min_range:
                if start + min_range <= self._duration:
                    end = start + min_range
                else:
                    end = self._duration
                    start = max(0.0, end - min_range)
        return start, end

    def _update_duration_label(self):
        duration = self.end_spin.value() - self.start_spin.value()
        self.duration_label.setText(f"选中时长: {duration:.3f} 秒")
