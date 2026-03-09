import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable


def load_diff(diff_path: Path) -> Iterable[Dict[str, Any]]:
    """加载 compare_snapshots 生成的差异清单（JSON Lines）。"""
    with diff_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            path = obj.get("path")
            if not isinstance(path, str):
                continue
            yield obj


def copy_files(root_b: Path, target_root: Path, diff_path: Path, dry_run: bool) -> None:
    """
    根据差异清单，从 B 的根目录复制文件到目标目录，保持原有目录结构。

    diff_path 中每条记录至少包含:
        { "path": "relative/path", "reason": "new" | "modified", ... }
    """
    root_b = root_b.resolve()
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    for item in load_diff(diff_path):
        rel_path = item["path"]
        src = root_b / Path(rel_path)
        dst = target_root / Path(rel_path)

        if not src.is_file():
            # 源文件不存在，跳过
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)

        if dry_run:
            print(f"[DRY-RUN] {src} -> {dst}")
        else:
            # 使用 copy2 保留时间戳等元数据
            shutil.copy2(src, dst)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "根据对比结果清单，从 B 的根目录复制需要同步的文件到目标目录，保持目录结构。"
        )
    )
    parser.add_argument(
        "--root-b",
        required=True,
        help="B 机器上的根目录路径（与生成 snapshot_b 时使用的 root 相同）",
    )
    parser.add_argument(
        "--diff-file",
        required=True,
        help="compare_snapshots 生成的差异清单文件路径（JSON Lines）",
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        help="要复制到的目标根目录（用于打包或拷贝到 A 机器）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将要复制的文件，不实际执行复制",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_b = Path(args.root_b)
    diff_file = Path(args.diff_file)
    target_dir = Path(args.target_dir)

    if not root_b.exists():
        raise SystemExit(f"B 根目录不存在: {root_b}")
    if not diff_file.exists():
        raise SystemExit(f"差异清单文件不存在: {diff_file}")

    copy_files(root_b=root_b, target_root=target_dir, diff_path=diff_file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

