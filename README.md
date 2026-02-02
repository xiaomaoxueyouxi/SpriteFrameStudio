# SpriteFrameStudio - 精灵帧工作室

作者：小猫学游戏
QQ反馈群：722160123

## 项目介绍

**SpriteFrameStudio** 是一款功能强大的视频处理工具，专为游戏开发、动画制作和精灵图素材提取设计。它集成了先进的 AI 姿势检测、背景去除和图像优化功能，能够帮助用户快速从视频中提取高质量的帧序列，轻松制作游戏精灵图和动画素材。

### 核心功能

*   **智能帧提取**：支持自定义 FPS 和时间范围，精准提取视频片段。
*   **多模式分析**：
    *   **RTMPose 姿势检测**：利用高性能 AI 模型识别人物动作。
    *   **分区域 SSIM 比对**：针对动漫或特定场景的精细化相似度分析（可重点关注下半身）。
    *   **轮廓与图像匹配**：多种算法辅助寻找循环动作或剔除重复帧。
*   **背景处理**：
    *   **AI 智能抠图**：内置模型自动去除背景（支持 GPU 加速）。
    *   **传统颜色过滤**：支持绿幕、蓝幕等预设及自定义颜色剔除。
*   **图像后期优化**：
    *   **批量缩放**：保持比例或强制尺寸。
    *   **边缘优化**：平滑边缘，去除毛刺。
    *   **描边与裁剪**：自动为提取的对象添加描边，并裁剪多余空白区域。
*   **高效导出**：支持批量处理与多种导出格式。

## 视频教程

【AI帧动画工作流 开源 免费 本地部署 新鲜出炉】

 https://www.bilibili.com/video/BV1wK6GBuEVm/?share_source=copy_web&vd_source=705693c5674b2f7443dd56434b347847

---

## 安装教程

### 整合包（下载解压即用 运行run.bat）
------
第三版 整合包下载

20260202版整合包下载：
https://pan.quark.cn/s/23f4904da358

------
第三版 发布日期 2026-02-01

该版本是更新包，需要在第二版的基础上更新，包体积较小
https://pan.quark.cn/s/da47347a9d9b

使用说明：解压到程序根目录，并覆盖

更新说明：

功能更新：

1、增加【图像增强】（高清修复），用于对不清晰的视频进行帧 超分辨率高清修复

用到的开源库：https://github.com/xinntao/Real-ESRGAN

2、增加【单帧导出】，可以双击帧进行单张导出，也可以在导出中，选择导出单帧，批量导出

3、增加【视频区间选择】该功能由 Grealt 提供，为此表示感谢

优化

1、修复H264视频只能提取第一帧的问题

2、优化抽帧和播放流畅度

3、修复视频区间选择无法循环播放的问题


------
第二版 发布日期 2026-1-29 21:26

https://pan.quark.cn/s/6b6af66be508
解决姿势识别找不到 rtmlib 问题
------

第一版：发布日期 2026-01-29

整合包地址：
下载链接：已删除

------



### 环境要求（没有二次开发需求的就不要往下看了）

* **Anaconda** 或 **Miniconda**

  **官网下载**：

  - Anaconda：https://www.anaconda.com/download
  - Miniconda（轻量版）：https://docs.conda.io/en/latest/miniconda.html

网盘链接：https://pan.quark.cn/s/b7f280b54717


  **安装说明**：

  - Windows：下载 `.exe` 安装程序，按默认选项安装即可
  - Linux/macOS：下载 `.sh` 脚本，执行 `bash Miniconda3-latest-*.sh` 安装
  - 安装完成后需**重启终端**使 `conda` 命令生效

* **Python**：3.9.19 或 3.9.25（由 Anaconda 自动管理）

* **CUDA 和 cuDNN**（GPU 加速必需）：

  - CUDA 12.4
  - cuDNN 9.10.2
  - 由 `environment_gpu.yml` 自动安装

> 💡 **GPU 加速说明**：本项目支持 NVIDIA GPU 加速处理（如背景去除、姿势检测等），可显著提升处理速度。如无 GPU，程序将自动降级到 CPU 模式。

### 方式一：在线安装（推荐）

**适用系统**：Windows、Linux、macOS（Python 环境支持的系统）

#### 步骤 1：创建 Conda 环境

```bash
# 删除旧环境（如果存在）
conda env remove --name spriteframe_gpu -y

# 从 environment_gpu.yml 创建新环境
conda env create -f environment_gpu.yml

# 激活环境
conda activate spriteframe_gpu
```

#### 步骤 2：清理依赖冲突

由于 `rembg` 的依赖问题，安装时会同时安装 CPU 版本的 onnxruntime，需要清理：

```bash
# 卸载两个版本
pip uninstall onnxruntime onnxruntime-gpu -y

# 只装 GPU 版本
pip install onnxruntime-gpu==1.19.2

# 验证 GPU 支持
python -c "import onnxruntime as ort; print('GPU Providers:', ort.get_available_providers())"
```

