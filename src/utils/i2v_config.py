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

# 默认生成参数（与原工作流模板一致）
DEFAULT_WIDTH = 480
DEFAULT_HEIGHT = 832
DEFAULT_FRAMES = 49  # 帧数（原项目默认49帧）
DEFAULT_STEPS = 6
DEFAULT_SEED = -1  # -1表示随机

# 默认提示词（原项目正负向提示词相同）
DEFAULT_POSITIVE_PROMPT = ""
DEFAULT_NEGATIVE_PROMPT = ""  # 与正向提示词保持一致

# LoRA默认配置
DEFAULT_LORA_NAME = ""  # 空字符串表示不使用风格LoRA
DEFAULT_LORA_STRENGTH = 1.0

# 可用的LoRA模型列表（从ComfyUI动态获取）
# 空字符串表示不使用风格LoRA
AVAILABLE_LORAS = [
    "(无风格LoRA)",
    "catwalk.safetensors",
    "wan-nsfw-e14-fixed.safetensors",
]

# 分辨率预设
RESOLUTION_PRESETS = [
    ("480p (480x832)", 480, 832),
    ("480p 横版 (832x480)", 832, 480),
    ("360p (360x640)", 360, 640),
    ("自定义", None, None),
]

# 采样器配置
SAMPLER_NAME = "euler"
SCHEDULER = "simple"
