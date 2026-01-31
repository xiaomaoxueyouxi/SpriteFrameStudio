"""帧时间轴控件"""
from typing import Optional, Tuple
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QDoubleSpinBox, QVBoxLayout
from PySide6.QtCore import Qt, Signal


class FrameTimeline(QWidget):
    """帧时间轴控件 - 用于选择时间范围"""
    
    range_changed = Signal(float, float)  # start_time, end_time
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0.0
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 开始时间
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("开始时间:"))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0, 0)
        self.start_spin.setDecimals(3)
        self.start_spin.setSuffix(" 秒")
        self.start_spin.valueChanged.connect(self._on_start_changed)
        start_layout.addWidget(self.start_spin, 1)
        layout.addLayout(start_layout)
        
        # 结束时间
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("结束时间:"))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0, 0)
        self.end_spin.setDecimals(3)
        self.end_spin.setSuffix(" 秒")
        self.end_spin.valueChanged.connect(self._on_end_changed)
        end_layout.addWidget(self.end_spin, 1)
        layout.addLayout(end_layout)
        
        # 时长显示
        self.duration_label = QLabel("选中时长: 0.000 秒")
        self.duration_label.setStyleSheet("color: #888;")
        layout.addWidget(self.duration_label)
    
    def set_duration(self, duration: float):
        """设置视频总时长"""
        self._duration = duration
        
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        
        self.start_spin.setRange(0, duration)
        self.end_spin.setRange(0, duration)
        self.start_spin.setValue(0)
        self.end_spin.setValue(duration)
        
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        
        self._update_duration_label()
    
    def get_range(self) -> Tuple[float, float]:
        """获取时间范围"""
        return (self.start_spin.value(), self.end_spin.value())
    
    def set_range(self, start: float, end: float):
        """设置时间范围"""
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        
        self.start_spin.setValue(start)
        self.end_spin.setValue(end)
        
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        
        self._update_duration_label()
    
    def _on_start_changed(self, value):
        # 确保开始时间不大于结束时间
        if value > self.end_spin.value():
            self.end_spin.setValue(value)
        self._update_duration_label()
        self.range_changed.emit(self.start_spin.value(), self.end_spin.value())
    
    def _on_end_changed(self, value):
        # 确保结束时间不小于开始时间
        if value < self.start_spin.value():
            self.start_spin.setValue(value)
        self._update_duration_label()
        self.range_changed.emit(self.start_spin.value(), self.end_spin.value())
    
    def _update_duration_label(self):
        duration = self.end_spin.value() - self.start_spin.value()
        self.duration_label.setText(f"选中时长: {duration:.3f} 秒")
