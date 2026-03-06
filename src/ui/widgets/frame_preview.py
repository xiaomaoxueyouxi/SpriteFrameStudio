"""帧预览网格控件"""
from typing import Optional, List, Tuple
from dataclasses import dataclass
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QLabel, 
    QVBoxLayout, QHBoxLayout, QCheckBox, QFrame, QSizePolicy,
    QPushButton, QDialog, QSpinBox, QSlider, QComboBox, QGroupBox,
    QMessageBox, QColorDialog
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent, QPoint
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QCursor, QPen
import numpy as np

from src.utils.image_utils import numpy_to_qpixmap, composite_on_checkerboard
from src.utils.config import config
from src.core.magic_wand import MagicWand, clean_small_regions, grow_selection, shrink_selection


class FrameImageCanvas(QWidget):
    """帧图像画布 - 支持滚轮缩放和中键拖动"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._pixmap: Optional[QPixmap] = None
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 32.0
        
        self._panning = False
        self._last_pan_pos = QPoint()
        self._offset_x = 0
        self._offset_y = 0
        
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(400, 300)
    
    def set_pixmap(self, pixmap: QPixmap, reset_view: bool = True):
        """设置图像"""
        self._pixmap = pixmap
        if reset_view:
            self._fit_to_view()
        else:
            self.update()
    
    def _fit_to_view(self):
        """适应窗口大小"""
        if self._pixmap is None:
            return
        
        view_w = self.width() - 40
        view_h = self.height() - 40
        
        if view_w <= 0 or view_h <= 0:
            return
        
        img_w = self._pixmap.width()
        img_h = self._pixmap.height()
        
        scale_x = view_w / img_w
        scale_y = view_h / img_h
        self._zoom = min(scale_x, scale_y, 1.0)
        
        self._offset_x = (self.width() - img_w * self._zoom) / 2
        self._offset_y = (self.height() - img_h * self._zoom) / 2
        
        self.update()
    
    def get_zoom(self) -> float:
        return self._zoom
    
    def set_zoom(self, zoom: float, center_pos: QPoint = None):
        """设置缩放级别，可选以指定位置为中心"""
        if self._pixmap is None:
            return
        
        old_zoom = self._zoom
        self._zoom = max(self._min_zoom, min(self._max_zoom, zoom))
        
        if center_pos is not None:
            # 以鼠标位置为中心缩放
            img_x = (center_pos.x() - self._offset_x) / old_zoom
            img_y = (center_pos.y() - self._offset_y) / old_zoom
            
            self._offset_x = center_pos.x() - img_x * self._zoom
            self._offset_y = center_pos.y() - img_y * self._zoom
        else:
            # 以画布中心为中心缩放
            center_x = self.width() / 2
            center_y = self.height() / 2
            
            img_x = (center_x - self._offset_x) / old_zoom
            img_y = (center_y - self._offset_y) / old_zoom
            
            self._offset_x = center_x - img_x * self._zoom
            self._offset_y = center_y - img_y * self._zoom
        
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # 填充背景
        painter.fillRect(self.rect(), QColor(26, 26, 26))
        
        if self._pixmap is None:
            return
        
        # 绘制缩放后的图像
        target_w = int(self._pixmap.width() * self._zoom)
        target_h = int(self._pixmap.height() * self._zoom)
        
        if target_w > 0 and target_h > 0:
            scaled = self._pixmap.scaled(
                target_w, target_h,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(int(self._offset_x), int(self._offset_y), scaled)
    
    def wheelEvent(self, event):
        """滚轮缩放"""
        if self._pixmap is None:
            return
        
        delta = event.angleDelta().y()
        if delta == 0:
            return
        
        # 缩放因子
        factor = 1.1 if delta > 0 else 1 / 1.1
        new_zoom = self._zoom * factor
        
        # 以鼠标位置为中心缩放
        self.set_zoom(new_zoom, event.position().toPoint())
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            self._panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(QCursor(Qt.ClosedHandCursor))
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._last_pan_pos
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._last_pan_pos = event.pos()
            self.update()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            self._panning = False
            self.setCursor(QCursor(Qt.ArrowCursor))
        else:
            super().mouseReleaseEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 保持图像居中
        if self._pixmap:
            self.update()


@dataclass
class EditorState:
    """编辑器状态"""
    image: np.ndarray
    selection_mask: Optional[np.ndarray] = None


class EditorHistory:
    """编辑器历史记录"""
    
    MAX_HISTORY = 30
    
    def __init__(self):
        self._states: List[EditorState] = []
        self._current_index = -1
    
    def push(self, state: EditorState):
        if self._current_index < len(self._states) - 1:
            self._states = self._states[:self._current_index + 1]
        self._states.append(state)
        self._current_index = len(self._states) - 1
        while len(self._states) > self.MAX_HISTORY:
            self._states.pop(0)
            self._current_index -= 1
    
    def undo(self) -> Optional[EditorState]:
        if self._current_index > 0:
            self._current_index -= 1
            return self._states[self._current_index]
        return None
    
    def redo(self) -> Optional[EditorState]:
        if self._current_index < len(self._states) - 1:
            self._current_index += 1
            return self._states[self._current_index]
        return None
    
    def can_undo(self) -> bool:
        return self._current_index > 0
    
    def can_redo(self) -> bool:
        return self._current_index < len(self._states) - 1
    
    def clear(self):
        self._states.clear()
        self._current_index = -1


def _create_checkerboard_fast(width: int, height: int, square_size: int = 10) -> np.ndarray:
    """快速创建棋盘格背景"""
    board = np.zeros((height, width, 3), dtype=np.uint8)
    y_coords, x_coords = np.ogrid[:height, :width]
    grid_x = x_coords // square_size
    grid_y = y_coords // square_size
    use_color1 = ((grid_x + grid_y) % 2 == 0)
    board[use_color1] = [200, 200, 200]
    board[~use_color1] = [255, 255, 255]
    return board


class EditorCanvas(QWidget):
    """编辑器画布 - 支持选区显示和魔棒工具"""
    
    selection_changed = Signal()
    image_changed = Signal()
    zoom_changed = Signal()  # 缩放变化信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._image: Optional[np.ndarray] = None
        self._display_pixmap: Optional[QPixmap] = None
        self._selection_mask: Optional[np.ndarray] = None
        
        self._bg_mode = "checkerboard"
        self._checkerboard_cache: Optional[np.ndarray] = None
        
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 32.0
        
        self._panning = False
        self._last_pan_pos = QPoint()
        self._offset_x = 0
        self._offset_y = 0
        
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(400, 300)
    
    def set_image(self, image: np.ndarray, reset_view: bool = True):
        self._image = image.copy()
        if reset_view:
            self._selection_mask = None
            self._update_display_pixmap()
            self._fit_to_view()
        else:
            self._update_display_pixmap()
            self.update()  # 刷新显示
        self.image_changed.emit()
    
    def get_image(self) -> Optional[np.ndarray]:
        return self._image.copy() if self._image is not None else None
    
    def set_selection(self, mask: Optional[np.ndarray]):
        if mask is not None:
            mask = np.clip(mask, 0, 1).astype(np.float32)
        self._selection_mask = mask
        self.update()
        self.selection_changed.emit()
    
    def get_selection(self) -> Optional[np.ndarray]:
        return self._selection_mask.copy() if self._selection_mask is not None else None
    
    def has_selection(self) -> bool:
        return self._selection_mask is not None and np.any(self._selection_mask > 0)
    
    def set_background_mode(self, mode: str):
        self._bg_mode = mode
        self._update_display_pixmap()
        self.update()
    
    def _update_display_pixmap(self):
        if self._image is None:
            self._display_pixmap = None
            return
        display = self._image
        if len(display.shape) == 3 and display.shape[2] == 4:
            display = self._composite_background(display)
        self._display_pixmap = numpy_to_qpixmap(display)
    
    def _composite_background(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        alpha = image[:, :, 3:4] / 255.0
        rgb = image[:, :, :3]
        
        if self._bg_mode == "checkerboard":
            if self._checkerboard_cache is None or self._checkerboard_cache.shape[:2] != (h, w):
                self._checkerboard_cache = _create_checkerboard_fast(w, h)
            bg = self._checkerboard_cache
        elif self._bg_mode == "white":
            bg = np.full((h, w, 3), 255, dtype=np.uint8)
        elif self._bg_mode == "black":
            bg = np.full((h, w, 3), 0, dtype=np.uint8)
        else:
            bg = np.full((h, w, 3), 128, dtype=np.uint8)
        
        result = (rgb * alpha + bg * (1 - alpha)).astype(np.uint8)
        return result
    
    def _fit_to_view(self):
        if self._display_pixmap is None:
            return
        view_w = self.width() - 40
        view_h = self.height() - 40
        if view_w <= 0 or view_h <= 0:
            return
        img_w = self._display_pixmap.width()
        img_h = self._display_pixmap.height()
        scale_x = view_w / img_w
        scale_y = view_h / img_h
        self._zoom = min(scale_x, scale_y, 1.0)
        self._offset_x = (self.width() - img_w * self._zoom) / 2
        self._offset_y = (self.height() - img_h * self._zoom) / 2
        self.update()
    
    def image_to_screen(self, img_x: int, img_y: int) -> Tuple[int, int]:
        sx = int(img_x * self._zoom + self._offset_x)
        sy = int(img_y * self._zoom + self._offset_y)
        return sx, sy
    
    def screen_to_image(self, sx: int, sy: int) -> Tuple[int, int]:
        if self._zoom == 0:
            return 0, 0
        img_x = int((sx - self._offset_x) / self._zoom)
        img_y = int((sy - self._offset_y) / self._zoom)
        return img_x, img_y
    
    def get_zoom(self) -> float:
        return self._zoom
    
    def set_zoom(self, zoom: float):
        if self._display_pixmap is None:
            return
        old_zoom = self._zoom
        self._zoom = max(self._min_zoom, min(self._max_zoom, zoom))
        center_x = self.width() / 2
        center_y = self.height() / 2
        img_x, img_y = self.screen_to_image(int(center_x), int(center_y))
        self._offset_x = center_x - img_x * self._zoom
        self._offset_y = center_y - img_y * self._zoom
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QColor(45, 45, 45))
        
        if self._display_pixmap is not None:
            target_w = int(self._display_pixmap.width() * self._zoom)
            target_h = int(self._display_pixmap.height() * self._zoom)
            painter.drawPixmap(
                int(self._offset_x), int(self._offset_y),
                target_w, target_h,
                self._display_pixmap
            )
            if self._selection_mask is not None and np.any(self._selection_mask > 0):
                self._draw_selection_overlay(painter)
        
        if self._display_pixmap is not None:
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawRect(
                int(self._offset_x) - 1, int(self._offset_y) - 1,
                int(self._display_pixmap.width() * self._zoom) + 1,
                int(self._display_pixmap.height() * self._zoom) + 1
            )
    
    def _draw_selection_overlay(self, painter: QPainter):
        if self._selection_mask is None:
            return
        h, w = self._selection_mask.shape
        zoom = self._zoom
        offset_x = self._offset_x
        offset_y = self._offset_y
        binary_mask = (self._selection_mask > 0.5)
        overlay_rgba = np.zeros((h, w, 4), dtype=np.uint8)
        overlay_rgba[binary_mask] = [0, 255, 0, 80]
        overlay = QImage(overlay_rgba.data, w, h, w * 4, QImage.Format_ARGB32)
        scaled_overlay = overlay.scaled(
            int(w * zoom), int(h * zoom),
            Qt.IgnoreAspectRatio, Qt.FastTransformation
        )
        painter.drawImage(int(offset_x), int(offset_y), scaled_overlay)
        painter.setPen(QPen(QColor(0, 255, 0), 2))
        rows = np.any(binary_mask, axis=1)
        cols = np.any(binary_mask, axis=0)
        if np.any(rows) and np.any(cols):
            y_min, y_max = np.where(rows)[0][[0, -1]]
            x_min, x_max = np.where(cols)[0][[0, -1]]
            painter.drawRect(
                int(x_min * zoom + offset_x), int(y_min * zoom + offset_y),
                int((x_max - x_min + 1) * zoom), int((y_max - y_min + 1) * zoom)
            )
    
    def wheelEvent(self, event):
        if self._display_pixmap is None:
            return
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        new_zoom = self._zoom * factor
        new_zoom = max(self._min_zoom, min(self._max_zoom, new_zoom))
        mouse_pos = event.position()
        img_x, img_y = self.screen_to_image(int(mouse_pos.x()), int(mouse_pos.y()))
        self._zoom = new_zoom
        self._offset_x = mouse_pos.x() - img_x * self._zoom
        self._offset_y = mouse_pos.y() - img_y * self._zoom
        self.update()
        self.zoom_changed.emit()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            self._panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(QCursor(Qt.ClosedHandCursor))
    
    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._last_pan_pos
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._last_pan_pos = event.pos()
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            self._panning = False
            self.setCursor(QCursor(Qt.ArrowCursor))
    
    def keyPressEvent(self, event):
        # 把键盘事件传递给父对话框处理
        parent = self.parent()
        while parent and not isinstance(parent, QDialog):
            parent = parent.parent()
        if parent:
            parent.keyPressEvent(event)
        else:
            super().keyPressEvent(event)


class FrameEditorDialog(QDialog):
    """帧编辑器对话框 - 合并帧预览和魔棒编辑功能"""
    
    export_requested = Signal(int)
    image_edited = Signal(int, np.ndarray)
    
    PANEL_STYLE = """
        QFrame { background-color: #252525; border-right: 1px solid #3d3d3d; }
        QGroupBox { color: #ddd; border: 1px solid #3d3d3d; border-radius: 4px; margin-top: 10px; padding-top: 10px; font-weight: bold; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QLabel { color: #aaa; }
        QSlider::groove:horizontal { height: 6px; background: #3d3d3d; border-radius: 3px; }
        QSlider::handle:horizontal { background: #0078d4; width: 14px; margin: -4px 0; border-radius: 7px; }
        QSpinBox { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 2px; color: #ddd; }
        QCheckBox { color: #ddd; }
        QComboBox { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 2px; color: #ddd; }
        QPushButton { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 5px 10px; color: #ddd; }
        QPushButton:hover { background-color: #4d4d4d; border-color: #0078d4; }
        QPushButton:checked { background-color: #0078d4; border-color: #0078d4; }
        QPushButton:disabled { background-color: #2d2d2d; color: #666; }
    """
    
    def __init__(self, images: List[np.ndarray], frame_indices: List[int], current_index: int = 0, parent=None):
        super().__init__(parent)
        
        self._original_images = [img.copy() for img in images]
        self._images = [img.copy() for img in images]
        self._frame_indices = list(frame_indices)
        self._current_index = current_index
        
        # 每帧的历史记录
        self._histories: List[EditorHistory] = [EditorHistory() for _ in images]
        
        # 编辑工具状态
        self._magic_wand = MagicWand()
        self._tool_mode = "magic_wand"
        self._tolerance = 32
        self._contiguous = True
        self._anti_alias = True
        self._eraser_size = 10
        self._is_erasing = False
        self._fill_color = (255, 255, 255, 255)
        
        self._result_saved = False
        
        self.setWindowTitle(f"帧编辑器 - #{self._frame_indices[self._current_index]}")
        self.setMinimumSize(1100, 750)
        self.resize(1300, 850)
        self.setFocusPolicy(Qt.StrongFocus)  # 确保能接收键盘事件
        
        self._setup_ui()
        self._setup_connections()
        # 为每一帧初始化历史记录
        for i in range(len(self._images)):
            state = EditorState(image=self._images[i].copy(), selection_mask=None)
            self._histories[i].push(state)
        self._load_frame(self._current_index)
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 左侧工具面板
        left_panel = self._create_left_panel()
        layout.addWidget(left_panel)
        
        # 中间区域
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        
        # 顶部导航栏
        top_bar = self._create_top_bar()
        center.addWidget(top_bar)
        
        # 画布
        self._canvas = EditorCanvas()
        center.addWidget(self._canvas, 1)
        
        # 底部状态栏
        bottom_bar = self._create_bottom_bar()
        center.addWidget(bottom_bar)
        
        layout.addLayout(center, 1)
        
        # 右侧信息面板
        right_panel = self._create_right_panel()
        layout.addWidget(right_panel)
    
    def _create_left_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(200)
        panel.setStyleSheet(self.PANEL_STYLE)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 工具选择
        tool_group = QGroupBox("工具")
        tool_layout = QVBoxLayout(tool_group)
        
        self._magic_wand_btn = QPushButton("🪄 魔棒")
        self._magic_wand_btn.setCheckable(True)
        self._magic_wand_btn.setChecked(True)
        tool_layout.addWidget(self._magic_wand_btn)
        
        self._eraser_btn = QPushButton("🧹 橡皮擦")
        self._eraser_btn.setCheckable(True)
        tool_layout.addWidget(self._eraser_btn)
        
        self._move_btn = QPushButton("✋ 移动")
        self._move_btn.setCheckable(True)
        tool_layout.addWidget(self._move_btn)
        
        layout.addWidget(tool_group)
        
        # 选区模式
        mode_group = QGroupBox("选区模式")
        mode_layout = QVBoxLayout(mode_group)
        self._selection_mode_combo = QComboBox()
        self._selection_mode_combo.addItem("新建选区", "new")
        self._selection_mode_combo.addItem("添加到选区", "add")
        self._selection_mode_combo.addItem("从选区减去", "subtract")
        self._selection_mode_combo.addItem("选区交集", "intersect")
        mode_layout.addWidget(self._selection_mode_combo)
        layout.addWidget(mode_group)
        
        # 魔棒参数
        wand_group = QGroupBox("魔棒参数")
        wand_layout = QVBoxLayout(wand_group)
        
        wand_layout.addWidget(QLabel("颜色容差:"))
        tol_row = QHBoxLayout()
        self._tolerance_slider = QSlider(Qt.Horizontal)
        self._tolerance_slider.setRange(0, 255)
        self._tolerance_slider.setValue(self._tolerance)
        tol_row.addWidget(self._tolerance_slider)
        self._tolerance_spin = QSpinBox()
        self._tolerance_spin.setRange(0, 255)
        self._tolerance_spin.setValue(self._tolerance)
        self._tolerance_spin.setFixedWidth(60)
        tol_row.addWidget(self._tolerance_spin)
        wand_layout.addLayout(tol_row)
        
        self._contiguous_check = QCheckBox("连续选区")
        self._contiguous_check.setChecked(True)
        wand_layout.addWidget(self._contiguous_check)
        
        self._anti_alias_check = QCheckBox("抗锯齿")
        self._anti_alias_check.setChecked(True)
        wand_layout.addWidget(self._anti_alias_check)
        
        layout.addWidget(wand_group)
        
        # 橡皮擦参数
        eraser_group = QGroupBox("橡皮擦参数")
        eraser_layout = QVBoxLayout(eraser_group)
        eraser_layout.addWidget(QLabel("大小:"))
        eraser_row = QHBoxLayout()
        self._eraser_slider = QSlider(Qt.Horizontal)
        self._eraser_slider.setRange(1, 50)
        self._eraser_slider.setValue(self._eraser_size)
        eraser_row.addWidget(self._eraser_slider)
        self._eraser_spin = QSpinBox()
        self._eraser_spin.setRange(1, 50)
        self._eraser_spin.setValue(self._eraser_size)
        self._eraser_spin.setSuffix("px")
        self._eraser_spin.setFixedWidth(60)
        eraser_row.addWidget(self._eraser_spin)
        eraser_layout.addLayout(eraser_row)
        layout.addWidget(eraser_group)
        
        # 编辑操作
        edit_group = QGroupBox("编辑操作")
        edit_layout = QVBoxLayout(edit_group)
        
        self._delete_btn = QPushButton("删除选区")
        edit_layout.addWidget(self._delete_btn)
        
        self._fill_btn = QPushButton("填充选区")
        edit_layout.addWidget(self._fill_btn)
        
        fill_row = QHBoxLayout()
        fill_row.addWidget(QLabel("颜色:"))
        self._fill_color_btn = QPushButton()
        self._fill_color_btn.setFixedSize(40, 25)
        self._update_fill_color_btn()
        fill_row.addWidget(self._fill_color_btn)
        fill_row.addStretch()
        edit_layout.addLayout(fill_row)
        
        grow_shrink = QHBoxLayout()
        self._grow_btn = QPushButton("扩大")
        grow_shrink.addWidget(self._grow_btn)
        self._shrink_btn = QPushButton("缩小")
        grow_shrink.addWidget(self._shrink_btn)
        edit_layout.addLayout(grow_shrink)
        
        self._invert_btn = QPushButton("反选")
        edit_layout.addWidget(self._invert_btn)
        
        self._deselect_btn = QPushButton("取消选区")
        edit_layout.addWidget(self._deselect_btn)
        
        layout.addWidget(edit_group)
        
        layout.addStretch()
        
        return panel
    
    def _create_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet("QFrame { background-color: #2d2d2d; border-bottom: 1px solid #3d3d3d; }")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # 帧导航
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedWidth(40)
        self._prev_btn.setEnabled(self._current_index > 0)
        layout.addWidget(self._prev_btn)
        
        self._frame_counter = QLabel(f"{self._current_index + 1}/{len(self._images)}")
        self._frame_counter.setStyleSheet("color: #fff; font-weight: bold; min-width: 50px;")
        self._frame_counter.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._frame_counter)
        
        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(40)
        self._next_btn.setEnabled(self._current_index < len(self._images) - 1)
        layout.addWidget(self._next_btn)
        
        layout.addSpacing(20)
        
        # 缩放
        layout.addWidget(QLabel("缩放:"))
        self._zoom_out_btn = QPushButton("-")
        self._zoom_out_btn.setFixedSize(30, 30)
        layout.addWidget(self._zoom_out_btn)
        
        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(50)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._zoom_label)
        
        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedSize(30, 30)
        layout.addWidget(self._zoom_in_btn)
        
        self._fit_btn = QPushButton("适应")
        layout.addWidget(self._fit_btn)
        
        layout.addSpacing(20)
        
        # 背景
        layout.addWidget(QLabel("背景:"))
        self._bg_checker_btn = QPushButton("▦")
        self._bg_checker_btn.setCheckable(True)
        self._bg_checker_btn.setChecked(True)
        self._bg_checker_btn.setToolTip("棋盘格")
        layout.addWidget(self._bg_checker_btn)
        
        self._bg_white_btn = QPushButton("⚪")
        self._bg_white_btn.setCheckable(True)
        self._bg_white_btn.setToolTip("白色")
        layout.addWidget(self._bg_white_btn)
        
        self._bg_black_btn = QPushButton("⚫")
        self._bg_black_btn.setCheckable(True)
        self._bg_black_btn.setToolTip("黑色")
        layout.addWidget(self._bg_black_btn)
        
        layout.addStretch()
        
        # 导出
        self._export_btn = QPushButton("导出单帧")
        layout.addWidget(self._export_btn)
        
        return bar
    
    def _create_bottom_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(45)
        bar.setStyleSheet("""
            QFrame { background-color: #1e1e1e; border-top: 1px solid #3d3d3d; }
            QLabel { color: #888; }
            QPushButton { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 5px 15px; color: #ddd; }
            QPushButton:hover { background-color: #4d4d4d; }
            QPushButton#ok_btn { background-color: #0078d4; border-color: #0078d4; }
            QPushButton#ok_btn:hover { background-color: #1084d8; }
        """)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # 撤销/重做
        self._undo_btn = QPushButton("↩ 撤销")
        self._undo_btn.setEnabled(False)
        layout.addWidget(self._undo_btn)
        
        self._redo_btn = QPushButton("↪ 重做")
        self._redo_btn.setEnabled(False)
        layout.addWidget(self._redo_btn)
        
        layout.addSpacing(20)
        
        # 重置
        self._reset_btn = QPushButton("🔄 重置帧")
        layout.addWidget(self._reset_btn)
        
        layout.addStretch()
        
        # 状态
        self._status_label = QLabel("就绪")
        layout.addWidget(self._status_label)
        
        self._history_label = QLabel("历史: 1/1")
        layout.addWidget(self._history_label)
        
        layout.addSpacing(20)
        
        # 确定/取消
        self._cancel_btn = QPushButton("取消")
        layout.addWidget(self._cancel_btn)
        
        self._ok_btn = QPushButton("确定")
        self._ok_btn.setObjectName("ok_btn")
        layout.addWidget(self._ok_btn)
        
        return bar
    
    def _create_right_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(160)
        panel.setStyleSheet("QFrame { background-color: #252525; border-left: 1px solid #3d3d3d; } QLabel { color: #aaa; }")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        layout.addWidget(QLabel("图像信息:"))
        self._size_label = QLabel()
        layout.addWidget(self._size_label)
        
        layout.addSpacing(10)
        layout.addWidget(QLabel("选区:"))
        self._selection_info = QLabel("无选区")
        layout.addWidget(self._selection_info)
        
        layout.addSpacing(10)
        layout.addWidget(QLabel("颜色:"))
        self._color_info = QLabel("移动鼠标查看")
        layout.addWidget(self._color_info)
        
        layout.addStretch()
        
        return panel
    
    def _setup_connections(self):
        # 工具切换
        self._magic_wand_btn.clicked.connect(lambda: self._set_tool("magic_wand"))
        self._eraser_btn.clicked.connect(lambda: self._set_tool("eraser"))
        self._move_btn.clicked.connect(lambda: self._set_tool("move"))
        
        # 帧导航
        self._prev_btn.clicked.connect(self._prev_frame)
        self._next_btn.clicked.connect(self._next_frame)
        
        # 缩放
        self._zoom_in_btn.clicked.connect(self._zoom_in)
        self._zoom_out_btn.clicked.connect(self._zoom_out)
        self._fit_btn.clicked.connect(self._fit_to_view)
        
        # 背景
        self._bg_checker_btn.clicked.connect(lambda: self._set_background("checkerboard"))
        self._bg_white_btn.clicked.connect(lambda: self._set_background("white"))
        self._bg_black_btn.clicked.connect(lambda: self._set_background("black"))
        
        # 魔棒参数
        self._tolerance_slider.valueChanged.connect(self._on_tolerance_changed)
        self._tolerance_spin.valueChanged.connect(self._on_tolerance_spin_changed)
        self._contiguous_check.stateChanged.connect(lambda s: setattr(self, '_contiguous', s == Qt.Checked))
        self._anti_alias_check.stateChanged.connect(lambda s: setattr(self, '_anti_alias', s == Qt.Checked))
        
        # 橡皮擦参数
        self._eraser_slider.valueChanged.connect(self._on_eraser_size_changed)
        self._eraser_spin.valueChanged.connect(self._on_eraser_spin_changed)
        
        # 编辑操作
        self._delete_btn.clicked.connect(self._delete_selection)
        self._fill_btn.clicked.connect(self._fill_selection)
        self._fill_color_btn.clicked.connect(self._choose_fill_color)
        self._grow_btn.clicked.connect(self._grow_selection)
        self._shrink_btn.clicked.connect(self._shrink_selection)
        self._invert_btn.clicked.connect(self._invert_selection)
        self._deselect_btn.clicked.connect(self._deselect)
        
        # 撤销/重做/重置
        self._undo_btn.clicked.connect(self._undo)
        self._redo_btn.clicked.connect(self._redo)
        self._reset_btn.clicked.connect(self._reset_frame)
        
        # 确定/取消
        self._ok_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        
        # 导出
        self._export_btn.clicked.connect(self._on_export)
        
        # 画布事件
        self._canvas.mousePressEvent = self._on_canvas_mouse_press
        self._canvas.mouseMoveEvent = self._on_canvas_mouse_move
        self._canvas.mouseReleaseEvent = self._on_canvas_mouse_release
        self._canvas.selection_changed.connect(self._update_selection_info)
        self._canvas.image_changed.connect(self._update_image_info)
        self._canvas.zoom_changed.connect(self._on_canvas_zoom_changed)
    
    def _load_frame(self, index: int):
        """加载指定帧"""
        self._current_index = index
        image = self._images[index]
        self._canvas.set_image(image)
        self._update_ui()
        self._update_history_buttons()
        self.setFocus()  # 确保对话框获得焦点
    
    def _update_ui(self):
        """更新UI状态"""
        self.setWindowTitle(f"帧编辑器 - #{self._frame_indices[self._current_index]}")
        self._frame_counter.setText(f"{self._current_index + 1}/{len(self._images)}")
        self._prev_btn.setEnabled(self._current_index > 0)
        self._next_btn.setEnabled(self._current_index < len(self._images) - 1)
        self._zoom_label.setText(f"{int(self._canvas.get_zoom() * 100)}%")
        self._update_image_info()
        self._update_selection_info()
    
    def _set_tool(self, tool: str):
        self._tool_mode = tool
        self._magic_wand_btn.setChecked(tool == "magic_wand")
        self._eraser_btn.setChecked(tool == "eraser")
        self._move_btn.setChecked(tool == "move")
        
        if tool == "magic_wand":
            self._canvas.setCursor(QCursor(Qt.CrossCursor))
        elif tool == "eraser":
            self._canvas.setCursor(self._create_eraser_cursor())
        else:
            self._canvas.setCursor(QCursor(Qt.OpenHandCursor))
    
    def _create_eraser_cursor(self) -> QCursor:
        """创建像素方格橡皮擦光标，大小随缩放变化"""
        size = self._eraser_size
        zoom = self._canvas.get_zoom()
        # 光标大小精确等于擦除区域大小
        actual_size = int(size * zoom)
        # 光标显示大小（最小8像素以便看清，但热点位置基于实际大小）
        display_size = max(8, actual_size)
        
        pixmap = QPixmap(display_size, display_size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)
        
        # 绘制实际擦除区域（居中显示）
        offset = (display_size - actual_size) // 2
        if actual_size > 0:
            cell_size = max(1, actual_size // 4) if actual_size >= 4 else 1
            for i in range(0, actual_size, cell_size):
                for j in range(0, actual_size, cell_size):
                    if (i // cell_size + j // cell_size) % 2 == 0:
                        painter.fillRect(offset + i, offset + j, cell_size, cell_size, QColor(200, 200, 200))
                    else:
                        painter.fillRect(offset + i, offset + j, cell_size, cell_size, QColor(100, 100, 100))
            # 绘制实际擦除区域边框
            painter.setPen(QPen(QColor(255, 0, 0), 1))
            painter.drawRect(offset, offset, actual_size - 1, actual_size - 1)
        else:
            # 太小时绘制十字
            painter.setPen(QPen(QColor(255, 0, 0), 1))
            center = display_size // 2
            painter.drawLine(center - 3, center, center + 3, center)
            painter.drawLine(center, center - 3, center, center + 3)
        
        painter.end()
        
        return QCursor(pixmap, display_size // 2, display_size // 2)
    
    def _prev_frame(self):
        if self._current_index > 0:
            self._load_frame(self._current_index - 1)
        self.setFocus()
    
    def _next_frame(self):
        if self._current_index < len(self._images) - 1:
            self._load_frame(self._current_index + 1)
        self.setFocus()
    
    def _zoom_in(self):
        self._canvas.set_zoom(self._canvas.get_zoom() * 1.25)
        self._zoom_label.setText(f"{int(self._canvas.get_zoom() * 100)}%")
    
    def _zoom_out(self):
        self._canvas.set_zoom(self._canvas.get_zoom() / 1.25)
        self._zoom_label.setText(f"{int(self._canvas.get_zoom() * 100)}%")
    
    def _fit_to_view(self):
        self._canvas._fit_to_view()
        self._zoom_label.setText(f"{int(self._canvas.get_zoom() * 100)}%")
    
    def _on_canvas_zoom_changed(self):
        """画布缩放变化时更新UI"""
        self._zoom_label.setText(f"{int(self._canvas.get_zoom() * 100)}%")
        # 更新橡皮擦光标
        if self._tool_mode == "eraser":
            self._canvas.setCursor(self._create_eraser_cursor())
    
    def _set_background(self, mode: str):
        self._canvas.set_background_mode(mode)
        self._bg_checker_btn.setChecked(mode == "checkerboard")
        self._bg_white_btn.setChecked(mode == "white")
        self._bg_black_btn.setChecked(mode == "black")
    
    def _on_tolerance_changed(self, value: int):
        self._tolerance = value
        self._tolerance_spin.blockSignals(True)
        self._tolerance_spin.setValue(value)
        self._tolerance_spin.blockSignals(False)
    
    def _on_tolerance_spin_changed(self, value: int):
        self._tolerance = value
        self._tolerance_slider.blockSignals(True)
        self._tolerance_slider.setValue(value)
        self._tolerance_slider.blockSignals(False)
    
    def _on_eraser_size_changed(self, value: int):
        self._eraser_size = value
        self._eraser_spin.blockSignals(True)
        self._eraser_spin.setValue(value)
        self._eraser_spin.blockSignals(False)
        if self._tool_mode == "eraser":
            self._canvas.setCursor(self._create_eraser_cursor())
    
    def _on_eraser_spin_changed(self, value: int):
        self._eraser_size = value
        self._eraser_slider.blockSignals(True)
        self._eraser_slider.setValue(value)
        self._eraser_slider.blockSignals(False)
        if self._tool_mode == "eraser":
            self._canvas.setCursor(self._create_eraser_cursor())
    
    def _on_canvas_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            if self._tool_mode == "magic_wand":
                sx, sy = event.pos().x(), event.pos().y()
                img_x, img_y = self._canvas.screen_to_image(sx, sy)
                image = self._images[self._current_index]
                if image is not None:
                    h, w = image.shape[:2]
                    if 0 <= img_x < w and 0 <= img_y < h:
                        self._create_selection(img_x, img_y)
            elif self._tool_mode == "eraser":
                self._is_erasing = True
                self._erase_at_position(event.pos())
        EditorCanvas.mousePressEvent(self._canvas, event)
    
    def _on_canvas_mouse_move(self, event):
        sx, sy = event.pos().x(), event.pos().y()
        img_x, img_y = self._canvas.screen_to_image(sx, sy)
        image = self._images[self._current_index]
        if image is not None:
            h, w = image.shape[:2]
            if 0 <= img_x < w and 0 <= img_y < h:
                color = image[img_y, img_x]
                if len(color) == 4:
                    self._color_info.setText(f"R:{color[0]} G:{color[1]}\nB:{color[2]} A:{color[3]}")
                elif len(color) == 3:
                    self._color_info.setText(f"R:{color[0]} G:{color[1]}\nB:{color[2]}")
            else:
                self._color_info.setText("超出范围")
        
        if self._is_erasing and self._tool_mode == "eraser":
            self._erase_at_position(event.pos())
        EditorCanvas.mouseMoveEvent(self._canvas, event)
    
    def _on_canvas_mouse_release(self, event):
        if event.button() == Qt.LeftButton and self._is_erasing:
            self._is_erasing = False
            self._save_state()
            self._status_label.setText("擦除完成")
        
        # 调用原始处理
        EditorCanvas.mouseReleaseEvent(self._canvas, event)
        
        # 恢复工具光标（中键/右键释放后）
        if event.button() == Qt.MiddleButton or event.button() == Qt.RightButton:
            if self._tool_mode == "eraser":
                self._canvas.setCursor(self._create_eraser_cursor())
            elif self._tool_mode == "magic_wand":
                self._canvas.setCursor(QCursor(Qt.CrossCursor))
            elif self._tool_mode == "move":
                self._canvas.setCursor(QCursor(Qt.OpenHandCursor))
    
    def _create_selection(self, x: int, y: int):
        try:
            selection = self._magic_wand.select(
                self._images[self._current_index], x, y,
                self._tolerance, self._contiguous, self._anti_alias
            )
            mode = self._selection_mode_combo.currentData()
            current = self._canvas.get_selection()
            
            if mode == "new":
                self._canvas.set_selection(selection.mask)
            elif mode == "add" and current is not None:
                new_mask = np.clip(current + selection.mask, 0, 1)
                self._canvas.set_selection(clean_small_regions(new_mask, min_area=20))
            elif mode == "subtract" and current is not None:
                new_mask = np.clip(current - selection.mask, 0, 1)
                self._canvas.set_selection(clean_small_regions(new_mask, min_area=20))
            elif mode == "intersect" and current is not None:
                new_mask = np.minimum(current, selection.mask)
                self._canvas.set_selection(clean_small_regions(new_mask, min_area=20))
            else:
                self._canvas.set_selection(selection.mask)
            
            self._status_label.setText(f"选区: {selection.area} 像素")
        except Exception as e:
            self._status_label.setText(f"错误: {str(e)}")
    
    def _erase_at_position(self, pos):
        image = self._images[self._current_index]
        if image is None:
            return
        sx, sy = pos.x(), pos.y()
        zoom = self._canvas.get_zoom()
        offset_x = self._canvas._offset_x
        offset_y = self._canvas._offset_y
        if zoom == 0:
            return
        img_x = int((sx - offset_x) / zoom)
        img_y = int((sy - offset_y) / zoom)
        h, w = image.shape[:2]
        
        if len(image.shape) == 3 and image.shape[2] == 3:
            image = np.concatenate([image, np.full((h, w, 1), 255, dtype=np.uint8)], axis=2)
            self._images[self._current_index] = image
        
        half_size = self._eraser_size // 2
        x1, y1 = img_x - half_size, img_y - half_size
        x2, y2 = x1 + self._eraser_size, y1 + self._eraser_size
        x1_clip, y1_clip = max(0, x1), max(0, y1)
        x2_clip, y2_clip = min(w, x2), min(h, y2)
        
        if x1_clip < x2_clip and y1_clip < y2_clip:
            image[y1_clip:y2_clip, x1_clip:x2_clip, 3] = 0
            self._canvas.set_image(image, reset_view=False)
    
    def _delete_selection(self):
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        mask = self._canvas.get_selection()
        image = self._images[self._current_index].copy()
        binary_mask = (mask > 0.5).astype(np.float32)
        
        if len(image.shape) == 3 and image.shape[2] == 4:
            alpha = image[:, :, 3].astype(np.float32)
            image[:, :, 3] = np.where(binary_mask > 0, 0, alpha).astype(np.uint8)
        elif len(image.shape) == 3 and image.shape[2] == 3:
            alpha = np.full(image.shape[:2], 255, dtype=np.float32)
            alpha = np.where(binary_mask > 0, 0, alpha)
            image = np.dstack([image, alpha.astype(np.uint8)])
        
        self._apply_edit(image, "删除选区")
    
    def _fill_selection(self):
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        mask = self._canvas.get_selection()
        image = self._images[self._current_index].copy()
        
        if len(image.shape) == 2:
            image = np.stack([image]*3 + [np.full_like(image, 255)], axis=2)
        elif image.shape[2] == 3:
            image = np.concatenate([image, np.full((*image.shape[:2], 1), 255, dtype=np.uint8)], axis=2)
        
        for c in range(4):
            image[:, :, c] = (image[:, :, c] * (1 - mask) + np.full_like(image[:, :, c], self._fill_color[c]) * mask).astype(np.uint8)
        
        self._apply_edit(image, "填充选区")
    
    def _choose_fill_color(self):
        color = QColorDialog.getColor(QColor(*self._fill_color[:3]), self, "选择填充颜色")
        if color.isValid():
            self._fill_color = (color.red(), color.green(), color.blue(), 255)
            self._update_fill_color_btn()
    
    def _update_fill_color_btn(self):
        r, g, b, a = self._fill_color
        self._fill_color_btn.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border: 1px solid #4d4d4d; border-radius: 3px;")
    
    def _grow_selection(self):
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        mask = self._canvas.get_selection()
        self._canvas.set_selection(grow_selection(mask, pixels=1))
        self._status_label.setText("已扩大选区")
    
    def _shrink_selection(self):
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        mask = self._canvas.get_selection()
        self._canvas.set_selection(shrink_selection(mask, pixels=1))
        self._status_label.setText("已缩小选区")
    
    def _invert_selection(self):
        if self._canvas.has_selection():
            self._canvas.set_selection(1.0 - self._canvas.get_selection())
            self._status_label.setText("已反选")
        else:
            image = self._images[self._current_index]
            self._canvas.set_selection(np.ones(image.shape[:2], dtype=np.float32))
            self._status_label.setText("已全选")
    
    def _deselect(self):
        self._canvas.set_selection(None)
        self._status_label.setText("已取消选区")
    
    def _apply_edit(self, new_image: np.ndarray, action: str):
        self._images[self._current_index] = new_image
        self._canvas.set_selection(None)
        self._canvas.set_image(new_image, reset_view=False)
        self._save_state()
        self._status_label.setText(f"已执行: {action}")
    
    def _save_state(self):
        state = EditorState(
            image=self._images[self._current_index].copy(),
            selection_mask=self._canvas.get_selection()
        )
        self._histories[self._current_index].push(state)
        self._update_history_buttons()
    
    def _undo(self):
        state = self._histories[self._current_index].undo()
        if state is not None:
            self._images[self._current_index] = state.image.copy()
            self._canvas.set_image(state.image, reset_view=False)
            self._canvas.set_selection(state.selection_mask)
            self._update_history_buttons()
            self._status_label.setText("已撤销")
    
    def _redo(self):
        state = self._histories[self._current_index].redo()
        if state is not None:
            self._images[self._current_index] = state.image.copy()
            self._canvas.set_image(state.image, reset_view=False)
            self._canvas.set_selection(state.selection_mask)
            self._update_history_buttons()
            self._status_label.setText("已重做")
    
    def _update_history_buttons(self):
        history = self._histories[self._current_index]
        self._undo_btn.setEnabled(history.can_undo())
        self._redo_btn.setEnabled(history.can_redo())
        total = len(history._states)
        current = history._current_index + 1 if total > 0 else 0
        self._history_label.setText(f"历史: {current}/{total}")
    
    def _reset_frame(self):
        reply = QMessageBox.question(self, "确认重置", "确定要重置当前帧为原始图像吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._images[self._current_index] = self._original_images[self._current_index].copy()
            self._canvas.set_image(self._images[self._current_index])
            self._canvas.set_selection(None)
            self._histories[self._current_index].clear()
            self._save_state()
            self._status_label.setText("已重置")
    
    def _update_image_info(self):
        image = self._images[self._current_index]
        if image is not None:
            h, w = image.shape[:2]
            channels = image.shape[2] if len(image.shape) == 3 else 1
            self._size_label.setText(f"尺寸: {w}x{h}\n通道: {channels}")
    
    def _update_selection_info(self):
        mask = self._canvas.get_selection()
        if mask is not None and np.any(mask > 0):
            area = int(np.count_nonzero(mask > 0))
            h, w = mask.shape
            percent = area / (h * w) * 100
            self._selection_info.setText(f"面积: {area}\n占比: {percent:.1f}%")
        else:
            self._selection_info.setText("无选区")
    
    def _on_export(self):
        self.export_requested.emit(self._frame_indices[self._current_index])
        self.accept()
    
    def keyPressEvent(self, event):
        mods = event.modifiers()
        if mods & Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                self._undo()
                return
            elif event.key() == Qt.Key_Y:
                self._redo()
                return
            elif event.key() == Qt.Key_D:
                self._deselect()
                return
            elif event.key() == Qt.Key_I:
                self._invert_selection()
                return
        
        if event.key() == Qt.Key_Delete:
            self._delete_selection()
            return
        elif event.key() == Qt.Key_Escape:
            self._deselect()
            return
        
        super().keyPressEvent(event)
    
    def accept(self):
        for i, img in enumerate(self._images):
            if not np.array_equal(img, self._original_images[i]):
                self.image_edited.emit(self._frame_indices[i], img)
        self._result_saved = True
        super().accept()
    
    def reject(self):
        has_changes = any(not np.array_equal(self._images[i], self._original_images[i]) for i in range(len(self._images)))
        if has_changes:
            reply = QMessageBox.question(self, "保存编辑", "是否保存编辑结果？", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                self.accept()
                return
        super().reject()


class FrameZoomDialog(QDialog):
    """帧放大预览对话框 - 支持左右切换和缩放"""
    
    export_requested = Signal(int)  # frame_index
    image_edited = Signal(int, np.ndarray)  # frame_index, edited_image
    
    def __init__(self, images: List[np.ndarray], frame_indices: List[int], current_index: int = 0, parent=None):
        super().__init__(parent)
        self.images = list(images)
        self.frame_indices = list(frame_indices)
        self.current_index = current_index
        self.zoom_factor = 1.0  # 缩放因子
        self.max_zoom = 32.0     # 最大缩放
        self.min_zoom = 0.1     # 最小缩放
        self.bg_mode = "checkerboard"
        
        self.setWindowTitle(f"帧 #{self.frame_indices[self.current_index]} - 放大预览")
        self.setMinimumSize(800, 600)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 顶部工具栏
        toolbar = QHBoxLayout()
        
        # 左切换按钮
        self.prev_btn = QPushButton("◀ 上一帧")
        self.prev_btn.clicked.connect(self._prev_frame)
        self.prev_btn.setEnabled(self.current_index > 0)
        toolbar.addWidget(self.prev_btn)
        
        # 帧计数
        self.frame_counter = QLabel(f"{self.current_index + 1}/{len(self.images)}")
        self.frame_counter.setStyleSheet("color: #fff; font-weight: bold;")
        self.frame_counter.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self.frame_counter)
        
        # 右切换按钮
        self.next_btn = QPushButton("下一帧 ▶")
        self.next_btn.clicked.connect(self._next_frame)
        self.next_btn.setEnabled(self.current_index < len(self.images) - 1)
        toolbar.addWidget(self.next_btn)
        
        toolbar.addStretch()
        
        # 缩放控件
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("缩放:"))
        
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setFixedSize(30, 30)
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        zoom_layout.addWidget(self.zoom_out_btn)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        zoom_layout.addWidget(self.zoom_label)
        
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedSize(30, 30)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        zoom_layout.addWidget(self.zoom_in_btn)
        
        self.reset_zoom_btn = QPushButton("重置")
        self.reset_zoom_btn.clicked.connect(self._reset_zoom)
        zoom_layout.addWidget(self.reset_zoom_btn)
        
        # 背景切换
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(QLabel("背景:"))
        
        self.bg_checker_btn = QPushButton("▦ 棋盘")
        self.bg_checker_btn.setCheckable(True)
        self.bg_checker_btn.setChecked(True)
        self.bg_checker_btn.clicked.connect(lambda: self._set_background("checkerboard"))
        bg_layout.addWidget(self.bg_checker_btn)
        
        self.bg_gray_btn = QPushButton("⚪ 灰色")
        self.bg_gray_btn.setCheckable(True)
        self.bg_gray_btn.clicked.connect(lambda: self._set_background("gray"))
        bg_layout.addWidget(self.bg_gray_btn)
        
        self.bg_white_btn = QPushButton("⚪ 白色")
        self.bg_white_btn.setCheckable(True)
        self.bg_white_btn.clicked.connect(lambda: self._set_background("white"))
        bg_layout.addWidget(self.bg_white_btn)
        
        self.bg_black_btn = QPushButton("⚫ 黑色")
        self.bg_black_btn.setCheckable(True)
        self.bg_black_btn.clicked.connect(lambda: self._set_background("black"))
        bg_layout.addWidget(self.bg_black_btn)
        
        toolbar.addLayout(bg_layout)
        
        toolbar.addLayout(zoom_layout)
        layout.addLayout(toolbar)
        
        # 图像显示区域 - 使用自定义画布支持滚轮缩放和中键拖动
        self.image_canvas = FrameImageCanvas()
        layout.addWidget(self.image_canvas, 1)
        
        # 底部信息和按钮
        bottom_layout = QHBoxLayout()
        
        # 信息
        h, w = self.images[self.current_index].shape[:2]
        channels = self.images[self.current_index].shape[2] if len(self.images[self.current_index].shape) == 3 else 1
        info = f"尺寸: {w}x{h} | 通道: {channels}"
        if channels == 4:
            alpha = self.images[self.current_index][:, :, 3]
            transparent = np.sum(alpha < 128) / alpha.size * 100
            info += f" | 透明: {transparent:.1f}%"
        
        info_label = QLabel(info)
        info_label.setStyleSheet("color: #888;")
        bottom_layout.addWidget(info_label)
        
        bottom_layout.addStretch()
        
        self.edit_btn = QPushButton("🪄 魔棒编辑")
        self.edit_btn.setToolTip("使用魔棒工具手动编辑此帧")
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        bottom_layout.addWidget(self.edit_btn)
        
        export_btn = QPushButton("导出单帧")
        export_btn.clicked.connect(self._on_export_clicked)
        bottom_layout.addWidget(export_btn)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)
        
        layout.addLayout(bottom_layout)
        
        self._display_image()
    
    def _display_image(self):
        """显示当前帧图像"""
        current_image = self.images[self.current_index]
        
        # 根据背景模式处理透明通道
        display_image = current_image
        if len(current_image.shape) == 3 and current_image.shape[2] == 4:
            if self.bg_mode == "checkerboard":
                display_image = composite_on_checkerboard(current_image, square_size=15)
            elif self.bg_mode == "gray":
                from PIL import Image
                pil_img = Image.fromarray(current_image)
                background = Image.new('RGBA', pil_img.size, (128, 128, 128, 255))
                pil_img = Image.alpha_composite(background, pil_img)
                display_image = np.array(pil_img)
            else:
                from PIL import Image
                pil_img = Image.fromarray(current_image)
                if self.bg_mode == "white":
                    background = Image.new('RGBA', pil_img.size, (255, 255, 255, 255))
                else:
                    background = Image.new('RGBA', pil_img.size, (0, 0, 0, 255))
                pil_img = Image.alpha_composite(background, pil_img)
                display_image = np.array(pil_img)
        
        pixmap = numpy_to_qpixmap(display_image)
        
        # 使用自定义画布显示图像
        self.image_canvas.set_pixmap(pixmap, reset_view=False)
        # 同步缩放级别
        self.image_canvas.set_zoom(self.zoom_factor)
        
        # 更新窗口标题和控件状态
        self.setWindowTitle(f"帧 #{self.frame_indices[self.current_index]} - 放大预览")
        self.frame_counter.setText(f"{self.current_index + 1}/{len(self.images)}")
        self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
        
        # 更新导航按钮状态
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.images) - 1)
        
        # 更新缩放按钮状态
        self.zoom_out_btn.setEnabled(self.zoom_factor > self.min_zoom)
        self.zoom_in_btn.setEnabled(self.zoom_factor < self.max_zoom)
        
        # 更新信息显示
        self._update_info()
    
    def _prev_frame(self):
        """切换到上一帧"""
        if self.current_index > 0:
            self.current_index -= 1
            self._display_image()
    
    def _next_frame(self):
        """切换到下一帧"""
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            self._display_image()
    
    def _zoom_in(self):
        """放大"""
        if self.zoom_factor < self.max_zoom:
            self.zoom_factor = min(self.zoom_factor * 1.25, self.max_zoom)
            self.image_canvas.set_zoom(self.zoom_factor)
            self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
            self.zoom_out_btn.setEnabled(self.zoom_factor > self.min_zoom)
            self.zoom_in_btn.setEnabled(self.zoom_factor < self.max_zoom)
    
    def _zoom_out(self):
        """缩小"""
        if self.zoom_factor > self.min_zoom:
            self.zoom_factor = max(self.zoom_factor / 1.25, self.min_zoom)
            self.image_canvas.set_zoom(self.zoom_factor)
            self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
            self.zoom_out_btn.setEnabled(self.zoom_factor > self.min_zoom)
            self.zoom_in_btn.setEnabled(self.zoom_factor < self.max_zoom)
    
    def _reset_zoom(self):
        """重置缩放"""
        self.zoom_factor = 1.0
        self.image_canvas.set_zoom(self.zoom_factor)
        self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
        self.zoom_out_btn.setEnabled(self.zoom_factor > self.min_zoom)
        self.zoom_in_btn.setEnabled(self.zoom_factor < self.max_zoom)
    
    def _set_background(self, mode: str):
        """设置背景模式"""
        self.bg_mode = mode
        
        # 更新按钮选中状态
        self.bg_checker_btn.setChecked(mode == "checkerboard")
        self.bg_gray_btn.setChecked(mode == "gray")
        self.bg_white_btn.setChecked(mode == "white")
        self.bg_black_btn.setChecked(mode == "black")
        
        # 更新背景显示
        self._display_image()
    
    def _update_info(self):
        """更新底部信息显示"""
        current_image = self.images[self.current_index]
        h, w = current_image.shape[:2]
        channels = current_image.shape[2] if len(current_image.shape) == 3 else 1
        info = f"尺寸: {w}x{h} | 通道: {channels}"
        if channels == 4:
            alpha = current_image[:, :, 3]
            transparent = np.sum(alpha < 128) / alpha.size * 100
            info += f" | 透明: {transparent:.1f}%"
        
        # 找到对应的info_label并更新文本
        for child in self.findChildren(QLabel):
            if "尺寸:" in child.text():
                child.setText(info)
                break
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._display_image()
    
    def _on_export_clicked(self):
        """导出按钮点击事件"""
        self.export_requested.emit(self.frame_indices[self.current_index])
        self.accept()
    
    def _on_edit_clicked(self):
        """魔棒编辑按钮点击事件"""
        from src.ui.widgets.magic_wand_editor import MagicWandEditor
        
        current_image = self.images[self.current_index]
        editor = MagicWandEditor(current_image, self)
        
        def on_image_edited(edited_image: np.ndarray):
            self.images[self.current_index] = edited_image
            self._display_image()
            self.image_edited.emit(self.frame_indices[self.current_index], edited_image)
        
        editor.image_edited.connect(on_image_edited)
        editor.exec()
    
    def update_image(self, index: int, image: np.ndarray):
        """更新指定索引的图像"""
        if 0 <= index < len(self.images):
            self.images[index] = image
            if index == self.current_index:
                self._display_image()


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
        self._display_pixmap: Optional[QPixmap] = None  # 缓存显示用的 pixmap
        
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
        """更新 pixmap，缓存合成结果"""
        if self._image is None:
            self._display_pixmap = None
            self.image_label.setPixmap(QPixmap())
            return
        
        # 如果有透明通道，先合成到棋盘格背景
        display_image = self._image
        if len(self._image.shape) == 3 and self._image.shape[2] == 4:
            display_image = composite_on_checkerboard(self._image)
        
        # 转换为 pixmap 并使用高质量缩放
        pixmap = numpy_to_qpixmap(display_image)
        self._display_pixmap = pixmap.scaled(
            self.thumbnail_size, self.thumbnail_size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(self._display_pixmap)
    
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
    image_edited = Signal(int, np.ndarray)  # frame_index, edited_image
    
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
        self.interval_spin.setRange(1, config.FRAME_INTERVAL_MAX)
        self.interval_spin.setValue(config.FRAME_INTERVAL_DEFAULT)
        self.interval_spin.setFixedWidth(60)
        self.interval_spin.setMinimumHeight(28)
        self.interval_spin.setStyleSheet("""
            QSpinBox {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
                border-radius: 4px;
                padding: 2px 4px;
                padding-right: 20px;
                color: #eee;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 18px;
                height: 12px;
            }
        """)
        toolbar.addWidget(self.interval_spin)
        
        self.interval_select_btn = QPushButton("⏹ 间隔选帧")
        self.interval_select_btn.setStyleSheet(btn_style)
        self.interval_select_btn.setToolTip("在当前选中范围内按间隔抽帧：间隔N=每隔N帧取1帧，首尾帧强制保留")
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
    
    def select_indices(self, indices: List[int]):
        """选中指定索引的帧"""
        indices_set = set(indices)
        for thumb in self._thumbnails:
            thumb.set_selected(thumb.frame_index in indices_set)
        self._update_selection_info()
        self.selection_changed.emit(self.get_selected_indices())
    
    def get_selected_indices(self) -> List[int]:
        """获取选中的帧索引"""
        return [thumb.frame_index for thumb in self._thumbnails if thumb._is_selected]
    
    def _on_interval_select_clicked(self):
        """间隔选帧：在首尾选中帧范围内，每隔 N 帧取 1 帧，首尾帧强制保留"""
        selected_indices = self.get_selected_indices()
        if not selected_indices:
            return

        interval = self.interval_spin.value()  # 间隔N = 跳过N帧，步长 = N+1
        step = interval + 1
        first_idx = selected_indices[0]
        last_idx = selected_indices[-1]

        # 收集范围内所有帧的 frame_index（按顺序）
        range_thumbs = sorted(
            [t for t in self._thumbnails if first_idx <= t.frame_index <= last_idx],
            key=lambda t: t.frame_index
        )
        if not range_thumbs:
            return

        # 按步长取帧索引，强制加入首尾
        all_range_indices = [t.frame_index for t in range_thumbs]
        new_selection = set(all_range_indices[i] for i in range(0, len(all_range_indices), step))
        new_selection.add(all_range_indices[0])   # 强制保留首帧
        new_selection.add(all_range_indices[-1])  # 强制保留尾帧

        # 批量更新 UI：范围内按新集合选中/取消，范围外不变
        self.begin_batch_update()
        for thumb in range_thumbs:
            thumb.set_selected(thumb.frame_index in new_selection)
        self.end_batch_update()

        msg = f"间隔选帧完成：范围 {len(all_range_indices)} 帧 → 保留 {len(new_selection)} 帧（间隔{interval}帧）"
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
        """双击帧放大预览 - 支持多帧浏览"""
        # 获取所有选中的帧（如果没有选中则使用当前帧）
        selected_indices = self.get_selected_indices()
        if not selected_indices:
            selected_indices = [frame_index]
        
        # 按索引排序
        selected_indices.sort()
        
        # 获取对应的所有图像
        images = []
        frame_indices = []
        current_pos = 0
        
        for i, idx in enumerate(selected_indices):
            for thumb in self._thumbnails:
                if thumb.frame_index == idx:
                    image = thumb.get_image()
                    if image is not None:
                        images.append(image)
                        frame_indices.append(idx)
                        if idx == frame_index:
                            current_pos = len(images) - 1
                    break
        
        if images:
            dialog = FrameEditorDialog(images, frame_indices, current_pos, parent=self)
            dialog.export_requested.connect(self.export_single_frame)
            dialog.image_edited.connect(self._on_image_edited)
            dialog.exec()
    
    def _on_image_edited(self, frame_index: int, edited_image: np.ndarray):
        """处理图像编辑完成事件"""
        self.update_frame(frame_index, edited_image)
        self.image_edited.emit(frame_index, edited_image)
    
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
