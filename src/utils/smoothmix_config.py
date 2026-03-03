"""SmoothMix视频生成配置"""
from pathlib import Path

# ComfyUI服务器配置 (端口8188)
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
COMFYUI_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"
COMFYUI_WS_URL = f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}/ws"

# 工作流模板路径
WORKFLOW_TEMPLATE_PATH = Path(__file__).parent.parent.parent / "workflows" / "SmoothMix-FLF2V.json"

# 默认参数
DEFAULT_WIDTH = 368
DEFAULT_HEIGHT = 704
DEFAULT_FRAMES = 33
DEFAULT_FPS = 16
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

# SmoothMix目录路径 - 兼容调试和打包环境
def _get_smoothmix_dir():
    """动态检测 SmoothMix 目录路径"""
    # 先检查当前项目根目录下的 portable_output (调试模式)
    project_root = Path(__file__).parent.parent.parent
    debug_path = project_root / "portable_output" / "SpriteFrameStudio" / "Wan2.2-SmoothMix"
    if debug_path.exists():
        return debug_path
    
    # 检查同级目录 (打包模式: portable_output/SpriteFrameStudio/)
    packed_path = project_root / "Wan2.2-SmoothMix"
    if packed_path.exists():
        return packed_path
    
    # 默认返回调试路径
    return debug_path

SMOOTHMIX_DIR = _get_smoothmix_dir()
SMOOTHMIX_COMFYUI_DIR = SMOOTHMIX_DIR / "ComfyUI"
SMOOTHMIX_OUTPUT_DIR = SMOOTHMIX_COMFYUI_DIR / "output"
SMOOTHMIX_START_BAT = SMOOTHMIX_DIR / "开始.bat"
