import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Iterator, Optional


def iter_files(root: Path, follow_symlinks: bool = False, exclude_paths: Optional[list] = None) -> Iterator[Path]:
    """遍历根目录下的所有普通文件，返回相对路径为基准的 Path 对象。
    
    Args:
        exclude_paths: 需要排除的目录路径列表（支持相对路径或绝对路径）
    """
    if exclude_paths is None:
        exclude_paths = []
    
    # 将排除路径转换为绝对路径并解析
    resolved_excludes = {Path(p).resolve() for p in exclude_paths}
    root = root.resolve()
    
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirpath_path = Path(dirpath).resolve()
        
        # 过滤掉需要排除的目录（检查完整路径）
        dirnames[:] = [
            d for d in dirnames 
            if (dirpath_path / d) not in resolved_excludes
        ]
        dirpath_path = Path(dirpath)
        for name in filenames:
            full_path = dirpath_path / name
            # 只处理普通文件
            try:
                if not full_path.is_file():
                    continue
            except OSError:
                continue
            yield full_path


def compute_md5(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    """以分块方式计算文件 MD5，适用于大文件。"""
    md5 = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def make_record(root: Path,
                file_path: Path,
                with_md5: bool,
                md5_large_threshold: Optional[int]) -> dict:
    """为单个文件生成快照记录。"""
    rel_path = file_path.relative_to(root)
    # 统一使用 POSIX 风格分隔符，便于跨平台比较
    rel_str = rel_path.as_posix()

    try:
        st = file_path.stat()
    except OSError:
        # 文件在扫描过程中被删除或权限问题，直接跳过
        return {}

    record = {
        "type": "file",
        "path": rel_str,
        "size": st.st_size,
        "mtime": st.st_mtime,
    }

    if with_md5:
        # 阈值为 None 或文件小于阈值时才计算 MD5
        if md5_large_threshold is None or st.st_size <= md5_large_threshold:
            record["md5"] = compute_md5(file_path)

    return record


def write_snapshot(root: Path,
                   output: Path,
                   with_md5: bool,
                   md5_large_threshold: Optional[int],
                   follow_symlinks: bool = False,
                   exclude_paths: Optional[list] = None) -> None:
    """生成目录快照（JSON Lines 格式）。"""
    root = root.resolve()
    output = output.resolve()

    # 确保输出目录存在
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as f:
        # 写入一行 meta 信息，便于后续调试
        meta = {
            "type": "meta",
            "root": str(root),
            "created_at": time.time(),
            "with_md5": with_md5,
            "md5_large_threshold": md5_large_threshold,
            "version": 1,
        }
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")

        for file_path in iter_files(root, follow_symlinks=follow_symlinks, exclude_paths=exclude_paths):
            record = make_record(root, file_path, with_md5, md5_large_threshold)
            if not record:
                continue
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成目录快照（JSON Lines），用于跨机器目录对比。"
    )
    parser.add_argument(
        "--root",
        required=True,
        help="要扫描的根目录路径",
    )
    parser.add_argument(
        "--output",
        default="snapshot.jsonl",
        help="快照输出文件路径（默认：snapshot.jsonl）",
    )
    parser.add_argument(
        "--with-md5",
        action="store_true",
        help="是否为文件计算 MD5（默认只记录 size 和 mtime）",
    )
    parser.add_argument(
        "--md5-large-threshold",
        type=int,
        default=100 * 1024 * 1024,
        help="只对小于该大小（字节）的文件计算 MD5，默认 100MB；设置为 0 表示对所有文件计算。",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="是否跟随符号链接（默认不跟随）",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="排除指定路径的目录（可多次使用，支持相对路径或绝对路径）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"根目录不存在: {root}")

    md5_threshold: Optional[int]
    if args.with_md5:
        md5_threshold = None if args.md5_large_threshold == 0 else args.md5_large_threshold
    else:
        md5_threshold = None

    write_snapshot(
        root=root,
        output=Path(args.output),
        with_md5=args.with_md5,
        md5_large_threshold=md5_threshold,
        follow_symlinks=args.follow_symlinks,
        exclude_paths=args.exclude if args.exclude else None,
    )


if __name__ == "__main__":
    main()

