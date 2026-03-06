"""动画预览控件 - 使用透明叠加方案，无需实时合成"""
from typing import List, Optional, Tuple
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QStyle, QSizePolicy, QComboBox,
    QCheckBox, QSpinBox, QTabWidget, QButtonGroup, QRadioButton,
    QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage
import numpy as np

from src.utils.crossfade import apply_loop_transition


class AnimationPreview(QWidget):
    """动画预览控件 - 使用透明叠加方案，无需实时合成"""
    
    # 信号：补帧完成
    rife_completed = Signal(int)  # 参数：生成的帧数
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: List[np.ndarray] = []
        self._original_frames: List[np.ndarray] = []  # 原始帧（crossfade前）
        self._timestamps: List[float] = None
        self._current_index = 0
        self._is_playing = False
        self._fps = 24.0
        self._bg_mode = "gray"  # 背景模式: checkerboard, white, black, gray, custom
        self._custom_bg_color = (128, 128, 128)
        self._cached_pixmaps: List[QPixmap] = []
        self._crossfade_enabled = False
        self._crossfade_count = 5
        self._crossfade_mode = "blend"  # "blend" 或 "align"
        
        # RIFE补帧相关属性
        self._rife_frames: List[np.ndarray] = []  # 补帧数据
        self._append_rife_to_preview: bool = True  # 是否追加到预览
        self._rife_worker = None  # 后台线程
        self._rife_output_dir = Path("output/rife_frames")  # 补帧输出目录
        
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
        
        # ========== Tab区域：循环过渡 + 首尾补帧 ==========
        self.effect_tab = QTabWidget()
        self.effect_tab.setStyleSheet("QTabWidget::pane { border: none; }")
        
        # --- Tab 1: 循环过渡 ---
        crossfade_tab = QWidget()
        crossfade_layout = QHBoxLayout(crossfade_tab)
        crossfade_layout.setContentsMargins(8, 4, 8, 4)
        
        self.crossfade_check = QCheckBox("循环过渡")
        self.crossfade_check.setChecked(False)
        self.crossfade_check.toggled.connect(self._on_crossfade_toggled)
        crossfade_layout.addWidget(self.crossfade_check)
        
        self.crossfade_mode_combo = QComboBox()
        self.crossfade_mode_combo.addItem("像素混合", "blend")
        self.crossfade_mode_combo.addItem("轮廓对齐", "align")
        self.crossfade_mode_combo.setEnabled(False)
        self.crossfade_mode_combo.currentIndexChanged.connect(self._on_crossfade_mode_changed)
        crossfade_layout.addWidget(self.crossfade_mode_combo)
        
        crossfade_layout.addWidget(QLabel("帧数:"))
        self.crossfade_spin = QSpinBox()
        self.crossfade_spin.setRange(1, 30)
        self.crossfade_spin.setValue(5)
        self.crossfade_spin.setEnabled(False)
        self.crossfade_spin.valueChanged.connect(self._on_crossfade_count_changed)
        crossfade_layout.addWidget(self.crossfade_spin)
        
        crossfade_layout.addStretch()
        self.effect_tab.addTab(crossfade_tab, "循环过渡")
        
        # --- Tab 2: 首尾补帧 ---
        rife_tab = QWidget()
        rife_vlayout = QVBoxLayout(rife_tab)
        rife_vlayout.setContentsMargins(8, 4, 8, 4)
        rife_vlayout.setSpacing(4)
        
        # 红字警告提示
        warning_label = QLabel("⚠️ 补帧部分不可操作，请处理完所有帧，最后补帧！然后再导出")
        warning_label.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 12px;")
        warning_label.setWordWrap(True)
        rife_vlayout.addWidget(warning_label)
        
        rife_layout = QHBoxLayout()
        rife_layout.setContentsMargins(0, 0, 0, 0)
        
        rife_layout.addWidget(QLabel("补帧数量:"))
        
        # 帧数量单选按钮组 (1-7帧)
        self.rife_frame_group = QButtonGroup(self)
        for i in range(1, 8):
            radio = QRadioButton(str(i))
            radio.setStyleSheet("margin: 0 2px;")
            self.rife_frame_group.addButton(radio, i)
            rife_layout.addWidget(radio)
            if i == 3:  # 默认选择3帧
                radio.setChecked(True)
        
        rife_layout.addSpacing(10)
        
        # 追加预览复选框
        self.append_rife_check = QCheckBox("追加预览")
        self.append_rife_check.setChecked(True)
        self.append_rife_check.toggled.connect(self._on_append_rife_toggled)
        rife_layout.addWidget(self.append_rife_check)
        
        rife_layout.addSpacing(10)
        
        # 开始补帧按钮
        self.rife_btn = QPushButton("开始补帧")
        self.rife_btn.clicked.connect(self._start_rife_interpolation)
        rife_layout.addWidget(self.rife_btn)
        
        rife_layout.addStretch()
        rife_vlayout.addLayout(rife_layout)
        self.effect_tab.addTab(rife_tab, "首尾补帧")
        
        layout.addWidget(self.effect_tab)
        
        # 进度条（隐藏状态）
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("QProgressBar { height: 20px; }")
        layout.addWidget(self.progress_bar)
    
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
        self._original_frames = list(frames)
        self._timestamps = timestamps
        self._current_index = 0
        
        # 清空补帧（设置新帧时重置）
        self._clear_rife_frames()
        
        # 更新过渡帧数上限
        max_crossfade = max(1, len(frames) // 2)
        self.crossfade_spin.blockSignals(True)
        self.crossfade_spin.setRange(1, max_crossfade)
        if self._crossfade_count > max_crossfade:
            self._crossfade_count = max_crossfade
            self.crossfade_spin.setValue(max_crossfade)
        self.crossfade_spin.blockSignals(False)
        
        # 应用交叉淡入淡出（内部会更新 self._frames 并缓存 pixmap）
        self._apply_crossfade()
        
        # 确保速度滑块显示正确的值
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(int(self._fps))
        self.speed_slider.blockSignals(False)
        self.speed_label.setText(f"{int(self._fps)} fps")
    
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
        
        # 确保数组是 C-contiguous（QImage 需要）
        if not array.flags['C_CONTIGUOUS']:
            array = np.ascontiguousarray(array)
        
        h, w = array.shape[:2]
        
        if len(array.shape) == 2:
            qimg = QImage(array.data, w, h, w, QImage.Format_Grayscale8)
        elif len(array.shape) == 3 and array.shape[2] == 3:
            qimg = QImage(array.data, w, h, w * 3, QImage.Format_RGB888)
        elif len(array.shape) == 3 and array.shape[2] == 4:
            # RGBA 图 - 保留透明通道
            qimg = QImage(array.data, w, h, w * 4, QImage.Format_RGBA8888)
        else:
            return QPixmap()
        
        return QPixmap.fromImage(qimg.copy())
    
    def clear(self):
        """清空帧"""
        self.stop()
        self._frames = []
        self._original_frames = []
        self._timestamps = None
        self._current_index = 0
        self._cached_pixmaps = []
        self._clear_rife_frames()
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
        """播放 - 使用用户设置的速度"""
        if not self._frames:
            return
        self._is_playing = True
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        
        # 总是使用用户设置的 fps，忽略时间戳计算
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
            # 重启播放以应用新的速度
            self.stop()
            self.play()
    
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
        
        # 安全检查：确保缓存和帧列表同步
        if self._current_index >= len(self._cached_pixmaps):
            self.image_label.clear()
            return
        
        pixmap = self._cached_pixmaps[self._current_index]
        
        # 获取原始图像尺寸
        orig_width = pixmap.width()
        orig_height = pixmap.height()
        
        # 直接使用 image_label 自身尺寸，避免硬编码控制栏高度导致裁剪
        label_size = self.image_label.size()
        if label_size.width() > 0 and label_size.height() > 0:
            max_width = label_size.width()
            max_height = label_size.height()
        else:
            # 首次显示时 label 尺寸可能为 0，降级回父容器推算
            parent_size = self.size()
            max_width = parent_size.width() - 20
            max_height = parent_size.height() - 220  # 保守估算控制栏高度
        
        # 确保有有效的显示区域
        if max_width <= 0 or max_height <= 0:
            self.image_label.setPixmap(pixmap)
            return
        
        # 计算合适的缩放比例
        scale_x = max_width / orig_width
        scale_y = max_height / orig_height
        scale = min(scale_x, scale_y, 1.0)  # 不放大，只缩小
        
        target_width = int(orig_width * scale)
        target_height = int(orig_height * scale)
        
        # 使用高质量缩放算法
        scaled = pixmap.scaled(
            target_width, 
            target_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
    
    def _update_labels(self):
        """更新标签"""
        total = len(self._frames)
        current = self._current_index + 1 if total > 0 else 0
        self.frame_label.setText(f"{current} / {total}")
    
    # ========== 循环过渡相关方法 ==========
    
    def _on_crossfade_toggled(self, enabled: bool):
        """循环过渡开关切换"""
        self._crossfade_enabled = enabled
        self.crossfade_spin.setEnabled(enabled)
        self.crossfade_mode_combo.setEnabled(enabled)
        if self._original_frames:
            self._apply_crossfade()
    
    def _on_crossfade_count_changed(self, value: int):
        """过渡帧数变更"""
        self._crossfade_count = value
        if self._crossfade_enabled and self._original_frames:
            self._apply_crossfade()
    
    def _on_crossfade_mode_changed(self, index: int):
        """过渡模式变更"""
        self._crossfade_mode = self.crossfade_mode_combo.currentData()
        if self._crossfade_enabled and self._original_frames:
            self._apply_crossfade()
    
    def _apply_crossfade(self):
        """应用循环过渡并刷新显示"""
        # 先停止播放
        was_playing = self._is_playing
        self.pause()
        
        # 获取基础帧（原始帧 + 补帧）
        base_frames = self._get_base_frames()
        
        if self._crossfade_enabled and len(base_frames) > 1:
            self._frames = apply_loop_transition(
                base_frames, self._crossfade_count,
                mode=self._crossfade_mode
            )
        else:
            self._frames = list(base_frames)
        
        # 确保当前索引不越界
        if self._current_index >= len(self._frames):
            self._current_index = 0
        
        self._cache_all_pixmaps()
        self.frame_slider.setRange(0, max(0, len(self._frames) - 1))
        self.frame_slider.setValue(self._current_index)
        self._update_display()
        self._update_labels()
    
    def get_crossfade_settings(self) -> Tuple[bool, int, str]:
        """获取当前循环过渡设置（供导出使用）"""
        return (self._crossfade_enabled, self._crossfade_count, self._crossfade_mode)
    
    # ========== 首尾补帧相关方法 ==========
    
    def _get_base_frames(self) -> List[np.ndarray]:
        """获取基础帧（原始帧 + 补帧，如果启用追加预览）"""
        if self._append_rife_to_preview and self._rife_frames:
            return list(self._original_frames) + self._rife_frames
        return list(self._original_frames)
    
    def _clear_rife_frames(self):
        """清空补帧数据"""
        self._rife_frames = []
        
        # 删除输出目录中的旧文件
        if self._rife_output_dir.exists():
            for old_file in self._rife_output_dir.glob("*.png"):
                old_file.unlink()
    
    def _on_append_rife_toggled(self, checked: bool):
        """追加预览开关切换"""
        self._append_rife_to_preview = checked
        # 重新应用效果
        self._apply_crossfade()
    
    def _start_rife_interpolation(self):
        """开始RIFE补帧"""
        # 检查是否有帧
        if not self._original_frames or len(self._original_frames) < 2:
            QMessageBox.warning(self, "提示", "至少需要选择2帧才能进行首尾补帧")
            return
        
        # 获取补帧数量
        num_frames = self.rife_frame_group.checkedId()
        if num_frames < 1:
            num_frames = 3
        
        # 清空之前的补帧
        self._clear_rife_frames()
        
        # 获取尾首帧（最后一帧 -> 第一帧，用于循环过渡）
        last_frame = self._original_frames[-1]  # 尾帧作为输入的第一帧
        first_frame = self._original_frames[0]  # 首帧作为输入的最后一帧
        
        # 禁用按钮，显示进度条
        self.rife_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, num_frames + 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("加载模型...")
        
        # 创建工作线程
        from src.tools.rife import RifeWorker
        self._rife_worker = RifeWorker()
        # 尾帧作为起点，首帧作为终点（尾首帧补帧）
        self._rife_worker.setup(last_frame, first_frame, num_frames, self._rife_output_dir)
        self._rife_worker.progress.connect(self._on_rife_progress)
        self._rife_worker.finished.connect(self._on_rife_finished)
        self._rife_worker.error.connect(self._on_rife_error)
        self._rife_worker.start()
    
    def _on_rife_progress(self, current: int, total: int, message: str):
        """补帧进度回调"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(message)
    
    def _on_rife_finished(self, frames: List[np.ndarray]):
        """补帧完成"""
        # 先停止播放，避免更新过程中索引越界
        self.stop()
        
        self._rife_frames = frames
        self.rife_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # 刷新预览
        self._apply_crossfade()
        
        # 发送信号
        self.rife_completed.emit(len(frames))
        
        # 显示提示
        if self._append_rife_to_preview:
            QMessageBox.information(
                self, "补帧完成", 
                f"已生成 {len(frames)} 帧中间帧\n已追加到预览序列末尾"
            )
        else:
            QMessageBox.information(
                self, "补帧完成", 
                f"已生成 {len(frames)} 帧中间帧\n帧文件保存在: {self._rife_output_dir}"
            )
    
    def _on_rife_error(self, error_msg: str):
        """补帧出错"""
        self.rife_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "补帧失败", f"错误: {error_msg}")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()
