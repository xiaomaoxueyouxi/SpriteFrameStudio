"""动画预览控件 - 使用透明叠加方案，无需实时合成"""
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QStyle, QSizePolicy, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage
import numpy as np


class AnimationPreview(QWidget):
    """动画预览控件 - 使用透明叠加方案，无需实时合成"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: List[np.ndarray] = []
        self._timestamps: List[float] = None
        self._current_index = 0
        self._is_playing = False
        self._fps = 24.0
        self._bg_mode = "gray"  # 背景模式: checkerboard, white, black, gray, custom
        self._custom_bg_color = (128, 128, 128)
        self._cached_pixmaps: List[QPixmap] = []
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 图像显示区域 - 设置棋盘格背景
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._update_bg_style()
        layout.addWidget(self.image_label)
        
        # 控制栏
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(8, 4, 8, 4)
        
        # 播放/暂停按钮
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        # 帧滑块
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.setValue(0)
        self.frame_slider.sliderMoved.connect(self._on_slider_moved)
        control_layout.addWidget(self.frame_slider, 1)
        
        # 帧计数
        self.frame_label = QLabel("0 / 0")
        self.frame_label.setStyleSheet("color: #888; font-size: 11px; min-width: 60px;")
        control_layout.addWidget(self.frame_label)
        
        layout.addLayout(control_layout)
        
        # 速度控制
        speed_layout = QHBoxLayout()
        speed_layout.setContentsMargins(8, 0, 8, 4)
        
        speed_layout.addWidget(QLabel("速度:"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(1, 60)
        self.speed_slider.setValue(24)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.speed_slider, 1)
        
        self.speed_label = QLabel("24 fps")
        self.speed_label.setStyleSheet("color: #888; font-size: 11px; min-width: 50px;")
        speed_layout.addWidget(self.speed_label)
        
        layout.addLayout(speed_layout)
        
        # 背景选择
        bg_layout = QHBoxLayout()
        bg_layout.setContentsMargins(8, 0, 8, 4)
        
        bg_layout.addWidget(QLabel("背景:"))
        self.bg_combo = QComboBox()
        self.bg_combo.addItem("⚪ 灰色", "gray")
        self.bg_combo.addItem("⚪ 白色", "white")
        self.bg_combo.addItem("⚫ 黑色", "black")
        self.bg_combo.addItem("⭕ 自定义...", "custom")
        self.bg_combo.currentIndexChanged.connect(self._on_bg_changed)
        bg_layout.addWidget(self.bg_combo)
        
        # 颜色选择按钮
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(24, 24)
        self.color_btn.setStyleSheet(
            "background-color: rgb(128, 128, 128); "
            "border: 1px solid #666; border-radius: 3px;"
        )
        self.color_btn.clicked.connect(self._choose_bg_color)
        self.color_btn.setVisible(False)
        bg_layout.addWidget(self.color_btn)
        
        bg_layout.addStretch()
        layout.addLayout(bg_layout)
    
    def _update_bg_style(self):
        """更新背景样式"""
        if self._bg_mode == "gray":
            # 默认灰色背景
            self.image_label.setStyleSheet("background-color: #808080;")
        elif self._bg_mode == "white":
            self.image_label.setStyleSheet("background-color: #ffffff;")
        elif self._bg_mode == "black":
            self.image_label.setStyleSheet("background-color: #000000;")
        elif self._bg_mode == "custom":
            r, g, b = self._custom_bg_color
            self.image_label.setStyleSheet(f"background-color: rgb({r}, {g}, {b});")
    
    def set_frames(self, frames: List[np.ndarray], timestamps: List[float] = None):
        """设置帧序列"""
        self.stop()
        self._frames = frames
        self._timestamps = timestamps
        self._current_index = 0
        
        # 缓存所有帧的 pixmap（保留原始格式，透明自动叠加）
        self._cache_all_pixmaps()
        
        self.frame_slider.setRange(0, max(0, len(frames) - 1))
        self.frame_slider.setValue(0)
        
        self._update_display()
        self._update_labels()
    
    def _cache_all_pixmaps(self):
        """缓存所有帧的 pixmap（保留透明通道）"""
        self._cached_pixmaps = []
        for frame in self._frames:
            pixmap = self._numpy_to_pixmap(frame)
            self._cached_pixmaps.append(pixmap)
    
    def _numpy_to_pixmap(self, array: np.ndarray) -> QPixmap:
        """将 numpy 数组转换为 QPixmap，保留透明通道"""
        if array is None:
            return QPixmap()
        
        h, w = array.shape[:2]
        
        if len(array.shape) == 2:
            qimg = QImage(array.data, w, h, w, QImage.Format_Grayscale8)
        elif array.shape[2] == 3:
            qimg = QImage(array.data, w, h, w * 3, QImage.Format_RGB888)
        elif array.shape[2] == 4:
            # RGBA 图 - 保留透明通道
            qimg = QImage(array.data, w, h, w * 4, QImage.Format_RGBA8888)
        else:
            return QPixmap()
        
        return QPixmap.fromImage(qimg.copy())
    
    def clear(self):
        """清空帧"""
        self.stop()
        self._frames = []
        self._timestamps = None
        self._current_index = 0
        self._cached_pixmaps = []
        self.frame_slider.setRange(0, 0)
        self.image_label.clear()
        self._update_labels()
    
    def toggle_play(self):
        """切换播放/暂停"""
        if self._is_playing:
            self.pause()
        else:
            self.play()
    
    def play(self):
        """播放"""
        if not self._frames:
            return
        self._is_playing = True
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        
        if self._timestamps and len(self._timestamps) > 1:
            total_duration = self._timestamps[-1] - self._timestamps[0]
            avg_fps = (len(self._frames) - 1) / total_duration if total_duration > 0 else self._fps
            interval = int(1000 / avg_fps)
        else:
            interval = int(1000 / self._fps)
        
        self._timer.start(interval)
    
    def pause(self):
        """暂停"""
        self._is_playing = False
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self._timer.stop()
    
    def stop(self):
        """停止"""
        self.pause()
        self._current_index = 0
        self.frame_slider.setValue(0)
        self._update_display()
        self._update_labels()
    
    def _on_tick(self):
        """定时器回调"""
        if not self._frames:
            return
        
        self._current_index = (self._current_index + 1) % len(self._frames)
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(self._current_index)
        self.frame_slider.blockSignals(False)
        
        self._update_display()
        self._update_labels()
    
    def _on_slider_moved(self, value):
        """滑块移动"""
        self._current_index = value
        self._update_display()
        self._update_labels()
    
    def _on_speed_changed(self, value):
        """速度改变"""
        self._fps = value
        self.speed_label.setText(f"{value} fps")
        
        if self._is_playing:
            interval = int(1000 / self._fps)
            self._timer.setInterval(interval)
    
    def _on_bg_changed(self, index):
        """背景模式改变"""
        self._bg_mode = self.bg_combo.currentData()
        self.color_btn.setVisible(self._bg_mode == "custom")
        # 切换背景样式（零计算）
        self._update_bg_style()
    
    def _choose_bg_color(self):
        """选择自定义背景色"""
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        
        current_color = QColor(*self._custom_bg_color)
        color = QColorDialog.getColor(current_color, self, "选择背景色")
        
        if color.isValid():
            self._custom_bg_color = (color.red(), color.green(), color.blue())
            self.color_btn.setStyleSheet(
                f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); "
                "border: 1px solid #666; border-radius: 3px;"
            )
            # 切换背景样式（零计算）
            self._update_bg_style()
    
    def _update_display(self):
        """更新显示"""
        if not self._frames or self._current_index >= len(self._frames):
            self.image_label.clear()
            return
        
        pixmap = self._cached_pixmaps[self._current_index]
        # 缩放到适合显示的大小
        scaled = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.FastTransformation
        )
        self.image_label.setPixmap(scaled)
    
    def _update_labels(self):
        """更新标签"""
        total = len(self._frames)
        current = self._current_index + 1 if total > 0 else 0
        self.frame_label.setText(f"{current} / {total}")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()
