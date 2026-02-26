"""I2V视频生成配置"""
from pathlib import Path

# ComfyUI服务器配置
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
COMFYUI_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"
COMFYUI_WS_URL = f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}/ws"

# 生成模式
GENERATION_MODE_I2V = "i2v"  # 仅首帧
GENERATION_MODE_FLF2V = "flf2v"  # 首尾帧

# 工作流模板文件路径 - 统一使用FLF2V模板
# 当仅首帧时，尾帧设置为首帧相同图片即可
WORKFLOWS_DIR = Path(__file__).parent.parent.parent / "workflows"
WORKFLOW_TEMPLATE_PATH = WORKFLOWS_DIR / "WAN_2.2_FLF2V_lora.json"

# 默认生成参数
DEFAULT_WIDTH = 360
DEFAULT_HEIGHT = 704
DEFAULT_FRAMES = 49  # 帧数
DEFAULT_STEPS = 6
DEFAULT_SEED = -1  # -1表示随机

# 默认提示词
DEFAULT_POSITIVE_PROMPT = "女人正在走猫步,catwalk"
DEFAULT_NEGATIVE_PROMPT = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"

# LoRA默认配置
DEFAULT_LORA_NAME = "catwalk.safetensors"
DEFAULT_LORA_STRENGTH = 1.0

# 可用的LoRA模型列表（从ComfyUI动态获取）
# 这里是预设列表，实际运行时会从服务器获取
AVAILABLE_LORAS = [
    "catwalk.safetensors",
    "lightx2v_I2V_14B_480p_cfg_step_distill_rank32_bf16.safetensors",
    "wan-nsfw-e14-fixed.safetensors",
]

# 分辨率预设
RESOLUTION_PRESETS = [
    ("480p (360x704)", 360, 704),
    ("480p 横版 (704x360)", 704, 360),
    ("720p (540x1056)", 540, 1056),
    ("自定义", None, None),
]

# 采样器配置
SAMPLER_NAME = "euler"
SCHEDULER = "simple"
