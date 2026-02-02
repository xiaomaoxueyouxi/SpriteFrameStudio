"""帧预览网格控件"""
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QLabel, 
    QVBoxLayout, QHBoxLayout, QCheckBox, QFrame, QSizePolicy,
    QPushButton, QDialog, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor
import numpy as np

from src.utils.image_utils import numpy_to_qpixmap, composite_on_checkerboard


class FrameZoomDialog(QDialog):
    """帧放大预览对话框"""
    
    export_requested = Signal(int)  # frame_index
    
    def __init__(self, image: np.ndarray, frame_index: int, parent=None):
        super().__init__(parent)
        self.image = image
        self.frame_index = frame_index
        
        self.setWindowTitle(f"帧 #{frame_index} - 放大预览")
        self.setMinimumSize(600, 600)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 图像标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1a1a1a;")
        layout.addWidget(self.image_label)
        
        # 信息
        h, w = self.image.shape[:2]
        channels = self.image.shape[2] if len(self.image.shape) == 3 else 1
        info = f"尺寸: {w}x{h} | 通道: {channels}"
        if channels == 4:
            alpha = self.image[:, :, 3]
            transparent = np.sum(alpha < 128) / alpha.size * 100
            info += f" | 透明: {transparent:.1f}%"
        
        info_label = QLabel(info)
        info_label.setStyleSheet("color: #888;")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        
        # 导出按钮
        export_btn = QPushButton("导出单帧")
        export_btn.clicked.connect(self._on_export_clicked)
        btn_layout.addWidget(export_btn)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        self._display_image()
    
    def _display_image(self):
        # 如果有透明通道，合成到棋盘格背景
        display_image = self.image
        if len(self.image.shape) == 3 and self.image.shape[2] == 4:
            display_image = composite_on_checkerboard(self.image, square_size=15)
        
        pixmap = numpy_to_qpixmap(display_image)
        
        # 适应窗口大小
        max_size = min(self.width() - 40, self.height() - 100)
        if max_size < 400:
            max_size = 500
        
        scaled = pixmap.scaled(
            max_size, max_size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._display_image()
    
    def _on_export_clicked(self):
        """导出按钮点击事件"""
        self.export_requested.emit(self.frame_index)
        self.accept()


class FrameThumbnail(QFrame):
    """单个帧缩略图控件"""
    
    clicked = Signal(int, bool)  # frame_index, shift_pressed
    double_clicked = Signal(int)  # frame_index - 双击放大
    selection_changed = Signal(int, bool)  # frame_index, is_selected
    
    def __init__(self, frame_index: int, thumbnail_size: int = 120, parent=None):
        super().__init__(parent)
        self.frame_index = frame_index
        self.thumbnail_size = thumbnail_size
        self._is_selected = False
        self._image: Optional[np.ndarray] = None
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        # 图像标签
        self.image_label = QLabel()
        self.image_label.setFixedSize(self.thumbnail_size, self.thumbnail_size)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3d3d3d; border-radius: 4px;")
        layout.addWidget(self.image_label)
        
        # 帧序号
        self.index_label = QLabel(f"#{self.frame_index}")
        self.index_label.setAlignment(Qt.AlignCenter)
        self.index_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.index_label)
        
        # 选中复选框
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(False)
        self.checkbox.stateChanged.connect(self._on_checkbox_changed)
        # 安装事件过滤器来捕获 Shift 键状态
        self.checkbox.installEventFilter(self)
        layout.addWidget(self.checkbox, alignment=Qt.AlignCenter)
        
        self.setFrameStyle(QFrame.Box)
        self.update_style()
    
    def set_image(self, image: np.ndarray):
        """设置图像"""
        self._image = image
        self._update_pixmap()
    
    def _update_pixmap(self):
        if self._image is None:
            return
        
        # 如果有透明通道，合成到棋盘格背景
        display_image = self._image
        if len(self._image.shape) == 3 and self._image.shape[2] == 4:
            display_image = composite_on_checkerboard(self._image)
        
        pixmap = numpy_to_qpixmap(display_image)
        scaled = pixmap.scaled(
            self.thumbnail_size, self.thumbnail_size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
    
    def set_selected(self, selected: bool):
        """设置选中状态"""
        self._is_selected = selected
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(selected)
        self.checkbox.blockSignals(False)
        self.update_style()
    
    def eventFilter(self, obj, event):
        """事件过滤器，捕获复选框的鼠标点击事件"""
        if obj == self.checkbox and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                # 检测 Shift 键状态
                shift_pressed = event.modifiers() & Qt.ShiftModifier
                # 发送点击信号（带 Shift 状态）
                self.clicked.emit(self.frame_index, bool(shift_pressed))
                # 如果按下了 Shift，阻止复选框的默认行为
                if shift_pressed:
                    return True  # 阻止事件继续传播
        return super().eventFilter(obj, event)
    
    def _on_checkbox_changed(self, state):
        # PySide6 中 state 可能是 Qt.CheckState 枚举或整数
        is_selected = (state == Qt.CheckState.Checked or state == 2)
        self._is_selected = is_selected
        self.update_style()
        self.selection_changed.emit(self.frame_index, self._is_selected)
    
    def update_style(self):
        if self._is_selected:
            self.setStyleSheet("""
                FrameThumbnail { 
                    background-color: #0078d4; 
                    border: 2px solid #00b8d4; 
                    border-radius: 6px; 
                }
                QLabel { color: white; }
            """)
        else:
            self.setStyleSheet("""
                FrameThumbnail { 
                    background-color: #2d2d2d; 
                    border: 1px solid #3d3d3d; 
                    border-radius: 6px; 
                }
                FrameThumbnail:hover {
                    background-color: #3d3d3d;
                    border-color: #4d4d4d;
                }
                QLabel { color: #888; }
            """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 普通点击，不传递 Shift 键状态
            self.clicked.emit(self.frame_index, False)
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.frame_index)
        super().mouseDoubleClickEvent(event)
    
    def get_image(self) -> Optional[np.ndarray]:
        """获取图像"""
        return self._image


class FramePreview(QWidget):
    """帧预览网格控件"""
    
    frame_clicked = Signal(int)  # frame_index
    selection_changed = Signal(list)  # List[int] selected indices
    status_message = Signal(str)  # 状态消息
    export_single_frame = Signal(int)  # frame_index
    
    def __init__(self, thumbnail_size: int = 120, columns: int = 4, parent=None):
        super().__init__(parent)
        self.thumbnail_size = thumbnail_size
        self.columns = columns
        self._thumbnails: List[FrameThumbnail] = []
        self._batch_update_mode = False  # 批量更新模式，禁止信号触发
        self._last_clicked_index: Optional[int] = None  # 记录最后一次单击选中的帧索引
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 8, 8, 8)
        
        btn_style = """
            QPushButton {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
                border-radius: 4px;
                padding: 5px 10px;
                color: #ddd;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
                border-color: #00b8d4;
            }
        """
        
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setStyleSheet(btn_style)
        self.select_all_btn.clicked.connect(self.select_all)
        toolbar.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.setStyleSheet(btn_style)
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        toolbar.addWidget(self.deselect_all_btn)
        
        # 间隔选帧工具
        toolbar.addSpacing(10)
        toolbar.addWidget(QLabel("间隔:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(2, 100)
        self.interval_spin.setValue(2)
        self.interval_spin.setFixedWidth(50)
        self.interval_spin.setStyleSheet("background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 2px; color: #eee;")
        toolbar.addWidget(self.interval_spin)
        
        self.interval_select_btn = QPushButton("⏹ 间隔选帧")
        self.interval_select_btn.setStyleSheet(btn_style)
        self.interval_select_btn.setToolTip("在当前勾选范围内按间隔重新选帧，强制保留首尾帧")
        self.interval_select_btn.clicked.connect(self._on_interval_select_clicked)
        toolbar.addWidget(self.interval_select_btn)
        
        toolbar.addStretch()
        
        self.selection_info = QLabel("已选择: 0 帧")
        self.selection_info.setStyleSheet("color: #888;")
        toolbar.addWidget(self.selection_info)
        
        # 提示
        tip_label = QLabel("(双击帧可放大，预览中可导出单帧 | Shift+点击可连续选中)")
        tip_label.setStyleSheet("color: #666; font-size: 11px;")
        toolbar.addWidget(tip_label)
        
        layout.addLayout(toolbar)
        
        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll_area)
        
        # 内容容器
        self.content_widget = QWidget()
        self.grid_layout = QGridLayout(self.content_widget)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        
        self.scroll_area.setWidget(self.content_widget)
    
    def clear(self):
        """清空所有缩略图"""
        for thumb in self._thumbnails:
            thumb.deleteLater()
        self._thumbnails.clear()
        
        # 清空布局
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def set_frames(self, frames: list):
        """设置帧数据"""
        self.clear()
        
        for i, frame in enumerate(frames):
            thumb = FrameThumbnail(frame.index, self.thumbnail_size)
            
            # 设置图像
            if frame.display_image is not None:
                thumb.set_image(frame.display_image)
            
            # 设置选中状态
            thumb.set_selected(frame.is_selected)
            
            # 连接信号
            thumb.clicked.connect(self._on_thumbnail_clicked)
            thumb.double_clicked.connect(self._on_thumbnail_double_clicked)
            thumb.selection_changed.connect(self._on_selection_changed)
            
            # 添加到网格
            row = i // self.columns
            col = i % self.columns
            self.grid_layout.addWidget(thumb, row, col)
            
            self._thumbnails.append(thumb)
        
        self._update_selection_info()
    
    def update_frame(self, index: int, image: np.ndarray):
        """更新单帧图像"""
        for thumb in self._thumbnails:
            if thumb.frame_index == index:
                thumb.set_image(image)
                break
    
    def update_selection(self, index: int, selected: bool):
        """更新选中状态"""
        for thumb in self._thumbnails:
            if thumb.frame_index == index:
                thumb.set_selected(selected)
                break
    
    def select_all(self):
        """全选"""
        for thumb in self._thumbnails:
            thumb.set_selected(True)
        self._update_selection_info()
        self.selection_changed.emit(self.get_selected_indices())
    
    def deselect_all(self):
        """取消全选"""
        for thumb in self._thumbnails:
            thumb.set_selected(False)
        self._update_selection_info()
        self.selection_changed.emit(self.get_selected_indices())
    
    def get_selected_indices(self) -> List[int]:
        """获取选中的帧索引"""
        return [thumb.frame_index for thumb in self._thumbnails if thumb._is_selected]
    
    def _on_interval_select_clicked(self):
        """处理间隔选帧逻辑：仅作用于当前已选中的帧范围"""
        selected_indices = self.get_selected_indices()
        if not selected_indices:
            return
            
        interval = self.interval_spin.value()
        if interval <= 1:
            return
            
        first_idx = selected_indices[0]
        last_idx = selected_indices[-1]
        
        # 在已选中集合中进行筛选
        selected_set = set(selected_indices)
        new_selection = set()
        
        # 从第一个选中的帧开始，按间隔跳跃
        for i in range(first_idx, last_idx + 1, interval):
            if i in selected_set:
                new_selection.add(i)
        
        # 确保包含最后一个原本选中的帧
        new_selection.add(last_idx)
        
        # 批量更新 UI
        self.begin_batch_update()
        # 遍历所有缩略图，如果在原本选中的范围内，则根据新集合决定是否选中
        for thumb in self._thumbnails:
            if thumb.frame_index in selected_set:
                thumb.set_selected(thumb.frame_index in new_selection)
        self.end_batch_update()
        
        msg = f"间隔选帧完成：从 {len(selected_indices)} 帧中保留了 {len(new_selection)} 帧"
        self.status_message.emit(msg)

    def _on_thumbnail_clicked(self, frame_index: int, shift_pressed: bool = False):
        """处理缩略图点击事件，支持Shift连续选中"""
        if shift_pressed and self._last_clicked_index is not None:
            # Shift + 点击复选框：连续选中范围内的帧
            start_idx = min(self._last_clicked_index, frame_index)
            end_idx = max(self._last_clicked_index, frame_index)
            
            self.begin_batch_update()
            # 选中范围内的所有帧
            for thumb in self._thumbnails:
                if start_idx <= thumb.frame_index <= end_idx:
                    thumb.set_selected(True)
            self.end_batch_update()
            
            # 更新最后点击的索引
            self._last_clicked_index = frame_index
        
        # 发送点击信号用于预览
        self.frame_clicked.emit(frame_index)
    
    def _on_thumbnail_double_clicked(self, frame_index: int):
        """双击帧放大预览"""
        for thumb in self._thumbnails:
            if thumb.frame_index == frame_index:
                image = thumb.get_image()
                if image is not None:
                    dialog = FrameZoomDialog(image, frame_index, parent=self)
                    # 连接导出信号
                    dialog.export_requested.connect(self.export_single_frame)
                    dialog.exec()
                break
    
    def _on_selection_changed(self, frame_index: int, is_selected: bool):
        """处理选中状态变化，记录最后一次选中的帧"""
        # 记录最后一次选中的帧索引，用于Shift连续选中
        if is_selected:
            self._last_clicked_index = frame_index
        
        self._update_selection_info()
        # 批量更新模式下不发送信号
        if not self._batch_update_mode:
            self.selection_changed.emit(self.get_selected_indices())
    
    def begin_batch_update(self):
        """开始批量更新（禁止信号触发）"""
        self._batch_update_mode = True
    
    def end_batch_update(self):
        """结束批量更新（发送一次信号）"""
        self._batch_update_mode = False
        self._update_selection_info()
        self.selection_changed.emit(self.get_selected_indices())
    
    def _update_selection_info(self):
        """更新选中数量显示"""
        count = len(self.get_selected_indices())
        total = len(self._thumbnails)
        self.selection_info.setText(f"已选择: {count}/{total} 帧")
