"""配置管理"""
from pathlib import Path
from typing import Optional
import json


class Config:
    """应用配置 - 集中管理所有默认值"""
    
    # ==================== 路径配置 ====================
    TEMP_DIR = Path("resources/temp")
    
    # ==================== 提取设置 ====================
    EXTRACT_FPS_DEFAULT = 10.0
    EXTRACT_FPS_MIN = 0.1
    EXTRACT_FPS_MAX = 60.0
    
    # ==================== 分析设置 ====================
    SIMILARITY_DEFAULT = 90  # 相似度阈值 %
    SIMILARITY_MIN = 50
    SIMILARITY_MAX = 99
    
    INTERVAL_DEFAULT = 10  # 帧间隔
    INTERVAL_MIN = 1
    INTERVAL_MAX = 30
    
    # 帧管理间隔选帧
    FRAME_INTERVAL_DEFAULT = 2  # 间隔选帧默认值
    FRAME_INTERVAL_MAX = 100
    
    # ==================== 缩放设置 ====================
    SCALE_PERCENT_DEFAULT = 50  # 缩放比例 %
    SCALE_PERCENT_MIN = 10
    SCALE_PERCENT_MAX = 200
    
    SCALE_WIDTH_DEFAULT = 512
    SCALE_HEIGHT_DEFAULT = 512
    SCALE_SIZE_MIN = 1
    SCALE_SIZE_MAX = 4096
    
    # ==================== 背景处理设置 ====================
    # 颜色过滤
    COLOR_FEATHER_DEFAULT = 0  # 羽化
    COLOR_FEATHER_MAX = 20
    
    DENOISE_DEFAULT = 1  # 去噪
    DENOISE_MAX = 10
    
    # 绿幕默认 HSV 范围
    GREENSCREEN_H_MIN = 35
    GREENSCREEN_H_MAX = 85
    GREENSCREEN_S_MIN = 50
    GREENSCREEN_S_MAX = 255
    GREENSCREEN_V_MIN = 50
    GREENSCREEN_V_MAX = 255
    
    SPILL_DEFAULT = 0  # 溢色
    SPILL_MAX = 100
    
    # 边缘优化
    EDGE_ERODE_DEFAULT = 0  # 边缘收缩
    EDGE_ERODE_MAX = 10
    
    # ==================== 导出设置 ====================
    # PNG 压缩
    PNG_QUALITY_DEFAULT = 80
    PNG_QUALITY_MIN = 40
    PNG_QUALITY_MAX = 100
    
    # WebP
    WEBP_QUALITY_DEFAULT = 80
    WEBP_QUALITY_MIN = 1
    WEBP_QUALITY_MAX = 100
    
    # 精灵图
    SPRITE_COLS_DEFAULT = 4
    SPRITE_COLS_MAX = 100
    
    FRAME_WIDTH_DEFAULT = 128
    FRAME_HEIGHT_DEFAULT = 128
    FRAME_SIZE_MIN = 1
    FRAME_SIZE_MAX = 4096
    
    PADDING_DEFAULT = 0  # 间距
    PADDING_MAX = 100
    
    RESAMPLE_DEFAULT = "lanczos"  # 缩放算法
    
    # GIF
    GIF_FPS_DEFAULT = 10.0
    GIF_FPS_MAX = 60.0
    
    GIF_LOOP_DEFAULT = 0  # 0 = 无限循环
    GIF_LOOP_MAX = 100
    
    GIF_WIDTH_DEFAULT = 256
    GIF_HEIGHT_DEFAULT = 256
    GIF_SIZE_MAX = 2048
    
    GIF_OPTIMIZE_DEFAULT = True  # 优化文件大小
    
    # ==================== 魔棒工具 ====================
    MAGICWAND_TOLERANCE_DEFAULT = 32
    MAGICWAND_TOLERANCE_MAX = 255
    
    # ==================== UI 设置 ====================
    THUMBNAIL_SIZE_DEFAULT = 128
    MAX_ZOOM = 32.0
    MIN_ZOOM = 0.1
    
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or Path("config.json")
        self._data = {}
        self._load()
    
    def _load(self):
        """加载配置"""
        if self._config_path.exists():
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
    
    def save(self):
        """保存配置"""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get(self, key: str, default=None):
        """获取配置值"""
        return self._data.get(key, default)
    
    def set(self, key: str, value):
        """设置配置值"""
        self._data[key] = value
    
    # ==================== 持久化配置属性 ====================
    
    @property
    def last_video_dir(self) -> str:
        """上次打开视频的目录"""
        return self.get("last_video_dir", "")
    
    @last_video_dir.setter
    def last_video_dir(self, value: str):
        self.set("last_video_dir", value)
        self.save()
    
    @property
    def last_export_dir(self) -> str:
        """上次导出的目录"""
        return self.get("last_export_dir", "")
    
    @last_export_dir.setter
    def last_export_dir(self, value: str):
        self.set("last_export_dir", value)
        self.save()
    
    @property
    def extract_fps(self) -> float:
        """提取帧率"""
        return self.get("extract_fps", self.EXTRACT_FPS_DEFAULT)
    
    @extract_fps.setter
    def extract_fps(self, value: float):
        self.set("extract_fps", value)
        self.save()


# 全局配置实例
config = Config()
