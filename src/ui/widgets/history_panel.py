"""历史记录面板控件"""
from typing import List
from datetime import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame
from PySide6.QtCore import Signal, Qt, Slot
from PySide6.QtGui import QFont

from src.core.history_manager import HistoryEntry


class HistoryEntryWidget(QWidget):
    """单条历史记录控件"""
    revert_clicked = Signal(int)  # step_id

    def __init__(self, entry: HistoryEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(2)
        self.setFixedHeight(60)  # 固定高度避免拉伸

        # 标题栏
        title_layout = QHBoxLayout()
        title_layout.setSpacing(10)

        # 步骤编号和操作名称
        step_label = QLabel(f"#{self.entry.step_id}  {self.entry.operation_name}")
        step_label.setFont(QFont("Arial", 10, QFont.Bold))
        title_layout.addWidget(step_label)

        # 回退按钮
        revert_btn = QPushButton("回退到此")
        revert_btn.setFixedSize(80, 22)
        revert_btn.setFont(QFont("Arial", 9))
        revert_btn.clicked.connect(lambda: self.revert_clicked.emit(self.entry.step_id))
        title_layout.addWidget(revert_btn, 0, Qt.AlignRight)

        layout.addLayout(title_layout)

        # 详细描述和时间
        desc_layout = QHBoxLayout()
        desc_layout.setSpacing(10)

        # 详细描述
        desc_label = QLabel(self.entry.description)
        desc_label.setFont(QFont("Arial", 9))
        desc_label.setStyleSheet("color: #666;")
        desc_layout.addWidget(desc_label)

        # 时间
        time_str = datetime.fromtimestamp(self.entry.timestamp).strftime("%H:%M:%S")
        time_label = QLabel(time_str)
        time_label.setFont(QFont("Arial", 8))
        time_label.setStyleSheet("color: #999;")
        desc_layout.addWidget(time_label, 0, Qt.AlignRight)

        layout.addLayout(desc_layout)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #eee;")
        layout.addWidget(separator)

    def disable(self):
        """禁用控件"""
        for btn in self.findChildren(QPushButton):
            btn.setEnabled(False)

    def enable(self):
        """启用控件"""
        for btn in self.findChildren(QPushButton):
            btn.setEnabled(True)


class HistoryPanel(QWidget):
    """历史记录面板"""
    revert_requested = Signal(int)  # step_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setFixedHeight(30)
        title_bar.setStyleSheet("background-color: #f5f5f5;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 0, 10, 0)

        # 标题
        self.title_label = QLabel("历史记录 (0/20)")
        self.title_label.setFont(QFont("Arial", 9, QFont.Bold))
        title_layout.addWidget(self.title_label)

        # 内存使用情况
        self.memory_label = QLabel("内存: 0.0 MB / 500 MB")
        self.memory_label.setFont(QFont("Arial", 8))
        self.memory_label.setStyleSheet("color: #666;")
        title_layout.addWidget(self.memory_label, 0, Qt.AlignRight)

        layout.addWidget(title_bar)

        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 内容区域
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 5, 0, 5)
        self.content_layout.setSpacing(2)  # 减少条目间距
        self.content_layout.setAlignment(Qt.AlignTop)  # 内容顶部对齐

        # 初始状态条目（带回退按钮）
        self.initial_widget = QWidget()
        self.initial_widget.setFixedHeight(40)
        init_layout = QHBoxLayout(self.initial_widget)
        init_layout.setContentsMargins(10, 5, 10, 5)
        
        self.initial_state_label = QLabel("⚪ 初始状态（帧提取完成）")
        self.initial_state_label.setFont(QFont("Arial", 9))
        self.initial_state_label.setStyleSheet("color: #999;")
        init_layout.addWidget(self.initial_state_label)
        
        self.initial_revert_btn = QPushButton("回退到此")
        self.initial_revert_btn.setFixedSize(80, 22)
        self.initial_revert_btn.setFont(QFont("Arial", 9))
        self.initial_revert_btn.clicked.connect(lambda: self.revert_requested.emit(0))
        self.initial_revert_btn.hide()  # 初始隐藏，有历史时才显示
        init_layout.addWidget(self.initial_revert_btn, 0, Qt.AlignRight)
        
        self.content_layout.addWidget(self.initial_widget)

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)

    def refresh(self, entries: List[HistoryEntry], memory_usage: str = "0.0 MB / 500 MB"):
        """刷新历史记录列表
        
        Args:
            entries: 历史记录列表，最新的在最前面
            memory_usage: 内存使用情况字符串
        """
        # 清空现有条目（保留初始状态控件）
        for i in reversed(range(self.content_layout.count())):
            widget = self.content_layout.itemAt(i).widget()
            if widget and widget != self.initial_widget:
                widget.deleteLater()

        # 更新标题
        self.title_label.setText(f"历史记录 ({len(entries)}/20)")
        self.memory_label.setText(f"内存: {memory_usage}")

        # 添加历史条目
        if entries:
            # 有历史时显示初始状态回退按钮
            self.initial_revert_btn.show()

            # 添加历史条目
            for entry in entries:
                entry_widget = HistoryEntryWidget(entry)
                entry_widget.revert_clicked.connect(self.revert_requested)
                self.content_layout.insertWidget(self.content_layout.count() - 1, entry_widget)  # 插到初始状态之前
        else:
            # 无历史时隐藏初始状态回退按钮
            self.initial_revert_btn.hide()

    def disable_all(self):
        """禁用所有回退按钮"""
        self.initial_revert_btn.setEnabled(False)
        for widget in self.content_widget.findChildren(HistoryEntryWidget):
            widget.disable()

    def enable_all(self):
        """启用所有回退按钮"""
        self.initial_revert_btn.setEnabled(True)
        for widget in self.content_widget.findChildren(HistoryEntryWidget):
            widget.enable()
