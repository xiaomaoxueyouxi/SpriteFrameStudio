"""姿势骨架可视化控件"""
from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import numpy as np

from src.models.pose_data import PoseData
from src.core.pose_detector import PoseDetector
from src.utils.image_utils import numpy_to_qpixmap


class PoseViewer(QWidget):
    """姿势骨架可视化控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._image: Optional[np.ndarray] = None
        self._pose: Optional[PoseData] = None
        self._detector = PoseDetector()
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 图像显示区域
        self.image_label = QLabel("👤\n等待姿势分析结果")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 8px;
                color: #555;
                font-size: 24px;
                font-weight: bold;
            }
        """)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.image_label)
        
        # 信息标签
        self.info_label = QLabel("未检测到姿势")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        layout.addWidget(self.info_label)
    
    def set_image(self, image: np.ndarray):
        """设置图像"""
        self._image = image
        self._update_display()
    
    def set_pose(self, pose: Optional[PoseData]):
        """设置姿势数据"""
        self._pose = pose
        self._update_display()
        self._update_info()
    
    def set_image_and_pose(self, image: np.ndarray, pose: Optional[PoseData]):
        """同时设置图像和姿势"""
        self._image = image
        self._pose = pose
        self._update_display()
        self._update_info()
    
    def clear(self):
        """清空显示"""
        self._image = None
        self._pose = None
        self.image_label.clear()
        self.info_label.setText("未检测到姿势")
    
    def _update_display(self):
        """更新显示"""
        if self._image is None:
            self.image_label.clear()
            return
        
        # 绘制姿势骨架
        display_image = self._image
        if self._pose is not None:
            display_image = self._detector.draw_pose_on_image(
                self._image, 
                self._pose,
                landmark_color=(0, 255, 0),
                connection_color=(255, 255, 255),
                thickness=2
            )
        
        # 转换为QPixmap并显示
        pixmap = numpy_to_qpixmap(display_image)
        scaled = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
    
    def _update_info(self):
        """更新信息标签"""
        if self._pose is None:
            self.info_label.setText("未检测到姿势")
        else:
            visible_count = sum(1 for lm in self._pose.landmarks if lm.visibility > 0.5)
            confidence = self._pose.confidence * 100
            self.info_label.setText(f"检测到 {visible_count}/33 个关键点 | 置信度: {confidence:.1f}%")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()
