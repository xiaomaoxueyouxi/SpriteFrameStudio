"""主窗口"""
from typing import Optional
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QGroupBox, QLabel, QDoubleSpinBox,
    QRadioButton, QButtonGroup, QPushButton, QSlider,
    QTabWidget, QProgressBar, QStatusBar, QFileDialog,
    QMessageBox, QComboBox, QCheckBox, QToolBar, QApplication,
    QScrollArea, QFrame, QGridLayout, QColorDialog, QSpinBox,
    QStackedWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer
from PySide6.QtGui import QAction, QColor, QPainter, QFont

from src.ui.widgets.video_player import VideoPlayer
from src.ui.widgets.frame_preview import FramePreview
from src.ui.widgets.frame_timeline import FrameTimeline
from src.ui.widgets.pose_viewer import PoseViewer
from src.ui.widgets.export_dialog import ExportDialog
from src.ui.widgets.animation_preview import AnimationPreview

from src.core.video_processor import VideoProcessor
from src.core.frame_manager import FrameManager
from src.core.background_remover import BackgroundRemover, BackgroundMode
from src.core.pose_detector import PoseDetector
from src.core.exporter import Exporter

from src.workers.extraction_worker import ExtractionWorker
from src.workers.background_worker import BackgroundWorker
from src.workers.pose_worker import PoseWorker

from src.models.frame_data import VideoInfo
from src.utils.config import config


