"""I2V视频生成面板"""
from typing import Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QFileDialog, QProgressBar, QMessageBox,
    QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QPixmap, QImage

from src.core.comfyui_client import ComfyUIClient
from src.workers.i2v_worker import I2VWorker
from src.utils.i2v_config import (
    GENERATION_MODE_I2V, GENERATION_MODE_FLF2V,
    DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FRAMES, DEFAULT_STEPS,
    DEFAULT_POSITIVE_PROMPT, DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_LORA_NAME, DEFAULT_LORA_STRENGTH,
    RESOLUTION_PRESETS
)


class ImageSelector(QWidget):
    """图片选择器组件"""
    
    image_changed = Signal(str)  # 图片路径改变信号
    
    def __init__(self, title: str = "选择图片", parent=None):
        super().__init__(parent)
        self._image_path = ""
        self._setup_ui(title)
    
    def _setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        # 标题和路径
        header = QHBoxLayout()
        header.addWidget(QLabel(title))
        self.path_label = QLabel("未选择")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #888;")
        header.addWidget(self.path_label, 1)
        layout.addLayout(header)
        
        # 图片预览
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(100, 100)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                border: 2px dashed #555;
                border-radius: 8px;
            }
        """)
        self.preview_label.setText("点击选择图片")
        self.preview_label.setCursor(Qt.PointingHandCursor)
        self.preview_label.mousePressEvent = lambda e: self._select_image()
        layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("选择图片")
        self.select_btn.clicked.connect(self._select_image)
        btn_layout.addStretch()
        btn_layout.addWidget(self.select_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _select_image(self):
        """选择图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)"
        )
        if file_path:
            self.set_image(file_path)
    
    def set_image(self, path: str):
        """设置图片"""
        self._image_path = path
        self.path_label.setText(Path(path).name)
        self.path_label.setStyleSheet("color: #0078d4;")
        
        # 显示预览
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                96, 96,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)
            self.preview_label.setStyleSheet("""
                QLabel {
                    background-color: #2d2d2d;
                    border: 2px solid #0078d4;
                    border-radius: 8px;
                }
            """)
        
        self.image_changed.emit(path)
    
    def get_image_path(self) -> str:
        return self._image_path
    
    def clear(self):
        """清除选择"""
        self._image_path = ""
        self.path_label.setText("未选择")
        self.path_label.setStyleSheet("color: #888;")
        self.preview_label.clear()
        self.preview_label.setText("点击选择图片")
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                border: 2px dashed #555;
                border-radius: 8px;
            }
        """)


class I2VPanel(QWidget):
    """I2V视频生成面板"""
    
    # 信号
    video_generated = Signal(str)  # 视频生成完成，参数为视频路径
    status_changed = Signal(str)  # 状态改变
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[I2VWorker] = None
        self._client = ComfyUIClient()
        self._setup_ui()
        self._connect_signals()
        
        # 定时检查连接状态
        self._connection_timer = QTimer(self)
        self._connection_timer.timeout.connect(self._check_connection)
        self._connection_timer.start(5000)  # 每5秒检查一次
        self._check_connection()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        
        # 设置大小策略，适应父容器
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMinimumWidth(340)
        self.setMaximumWidth(350)
        self.setMinimumHeight(600)  # 确保有足够的内容高度触发滚动
        
        # 服务状态
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 5, 10, 5)
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #ff4444; font-size: 16px;")
        status_layout.addWidget(self.status_indicator)
        self.status_label = QLabel("ComfyUI: 未连接")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        # 启动ComfyUI按钮
        self.start_comfyui_btn = QPushButton("启动ComfyUI")
        self.start_comfyui_btn.setMaximumWidth(100)
        self.start_comfyui_btn.clicked.connect(self._start_comfyui)
        status_layout.addWidget(self.start_comfyui_btn)
        
        layout.addWidget(status_frame)
        
        # 图片选择（模式自动判断：首帧=尾帧 → I2V，首帧≠尾帧 → FLF2V）
        image_group = QGroupBox("输入图片")
        image_layout = QVBoxLayout(image_group)
        
        # 首帧图片
        self.start_image_selector = ImageSelector("首帧图片")
        image_layout.addWidget(self.start_image_selector)
        
        # 尾帧图片（不选择时自动使用首帧，即I2V模式）
        self.end_image_selector = ImageSelector("尾帧(可选，不选=I2V)")
        image_layout.addWidget(self.end_image_selector)
        
        layout.addWidget(image_group)
        
        # 提示词
        prompt_group = QGroupBox("提示词")
        prompt_layout = QVBoxLayout(prompt_group)
        
        # 提示词
        prompt_layout.addWidget(QLabel("提示词:"))
        self.positive_prompt_edit = QTextEdit()
        self.positive_prompt_edit.setAcceptRichText(False)  # 只接受纯文本
        self.positive_prompt_edit.setPlaceholderText("描述你想要生成的视频内容...")
        self.positive_prompt_edit.setText(DEFAULT_POSITIVE_PROMPT)
        self.positive_prompt_edit.setMaximumHeight(60)
        prompt_layout.addWidget(self.positive_prompt_edit)
        
        layout.addWidget(prompt_group)
        
        # 生成参数
        params_group = QGroupBox("生成参数")
        params_layout = QVBoxLayout(params_group)
        
        # 分辨率
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        for name, w, h in RESOLUTION_PRESETS:
            self.resolution_combo.addItem(name, (w, h))
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)
        res_row.addWidget(self.resolution_combo)
        res_row.addStretch()
        params_layout.addLayout(res_row)
        
        # 自定义分辨率
        self.custom_res_widget = QWidget()
        self.custom_res_widget.setVisible(False)
        custom_res_layout = QHBoxLayout(self.custom_res_widget)
        custom_res_layout.setContentsMargins(0, 0, 0, 0)
        custom_res_layout.addWidget(QLabel("宽:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(128, 2048)
        self.width_spin.setValue(DEFAULT_WIDTH)
        self.width_spin.setSingleStep(16)
        custom_res_layout.addWidget(self.width_spin)
        custom_res_layout.addWidget(QLabel("高:"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(128, 2048)
        self.height_spin.setValue(DEFAULT_HEIGHT)
        self.height_spin.setSingleStep(16)
        custom_res_layout.addWidget(self.height_spin)
        custom_res_layout.addStretch()
        params_layout.addWidget(self.custom_res_widget)
        
        # 帧数和步数
        frames_row = QHBoxLayout()
        frames_row.addWidget(QLabel("帧数:"))
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(9, 121)
        self.frames_spin.setValue(DEFAULT_FRAMES)
        self.frames_spin.setSingleStep(4)
        frames_row.addWidget(self.frames_spin)
        frames_row.addSpacing(20)
        frames_row.addWidget(QLabel("步数:"))
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 50)
        self.steps_spin.setValue(DEFAULT_STEPS)
        frames_row.addWidget(self.steps_spin)
        frames_row.addStretch()
        params_layout.addLayout(frames_row)
        
        # 种子
        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("种子:"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-1, 2**31 - 1)
        self.seed_spin.setValue(-1)
        self.seed_spin.setSpecialValueText("随机")
        seed_row.addWidget(self.seed_spin)
        self.random_seed_btn = QPushButton("🎲")
        self.random_seed_btn.setFixedSize(30, 30)
        self.random_seed_btn.clicked.connect(self._random_seed)
        seed_row.addWidget(self.random_seed_btn)
        seed_row.addStretch()
        params_layout.addLayout(seed_row)
        
        layout.addWidget(params_group)
        
        # LoRA设置
        lora_group = QGroupBox("LoRA设置")
        lora_layout = QVBoxLayout(lora_group)
        
        lora_row = QHBoxLayout()
        lora_row.addWidget(QLabel("LoRA模型:"))
        self.lora_combo = QComboBox()
        self.lora_combo.addItem("(无风格LoRA)")  # 默认选项
        self._refresh_loras()  # 异步刷新LoRA列表
        lora_row.addWidget(self.lora_combo, 1)
        self.refresh_lora_btn = QPushButton("🔄")
        self.refresh_lora_btn.setFixedSize(30, 30)
        self.refresh_lora_btn.clicked.connect(self._refresh_loras)
        lora_row.addWidget(self.refresh_lora_btn)
        lora_layout.addLayout(lora_row)
        
        strength_row = QHBoxLayout()
        strength_row.addWidget(QLabel("强度:"))
        self.lora_strength_spin = QDoubleSpinBox()
        self.lora_strength_spin.setRange(0.0, 10.0)
        self.lora_strength_spin.setValue(DEFAULT_LORA_STRENGTH)
        self.lora_strength_spin.setSingleStep(0.1)
        strength_row.addWidget(self.lora_strength_spin)
        strength_row.addStretch()
        lora_layout.addLayout(strength_row)
        
        layout.addWidget(lora_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # 生成按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.generate_btn = QPushButton("🎬 生成视频")
        self.generate_btn.setMinimumWidth(150)
        self.generate_btn.clicked.connect(self._start_generation)
        btn_layout.addWidget(self.generate_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_generation)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        layout.addStretch()
    
    def _connect_signals(self):
        """连接信号"""
        pass
    
    def _check_connection(self):
        """检查ComfyUI连接状态"""
        connected = self._client.check_connection()
        if connected:
            self.status_indicator.setStyleSheet("color: #44ff44; font-size: 16px;")
            self.status_label.setText("ComfyUI: 已连接")
            self.start_comfyui_btn.setVisible(False)
        else:
            self.status_indicator.setStyleSheet("color: #ff4444; font-size: 16px;")
            self.status_label.setText("ComfyUI: 未连接")
            self.start_comfyui_btn.setVisible(True)
    
    def _start_comfyui(self):
        """启动ComfyUI"""
        import subprocess
        from pathlib import Path
        from PySide6.QtCore import QTimer
        
        # 立即更新UI反馈
        self.start_comfyui_btn.setEnabled(False)
        self.status_label.setText("ComfyUI: 正在查找启动脚本...")
        
        def do_start():
            base_path = Path(__file__).parent.parent.parent.parent
            possible_paths = [
                base_path / "wan2.2-14B-I2V" / "启动ComfyUI.bat",
                base_path.parent / "wan2.2-14B-I2V" / "启动ComfyUI.bat",
            ]
            
            comfyui_path = None
            for p in possible_paths:
                if p.exists():
                    comfyui_path = p
                    break
            
            if comfyui_path:
                # 直接启动bat，避免双重shell
                subprocess.Popen([str(comfyui_path)], shell=True, cwd=str(comfyui_path.parent))
                self.status_label.setText("ComfyUI: 正在启动...")
                QTimer.singleShot(3000, self._check_connection)
                QTimer.singleShot(6000, self._check_connection)
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "提示", "找不到ComfyUI启动脚本，请手动启动 start_comfyui.bat")
            self.start_comfyui_btn.setEnabled(True)
        
        QTimer.singleShot(10, do_start)
    
    def _on_resolution_changed(self, index):
        """分辨率选择改变"""
        data = self.resolution_combo.currentData()
        if data == (None, None):
            self.custom_res_widget.setVisible(True)
        else:
            self.custom_res_widget.setVisible(False)
    
    def _random_seed(self):
        """生成随机种子"""
        import random
        self.seed_spin.setValue(random.randint(0, 2**31 - 1))
    
    def _refresh_loras(self):
        """刷新LoRA列表"""
        loras = self._client.get_loras()
        current = self.lora_combo.currentText()
        self.lora_combo.clear()
        # 先添加"无"选项
        self.lora_combo.addItem("(无风格LoRA)")
        if loras:
            self.lora_combo.addItems(loras)
        # 恢复之前的选择
        idx = self.lora_combo.findText(current)
        if idx >= 0:
            self.lora_combo.setCurrentIndex(idx)
        else:
            # 默认选择"无"
            self.lora_combo.setCurrentIndex(0)
    
    def _get_resolution(self) -> tuple:
        """获取当前分辨率设置"""
        data = self.resolution_combo.currentData()
        if data == (None, None):
            return self.width_spin.value(), self.height_spin.value()
        return data
    
    def _start_generation(self):
        """开始生成视频"""
        # 检查首帧图片
        start_image_path = self.start_image_selector.get_image_path()
        if not start_image_path:
            QMessageBox.warning(self, "提示", "请先选择首帧图片")
            return
        
        # 获取尾帧图片，自动判断模式
        end_image_path = self.end_image_selector.get_image_path()
        
        # 自动判断模式：尾帧为空或与首帧相同 → I2V，否则 → FLF2V
        if end_image_path and end_image_path != start_image_path:
            mode = GENERATION_MODE_FLF2V
        else:
            mode = GENERATION_MODE_I2V
            end_image_path = ""  # I2V模式不需要尾帧
        
        # 检查连接
        if not self._client.check_connection():
            QMessageBox.warning(self, "提示", "ComfyUI未连接，请先启动ComfyUI服务")
            return
        
        # 获取参数
        width, height = self._get_resolution()
        
        # 创建工作线程
        self._worker = I2VWorker(self)
        self._worker.set_parameters(
            start_image_path=start_image_path,
            end_image_path=end_image_path,
            mode=mode,
            positive_prompt=self.positive_prompt_edit.toPlainText(),
            negative_prompt="",  # 不使用负向提示词
            width=width,
            height=height,
            frames=self.frames_spin.value(),
            steps=self.steps_spin.value(),
            seed=self.seed_spin.value(),
            lora_name=self.lora_combo.currentText(),
            lora_strength=self.lora_strength_spin.value()
        )
        
        # 连接信号
        self._worker.progress.connect(self._on_progress)
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        
        # 更新UI状态
        self.generate_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 启动
        self._worker.start()
        mode_text = "I2V" if mode == GENERATION_MODE_I2V else "FLF2V"
        self.status_changed.emit(f"开始生成视频 ({mode_text}模式)...")
    
    def _cancel_generation(self):
        """取消生成"""
        if self._worker:
            self._worker.cancel()
    
    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, message: str):
        """进度更新"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(message)
    
    @Slot(str)
    def _on_status_changed(self, status: str):
        """状态更新"""
        self.status_changed.emit(status)
    
    @Slot(str, str)
    def _on_finished(self, video_path: str, prompt_id: str):
        """生成完成"""
        self._reset_ui()
        self.status_changed.emit(f"视频生成完成: {video_path}")
        
        # 询问是否导入视频
        reply = QMessageBox.question(
            self,
            "生成完成",
            f"视频已保存到:\n{video_path}\n\n是否导入到帧处理流程?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # 发送信号让主窗口处理
            self.video_generated.emit(video_path)
    
    @Slot(str)
    def _on_error(self, error_msg: str):
        """生成错误"""
        self._reset_ui()
        self.status_changed.emit(f"生成失败: {error_msg}")
        QMessageBox.critical(self, "生成失败", error_msg)
    
    def _reset_ui(self):
        """重置UI状态"""
        self.generate_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self._worker = None
