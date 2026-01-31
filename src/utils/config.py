"""配置管理"""
from pathlib import Path
from typing import Optional
import json


class Config:
    """应用配置"""
    
    # 默认配置
    DEFAULT_EXTRACT_FPS = 10.0
    DEFAULT_BACKGROUND_MODE = "ai"
    DEFAULT_EXPORT_FORMAT = "sprite_sheet"
    DEFAULT_GIF_FPS = 10.0
    DEFAULT_THUMBNAIL_SIZE = 128
    
    # 临时文件目录
    TEMP_DIR = Path("resources/temp")
    
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
        return self.get("extract_fps", self.DEFAULT_EXTRACT_FPS)
    
    @extract_fps.setter
    def extract_fps(self, value: float):
        self.set("extract_fps", value)
        self.save()


# 全局配置实例
config = Config()