输出应包含 `CUDAExecutionProvider`，表示 GPU 配置成功。

#### 步骤 3：启动程序

```bash
python src/main.py
```

---

### 方式二：离线安装（conda pack）

**适用系统**：**仅限 Windows** （因为导出的环境包是从 Windows 系统生成的）

> ⚠️ **重要提示**：由于 conda pack 导出的环境包包含平台特定的二进制文件和路径，**不同操作系统的环境包不可互用**。本方案仅适用于 Windows 系统。

环境包下载地址：

通过网盘分享的文件：spriteframe.rar
链接: https://pan.baidu.com/s/1q5Wr0_fGPQ-4hM6kKr0RIQ?pwd=game 提取码: game 

#### 步骤 1：解压环境包

```bash
# 找到 Anaconda 的 envs 目录
# 通常位置：C:\Users\{用户名}\anaconda3\envs
# 或 C:\Users\{用户名}\miniconda3\envs

# 使用 7-Zip、WinRAR 或命令行解压
# 如果使用 WSL 或 git bash：
tar -xzf spriteframe_gpu.tar.gz -C "C:\Users\{用户名}\anaconda3\envs\spriteframe_gpu"

# 或直接在 Explorer 中用 7-Zip 解压到 envs 目录
```

#### 步骤 2：激活环境

```bash
# Anaconda 会自动识别 envs 目录中的环境
conda activate spriteframe_gpu
```

#### 步骤 3：启动程序

```bash
python src/main.py
```

---

### 环境包导出（供参考）

如需导出当前工作的 GPU 环境以供他人在同系统使用：

```bash
# 1. 激活环境
conda activate spriteframe_gpu

# 2. 安装 conda-pack（如果未安装）
conda install -c conda-forge conda-pack

# 3. 导出环境
conda pack -n spriteframe_gpu -o spriteframe_gpu.tar.gz

# 输出文件：spriteframe_gpu.tar.gz（大约 5-10 GB）
```

**导出后的 environment.yml 说明**：

- 包含所有 CUDA 工具链和 cuDNN
- PyTorch GPU 版本（2.5.1）
- onnxruntime-gpu 和其他依赖
- 需要手动卸载 onnxruntime（CPU版）后才能正常运行

---

## 运行程序

### 启动 GUI

#### 方式一：一键启动（推荐 ⭐）

**Windows 用户**：

1. 编辑项目根目录的 `run.bat` 文件，修改第 5 行的 Miniconda 路径：

   ```batch
   set "CONDA_PATH=E:\software\miniconda"
   ```

   > 💡 查询你的 Miniconda 路径：打开 Anaconda Prompt，执行 `echo %CONDA_PREFIX%`

2. 双击 `run.bat` 或在 PowerShell 中执行：

   ```powershell
   .\run.bat
   ```

3. 应用会自动启动，首次启动可能需要等待 10-30 秒

#### 方式二：命令行启动

```bash
# 确保环境已激活
conda activate spriteframe

# 启动应用
python src/main.py
```

### 操作流程

1. **加载视频**：选择要处理的视频文件，设置提取范围和 FPS。
2. **提取帧**：点击"提取帧"按钮获取视频帧。
3. **动作分析**：选择检测模式（RTMPose/SSIM/轮廓），分析并标记相似/重复帧。
4. **背景处理**：使用 AI 抠图或颜色过滤清理背景。
5. **后期优化**：调整边缘、描边、缩放等参数。
6. **导出结果**：选择导出格式和路径，生成最终素材。

---

## 常见问题

### Q： 姿势识别提示  找不到rtmlib 

**解决方案**：

下载rtmlib 到 根目录，然后解压到当前文件夹
https://pan.quark.cn/s/a9c9502b0302

### Q: GPU 加速失效，提示"GPU 初始化失败，已回退到 CPU"

**解决方案**：

```bash
# 检查 onnxruntime 版本
pip show onnxruntime onnxruntime-gpu

# 卸载两个都卸载
pip uninstall onnxruntime onnxruntime-gpu -y

# 只装 GPU 版本
pip install onnxruntime-gpu==1.19.2

# 验证 GPU 支持
python -c "import onnxruntime as ort; print('GPU Providers:', ort.get_available_providers())"

```

### Q: 环境创建失败，报错"gbk codec can't decode byte 0xff"

**原因**：Windows 系统上 environment_gpu.yml 文件编码问题

**解决方案**：

```powershell
# 用 PowerShell 转换文件编码为 UTF-8 无 BOM
$file = "environment_gpu.yml"
$content = Get-Content $file -Encoding UTF8
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($file, $content, $utf8NoBom)
```

### Q: 如何在 Linux/macOS 上使用本项目？

