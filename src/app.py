"""应用主类"""
import sys
from PySide6.QtWidgets import QApplication, QComboBox, QSlider, QSpinBox, QDoubleSpinBox
from PySide6.QtCore import Qt, QObject, QEvent

from src.ui.main_window import MainWindow


class GlobalWheelEventFilter(QObject):
    """全局鼠标滚动事件过滤器，防止控件误操作"""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            # 过滤常见的输入型控件，防止通过滚动滚轮改变数值
            if isinstance(obj, (QComboBox, QSlider, QSpinBox, QDoubleSpinBox)):
                # 如果控件没有焦点，或者我们想彻底禁止滚动改变值
                # 这里选择彻底禁止滚动改变值，因为用户明确要求“不要支持鼠标滚动”
                event.ignore()
                return True
        return super().eventFilter(obj, event)


class App:
    """应用主类"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setStyle("Fusion")
        
        # 安装全局事件过滤器
        self.wheel_filter = GlobalWheelEventFilter()
        self.app.installEventFilter(self.wheel_filter)
        
        # 设置深色主题
        self._set_dark_theme()
        
        self.main_window = MainWindow()
    
    def _set_dark_theme(self):
        """设置现代深色主题"""
        from PySide6.QtGui import QPalette, QColor
        
        palette = QPalette()
        # 基础配色 (使用更柔和的深灰色)
        bg_color = QColor(30, 30, 30)
        base_color = QColor(25, 25, 25)
        text_color = QColor(225, 225, 225)
        accent_color = QColor(0, 120, 212) # Windows Blue
        
        palette.setColor(QPalette.Window, bg_color)
        palette.setColor(QPalette.WindowText, text_color)
        palette.setColor(QPalette.Base, base_color)
        palette.setColor(QPalette.AlternateBase, bg_color)
        palette.setColor(QPalette.ToolTipBase, text_color)
        palette.setColor(QPalette.ToolTipText, text_color)
        palette.setColor(QPalette.Text, text_color)
        palette.setColor(QPalette.Button, bg_color)
        palette.setColor(QPalette.ButtonText, text_color)
        palette.setColor(QPalette.BrightText, Qt.white)
        palette.setColor(QPalette.Link, accent_color)
        palette.setColor(QPalette.Highlight, accent_color)
        palette.setColor(QPalette.HighlightedText, Qt.white)
        
        # 禁用状态
        disabled_color = QColor(80, 80, 80)
        palette.setColor(QPalette.Disabled, QPalette.WindowText, disabled_color)
        palette.setColor(QPalette.Disabled, QPalette.Text, disabled_color)
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_color)
        
        self.app.setPalette(palette)
        
        # 设置全局字体
        from PySide6.QtGui import QFont
        font = QFont("Microsoft YaHei", 9)
        self.app.setFont(font)
    
    def run(self) -> int:
        """运行应用"""
        self.main_window.show()
        return self.app.exec()
