"""视频处理核心模块"""
from typing import Optional, Dict
from pathlib import Path
import cv2
import numpy as np

from src.models.frame_data import VideoInfo


class VideoProcessor:
    """视频处理器 - 负责视频加载和元数据提取"""
    
    def __init__(self):
        self._cap: Optional[cv2.VideoCapture] = None
        self._video_info: Optional[VideoInfo] = None
        self._frame_cache: Dict[int, np.ndarray] = {}
        self._cache_size = 30  # 缓存30帧
        self._last_accessed_frame = -1
        self._use_sequential_mode = False
    
    @property
    def is_loaded(self) -> bool:
        """是否已加载视频"""
        return self._cap is not None and self._cap.isOpened()
    
    @property
    def video_info(self) -> Optional[VideoInfo]:
        """获取视频信息"""
        return self._video_info
    
    def load_video(self, path: str) -> VideoInfo:
        """加载视频文件并提取元数据"""
        self.release()
        
        video_path = Path(path)
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {path}")
        
        self._cap = cv2.VideoCapture(str(video_path))
        if not self._cap.isOpened():
            raise IOError(f"无法打开视频文件: {path}")
        
        # 提取视频信息
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 获取编码格式
        fourcc = int(self._cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
        
        # 计算时长
        duration = frame_count / fps if fps > 0 else 0
        
        self._video_info = VideoInfo(
            path=video_path,
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration=duration,
            codec=codec
        )
        
        # 检测是否需要使用顺序模式
        self._detect_seek_mode()
        
        return self._video_info

    def _detect_seek_mode(self):
        """检测视频是否需要使用顺序读取模式"""
        # 模拟播放场景：先定位到0，再定位到1秒位置
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._cap.read()  # 读取一帧
        
        target_frame = int(1.0 * self._video_info.fps)
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        actual_pos = self._cap.get(cv2.CAP_PROP_POS_FRAMES)
        
        # 重置到开头
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        self._use_sequential_mode = actual_pos < 0 or abs(actual_pos - target_frame) > 1

    def get_frame_at(self, timestamp: float) -> Optional[np.ndarray]:
        """获取指定时间戳的帧"""
        if not self.is_loaded or self._video_info is None:
            return None
        
        # 计算帧号
        frame_number = int(timestamp * self._video_info.fps)
        return self.get_frame_by_index(frame_number)
    
    def get_frame_by_index(self, frame_index: int) -> Optional[np.ndarray]:
        """获取指定索引的帧"""
        if not self.is_loaded or self._video_info is None:
            return None
        
        # 边界检查
        if frame_index < 0 or frame_index >= self._video_info.frame_count:
            return None
        
        # 检查缓存
        if frame_index in self._frame_cache:
            self._last_accessed_frame = frame_index
            return self._frame_cache[frame_index].copy()
        
        if self._use_sequential_mode:
            # 顺序模式：利用连续性优化读取
            frame = self._get_frame_sequential(frame_index)
        else:
            # 正常模式：使用帧定位
            frame = self._get_frame_seek(frame_index)
        
        if frame is not None:
            # 添加到缓存
            self._add_to_cache(frame_index, frame)
            self._last_accessed_frame = frame_index
            return frame.copy()
        return None

    def _get_frame_seek(self, frame_index: int) -> Optional[np.ndarray]:
        """使用帧定位获取帧（适用于支持随机访问的视频）"""
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = self._cap.read()
        if ret:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return None

    def _get_frame_sequential(self, frame_index: int) -> Optional[np.ndarray]:
        """顺序读取获取帧（适用于不支持随机访问的视频）"""
        # 如果请求的是连续帧，直接从当前位置读取
        if frame_index == self._last_accessed_frame + 1:
            ret, frame = self._cap.read()
            if ret:
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return None

        # 如果请求的是已经缓存的帧附近，从缓存恢复
        if frame_index > 0 and (frame_index - 1) in self._frame_cache:
            # 从上一帧继续读取
            pass
        else:
            # 需要重新定位：使用基于时间的定位尝试
            timestamp_ms = (frame_index / self._video_info.fps) * 1000
            self._cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
            actual_pos = self._cap.get(cv2.CAP_PROP_POS_FRAMES)
            
            # 如果时间定位也失败，重新打开视频
            if actual_pos < 0:
                self._cap.release()
                self._cap = cv2.VideoCapture(str(self._video_info.path))
                # 顺序读取到目标帧
                for _ in range(frame_index):
                    self._cap.read()

        ret, frame = self._cap.read()
        if ret:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return None

    def _add_to_cache(self, frame_index: int, frame: np.ndarray):
        """添加帧到缓存"""
        self._frame_cache[frame_index] = frame.copy()
        # 限制缓存大小
        if len(self._frame_cache) > self._cache_size:
            # 删除最旧的帧（距离当前帧最远的）
            oldest = min(self._frame_cache.keys(), 
                        key=lambda k: abs(k - frame_index))
            del self._frame_cache[oldest]

    def get_frame_count_in_range(self, start_time: float, end_time: float, fps: float) -> int:
        """计算时间范围内按指定帧率的帧数"""
        duration = end_time - start_time
        return max(1, int(duration * fps))
    
    def release(self):
        """释放视频资源"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._video_info = None
            self._frame_cache.clear()
            self._last_accessed_frame = -1
            self._use_sequential_mode = False