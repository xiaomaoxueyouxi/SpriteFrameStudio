"""帧数据模型"""
from typing import Optional
from pathlib import Path
from enum import Enum
import numpy as np
from pydantic import BaseModel, Field, ConfigDict


class FrameStatus(str, Enum):
    """帧处理状态"""
    RAW = "raw"                    # 原始帧
    BACKGROUND_REMOVED = "bg_removed"  # 已去背景
    POSE_DETECTED = "pose_detected"    # 已检测姿势


class FrameData(BaseModel):
    """单帧数据模型"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    index: int = Field(..., description="帧序号")
    timestamp: float = Field(..., description="时间戳(秒)")
    
    # 图像数据 (numpy数组，不序列化)
    image: Optional[np.ndarray] = Field(default=None, exclude=True)
    processed_image: Optional[np.ndarray] = Field(default=None, exclude=True)
    
    # 文件路径 (用于持久化)
    image_path: Optional[Path] = Field(default=None, description="原始图像路径")
    processed_path: Optional[Path] = Field(default=None, description="处理后图像路径")
    
    # 状态
    status: FrameStatus = Field(default=FrameStatus.RAW, description="处理状态")
    is_selected: bool = Field(default=False, description="是否被选中")
    
    # 姿势数据引用ID
    pose_id: Optional[str] = Field(default=None, description="关联的姿势数据ID")
    
    # 轮廓数据引用ID
    contour_id: Optional[str] = Field(default=None, description="关联的轮廓数据ID")
    
    # 图像特征数据引用ID
    image_feature_id: Optional[str] = Field(default=None, description="关联的图像特征数据ID")
    
    # 分区域特征数据引用ID
    regional_feature_id: Optional[str] = Field(default=None, description="关联的分区域特征数据ID")
    
    @property
    def has_image(self) -> bool:
        """是否有图像数据"""
        return self.image is not None
    
    @property
    def has_processed(self) -> bool:
        """是否有处理后的图像"""
        return self.processed_image is not None
    
    @property
    def display_image(self) -> Optional[np.ndarray]:
        """获取用于显示的图像（优先处理后的）"""
        return self.processed_image if self.has_processed else self.image


class VideoInfo(BaseModel):
    """视频信息模型"""
    path: Path = Field(..., description="视频文件路径")
    width: int = Field(..., description="视频宽度")
    height: int = Field(..., description="视频高度")
    fps: float = Field(..., description="帧率")
    frame_count: int = Field(..., description="总帧数")
    duration: float = Field(..., description="时长(秒)")
    codec: str = Field(default="", description="编码格式")
    
    @property
    def resolution(self) -> str:
        """分辨率字符串"""
        return f"{self.width}x{self.height}"
    
    def format_duration(self) -> str:
        """格式化时长为 HH:MM:SS.mmm"""
        hours = int(self.duration // 3600)
        minutes = int((self.duration % 3600) // 60)
        seconds = self.duration % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
