"""视频播放器控件"""
from typing import Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSlider, QStyle, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap
import numpy as np

from src.core.video_processor import VideoProcessor
from src.models.frame_data import VideoInfo
from src.utils.image_utils import numpy_to_qpixmap


class VideoPlayer(QWidget):
    """视频播放器控件"""
    
    position_changed = Signal(float)  # 当前时间(秒)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._processor = VideoProcessor()
        self._video_info: Optional[VideoInfo] = None
        self._current_position = 0.0
        self._is_playing = False
        self._range_playback_enabled = False
        self._range_start = 0.0
        self._range_end = 0.0
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._on_play_tick)
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 视频显示区域
        self.video_label = QLabel("🎬\n点击左侧按钮加载视频")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #1e1e1e; 
                border: 1px solid #333; 
                border-radius: 8px;
                color: #555;
                font-size: 24px;
                font-weight: bold;
            }
        """)
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.video_label)
        
        # 控制栏
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(8, 4, 8, 4)
        
        # 播放/暂停按钮
        self.play_btn = QPushButton()
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
                border-color: #00b8d4;
            }
        """)
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        # 时间滑块
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.setValue(0)
        self.time_slider.sliderMoved.connect(self._on_slider_moved)
        self.time_slider.sliderPressed.connect(self._on_slider_pressed)
        self.time_slider.sliderReleased.connect(self._on_slider_released)
        control_layout.addWidget(self.time_slider, 1)
        
        # 时间标签
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setStyleSheet("color: #888; font-size: 11px;")
        control_layout.addWidget(self.time_label)
        
        layout.addLayout(control_layout)
        
        self._slider_dragging = False
    
    def load_video(self, path: str) -> Optional[VideoInfo]:
        """加载视频"""
        try:
            self._video_info = self._processor.load_video(path)
            self._current_position = 0.0
            self._update_time_label()
            self._show_frame_at(0.0)
            return self._video_info
        except Exception as e:
            print(f"加载视频失败: {e}")
            return None
    
    @property
    def video_info(self) -> Optional[VideoInfo]:
        return self._video_info
    
    @property
    def current_position(self) -> float:
        return self._current_position
    
    def set_playback_range(self, start: float, end: float):
        self._range_start = max(0.0, start)
        self._range_end = max(self._range_start, end)
        self._clamp_playback_range()

    def clear_playback_range(self):
        self._range_start = 0.0
        self._range_end = 0.0

    def set_range_playback_enabled(self, enabled: bool):
        self._range_playback_enabled = enabled
        if enabled:
            self._clamp_playback_range()

    def _clamp_playback_range(self):
        if not self._video_info:
            return
        duration = self._video_info.duration
        self._range_start = max(0.0, min(self._range_start, duration))
        self._range_end = max(0.0, min(self._range_end, duration))
        if self._range_end < self._range_start:
            self._range_end = self._range_start

    def toggle_play(self):
        """切换播放/暂停"""
        if self._is_playing:
            self.pause()
        else:
            self.play()
    
    def play(self):
        """播放"""
        if not self._video_info:
            return
        if self._range_playback_enabled:
            self._clamp_playback_range()
            self.seek(self._range_start)
        self._is_playing = True
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        # 30fps更新
        self._play_timer.start(33)
    
    def pause(self):
        """暂停"""
        self._is_playing = False
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self._play_timer.stop()
    
    def seek(self, position: float):
        """跳转到指定位置"""
        if not self._video_info:
            return
        
        position = max(0, min(position, self._video_info.duration))
        self._current_position = position
        self._show_frame_at(position)
        self._update_slider()
        self._update_time_label()
        self.position_changed.emit(position)
    
    def _show_frame_at(self, timestamp: float):
        """显示指定时间的帧"""
        frame = self._processor.get_frame_at(timestamp)
        if frame is not None:
            pixmap = numpy_to_qpixmap(frame)
            scaled = pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.video_label.setPixmap(scaled)
    
    def _on_play_tick(self):
        """播放定时器回调"""
        if not self._video_info:
            return

        if self._range_playback_enabled:
            self._clamp_playback_range()
            if self._current_position < self._range_start:
                self._current_position = self._range_start
            range_end = self._range_end
        else:
            range_end = self._video_info.duration

        # 前进一帧的时间
        self._current_position += 0.033  # ~30fps

        if self._range_playback_enabled:
            if self._current_position >= range_end:
                self._current_position = range_end
                self._show_frame_at(self._current_position)
                if not self._slider_dragging:
                    self._update_slider()
                self._update_time_label()
                self.position_changed.emit(self._current_position)
                self.pause()
                return
        else:
            if self._current_position >= self._video_info.duration:
                self._current_position = 0.0  # 循环

        self._show_frame_at(self._current_position)
        if not self._slider_dragging:
            self._update_slider()
        self._update_time_label()
        self.position_changed.emit(self._current_position)

    def _on_slider_moved(self, value):
        """滑块移动"""
        if not self._video_info:
            return
        
        position = (value / 1000.0) * self._video_info.duration
        self._current_position = position
        self._show_frame_at(position)
        self._update_time_label()
    
    def _on_slider_pressed(self):
        self._slider_dragging = True
    
    def _on_slider_released(self):
        self._slider_dragging = False
        self.position_changed.emit(self._current_position)
    
    def _update_slider(self):
        if not self._video_info or self._video_info.duration == 0:
            return
        value = int((self._current_position / self._video_info.duration) * 1000)
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(value)
        self.time_slider.blockSignals(False)
    
    def _update_time_label(self):
        current = self._format_time(self._current_position)
        total = self._format_time(self._video_info.duration if self._video_info else 0)
        self.time_label.setText(f"{current} / {total}")
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:02d}:{secs:06.3f}"
    
    def release(self):
        """释放资源"""
        self.pause()
        self._processor.release()
