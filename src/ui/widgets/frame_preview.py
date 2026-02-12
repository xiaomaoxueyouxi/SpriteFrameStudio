"""帧预览网格控件"""
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QLabel, 
    QVBoxLayout, QHBoxLayout, QCheckBox, QFrame, QSizePolicy,
    QPushButton, QDialog, QSpinBox, QSlider, QButtonGroup, QRadioButton,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent, QPoint
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QMouseEvent, QKeyEvent, QCursor
import numpy as np

from src.utils.image_utils import numpy_to_qpixmap, composite_on_checkerboard, blend_with_overlay
from src.core.frame_editor import FrameEditor, EditTool


class FrameZoomDialog(QDialog):
    """帧放大预览对话框 - 支持左右切换、缩放和精修"""
    
    export_requested = Signal(int)  # frame_index
    image_edited = Signal(int, np.ndarray)  # frame_index, edited_image
    
    def __init__(self, images: List[np.ndarray], frame_indices: List[int], current_index: int = 0, parent=None):
        super().__init__(parent)
        self.images = images
        self.frame_indices = frame_indices
        self.current_index = current_index
        self.zoom_factor = 1.0  # 缩放因子
        self.max_zoom = 5.0     # 最大缩放
        self.min_zoom = 0.1     # 最小缩放
        self.bg_mode = "gray"   # 背景模式: gray, white, black
        
        # 精修模式
        self.edit_mode = False
        self.frame_editor: Optional[FrameEditor] = None
        self.current_tool = EditTool.MOVE
        self.is_dragging = False
        self.is_panning = False  # 移动工具拖动状态
        self.last_pan_pos = None  # 上次拖动位置
        
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
        
        self.bg_gray_btn = QPushButton("⚪ 灰色")
        self.bg_gray_btn.setCheckable(True)
        self.bg_gray_btn.setChecked(True)
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
        
        # 精修工具按钮
        self.edit_btn = QPushButton("🔧 精修")
        self.edit_btn.setCheckable(True)
        self.edit_btn.clicked.connect(self._toggle_edit_mode)
        toolbar.addWidget(self.edit_btn)
        
        layout.addLayout(toolbar)

        # 精修工具栏（默认隐藏）- 使用两行布局
        self.edit_toolbar = QVBoxLayout()
        self.edit_toolbar.setSpacing(8)
        self.edit_toolbar.setContentsMargins(8, 8, 8, 8)

        # 第一行：工具选择和参数
        row1_layout = QHBoxLayout()

        # 工具选择
        tool_layout = QHBoxLayout()
        tool_layout.addWidget(QLabel("工具:"))

        self.tool_group = QButtonGroup(self)

        self.move_radio = QRadioButton("移动")
        self.move_radio.setChecked(True)
        self.move_radio.clicked.connect(lambda: self._set_tool(EditTool.MOVE))
        self.tool_group.addButton(self.move_radio)
        tool_layout.addWidget(self.move_radio)

        self.magic_wand_radio = QRadioButton("魔棒")
        self.magic_wand_radio.clicked.connect(lambda: self._set_tool(EditTool.MAGIC_WAND))
        self.tool_group.addButton(self.magic_wand_radio)
        tool_layout.addWidget(self.magic_wand_radio)

        self.eraser_radio = QRadioButton("橡皮")
        self.eraser_radio.clicked.connect(lambda: self._set_tool(EditTool.ERASER))
        self.tool_group.addButton(self.eraser_radio)
        tool_layout.addWidget(self.eraser_radio)

        row1_layout.addLayout(tool_layout)
        row1_layout.addSpacing(30)

        # 容差设置（魔棒工具）
        self.tolerance_layout = QHBoxLayout()
        self.tolerance_layout.addWidget(QLabel("容差:"))
        self.tolerance_slider = QSlider(Qt.Horizontal)
        self.tolerance_slider.setRange(0, 100)
        self.tolerance_slider.setValue(30)
        self.tolerance_slider.setFixedWidth(100)
        self.tolerance_slider.valueChanged.connect(self._on_tolerance_changed)
        self.tolerance_layout.addWidget(self.tolerance_slider)
        self.tolerance_label = QLabel("30")
        self.tolerance_label.setFixedWidth(30)
        self.tolerance_layout.addWidget(self.tolerance_label)
        row1_layout.addLayout(self.tolerance_layout)

        row1_layout.addSpacing(20)

        # 橡皮擦大小
        self.eraser_layout = QHBoxLayout()
        self.eraser_layout.addWidget(QLabel("大小:"))
        self.eraser_slider = QSlider(Qt.Horizontal)
        self.eraser_slider.setRange(1, 50)
        self.eraser_slider.setValue(10)
        self.eraser_slider.setFixedWidth(100)
        self.eraser_slider.valueChanged.connect(self._on_eraser_size_changed)
        self.eraser_layout.addWidget(self.eraser_slider)
        self.eraser_size_label = QLabel("10")
        self.eraser_size_label.setFixedWidth(30)
        self.eraser_layout.addWidget(self.eraser_size_label)
        row1_layout.addLayout(self.eraser_layout)
        self.eraser_layout.setEnabled(False)

        row1_layout.addStretch()
        self.edit_toolbar.addLayout(row1_layout)

        # 第二行：操作按钮
        row2_layout = QHBoxLayout()

        # 选区操作按钮组
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setFixedWidth(60)
        self.select_all_btn.clicked.connect(self._select_all)
        row2_layout.addWidget(self.select_all_btn)

        self.invert_btn = QPushButton("反选")
        self.invert_btn.setFixedWidth(60)
        self.invert_btn.clicked.connect(self._invert_selection)
        row2_layout.addWidget(self.invert_btn)

        self.clear_sel_btn = QPushButton("清除选区")
        self.clear_sel_btn.setFixedWidth(80)
        self.clear_sel_btn.clicked.connect(self._clear_selection)
        row2_layout.addWidget(self.clear_sel_btn)

        row2_layout.addSpacing(20)

        self.delete_btn = QPushButton("🗑️ 删除")
        self.delete_btn.setFixedWidth(80)
        self.delete_btn.setStyleSheet("background-color: #ff4444; color: white;")
        self.delete_btn.clicked.connect(self._delete_selection)
        row2_layout.addWidget(self.delete_btn)

        row2_layout.addSpacing(30)

        # 撤销重做
        self.undo_btn = QPushButton("↩️ 撤销")
        self.undo_btn.setFixedWidth(70)
        self.undo_btn.clicked.connect(self._undo)
        row2_layout.addWidget(self.undo_btn)

        self.redo_btn = QPushButton("↪️ 重做")
        self.redo_btn.setFixedWidth(70)
        self.redo_btn.clicked.connect(self._redo)
        row2_layout.addWidget(self.redo_btn)

        row2_layout.addStretch()

        # 完成和取消
        self.commit_btn = QPushButton("✓ 完成")
        self.commit_btn.setFixedWidth(70)
        self.commit_btn.setStyleSheet("background-color: #44ff44; color: black;")
        self.commit_btn.clicked.connect(self._commit_edit)
        row2_layout.addWidget(self.commit_btn)

        self.cancel_edit_btn = QPushButton("✗ 取消")
        self.cancel_edit_btn.setFixedWidth(70)
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        row2_layout.addWidget(self.cancel_edit_btn)

        self.edit_toolbar.addLayout(row2_layout)

        # 将精修工具栏放入widget以便控制显示
        self.edit_toolbar_widget = QWidget()
        self.edit_toolbar_widget.setLayout(self.edit_toolbar)
        self.edit_toolbar_widget.setStyleSheet("background-color: #2d2d2d; border-radius: 4px;")
        self.edit_toolbar_widget.setVisible(False)
        layout.addWidget(self.edit_toolbar_widget)
        
        # 图像显示区域（可滚动）
        from PySide6.QtWidgets import QScrollArea
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self._update_scroll_area_bg()
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1a1a1a;")
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)
        
        # 底部信息和按钮
        bottom_layout = QHBoxLayout()
        
        # 信息
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #888;")
        bottom_layout.addWidget(self.info_label)
        self._update_info_label()
        
        bottom_layout.addStretch()
        
        # 导出按钮
        export_btn = QPushButton("导出单帧")
        export_btn.clicked.connect(self._on_export_clicked)
        bottom_layout.addWidget(export_btn)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self._on_close)
        bottom_layout.addWidget(close_btn)
        
        layout.addLayout(bottom_layout)
        
        self._display_image()
        
        # 安装事件过滤器以捕获鼠标事件
        self.image_label.installEventFilter(self)
        self.setFocusPolicy(Qt.StrongFocus)
    
    def _toggle_edit_mode(self):
        """切换精修模式"""
        self.edit_mode = self.edit_btn.isChecked()
        self.edit_toolbar_widget.setVisible(self.edit_mode)
        
        if self.edit_mode:
            # 进入精修模式，初始化编辑器
            current_image = self.images[self.current_index]
            self.frame_editor = FrameEditor(current_image)
            self._set_tool(EditTool.MOVE)
            self._update_edit_buttons()
        else:
            # 退出精修模式
            self.frame_editor = None
        
        self._display_image()
    
    def _set_tool(self, tool: EditTool):
        """设置当前工具"""
        self.current_tool = tool

        if self.frame_editor:
            self.frame_editor.current_tool = tool

        # 更新UI
        self.move_radio.setChecked(tool == EditTool.MOVE)
        self.magic_wand_radio.setChecked(tool == EditTool.MAGIC_WAND)
        self.eraser_radio.setChecked(tool == EditTool.ERASER)

        # 启用/禁用相应的设置
        self.tolerance_layout.setEnabled(tool == EditTool.MAGIC_WAND)
        self.eraser_layout.setEnabled(tool == EditTool.ERASER)

        # 更新鼠标样式
        self._update_cursor()

    def _update_cursor(self):
        """根据当前工具更新鼠标样式"""
        if not self.edit_mode:
            self.image_label.setCursor(QCursor(Qt.ArrowCursor))
            return

        if self.current_tool == EditTool.MOVE:
            self.image_label.setCursor(QCursor(Qt.OpenHandCursor))
        elif self.current_tool == EditTool.MAGIC_WAND:
            self.image_label.setCursor(QCursor(Qt.CrossCursor))
        elif self.current_tool == EditTool.ERASER:
            self.image_label.setCursor(QCursor(Qt.PointingHandCursor))
        else:
            self.image_label.setCursor(QCursor(Qt.ArrowCursor))

    def _on_tolerance_changed(self, value):
        """容差滑块变化"""
        self.tolerance_label.setText(str(value))
        if self.frame_editor:
            self.frame_editor.tolerance = value
    
    def _on_eraser_size_changed(self, value):
        """橡皮擦大小变化"""
        self.eraser_size_label.setText(str(value))
        if self.frame_editor:
            self.frame_editor.brush_size = value
    
    def _select_all(self):
        """全选"""
        if self.frame_editor:
            self.frame_editor.select_all()
            self._display_image()
    
    def _invert_selection(self):
        """反选"""
        if self.frame_editor:
            self.frame_editor.invert_selection()
            self._display_image()
    
    def _clear_selection(self):
        """清除选区"""
        if self.frame_editor:
            self.frame_editor.clear_selection()
            self._display_image()
    
    def _delete_selection(self):
        """删除选区"""
        if self.frame_editor:
            self.frame_editor.delete_selection()
            self._update_edit_buttons()
            self._display_image()
    
    def _undo(self):
        """撤销"""
        if self.frame_editor:
            self.frame_editor.undo()
            self._update_edit_buttons()
            self._display_image()
    
    def _redo(self):
        """重做"""
        if self.frame_editor:
            self.frame_editor.redo()
            self._update_edit_buttons()
            self._display_image()
    
    def _update_edit_buttons(self):
        """更新编辑按钮状态"""
        if self.frame_editor:
            self.undo_btn.setEnabled(self.frame_editor.can_undo())
            self.redo_btn.setEnabled(self.frame_editor.can_redo())
    
    def _commit_edit(self):
        """完成编辑"""
        if self.frame_editor:
            edited_image = self.frame_editor.commit()
            self.images[self.current_index] = edited_image
            self.image_edited.emit(self.frame_indices[self.current_index], edited_image)
        
        self.edit_btn.setChecked(False)
        self._toggle_edit_mode()
    
    def _cancel_edit(self):
        """取消编辑"""
        self.edit_btn.setChecked(False)
        self._toggle_edit_mode()
    
    def _on_close(self):
        """关闭对话框"""
        if self.edit_mode:
            reply = QMessageBox.question(
                self, "确认关闭",
                "正在精修模式中，是否保存更改？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Save:
                self._commit_edit()
                self.accept()
            elif reply == QMessageBox.Discard:
                self._cancel_edit()
                self.accept()
            # Cancel则不关闭
        else:
            self.accept()
    
    def eventFilter(self, obj, event):
        """事件过滤器 - 处理鼠标事件"""
        if obj == self.image_label and self.edit_mode and self.frame_editor:
            if event.type() == QEvent.MouseButtonPress:
                self._handle_mouse_press(event)
                return True
            elif event.type() == QEvent.MouseMove:
                self._handle_mouse_move(event)
                return True
            elif event.type() == QEvent.MouseButtonRelease:
                self._handle_mouse_release(event)
                return True
        
        return super().eventFilter(obj, event)
    
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件处理"""
        if self.edit_mode and self.frame_editor:
            if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
                self._delete_selection()
            elif event.key() == Qt.Key_Z and event.modifiers() == Qt.ControlModifier:
                self._undo()
            elif event.key() == Qt.Key_Y and event.modifiers() == Qt.ControlModifier:
                self._redo()
            elif event.key() == Qt.Key_Escape:
                self._clear_selection()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
    
    def _get_image_coords(self, pos: QPoint) -> tuple:
        """将鼠标坐标转换为图像坐标"""
        if not self.image_label.pixmap():
            return (-1, -1)
        
        pixmap = self.image_label.pixmap()
        label_width = self.image_label.width()
        label_height = self.image_label.height()
        pixmap_width = pixmap.width()
        pixmap_height = pixmap.height()
        
        # 计算居中偏移
        offset_x = (label_width - pixmap_width) // 2
        offset_y = (label_height - pixmap_height) // 2
        
        # 转换为图像坐标
        x = pos.x() - offset_x
        y = pos.y() - offset_y
        
        # 检查是否在图像范围内
        if x < 0 or x >= pixmap_width or y < 0 or y >= pixmap_height:
            return (-1, -1)
        
        # 考虑缩放因子，转换回原始图像坐标
        original_x = int(x / self.zoom_factor)
        original_y = int(y / self.zoom_factor)
        
        return (original_x, original_y)
    
    def _handle_mouse_press(self, event: QMouseEvent):
        """处理鼠标按下事件"""
        if not self.frame_editor:
            return

        if self.current_tool == EditTool.MOVE:
            # 移动工具：开始拖动滚动
            if event.button() == Qt.LeftButton:
                self.is_panning = True
                self.last_pan_pos = event.pos()
                self.image_label.setCursor(QCursor(Qt.ClosedHandCursor))
            return

        x, y = self._get_image_coords(event.pos())
        if x < 0 or y < 0:
            return

        if self.current_tool == EditTool.MAGIC_WAND:
            if event.button() == Qt.LeftButton:
                # 左键：添加到选区
                if event.modifiers() == Qt.ShiftModifier:
                    self.frame_editor.add_to_selection(x, y)
                else:
                    self.frame_editor.magic_wand_select(x, y)
                self._display_image()
            elif event.button() == Qt.RightButton:
                # 右键：从选区减去
                self.frame_editor.subtract_from_selection(x, y)
                self._display_image()

        elif self.current_tool == EditTool.ERASER:
            if event.button() == Qt.LeftButton:
                self.is_dragging = True
                self.frame_editor.start_eraser_stroke()
                self.frame_editor.erase_at(x, y)
                self._display_image()

    def _handle_mouse_move(self, event: QMouseEvent):
        """处理鼠标移动事件"""
        if not self.frame_editor:
            return

        if self.current_tool == EditTool.MOVE and self.is_panning:
            # 移动工具：拖动滚动（不重新渲染图像，避免抖动）
            if self.last_pan_pos:
                delta = event.pos() - self.last_pan_pos
                self.scroll_area.horizontalScrollBar().setValue(
                    self.scroll_area.horizontalScrollBar().value() - delta.x()
                )
                self.scroll_area.verticalScrollBar().setValue(
                    self.scroll_area.verticalScrollBar().value() - delta.y()
                )
                self.last_pan_pos = event.pos()
            return

        # 获取图像坐标（用于橡皮擦和显示预览）
        x, y = self._get_image_coords(event.pos())

        # 橡皮擦工具：显示大小预览
        if self.current_tool == EditTool.ERASER:
            self._update_eraser_preview(x, y)

        if not self.is_dragging:
            return

        if x < 0 or y < 0:
            return

        if self.current_tool == EditTool.ERASER:
            self.frame_editor.erase_at(x, y)
            self._display_image()

    def _handle_mouse_release(self, event: QMouseEvent):
        """处理鼠标释放事件"""
        if self.current_tool == EditTool.MOVE and self.is_panning:
            # 移动工具：结束拖动
            self.is_panning = False
            self.last_pan_pos = None
            self.image_label.setCursor(QCursor(Qt.OpenHandCursor))
            return

        if self.current_tool == EditTool.ERASER:
            self.is_dragging = False
            self._update_edit_buttons()
            # 清除橡皮擦预览
            self._clear_eraser_preview()

    def _update_eraser_preview(self, x: int, y: int):
        """更新橡皮擦大小预览"""
        if not self.frame_editor or x < 0 or y < 0:
            self._clear_eraser_preview()
            return

        # 获取当前显示的图像
        if self.edit_mode and self.frame_editor:
            current_image = self.frame_editor.get_display_image(show_selection=True)
        else:
            current_image = self.images[self.current_index]

        # 根据背景模式处理
        display_image = current_image.copy()
        if len(current_image.shape) == 3 and current_image.shape[2] == 4:
            if self.bg_mode == "gray":
                display_image = composite_on_checkerboard(current_image, square_size=15)
            else:
                from PIL import Image
                pil_img = Image.fromarray(current_image)
                if self.bg_mode == "white":
                    background = Image.new('RGBA', pil_img.size, (255, 255, 255, 255))
                else:
                    background = Image.new('RGBA', pil_img.size, (0, 0, 0, 255))
                pil_img = Image.alpha_composite(background, pil_img)
                display_image = np.array(pil_img)

        # 在鼠标位置绘制橡皮擦范围圆圈
        eraser_size = self.frame_editor.brush_size
        scaled_eraser_size = int(eraser_size * self.zoom_factor)

        # 转换图像坐标到显示坐标
        display_x = int(x * self.zoom_factor)
        display_y = int(y * self.zoom_factor)

        # 绘制红色圆圈表示橡皮擦范围
        from PIL import ImageDraw
        pil_display = Image.fromarray(display_image)
        draw = ImageDraw.Draw(pil_display)
        draw.ellipse(
            [display_x - scaled_eraser_size, display_y - scaled_eraser_size,
             display_x + scaled_eraser_size, display_y + scaled_eraser_size],
            outline=(255, 0, 0, 255),
            width=2
        )
        display_image = np.array(pil_display)

        # 显示图像
        pixmap = numpy_to_qpixmap(display_image)
        scaled_width = int(pixmap.width() * self.zoom_factor)
        scaled_height = int(pixmap.height() * self.zoom_factor)
        scaled = pixmap.scaled(
            scaled_width, scaled_height,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def _clear_eraser_preview(self):
        """清除橡皮擦预览，恢复正常显示"""
        self._display_image()

    def _display_image(self):
        """显示当前帧图像"""
        # 获取要显示的图像
        if self.edit_mode and self.frame_editor:
            current_image = self.frame_editor.get_display_image(show_selection=True)
        else:
            current_image = self.images[self.current_index]
        
        # 根据背景模式处理透明通道
        display_image = current_image
        if len(current_image.shape) == 3 and current_image.shape[2] == 4:
            if self.bg_mode == "gray":
                # 灰色背景使用棋盘格
                display_image = composite_on_checkerboard(current_image, square_size=15)
            else:
                # 白色或黑色背景直接合成
                from PIL import Image
                pil_img = Image.fromarray(current_image)
                if self.bg_mode == "white":
                    background = Image.new('RGBA', pil_img.size, (255, 255, 255, 255))
                else:  # black
                    background = Image.new('RGBA', pil_img.size, (0, 0, 0, 255))
                pil_img = Image.alpha_composite(background, pil_img)
                display_image = np.array(pil_img)
        
        pixmap = numpy_to_qpixmap(display_image)
        
        # 应用缩放
        scaled_width = int(pixmap.width() * self.zoom_factor)
        scaled_height = int(pixmap.height() * self.zoom_factor)
        
        # 使用高质量缩放
        scaled = pixmap.scaled(
            scaled_width, scaled_height,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        
        # 更新窗口标题和控件状态
        title = f"帧 #{self.frame_indices[self.current_index]}"
        if self.edit_mode:
            title += " - 精修模式"
        self.setWindowTitle(title)
        self.frame_counter.setText(f"{self.current_index + 1}/{len(self.images)}")
        self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
        
        # 更新导航按钮状态
        can_navigate = not self.edit_mode
        self.prev_btn.setEnabled(can_navigate and self.current_index > 0)
        self.next_btn.setEnabled(can_navigate and self.current_index < len(self.images) - 1)
        
        # 更新缩放按钮状态
        self.zoom_out_btn.setEnabled(self.zoom_factor > self.min_zoom)
        self.zoom_in_btn.setEnabled(self.zoom_factor < self.max_zoom)
        
        # 更新信息显示
        self._update_info_label()
    
    def _update_info_label(self):
        """更新底部信息标签"""
        if self.edit_mode and self.frame_editor:
            current_image = self.frame_editor.current_image
        else:
            current_image = self.images[self.current_index]
        
        h, w = current_image.shape[:2]
        channels = current_image.shape[2] if len(current_image.shape) == 3 else 1
        info = f"尺寸: {w}x{h} | 通道: {channels}"
        if channels == 4:
            alpha = current_image[:, :, 3]
            transparent = np.sum(alpha < 128) / alpha.size * 100
            info += f" | 透明: {transparent:.1f}%"
        
        if self.edit_mode and self.frame_editor:
            has_selection = np.any(self.frame_editor.selection_mask > 0)
            info += f" | 选区: {'有' if has_selection else '无'}"
        
        self.info_label.setText(info)
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
            self.zoom_factor = min(self.zoom_factor * 1.2, self.max_zoom)
            self._display_image()
    
    def _zoom_out(self):
        """缩小"""
        if self.zoom_factor > self.min_zoom:
            self.zoom_factor = max(self.zoom_factor / 1.2, self.min_zoom)
            self._display_image()
    
    def _reset_zoom(self):
        """重置缩放"""
        self.zoom_factor = 1.0
        self._display_image()
    
    def _set_background(self, mode: str):
        """设置背景模式"""
        self.bg_mode = mode
        
        # 更新按钮选中状态
        self.bg_gray_btn.setChecked(mode == "gray")
        self.bg_white_btn.setChecked(mode == "white")
        self.bg_black_btn.setChecked(mode == "black")
        
        # 更新背景显示
        self._update_scroll_area_bg()
        self._display_image()
    
    def _update_scroll_area_bg(self):
        """更新滚动区域背景色"""
        if self.bg_mode == "gray":
            self.scroll_area.setStyleSheet("background-color: #808080;")
        elif self.bg_mode == "white":
            self.scroll_area.setStyleSheet("background-color: #ffffff;")
        elif self.bg_mode == "black":
            self.scroll_area.setStyleSheet("background-color: #000000;")
    
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
    frame_edited = Signal(int, np.ndarray)  # frame_index, edited_image
    
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
        """双击帧放大预览 - 支持多帧浏览和精修"""
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
            dialog = FrameZoomDialog(images, frame_indices, current_pos, parent=self)
            # 连接导出信号
            dialog.export_requested.connect(self.export_single_frame)
            # 连接编辑信号
            dialog.image_edited.connect(self._on_frame_edited)
            dialog.exec()
    
    def _on_frame_edited(self, frame_index: int, edited_image: np.ndarray):
        """处理帧编辑完成事件"""
        # 更新缩略图
        self.update_frame(frame_index, edited_image)
        # 发送信号通知主窗口保存编辑后的帧
        self.frame_edited.emit(frame_index, edited_image)
    
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
