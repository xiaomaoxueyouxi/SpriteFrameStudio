""" 导出配置对话框"""
from typing import Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QFileDialog, QLineEdit, QRadioButton,
    QButtonGroup, QTabWidget, QWidget, QMessageBox, QSlider
)
from PySide6.QtCore import Qt

from src.models.export_config import ExportConfig, ExportFormat, LayoutMode, ResampleFilter
from src.utils.config import config
from src.utils.pngquant import is_pngquant_available


class ExportDialog(QDialog):
    """导出配置对话框"""
    
    def __init__(self, frame_count: int = 0, parent=None):
        super().__init__(parent)
        self.frame_count = frame_count
        self._config = ExportConfig()
        self._aspect_ratio = 1.0  # 宽高比
        self._lock_aspect_ratio = True  # 锁定比例
        self._updating_size = False  # 防止递归更新
        
        self.setWindowTitle("导出设置")
        self.setMinimumWidth(400)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Tab页
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # 精灵图选项卡
        sprite_tab = self._create_sprite_tab()
        self.tab_widget.addTab(sprite_tab, "精灵图")
        
        # GIF选项卡
        gif_tab = self._create_gif_tab()
        self.tab_widget.addTab(gif_tab, "GIF动画")
        
        # 单独帧选项卡
        frames_tab = self._create_frames_tab()
        self.tab_widget.addTab(frames_tab, "单独帧")
        
        # Godot选项卡 - 暂时隐藏，功能不成熟
        # godot_tab = self._create_godot_tab()
        # self.tab_widget.addTab(godot_tab, "Godot")
        
        # 输出路径
        path_group = QGroupBox("输出设置")
        path_layout = QVBoxLayout(path_group)
        
        # 文件名
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("文件名:"))
        self.name_edit = QLineEdit("default")
        # 禁止按回车键触发导出
        self.name_edit.returnPressed.connect(lambda: None)
        name_layout.addWidget(self.name_edit, 1)
        path_layout.addLayout(name_layout)
        
        # 输出目录
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("保存到:"))
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        # 加载上次导出路径
        last_dir = config.last_export_dir
        if last_dir:
            self.path_edit.setText(last_dir)
        dir_layout.addWidget(self.path_edit, 1)
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_path)
        dir_layout.addWidget(self.browse_btn)
        path_layout.addLayout(dir_layout)
        
        # PNG压缩选项
        compress_layout = QHBoxLayout()
        self.compress_check = QCheckBox("PNG压缩 (pngquant)")
        self.compress_check.setChecked(False)
        self.compress_check.stateChanged.connect(self._on_compress_changed)
        compress_layout.addWidget(self.compress_check)
        
        compress_layout.addWidget(QLabel("质量:"))
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(40, 100)
        self.quality_slider.setValue(80)
        self.quality_slider.setFixedWidth(100)
        self.quality_slider.setEnabled(False)
        self.quality_slider.valueChanged.connect(self._on_quality_changed)
        compress_layout.addWidget(self.quality_slider)
        
        self.quality_label = QLabel("80")
        self.quality_label.setFixedWidth(25)
        self.quality_label.setEnabled(False)
        compress_layout.addWidget(self.quality_label)
        
        compress_layout.addStretch()
        
        # 检查 pngquant 是否可用
        if not is_pngquant_available():
            self.compress_check.setEnabled(False)
            self.compress_check.setToolTip("pngquant.exe 未找到")
        
        path_layout.addLayout(compress_layout)
        
        layout.addWidget(path_group)
        
        # 信息标签
        self.info_label = QLabel(f"将导出 {self.frame_count} 帧")
        self.info_label.setStyleSheet("color: #888;")
        layout.addWidget(self.info_label)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        self.export_btn = QPushButton("导出")
        # 不设置为默认按钮，防止回车键触发
        # self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._on_export_clicked)
        btn_layout.addWidget(self.export_btn)
        
        layout.addLayout(btn_layout)
    
    def _create_sprite_tab(self) -> QWidget:
        """创建精灵图选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 布局模式
        layout_group = QGroupBox("布局")
        layout_group_layout = QVBoxLayout(layout_group)
        
        self.layout_group = QButtonGroup(self)
        
        self.grid_radio = QRadioButton("网格排列")
        self.grid_radio.setChecked(True)
        self.layout_group.addButton(self.grid_radio)
        layout_group_layout.addWidget(self.grid_radio)
        
        # 列数
        cols_layout = QHBoxLayout()
        cols_layout.addSpacing(20)
        cols_layout.addWidget(QLabel("列数:"))
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 100)
        self.cols_spin.setValue(4)
        cols_layout.addWidget(self.cols_spin)
        cols_layout.addStretch()
        layout_group_layout.addLayout(cols_layout)
        
        self.horizontal_radio = QRadioButton("水平排列")
        self.layout_group.addButton(self.horizontal_radio)
        layout_group_layout.addWidget(self.horizontal_radio)
        
        self.vertical_radio = QRadioButton("垂直排列")
        self.layout_group.addButton(self.vertical_radio)
        layout_group_layout.addWidget(self.vertical_radio)
        
        layout.addWidget(layout_group)
        
        # 尺寸设置
        size_group = QGroupBox("帧尺寸")
        size_layout = QVBoxLayout(size_group)
        
        self.original_size_check = QCheckBox("使用当前尺寸")
        self.original_size_check.setChecked(True)
        self.original_size_check.stateChanged.connect(self._on_original_size_changed)
        size_layout.addWidget(self.original_size_check)
        
        size_input_layout = QHBoxLayout()
        size_input_layout.addWidget(QLabel("宽:"))
        self.frame_width_spin = QSpinBox()
        self.frame_width_spin.setRange(1, 4096)
        self.frame_width_spin.setValue(128)
        self.frame_width_spin.setEnabled(False)
        self.frame_width_spin.valueChanged.connect(self._on_sprite_width_changed)
        size_input_layout.addWidget(self.frame_width_spin)
        
        size_input_layout.addWidget(QLabel("高:"))
        self.frame_height_spin = QSpinBox()
        self.frame_height_spin.setRange(1, 4096)
        self.frame_height_spin.setValue(128)
        self.frame_height_spin.setEnabled(False)
        self.frame_height_spin.valueChanged.connect(self._on_sprite_height_changed)
        size_input_layout.addWidget(self.frame_height_spin)
        
        # 锁定比例按钮
        self.lock_ratio_check = QCheckBox("🔒 锁定比例")
        self.lock_ratio_check.setChecked(True)
        size_input_layout.addWidget(self.lock_ratio_check)
        
        size_layout.addLayout(size_input_layout)
        
        layout.addWidget(size_group)
        
        # 缩放算法选择
        resample_group = QGroupBox("缩放算法")
        resample_layout = QHBoxLayout(resample_group)
        
        resample_layout.addWidget(QLabel("算法:"))
        self.resample_combo = QComboBox()
        self.resample_combo.addItem("📍 最近邻 (像素风格)", ResampleFilter.NEAREST.value)
        self.resample_combo.addItem("📊 盒式滤波", ResampleFilter.BOX.value)
        self.resample_combo.addItem("🌀 双线性 (平滑)", ResampleFilter.BILINEAR.value)
        self.resample_combo.addItem("🔊 Hamming", ResampleFilter.HAMMING.value)
        self.resample_combo.addItem("✨ 双三次 (高质量)", ResampleFilter.BICUBIC.value)
        self.resample_combo.addItem("🌟 Lanczos (最高质量)", ResampleFilter.LANCZOS.value)
        self.resample_combo.setCurrentIndex(5)  # 默认Lanczos
        resample_layout.addWidget(self.resample_combo, 1)
        
        layout.addWidget(resample_group)
        
        # 其他选项
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 100)
        self.padding_spin.setValue(0)
        
        padding_layout = QHBoxLayout()
        padding_layout.addWidget(QLabel("间距:"))
        padding_layout.addWidget(self.padding_spin)
        padding_layout.addWidget(QLabel("像素"))
        padding_layout.addStretch()
        layout.addLayout(padding_layout)
        
        # 取消生成JSON元数据功能
        # self.generate_json_check = QCheckBox("生成JSON元数据")
        # self.generate_json_check.setChecked(True)
        # layout.addWidget(self.generate_json_check)
        
        layout.addStretch()
        return widget
    
    def _create_gif_tab(self) -> QWidget:
        """创建GIF选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 动画设置
        anim_group = QGroupBox("动画设置")
        anim_layout = QVBoxLayout(anim_group)
        
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("帧率:"))
        self.gif_fps_spin = QDoubleSpinBox()
        self.gif_fps_spin.setRange(1, 60)
        self.gif_fps_spin.setValue(10)
        self.gif_fps_spin.setSuffix(" fps")
        fps_layout.addWidget(self.gif_fps_spin)
        fps_layout.addStretch()
        anim_layout.addLayout(fps_layout)
        
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel("循环次数:"))
        self.loop_spin = QSpinBox()
        self.loop_spin.setRange(0, 100)
        self.loop_spin.setValue(0)
        self.loop_spin.setSpecialValueText("无限循环")
        loop_layout.addWidget(self.loop_spin)
        loop_layout.addStretch()
        anim_layout.addLayout(loop_layout)
        
        layout.addWidget(anim_group)
        
        # 尺寸设置
        size_group = QGroupBox("尺寸")
        size_layout = QVBoxLayout(size_group)
        
        self.gif_original_size_check = QCheckBox("使用当前尺寸")
        self.gif_original_size_check.setChecked(True)
        self.gif_original_size_check.stateChanged.connect(self._on_gif_original_size_changed)
        size_layout.addWidget(self.gif_original_size_check)
        
        gif_size_input_layout = QHBoxLayout()
        gif_size_input_layout.addWidget(QLabel("宽:"))
        self.gif_width_spin = QSpinBox()
        self.gif_width_spin.setRange(1, 2048)
        self.gif_width_spin.setValue(256)
        self.gif_width_spin.setEnabled(False)
        self.gif_width_spin.valueChanged.connect(self._on_gif_width_changed)
        gif_size_input_layout.addWidget(self.gif_width_spin)
        
        gif_size_input_layout.addWidget(QLabel("高:"))
        self.gif_height_spin = QSpinBox()
        self.gif_height_spin.setRange(1, 2048)
        self.gif_height_spin.setValue(256)
        self.gif_height_spin.setEnabled(False)
        self.gif_height_spin.valueChanged.connect(self._on_gif_height_changed)
        gif_size_input_layout.addWidget(self.gif_height_spin)
        
        # 锁定比例按钮
        self.gif_lock_ratio_check = QCheckBox("🔒 锁定比例")
        self.gif_lock_ratio_check.setChecked(True)
        gif_size_input_layout.addWidget(self.gif_lock_ratio_check)
        
        size_layout.addLayout(gif_size_input_layout)
        
        layout.addWidget(size_group)
        
        # 缩放算法选择
        gif_resample_group = QGroupBox("缩放算法")
        gif_resample_layout = QHBoxLayout(gif_resample_group)
        
        gif_resample_layout.addWidget(QLabel("算法:"))
        self.gif_resample_combo = QComboBox()
        self.gif_resample_combo.addItem("📍 最近邻 (像素风格)", ResampleFilter.NEAREST.value)
        self.gif_resample_combo.addItem("📊 盒式滤波", ResampleFilter.BOX.value)
        self.gif_resample_combo.addItem("🌀 双线性 (平滑)", ResampleFilter.BILINEAR.value)
        self.gif_resample_combo.addItem("🔊 Hamming", ResampleFilter.HAMMING.value)
        self.gif_resample_combo.addItem("✨ 双三次 (高质量)", ResampleFilter.BICUBIC.value)
        self.gif_resample_combo.addItem("🌟 Lanczos (最高质量)", ResampleFilter.LANCZOS.value)
        self.gif_resample_combo.setCurrentIndex(5)  # 默认Lanczos
        gif_resample_layout.addWidget(self.gif_resample_combo, 1)
        
        layout.addWidget(gif_resample_group)
        
        # 优化选项
        self.optimize_check = QCheckBox("优化文件大小")
        self.optimize_check.setChecked(True)
        layout.addWidget(self.optimize_check)
        
        layout.addStretch()
        return widget
    
    def _create_frames_tab(self) -> QWidget:
        """创建单独帧选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 尺寸设置
        size_group = QGroupBox("尺寸")
        size_layout = QVBoxLayout(size_group)
        
        self.frames_original_size_check = QCheckBox("使用当前尺寸")
        self.frames_original_size_check.setChecked(True)
        self.frames_original_size_check.stateChanged.connect(self._on_frames_original_size_changed)
        size_layout.addWidget(self.frames_original_size_check)
        
        frames_size_input_layout = QHBoxLayout()
        frames_size_input_layout.addWidget(QLabel("宽:"))
        self.frames_width_spin = QSpinBox()
        self.frames_width_spin.setRange(1, 4096)
        self.frames_width_spin.setValue(128)
        self.frames_width_spin.setEnabled(False)
        self.frames_width_spin.valueChanged.connect(self._on_frames_width_changed)
        frames_size_input_layout.addWidget(self.frames_width_spin)
        
        frames_size_input_layout.addWidget(QLabel("高:"))
        self.frames_height_spin = QSpinBox()
        self.frames_height_spin.setRange(1, 4096)
        self.frames_height_spin.setValue(128)
        self.frames_height_spin.setEnabled(False)
        self.frames_height_spin.valueChanged.connect(self._on_frames_height_changed)
        frames_size_input_layout.addWidget(self.frames_height_spin)
        
        self.frames_lock_ratio_check = QCheckBox("🔒 锁定比例")
        self.frames_lock_ratio_check.setChecked(True)
        frames_size_input_layout.addWidget(self.frames_lock_ratio_check)
        
        size_layout.addLayout(frames_size_input_layout)
        layout.addWidget(size_group)
        
        # 缩放算法选择
        frames_resample_group = QGroupBox("缩放算法")
        frames_resample_layout = QHBoxLayout(frames_resample_group)
        
        frames_resample_layout.addWidget(QLabel("算法:"))
        self.frames_resample_combo = QComboBox()
        self.frames_resample_combo.addItem("📍 最近邻 (像素风格)", ResampleFilter.NEAREST.value)
        self.frames_resample_combo.addItem("📊 盒式滤波", ResampleFilter.BOX.value)
        self.frames_resample_combo.addItem("🌀 双线性 (平滑)", ResampleFilter.BILINEAR.value)
        self.frames_resample_combo.addItem("🔊 Hamming", ResampleFilter.HAMMING.value)
        self.frames_resample_combo.addItem("✨ 双三次 (高质量)", ResampleFilter.BICUBIC.value)
        self.frames_resample_combo.addItem("🌟 Lanczos (最高质量)", ResampleFilter.LANCZOS.value)
        self.frames_resample_combo.setCurrentIndex(5)  # 默认Lanczos
        frames_resample_layout.addWidget(self.frames_resample_combo, 1)
        
        layout.addWidget(frames_resample_group)
        
        # 提示
        hint_label = QLabel(
            "📁 导出说明：\n"
            "• 每帧导出为单独的PNG文件\n"
            "• 文件名格式：{输出名称}_{帧索引}.png\n"
            "• 适用于需要单独处理每帧的场景"
        )
        hint_label.setStyleSheet("color: #888; padding: 10px; background-color: #2a2a2a; border-radius: 4px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        layout.addStretch()
        return widget
    
    def _create_godot_tab(self) -> QWidget:
        """创建Godot选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 动画设置
        anim_group = QGroupBox("动画设置")
        anim_layout = QVBoxLayout(anim_group)
        
        # 动画名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("动画名称:"))
        self.godot_anim_name_edit = QLineEdit("default")
        name_layout.addWidget(self.godot_anim_name_edit)
        name_layout.addStretch()
        anim_layout.addLayout(name_layout)
        
        # 帧率
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("帧率:"))
        self.godot_fps_spin = QDoubleSpinBox()
        self.godot_fps_spin.setRange(1, 60)
        self.godot_fps_spin.setValue(10)
        self.godot_fps_spin.setSuffix(" fps")
        fps_layout.addWidget(self.godot_fps_spin)
        fps_layout.addStretch()
        anim_layout.addLayout(fps_layout)
        
        # 循环设置
        self.godot_loop_check = QCheckBox("循环播放")
        self.godot_loop_check.setChecked(True)
        anim_layout.addWidget(self.godot_loop_check)
        
        layout.addWidget(anim_group)
        
        # 尺寸设置
        size_group = QGroupBox("尺寸")
        size_layout = QVBoxLayout(size_group)
        
        self.godot_original_size_check = QCheckBox("使用当前尺寸")
        self.godot_original_size_check.setChecked(True)
        self.godot_original_size_check.stateChanged.connect(self._on_godot_original_size_changed)
        size_layout.addWidget(self.godot_original_size_check)
        
        godot_size_input_layout = QHBoxLayout()
        godot_size_input_layout.addWidget(QLabel("宽:"))
        self.godot_width_spin = QSpinBox()
        self.godot_width_spin.setRange(1, 2048)
        self.godot_width_spin.setValue(128)
        self.godot_width_spin.setEnabled(False)
        self.godot_width_spin.valueChanged.connect(self._on_godot_width_changed)
        godot_size_input_layout.addWidget(self.godot_width_spin)
        
        godot_size_input_layout.addWidget(QLabel("高:"))
        self.godot_height_spin = QSpinBox()
        self.godot_height_spin.setRange(1, 2048)
        self.godot_height_spin.setValue(128)
        self.godot_height_spin.setEnabled(False)
        self.godot_height_spin.valueChanged.connect(self._on_godot_height_changed)
        godot_size_input_layout.addWidget(self.godot_height_spin)
        
        self.godot_lock_ratio_check = QCheckBox("🔒 锁定比例")
        self.godot_lock_ratio_check.setChecked(True)
        godot_size_input_layout.addWidget(self.godot_lock_ratio_check)
        
        size_layout.addLayout(godot_size_input_layout)
        layout.addWidget(size_group)
        
        # 缩放算法
        godot_resample_group = QGroupBox("缩放算法")
        godot_resample_layout = QHBoxLayout(godot_resample_group)
        
        godot_resample_layout.addWidget(QLabel("算法:"))
        self.godot_resample_combo = QComboBox()
        self.godot_resample_combo.addItem("📍 最近邻 (像素风格)", ResampleFilter.NEAREST.value)
        self.godot_resample_combo.addItem("📊 盒式滤波", ResampleFilter.BOX.value)
        self.godot_resample_combo.addItem("🌀 双线性 (平滑)", ResampleFilter.BILINEAR.value)
        self.godot_resample_combo.addItem("🔊 Hamming", ResampleFilter.HAMMING.value)
        self.godot_resample_combo.addItem("✨ 双三次 (高质量)", ResampleFilter.BICUBIC.value)
        self.godot_resample_combo.addItem("🌟 Lanczos (最高质量)", ResampleFilter.LANCZOS.value)
        self.godot_resample_combo.setCurrentIndex(5)
        godot_resample_layout.addWidget(self.godot_resample_combo, 1)
        
        layout.addWidget(godot_resample_group)
        
        # 提示
        hint_label = QLabel(
            "🎮 导出说明：\n"
            "• 生成 .tres 资源文件 + 单独帧PNG\n"
            "• 直接导入Godot，无需手动配置\n"
            "• 适用于AnimatedSprite2D节点"
        )
        hint_label.setStyleSheet("color: #888; padding: 10px; background-color: #2a2a2a; border-radius: 4px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        layout.addStretch()
        return widget
    
    def _on_original_size_changed(self, state):
        enabled = state != Qt.Checked
        self.frame_width_spin.setEnabled(enabled)
        self.frame_height_spin.setEnabled(enabled)
        self.lock_ratio_check.setEnabled(enabled)
    
    def _on_sprite_width_changed(self, value):
        if self._updating_size or not self.lock_ratio_check.isChecked():
            return
        if self._aspect_ratio > 0:
            self._updating_size = True
            new_height = int(value / self._aspect_ratio)
            self.frame_height_spin.setValue(new_height)
            self._updating_size = False
    
    def _on_sprite_height_changed(self, value):
        if self._updating_size or not self.lock_ratio_check.isChecked():
            return
        if value > 0:
            self._updating_size = True
            new_width = int(value * self._aspect_ratio)
            self.frame_width_spin.setValue(new_width)
            self._updating_size = False
    
    def _on_gif_original_size_changed(self, state):
        enabled = state != Qt.Checked
        self.gif_width_spin.setEnabled(enabled)
        self.gif_height_spin.setEnabled(enabled)
        self.gif_lock_ratio_check.setEnabled(enabled)
    
    def _on_gif_width_changed(self, value):
        if self._updating_size or not self.gif_lock_ratio_check.isChecked():
            return
        if self._aspect_ratio > 0:
            self._updating_size = True
            new_height = int(value / self._aspect_ratio)
            self.gif_height_spin.setValue(new_height)
            self._updating_size = False
    
    def _on_gif_height_changed(self, value):
        if self._updating_size or not self.gif_lock_ratio_check.isChecked():
            return
        if value > 0:
            self._updating_size = True
            new_width = int(value * self._aspect_ratio)
            self.gif_width_spin.setValue(new_width)
            self._updating_size = False
    
    def _on_godot_original_size_changed(self, state):
        enabled = state != Qt.Checked
        self.godot_width_spin.setEnabled(enabled)
        self.godot_height_spin.setEnabled(enabled)
        self.godot_lock_ratio_check.setEnabled(enabled)
    
    def _on_godot_width_changed(self, value):
        if self._updating_size or not self.godot_lock_ratio_check.isChecked():
            return
        if self._aspect_ratio > 0:
            self._updating_size = True
            new_height = int(value / self._aspect_ratio)
            self.godot_height_spin.setValue(new_height)
            self._updating_size = False
    
    def _on_godot_height_changed(self, value):
        if self._updating_size or not self.godot_lock_ratio_check.isChecked():
            return
        if value > 0:
            self._updating_size = True
            new_width = int(value * self._aspect_ratio)
            self.godot_width_spin.setValue(new_width)
            self._updating_size = False
    
    def _on_frames_original_size_changed(self, state):
        enabled = state != Qt.Checked
        self.frames_width_spin.setEnabled(enabled)
        self.frames_height_spin.setEnabled(enabled)
        self.frames_lock_ratio_check.setEnabled(enabled)
    
    def _on_frames_width_changed(self, value):
        if self._updating_size or not self.frames_lock_ratio_check.isChecked():
            return
        if self._aspect_ratio > 0:
            self._updating_size = True
            new_height = int(value / self._aspect_ratio)
            self.frames_height_spin.setValue(new_height)
            self._updating_size = False
    
    def _on_frames_height_changed(self, value):
        if self._updating_size or not self.frames_lock_ratio_check.isChecked():
            return
        if value > 0:
            self._updating_size = True
            new_width = int(value * self._aspect_ratio)
            self.frames_width_spin.setValue(new_width)
            self._updating_size = False
    
    def _on_compress_changed(self, state):
        """压缩选项变化"""
        enabled = state == Qt.Checked
        self.quality_slider.setEnabled(enabled)
        self.quality_label.setEnabled(enabled)
    
    def _on_quality_changed(self, value):
        """质量滑块变化"""
        self.quality_label.setText(str(value))
    
    def _browse_path(self):
        # 从上次路径或当前路径开始
        start_dir = self.path_edit.text() or config.last_export_dir or ""
        path = QFileDialog.getExistingDirectory(self, "选择保存目录", start_dir)
        if path:
            self.path_edit.setText(path)
            # 保存路径到配置
            config.last_export_dir = path
    
    def _on_export_clicked(self):
        """点击导出按钮 - 检查文件是否存在"""
        # 检查是否选择了输出目录
        if not self.path_edit.text():
            QMessageBox.warning(self, "提示", "请选择保存目录")
            return
        
        # 检查文件是否已存在
        output_path = Path(self.path_edit.text())
        output_name = self.name_edit.text() or "default"
        
        # 根据当前选中的格式检查文件
        file_exists = False
        existing_files = []
        
        if self.tab_widget.currentIndex() == 0:  # 精灵图
            sprite_file = output_path / f"{output_name}.png"
            if sprite_file.exists():
                file_exists = True
                existing_files.append(sprite_file.name)
        elif self.tab_widget.currentIndex() == 1:  # GIF
            gif_file = output_path / f"{output_name}.gif"
            if gif_file.exists():
                file_exists = True
                existing_files.append(gif_file.name)
        elif self.tab_widget.currentIndex() == 2:  # 单独帧
            # 检查输出目录是否存在
            if output_path.exists():
                # 检查是否有与输出名称相关的文件存在
                import glob
                existing_files = glob.glob(str(output_path / f"{output_name}_*.png"))
                if existing_files:
                    file_exists = True
                    existing_files = [Path(f).name for f in existing_files[:3]]  # 只显示前3个文件
                    if len(existing_files) > 3:
                        existing_files.append("...")
        
        # 如果文件已存在，询问是否覆盖
        if file_exists:
            reply = QMessageBox.question(
                self, "文件已存在",
                f"以下文件已存在:\n{', '.join(existing_files)}\n\n是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
        
        # 保存路径到配置
        config.last_export_dir = self.path_edit.text()
        
        # 接受对话框
        self.accept()
    
    def set_original_size(self, width: int, height: int):
        """设置当前帧尺寸和宽高比（用于初始化默认值）"""
        if height > 0:
            self._aspect_ratio = width / height
            self.frame_width_spin.setValue(width)
            self.frame_height_spin.setValue(height)
            self.gif_width_spin.setValue(width)
            self.gif_height_spin.setValue(height)
            self.frames_width_spin.setValue(width)
            self.frames_height_spin.setValue(height)
            # Godot选项卡已隐藏，注释掉相关代码
            # self.godot_width_spin.setValue(width)
            # self.godot_height_spin.setValue(height)
    
    def get_config(self) -> ExportConfig:
        """获取导出配置"""
        config = ExportConfig()
        
        # 格式
        if self.tab_widget.currentIndex() == 0:
            config.format = ExportFormat.SPRITE_SHEET
        elif self.tab_widget.currentIndex() == 1:
            config.format = ExportFormat.GIF
        elif self.tab_widget.currentIndex() == 2:
            config.format = ExportFormat.FRAMES
        # elif self.tab_widget.currentIndex() == 3:
        #     config.format = ExportFormat.GODOT
        
        # 输出路径
        config.output_name = self.name_edit.text() or "default"
        if self.path_edit.text():
            config.output_path = Path(self.path_edit.text())
        
        # 精灵图配置
        if self.grid_radio.isChecked():
            config.sprite_config.layout = LayoutMode.GRID
            config.sprite_config.columns = self.cols_spin.value()
        elif self.horizontal_radio.isChecked():
            config.sprite_config.layout = LayoutMode.HORIZONTAL
        else:
            config.sprite_config.layout = LayoutMode.VERTICAL
        
        config.sprite_config.padding = self.padding_spin.value()
        config.sprite_config.generate_json = False  # 取消JSON元数据生成功能
        config.sprite_config.resample_filter = ResampleFilter(self.resample_combo.currentData())
        
        if not self.original_size_check.isChecked():
            config.sprite_config.frame_width = self.frame_width_spin.value()
            config.sprite_config.frame_height = self.frame_height_spin.value()
        
        # GIF配置
        config.gif_config.fps = self.gif_fps_spin.value()
        config.gif_config.loop = self.loop_spin.value()
        config.gif_config.optimize = self.optimize_check.isChecked()
        config.gif_config.resample_filter = ResampleFilter(self.gif_resample_combo.currentData())
        
        if not self.gif_original_size_check.isChecked():
            config.gif_config.frame_width = self.gif_width_spin.value()
            config.gif_config.frame_height = self.gif_height_spin.value()
        
        # Godot配置（已隐藏，保留代码以备后用）
        # config.godot_config.animation_name = self.godot_anim_name_edit.text() or "default"
        # config.godot_config.fps = self.godot_fps_spin.value()
        # config.godot_config.loop = self.godot_loop_check.isChecked()
        # config.godot_config.resample_filter = ResampleFilter(self.godot_resample_combo.currentData())
        # 
        # if not self.godot_original_size_check.isChecked():
        #     config.godot_config.frame_width = self.godot_width_spin.value()
        #     config.godot_config.frame_height = self.godot_height_spin.value()
        
        # PNG压缩配置
        config.pngquant_config.enabled = self.compress_check.isChecked()
        quality = self.quality_slider.value()
        config.pngquant_config.quality_min = max(quality - 20, 0)
        config.pngquant_config.quality_max = quality
        
        return config
