"""测试默认窗口状态下左侧菜单显示效果"""
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QMainWindow
from PySide6.QtCore import Qt
import sys

# 导入 VerticalTabButton 类
from src.ui.main_window import VerticalTabButton

class TestDefaultWindow(QMainWindow):
    """测试默认窗口状态"""
    
    def __init__(self):
        super().__init__()
        # 设置默认窗口大小，模拟启动时的状态
        self.setWindowTitle("测试默认窗口状态")
        self.setGeometry(100, 100, 1000, 700)  # 更接近默认窗口大小
        
        # 创建中央组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建垂直Tab栏
        tab_bar = QWidget()
        tab_bar.setObjectName("vertical_tab_bar")
        tab_bar.setFixedWidth(60)
        tab_bar.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border-right: 1px solid #333333;
            }
        """)
        
        tab_layout = QVBoxLayout(tab_bar)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        
        # 创建测试按钮
        test_names = ["准备视频", "动作分析", "批量缩放", "背景处理", "边缘优化", "描边", "空白裁剪", "图像增强", "导出"]
        
        for name in test_names:
            btn = VerticalTabButton(name)
            tab_layout.addWidget(btn)
        
        tab_layout.addStretch()
        main_layout.addWidget(tab_bar)
        
        # 创建右侧内容区域
        content = QWidget()
        content.setStyleSheet("background-color: #f0f0f0;")
        main_layout.addWidget(content, 1)

def test_default_window():
    """测试默认窗口状态"""
    app = QApplication(sys.argv)
    window = TestDefaultWindow()
    window.show()
    print("测试默认窗口状态已显示，请检查左侧菜单的垂直居中效果")
    print("特别注意 '图像增强' 四个字是否垂直居中显示")
    sys.exit(app.exec())

if __name__ == "__main__":
    test_default_window()
