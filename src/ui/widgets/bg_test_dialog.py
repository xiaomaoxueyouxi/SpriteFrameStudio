"""背景去除测试对话框"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import numpy as np

from src.utils.image_utils import numpy_to_qpixmap, composite_on_checkerboard


class BackgroundTestDialog(QDialog):
    """背景去除效果测试对话框"""
    
    def __init__(self, original: np.ndarray, processed: np.ndarray, parent=None):
        super().__init__(parent)
        self.original = original
        self.processed = processed
        
        self.setWindowTitle("背景去除效果测试")
        self.setMinimumSize(800, 500)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 图像对比区域
        compare_layout = QHBoxLayout()
        
        # 原图
        original_group = QVBoxLayout()
        original_label = QLabel("原图")
        original_label.setAlignment(Qt.AlignCenter)
        original_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        original_group.addWidget(original_label)
        
        self.original_image = QLabel()
        self.original_image.setAlignment(Qt.AlignCenter)
        self.original_image.setStyleSheet("background-color: #2d2d2d; border: 1px solid #3d3d3d;")
        self.original_image.setMinimumSize(350, 350)
        original_group.addWidget(self.original_image)
        
        compare_layout.addLayout(original_group)
        
        # 处理后
        processed_group = QVBoxLayout()
        processed_label = QLabel("去背景后 (棋盘格表示透明)")
        processed_label.setAlignment(Qt.AlignCenter)
        processed_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        processed_group.addWidget(processed_label)
        
        self.processed_image = QLabel()
        self.processed_image.setAlignment(Qt.AlignCenter)
        self.processed_image.setStyleSheet("background-color: #2d2d2d; border: 1px solid #3d3d3d;")
        self.processed_image.setMinimumSize(350, 350)
        processed_group.addWidget(self.processed_image)
        
        compare_layout.addLayout(processed_group)
        
        layout.addLayout(compare_layout)
        
        # 信息标签
        info_text = f"原图尺寸: {self.original.shape[1]}x{self.original.shape[0]}"
        if len(self.processed.shape) == 3:
            channels = self.processed.shape[2]
            info_text += f" | 处理后: {self.processed.shape[1]}x{self.processed.shape[0]}, {channels}通道"
            if channels == 4:
                # 统计透明像素
                alpha = self.processed[:, :, 3]
                transparent = np.sum(alpha < 128)
                total = alpha.size
                percent = transparent / total * 100
                info_text += f" | 透明像素: {percent:.1f}%"
        
        self.info_label = QLabel(info_text)
        self.info_label.setStyleSheet("color: #888;")
        layout.addWidget(self.info_label)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        # 显示图像
        self._display_images()
    
    def _display_images(self):
        """显示图像"""
        max_size = 350
        
        # 原图
        original_pixmap = numpy_to_qpixmap(self.original)
        scaled_original = original_pixmap.scaled(
            max_size, max_size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.original_image.setPixmap(scaled_original)
        
        # 处理后 - 合成到棋盘格背景显示透明效果
        display_processed = self.processed
        if len(self.processed.shape) == 3 and self.processed.shape[2] == 4:
            display_processed = composite_on_checkerboard(self.processed)
        
        processed_pixmap = numpy_to_qpixmap(display_processed)
        scaled_processed = processed_pixmap.scaled(
            max_size, max_size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.processed_image.setPixmap(scaled_processed)
    
    def resizeEvent(self, event):
        """窗口大小变化时重新缩放图像"""
        super().resizeEvent(event)
        self._display_images()
