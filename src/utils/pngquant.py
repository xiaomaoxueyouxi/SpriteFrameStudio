"""pngquant 压缩工具模块"""
import subprocess
from pathlib import Path
from typing import Tuple, Optional
import os


def get_pngquant_path() -> Path:
    """获取 pngquant 可执行文件路径"""
    # 相对于项目根目录的位置
    return Path(__file__).parent.parent / "tools" / "pngquant" / "pngquant.exe"


def is_pngquant_available() -> bool:
    """检查 pngquant 是否可用"""
    pngquant_path = get_pngquant_path()
    return pngquant_path.exists()


def compress_png(
    input_path: Path,
    output_path: Optional[Path] = None,
    quality_min: int = 60,
    quality_max: int = 80
) -> Tuple[bool, int, int]:
    """
    使用 pngquant 压缩 PNG 文件
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径（None 表示覆盖原文件）
        quality_min: 最低质量 (0-100)
        quality_max: 最高质量 (0-100)
    
    Returns:
        (成功, 原始大小, 压缩后大小)
    """
    pngquant_path = get_pngquant_path()
    
    if not pngquant_path.exists():
        return (False, 0, 0)
    
    if not input_path.exists():
        return (False, 0, 0)
    
    # 获取原始文件大小
    original_size = input_path.stat().st_size
    
    # 构建命令
    quality_arg = f"--quality={quality_min}-{quality_max}"
    
    if output_path is None:
        # 覆盖原文件
        output_path = input_path
        cmd = [
            str(pngquant_path),
            quality_arg,
            "--force",
            "--ext", ".png",
            str(input_path)
        ]
    else:
        cmd = [
            str(pngquant_path),
            quality_arg,
            "--force",
            "-o", str(output_path),
            str(input_path)
        ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30
        )
        
        # pngquant 返回码：0=成功, 99=质量无法达到但仍输出
        if result.returncode in (0, 99):
            compressed_size = output_path.stat().st_size
            return (True, original_size, compressed_size)
        else:
            return (False, original_size, original_size)
            
    except (subprocess.TimeoutExpired, Exception):
        return (False, original_size, original_size)


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小为可读字符串"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
