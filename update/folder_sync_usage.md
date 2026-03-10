## 目录对比与同步脚本使用说明

本文件配合以下三个脚本一起使用（放在同一文件夹即可）：

- `snapshot_dir.py`：生成目录快照
- `compare_snapshots.py`：对比两个快照，生成差异清单
- `collect_diff_files.py`：按清单复制需要同步的文件

你可以把这 4 个文件（3 个 `.py` + 这个 `.md`）拷到任意位置单独使用，与本项目无强依赖。

---

## 一、在两台电脑上生成目录快照

在 **A 电脑** 和 **B 电脑** 上分别执行（注意根目录不同）。

### 1. A 电脑：生成快照 A

在命令行中进入脚本所在目录，例如：

```
python update/snapshot_dir.py --root . --exclude ./Wan2.2-SmoothMix --output update/snapshot.jsonl
```

```bash
cd D:\tools\folder_sync
python snapshot_dir.py --root "D:\GameAssets" --output "snapshot_A.jsonl"
```

```
python "C:\git\SpriteFrameStudio\update\snapshot_dir.py" `
  --root "C:\git\SpriteFrameStudio" `
  --output "snapshot_this_pc.jsonl"
```

- `--root`：要对比的根目录（比如整个工程或资源目录）。
- `--output`：快照文件名（可自定义）。
- 可选：`--with-md5`，如果想同时计算 MD5，可加上此参数（会更慢）：

```bash
python snapshot_dir.py --root "D:\GameAssets" --output "snapshot_A.jsonl" --with-md5
```

将生成的 `snapshot_A.jsonl` 拷贝到 **B 电脑**（U 盘、网盘均可）。

### 2. B 电脑：生成快照 B

同样在 B 电脑上执行，例如：

```bash
cd E:\tools\folder_sync
python snapshot_dir.py --root "E:\GameAssets" --output "snapshot_B.jsonl"
```

注意：这里的 `--root` 必须是你在 B 机器上实际存放对应文件的根目录。

---

## 二、在 B 电脑上对比快照，生成差异清单

确保 B 电脑上同时存在：

- 从 A 电脑拷过来的 `snapshot_A.jsonl`
- B 电脑自己生成的 `snapshot_B.jsonl`

在脚本目录执行：

```
python update/compare_snapshots.py --snapshot-a update/A.jsonl --snapshot-b update/B.jsonl --output update/diff_result.jsonl
```

```bash
python compare_snapshots.py ^
  --snapshot-a "D:\from_A\snapshot_A.jsonl" ^
  --snapshot-b "E:\GameAssets\snapshot_B.jsonl" ^
  --output "diff_to_copy.jsonl"
```

参数说明：

- `--snapshot-a`：来自 A 机器的快照文件路径。
- `--snapshot-b`：B 机器生成的快照文件路径。
- `--output`：对比后的差异清单（JSON Lines 格式）。

可选：如果两边快照都包含 MD5，并且你想更严格一点，可以加 `--check-md5`：

```bash
python compare_snapshots.py ^
  --snapshot-a "D:\from_A\snapshot_A.jsonl" ^
  --snapshot-b "E:\GameAssets\snapshot_B.jsonl" ^
  --output "diff_to_copy.jsonl" ^
  --check-md5
```

生成的 `diff_to_copy.jsonl` 中，每一行是一条差异记录，至少包含：

- `path`：相对路径（以 `/` 分隔）
- `reason`：`"new"` 或 `"modified"`

---

## 三、在 B 电脑上按清单复制需要同步的文件

有了差异清单 `diff_to_copy.jsonl` 后，可以把 B 侧“新增/变化”的文件复制到一个单独的打包目录中，保持原有目录结构，方便拷贝到 A 机器覆盖。

示例：

``````python
python update/collect_diff_files.py --root-b . --diff-file update/diff_result.jsonl --target-dir update/sync_files
``````


```bash
python collect_diff_files.py ^
  --root-b "E:\GameAssets" ^
  --diff-file "diff_to_copy.jsonl" ^
  --target-dir "E:\to_sync_for_A"
```

参数说明：

- `--root-b`：B 机器上的根目录，必须与生成 `snapshot_B.jsonl` 时的 `--root` 保持一致。
- `--diff-file`：上一步生成的 `diff_to_copy.jsonl`。
- `--target-dir`：要输出的目标根目录（脚本会在此目录下自动创建子目录并复制文件）。

这个命令执行后，`E:\to_sync_for_A` 中就只包含 **需要同步给 A 机器** 的那部分文件，并保留完整目录结构。你可以：

- 直接把 `E:\to_sync_for_A` 整个文件夹拷到 A 机器并覆盖对应目录，或者
- 把它打成压缩包再拷过去。

### 先试运行（不真正复制）

如果你想先看看会复制哪些文件，可以加 `--dry-run` 参数：

```bash
python collect_diff_files.py ^
  --root-b "E:\GameAssets" ^
  --diff-file "diff_to_copy.jsonl" ^
  --target-dir "E:\to_sync_for_A" ^
  --dry-run
```

此时脚本只会在控制台打印类似：

```text
[DRY-RUN] E:\GameAssets\foo\bar.png -> E:\to_sync_for_A\foo\bar.png
```

确认无误后，去掉 `--dry-run` 再执行一次即可真正复制。

---

## 四、常用参数小结

### snapshot_dir.py

- `--root`：要扫描的根目录（必选）。
- `--output`：快照文件路径，默认 `snapshot.jsonl`。
- `--with-md5`：是否计算 MD5（可选，默认不算）。
- `--md5-large-threshold`：只对小于该大小（字节）的文件算 MD5，默认 `100MB`，设为 `0` 表示所有文件都算。
- `--follow-symlinks`：是否跟随符号链接（默认不跟随）。

### compare_snapshots.py

- `--snapshot-a`：A 机器的快照文件路径。
- `--snapshot-b`：B 机器的快照文件路径。
- `--output`：差异清单输出路径，默认 `diff_to_copy.jsonl`。
- `--check-md5`：当 size/mtime 不同且 A/B 都有 MD5 时，再用 MD5 判断是否真正变化。

### collect_diff_files.py

- `--root-b`：B 机器上的根目录（生成 snapshot_B 时的 root）。
- `--diff-file`：差异清单文件路径。
- `--target-dir`：复制文件的目标根目录。
- `--dry-run`：仅打印将要复制的文件，不真正复制。
