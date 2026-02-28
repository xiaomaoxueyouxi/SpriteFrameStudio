"""SmoothMix视频生成面板"""
from typing import Optional, List
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QSpinBox, QTextEdit, QFileDialog,
    QProgressBar, QMessageBox, QSizePolicy, QFrame, QListWidget, QListWidgetItem,
    QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QPixmap

from src.workers.smoothmix_worker import SmoothMixWorker


class ImagePreview(QWidget):
    """图片预览组件"""
    
    image_changed = Signal(str)
    
    def __init__(self, title: str = "图片", parent=None):
        super().__init__(parent)
        self._image_path = ""
        self._setup_ui(title)
    
    def _setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label, alignment=Qt.AlignCenter)
        
        # 预览区域 - 大尺寸
        self.preview = QLabel()
        self.preview.setFixedSize(220, 220)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                border: 3px dashed #555;
                border-radius: 8px;
                font-size: 14px;
                color: #666;
            }
        """)
        self.preview.setText("点击选择图片")
        self.preview.setCursor(Qt.PointingHandCursor)
        self.preview.mousePressEvent = lambda e: self._select_image()
        layout.addWidget(self.preview, alignment=Qt.AlignCenter)
        
        # 文件名
        self.path_label = QLabel("未选择")
        self.path_label.setStyleSheet("color: #888; font-size: 12px;")
        self.path_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.path_label)
        
        # 按钮
        self.select_btn = QPushButton("选择图片")
        self.select_btn.setMinimumWidth(120)
        self.select_btn.clicked.connect(self._select_image)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.select_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)"
        )
        if file_path:
            self.set_image(file_path)
    
    def set_image(self, path: str):
        self._image_path = path
        self.path_label.setText(Path(path).name)
        self.path_label.setStyleSheet("color: #0078d4; font-size: 12px;")
        
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(210, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(scaled)
            self.preview.setStyleSheet("""
                QLabel {
                    background-color: #2d2d2d;
                    border: 3px solid #0078d4;
                    border-radius: 8px;
                }
            """)
        self.image_changed.emit(path)
    
    def get_image_path(self) -> str:
        return self._image_path
    
    def clear(self):
        self._image_path = ""
        self.path_label.setText("未选择")
        self.path_label.setStyleSheet("color: #888; font-size: 12px;")
        self.preview.clear()
        self.preview.setText("点击选择图片")
        self.preview.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                border: 3px dashed #555;
                border-radius: 8px;
                font-size: 14px;
                color: #666;
            }
        """)


