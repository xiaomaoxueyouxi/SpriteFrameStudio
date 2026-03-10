import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, Any


FileInfo = Tuple[int, float, Optional[str]]  # size, mtime, md5


def load_snapshot(path: Path) -> Dict[str, FileInfo]:
    """加载快照文件，返回 path -> (size, mtime, md5) 的映射。"""
    files: Dict[str, FileInfo] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj: Any = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(obj, dict):
                continue

            if obj.get("type") == "meta":
                # 元信息行，跳过
                continue

            if obj.get("type") != "file":
                continue

            rel_path = obj.get("path")
            if not isinstance(rel_path, str):
                continue

            size = int(obj.get("size", 0))
            mtime = float(obj.get("mtime", 0.0))
            md5 = obj.get("md5")
            if not isinstance(md5, str):
                md5 = None

            files[rel_path] = (size, mtime, md5)
    return files


def compare_snapshots(
    snapshot_a: Path,
    snapshot_b: Path,
    output: Path,
    check_md5: bool = False,
) -> None:
    """
    对比两个快照，找出 B 相比 A 新增或变化的文件。

    结果以 JSON Lines 形式写入 output，每行包含：
        {
          "path": "relative/path",
          "reason": "new" | "modified",
          "size_b": int,
          "mtime_b": float
        }
    """
    a_files = load_snapshot(snapshot_a)
    b_files = load_snapshot(snapshot_b)

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as f:
        for path, (size_b, mtime_b, md5_b) in b_files.items():
            info_a = a_files.get(path)
            if info_a is None:
                record = {
                    "path": path,
                    "reason": "new",
                    "size_b": size_b,
                    "mtime_b": mtime_b,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            size_a, mtime_a, md5_a = info_a

            # 先用 size + mtime 判断
            if size_a == size_b and mtime_a == mtime_b:
                continue

            # 如有需要，再用 md5 复核
            if check_md5 and md5_a and md5_b and md5_a == md5_b:
                # 内容相同，仅时间戳不同，视为未变化
                continue

            record = {
                "path": path,
                "reason": "modified",
                "size_b": size_b,
                "mtime_b": mtime_b,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "对比两个目录快照（A 与 B），输出 B 相比 A 新增或变化的文件清单。"
        )
    )
    parser.add_argument(
        "--snapshot-a",
        required=True,
        help="来自 A 机器的快照文件路径（JSON Lines）",
    )
    parser.add_argument(
        "--snapshot-b",
        required=True,
        help="在 B 机器上生成的快照文件路径（JSON Lines）",
    )
    parser.add_argument(
        "--output",
        default="diff_to_copy.jsonl",
        help="对比结果输出文件路径（JSON Lines，默认：diff_to_copy.jsonl）",
    )
    parser.add_argument(
        "--check-md5",
        action="store_true",
        help="在 size/mtime 不同且双方都有 md5 时，再用 md5 判定是否真正变化",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot_a = Path(args.snapshot_a)
    snapshot_b = Path(args.snapshot_b)
    if not snapshot_a.exists():
        raise SystemExit(f"快照文件不存在: {snapshot_a}")
    if not snapshot_b.exists():
        raise SystemExit(f"快照文件不存在: {snapshot_b}")

    compare_snapshots(
        snapshot_a=snapshot_a,
        snapshot_b=snapshot_b,
        output=Path(args.output),
        check_md5=args.check_md5,
    )


if __name__ == "__main__":
    main()

