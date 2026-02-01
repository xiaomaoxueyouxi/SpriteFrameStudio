"""测试左侧垂直菜单显示效果"""
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QMainWindow
from PySide6.QtCore import Qt
import sys

# 导入 VerticalTabButton 类
from src.ui.main_window import VerticalTabButton

class TestWindow(QMainWindow):
    """测试窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("测试垂直菜单显示")
        self.setGeometry(100, 100, 800, 600)
        
        # 创建中央组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建垂直Tab栏
        tab_bar = QWidget()
        tab_bar.setFixedWidth(70)
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

def test_menu_display():
    """测试菜单显示效果"""
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    print("测试窗口已显示，请检查垂直菜单的显示效果")
    print("特别注意 '图像增强' 四个字是否完全显示")
    sys.exit(app.exec())

if __name__ == "__main__":
    test_menu_display()