class SmoothMixPanel(QWidget):
    """SmoothMix视频生成面板"""
    
    video_generated = Signal(str)
    status_changed = Signal(str)
    _connection_result = Signal(bool)  # 线程安全的连接结果信号
    _log_signal = Signal(str)  # 线程安全的日志信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[SmoothMixWorker] = None
        self._comfyui_process = None
        self._was_connected = None
        self._setup_ui()
        
        # 连接信号
        self._connection_result.connect(self._update_connection_status)
        self._log_signal.connect(self._do_log)
        
        self._connection_timer = QTimer(self)
        self._connection_timer.timeout.connect(self._check_connection)
        self._connection_timer.start(5000)
        self._check_connection()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # 服务状态
        status_frame = QFrame()
        status_frame.setStyleSheet("QFrame { background-color: #2d2d2d; border-radius: 8px; padding: 10px; }")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(15, 10, 15, 10)
        
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #ff4444; font-size: 18px;")
        status_layout.addWidget(self.status_indicator)
        
        self.status_label = QLabel("ComfyUI (8188): 未连接")
        self.status_label.setStyleSheet("font-size: 14px;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        self.start_btn = QPushButton("启动 ComfyUI")
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self._start_comfyui)
        status_layout.addWidget(self.start_btn)
        
        layout.addWidget(status_frame)
        
        # 主内容区：左右分栏
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)
        
        # 左侧：图片选择
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)
        
        # 首帧图片
        self.start_image = ImagePreview("首帧图片")
        left_layout.addWidget(self.start_image)
        
        # 尾帧图片
        self.end_image = ImagePreview("尾帧图片 (可选)")
        left_layout.addWidget(self.end_image)
        
        content_layout.addWidget(left_widget)
        
        # 右侧：参数和队列
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(15)
        
        # 提示词
        prompt_group = QGroupBox("提示词")
        prompt_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        prompt_layout = QVBoxLayout(prompt_group)
        
        # 正向提示词
        prompt_layout.addWidget(QLabel("正向提示词:"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述视频内容...")
        self.prompt_edit.setText("镜头跟随，缓慢走路")
        self.prompt_edit.setMinimumHeight(60)
        prompt_layout.addWidget(self.prompt_edit)
        
        # 负向提示词
        prompt_layout.addWidget(QLabel("负向提示词 (可选):"))
        self.negative_prompt_edit = QTextEdit()
        self.negative_prompt_edit.setPlaceholderText("留空使用默认负向提示词...")
        self.negative_prompt_edit.setMaximumHeight(60)
        prompt_layout.addWidget(self.negative_prompt_edit)
        
        right_layout.addWidget(prompt_group)
        
        # 参数
        params_group = QGroupBox("生成参数")
        params_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(12)
        
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("368x704 (竖屏)", (368, 704))
        self.resolution_combo.addItem("480x854 (竖屏)", (480, 854))
        self.resolution_combo.addItem("自定义", (None, None))
        self.resolution_combo.setMinimumWidth(150)
        res_row.addWidget(self.resolution_combo)
        res_row.addStretch()
        params_layout.addLayout(res_row)
        
        frames_row = QHBoxLayout()
        frames_row.addWidget(QLabel("帧数:"))
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(9, 121)
        self.frames_spin.setValue(33)
        self.frames_spin.setMinimumWidth(80)
        frames_row.addWidget(self.frames_spin)
        frames_row.addSpacing(30)
        frames_row.addWidget(QLabel("步数:"))
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 20)
        self.steps_spin.setValue(4)
        self.steps_spin.setMinimumWidth(80)
        frames_row.addWidget(self.steps_spin)
        frames_row.addStretch()
        params_layout.addLayout(frames_row)
        
        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("种子:"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-1, 2**31 - 1)
        self.seed_spin.setValue(-1)
        self.seed_spin.setSpecialValueText("随机")
        self.seed_spin.setMinimumWidth(100)
        seed_row.addWidget(self.seed_spin)
        self.random_btn = QPushButton("🎲 随机")
        self.random_btn.setFixedHeight(32)
        self.random_btn.clicked.connect(self._random_seed)
        seed_row.addWidget(self.random_btn)
        seed_row.addStretch()
        params_layout.addLayout(seed_row)
        
        # 加速和高清选项
        options_row = QHBoxLayout()
        self.sage_attn_check = QCheckBox("Sage-Attention 加速")
        self.sage_attn_check.setToolTip("启用Sage-Attention可加速生成，但需要支持的GPU")
        options_row.addWidget(self.sage_attn_check)
        options_row.addSpacing(20)
        self.upscale_check = QCheckBox("高清修复 (4x)")
        self.upscale_check.setToolTip("使用RealESRGAN进行4倍高清放大")
        options_row.addWidget(self.upscale_check)
        options_row.addStretch()
        params_layout.addLayout(options_row)
        
        right_layout.addWidget(params_group)
        
        # 按钮
        add_row = QHBoxLayout()
        self.add_btn = QPushButton("➕ 添加到队列")
        self.add_btn.setMinimumHeight(40)
        self.add_btn.clicked.connect(self._add_to_queue)
        add_row.addWidget(self.add_btn)
        
        self.clear_btn = QPushButton("🗑️ 清空队列")
        self.clear_btn.setMinimumHeight(40)
        self.clear_btn.clicked.connect(self._clear_queue)
        add_row.addWidget(self.clear_btn)
        right_layout.addLayout(add_row)
        
        content_layout.addWidget(right_widget)
        layout.addLayout(content_layout)
        
        # 底部：任务状态和队列
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)
        
        # 当前任务
        current_group = QGroupBox("当前任务")
        current_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        current_layout = QVBoxLayout(current_group)
        
        self.current_label = QLabel("无")
        self.current_label.setStyleSheet("color: #888; font-size: 14px;")
        current_layout.addWidget(self.current_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(25)
        current_layout.addWidget(self.progress_bar)
        
        self.cancel_btn = QPushButton("取消当前任务")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_current)
        current_layout.addWidget(self.cancel_btn)
        
        bottom_layout.addWidget(current_group)
        
        # 队列
        queue_group = QGroupBox("等待队列")
        queue_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        queue_layout = QVBoxLayout(queue_group)
        
        self.queue_label = QLabel("0 个任务等待中")
        self.queue_label.setStyleSheet("font-size: 13px;")
        queue_layout.addWidget(self.queue_label)
        
        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(100)
        self.queue_list.setStyleSheet("QListWidget { background-color: #2d2d2d; font-size: 13px; }")
        queue_layout.addWidget(self.queue_list)
        
        bottom_layout.addWidget(queue_group)
        
        # 日志区域
        log_group = QGroupBox("运行日志")
        log_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("QTextEdit { background-color: #1e1e1e; color: #cccccc; font-family: Consolas; font-size: 12px; }")
        log_layout.addWidget(self.log_text)
        
        bottom_layout.addWidget(log_group)
        
        layout.addLayout(bottom_layout)
    
    def _log(self, msg: str):
        """添加日志（主线程调用）"""
        self._do_log(msg)
    
    def _do_log(self, msg: str):
        """实际写入日志"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        # 滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _check_connection(self):
        """异步检查连接"""
        from threading import Thread
        
        def do_check():
            import requests
            try:
                r = requests.get("http://127.0.0.1:8188/system_stats", timeout=2)
                self._connection_result.emit(r.status_code == 200)
            except:
                self._connection_result.emit(False)
        
        Thread(target=do_check, daemon=True).start()
    
    def _update_connection_status(self, connected: bool):
        """更新连接状态UI（主线程）"""
        # 只在状态变化时记录日志
        if connected:
            self.status_indicator.setStyleSheet("color: #44ff44; font-size: 16px;")
            self.status_label.setText("ComfyUI (8188): 已连接")
            self.start_btn.setVisible(False)
            if self._was_connected != True:
                self._log("ComfyUI 已连接")
        else:
            self.status_indicator.setStyleSheet("color: #ff4444; font-size: 16px;")
            self.status_label.setText("ComfyUI (8188): 未连接")
            self.start_btn.setVisible(True)
        
        self._was_connected = connected
    
    def _start_comfyui(self):
        import subprocess
        
        base_path = Path(__file__).parent.parent.parent.parent / "portable_output" / "SpriteFrameStudio" / "Wan2.2-SmoothMix"
        start_bat = base_path / "start_comfyui.bat"
        
        if not start_bat.exists():
            QMessageBox.warning(self, "错误", f"找不到启动脚本:\n{start_bat}")
            return
        
        # 显示硬件信息
        self._log("正在检测硬件...")
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
                self._log(f"GPU: {gpu_name} ({gpu_mem:.1f} GB)")
                self._log(f"CUDA: {torch.version.cuda}")
            else:
                self._log("未检测到CUDA GPU")
        except Exception as e:
            self._log(f"硬件检测失败: {e}")
        
        try:
            self._log("启动 ComfyUI (端口 8188)...")
            subprocess.Popen(
                ["cmd", "/c", str(start_bat)],
                cwd=str(base_path),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            self.status_label.setText("ComfyUI (8188): 正在启动...")
            self._log("请等待ComfyUI启动完成...")
        except Exception as e:
            self._log(f"启动失败: {e}")
            QMessageBox.warning(self, "启动失败", str(e))
    
    def _random_seed(self):
        import random
        self.seed_spin.setValue(random.randint(0, 2**31 - 1))
    
    def _add_to_queue(self):
        start_path = self.start_image.get_image_path()
        if not start_path:
            QMessageBox.warning(self, "提示", "请先选择首帧图片")
            return
        
        end_path = self.end_image.get_image_path()
        prompt = self.prompt_edit.toPlainText()
        negative_prompt = self.negative_prompt_edit.toPlainText()
        width, height = self.resolution_combo.currentData() or (368, 704)
        frames = self.frames_spin.value()
        steps = self.steps_spin.value()
        seed = self.seed_spin.value()
        sage_attention = self.sage_attn_check.isChecked()
        enable_upscale = self.upscale_check.isChecked()
        
        if not self._worker:
            self._worker = SmoothMixWorker()
        
        task_id = self._worker.add_task(
            start_image=start_path,
            end_image=end_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            frames=frames,
            steps=steps,
            seed=seed,
            sage_attention=sage_attention,
            enable_upscale=enable_upscale
        )
        
        self._update_queue_list()
        self._start_worker_if_needed()
        
        QMessageBox.information(self, "添加成功", f"任务 {task_id} 已添加到队列")
    
    def _start_worker_if_needed(self):
        if self._worker and not self._worker.isRunning():
            self._worker.task_started.connect(self._on_task_started)
            self._worker.task_progress.connect(self._on_task_progress)
            self._worker.task_completed.connect(self._on_task_completed)
            self._worker.task_failed.connect(self._on_task_failed)
            self._worker.queue_changed.connect(self._on_queue_changed)
            self._worker.start()
    
    def _update_queue_list(self):
        self.queue_list.clear()
        if self._worker:
            pending_count = 0
            for task in self._worker.get_all_tasks():
                if task.status == "pending":
                    pending_count += 1
                    item = QListWidgetItem(f"任务 {task.task_id}: {Path(task.start_image).name[:20]}")
                    self.queue_list.addItem(item)
            self.queue_label.setText(f"{pending_count} 个任务等待中")
    
    def _clear_queue(self):
        if self._worker:
            self._worker.clear_queue()
            self._update_queue_list()
    
    def _cancel_current(self):
        if self._worker:
            self._worker.cancel_current()
    
    @Slot(int, str)
    def _on_task_started(self, task_id: int, message: str):
        self.current_label.setText(f"任务 {task_id}")
        self.current_label.setStyleSheet("color: #0078d4;")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.cancel_btn.setVisible(True)
        self.status_changed.emit(message)
    
    @Slot(int, int, int, str)
    def _on_task_progress(self, task_id: int, current: int, total: int, message: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(message)
    
    @Slot(int, str)
    def _on_task_completed(self, task_id: int, video_path: str):
        self.current_label.setText("无")
        self.current_label.setStyleSheet("color: #888;")
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self._update_queue_list()
        
        reply = QMessageBox.question(
            self, "生成完成",
            f"任务 {task_id} 完成\n视频: {video_path}\n\n是否导入到帧处理?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.video_generated.emit(video_path)
    
    @Slot(int, str)
    def _on_task_failed(self, task_id: int, error: str):
        self.current_label.setText("无")
        self.current_label.setStyleSheet("color: #888;")
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self._update_queue_list()
        QMessageBox.warning(self, "任务失败", f"任务 {task_id} 失败:\n{error}")
    
    @Slot(int)
    def _on_queue_changed(self, length: int):
        self._update_queue_list()