本项目的离线包仅支持 Windows。对于 Linux/macOS，请使用**在线安装方式**，但需要：

- 手动安装 CUDA 12.4 和 cuDNN 9.10.2
- 使用 `environment_gpu.yml` 创建环境（需要修改 Windows 特定的依赖）

---

## 开源协议

本项目采用 **[CC BY 4.0（署名4.0国际）](https://creativecommons.org/licenses/by/4.0/deed.zh)** 开源协议。

### 协议说明

**CC BY 4.0** 要求：

- ✅ **允许商用**：可用于商业项目
- ✅ **允许修改**：可以自由修改和衍生
- ✅ **允许分发**：可以分发和共享
- **✅ 必须署名**：任何使用或衍生作品必须明显标注原作者名字

**署名方式示例**：

```
本项目基于 SpriteFrameStudio 开发
原作者：小猫学游戏
原项目：https://github.com/game-cat/SpriteFrameStudio
```

### 第三方组件协议

本项目使用了以下开源组件，请遵守其各自的协议：

| 组件        | 协议       | 说明                             |
| ----------- | ---------- | -------------------------------- |
| **RTMPose** | Apache 2.0 | 代码开源，模型权重仅限非商业用途 |
| **rembg**   | MIT        | 背景去除库                       |
| **PyTorch** | BSD        | 深度学习框架                     |
| **OpenCV**  | Apache 2.0 | 计算机视觉库                     |
| **PySide6** | LGPL       | Qt Python 绑定                   |

**特别提醒**：RTMPose 的预训练模型受 COCO 等数据集限制，**商业使用前请联系 [OpenMMLab](https://github.com/open-mmlab/mmpose) 确认许可**。

---

## 模型文件

本项目使用以下 ONNX 格式的预训练模型进行 AI 推理：

模型文件下载：通过网盘分享的文件：models.rar

链接：https://pan.quark.cn/s/b0db432774db

下载后解压到项目根目录

### RTMPose 姿势检测模型

用于人物骨骼关键点检测，支持 3 种精度模式：

| 模式            | 检测模型   | 姿态模型        | 模型大小 | 性能 | 推荐场景                 |
| --------------- | ---------- | --------------- | -------- | ---- | ------------------------ |
| **Performance** | YOLOX-M    | RTMPose-X-Large | ~350MB   | 最快 | 实时处理，对精度要求不高 |
| **Balanced**    | YOLOX-M    | RTMPose-X-Large | ~350MB   | 中等 | 通用场景，平衡性能和精度 |
| **Lightweight** | YOLOX-Tiny | RTMPose-M       | ~100MB   | 最慢 | 低端设备，严格限制内存   |

**模型文件需要手动放置**：将下载的模型文件放在 `models/` 目录中

**模型目录结构示例**：

```
SpriteFrameStudio/
├── models/
│   ├── yolox_m_8xb8-300e_coco.onnx
│   ├── rtmpose_x_onnx_model.onnx
│   └── ...（其他模型文件）
└── ...
```

### 背景去除模型

用于 AI 智能抠图：

| 模型              | 大小   | 说明                   |
| ----------------- | ------ | ---------------------- |
| **U2Net**         | 176MB  | 通用背景分割           |
| **U2Net Human**   | 176MB  | 人像专用分割           |
| **Silueta**       | 43MB   | 轻量级，轮廓精细       |
| **ISNet Anime**   | 176MB  | 动漫角色专用           |
| **BRIA RMBG 2.0** | 100MB+ | 高精度背景移除（推荐） |

**模型位置**：放在项目根目录的 `models/` 文件夹中

**首次使用**：如果对应的模型文件不存在，程序会提示下载或从默认位置加载

---

## 推理引擎

### ONNX Runtime

本项目使用 **ONNX Runtime 1.19.2** 作为模型推理引擎。

**ONNX Runtime 说明**：

- **ONNX Runtime CPU**：纯 CPU 推理，速度较慢
- **ONNX Runtime GPU**（本项目使用）：利用 NVIDIA CUDA 加速推理，速度快 5-10 倍

**GPU 加速原理**：

- 依赖 **CUDA 12.4** 和 **cuDNN 9.10.2**
- 在 `environment_gpu.yml` 中自动配置
- 自动检测 GPU 设备（GTX/RTX 系列）

**性能对比**（以背景去除为例）：

| 设备     | RTX 3060 Ti | CPU (i7-9700K) |
| -------- | ----------- | -------------- |
| 处理速度 | ~200ms/张   | ~2000ms/张     |
| 加速比   | **10倍**    | -              |

**验证 GPU 支持**：

```python
import onnxruntime as ort
providers = ort.get_available_providers()
print("可用推理器:", providers)
# 输出应包含: 'CUDAExecutionProvider'
```



欢迎提交 Issue 或 Pull Request 来改进本项目！

---

*Created by 小猫学游戏*