class VerticalTabButton(QPushButton):
    """垂直文字Tab按钮"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedWidth(50)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        
    def paintEvent(self, event):
        """重绘以显示垂直文字（逐字竖排）"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 背景
        if self.isChecked():
            painter.fillRect(self.rect(), QColor("#0078d4"))
        elif self.underMouse():
            painter.fillRect(self.rect(), QColor("#2d2d2d"))
        else:
            painter.fillRect(self.rect(), QColor("#1e1e1e"))
        
        # 文字（竖排，逐字绘制）
        painter.setPen(QColor("#ffffff") if self.isChecked() else QColor("#aaaaaa"))
        font = QFont("Microsoft YaHei", 11)
        painter.setFont(font)
        
        # 逐字竖排显示
        text = self.text()
        font_metrics = painter.fontMetrics()
        char_height = font_metrics.height()
        
        # 计算总高度
        total_height = char_height * len(text)
        
        # 起始Y位置（居中）
        start_y = (self.height() - total_height) / 2 + char_height
        
        # 逐字绘制
        x = self.width() / 2
        for i, char in enumerate(text):
            char_width = font_metrics.horizontalAdvance(char)
            y = start_y + i * char_height
            painter.drawText(int(x - char_width / 2), int(y), char)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 核心组件
        self._video_processor = VideoProcessor()
        self._frame_manager = FrameManager()
        self._background_remover = BackgroundRemover()
        self._pose_detector = PoseDetector()
        self._exporter = Exporter()
        
        # 工作线程
        self._extraction_worker: Optional[ExtractionWorker] = None
        self._background_worker: Optional[BackgroundWorker] = None
        self._pose_worker: Optional[PoseWorker] = None
        
        # 状态
        self._video_info: Optional[VideoInfo] = None
        self._scale_aspect_ratio = 1.0  # 缩放宽高比
        self._updating_scale_size = False  # 防止递归更新
        
        # 垂直Tab按钮列表
        self.tab_buttons = []
        
        self.setup_ui()
        self.setup_connections()
        
        # 性能监控定时器
        self.performance_timer = QTimer(self)
        self.performance_timer.timeout.connect(self.update_performance_stats)
        self.performance_timer.start(1000)  # 每秒更新一次
    
    def _apply_flow_btn_style(self, button: QPushButton):
        """为主要操作按钮应用统一样式"""
        # 主要操作按钮使用sidebar的统一样式，不单独设置
        pass
    
    def setup_ui(self):
        self.setWindowTitle("视频帧提取工具")
        self.setMinimumSize(1200, 800)
        
        # 中央组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ===== 左侧：垂直Tab栏 =====
        self.vertical_tab_bar = QWidget()
        self.vertical_tab_bar.setObjectName("vertical_tab_bar")
        self.vertical_tab_bar.setFixedWidth(50)
        self.vertical_tab_bar.setStyleSheet("""
            QWidget#vertical_tab_bar {
                background-color: #1e1e1e;
                border-right: 1px solid #333333;
            }
        """)
        
        tab_bar_layout = QVBoxLayout(self.vertical_tab_bar)
        tab_bar_layout.setContentsMargins(0, 0, 0, 0)
        tab_bar_layout.setSpacing(0)
        
        # 创建垂直Tab按钮
        tab_names = ["准备视频", "动作分析", "批量缩放", "背景处理", "边缘优化", "描边", "空白裁剪", "导出"]
        
        # 创建按钮组实现互斥选择
        self.tab_button_group = QButtonGroup()
        self.tab_button_group.setExclusive(True)
        
        for i, name in enumerate(tab_names):
            btn = VerticalTabButton(name)
            btn.setAutoExclusive(False)  # 关闭自动互斥，使用按钮组管理
            self.tab_button_group.addButton(btn, i)
            self.tab_buttons.append(btn)
            tab_bar_layout.addWidget(btn)
        
        # 连接按钮组信号
        self.tab_button_group.buttonClicked.connect(self._on_vertical_tab_button_clicked)
        
        # 第一个按钮默认选中
        if self.tab_buttons:
            self.tab_buttons[0].setChecked(True)
        
        tab_bar_layout.addStretch()
        main_layout.addWidget(self.vertical_tab_bar)
        
        # ===== 中间：操作面板 =====
        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("sidebar")
        self.sidebar_widget.setFixedWidth(360)
        # 不设置自定义样式，使用Qt默认样式（与导出设置对话框一致）
        
        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(10)
        
        # 使用StackedWidget管理不同页面
        self.page_stack = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用横向滚动条
        scroll.setWidget(self.page_stack)
        
        sidebar_layout.addWidget(scroll)
        main_layout.addWidget(self.sidebar_widget)
        
        # 创建各个页面
        self._create_pages()
        
        # ===== 右侧：工作区 =====
        center_panel = self._create_center_panel()
        main_layout.addWidget(center_panel, 1)
        
        # 状态栏
        self._create_statusbar()
    
    def _on_vertical_tab_button_clicked(self, button):
        """垂直Tab按钮点击事件"""
        # 获取按钮索引
        index = self.tab_button_group.id(button)
        
        # 切换页面
        self.page_stack.setCurrentIndex(index)
    
    def _create_pages(self):
        """创建各个操作页面"""
        # 页面0: 准备视频
        page0 = self._create_video_page()
        self.page_stack.addWidget(page0)
        
        # 页面1: 动作分析
        page1 = self._create_pose_page()
        self.page_stack.addWidget(page1)
        
        # 页面2: 批量缩放
        page2 = self._create_scale_page()
        self.page_stack.addWidget(page2)
        
        # 页面3: 背景处理
        page3 = self._create_background_page()
        self.page_stack.addWidget(page3)
        
        # 页面4: 边缘优化
        page4 = self._create_edge_page()
        self.page_stack.addWidget(page4)
        
        # 页面5: 描边
        page5 = self._create_outline_page()
        self.page_stack.addWidget(page5)
        
        # 页面6: 空白裁剪
        page6 = self._create_crop_page()
        self.page_stack.addWidget(page6)
        
        # 页面7: 导出
        page7 = self._create_export_page()
        self.page_stack.addWidget(page7)
    
    def _create_video_page(self) -> QWidget:
        """创建准备视频页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # 打开视频
        self.open_btn = QPushButton("📁 打开本地视频")
        self.open_btn.clicked.connect(self.open_video)
        
        # 居中对齐按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.open_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.video_path_label = QLabel("未加载")
        self.video_path_label.setWordWrap(True)
        layout.addWidget(self.video_path_label)
        
        self.video_info_label = QLabel("")
        layout.addWidget(self.video_info_label)
        
        # 抽帧设置
        fps_group = QGroupBox("抽帧设置")
        fps_layout = QVBoxLayout(fps_group)
        
        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("🎬 帧率:"))
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(0.1, 60)
        self.fps_spin.setValue(config.extract_fps)
        self.fps_spin.setSuffix(" fps")
        fps_row.addWidget(self.fps_spin)
        fps_layout.addLayout(fps_row)
        
        self.timeline = FrameTimeline()
        fps_layout.addWidget(self.timeline)

        self.range_play_check = QCheckBox("播放区间")
        self.range_play_check.setChecked(False)
        fps_layout.addWidget(self.range_play_check)
        
        self.estimate_label = QLabel("预计: 0 帧")
        fps_layout.addWidget(self.estimate_label)
        
        layout.addWidget(fps_group)
        
        self.extract_btn = QPushButton("✂️ 开始抽帧")
        self.extract_btn.setEnabled(False)
        self.extract_btn.clicked.connect(self.extract_frames)
        
        # 居中对齐按钮
        extract_btn_layout = QHBoxLayout()
        extract_btn_layout.addStretch()
        extract_btn_layout.addWidget(self.extract_btn)
        extract_btn_layout.addStretch()
        layout.addLayout(extract_btn_layout)
        
        layout.addStretch()
        
        return page
    
    def _create_scale_page(self) -> QWidget:
        """创建批量缩放页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # 批量缩放
        scale_group = QGroupBox("批量缩放")
        scale_layout = QVBoxLayout(scale_group)
        
        hint = QLabel("先缩小图片再抠图，速度可提升10倍+")
        scale_layout.addWidget(hint)
        
        mode_layout = QHBoxLayout()
        self.scale_percent_radio = QRadioButton("比例缩放")
        self.scale_percent_radio.setChecked(True)
        self.scale_percent_radio.toggled.connect(self._on_scale_mode_changed)
        mode_layout.addWidget(self.scale_percent_radio)
        self.scale_fixed_radio = QRadioButton("固定尺寸")
        mode_layout.addWidget(self.scale_fixed_radio)
        scale_layout.addLayout(mode_layout)
        
        # 比例缩放
        self.scale_percent_widget = QWidget()
        percent_layout = QHBoxLayout(self.scale_percent_widget)
        percent_layout.setContentsMargins(0, 0, 0, 0)
        percent_layout.addWidget(QLabel("缩放比例:"))
        self.scale_percent_spin = QSpinBox()
        self.scale_percent_spin.setRange(10, 200)
        self.scale_percent_spin.setValue(50)
        self.scale_percent_spin.setSuffix("%")
        percent_layout.addWidget(self.scale_percent_spin)
        percent_layout.addStretch()
        scale_layout.addWidget(self.scale_percent_widget)
        
        # 固定尺寸
        self.scale_fixed_widget = QWidget()
        self.scale_fixed_widget.setVisible(False)
        fixed_layout = QVBoxLayout(self.scale_fixed_widget)
        fixed_layout.setContentsMargins(0, 0, 0, 0)
        
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("宽:"))
        self.scale_width_spin = QSpinBox()
        self.scale_width_spin.setRange(1, 4096)
        self.scale_width_spin.setValue(512)
        self.scale_width_spin.valueChanged.connect(self._on_scale_width_changed)
        size_row.addWidget(self.scale_width_spin)
        size_row.addWidget(QLabel("高:"))
        self.scale_height_spin = QSpinBox()
        self.scale_height_spin.setRange(1, 4096)
        self.scale_height_spin.setValue(512)
        self.scale_height_spin.valueChanged.connect(self._on_scale_height_changed)
        size_row.addWidget(self.scale_height_spin)
        self.scale_lock_ratio_check = QCheckBox("🔒锁定比例")
        self.scale_lock_ratio_check.setChecked(True)
        size_row.addWidget(self.scale_lock_ratio_check)
        size_row.addStretch()
        fixed_layout.addLayout(size_row)
        scale_layout.addWidget(self.scale_fixed_widget)
        
        # 算法
        algo_row = QHBoxLayout()
        algo_row.addWidget(QLabel("算法:"))
        self.scale_algorithm_combo = QComboBox()
        self.scale_algorithm_combo.addItem("📍 最近邻", "nearest")
        self.scale_algorithm_combo.addItem("🌀 双线性", "bilinear")
        self.scale_algorithm_combo.addItem("✨ 双三次", "bicubic")
        self.scale_algorithm_combo.addItem("🌟 Lanczos", "lanczos")
        self.scale_algorithm_combo.setCurrentIndex(3)
        algo_row.addWidget(self.scale_algorithm_combo, 1)
        scale_layout.addLayout(algo_row)
        
        self.scale_frames_btn = QPushButton("🔍 批量缩放")
        self.scale_frames_btn.setEnabled(False)
        self.scale_frames_btn.clicked.connect(self._scale_frames)
        
        # 居中对齐
        scale_btn_layout = QHBoxLayout()
        scale_btn_layout.addStretch()
        scale_btn_layout.addWidget(self.scale_frames_btn)
        scale_btn_layout.addStretch()
        scale_layout.addLayout(scale_btn_layout)
        
        layout.addWidget(scale_group)
        layout.addStretch()
        
        return page
    
    def _create_pose_page(self) -> QWidget:
        """创建动作分析页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        group = QGroupBox("动作分析")
        group_layout = QVBoxLayout(group)
        
        self.detect_mode_combo = QComboBox()
        self.detect_mode_combo.addItem("🤖 姿势检测 (RTMPose)", "pose_rtm")
        self.detect_mode_combo.addItem("🦶 分区域SSIM", "regional")
        # MediaPipe 姿势检测效果不好，已移除
        # self.detect_mode_combo.addItem("👤 姿势检测", "pose")
        self.detect_mode_combo.addItem("🌀 轮廓匹配", "contour")
        self.detect_mode_combo.addItem("🖼️ 图像相似度", "image")
        group_layout.addWidget(self.detect_mode_combo)
        
        self.pose_btn = QPushButton("🔍 分析特征/姿势")
        self.pose_btn.setEnabled(False)
        self.pose_btn.clicked.connect(self.detect_pose)
        
        # 居中对齐
        pose_btn_layout = QHBoxLayout()
        pose_btn_layout.addStretch()
        pose_btn_layout.addWidget(self.pose_btn)
        pose_btn_layout.addStretch()
        group_layout.addLayout(pose_btn_layout)
        
        tools_layout = QHBoxLayout()
        self.remove_similar_btn = QPushButton("🗑️去除相似")
        self.remove_similar_btn.clicked.connect(self._remove_similar_frames)
        tools_layout.addWidget(self.remove_similar_btn)
        
        self.find_loop_btn = QPushButton("➰寻找循环")
        self.find_loop_btn.clicked.connect(self._find_loop_frame)
        tools_layout.addWidget(self.find_loop_btn)
        group_layout.addLayout(tools_layout)
        
        # 相似度阈值
        sim_row = QHBoxLayout()
        sim_row.addWidget(QLabel("相似度阈值:"))
        self.similarity_spin = QSpinBox()
        self.similarity_spin.setRange(50, 99)
        self.similarity_spin.setValue(90)  # 默认90%
        self.similarity_spin.setSuffix("%")
        sim_row.addWidget(self.similarity_spin)
        sim_row.addStretch()
        group_layout.addLayout(sim_row)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return page
    
    def _create_background_page(self) -> QWidget:
        """创建背景处理页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        group = QGroupBox("背景处理")
        group_layout = QVBoxLayout(group)
        
        # 颜色过滤模式
        self.color_mode_radio = QRadioButton("🎨 颜色过滤")
        self.color_mode_radio.setChecked(False)  # 默认不选中
        self.color_mode_radio.toggled.connect(self._on_color_mode_toggled)
        group_layout.addWidget(self.color_mode_radio)
        
        preset_row = QHBoxLayout()
        preset_row.addSpacing(20)
        preset_row.addWidget(QLabel("预设:"))
        self.color_preset_combo = QComboBox()
        self.color_preset_combo.addItems(["绿幕", "蓝幕", "白色背景", "黑色背景", "自定义"])
        self.color_preset_combo.currentTextChanged.connect(self._on_color_preset_changed)
        preset_row.addWidget(self.color_preset_combo)
        group_layout.addLayout(preset_row)
        
        # 颜色通用参数
        self.color_common_widget = QWidget()
        cc_layout = QVBoxLayout(self.color_common_widget)
        cc_layout.setContentsMargins(20, 5, 0, 5)
        cc_layout.setSpacing(8)
        
        # 羽化
        feather_row = QHBoxLayout()
        feather_row.addWidget(QLabel("羽化:"))
        self.color_feather_spin = QSpinBox()
        self.color_feather_spin.setRange(0, 20)
        self.color_feather_spin.setValue(0)
        feather_row.addWidget(self.color_feather_spin)
        feather_row.addStretch()
        cc_layout.addLayout(feather_row)
        
        # 去噪
        denoise_row = QHBoxLayout()
        denoise_row.addWidget(QLabel("去噪:"))
        self.denoise_spin = QSpinBox()
        self.denoise_spin.setRange(0, 10)
        self.denoise_spin.setValue(1)
        denoise_row.addWidget(self.denoise_spin)
        denoise_row.addStretch()
        cc_layout.addLayout(denoise_row)
        
        group_layout.addWidget(self.color_common_widget)
        
        # 颜色自定义参数
        self.color_params_widget = QWidget()
        self.color_params_widget.setVisible(False)
        cp_layout = QVBoxLayout(self.color_params_widget)
        cp_layout.setContentsMargins(20, 5, 0, 5)
        cp_layout.setSpacing(8)
        
        # H范围
        h_row = QHBoxLayout()
        h_row.addWidget(QLabel("H:"))
        self.h_min_spin = QSpinBox()
        self.h_min_spin.setRange(0, 255)
        self.h_min_spin.setValue(35)
        h_row.addWidget(self.h_min_spin)
        h_row.addWidget(QLabel("-"))
        self.h_max_spin = QSpinBox()
        self.h_max_spin.setRange(0, 255)
        self.h_max_spin.setValue(85)
        h_row.addWidget(self.h_max_spin)
        h_row.addStretch()
        cp_layout.addLayout(h_row)
        
        # S范围
        s_row = QHBoxLayout()
        s_row.addWidget(QLabel("S:"))
        self.s_min_spin = QSpinBox()
        self.s_min_spin.setRange(0, 255)
        self.s_min_spin.setValue(50)
        s_row.addWidget(self.s_min_spin)
        s_row.addWidget(QLabel("-"))
        self.s_max_spin = QSpinBox()
        self.s_max_spin.setRange(0, 255)
        self.s_max_spin.setValue(255)
        s_row.addWidget(self.s_max_spin)
        s_row.addStretch()
        cp_layout.addLayout(s_row)
        
        # V范围
        v_row = QHBoxLayout()
        v_row.addWidget(QLabel("V:"))
        self.v_min_spin = QSpinBox()
        self.v_min_spin.setRange(0, 255)
        self.v_min_spin.setValue(50)
        v_row.addWidget(self.v_min_spin)
        v_row.addWidget(QLabel("-"))
        self.v_max_spin = QSpinBox()
        self.v_max_spin.setRange(0, 255)
        self.v_max_spin.setValue(255)
        v_row.addWidget(self.v_max_spin)
        v_row.addStretch()
        cp_layout.addLayout(v_row)
        
        # 溢色
        spill_row = QHBoxLayout()
        spill_row.addWidget(QLabel("溢色:"))
        self.spill_spin = QSpinBox()
        self.spill_spin.setRange(0, 100)
        self.spill_spin.setValue(0)
        spill_row.addWidget(self.spill_spin)
        spill_row.addStretch()
        cp_layout.addLayout(spill_row)
        
        group_layout.addWidget(self.color_params_widget)
        
        # AI模式
        self.ai_mode_radio = QRadioButton("✨ AI智能抠图")
        self.ai_mode_radio.setChecked(True)  # 默认选中AI模式
        self.ai_mode_radio.toggled.connect(self._on_ai_mode_toggled)
        group_layout.addWidget(self.ai_mode_radio)
        
        ai_model_row = QHBoxLayout()
        ai_model_row.addSpacing(20)
        ai_model_row.addWidget(QLabel("模型:"))
        self.ai_model_combo = QComboBox()
        self._update_model_list()
        ai_model_row.addWidget(self.ai_model_combo)
        group_layout.addLayout(ai_model_row)
        
        device_row = QHBoxLayout()
        device_row.addSpacing(20)
        device_row.addWidget(QLabel("设备:"))
        self.device_combo = QComboBox()
        self.device_combo.addItem("💻 CPU", "cpu")
        self.device_combo.addItem("🚀 GPU", "gpu")
        device_row.addWidget(self.device_combo)
        group_layout.addLayout(device_row)
        
        self.ai_params_widget = QWidget()
        self.ai_params_widget.setVisible(False)
        
        # 测试按钮
        self.test_bg_btn = QPushButton("👁 预览单帧")
        self.test_bg_btn.setEnabled(False)
        self.test_bg_btn.clicked.connect(self._test_background_removal)
        group_layout.addWidget(self.test_bg_btn)
        
        self.remove_bg_btn = QPushButton("🚀 批量去背景")
        self.remove_bg_btn.setEnabled(False)
        self.remove_bg_btn.clicked.connect(self.remove_background)
        
        # 居中对齐
        bg_btn_layout = QHBoxLayout()
        bg_btn_layout.addStretch()
        bg_btn_layout.addWidget(self.remove_bg_btn)
        bg_btn_layout.addStretch()
        group_layout.addLayout(bg_btn_layout)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return page
    
    def _create_edge_page(self) -> QWidget:
        """创建边缘优化页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        group = QGroupBox("边缘优化")
        group_layout = QVBoxLayout(group)
        
        hint = QLabel("对抠图后的帧进行边缘收缩处理")
        group_layout.addWidget(hint)
        
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("边缘收缩:"))
        self.edge_erode_spin = QSpinBox()
        self.edge_erode_spin.setRange(0, 10)
        self.edge_erode_spin.setValue(0)
        self.edge_erode_spin.setSuffix(" px")
        params_layout.addWidget(self.edge_erode_spin)
        params_layout.addStretch()
        group_layout.addLayout(params_layout)
        
        self.edge_optimize_btn = QPushButton("✂️ 批量收缩边缘")
        self.edge_optimize_btn.setEnabled(False)
        self.edge_optimize_btn.clicked.connect(self._optimize_edges)
        
        # 居中对齐
        edge_btn_layout = QHBoxLayout()
        edge_btn_layout.addStretch()
        edge_btn_layout.addWidget(self.edge_optimize_btn)
        edge_btn_layout.addStretch()
        group_layout.addLayout(edge_btn_layout)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return page
    
    def _create_outline_page(self) -> QWidget:
        """创建描边页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        group = QGroupBox("描边")
        group_layout = QVBoxLayout(group)
        
        hint = QLabel("给所有帧添加轮廓描边")
        group_layout.addWidget(hint)
        
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("描边宽度:"))
        self.outline_spin = QSpinBox()
        self.outline_spin.setRange(0, 20)
        self.outline_spin.setValue(0)
        params_layout.addWidget(self.outline_spin)
        
        self.outline_color_btn = QPushButton("颜色")
        self.outline_color_btn.setMaximumWidth(60)
        self.outline_color = QColor(0, 0, 0)
        self._update_outline_color_btn_style()
        self.outline_color_btn.clicked.connect(self._choose_outline_color)
        params_layout.addWidget(self.outline_color_btn)
        group_layout.addLayout(params_layout)
        
        self.add_outline_btn = QPushButton("🖍️ 批量添加描边")
        self.add_outline_btn.setEnabled(False)
        self.add_outline_btn.clicked.connect(self.add_outline_to_frames)
        
        # 居中对齐
        outline_btn_layout = QHBoxLayout()
        outline_btn_layout.addStretch()
        outline_btn_layout.addWidget(self.add_outline_btn)
        outline_btn_layout.addStretch()
        group_layout.addLayout(outline_btn_layout)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return page
    
    def _create_crop_page(self) -> QWidget:
        """创建空白裁剪页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        group = QGroupBox("空白裁剪")
        group_layout = QVBoxLayout(group)
        
        hint = QLabel("去除所有帧的多余空白区域")
        group_layout.addWidget(hint)
        
        margin_group = QGroupBox("预留边距")
        margin_layout = QGridLayout(margin_group)
        
        margin_layout.addWidget(QLabel("上:"), 0, 0)
        self.crop_margin_top = QSpinBox()
        self.crop_margin_top.setRange(0, 500)
        self.crop_margin_top.setValue(0)
        self.crop_margin_top.setSuffix(" px")
        margin_layout.addWidget(self.crop_margin_top, 0, 1)
        
        margin_layout.addWidget(QLabel("下:"), 0, 2)
        self.crop_margin_bottom = QSpinBox()
        self.crop_margin_bottom.setRange(0, 500)
        self.crop_margin_bottom.setValue(0)
        self.crop_margin_bottom.setSuffix(" px")
        margin_layout.addWidget(self.crop_margin_bottom, 0, 3)
        
        margin_layout.addWidget(QLabel("左:"), 1, 0)
        self.crop_margin_left = QSpinBox()
        self.crop_margin_left.setRange(0, 500)
        self.crop_margin_left.setValue(0)
        self.crop_margin_left.setSuffix(" px")
        margin_layout.addWidget(self.crop_margin_left, 1, 1)
        
        margin_layout.addWidget(QLabel("右:"), 1, 2)
        self.crop_margin_right = QSpinBox()
        self.crop_margin_right.setRange(0, 500)
        self.crop_margin_right.setValue(0)
        self.crop_margin_right.setSuffix(" px")
        margin_layout.addWidget(self.crop_margin_right, 1, 3)
        
        group_layout.addWidget(margin_group)
        
        self.crop_btn = QPushButton("✂️ 裁剪空白区域")
        self.crop_btn.setEnabled(False)
        self.crop_btn.clicked.connect(self.crop_whitespace)
        
        # 居中对齐
        crop_btn_layout = QHBoxLayout()
        crop_btn_layout.addStretch()
        crop_btn_layout.addWidget(self.crop_btn)
        crop_btn_layout.addStretch()
        group_layout.addLayout(crop_btn_layout)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return page
    
    def _create_export_page(self) -> QWidget:
        """创建导出页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        group = QGroupBox("导出成果")
        group_layout = QVBoxLayout(group)
        
        self.export_btn = QPushButton("📤 导出图片序列")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_frames)
        
        # 居中对齐
        export_btn_layout = QHBoxLayout()
        export_btn_layout.addStretch()
        export_btn_layout.addWidget(self.export_btn)
        export_btn_layout.addStretch()
        group_layout.addLayout(export_btn_layout)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return page
    
    def _create_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Tab页
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # 视频预览Tab
        video_tab = QWidget()
        video_layout = QVBoxLayout(video_tab)
        self.video_player = VideoPlayer()
        video_layout.addWidget(self.video_player)
        self.tab_widget.addTab(video_tab, "视频预览")
        
        # 帧管理Tab
        frame_tab = QWidget()
        frame_layout = QVBoxLayout(frame_tab)
        self.frame_preview = FramePreview(thumbnail_size=120, columns=5)
        frame_layout.addWidget(self.frame_preview)
        self.tab_widget.addTab(frame_tab, "帧管理")
        
        # 姿势分析Tab
        pose_tab = QWidget()
        pose_layout = QVBoxLayout(pose_tab)
        self.pose_viewer = PoseViewer()
        pose_layout.addWidget(self.pose_viewer)
        self.tab_widget.addTab(pose_tab, "姿势分析")
        
        # 动画预览Tab
        anim_tab = QWidget()
        anim_layout = QVBoxLayout(anim_tab)
        self.animation_preview = AnimationPreview()
        anim_layout.addWidget(self.animation_preview)
        
        self.tab_widget.addTab(anim_tab, "动画预览")
        
        return panel
    
    def _create_statusbar(self):
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)
        
        # 设置状态栏内边距，特别是右边距
        statusbar.setContentsMargins(5, 0, 15, 0)  # 左、上、右、下
        
        self.status_label = QLabel("就绪")
        statusbar.addWidget(self.status_label)
        
        # 性能监控标签
        self.performance_label = QLabel("性能: 就绪")
        self.performance_label.setStyleSheet("color: #666;")
        statusbar.addWidget(self.performance_label)
        
        self.frame_count_label = QLabel("帧数: 0")
        statusbar.addPermanentWidget(self.frame_count_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        statusbar.addPermanentWidget(self.progress_bar)
    
    def update_performance_stats(self):
        """更新性能统计信息"""
        if hasattr(self.video_player, 'get_performance_stats'):
            stats = self.video_player.get_performance_stats()
            avg_time = stats['average_frame_display_time'] * 1000  # 转换为毫秒
            hit_rate = stats['cache_hit_rate']
            
            self.performance_label.setText(
                f"性能: 帧显示 {avg_time:.1f}ms, 缓存命中率 {hit_rate:.1f}%"
            )
    
    def reset_performance_stats(self):
        """重置性能统计信息"""
        if hasattr(self.video_player, 'reset_performance_stats'):
            self.video_player.reset_performance_stats()
            self.performance_label.setText("性能: 就绪")
    
    def setup_connections(self):
        # 时间轴变化
        self.timeline.range_changed.connect(self._on_time_range_changed)
        self.timeline.seek_requested.connect(self.video_player.seek)
        self.video_player.position_changed.connect(self.timeline.set_current_position)
        self.range_play_check.toggled.connect(self._on_range_play_toggled)
        self.fps_spin.valueChanged.connect(self._on_fps_changed)
        
        # 帧选择
        self.frame_preview.frame_clicked.connect(self._on_frame_clicked)
        self.frame_preview.selection_changed.connect(self._on_selection_changed)
        self.frame_preview.status_message.connect(self.status_label.setText)
        self.frame_preview.export_single_frame.connect(self.export_single_frame)
        
        # Tab切换
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
    
    # ============ 槽函数 ============
    
    @Slot()
    def open_video(self):
        """打开视频文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件",
            config.last_video_dir,
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.webm);;所有文件 (*.*)"
        )
        
        if not path:
            return
        
        # 保存目录
        config.last_video_dir = str(Path(path).parent)
        
        # 加载视频
        self._video_info = self.video_player.load_video(path)
        
        if self._video_info:
            # 更新UI
            filename = Path(path).name
            # 如果文件名过长，截断显示
            if len(filename) > 40:
                # 保留前20个字符和后15个字符（含扩展名）
                name_part = filename[:20]
                ext_part = filename[-15:]
                display_name = f"{name_part}...{ext_part}"
            else:
                display_name = filename
            self.video_path_label.setText(display_name)
            self.video_path_label.setToolTip(filename)  # 鼠标悬停显示完整文件名
            self.video_info_label.setText(
                f"分辨率: {self._video_info.resolution}\n"
                f"帧率: {self._video_info.fps:.2f} fps\n"
                f"时长: {self._video_info.format_duration()}"
            )
            
            # 设置时间轴
            self.timeline.set_duration(self._video_info.duration)
            self.timeline.set_fps(self._video_info.fps)
            self.video_player.set_playback_range(*self.timeline.get_range())
            self.video_player.set_range_playback_enabled(self.range_play_check.isChecked())
            
            # 启用功能
            self.extract_btn.setEnabled(True)
            
            # 清空旧数据，重置所有状态
            self._frame_manager.clear()
            self.frame_preview.clear()
            
            # 重置所有按钮状态
            self.test_bg_btn.setEnabled(False)
            self.remove_bg_btn.setEnabled(False)
            self.edge_optimize_btn.setEnabled(False)  # 边缘优化按钮
            self.pose_btn.setEnabled(False)
            self.add_outline_btn.setEnabled(False)
            self.crop_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            
            # 重置描边参数（通用描边）
            self.outline_spin.setValue(0)
            
            # 切换到视频预览Tab
            self.tab_widget.setCurrentIndex(0)
            
            self._update_estimate()
            self.status_label.setText("视频加载成功")
        else:
            QMessageBox.warning(self, "错误", "无法加载视频文件")
    
    @Slot()
    def extract_frames(self):
        """提取帧"""
        if not self._video_info:
            return
        
        start_time, end_time = self.timeline.get_range()
        fps = self.fps_spin.value()
        
        # 创建工作线程
        self._extraction_worker = ExtractionWorker(
            video_path=str(self._video_info.path),
            start_time=start_time,
            end_time=end_time,
            extract_fps=fps,
            video_info=self._video_info
        )
        
        self._extraction_worker.progress.connect(self._on_extraction_progress)
        self._extraction_worker.finished.connect(self._on_extraction_finished)
        self._extraction_worker.error.connect(self._on_extraction_error)
        
        # 开始提取
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.extract_btn.setEnabled(False)
        self.status_label.setText("正在提取帧...")
        
        self._extraction_worker.start()
    
    @Slot()
    def remove_background(self):
        """去除背景（可重复抠图）"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "请先选择要处理的帧")
            return
        
        # 检查是否有已处理的帧
        has_processed = any(self._frame_manager.get_frame(idx).has_processed for idx in selected_indices)
        use_original = True  # 默认使用原始图像
        
        # 如果有已处理的帧，让用户选择抠图源
        if has_processed:
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QDialogButtonBox, QLabel
            
            dialog = QDialog(self)
            dialog.setWindowTitle("选择抠图源")
            dialog.setMinimumWidth(400)
            
            layout = QVBoxLayout(dialog)
            
            # 说明
            info_label = QLabel(
                f"选中的 {len(selected_indices)} 帧中有已处理的帧\n\n"
                "请选择要使用的图像源进行抠图："
            )
            info_label.setWordWrap(True)
            layout.addWidget(info_label)
            
            # 选项
            original_radio = QRadioButton(
                "🎞️ 使用原始图像\n"
                "   • 从视频抽取的原始帧\n"
                "   • 会覆盖之前所有处理（抠图、描边、裁剪等）\n"
                "   • 适合：想重新开始处理"
            )
            layout.addWidget(original_radio)
            
            processed_radio = QRadioButton(
                "✨ 使用已处理图像\n"
                "   • 在当前处理结果基础上再次抠图\n"
                "   • 保留之前的描边、裁剪等效果\n"
                "   • 适合：二次精修，去除残留背景"
            )
            processed_radio.setChecked(True)  # 默认选择已处理图像
            layout.addWidget(processed_radio)
            
            # 按钮
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec() != QDialog.Accepted:
                return
            
            use_original = original_radio.isChecked()
        
        # 获取选中帧的图像（根据用户选择）
        frames = []
        for idx in selected_indices:
            frame = self._frame_manager.get_frame(idx)
            if use_original:
                # 使用原始图像
                if frame and frame.image is not None:
                    frames.append((frame.index, frame.image))
            else:
                # 使用已处理图像（display_image包含所有处理：缩放、抠图、描边等）
                if frame and frame.display_image is not None:
                    frames.append((frame.index, frame.display_image))
        
        if not frames:
            source_text = "原始图像" if use_original else "处理后图像"
            QMessageBox.warning(self, "错误", f"所选帧没有{source_text}\n\n"
                              "请确保已正确抽帧，并且帧数据完整")
            return
        
        # 确定模式
        mode = BackgroundMode.AI if self.ai_mode_radio.isChecked() else BackgroundMode.COLOR
        
        color_params = None
        ai_params = None
        
        if mode == BackgroundMode.COLOR:
            color_params = self._get_color_params()
        else:
            ai_params = self._get_ai_params()
        
        # 创建工作线程
        self._background_worker = BackgroundWorker(
            frames=frames,
            mode=mode,
            color_params=color_params,
            ai_params=ai_params
        )
        
        self._background_worker.progress.connect(self._on_bg_progress)
        self._background_worker.frame_processed.connect(self._on_frame_processed)
        self._background_worker.status_changed.connect(self._on_bg_status)
        self._background_worker.finished.connect(self._on_bg_finished)
        self._background_worker.error.connect(self._on_bg_error)
        
        # 开始处理
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.remove_bg_btn.setEnabled(False)
        
        source_text = "原始图" if use_original else "已处理图"
        self.status_label.setText(f"正在去除背景（源：{source_text}）...")
        
        self._background_worker.start()
    
    @Slot()
    def detect_pose(self):
        """检测姿势/轮廓"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "请先选择要检测的帧")
            return
        
        # 获取检测模式
        detect_mode = self.detect_mode_combo.currentData()
        
        # 获取选中帧的图像
        frames = []
        for idx in selected_indices:
            frame = self._frame_manager.get_frame(idx)
            if frame and frame.image is not None:
                frames.append((frame.index, frame.image))
        
        if not frames:
            return
        
        # 创建工作线程，传入检测模式
        self._pose_worker = PoseWorker(frames=frames, mode=detect_mode)
        
        self._pose_worker.progress.connect(self._on_pose_progress)
        self._pose_worker.pose_detected.connect(self._on_pose_detected)
        self._pose_worker.finished.connect(self._on_pose_finished)
        self._pose_worker.error.connect(self._on_pose_error)
        
        # 开始处理
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.pose_btn.setEnabled(False)
                
        mode_text = "轮廓" if detect_mode == "contour" else "姿势"
        self.status_label.setText(f"正在检测{mode_text}...")
        
        self._pose_worker.start()
    
    @Slot()
    def export_frames(self):
        """导出帧"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            # 如果没有选中，使用所有帧
            selected_indices = list(range(self._frame_manager.frame_count))
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "没有可导出的帧")
            return
        
        # 打开导出对话框
        dialog = ExportDialog(frame_count=len(selected_indices), parent=self)
        
        # 设置当前帧尺寸（用于宽高比计算和默认值）
        if selected_indices:
            first_frame = self._frame_manager.get_frame(selected_indices[0])
            if first_frame and first_frame.display_image is not None:
                h, w = first_frame.display_image.shape[:2]
                dialog.set_original_size(w, h)
        
        if dialog.exec() == ExportDialog.Accepted:
            export_config = dialog.get_config()
            export_config.frame_indices = selected_indices
            
            # 获取要导出的帧
            frames = []
            for idx in selected_indices:
                frame = self._frame_manager.get_frame(idx)
                if frame:
                    frames.append(frame)
            
            try:
                self.status_label.setText("正在导出...")
                QApplication.processEvents()
                
                result = self._exporter.export(frames, export_config)
                
                self.status_label.setText("导出完成")
                QMessageBox.information(
                    self, "导出成功",
                    f"文件已保存到:\n{result[0]}" + 
                    (f"\n{result[1]}" if result[1] else "")
                )
            except Exception as e:
                QMessageBox.warning(self, "导出失败", str(e))
                self.status_label.setText("导出失败")
    
    @Slot(int)
    def export_single_frame(self, frame_index):
        """导出单个帧"""
        # 获取要导出的帧
        frame = self._frame_manager.get_frame(frame_index)
        if not frame:
            QMessageBox.warning(self, "错误", f"无法获取帧 #{frame_index}")
            return
        
        # 打开导出对话框
        dialog = ExportDialog(frame_count=1, parent=self)
        
        # 设置当前帧尺寸（用于宽高比计算和默认值）
        if frame.display_image is not None:
            h, w = frame.display_image.shape[:2]
            dialog.set_original_size(w, h)
        
        # 修改提示信息，添加帧索引
        dialog.info_label.setText(f"将导出 1 帧 (#{frame_index})")
        
        # 默认切换到单独帧选项卡
        dialog.tab_widget.setCurrentIndex(2)  # 单独帧选项卡
        
        if dialog.exec() == ExportDialog.Accepted:
            export_config = dialog.get_config()
            export_config.frame_indices = [frame_index]
            
            try:
                self.status_label.setText("正在导出...")
                QApplication.processEvents()
                
                result = self._exporter.export([frame], export_config)
                
                self.status_label.setText("导出完成")
                QMessageBox.information(
                    self, "导出成功",
                    f"文件已保存到:\n{result[0]}" + 
                    (f"\n{result[1]}" if result[1] else "")
                )
            except Exception as e:
                QMessageBox.warning(self, "导出失败", str(e))
                self.status_label.setText("导出失败")
    
    @Slot()
    def add_outline_to_frames(self):
        """批量添加描边"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "请先选择要描边的帧")
            return
        
        # 获取描边参数
        thickness = self.outline_spin.value()
        
        if thickness <= 0:
            QMessageBox.information(self, "提示", "描边宽度必须大于0")
            return
        
        # 获取描边颜色 (RGB)
        color = (
            self.outline_color.red(),
            self.outline_color.green(),
            self.outline_color.blue()
        )
        
        self.status_label.setText(f"正在添加描边... 0/{len(selected_indices)}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.add_outline_btn.setEnabled(False)
        QApplication.processEvents()
        
        from ..core.background_remover import BackgroundRemover
        remover = BackgroundRemover()
        
        processed_count = 0
        for i, idx in enumerate(selected_indices):
            frame = self._frame_manager.get_frame(idx)
            if frame and frame.display_image is not None:
                img = frame.display_image
                
                # 检查是否是RGBA图像
                if len(img.shape) == 3 and img.shape[2] == 4:
                    # 添加描边
                    outlined = remover.add_outline(img, thickness, color)
                    
                    # 更新帧数据
                    self._frame_manager.update_frame_image(idx, outlined, processed=True)
                    self.frame_preview.update_frame(idx, outlined)
                    processed_count += 1
                else:
                    # 非RGBA图像，跳过
                    pass
            
            # 更新进度
            progress = int((i + 1) / len(selected_indices) * 100)
            self.progress_bar.setValue(progress)
            self.status_label.setText(f"正在添加描边... {i+1}/{len(selected_indices)}")
            QApplication.processEvents()
        
        # 更新动画预览
        self._update_animation_preview()
        
        self.progress_bar.setVisible(False)
        self.add_outline_btn.setEnabled(True)
        self.status_label.setText(f"描边完成：{processed_count} 帧")
        
        if processed_count < len(selected_indices):
            skipped = len(selected_indices) - processed_count
            QMessageBox.information(
                self, "描边完成",
                f"已处理 {processed_count} 帧\n"
                f"跳过 {skipped} 帧（非RGBA格式）\n\n"
                f"描边宽度: {thickness} 像素\n"
                f"描边颜色: RGB{color}"
            )
        else:
            QMessageBox.information(
                self, "描边完成",
                f"已处理 {processed_count} 帧\n\n"
                f"描边宽度: {thickness} 像素\n"
                f"描边颜色: RGB{color}"
            )
    
    def _optimize_edges(self):
        """批量优化边缘（收缩）"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "请先选择要优化的帧")
            return
        
        # 获取边缘收缩参数
        edge_erode = self.edge_erode_spin.value()
        
        if edge_erode <= 0:
            QMessageBox.information(self, "提示", "边缘收缩必须大于0")
            return
        
        self.status_label.setText(f"正在优化边缘... 0/{len(selected_indices)}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.edge_optimize_btn.setEnabled(False)
        QApplication.processEvents()
        
        import cv2
        
        processed_count = 0
        for i, idx in enumerate(selected_indices):
            frame = self._frame_manager.get_frame(idx)
            if frame and frame.display_image is not None:
                img = frame.display_image
                
                # 检查是否是RGBA图像
                if len(img.shape) == 3 and img.shape[2] == 4:
                    # 提取alpha通道
                    alpha = img[:, :, 3]
                    
                    # 边缘收缩（腐蚀）
                    kernel_size = edge_erode * 2 + 1
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
                    eroded_alpha = cv2.erode(alpha, kernel, iterations=1)
                    
                    # 更新alpha通道
                    optimized = img.copy()
                    optimized[:, :, 3] = eroded_alpha
                    
                    # 更新帧数据
                    self._frame_manager.update_frame_image(idx, optimized, processed=True)
                    self.frame_preview.update_frame(idx, optimized)
                    processed_count += 1
                else:
                    # 非RGBA图像，跳过
                    pass
            
            # 更新进度
            progress = int((i + 1) / len(selected_indices) * 100)
            self.progress_bar.setValue(progress)
            self.status_label.setText(f"正在优化边缘... {i+1}/{len(selected_indices)}")
            QApplication.processEvents()
        
        # 更新动画预览
        self._update_animation_preview()
        
        self.progress_bar.setVisible(False)
        self.edge_optimize_btn.setEnabled(True)
        self.status_label.setText(f"边缘优化完成：{processed_count} 帧")
        
        if processed_count < len(selected_indices):
            skipped = len(selected_indices) - processed_count
            QMessageBox.information(
                self, "优化完成",
                f"已处理 {processed_count} 帧\n"
                f"跳过 {skipped} 帧（非RGBA格式）\n\n"
                f"边缘收缩: {edge_erode} 像素"
            )
        else:
            QMessageBox.information(
                self, "优化完成",
                f"已处理 {processed_count} 帧\n\n"
                f"边缘收缩: {edge_erode} 像素"
            )
    
    @Slot()
    def crop_whitespace(self):
        """裁剪空白区域"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "请先选择要裁剪的帧")
            return
        
        # 获取边距
        margin_top = self.crop_margin_top.value()
        margin_bottom = self.crop_margin_bottom.value()
        margin_left = self.crop_margin_left.value()
        margin_right = self.crop_margin_right.value()
        
        self.status_label.setText("正在计算统一裁剪区域...")
        QApplication.processEvents()
        
        # 第一步：找到所有帧的联合边界框
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = 0, 0
        
        for idx in selected_indices:
            frame = self._frame_manager.get_frame(idx)
            if frame and frame.display_image is not None:
                img = frame.display_image
                
                # 如果是4通道（有透明度），使用alpha通道找边界
                if len(img.shape) == 3 and img.shape[2] == 4:
                    alpha = img[:, :, 3]
                    # 找到非透明的像素
                    rows = np.any(alpha > 0, axis=1)
                    cols = np.any(alpha > 0, axis=0)
                else:
                    # RGB图像，假设黑色为背景
                    gray = np.mean(img, axis=2) if len(img.shape) == 3 else img
                    rows = np.any(gray > 10, axis=1)
                    cols = np.any(gray > 10, axis=0)
                
                if np.any(rows) and np.any(cols):
                    y_indices = np.where(rows)[0]
                    x_indices = np.where(cols)[0]
                    
                    min_x = min(min_x, x_indices[0])
                    max_x = max(max_x, x_indices[-1])
                    min_y = min(min_y, y_indices[0])
                    max_y = max(max_y, y_indices[-1])
        
        if min_x == float('inf') or max_x == 0:
            QMessageBox.warning(self, "错误", "未找到有效的内容区域")
            return
        
        # 应用边距（确保不超出图像边界）
        first_frame = self._frame_manager.get_frame(selected_indices[0])
        img_height, img_width = first_frame.display_image.shape[:2]
        
        min_x = max(0, min_x - margin_left)
        max_x = min(img_width - 1, max_x + margin_right)
        min_y = max(0, min_y - margin_top)
        max_y = min(img_height - 1, max_y + margin_bottom)
        
        crop_width = max_x - min_x + 1
        crop_height = max_y - min_y + 1
        
        # 第二步：应用裁剪到所有选中的帧
        self.status_label.setText(f"正在裁剪 {len(selected_indices)} 帧...")
        QApplication.processEvents()
        
        cropped_count = 0
        for idx in selected_indices:
            frame = self._frame_manager.get_frame(idx)
            if frame and frame.display_image is not None:
                img = frame.display_image
                
                # 裁剪
                cropped = img[min_y:max_y+1, min_x:max_x+1].copy()
                
                # 更新帧数据
                self._frame_manager.update_frame_image(idx, cropped, processed=True)
                self.frame_preview.update_frame(idx, cropped)
                cropped_count += 1
        
        # 更新动画预览
        self._update_animation_preview()
        
        self.status_label.setText(f"裁剪完成：{cropped_count} 帧 ({crop_width}x{crop_height})")
        QMessageBox.information(
            self, "裁剪完成",
            f"已裁剪 {cropped_count} 帧\n"
            f"原始尺寸: {img_width}x{img_height}\n"
            f"裁剪后: {crop_width}x{crop_height}\n"
            f"裁剪区域: ({min_x}, {min_y}) - ({max_x}, {max_y})"
        )
    
    def _on_time_range_changed(self, start: float, end: float):
        """时间范围变化"""
        self._update_estimate()
        if self.range_play_check.isChecked():
            self.video_player.set_playback_range(start, end)

    def _on_range_play_toggled(self, checked: bool):
        if checked:
            start, end = self.timeline.get_range()
            self.video_player.set_playback_range(start, end)
            self.video_player.set_range_playback_enabled(True)
        else:
            self.video_player.set_range_playback_enabled(False)
            self.video_player.clear_playback_range()

    def _on_fps_changed(self, fps: float):
        """FPS变化"""
        config.extract_fps = fps
        self._update_estimate()
    
    def _update_estimate(self):
        """更新预计帧数"""
        if not self._video_info:
            return
        
        start, end = self.timeline.get_range()
        fps = self.fps_spin.value()
        count = int((end - start) * fps)
        self.estimate_label.setText(f"预计: {count} 帧")
    
    def _on_extraction_progress(self, current: int, total: int, percent: float):
        self.progress_bar.setValue(int(percent))
        self.status_label.setText(f"正在提取帧... {current}/{total}")
    
    def _on_extraction_finished(self, frames: list):
        self.progress_bar.setVisible(False)
        self.extract_btn.setEnabled(True)
        
        # 检查是否已有帧数据（重新抽帧的情况）
        has_existing_frames = self._frame_manager.frame_count > 0
        existing_selected = []
        if has_existing_frames:
            # 保存当前勾选状态
            existing_selected = self.frame_preview.get_selected_indices()
        
        # 保存帧数据
        self._frame_manager.clear()
        self._frame_manager.add_frames(frames)
        
        # 更新预览
        self.frame_preview.set_frames(frames)
        
        # 只有首次抽帧或没有勾选时才全选
        if not has_existing_frames or len(existing_selected) == 0:
            # 默认全选所有帧
            self._frame_manager.select_all()
            self.frame_preview.select_all()
            self.status_label.setText(f"提取完成，共 {len(frames)} 帧（已全选）")
        else:
            # 保持原有勾选状态（只勾选范围内的帧）
            for idx in existing_selected:
                if idx < len(frames):
                    self._frame_manager.select_frame(idx, True)
                    self.frame_preview.update_selection(idx, True)
            self.status_label.setText(f"提取完成，共 {len(frames)} 帧（保持勾选状态）")
        
        # 更新状态
        self._update_frame_count()
        
        # 初始化缩放宽高比（基于第一帧）
        if len(frames) > 0 and frames[0].image is not None:
            h, w = frames[0].image.shape[:2]
            self._scale_aspect_ratio = w / h if h > 0 else 1.0
            self.scale_width_spin.setValue(w)
            self.scale_height_spin.setValue(h)
        
        # 启用后续功能
        self.scale_frames_btn.setEnabled(True)
        self.remove_bg_btn.setEnabled(True)
        self.test_bg_btn.setEnabled(True)
        self.pose_btn.setEnabled(True)
        self.add_outline_btn.setEnabled(True)
        self.crop_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        
        # 切换到帧管理Tab
        self.tab_widget.setCurrentIndex(1)
        
        # 初始化动画预览（显示所有选中的帧）
        self._update_animation_preview()
    
    def _on_extraction_error(self, error: str):
        self.progress_bar.setVisible(False)
        self.extract_btn.setEnabled(True)
        self.status_label.setText("提取失败")
        QMessageBox.warning(self, "错误", f"帧提取失败: {error}")
    
    def _on_bg_progress(self, current: int, total: int, percent: float):
        self.progress_bar.setValue(int(percent))
    
    def _on_bg_status(self, status: str):
        self.status_label.setText(status)
    
    def _on_frame_processed(self, frame_index: int, processed_image):
        # 更新帧数据
        self._frame_manager.update_frame_image(frame_index, processed_image, processed=True)
        
        # 更新预览
        self.frame_preview.update_frame(frame_index, processed_image)
    
    def _on_bg_finished(self):
        self.progress_bar.setVisible(False)
        self.remove_bg_btn.setEnabled(True)
        self.edge_optimize_btn.setEnabled(True)  # 抠图完成后启用边缘优化
        self.status_label.setText("背景去除完成")
    
    def _on_bg_error(self, error: str):
        self.progress_bar.setVisible(False)
        self.remove_bg_btn.setEnabled(True)
        self.status_label.setText("背景去除失败")
        QMessageBox.warning(self, "错误", f"背景去除失败: {error}")
    
    def _test_background_removal(self):
        """测试背景去除效果"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "请先在'帧管理'中勾选要测试的帧")
            return
        
        # 只取第一帧测试
        frame_index = selected_indices[0]
        frame = self._frame_manager.get_frame(frame_index)
        
        if frame is None or frame.image is None:
            QMessageBox.warning(self, "错误", f"无法获取第 {frame_index} 帧的图像")
            return
        
        # 确定模式
        mode = BackgroundMode.AI if self.ai_mode_radio.isChecked() else BackgroundMode.COLOR
        
        color_params = None
        ai_params = None
        
        if mode == BackgroundMode.COLOR:
            color_params = self._get_color_params()
        else:
            ai_params = self._get_ai_params()
        
        # 显示处理中
        self.status_label.setText(f"正在测试第 {frame_index} 帧背景去除...")
        QApplication.processEvents()
        
        try:
            # 创建临时的 BackgroundRemover，并传入状态更新回调
            remover = BackgroundRemover(progress_callback=lambda msg: self.status_label.setText(msg))
            result = remover.remove_background(frame.image, mode, color_params, ai_params)
            
            # 获取实际使用的设备信息
            device_info = ""
            if mode == BackgroundMode.AI and remover._rembg_session:
                device_type = getattr(remover._rembg_session, 'device_type', '未知')
                device_info = f" [设备: {device_type}]"
            
            # 显示对比对话框
            from src.ui.widgets.bg_test_dialog import BackgroundTestDialog
            dialog = BackgroundTestDialog(frame.image, result, parent=self)
            dialog.setWindowTitle(f"背景去除效果预览{device_info}")
            dialog.exec()
            
            self.status_label.setText(f"测试完成{device_info}")
        except Exception as e:
            import traceback
            error_msg = f"背景去除测试失败:\n{str(e)}\n\n{traceback.format_exc()}"
            print(error_msg)
            QMessageBox.critical(self, "测试失败", error_msg)
            self.status_label.setText("测试失败")
    
    def _update_model_list(self):
        """更新模型列表"""
        self.ai_model_combo.clear()
        models = BackgroundRemover.get_available_models()
        for model in models:
            display = model['display_name']
            if not model['installed']:
                display += " (未安装)"
            self.ai_model_combo.addItem(display, model['name'])
    
    def _on_ai_mode_toggled(self, checked: bool):
        """颜色模式切换（与AI模式互补）"""
        # AI相关控件（模型、设备、参数）
        # 注意：ai_model_combo和device_combo是QHBoxLayout中的，需要通过parentWidget控制
        # 此处简化处理，直接设置显示/隐藏即可
        pass  # 由于UI重构，AI相关控件已经在默认状态下隐藏
    
    def _get_ai_params(self) -> dict:
        """获取AI参数"""
        model_idx = self.ai_model_combo.currentIndex()
        model_name = self.ai_model_combo.itemData(model_idx) if model_idx >= 0 else "bria-rmbg-2.0"  # 默认使用BRIA
        device_mode = self.device_combo.currentData()
        
        # AI模式简化后只有模型和设备，描边使用通用描边设置
        return {
            'model': model_name,
            'alpha_threshold': 0,  # AI模式不需要
            'erode': 0,  # AI模式不需要
            'feather': 0,  # AI模式不需要
            'outline': self.outline_spin.value(),  # 使用通用描边
            'outline_color': (self.outline_color.red(), self.outline_color.green(), self.outline_color.blue()),
            'force_cpu': (device_mode == 'cpu')
        }
    
    def _choose_ai_outline_color(self):
        """选择AI模式描边颜色（已废弃，使用通用描边）"""
        pass

    
    def _on_color_mode_toggled(self, checked: bool):
        """颜色模式切换"""
        # 颜色模式选中时显示颜色相关控件，隐藏AI控件
        # 由于UI已重构，默认颜色模式已选中，无需额外处理
        
        # 根据预设决定是否显示高级参数
        if checked:
            is_custom = self.color_preset_combo.currentText() == "自定义"
            self.color_params_widget.setVisible(is_custom)
        else:
            self.color_params_widget.setVisible(False)
    
    def _on_color_preset_changed(self, preset: str):
        """颜色预设变化"""
        self.color_params_widget.setVisible(preset == "自定义")
        
        presets = BackgroundRemover.get_color_presets()
        if preset in presets:
            params = presets[preset]
            lower = params['lower']
            upper = params['upper']
            # 更新SpinBox值
            self.h_min_spin.setValue(lower[0])
            self.s_min_spin.setValue(lower[1])
            self.v_min_spin.setValue(lower[2])
            self.h_max_spin.setValue(upper[0])
            self.s_max_spin.setValue(upper[1])
            self.v_max_spin.setValue(upper[2])
    
    def _get_color_params(self) -> dict:
        """获取颜色参数"""
        return {
            'lower': (
                self.h_min_spin.value(),
                self.s_min_spin.value(),
                self.v_min_spin.value()
            ),
            'upper': (
                self.h_max_spin.value(),
                self.s_max_spin.value(),
                self.v_max_spin.value()
            ),
            'invert': False,
            'feather': self.color_feather_spin.value(),
            'denoise': self.denoise_spin.value(),
            'outline': self.outline_spin.value(),
            'outline_color': (self.outline_color.red(), self.outline_color.green(), self.outline_color.blue())
        }
    
    def _choose_outline_color(self):
        """选择颜色模式描边颜色"""
        color = QColorDialog.getColor(self.outline_color, self, "选择描边颜色")
        if color.isValid():
            self.outline_color = color
            self._update_outline_color_btn_style()
    
    def _update_outline_color_btn_style(self):
        """更新颜色按钮的背景色"""
        from PySide6.QtGui import QPalette
        brightness = (self.outline_color.red() * 299 + 
                     self.outline_color.green() * 587 + 
                     self.outline_color.blue() * 114) / 1000
        text_color = QColor("white") if brightness < 128 else QColor("black")
        
        # 使用调色板设置背景色，保留默认按钮样式
        palette = self.outline_color_btn.palette()
        palette.setColor(QPalette.Button, self.outline_color)
        palette.setColor(QPalette.ButtonText, text_color)
        self.outline_color_btn.setPalette(palette)
        self.outline_color_btn.setAutoFillBackground(True)
    
    def _on_scale_mode_changed(self):
        """缩放模式切换"""
        is_percent = self.scale_percent_radio.isChecked()
        self.scale_percent_widget.setVisible(is_percent)
        self.scale_fixed_widget.setVisible(not is_percent)
    
    def _on_scale_width_changed(self, value):
        """固定宽度变化"""
        if self._updating_scale_size or not self.scale_lock_ratio_check.isChecked():
            return
        if self._scale_aspect_ratio > 0:
            self._updating_scale_size = True
            new_height = int(value / self._scale_aspect_ratio)
            self.scale_height_spin.setValue(new_height)
            self._updating_scale_size = False
    
    def _on_scale_height_changed(self, value):
        """固定高度变化"""
        if self._updating_scale_size or not self.scale_lock_ratio_check.isChecked():
            return
        if value > 0:
            self._updating_scale_size = True
            new_width = int(value * self._scale_aspect_ratio)
            self.scale_width_spin.setValue(new_width)
            self._updating_scale_size = False
    
    def _scale_frames(self):
        """批量缩放帧"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        if not selected_indices:
            QMessageBox.information(self, "提示", "请先在'帧管理'中勾选要缩放的帧")
            return
        
        # 获取原始尺寸
        first_frame = self._frame_manager.get_frame(selected_indices[0])
        if not first_frame or first_frame.image is None:
            QMessageBox.warning(self, "错误", "无法获取帧图像")
            return
        
        orig_h, orig_w = first_frame.display_image.shape[:2]
        
        # 计算目标尺寸
        if self.scale_percent_radio.isChecked():
            # 比例缩放
            scale = self.scale_percent_spin.value() / 100.0
            target_w = int(orig_w * scale)
            target_h = int(orig_h * scale)
        else:
            # 固定尺寸
            target_w = self.scale_width_spin.value()
            target_h = self.scale_height_spin.value()
        
        if target_w == orig_w and target_h == orig_h:
            QMessageBox.information(self, "提示", "目标尺寸与原始尺寸相同，无需缩放")
            return
        
        # 获取缩放算法
        from PIL import Image
        algorithm_map = {
            "nearest": Image.Resampling.NEAREST,
            "box": Image.Resampling.BOX,
            "bilinear": Image.Resampling.BILINEAR,
            "hamming": Image.Resampling.HAMMING,
            "bicubic": Image.Resampling.BICUBIC,
            "lanczos": Image.Resampling.LANCZOS,
        }
        algorithm = algorithm_map.get(self.scale_algorithm_combo.currentData(), Image.Resampling.LANCZOS)
        
        # 确认对话框
        reply = QMessageBox.question(
            self, "确认缩放",
            f"将对 {len(selected_indices)} 帧进行缩放\n\n"
            f"原始尺寸: {orig_w}x{orig_h}\n"
            f"目标尺寸: {target_w}x{target_h}\n\n"
            f"❗ 注意：缩放后无法恢复，建议先保存工程",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 开始缩放
        self.status_label.setText(f"正在缩放 {len(selected_indices)} 帧...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(selected_indices))
        self.scale_frames_btn.setEnabled(False)
        QApplication.processEvents()
        
        scaled_count = 0
        for i, idx in enumerate(selected_indices):
            frame = self._frame_manager.get_frame(idx)
            if frame and frame.display_image is not None:
                img = frame.display_image
                
                # 转换为PIL图像
                pil_img = Image.fromarray(img)
                
                # 缩放
                scaled_pil = pil_img.resize((target_w, target_h), algorithm)
                
                # 转回 numpy
                import numpy as np
                scaled_img = np.array(scaled_pil)
                
                # 更新帧数据
                self._frame_manager.update_frame_image(idx, scaled_img, processed=True)
                self.frame_preview.update_frame(idx, scaled_img)
                scaled_count += 1
            
            self.progress_bar.setValue(i + 1)
            QApplication.processEvents()
        
        # 更新动画预览
        self._update_animation_preview()
        
        self.progress_bar.setVisible(False)
        self.scale_frames_btn.setEnabled(True)
        self.status_label.setText(f"缩放完成：{scaled_count} 帧 ({orig_w}x{orig_h} → {target_w}x{target_h})")
        QMessageBox.information(
            self, "缩放完成",
            f"已缩放 {scaled_count} 帧\n"
            f"原始尺寸: {orig_w}x{orig_h}\n"
            f"缩放后: {target_w}x{target_h}"
        )

    
    def _on_pose_progress(self, current: int, total: int, percent: float):
        self.progress_bar.setValue(int(percent))
        detect_mode = self.detect_mode_combo.currentData()
        mode_text = "轮廓" if detect_mode == "contour" else "姿势"
        self.status_label.setText(f"正在检测{mode_text}... {current}/{total}")
    
    def _on_pose_detected(self, frame_index: int, data):
        if data:
            detect_mode = self.detect_mode_combo.currentData()
            if detect_mode == "contour":
                self._frame_manager.add_contour(data)
            elif detect_mode == "image":
                self._frame_manager.add_image_feature(data)
            elif detect_mode == "regional":
                self._frame_manager.add_regional_feature(data)
            else:
                self._frame_manager.add_pose(data)
    
    def _on_pose_finished(self):
        self.progress_bar.setVisible(False)
        self.pose_btn.setEnabled(True)
        
        detect_mode = self.detect_mode_combo.currentData()
        mode_text = {"pose": "姿势", "pose_rtm": "姿势(RTM)", "contour": "轮廓", "image": "图像特征", "regional": "分区域SSIM"}.get(detect_mode, "检测")
        self.status_label.setText(f"{mode_text}检测完成")
        
        # 切换到姿势分析视图 (如果是姿势模式)
        if detect_mode in ("pose", "pose_rtm"):
            for frame in self._frame_manager.frames:
                if frame.pose_id:
                    pose = self._frame_manager.get_pose(frame.pose_id)
                    if frame.image is not None:
                        self.pose_viewer.set_image_and_pose(frame.image, pose)
                        self.tab_widget.setCurrentIndex(2)  # 切换到姿势分析Tab
                    break
    
    def _on_pose_error(self, error: str):
        self.progress_bar.setVisible(False)
        self.pose_btn.setEnabled(True)
        self.status_label.setText("姿势检测失败")
        QMessageBox.warning(self, "错误", f"姿势检测失败: {error}")
    
    def _remove_similar_frames(self):
        """在当前勾选范围内，将相似帧分组，每组只保留第一帧"""
        if self._frame_manager.frame_count == 0:
            QMessageBox.warning(self, "提示", "请先提取视频帧")
            return
            
        # 获取当前勾选的帧索引
        selected_indices = self.frame_preview.get_selected_indices()
            
        if len(selected_indices) < 2:
            QMessageBox.information(self, "提示", 
                "当前勾选少于 2 帧，无法进行相似度对比\n\n"
                "建议：先点击 '寻找循环' 确定范围，再点击 '去除相似' 精简帧"
            )
            return
                
        threshold = self.similarity_spin.value() / 100.0
        detect_mode = self.detect_mode_combo.currentData()
            
        # 根据模式获取已勾选帧中有数据的帧
        frames_with_data = []
        for idx in selected_indices:
            frame = self._frame_manager.get_frame(idx)
            if not frame:
                continue
                    
            if detect_mode == "contour":
                if frame.contour_id:
                    data = self._frame_manager.get_contour(frame.contour_id)
                    if data:
                        frames_with_data.append((frame, data))
            elif detect_mode == "image":
                if frame.image_feature_id:
                    data = self._frame_manager.get_image_feature(frame.image_feature_id)
                    if data:
                        frames_with_data.append((frame, data))
            elif detect_mode == "regional":
                if hasattr(frame, 'regional_feature_id') and frame.regional_feature_id:
                    data = self._frame_manager.get_regional_feature(frame.regional_feature_id)
                    if data:
                        frames_with_data.append((frame, data))
            elif detect_mode in ("pose", "pose_rtm"):
                if frame.pose_id:
                    data = self._frame_manager.get_pose(frame.pose_id)
                    if data:
                        frames_with_data.append((frame, data))
            
        mode_text = {"pose": "姿势", "pose_rtm": "姿势(RTM)", "contour": "轮廓", "image": "图像特征", "regional": "分区域SSIM"}.get(detect_mode, "检测")
            
        if not frames_with_data:
            QMessageBox.warning(self, "提示", 
                f"当前勾选的帧中，尚无{mode_text}数据\n\n"
                f"请先点击 '分析特征/姿势' 按钮进行检测"
            )
            return
                
        if len(frames_with_data) < 2:
            QMessageBox.information(self, "提示", f"当前勾选的帧中，只有 {len(frames_with_data)} 帧有{mode_text}数据，需要至少 2 帧才能进行对比")
            return
    
        # 分组：连续相似的帧归为一组
        groups = []  # [(anchor_frame, [member_frames])]
        current_group_anchor = frames_with_data[0]
        current_group_members = [frames_with_data[0][0]]  # 只存frame
        
        for i in range(1, len(frames_with_data)):
            curr_frame, curr_data = frames_with_data[i]
            anchor_frame, anchor_data = current_group_anchor
            
            # 与组锚点（第一帧）比较
            similarity = anchor_data.similarity_to(curr_data)
            
            if similarity >= threshold:
                # 相似，加入当前组
                current_group_members.append(curr_frame)
            else:
                # 不相似，保存当前组，开始新组
                groups.append((anchor_frame, current_group_members))
                current_group_anchor = (curr_frame, curr_data)
                current_group_members = [curr_frame]
        
        # 保存最后一组
        groups.append((current_group_anchor[0], current_group_members))
        
        # 开始批量更新（禁止信号触发）
        self.frame_preview.begin_batch_update()
        
        # 处理分组：每组只勾选第一帧
        removed_count = 0
        kept_count = 0
        group_info = []
        
        for anchor_frame, members in groups:
            # 保留锚点帧（组内第一帧）
            self.frame_preview.update_selection(anchor_frame.index, True)
            self._frame_manager.select_frame(anchor_frame.index, True)
            kept_count += 1
            
            # 取消勾选组内其他帧
            for member in members[1:]:  # 跳过第一帧
                self.frame_preview.update_selection(member.index, False)
                self._frame_manager.select_frame(member.index, False)
                removed_count += 1
            
            # 记录分组信息
            if len(members) > 1:
                group_info.append(f"组: #{anchor_frame.index} (包含{len(members)}帧)")
            else:
                group_info.append(f"组: #{anchor_frame.index}")
        
        # 结束批量更新（发送一次信号）
        self.frame_preview.end_batch_update()
        
        # 显示结果
        detail_msg = "\n".join(group_info[:10])  # 最多显示10组
        if len(group_info) > 10:
            detail_msg += f"\n... 共 {len(group_info)} 组"
        
        self.status_label.setText(f"分组完成: {len(groups)} 组，保留 {kept_count} 帧")
        QMessageBox.information(
            self, "相似帧分组完成", 
            f"检测模式: {mode_text}\n"
            f"相似度阈值: {threshold*100:.0f}%\n"
            f"处理范围: 当前勾选的 {len(selected_indices)} 帧\n"
            f"分组数量: {len(groups)}\n"
            f"保留帧数: {kept_count}\n"
            f"取消勾选: {removed_count} 帧\n\n"
            f"{detail_msg}"
        )
    
    def _find_loop_frame(self):
        """从勾选的帧中，找到与首帧最相似的帧，用于动画首尾衔接"""
        selected_indices = self.frame_preview.get_selected_indices()
        detect_mode = self.detect_mode_combo.currentData()
        mode_text = {"pose": "姿势", "pose_rtm": "姿势(RTM)", "contour": "轮廓", "image": "图像特征", "regional": "分区域SSIM"}.get(detect_mode, "检测")
            
        if len(selected_indices) < 2:
            QMessageBox.information(self, "提示", "请先选择至少 2 帧（首帧和可能的循环点）")
            return
            
        # 获取首帧的数据
        first_idx = selected_indices[0]
        first_frame = self._frame_manager.get_frame(first_idx)
    
        if detect_mode == "contour":
            if not first_frame or not first_frame.contour_id:
                QMessageBox.warning(self, "错误", f"首帧没有{mode_text}数据，请先进行检测")
                return
            first_data = self._frame_manager.get_contour(first_frame.contour_id)
        elif detect_mode == "image":
            if not first_frame or not first_frame.image_feature_id:
                QMessageBox.warning(self, "错误", f"首帧没有{mode_text}数据，请先进行检测")
                return
            first_data = self._frame_manager.get_image_feature(first_frame.image_feature_id)
        elif detect_mode == "regional":
            if not first_frame or not hasattr(first_frame, 'regional_feature_id') or not first_frame.regional_feature_id:
                QMessageBox.warning(self, "错误", f"首帧没有{mode_text}数据，请先进行检测")
                return
            first_data = self._frame_manager.get_regional_feature(first_frame.regional_feature_id)
        elif detect_mode in ("pose", "pose_rtm"):
            if not first_frame or not first_frame.pose_id:
                QMessageBox.warning(self, "错误", f"首帧没有{mode_text}数据，请先进行检测")
                return
            first_data = self._frame_manager.get_pose(first_frame.pose_id)
        
        if not first_data:
            QMessageBox.warning(self, "错误", f"无法获取首帧{mode_text}数据")
            return
        
        # 从勾选的帧中，从后往前找与首帧最相似的帧
        best_similarity = -1
        best_frame_idx = -1
        
        # 从勾选帧的末尾往前遍历（跳过首帧自己）
        for idx in reversed(selected_indices[1:]):
            frame = self._frame_manager.get_frame(idx)
            if frame:
                if detect_mode == "contour":
                    if frame.contour_id:
                        data = self._frame_manager.get_contour(frame.contour_id)
                        if data:
                            similarity = first_data.similarity_to(data)
                            if similarity > best_similarity:
                                best_similarity = similarity
                                best_frame_idx = idx
                elif detect_mode == "image":
                    if frame.image_feature_id:
                        data = self._frame_manager.get_image_feature(frame.image_feature_id)
                        if data:
                            similarity = first_data.similarity_to(data)
                            if similarity > best_similarity:
                                best_similarity = similarity
                                best_frame_idx = idx
                elif detect_mode == "regional":
                    if hasattr(frame, 'regional_feature_id') and frame.regional_feature_id:
                        data = self._frame_manager.get_regional_feature(frame.regional_feature_id)
                        if data:
                            similarity = first_data.similarity_to(data)
                            if similarity > best_similarity:
                                best_similarity = similarity
                                best_frame_idx = idx
                elif detect_mode in ("pose", "pose_rtm"):
                    if frame.pose_id:
                        data = self._frame_manager.get_pose(frame.pose_id)
                        if data:
                            similarity = first_data.similarity_to(data)
                            if similarity > best_similarity:
                                best_similarity = similarity
                                best_frame_idx = idx
        
        if best_frame_idx < 0:
            QMessageBox.information(self, "提示", f"没有找到有{mode_text}数据的帧")
            return
        
        # 显示结果 - 注意：循环动画应该不包括最后那个相似帧，否则会重复
        end_frame_idx = best_frame_idx - 1  # 实际结束帧是相似帧的前一帧
        result_msg = (
            f"检测模式: {mode_text}\n"
            f"首帧: #{first_idx}\n"
            f"循环点: #{best_frame_idx} (相似度 {best_similarity*100:.1f}%)\n"
            f"建议范围: #{first_idx} ~ #{end_frame_idx}\n\n"
            f"说明: 从当前勾选的帧中查找，\n"
            f"不包括循环点帧，因为它与首帧相似，循环时会重复"
        )
        
        reply = QMessageBox.question(
            self, "找到循环帧",
            result_msg + "\n\n是否只保留这个范围内的帧？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 只保留首帧到循环点之间的帧（不包括循环点本身）
            self.frame_preview.begin_batch_update()
            
            for i in range(self._frame_manager.frame_count):
                if first_idx <= i < best_frame_idx:
                    # 在循环范围内，保持原有的选中状态（不强制改变）
                    pass
                else:
                    # 范围外，取消选中
                    self.frame_preview.update_selection(i, False)
                    self._frame_manager.select_frame(i, False)
            
            self.frame_preview.end_batch_update()
            self.status_label.setText(f"已取消范围外的帧，保留 #{first_idx} ~ #{end_frame_idx} 范围内的选择")
        else:
            # 高亮显示找到的帧
            self.frame_preview.update_selection(best_frame_idx, True)
            self._frame_manager.select_frame(best_frame_idx, True)
            self.status_label.setText(f"循环点: #{best_frame_idx} (相似度 {best_similarity*100:.1f}%)")
    
    def _on_frame_clicked(self, frame_index: int):
        """帧被点击"""
        frame = self._frame_manager.get_frame(frame_index)
        if frame and frame.image is not None:
            # 更新姿势视图
            pose = self._frame_manager.get_pose_for_frame(frame_index)
            self.pose_viewer.set_image_and_pose(frame.image, pose)
    
    def _on_selection_changed(self, selected_indices: list):
        """选择变化"""
        # 同步到frame_manager
        self._frame_manager.deselect_all()
        for idx in selected_indices:
            self._frame_manager.select_frame(idx, True)
        # 更新状态栏显示
        self._update_frame_count()
        
        # 自动更新动画预览
        self._update_animation_preview()
    
    def _on_tab_changed(self, index: int):
        """切换Tab时同步状态"""
        # 如果切换到动画预览Tab（索引为3），确保动画预览是最新的
        if index == 3:  # 动画预览Tab
            self._update_animation_preview()
    
    def _select_all_frames(self):
        """全选"""
        self._frame_manager.select_all()
        self.frame_preview.select_all()
        self._update_frame_count()
    
    def _deselect_all_frames(self):
        """取消全选"""
        self._frame_manager.deselect_all()
        self.frame_preview.deselect_all()
        self._update_frame_count()
    
    def _preview_selected_frames(self):
        """预览选中的帧"""
        self._update_animation_preview()
    
    def _update_animation_preview(self):
        """更新动画预览（内部方法）"""
        selected_indices = self.frame_preview.get_selected_indices()
        
        print(f"[DEBUG] 更新动画预览: 选中 {len(selected_indices)} 帧")  # 调试信息
        
        if not selected_indices:
            # 没有选中任何帧，清空预览
            self.animation_preview.set_frames([])
            return
        
        # 获取图像
        images = []
        for idx in selected_indices:
            frame = self._frame_manager.get_frame(idx)
            if frame:
                img = frame.display_image
                if img is not None:
                    images.append(img)
        
        print(f"[DEBUG] 实际加载 {len(images)} 帧到动画预览")  # 调试信息
        
        if images:
            self.animation_preview.set_frames(images)
    
    def _update_frame_count(self):
        """更新帧计数"""
        count = self._frame_manager.frame_count
        selected = self._frame_manager.selected_count
        self.frame_count_label.setText(f"帧数: {count} (选中: {selected})")
    
    def closeEvent(self, event):
        """关闭事件"""
        # 停止所有工作线程
        if self._extraction_worker and self._extraction_worker.isRunning():
            self._extraction_worker.cancel()
            self._extraction_worker.wait()
        
        if self._background_worker and self._background_worker.isRunning():
            self._background_worker.cancel()
            self._background_worker.wait()
        
        if self._pose_worker and self._pose_worker.isRunning():
            self._pose_worker.cancel()
            self._pose_worker.wait()
        
        # 释放资源
        self.video_player.release()
        
        event.accept()
