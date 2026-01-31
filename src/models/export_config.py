"""导出配置模型"""
from typing import Optional, Tuple, List
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    """导出格式"""
    SPRITE_SHEET = "sprite_sheet"  # PNG精灵图 + JSON
    GIF = "gif"                    # GIF动画
    FRAMES = "frames"              # 单独的帧图片
    GODOT = "godot"                # Godot SpriteFrames (.tres)


class LayoutMode(str, Enum):
    """精灵图布局模式"""
    GRID = "grid"        # 网格排列
    HORIZONTAL = "horizontal"  # 水平排列
    VERTICAL = "vertical"      # 垂直排列


class ResampleFilter(str, Enum):
    """图像缩放算法"""
    NEAREST = "nearest"      # 最近邻（像素风格，速度最快）
    BOX = "box"              # 盒式滤波
    BILINEAR = "bilinear"    # 双线性插值（平滑，质量中等）
    HAMMING = "hamming"      # Hamming滤波
    BICUBIC = "bicubic"      # 双三次插值（高质量，速度较慢）
    LANCZOS = "lanczos"      # Lanczos滤波（最高质量，速度最慢）


class SpriteSheetConfig(BaseModel):
    """精灵图导出配置"""
    layout: LayoutMode = Field(default=LayoutMode.GRID, description="布局模式")
    columns: Optional[int] = Field(default=None, description="列数(仅grid模式)")
    padding: int = Field(default=0, description="帧之间的间距")
    frame_width: Optional[int] = Field(default=None, description="帧宽度(None为原始)")
    frame_height: Optional[int] = Field(default=None, description="帧高度(None为原始)")
    background_color: Tuple[int, int, int, int] = Field(
        default=(0, 0, 0, 0), 
        description="背景颜色(RGBA)"
    )
    generate_json: bool = Field(default=True, description="是否生成JSON元数据")
    resample_filter: ResampleFilter = Field(default=ResampleFilter.LANCZOS, description="缩放算法")


class GifConfig(BaseModel):
    """导出配置"""
    fps: float = Field(default=10.0, description="帧率")
    loop: int = Field(default=0, description="循环次数(0为无限)")
    optimize: bool = Field(default=True, description="是否优化文件大小")
    quality: int = Field(default=85, description="质量(1-100)")
    frame_width: Optional[int] = Field(default=None, description="帧宽度")
    frame_height: Optional[int] = Field(default=None, description="帧高度")
    resample_filter: ResampleFilter = Field(default=ResampleFilter.LANCZOS, description="缩放算法")


class GodotConfig(BaseModel):
    """Godot导出配置"""
    animation_name: str = Field(default="default", description="动画名称")
    fps: float = Field(default=10.0, description="播放帧率")
    loop: bool = Field(default=True, description="是否循环播放")
    export_individual_frames: bool = Field(default=True, description="是否导出单独帧文件")
    frame_width: Optional[int] = Field(default=None, description="帧宽度")
    frame_height: Optional[int] = Field(default=None, description="帧高度")
    resample_filter: ResampleFilter = Field(default=ResampleFilter.LANCZOS, description="缩放算法")


class ExportConfig(BaseModel):
    """导出配置模型"""
    format: ExportFormat = Field(default=ExportFormat.SPRITE_SHEET, description="导出格式")
    output_path: Optional[Path] = Field(default=None, description="输出路径")
    output_name: str = Field(default="sprite", description="输出文件名(不含扩展名)")
    
    # 精灵图配置
    sprite_config: SpriteSheetConfig = Field(
        default_factory=SpriteSheetConfig,
        description="精灵图配置"
    )
    
    # GIF配置
    gif_config: GifConfig = Field(
        default_factory=GifConfig,
        description="GIF配置"
    )
    
    # Godot配置
    godot_config: GodotConfig = Field(
        default_factory=GodotConfig,
        description="Godot配置"
    )
    
    # 选中的帧索引
    frame_indices: List[int] = Field(default_factory=list, description="要导出的帧索引")
    
    def get_output_file(self) -> Path:
        """获取输出文件完整路径"""
        if self.output_path is None:
            self.output_path = Path(".")
        
        if self.format == ExportFormat.GIF:
            return self.output_path / f"{self.output_name}.gif"
        elif self.format == ExportFormat.GODOT:
            return self.output_path / f"{self.output_name}.tres"
        else:
            return self.output_path / f"{self.output_name}.png"
    
    def get_json_file(self) -> Path:
        """获取JSON元数据文件路径"""
        if self.output_path is None:
            self.output_path = Path(".")
        return self.output_path / f"{self.output_name}.json"


class FrameRect(BaseModel):
    """精灵图中单帧的位置信息"""
    frame_index: int = Field(..., description="原始帧索引")
    x: int = Field(..., description="在精灵图中的x坐标")
    y: int = Field(..., description="在精灵图中的y坐标")
    width: int = Field(..., description="帧宽度")
    height: int = Field(..., description="帧高度")


class SpriteSheetMeta(BaseModel):
    """精灵图元数据"""
    image_path: str = Field(..., description="图片文件名")
    image_width: int = Field(..., description="精灵图总宽度")
    image_height: int = Field(..., description="精灵图总高度")
    frame_count: int = Field(..., description="帧数量")
    frames: List[FrameRect] = Field(default_factory=list, description="各帧位置信息")
