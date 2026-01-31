"""帧数据管理模块"""
from typing import List, Optional, Dict
from pathlib import Path
import numpy as np

from src.models.frame_data import FrameData, FrameStatus
from src.models.pose_data import PoseData
from src.core.pose_detector import ContourData, ImageFeatureData, RegionalFeatureData


class FrameManager:
    """帧数据管理器 - 管理提取的帧集合"""
    
    def __init__(self):
        self._frames: List[FrameData] = []
        self._poses: Dict[str, PoseData] = {}  # pose_id -> PoseData
        self._contours: Dict[str, ContourData] = {}  # contour_id -> ContourData
        self._image_features: Dict[str, ImageFeatureData] = {}  # feature_id -> ImageFeatureData
        self._regional_features: Dict[str, RegionalFeatureData] = {}  # regional_id -> RegionalFeatureData
    
    @property
    def frame_count(self) -> int:
        """帧数量"""
        return len(self._frames)
    
    @property
    def frames(self) -> List[FrameData]:
        """所有帧"""
        return self._frames
    
    @property
    def selected_frames(self) -> List[FrameData]:
        """选中的帧"""
        return [f for f in self._frames if f.is_selected]
    
    @property
    def selected_count(self) -> int:
        """选中的帧数量"""
        return len(self.selected_frames)
    
    def clear(self):
        """清空所有帧"""
        self._frames.clear()
        self._poses.clear()
        self._contours.clear()
        self._image_features.clear()
        self._regional_features.clear()
    
    def add_frames(self, frames: List[FrameData]):
        """添加帧列表"""
        self._frames.extend(frames)
    
    def add_frame(self, frame: FrameData):
        """添加单帧"""
        self._frames.append(frame)
    
    def get_frame(self, index: int) -> Optional[FrameData]:
        """获取指定索引的帧"""
        if 0 <= index < len(self._frames):
            return self._frames[index]
        return None
    
    def remove_frame(self, index: int) -> bool:
        """删除指定索引的帧"""
        if 0 <= index < len(self._frames):
            frame = self._frames.pop(index)
            # 同时删除关联的姿势数据
            if frame.pose_id and frame.pose_id in self._poses:
                del self._poses[frame.pose_id]
            # 更新后续帧的索引
            for i in range(index, len(self._frames)):
                self._frames[i].index = i
            return True
        return False
    
    def select_frame(self, index: int, selected: bool = True):
        """选中/取消选中帧"""
        if 0 <= index < len(self._frames):
            self._frames[index].is_selected = selected
    
    def select_all(self):
        """选中所有帧"""
        for frame in self._frames:
            frame.is_selected = True
    
    def deselect_all(self):
        """取消所有选中"""
        for frame in self._frames:
            frame.is_selected = False
    
    def select_range(self, start: int, end: int):
        """选中范围内的帧"""
        for i in range(max(0, start), min(end + 1, len(self._frames))):
            self._frames[i].is_selected = True
    
    def get_frames_by_status(self, status: FrameStatus) -> List[FrameData]:
        """获取指定状态的帧"""
        return [f for f in self._frames if f.status == status]
    
    def update_frame_image(self, index: int, image: np.ndarray, processed: bool = False):
        """更新帧图像"""
        if 0 <= index < len(self._frames):
            if processed:
                self._frames[index].processed_image = image
                self._frames[index].status = FrameStatus.BACKGROUND_REMOVED
            else:
                self._frames[index].image = image
    
    def add_pose(self, pose: PoseData):
        """添加姿势数据"""
        self._poses[pose.id] = pose
        # 关联到帧
        if 0 <= pose.frame_index < len(self._frames):
            self._frames[pose.frame_index].pose_id = pose.id
            self._frames[pose.frame_index].status = FrameStatus.POSE_DETECTED
    
    def get_pose(self, pose_id: str) -> Optional[PoseData]:
        """获取姿势数据"""
        return self._poses.get(pose_id)
    
    def get_pose_for_frame(self, frame_index: int) -> Optional[PoseData]:
        """获取帧关联的姿势数据"""
        frame = self.get_frame(frame_index)
        if frame and frame.pose_id:
            return self._poses.get(frame.pose_id)
        return None
    
    def add_contour(self, contour: ContourData):
        """添加轮廓数据"""
        self._contours[contour.id] = contour
        # 关联到帧
        if 0 <= contour.frame_index < len(self._frames):
            self._frames[contour.frame_index].contour_id = contour.id
    
    def get_contour(self, contour_id: str) -> Optional[ContourData]:
        """获取轮廓数据"""
        return self._contours.get(contour_id)
    
    def get_contour_for_frame(self, frame_index: int) -> Optional[ContourData]:
        """获取帧关联的轮廓数据"""
        frame = self.get_frame(frame_index)
        if frame and frame.contour_id:
            return self._contours.get(frame.contour_id)
        return None
    
    def add_image_feature(self, feature: ImageFeatureData):
        """添加图像特征数据"""
        self._image_features[feature.id] = feature
        # 关联到帧
        if 0 <= feature.frame_index < len(self._frames):
            self._frames[feature.frame_index].image_feature_id = feature.id
    
    def get_image_feature(self, feature_id: str) -> Optional[ImageFeatureData]:
        """获取图像特征数据"""
        return self._image_features.get(feature_id)
    
    def get_image_feature_for_frame(self, frame_index: int) -> Optional[ImageFeatureData]:
        """获取帧关联的图像特征数据"""
        frame = self.get_frame(frame_index)
        if frame and frame.image_feature_id:
            return self._image_features.get(frame.image_feature_id)
        return None
    
    def add_regional_feature(self, feature: RegionalFeatureData):
        """添加分区域特征数据"""
        self._regional_features[feature.id] = feature
        # 关联到帧
        if 0 <= feature.frame_index < len(self._frames):
            self._frames[feature.frame_index].regional_feature_id = feature.id
    
    def get_regional_feature(self, feature_id: str) -> Optional[RegionalFeatureData]:
        """获取分区域特征数据"""
        return self._regional_features.get(feature_id)
    
    def get_regional_feature_for_frame(self, frame_index: int) -> Optional[RegionalFeatureData]:
        """获取帧关联的分区域特征数据"""
        frame = self.get_frame(frame_index)
        if frame and hasattr(frame, 'regional_feature_id') and frame.regional_feature_id:
            return self._regional_features.get(frame.regional_feature_id)
        return None
    
    def get_frames_with_images(self) -> List[FrameData]:
        """获取有图像数据的帧"""
        return [f for f in self._frames if f.has_image]
    
    def reorder_frames(self, new_order: List[int]):
        """重新排序帧"""
        if len(new_order) != len(self._frames):
            return
        
        new_frames = []
        for i, old_index in enumerate(new_order):
            if 0 <= old_index < len(self._frames):
                frame = self._frames[old_index]
                frame.index = i
                new_frames.append(frame)
        
        self._frames = new_frames
