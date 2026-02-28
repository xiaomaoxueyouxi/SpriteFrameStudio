"""SmoothMix视频生成面板"""
from typing import Optional, List
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QSpinBox, QTextEdit, QFileDialog,
    QProgressBar, QMessageBox, QSizePolicy, QFrame, QScrollArea, QDialog,
    QCheckBox, QSlider, QStyle
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QUrl
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
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title_label, alignment=Qt.AlignCenter)
        
        # 预览区域 - 加大尺寸
        self.preview = QLabel()
        self.preview.setMinimumSize(280, 280)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                border: 2px dashed #555;
                border-radius: 6px;
                font-size: 13px;
                color: #666;
            }
        """)
        self.preview.setText("点击选择图片")
        self.preview.setCursor(Qt.PointingHandCursor)
        self.preview.mousePressEvent = lambda e: self._select_image()
        layout.addWidget(self.preview, 1)  # 拉伸填充
        
        # 文件名和按钮在一行
        bottom_row = QHBoxLayout()
        self.path_label = QLabel("未选择")
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        bottom_row.addWidget(self.path_label, 1)
        
        self.select_btn = QPushButton("选择")
        self.select_btn.setFixedWidth(60)
        self.select_btn.clicked.connect(self._select_image)
        bottom_row.addWidget(self.select_btn)
        layout.addLayout(bottom_row)
    
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
        self.path_label.setStyleSheet("color: #0078d4; font-size: 11px;")
        
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            # 根据容器大小缩放
            size = self.preview.size()
            scaled = pixmap.scaled(size.width() - 10, size.height() - 10, 
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(scaled)
            self.preview.setStyleSheet("""
                QLabel {
                    background-color: #2d2d2d;
                    border: 2px solid #0078d4;
                    border-radius: 6px;
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
        # 设置ToolTip全局样式（解决深色背景下白字看不见的问题）
        self.setStyleSheet("QToolTip { color: black; background-color: white; border: 1px solid #ccc; }")
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
        # self._check_connection()  # 暂时禁用初始连接检查，测试弹框问题
        
        # 初始化时加载历史任务
        self._ensure_worker_running()
        self._update_queue_list()
        # 显示加载结果
        if self._worker:
            loaded = getattr(self._worker, '_loaded_task_count', None)
            if loaded is not None:
                if loaded == -1:
                    self._log("加载历史任务失败")
                else:
                    self._log(f"加载了 {loaded} 个历史任务")
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)
        
        # 服务状态
        status_frame = QFrame()
        status_frame.setStyleSheet("QFrame { background-color: #2d2d2d; border-radius: 6px; }")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 8, 12, 8)
        
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #ff4444; font-size: 16px;")
        status_layout.addWidget(self.status_indicator)
        
        self.status_label = QLabel("ComfyUI (8188): 未连接")
        self.status_label.setStyleSheet("font-size: 13px;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        self.start_btn = QPushButton("启动 ComfyUI")
        self.start_btn.setMinimumWidth(100)
        self.start_btn.clicked.connect(self._start_comfyui)
        status_layout.addWidget(self.start_btn)
        
        layout.addWidget(status_frame)
        
        # 主内容区：上下分栏
        # 上部：图片和参数
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)
        
        # 首帧图片
        self.start_image = ImagePreview("首帧图片")
        top_layout.addWidget(self.start_image, 1)
        
        # 尾帧图片
        self.end_image = ImagePreview("尾帧图片 (可选)")
        top_layout.addWidget(self.end_image, 1)
        
        # 参数区域
        params_widget = QWidget()
        params_main_layout = QVBoxLayout(params_widget)
        params_main_layout.setContentsMargins(0, 0, 0, 0)
        params_main_layout.setSpacing(8)
        
        # 提示词
        prompt_group = QGroupBox("提示词")
        prompt_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        prompt_layout = QVBoxLayout(prompt_group)
        
        # 正向提示词
        prompt_layout.addWidget(QLabel("正向提示词:"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述视频内容...")
        self.prompt_edit.setText("镜头跟随，缓慢走路")
        self.prompt_edit.setMaximumHeight(50)
        prompt_layout.addWidget(self.prompt_edit)
        
        # 负向提示词
        prompt_layout.addWidget(QLabel("负向提示词 (可选):"))
        self.negative_prompt_edit = QTextEdit()
        self.negative_prompt_edit.setPlaceholderText("留空使用默认负向提示词...")
        self.negative_prompt_edit.setMaximumHeight(40)
        prompt_layout.addWidget(self.negative_prompt_edit)
        
        params_main_layout.addWidget(prompt_group)
        
        # 参数
        params_group = QGroupBox("生成参数")
        params_group.setStyleSheet("QGroupBox { font-size: 13px; font-weight: bold; }")
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(8)
        
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("368x704 (竖屏)", (368, 704))
        self.resolution_combo.addItem("480x854 (竖屏)", (480, 854))
        self.resolution_combo.addItem("自定义", (None, None))
        self.resolution_combo.setMinimumWidth(120)
        res_row.addWidget(self.resolution_combo)
        res_row.addStretch()
        params_layout.addLayout(res_row)
        
        frames_row = QHBoxLayout()
        frames_row.addWidget(QLabel("帧数:"))
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(9, 121)
        self.frames_spin.setValue(33)
        self.frames_spin.setMinimumWidth(70)
        self.frames_spin.valueChanged.connect(self._update_duration)
        frames_row.addWidget(self.frames_spin)
        frames_row.addSpacing(10)
        frames_row.addWidget(QLabel("FPS:"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(8, 30)
        self.fps_spin.setValue(16)
        self.fps_spin.setMinimumWidth(60)
        self.fps_spin.valueChanged.connect(self._update_duration)
        frames_row.addWidget(self.fps_spin)
        frames_row.addSpacing(10)
        self.duration_label = QLabel("2.1秒")
        self.duration_label.setStyleSheet("color: #0078d4; font-weight: bold;")
        frames_row.addWidget(self.duration_label)
        frames_row.addStretch()
        params_layout.addLayout(frames_row)
        
        steps_seed_row = QHBoxLayout()
        steps_seed_row.addWidget(QLabel("步数:"))
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 20)
        self.steps_spin.setValue(4)
        self.steps_spin.setMinimumWidth(60)
        steps_seed_row.addWidget(self.steps_spin)
        steps_seed_row.addSpacing(10)
        steps_seed_row.addWidget(QLabel("种子:"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-1, 2**31 - 1)
        self.seed_spin.setValue(-1)
        self.seed_spin.setSpecialValueText("随机")
        self.seed_spin.setMinimumWidth(80)
        steps_seed_row.addWidget(self.seed_spin)
        self.random_btn = QPushButton("随机")
        self.random_btn.setFixedSize(28, 28)
        self.random_btn.clicked.connect(self._random_seed)
        steps_seed_row.addWidget(self.random_btn)
        steps_seed_row.addStretch()
        params_layout.addLayout(steps_seed_row)
        
        # 加速和高清选项
        options_row = QHBoxLayout()
        self.sage_attn_check = QCheckBox("Sage-Attention")
        self.sage_attn_check.setToolTip("启用Sage-Attention可加速生成")
        self.sage_attn_check.setStyleSheet("QCheckBox { color: white; }")
        options_row.addWidget(self.sage_attn_check)
        self.upscale_check = QCheckBox("高清修复(4x)")
        self.upscale_check.setToolTip("使用RealESRGAN进行4倍高清放大")
        self.upscale_check.setStyleSheet("QCheckBox { color: white; }")
        options_row.addWidget(self.upscale_check)
        options_row.addStretch()
        params_layout.addLayout(options_row)
        
        params_main_layout.addWidget(params_group)
        
        # 按钮
        add_row = QHBoxLayout()
        self.add_btn = QPushButton("添加到队列")
        self.add_btn.setMinimumHeight(35)
        self.add_btn.clicked.connect(self._add_to_queue)
        add_row.addWidget(self.add_btn)
        
        self.clear_btn = QPushButton("清空队列")
        self.clear_btn.setMinimumHeight(35)
        self.clear_btn.clicked.connect(self._clear_queue)
        add_row.addWidget(self.clear_btn)
        params_main_layout.addLayout(add_row)
        
        top_layout.addWidget(params_widget, 1)
        layout.addLayout(top_layout, 1)
        
        # 底部：任务队列和日志
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)
        
        # 任务队列
        queue_group = QGroupBox("任务队列")
        queue_group.setStyleSheet("QGroupBox { font-size: 13px; font-weight: bold; }")
        queue_layout = QVBoxLayout(queue_group)
        queue_layout.setContentsMargins(8, 8, 8, 8)
        
        self.queue_label = QLabel("暂无任务")
        self.queue_label.setStyleSheet("font-size: 12px;")
        queue_layout.addWidget(self.queue_label)
        
        # 使用滚动区域包裹任务列表
        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setMinimumHeight(180)  # 提高到180像素
        self.queue_scroll.setStyleSheet("QScrollArea { background-color: #2d2d2d; border: none; }")
        
        self.queue_container = QWidget()
        self.queue_container_layout = QVBoxLayout(self.queue_container)
        self.queue_container_layout.setContentsMargins(4, 4, 4, 4)
        self.queue_container_layout.setSpacing(4)  # 减少间距
        self.queue_container_layout.addStretch()
        
        self.queue_scroll.setWidget(self.queue_container)
        queue_layout.addWidget(self.queue_scroll)
        
        # 取消当前任务按钮
        self.cancel_btn = QPushButton("取消当前任务")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_current)
        queue_layout.addWidget(self.cancel_btn)
        
        bottom_layout.addWidget(queue_group, 2)  # 占更多空间
        
        # 日志区域
        log_group = QGroupBox("运行日志")
        log_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("QTextEdit { background-color: #1e1e1e; color: #cccccc; font-family: Consolas; font-size: 12px; }")
        log_layout.addWidget(self.log_text)
        
        bottom_layout.addWidget(log_group, 1)
        
        layout.addLayout(bottom_layout)
        
        # 任务卡片列表
        self._task_widgets = {}  # task_id -> TaskItemWidget
        
        # 实时耗时更新定时器
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)  # 每秒更新
        self._elapsed_timer.timeout.connect(self._update_elapsed_times)
        self._elapsed_timer.start()
    
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
    
    def _update_duration(self):
        """更新时长显示"""
        frames = self.frames_spin.value()
        fps = self.fps_spin.value()
        if fps > 0:
            duration = frames / fps
            self.duration_label.setText(f"{duration:.1f}秒")
    
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
        fps = self.fps_spin.value()
        steps = self.steps_spin.value()
        seed = self.seed_spin.value()
        sage_attention = self.sage_attn_check.isChecked()
        enable_upscale = self.upscale_check.isChecked()
        
        # 确保worker对象存在
        self._ensure_worker_exists()
        
        # 添加任务
        task_id = self._worker.add_task(
            start_image=start_path,
            end_image=end_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            frames=frames,
            fps=fps,
            steps=steps,
            seed=seed,
            sage_attention=sage_attention,
            enable_upscale=enable_upscale
        )
        
        # 添加任务后再启动worker
        self._start_worker_if_needed()
        
        self._update_queue_list()
        self._log(f"任务 {task_id} 已添加到队列")
    
    def _ensure_worker_exists(self):
        """确保worker对象存在且可用"""
        # QThread停止后不能重复启动，需要创建新实例
        if self._worker is None or (not self._worker.isRunning() and self._worker.isFinished()):
            old_tasks = []
            if self._worker:
                # 断开旧worker的信号连接
                try:
                    self._worker.task_started.disconnect()
                    self._worker.task_progress.disconnect()
                    self._worker.task_completed.disconnect()
                    self._worker.task_failed.disconnect()
                    self._worker.queue_changed.disconnect()
                    self._worker.status_changed.disconnect()
                    self._worker.log_message.disconnect()
                except:
                    pass
                old_tasks = self._worker.get_all_tasks()
            
            self._worker = SmoothMixWorker()
            self._connect_worker_signals()
            
            # 恢复旧任务（如果有，使用task_id去重）
            existing_ids = {t.task_id for t in self._worker._tasks}
            for task in old_tasks:
                if task.task_id not in existing_ids:
                    self._worker._tasks.append(task)
                    existing_ids.add(task.task_id)
            self._worker._task_counter = max(
                self._worker._task_counter,
                max((t.task_id for t in self._worker._tasks), default=0)
            )
    
    def _connect_worker_signals(self):
        """连接worker信号"""
        # 使用 UniqueConnection 防止重复连接
        self._worker.task_started.connect(self._on_task_started, Qt.UniqueConnection)
        self._worker.task_progress.connect(self._on_task_progress, Qt.UniqueConnection)
        self._worker.task_completed.connect(self._on_task_completed, Qt.UniqueConnection)
        self._worker.task_failed.connect(self._on_task_failed, Qt.UniqueConnection)
        self._worker.queue_changed.connect(self._on_queue_changed, Qt.UniqueConnection)
        self._worker.status_changed.connect(self._on_status_changed, Qt.UniqueConnection)
        self._worker.log_message.connect(self._on_log_message, Qt.UniqueConnection)
    
    def _start_worker_if_needed(self):
        """如果worker没在运行且有pending任务，则启动"""
        if self._worker and not self._worker.isRunning():
            pending = [t for t in self._worker.get_all_tasks() if t.status == "pending"]
            if pending:
                self._worker.start()
    
    def _ensure_worker_running(self):
        """确保worker对象存在（用于初始化加载历史任务）"""
        self._ensure_worker_exists()
        # 初始化时不自动启动历史任务，等待用户手动添加新任务或点击继续
        # self._start_worker_if_needed()
    
    def _update_queue_list(self):
        """更新任务队列显示"""
        if not self._worker:
            return
        
        tasks = self._worker.get_all_tasks()
        running_count = 0
        pending_count = 0
        
        # 清理已不存在的任务Widget
        existing_ids = {t.task_id for t in tasks}
        for task_id in list(self._task_widgets.keys()):
            if task_id not in existing_ids:
                widget = self._task_widgets.pop(task_id)
                self.queue_container_layout.removeWidget(widget)
                widget.deleteLater()
        
        # 更新或创建任务Widget
        for task in tasks:
            # 移除状态过滤，显示所有任务
            if task.status == "running":
                running_count += 1
            elif task.status == "pending":
                pending_count += 1
            
            if task.task_id not in self._task_widgets:
                # 创建新的任务Widget
                widget = self._create_task_widget(task)
                self._task_widgets[task.task_id] = widget
                # 插入到stretch之前
                self.queue_container_layout.insertWidget(
                    self.queue_container_layout.count() - 1, widget
                )
            else:
                # 更新现有Widget（状态变化时更新按钮可见性）
                self._update_task_widget(task)
        
        # 更新标签
        total = running_count + pending_count + len([t for t in tasks if t.status in ("completed", "failed")])
        if running_count > 0:
            self.queue_label.setText(f"正在执行 1 个, 等待 {pending_count} 个, 共 {total} 个任务")
            self.cancel_btn.setVisible(True)
        elif pending_count > 0:
            self.queue_label.setText(f"{pending_count} 个任务等待中, 共 {total} 个任务")
            self.cancel_btn.setVisible(False)
        elif total > 0:
            self.queue_label.setText(f"共 {total} 个任务")
            self.cancel_btn.setVisible(False)
        else:
            self.queue_label.setText("暂无任务")
            self.cancel_btn.setVisible(False)
    
    def _create_task_widget(self, task) -> QFrame:
        """创建任务卡片Widget"""
        frame = QWidget()
        frame.setProperty("task_id", task.task_id)
        
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)
        
        # 任务信息
        info_label = QLabel(
            f"<b>#{task.task_id}</b> "
            f"{task.get_create_time_str()} "
            f"{self._get_status_text(task)} "
            f"{task.get_elapsed_time() or '--'} | "
            f"{(task.prompt[:40] + '...' if len(task.prompt) > 40 else task.prompt or '(无)')} | "
            f"{task.frames / task.fps:.1f}s"
        )
        info_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(info_label, 1)
        
        # 查看按钮
        view_btn = QPushButton("查看")
        view_btn.setFixedWidth(40)
        layout.addWidget(view_btn)  # 先添加
        if not (task.status == "completed" and task.output_path):
            view_btn.hide()  # 后隐藏
        # 使用闭包捕获task_id，避免信号参数问题
        task_id_for_view = task.task_id
        view_btn.clicked.connect(lambda _=None, tid=task_id_for_view: self._view_video(tid))
        
        # 删除按钮
        delete_btn = QPushButton("删除")
        delete_btn.setFixedWidth(40)
        layout.addWidget(delete_btn)  # 先添加
        if task.status == "running":
            delete_btn.hide()  # 后隐藏
        # 使用闭包捕获task_id，避免信号参数问题
        task_id_for_delete = task.task_id
        delete_btn.clicked.connect(lambda _=None, tid=task_id_for_delete: self._delete_task(tid))
        
        return frame
    
    def _update_task_widget(self, task):
        """更新任务卡片 - 重新创建整个widget以更新内容"""
        if task.task_id not in self._task_widgets:
            return
        
        # 先找到旧widget的位置
        old_widget = self._task_widgets[task.task_id]
        insert_index = -1
        for i in range(self.queue_container_layout.count() - 1):
            item = self.queue_container_layout.itemAt(i)
            if item.widget() == old_widget:
                insert_index = i
                break
        
        # 删除旧widget
        self.queue_container_layout.removeWidget(old_widget)
        old_widget.deleteLater()
        
        # 创建新widget
        new_widget = self._create_task_widget(task)
        self._task_widgets[task.task_id] = new_widget
        
        # 插入到原来的位置
        if insert_index >= 0:
            self.queue_container_layout.insertWidget(insert_index, new_widget)
        else:
            # 如果找不到位置，插入到stretch之前
            self.queue_container_layout.insertWidget(
                self.queue_container_layout.count() - 1, new_widget
            )
    
    def _get_status_text(self, task) -> str:
        status_map = {
            "pending": "等待中",
            "running": "执行中",
            "completed": "完成",
            "failed": "失败"
        }
        return status_map.get(task.status, task.status)
    
    def _get_status_style(self, task) -> str:
        style_map = {
            "pending": "color: #888;",
            "running": "color: #4fc3f7;",
            "completed": "color: #81c784;",
            "failed": "color: #e57373;"
        }
        return style_map.get(task.status, "")
    
    def _apply_task_style(self, frame: QFrame, task):
        # 暂时禁用样式测试弹框
        pass
        # bg_map = {
        #     "pending": "#2a2a2a",
        #     "running": "#1a3a4a",
        #     "completed": "#1a3a1a",
        #     "failed": "#3a1a1a"
        # }
        # bg = bg_map.get(task.status, "#2a2a2a")
        # frame.setStyleSheet(f"QWidget {{ background-color: {bg}; border-radius: 6px; }}")
    
    def _update_elapsed_times(self):
        """实时更新执行中任务的耗时"""
        if not self._worker:
            return
        
        for task in self._worker.get_all_tasks():
            if task.status == "running" and task.task_id in self._task_widgets:
                # 直接更新整个widget
                self._update_task_widget(task)
    
    def _view_video(self, task_id: int):
        """查看生成的视频"""
        if not self._worker:
            self._log(f"查看任务 {task_id}: worker不存在")
            return
        
        all_tasks = self._worker.get_all_tasks()
        self._log(f"查看任务 {task_id}, worker中有 {len(all_tasks)} 个任务")
        
        for task in all_tasks:
            if task.task_id == task_id:
                if task.output_path:
                    self._show_video_dialog(task)
                else:
                    self._log(f"任务 {task_id} 没有输出文件")
                return
        
        self._log(f"任务 {task_id} 不在worker任务列表中")
    
    def _show_video_dialog(self, task):
        """显示视频预览对话框"""
        from PySide6.QtMultimedia import QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"任务 {task.task_id} - 视频预览")
        dialog.setMinimumSize(640, 480)
        
        layout = QVBoxLayout(dialog)
        
        # 视频播放器
        video_widget = QVideoWidget()
        layout.addWidget(video_widget, 1)
        
        player = QMediaPlayer(dialog)
        player.setVideoOutput(video_widget)
        player.setSource(QUrl.fromLocalFile(task.output_path))
        
        # 手动循环播放
        def on_media_status(status):
            if status == QMediaPlayer.EndOfMedia:
                player.setPosition(0)
                player.play()
        player.mediaStatusChanged.connect(on_media_status)
        
        # 进度控制栏
        control_layout = QHBoxLayout()
        
        # 播放/暂停按钮
        play_btn = QPushButton()
        play_btn.setFixedSize(36, 36)
        play_btn.setIcon(dialog.style().standardIcon(QStyle.SP_MediaPause))
        
        def toggle_play():
            if player.playbackState() == QMediaPlayer.PlayingState:
                player.pause()
                play_btn.setIcon(dialog.style().standardIcon(QStyle.SP_MediaPlay))
            else:
                player.play()
                play_btn.setIcon(dialog.style().standardIcon(QStyle.SP_MediaPause))
        play_btn.clicked.connect(toggle_play)
        control_layout.addWidget(play_btn)
        
        # 进度滑块
        time_slider = QSlider(Qt.Horizontal)
        time_slider.setRange(0, 1000)
        slider_dragging = [False]
        
        def on_slider_moved(value):
            dur = player.duration()
            if dur > 0:
                pos = int((value / 1000) * dur)
                player.setPosition(pos)
        
        def on_slider_pressed():
            slider_dragging[0] = True
        
        def on_slider_released():
            slider_dragging[0] = False
        
        time_slider.sliderMoved.connect(on_slider_moved)
        time_slider.sliderPressed.connect(on_slider_pressed)
        time_slider.sliderReleased.connect(on_slider_released)
        control_layout.addWidget(time_slider, 1)
        
        # 时间标签
        time_label = QLabel("00:00.000 / 00:00.000")
        time_label.setStyleSheet("color: #888; font-size: 11px;")
        control_layout.addWidget(time_label)
        
        layout.addLayout(control_layout)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        import_btn = QPushButton("导入到帧处理")
        import_btn.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold; padding: 8px 16px;")
        import_btn.clicked.connect(lambda: self._import_video(task.output_path, dialog))
        btn_layout.addWidget(import_btn)
        layout.addLayout(btn_layout)
        
        # 信息标签
        duration = task.frames / task.fps if task.fps > 0 else 0
        info = (f"文件: {Path(task.output_path).name} | "
                f"帧率: {task.fps} fps | 总时长: {duration:.2f}秒 | 耗时: {task.get_elapsed_time()}")
        info_label = QLabel(info)
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info_label)
        
        # 格式化时间
        def format_time(ms):
            total_sec = ms / 1000
            mins = int(total_sec // 60)
            secs = total_sec % 60
            return f"{mins:02d}:{secs:06.3f}"
        
        # 记录上次位置，用于检测循环
        last_pos = [0]
        
        # 更新进度
        def update_position(pos):
            dur = player.duration()
            if dur > 0:
                # 检测循环：从末尾跳回开头
                if pos < last_pos[0] and last_pos[0] > dur * 0.9:
                    pos = 0  # 强制重置
                last_pos[0] = pos
                
                time_label.setText(f"{format_time(pos)} / {format_time(dur)}")
                if not slider_dragging[0]:
                    time_slider.blockSignals(True)
                    time_slider.setValue(int((pos / dur) * 1000))
                    time_slider.blockSignals(False)
        
        player.positionChanged.connect(update_position)
        
        player.play()
        dialog.exec()
        player.stop()
    
    def _import_video(self, video_path: str, dialog: QDialog):
        """导入视频到帧处理"""
        dialog.accept()
        self.video_generated.emit(video_path)
    
    def _clear_queue(self):
        if self._worker:
            self._worker.clear_queue()
            self._update_queue_list()
    
    def _cancel_current(self):
        if self._worker:
            self._worker.cancel_current()
    
    def _delete_task(self, task_id: int):
        """删除指定任务"""
        if not self._worker:
            self._log(f"删除任务 {task_id}: worker不存在")
            return
        
        all_tasks = self._worker.get_all_tasks()
        self._log(f"删除任务 {task_id}, worker中有 {len(all_tasks)} 个任务: {[t.task_id for t in all_tasks]}")
        
        if self._worker.delete_task(task_id):
            self._update_queue_list()
            QTimer.singleShot(100, lambda: QMessageBox.information(self, "删除成功", f"任务 {task_id} 已删除"))
        else:
            # 检查具体原因
            for task in all_tasks:
                if task.task_id == task_id:
                    if task.status == "running":
                        QMessageBox.warning(self, "无法删除", "正在执行的任务无法删除")
                    else:
                        QMessageBox.warning(self, "无法删除", f"任务状态: {task.status}")
                    return
            QMessageBox.warning(self, "无法删除", f"任务 {task_id} 不存在")
    
    @Slot(str)
    def _on_status_changed(self, status: str):
        self._log(status)
    
    @Slot(str)
    def _on_log_message(self, message: str):
        self._log(message)
    
    @Slot(int, str)
    def _on_task_started(self, task_id: int, message: str):
        self._update_queue_list()
    
    @Slot(int, int, int, str)
    def _on_task_progress(self, task_id: int, current: int, total: int, message: str):
        # 更新对应任务的进度条
        if task_id in self._task_widgets:
            frame = self._task_widgets[task_id]
            progress_bar = frame.findChild(QProgressBar, "progress_bar")
            if progress_bar:
                progress_bar.setMaximum(total)
                progress_bar.setValue(current)
    
    @Slot(int, str)
    def _on_task_completed(self, task_id: int, video_path: str):
        self._update_queue_list()
        # 不再弹框，用户可以通过查看按钮查看视频
    
    @Slot(int, str)
    def _on_task_failed(self, task_id: int, error: str):
        self._update_queue_list()
        # 失败时记录日志，不弹框
        self._log(f"任务 {task_id} 失败: {error}")
    
    @Slot(int)
    def _on_queue_changed(self, length: int):
        self._update_queue_list()
