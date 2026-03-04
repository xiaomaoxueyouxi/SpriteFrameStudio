"""程序入口"""
import sys
from pathlib import Path

# 添加项目根目录和src目录到路径
_src_dir = Path(__file__).parent
_project_dir = _src_dir.parent
sys.path.insert(0, str(_project_dir))
sys.path.insert(0, str(_src_dir))

from src.app import App


def main():
    """主函数"""
    app = App()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
