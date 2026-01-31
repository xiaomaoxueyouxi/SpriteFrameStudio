"""动画预览控件"""
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QStyle, QSizePolicy, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTimer
import numpy as np

from src.utils.image_utils import numpy_to_qpixmap, composite_on_checkerboard


class AnimationPreview(QWidget):
    """动画预览控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: List[np.ndarray] = []
        self._current_index = 0
        self._is_playing = False
        self._fps = 24.0
        self._bg_mode = "checkerboard"  # 背景模式: checkerboard, white, black, gray, custom
        self._custom_bg_color = (128, 128, 128)  # 自定义背景色 (RGB)
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 图像显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1a1a1a;")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        self.bg_combo.addItem("⚫ 棋盘格", "checkerboard")
        self.bg_combo.addItem("⚪ 白色", "white")
        self.bg_combo.addItem("⚫ 黑色", "black")
        self.bg_combo.addItem("● 灰色", "gray")
        self.bg_combo.addItem("⭕ 自定义...", "custom")
        self.bg_combo.currentIndexChanged.connect(self._on_bg_changed)
        bg_layout.addWidget(self.bg_combo)
        
        # 颜色选择按钮（仅在自定义时显示）
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
    
    def set_frames(self, frames: List[np.ndarray]):
        """设置帧序列"""
        self.stop()
        self._frames = frames
        self._current_index = 0
        
        self.frame_slider.setRange(0, max(0, len(frames) - 1))
        self.frame_slider.setValue(0)
        
        self._update_display()
        self._update_labels()
    
    def clear(self):
        """清空帧"""
        self.stop()
        self._frames = []
        self._current_index = 0
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
        
        # 如果是自定义模式，显示颜色选择按钮
        self.color_btn.setVisible(self._bg_mode == "custom")
        
        # 重新渲染
        self._update_display()
    
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
                f"border: 1px solid #666; border-radius: 3px;"
            )
            self._update_display()
    
    def _update_display(self):
        """更新显示"""
        if not self._frames or self._current_index >= len(self._frames):
            self.image_label.clear()
            return
        
        frame = self._frames[self._current_index]
        
        # 如果有透明通道，根据背景模式合成
        if len(frame.shape) == 3 and frame.shape[2] == 4:
            frame = self._composite_background(frame)
        
        pixmap = numpy_to_qpixmap(frame)
        scaled = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
    
    def _composite_background(self, image: np.ndarray) -> np.ndarray:
        """将透明图像合成到指定背景"""
        if self._bg_mode == "checkerboard":
            # 棋盘格背景
            return composite_on_checkerboard(image)
        
        # 创建纯色背景
        h, w = image.shape[:2]
        
        if self._bg_mode == "white":
            background = np.ones((h, w, 3), dtype=np.uint8) * 255
        elif self._bg_mode == "black":
            background = np.zeros((h, w, 3), dtype=np.uint8)
        elif self._bg_mode == "gray":
            background = np.ones((h, w, 3), dtype=np.uint8) * 128
        elif self._bg_mode == "custom":
            background = np.ones((h, w, 3), dtype=np.uint8)
            background[:, :] = self._custom_bg_color
        else:
            # 默认棋盘格
            return composite_on_checkerboard(image)
        
        # Alpha 混合
        alpha = image[:, :, 3:4] / 255.0
        rgb = image[:, :, :3]
        result = (rgb * alpha + background * (1 - alpha)).astype(np.uint8)
        
        return result
    
    def _update_labels(self):
        """更新标签"""
        total = len(self._frames)
        current = self._current_index + 1 if total > 0 else 0
        self.frame_label.setText(f"{current} / {total}")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()
