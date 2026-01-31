"""程序入口"""
import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.app import App


def main():
    """主函数"""
    app = App()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
