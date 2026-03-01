"""魔棒工具编辑器 - 手动编辑图片选区（性能优化版）"""
from typing import Optional, List, Tuple
from dataclasses import dataclass
import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QSlider, QSpinBox, QCheckBox, QComboBox,
    QScrollArea, QFrame, QGroupBox, QMessageBox, QColorDialog,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QPoint, QTimer, QPointF
from PySide6.QtGui import (
    QPainter, QPixmap, QPen, QColor, QCursor, QImage, QPainterPath
)

from src.core.magic_wand import MagicWand, clean_small_regions, grow_selection, shrink_selection
from src.utils.image_utils import numpy_to_qpixmap


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


def create_checkerboard_fast(width: int, height: int, square_size: int = 10) -> np.ndarray:
    """快速创建棋盘格背景 - NumPy向量化"""
    board = np.zeros((height, width, 3), dtype=np.uint8)
    
    y_coords, x_coords = np.ogrid[:height, :width]
    grid_x = x_coords // square_size
    grid_y = y_coords // square_size
    use_color1 = ((grid_x + grid_y) % 2 == 0)
    
    board[use_color1] = [200, 200, 200]
    board[~use_color1] = [255, 255, 255]
    
    return board


class ImageCanvas(QWidget):
    """图像画布 - 性能优化版"""
    
    selection_changed = Signal()
    image_changed = Signal()
    background_changed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._image: Optional[np.ndarray] = None
        self._display_pixmap: Optional[QPixmap] = None
        self._selection_mask: Optional[np.ndarray] = None
        
        self._bg_mode = "checkerboard"
        
        self._zoom = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 32.0
        
        self._panning = False
        self._last_pan_pos = QPoint()
        self._offset_x = 0
        self._offset_y = 0
        
        self._checkerboard_cache: Optional[np.ndarray] = None
        
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
        self.background_changed.emit(mode)
    
    def get_background_mode(self) -> str:
        return self._bg_mode
    
    def _update_display_pixmap(self):
        if self._image is None:
            self._display_pixmap = None
            return
        
        display = self._image
        if len(display.shape) == 3 and display.shape[2] == 4:
            display = self._composite_background(display)
        
        self._display_pixmap = numpy_to_qpixmap(display)
    
    def _composite_background(self, image: np.ndarray) -> np.ndarray:
        """根据背景模式合成背景"""
        h, w = image.shape[:2]
        alpha = image[:, :, 3:4] / 255.0
        rgb = image[:, :, :3]
        
        if self._bg_mode == "checkerboard":
            if self._checkerboard_cache is None or self._checkerboard_cache.shape[:2] != (h, w):
                self._checkerboard_cache = create_checkerboard_fast(w, h)
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
            
            # 用绿色半透明填充显示选区
            if self._selection_mask is not None and np.any(self._selection_mask > 0):
                self._draw_selection_overlay(painter)
        
        if self._display_pixmap is not None:
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawRect(
                int(self._offset_x) - 1,
                int(self._offset_y) - 1,
                int(self._display_pixmap.width() * self._zoom) + 1,
                int(self._display_pixmap.height() * self._zoom) + 1
            )
    
    def _draw_selection_overlay(self, painter: QPainter):
        """绘制选区覆盖层 - 绿色半透明填充"""
        if self._selection_mask is None:
            return
        
        h, w = self._selection_mask.shape
        zoom = self._zoom
        offset_x = self._offset_x
        offset_y = self._offset_y
        
        # 使用 numpy 批量创建 overlay 图像
        binary_mask = (self._selection_mask > 0.5)
        
        # 创建 RGBA 数组
        overlay_rgba = np.zeros((h, w, 4), dtype=np.uint8)
        overlay_rgba[binary_mask] = [0, 255, 0, 80]  # 绿色半透明
        
        # 转换为 QImage
        overlay = QImage(overlay_rgba.data, w, h, w * 4, QImage.Format_ARGB32)
        
        # 缩放并绘制
        scaled_overlay = overlay.scaled(
            int(w * zoom), int(h * zoom),
            Qt.IgnoreAspectRatio, Qt.FastTransformation
        )
        painter.drawImage(int(offset_x), int(offset_y), scaled_overlay)
        
        # 绘制绿色边框
        painter.setPen(QPen(QColor(0, 255, 0), 2))
        
        # 找到选区边界矩形
        rows = np.any(binary_mask, axis=1)
        cols = np.any(binary_mask, axis=0)
        if np.any(rows) and np.any(cols):
            y_min, y_max = np.where(rows)[0][[0, -1]]
            x_min, x_max = np.where(cols)[0][[0, -1]]
            
            painter.drawRect(
                int(x_min * zoom + offset_x),
                int(y_min * zoom + offset_y),
                int((x_max - x_min + 1) * zoom),
                int((y_max - y_min + 1) * zoom)
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
    
    def get_zoom(self) -> float:
        return self._zoom
    
    def set_zoom(self, zoom: float):
        if self._display_pixmap is None:
            return
        
        self._zoom = max(self._min_zoom, min(self._max_zoom, zoom))
        
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        img_x, img_y = self.screen_to_image(int(center_x), int(center_y))
        
        self._offset_x = center_x - img_x * self._zoom
        self._offset_y = center_y - img_y * self._zoom
        
        self.update()


class MagicWandEditor(QDialog):
    """魔棒工具编辑器对话框"""
    
    image_edited = Signal(np.ndarray)
    
    def __init__(self, image: np.ndarray, parent=None):
        super().__init__(parent)
        
        self._original_image = image.copy()
        self._current_image = image.copy()
        
        self._magic_wand = MagicWand()
        self._history = EditorHistory()
        
        self._tool_mode = "magic_wand"
        self._tolerance = 32
        self._contiguous = True
        self._anti_alias = True
        
        self._eraser_size = 10
        self._is_erasing = False
        
        self._fill_color = (255, 255, 255, 255)
        self._result_saved = False
        
        self.setWindowTitle("魔棒工具编辑器")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        
        self._setup_ui()
        self._setup_connections()
        
        self._save_state()
        
        self._canvas.set_image(self._current_image)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        
        left_panel = self._create_left_panel()
        content.addWidget(left_panel)
        
        self._canvas = ImageCanvas()
        self._canvas.setMinimumWidth(600)
        content.addWidget(self._canvas, 1)
        
        right_panel = self._create_right_panel()
        content.addWidget(right_panel)
        
        layout.addLayout(content, 1)
        
        statusbar = self._create_statusbar()
        layout.addWidget(statusbar)
    
    def _create_toolbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setFrameStyle(QFrame.StyledPanel)
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet("""
            QFrame { background-color: #2d2d2d; border-bottom: 1px solid #3d3d3d; }
            QPushButton {
                background-color: #3d3d3d; border: 1px solid #4d4d4d;
                border-radius: 4px; padding: 5px 10px; color: #ddd; min-width: 60px;
            }
            QPushButton:hover { background-color: #4d4d4d; border-color: #0078d4; }
            QPushButton:pressed { background-color: #0078d4; }
            QPushButton:disabled { background-color: #2d2d2d; color: #666; }
            QPushButton:checked { background-color: #0078d4; border-color: #0078d4; }
        """)
        
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self._undo_btn = QPushButton("↩ 撤销")
        self._undo_btn.setToolTip("撤销上一步操作 (Ctrl+Z)")
        self._undo_btn.setEnabled(False)
        layout.addWidget(self._undo_btn)
        
        self._redo_btn = QPushButton("↪ 重做")
        self._redo_btn.setToolTip("重做操作 (Ctrl+Y)")
        self._redo_btn.setEnabled(False)
        layout.addWidget(self._redo_btn)
        
        layout.addSpacing(20)
        
        sep1 = QFrame()
        sep1.setFrameStyle(QFrame.VLine)
        sep1.setStyleSheet("color: #4d4d4d;")
        layout.addWidget(sep1)
        
        layout.addSpacing(10)
        
        self._magic_wand_btn = QPushButton("🪄 魔棒")
        self._magic_wand_btn.setCheckable(True)
        self._magic_wand_btn.setChecked(True)
        self._magic_wand_btn.setToolTip("魔棒选区工具")
        layout.addWidget(self._magic_wand_btn)
        
        self._eraser_btn = QPushButton("🧹 橡皮擦")
        self._eraser_btn.setCheckable(True)
        self._eraser_btn.setToolTip("橡皮擦工具 - 擦除像素")
        layout.addWidget(self._eraser_btn)
        
        self._move_btn = QPushButton("✋ 移动")
        self._move_btn.setCheckable(True)
        self._move_btn.setToolTip("移动视图 (或按住中键/右键拖动)")
        layout.addWidget(self._move_btn)
        
        layout.addSpacing(20)
        
        sep2 = QFrame()
        sep2.setFrameStyle(QFrame.VLine)
        sep2.setStyleSheet("color: #4d4d4d;")
        layout.addWidget(sep2)
        
        layout.addSpacing(10)
        
        self._zoom_in_btn = QPushButton("🔍+")
        self._zoom_in_btn.setToolTip("放大视图")
        layout.addWidget(self._zoom_in_btn)
        
        self._zoom_out_btn = QPushButton("🔍-")
        self._zoom_out_btn.setToolTip("缩小视图")
        layout.addWidget(self._zoom_out_btn)
        
        self._fit_btn = QPushButton("⬜ 适应")
        self._fit_btn.setToolTip("适应窗口大小")
        layout.addWidget(self._fit_btn)
        
        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet("color: #aaa; min-width: 50px;")
        layout.addWidget(self._zoom_label)
        
        sep3 = QFrame()
        sep3.setFrameStyle(QFrame.VLine)
        sep3.setStyleSheet("color: #4d4d4d;")
        layout.addWidget(sep3)
        
        self._bg_checker_btn = QPushButton("▦ 棋盘")
        self._bg_checker_btn.setCheckable(True)
        self._bg_checker_btn.setChecked(True)
        self._bg_checker_btn.setToolTip("棋盘格背景")
        layout.addWidget(self._bg_checker_btn)
        
        self._bg_white_btn = QPushButton("⚪ 白")
        self._bg_white_btn.setCheckable(True)
        self._bg_white_btn.setToolTip("白色背景")
        layout.addWidget(self._bg_white_btn)
        
        self._bg_black_btn = QPushButton("⚫ 黑")
        self._bg_black_btn.setCheckable(True)
        self._bg_black_btn.setToolTip("黑色背景")
        layout.addWidget(self._bg_black_btn)
        
        layout.addStretch()
        
        self._reset_btn = QPushButton("🔄 重置")
        self._reset_btn.setToolTip("重置为原始图像")
        layout.addWidget(self._reset_btn)
        
        return toolbar
    
    def _create_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        panel.setFixedWidth(200)
        panel.setStyleSheet("""
            QFrame { background-color: #252525; border-right: 1px solid #3d3d3d; }
            QGroupBox { color: #ddd; border: 1px solid #3d3d3d; border-radius: 4px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #aaa; }
            QSlider::groove:horizontal { height: 6px; background: #3d3d3d; border-radius: 3px; }
            QSlider::handle:horizontal { background: #0078d4; width: 14px; margin: -4px 0; border-radius: 7px; }
            QSpinBox { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 2px; color: #ddd; }
            QCheckBox { color: #ddd; }
            QComboBox { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 2px; color: #ddd; }
            QPushButton { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 5px 10px; color: #ddd; }
            QPushButton:hover { background-color: #4d4d4d; border-color: #0078d4; }
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        tool_group = QGroupBox("选区工具")
        tool_layout = QVBoxLayout(tool_group)
        
        mode_label = QLabel("选区模式:")
        tool_layout.addWidget(mode_label)
        
        self._selection_mode_combo = QComboBox()
        self._selection_mode_combo.addItem("新建选区", "new")
        self._selection_mode_combo.addItem("添加到选区", "add")
        self._selection_mode_combo.addItem("从选区减去", "subtract")
        self._selection_mode_combo.addItem("选区交集", "intersect")
        tool_layout.addWidget(self._selection_mode_combo)
        
        layout.addWidget(tool_group)
        
        params_group = QGroupBox("魔棒参数")
        params_layout = QVBoxLayout(params_group)
        
        tol_label = QLabel("颜色容差:")
        params_layout.addWidget(tol_label)
        
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
        params_layout.addLayout(tol_row)
        
        self._contiguous_check = QCheckBox("连续选区")
        self._contiguous_check.setChecked(self._contiguous)
        params_layout.addWidget(self._contiguous_check)
        
        self._anti_alias_check = QCheckBox("抗锯齿")
        self._anti_alias_check.setChecked(self._anti_alias)
        params_layout.addWidget(self._anti_alias_check)
        
        layout.addWidget(params_group)
        
        # 橡皮擦参数
        eraser_group = QGroupBox("橡皮擦参数")
        eraser_layout = QVBoxLayout(eraser_group)
        
        eraser_label = QLabel("橡皮大小:")
        eraser_layout.addWidget(eraser_label)
        
        eraser_row = QHBoxLayout()
        self._eraser_slider = QSlider(Qt.Horizontal)
        self._eraser_slider.setRange(1, 50)
        self._eraser_slider.setValue(self._eraser_size)
        eraser_row.addWidget(self._eraser_slider)
        
        self._eraser_spin = QSpinBox()
        self._eraser_spin.setRange(1, 50)
        self._eraser_spin.setValue(self._eraser_size)
        self._eraser_spin.setFixedWidth(60)
        self._eraser_spin.setSuffix("px")
        eraser_row.addWidget(self._eraser_spin)
        eraser_layout.addLayout(eraser_row)
        
        layout.addWidget(eraser_group)
        
        edit_group = QGroupBox("编辑操作")
        edit_layout = QVBoxLayout(edit_group)
        
        self._delete_btn = QPushButton("删除选区")
        self._delete_btn.setToolTip("删除选中区域 (Delete)")
        edit_layout.addWidget(self._delete_btn)
        
        self._fill_btn = QPushButton("填充选区")
        self._fill_btn.setToolTip("用颜色填充选区")
        edit_layout.addWidget(self._fill_btn)
        
        fill_color_row = QHBoxLayout()
        fill_color_row.addWidget(QLabel("填充色:"))
        self._fill_color_btn = QPushButton()
        self._fill_color_btn.setFixedSize(40, 25)
        self._update_fill_color_btn()
        fill_color_row.addWidget(self._fill_color_btn)
        fill_color_row.addStretch()
        edit_layout.addLayout(fill_color_row)
        
        self._invert_btn = QPushButton("反选")
        self._invert_btn.setToolTip("反转选区 (Ctrl+I)")
        edit_layout.addWidget(self._invert_btn)
        
        grow_shrink_row = QHBoxLayout()
        self._grow_btn = QPushButton("扩大")
        self._grow_btn.setToolTip("扩大选区1像素")
        grow_shrink_row.addWidget(self._grow_btn)
        
        self._shrink_btn = QPushButton("缩小")
        self._shrink_btn.setToolTip("缩小选区1像素")
        grow_shrink_row.addWidget(self._shrink_btn)
        edit_layout.addLayout(grow_shrink_row)
        
        self._deselect_btn = QPushButton("取消选区")
        self._deselect_btn.setToolTip("取消当前选区 (Ctrl+D)")
        edit_layout.addWidget(self._deselect_btn)
        
        layout.addWidget(edit_group)
        
        layout.addStretch()
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        panel.setFixedWidth(180)
        panel.setStyleSheet("""
            QFrame { background-color: #252525; border-left: 1px solid #3d3d3d; }
            QLabel { color: #aaa; }
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self._info_label = QLabel("图像信息:")
        self._info_label.setStyleSheet("color: #ddd; font-weight: bold;")
        layout.addWidget(self._info_label)
        
        self._size_label = QLabel()
        layout.addWidget(self._size_label)
        
        self._selection_label = QLabel("选区信息:")
        self._selection_label.setStyleSheet("color: #ddd; font-weight: bold; margin-top: 10px;")
        layout.addWidget(self._selection_label)
        
        self._selection_info = QLabel("无选区")
        layout.addWidget(self._selection_info)
        
        self._color_label = QLabel("颜色信息:")
        self._color_label.setStyleSheet("color: #ddd; font-weight: bold; margin-top: 10px;")
        layout.addWidget(self._color_label)
        
        self._color_info = QLabel("移动鼠标查看")
        layout.addWidget(self._color_info)
        
        layout.addStretch()
        
        self._update_info()
        
        return panel
    
    def _create_statusbar(self) -> QWidget:
        statusbar = QFrame()
        statusbar.setFrameStyle(QFrame.StyledPanel)
        statusbar.setFixedHeight(40)
        statusbar.setStyleSheet("""
            QFrame { background-color: #1e1e1e; border-top: 1px solid #3d3d3d; }
            QLabel { color: #888; }
            QPushButton { background-color: #3d3d3d; border: 1px solid #4d4d4d; border-radius: 4px; padding: 5px 15px; color: #ddd; }
            QPushButton:hover { background-color: #4d4d4d; border-color: #0078d4; }
            QPushButton#ok_btn { background-color: #0078d4; border-color: #0078d4; }
            QPushButton#ok_btn:hover { background-color: #1084d8; }
        """)
        
        layout = QHBoxLayout(statusbar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self._status_label = QLabel("就绪 - 点击图像创建选区")
        layout.addWidget(self._status_label)
        
        layout.addStretch()
        
        self._history_label = QLabel("历史: 0/0")
        layout.addWidget(self._history_label)
        
        layout.addSpacing(20)
        
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setToolTip("放弃所有编辑")
        layout.addWidget(self._cancel_btn)
        
        self._ok_btn = QPushButton("确定")
        self._ok_btn.setObjectName("ok_btn")
        self._ok_btn.setToolTip("保存编辑并关闭")
        layout.addWidget(self._ok_btn)
        
        return statusbar
    
    def _setup_connections(self):
        self._undo_btn.clicked.connect(self._undo)
        self._redo_btn.clicked.connect(self._redo)
        
        self._magic_wand_btn.clicked.connect(lambda: self._set_tool("magic_wand"))
        self._eraser_btn.clicked.connect(lambda: self._set_tool("eraser"))
        self._move_btn.clicked.connect(lambda: self._set_tool("move"))
        
        self._zoom_in_btn.clicked.connect(self._zoom_in)
        self._zoom_out_btn.clicked.connect(self._zoom_out)
        self._fit_btn.clicked.connect(self._fit_to_view)
        
        self._reset_btn.clicked.connect(self._reset_image)
        
        self._tolerance_slider.valueChanged.connect(self._on_tolerance_changed)
        self._tolerance_spin.valueChanged.connect(self._on_tolerance_spin_changed)
        self._contiguous_check.stateChanged.connect(self._on_contiguous_changed)
        self._anti_alias_check.stateChanged.connect(self._on_anti_alias_changed)
        
        self._eraser_slider.valueChanged.connect(self._on_eraser_size_changed)
        self._eraser_spin.valueChanged.connect(self._on_eraser_spin_changed)
        
        self._delete_btn.clicked.connect(self._delete_selection)
        self._fill_btn.clicked.connect(self._fill_selection)
        self._fill_color_btn.clicked.connect(self._choose_fill_color)
        self._invert_btn.clicked.connect(self._invert_selection)
        self._grow_btn.clicked.connect(self._grow_selection)
        self._shrink_btn.clicked.connect(self._shrink_selection)
        self._deselect_btn.clicked.connect(self._deselect)
        
        self._ok_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        
        self._bg_checker_btn.clicked.connect(lambda: self._set_background("checkerboard"))
        self._bg_white_btn.clicked.connect(lambda: self._set_background("white"))
        self._bg_black_btn.clicked.connect(lambda: self._set_background("black"))
        
        self._canvas.mousePressEvent = self._on_canvas_mouse_press
        self._canvas.mouseMoveEvent = self._on_canvas_mouse_move
        self._canvas.mouseReleaseEvent = self._on_canvas_mouse_release
        self._canvas.wheelEvent = self._on_canvas_wheel
        
        self._canvas.image_changed.connect(self._update_info)
        self._canvas.selection_changed.connect(self._update_selection_info)
    
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
        zoom = getattr(self._canvas, '_zoom', 1.0)
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
    
    def _update_eraser_cursor(self):
        """更新橡皮擦光标"""
        if self._tool_mode == "eraser":
            self._canvas.setCursor(self._create_eraser_cursor())
    
    def _on_eraser_size_changed(self, value: int):
        self._eraser_size = value
        self._eraser_spin.blockSignals(True)
        self._eraser_spin.setValue(value)
        self._eraser_spin.blockSignals(False)
        self._update_eraser_cursor()
    
    def _on_eraser_spin_changed(self, value: int):
        self._eraser_size = value
        self._eraser_slider.blockSignals(True)
        self._eraser_slider.setValue(value)
        self._eraser_slider.blockSignals(False)
        self._update_eraser_cursor()
    
    def _set_background(self, mode: str):
        self._canvas.set_background_mode(mode)
        
        self._bg_checker_btn.setChecked(mode == "checkerboard")
        self._bg_white_btn.setChecked(mode == "white")
        self._bg_black_btn.setChecked(mode == "black")
    
    def _on_canvas_mouse_press(self, event):
        if event.button() == Qt.LeftButton and self._tool_mode == "magic_wand":
            sx, sy = event.pos().x(), event.pos().y()
            img_x, img_y = self._canvas.screen_to_image(sx, sy)
            
            if self._current_image is not None:
                h, w = self._current_image.shape[:2]
                if 0 <= img_x < w and 0 <= img_y < h:
                    self._create_selection(img_x, img_y)
        
        elif event.button() == Qt.LeftButton and self._tool_mode == "eraser":
            self._is_erasing = True
            self._erase_at_position(event.pos())
        
        ImageCanvas.mousePressEvent(self._canvas, event)
    
    def _on_canvas_mouse_move(self, event):
        sx, sy = event.pos().x(), event.pos().y()
        img_x, img_y = self._canvas.screen_to_image(sx, sy)
        
        if self._current_image is not None:
            h, w = self._current_image.shape[:2]
            if 0 <= img_x < w and 0 <= img_y < h:
                color = self._current_image[img_y, img_x]
                if len(color) == 4:
                    self._color_info.setText(f"R:{color[0]} G:{color[1]} B:{color[2]} A:{color[3]}")
                elif len(color) == 3:
                    self._color_info.setText(f"R:{color[0]} G:{color[1]} B:{color[2]}")
            else:
                self._color_info.setText("超出范围")
        
        # 橡皮擦拖动绘制
        if self._is_erasing and self._tool_mode == "eraser":
            self._erase_at_position(event.pos())
        
        ImageCanvas.mouseMoveEvent(self._canvas, event)
    
    def _on_canvas_mouse_release(self, event):
        if event.button() == Qt.LeftButton and self._is_erasing:
            self._is_erasing = False
            self._save_state()
            self._status_label.setText("擦除完成")
        ImageCanvas.mouseReleaseEvent(self._canvas, event)
    
    def _on_canvas_wheel(self, event):
        """处理缩放事件，更新橡皮擦光标"""
        ImageCanvas.wheelEvent(self._canvas, event)
        # 缩放后更新橡皮擦光标
        if self._tool_mode == "eraser":
            self._canvas.setCursor(self._create_eraser_cursor())
    
    def _erase_at_position(self, pos):
        """在指定位置擦除像素"""
        if self._current_image is None:
            return
        
        sx, sy = pos.x(), pos.y()
        # 使用四舍五入获取更准确的图像坐标
        zoom = getattr(self._canvas, '_zoom', 1.0)
        offset_x = getattr(self._canvas, '_offset_x', 0)
        offset_y = getattr(self._canvas, '_offset_y', 0)
        if zoom == 0:
            return
        img_x = round((sx - offset_x) / zoom)
        img_y = round((sy - offset_y) / zoom)
        
        h, w = self._current_image.shape[:2]
        
        # 确保图像有alpha通道
        if len(self._current_image.shape) == 3 and self._current_image.shape[2] == 3:
            # 转换为RGBA
            self._current_image = np.concatenate([
                self._current_image,
                np.full((h, w, 1), 255, dtype=np.uint8)
            ], axis=2)
        
        # 擦除区域（允许鼠标中心在图像外，只要有交集就擦除）
        half_size = self._eraser_size // 2
        x1 = img_x - half_size
        y1 = img_y - half_size
        x2 = x1 + self._eraser_size
        y2 = y1 + self._eraser_size
        
        # 裁剪到图像范围
        x1_clip = max(0, x1)
        y1_clip = max(0, y1)
        x2_clip = min(w, x2)
        y2_clip = min(h, y2)
        
        if x1_clip < x2_clip and y1_clip < y2_clip:
            # 设置alpha为0（透明）
            self._current_image[y1_clip:y2_clip, x1_clip:x2_clip, 3] = 0
            self._canvas.set_image(self._current_image, reset_view=False)
            self._canvas.update()
    
    def _create_selection(self, x: int, y: int):
        try:
            selection = self._magic_wand.select(
                self._current_image,
                x, y,
                self._tolerance,
                self._contiguous,
                self._anti_alias
            )
            
            mode = self._selection_mode_combo.currentData()
            
            if mode == "new":
                self._canvas.set_selection(selection.mask)
            elif mode == "add":
                current = self._canvas.get_selection()
                if current is not None:
                    new_mask = np.clip(current + selection.mask, 0, 1)
                    new_mask = clean_small_regions(new_mask, min_area=20)
                    self._canvas.set_selection(new_mask)
                else:
                    self._canvas.set_selection(selection.mask)
            elif mode == "subtract":
                current = self._canvas.get_selection()
                if current is not None:
                    new_mask = np.clip(current - selection.mask, 0, 1)
                    new_mask = clean_small_regions(new_mask, min_area=20)
                    self._canvas.set_selection(new_mask)
            elif mode == "intersect":
                current = self._canvas.get_selection()
                if current is not None:
                    new_mask = np.minimum(current, selection.mask)
                    new_mask = clean_small_regions(new_mask, min_area=20)
                    self._canvas.set_selection(new_mask)
            
            self._status_label.setText(f"选区面积: {selection.area} 像素")
            
        except Exception as e:
            self._status_label.setText(f"错误: {str(e)}")
    
    def _delete_selection(self):
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        
        mask = self._canvas.get_selection()
        result = self._current_image.copy()
        
        # 确保mask是二值化的
        binary_mask = (mask > 0.5).astype(np.float32)
        
        if len(result.shape) == 3 and result.shape[2] == 4:
            # RGBA图像：直接删除选区
            alpha = result[:, :, 3].astype(np.float32)
            # 选区内设为0（完全透明），选区外保持原值
            result[:, :, 3] = np.where(binary_mask > 0, 0, alpha).astype(np.uint8)
        elif len(result.shape) == 3 and result.shape[2] == 3:
            # RGB图像：添加alpha通道后删除
            alpha = np.full(result.shape[:2], 255, dtype=np.float32)
            # 选区内设为0（完全透明），选区外保持255
            alpha = np.where(binary_mask > 0, 0, alpha)
            result = np.dstack([result, alpha.astype(np.uint8)])
        
        self._apply_edit(result, "删除选区")
    
    def _fill_selection(self):
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        
        mask = self._canvas.get_selection()
        result = self._current_image.copy()
        
        if len(result.shape) == 2:
            result = np.stack([result]*3 + [np.full_like(result, 255)], axis=2)
        elif result.shape[2] == 3:
            result = np.concatenate([result, np.full((*result.shape[:2], 1), 255, dtype=np.uint8)], axis=2)
        
        for c in range(4):
            result[:, :, c] = (
                result[:, :, c] * (1 - mask) + 
                np.full_like(result[:, :, c], self._fill_color[c]) * mask
            ).astype(np.uint8)
        
        self._apply_edit(result, "填充选区")
    
    def _choose_fill_color(self):
        color = QColorDialog.getColor(
            QColor(*self._fill_color[:3]),
            self,
            "选择填充颜色"
        )
        if color.isValid():
            self._fill_color = (color.red(), color.green(), color.blue(), 255)
            self._update_fill_color_btn()
    
    def _update_fill_color_btn(self):
        r, g, b, a = self._fill_color
        self._fill_color_btn.setStyleSheet(
            f"background-color: rgb({r}, {g}, {b}); border: 1px solid #4d4d4d; border-radius: 3px;"
        )
    
    def _invert_selection(self):
        if self._canvas.has_selection():
            mask = self._canvas.get_selection()
            self._canvas.set_selection(1.0 - mask)
            self._status_label.setText("已反选")
        else:
            h, w = self._current_image.shape[:2]
            self._canvas.set_selection(np.ones((h, w), dtype=np.float32))
            self._status_label.setText("已全选")
    
    def _grow_selection(self):
        """扩大选区 - 向外扩展1像素"""
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        
        mask = self._canvas.get_selection()
        new_mask = grow_selection(mask, pixels=1)
        
        old_area = np.sum(mask > 0.5)
        new_area = np.sum(new_mask > 0.5)
        
        self._canvas.set_selection(new_mask)
        self._status_label.setText(f"扩大选区: {int(old_area)} -> {int(new_area)} 像素")
    
    def _shrink_selection(self):
        """缩小选区 - 向内收缩1像素"""
        if not self._canvas.has_selection():
            self._status_label.setText("请先创建选区")
            return
        
        mask = self._canvas.get_selection()
        new_mask = shrink_selection(mask, pixels=1)
        
        old_area = np.sum(mask > 0.5)
        new_area = np.sum(new_mask > 0.5)
        
        self._canvas.set_selection(new_mask)
        self._status_label.setText(f"缩小选区: {int(old_area)} -> {int(new_area)} 像素")
    
    def _deselect(self):
        self._canvas.set_selection(None)
        self._status_label.setText("已取消选区")
    
    def _apply_edit(self, new_image: np.ndarray, action_name: str):
        self._current_image = new_image
        self._canvas.set_selection(None)
        self._canvas.set_image(self._current_image, reset_view=False)
        self._save_state()
        self._status_label.setText(f"已执行: {action_name}")
    
    def _save_state(self):
        state = EditorState(
            image=self._current_image.copy(),
            selection_mask=self._canvas.get_selection()
        )
        self._history.push(state)
        self._update_history_buttons()
    
    def _undo(self):
        state = self._history.undo()
        if state is not None:
            self._current_image = state.image.copy()
            self._canvas.set_image(self._current_image, reset_view=False)
            self._canvas.set_selection(state.selection_mask)
            self._update_history_buttons()
            self._status_label.setText("已撤销")
    
    def _redo(self):
        state = self._history.redo()
        if state is not None:
            self._current_image = state.image.copy()
            self._canvas.set_image(self._current_image, reset_view=False)
            self._canvas.set_selection(state.selection_mask)
            self._update_history_buttons()
            self._status_label.setText("已重做")
    
    def _update_history_buttons(self):
        self._undo_btn.setEnabled(self._history.can_undo())
        self._redo_btn.setEnabled(self._history.can_redo())
        self._update_history_label()
    
    def _update_history_label(self):
        total = len(self._history._states)
        current = self._history._current_index + 1 if total > 0 else 0
        self._history_label.setText(f"历史: {current}/{total}")
    
    def _zoom_in(self):
        self._canvas.set_zoom(self._canvas.get_zoom() * 1.25)
        self._update_zoom_label()
    
    def _zoom_out(self):
        self._canvas.set_zoom(self._canvas.get_zoom() / 1.25)
        self._update_zoom_label()
    
    def _fit_to_view(self):
        self._canvas._fit_to_view()
        self._update_zoom_label()
    
    def _update_zoom_label(self):
        self._zoom_label.setText(f"{int(self._canvas.get_zoom() * 100)}%")
    
    def _reset_image(self):
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为原始图像吗？所有编辑将被丢弃。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._current_image = self._original_image.copy()
            self._canvas.set_image(self._current_image)
            self._canvas.set_selection(None)
            self._history.clear()
            self._save_state()
            self._status_label.setText("已重置为原始图像")
    
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
    
    def _on_contiguous_changed(self, state: int):
        self._contiguous = state == Qt.Checked
    
    def _on_anti_alias_changed(self, state: int):
        self._anti_alias = state == Qt.Checked
    
    def _update_info(self):
        if self._current_image is not None:
            h, w = self._current_image.shape[:2]
            channels = self._current_image.shape[2] if len(self._current_image.shape) == 3 else 1
            self._size_label.setText(f"尺寸: {w} x {h}\n通道: {channels}")
    
    def _update_selection_info(self):
        mask = self._canvas.get_selection()
        if mask is not None and np.any(mask > 0):
            area = int(np.count_nonzero(mask > 0))
            h, w = mask.shape
            percent = area / (h * w) * 100
            self._selection_info.setText(f"面积: {area} 像素\n占比: {percent:.1f}%")
        else:
            self._selection_info.setText("无选区")
    
    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                self._undo()
            elif event.key() == Qt.Key_Y:
                self._redo()
            elif event.key() == Qt.Key_D:
                self._deselect()
            elif event.key() == Qt.Key_I:
                self._invert_selection()
        elif event.key() == Qt.Key_Delete:
            self._delete_selection()
        elif event.key() == Qt.Key_Escape:
            self._deselect()
        
        super().keyPressEvent(event)
    
    def get_result(self) -> np.ndarray:
        return self._current_image
    
    def closeEvent(self, event):
        if not self._result_saved and self._history.can_undo():
            reply = QMessageBox.question(
                self, "保存编辑",
                "是否保存编辑结果？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self._result_saved = True
                self.image_edited.emit(self._current_image)
                super().closeEvent(event)
                return
        
        super().closeEvent(event)
    
    def accept(self):
        self._result_saved = True
        self.image_edited.emit(self._current_image)
        super().accept()
    
    def reject(self):
        super().reject()
