"""SmoothMix视频生成配置"""
from pathlib import Path

# ComfyUI服务器配置 (端口8189，与I2V的8188区分)
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8189
COMFYUI_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"
COMFYUI_WS_URL = f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}/ws"

# 工作流模板路径
WORKFLOW_TEMPLATE_PATH = Path(__file__).parent.parent.parent / "workflows" / "SmoothMix-FLF2V.json"

# 默认参数
DEFAULT_WIDTH = 368
DEFAULT_HEIGHT = 704
DEFAULT_FRAMES = 33
DEFAULT_STEPS = 4
DEFAULT_POSITIVE_PROMPT = "镜头跟随，缓慢走路"
DEFAULT_NEGATIVE_PROMPT = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"

# 分辨率预设
RESOLUTION_PRESETS = [
    ("368x704 (竖屏)", 368, 704),
    ("480x854 (竖屏)", 480, 854),
    ("544x960 (竖屏)", 544, 960),
    ("640x360 (横屏)", 640, 360),
    ("720x480 (横屏)", 720, 480),
    ("自定义", None, None),
]

# 节点ID映射
NODE_IDS = {
    "start_image": "237",
    "end_image": "238",
    "positive_prompt": "241",
    "negative_prompt": "240",
    "width": "252",
    "height": "253",
    "frames": "285",
    "steps": "254",
    "seed": "229",
    "video_output": "236",
}

# SmoothMix目录路径
SMOOTHMIX_DIR = Path(__file__).parent.parent.parent.parent / "portable_output" / "SpriteFrameStudio" / "Wan2.2-SmoothMix"
SMOOTHMIX_COMFYUI_DIR = SMOOTHMIX_DIR / "ComfyUI"
SMOOTHMIX_OUTPUT_DIR = SMOOTHMIX_COMFYUI_DIR / "output"
SMOOTHMIX_START_BAT = SMOOTHMIX_DIR / "开始.bat"
