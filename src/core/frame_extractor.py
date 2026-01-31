"""帧提取器模块"""
from typing import List, Optional, Callable
from pathlib import Path
import cv2
import numpy as np

from src.models.frame_data import FrameData, VideoInfo


class FrameExtractor:
    """帧提取器 - 从视频中按指定参数提取帧"""
    
    def __init__(self):
        self._cancel_flag = False
    
    def cancel(self):
        """取消提取操作"""
        self._cancel_flag = True
    
    def _check_seek_available(self, cap: cv2.VideoCapture, video_fps: float) -> bool:
        """检查视频是否支持帧定位"""
        # 模拟实际抽帧场景：先定位到0，再定位到非0帧
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        cap.read()  # 读取一帧，模拟实际流程
        
        # 尝试定位到第1秒的位置
        target_frame = int(1.0 * video_fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        actual_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
        
        # 重置到开头
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        # 只有当实际位置接近目标位置时才认为支持定位
        return actual_pos >= 0 and abs(actual_pos - target_frame) <= 1
    
    def extract_frames(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        extract_fps: float,
        video_info: VideoInfo,
        progress_callback: Optional[Callable[[int, int, float], None]] = None
    ) -> List[FrameData]:
        """
        从视频中提取帧
        
        Args:
            video_path: 视频文件路径
            start_time: 开始时间(秒)
            end_time: 结束时间(秒)
            extract_fps: 提取帧率(每秒多少帧)
            video_info: 视频信息
            progress_callback: 进度回调 (current, total, percent)
        
        Returns:
            提取的帧数据列表
        """
        self._cancel_flag = False
        frames: List[FrameData] = []
        
        # 打开视频
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"无法打开视频文件: {video_path}")
        
        try:
            # 计算需要提取的帧
            video_fps = video_info.fps
            duration = end_time - start_time
            
            # 计算每帧的时间间隔
            frame_interval = 1.0 / extract_fps
            
            # 生成时间戳列表
            timestamps = []
            current_time = start_time
            while current_time <= end_time:
                timestamps.append(current_time)
                current_time += frame_interval
            
            total_frames = len(timestamps)
            
            # 检测是否支持帧定位
            seek_available = self._check_seek_available(cap, video_fps)
            
            if not seek_available:
                # 如果不支持定位，重新打开视频以确保状态干净
                cap.release()
                cap = cv2.VideoCapture(video_path)
            
            if seek_available:
                # 正常模式：使用帧定位
                for idx, timestamp in enumerate(timestamps):
                    if self._cancel_flag:
                        break
                    
                    # 计算对应的视频帧号
                    frame_number = int(timestamp * video_fps)
                    
                    # 定位到指定帧
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                    ret, frame = cap.read()
                    
                    if ret:
                        # BGR转RGB
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        frame_data = FrameData(
                            index=idx,
                            timestamp=timestamp,
                            image=frame_rgb
                        )
                        frames.append(frame_data)
                    
                    # 进度回调
                    if progress_callback:
                        progress = (idx + 1) / total_frames * 100
                        progress_callback(idx + 1, total_frames, progress)
            else:
                # 顺序模式：一次性遍历视频，提取所需帧
                # 计算需要提取的帧号集合
                target_frames = {int(ts * video_fps): (idx, ts) for idx, ts in enumerate(timestamps)}
                current_frame = 0
                
                while True:
                    if self._cancel_flag:
                        break
                    
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    if current_frame in target_frames:
                        idx, timestamp = target_frames[current_frame]
                        # BGR转RGB
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        frame_data = FrameData(
                            index=idx,
                            timestamp=timestamp,
                            image=frame_rgb
                        )
                        frames.append(frame_data)
                        
                        # 进度回调
                        if progress_callback:
                            progress = len(frames) / total_frames * 100
                            progress_callback(len(frames), total_frames, progress)
                        
                        # 如果所有帧都提取完成，提前退出
                        if len(frames) >= total_frames:
                            break
                    
                    current_frame += 1
            
        finally:
            cap.release()
        
        return frames
    
    def extract_single_frame(
        self,
        video_path: str,
        timestamp: float,
        video_fps: float
    ) -> Optional[np.ndarray]:
        """提取单帧"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        
        try:
            frame_number = int(timestamp * video_fps)
            
            # 尝试帧定位
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            actual_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
            
            if actual_pos < 0:
                # 定位失败，重新打开并顺序读取
                cap.release()
                cap = cv2.VideoCapture(video_path)
                for _ in range(frame_number):
                    if not cap.read()[0]:
                        return None
            
            ret, frame = cap.read()
            
            if ret:
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return None
        finally:
            cap.release()
