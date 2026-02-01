"""视频处理核心模块"""
from typing import Optional, Dict, List
from pathlib import Path
import cv2
import numpy as np
import threading
import time

from src.models.frame_data import VideoInfo


class VideoProcessor:
    """视频处理器 - 负责视频加载和元数据提取"""
    
    def __init__(self):
        self._cap: Optional[cv2.VideoCapture] = None
        self._video_info: Optional[VideoInfo] = None
        self._frame_cache: Dict[int, np.ndarray] = {}
        self._base_cache_size = 200  # 基础缓存大小
        self._cache_size = self._base_cache_size  # 初始缓存大小
        self._last_accessed_frame = -1
        self._use_sequential_mode = False
        self._lock = threading.RLock()  # 添加线程锁，确保线程安全
        self._preload_thread: Optional[threading.Thread] = None
        self._preload_stop_event = threading.Event()
        self._preload_queue: List[int] = []
        self._preload_batch_size = 30  # 每次预加载30帧
        self._max_preload_batch_size = 50  # 最大预加载批次大小
        self._min_preload_batch_size = 10  # 最小预加载批次大小
    
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
        
        # 动态调整缓存大小和预加载批次大小
        self._adjust_cache_settings()
        
        return self._video_info
    
    def _adjust_cache_settings(self):
        """根据视频特性动态调整缓存设置"""
        if not self._video_info:
            return
        
        width = self._video_info.width
        height = self._video_info.height
        fps = self._video_info.fps
        
        # 计算视频分辨率
        resolution = width * height
        
        # 根据分辨率调整缓存大小
        if resolution > 1920 * 1080:  # 4K及以上
            # 高分辨率视频，减少缓存大小以节省内存
            self._cache_size = max(100, int(self._base_cache_size * 0.5))
            self._preload_batch_size = min(self._max_preload_batch_size, 20)
        elif resolution > 1280 * 720:  # 1080p
            # 中等分辨率视频，保持默认缓存大小
            self._cache_size = self._base_cache_size
            self._preload_batch_size = 30
        else:  # 720p及以下
            # 低分辨率视频，增加缓存大小以提高性能
            self._cache_size = min(500, int(self._base_cache_size * 2))
            self._preload_batch_size = min(self._max_preload_batch_size, 40)
        
        # 根据帧率调整预加载批次大小
        if fps > 60:
            # 高帧率视频，增加预加载批次大小
            self._preload_batch_size = min(self._max_preload_batch_size, self._preload_batch_size + 10)
        elif fps < 24:
            # 低帧率视频，减少预加载批次大小
            self._preload_batch_size = max(self._min_preload_batch_size, self._preload_batch_size - 10)

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
        with self._lock:
            if frame_index in self._frame_cache:
                # 更新访问时间（通过重新插入来实现LRU）
                frame = self._frame_cache.pop(frame_index)
                self._frame_cache[frame_index] = frame
                self._last_accessed_frame = frame_index
                return frame.copy()
        
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
        with self._lock:
            # 添加或更新帧到缓存
            if frame_index in self._frame_cache:
                # 如果已存在，先删除旧的（为了更新位置，实现LRU）
                del self._frame_cache[frame_index]
            self._frame_cache[frame_index] = frame.copy()
            
            # 限制缓存大小
            if len(self._frame_cache) > self._cache_size:
                # 删除最早添加的帧（实现LRU策略）
                # 注意：Python 3.7+的字典会保持插入顺序
                oldest_frame = next(iter(self._frame_cache))
                del self._frame_cache[oldest_frame]

    def get_frame_count_in_range(self, start_time: float, end_time: float, fps: float) -> int:
        """计算时间范围内按指定帧率的帧数"""
        duration = end_time - start_time
        return max(1, int(duration * fps))
    
    def release(self):
        """释放视频资源"""
        # 停止预加载线程
        self.stop_preload()
        
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._video_info = None
            with self._lock:
                self._frame_cache.clear()
            self._last_accessed_frame = -1
            self._use_sequential_mode = False
    
    def start_preload(self):
        """开始预加载线程"""
        if self._preload_thread is not None and self._preload_thread.is_alive():
            return
        
        self._preload_stop_event.clear()
        self._preload_thread = threading.Thread(target=self._preload_worker, daemon=True)
        self._preload_thread.start()
    
    def stop_preload(self):
        """停止预加载线程"""
        if self._preload_thread is not None:
            self._preload_stop_event.set()
            if self._preload_thread.is_alive():
                self._preload_thread.join(timeout=1.0)
            self._preload_thread = None
    
    def preload_range(self, start_frame: int, end_frame: int):
        """预加载指定范围的帧"""
        if not self.is_loaded or self._video_info is None:
            return
        
        start_frame = max(0, start_frame)
        end_frame = min(end_frame, self._video_info.frame_count - 1)
        
        with self._lock:
            # 清除旧的预加载队列，添加新的范围
            self._preload_queue = list(range(start_frame, end_frame + 1))
    
    def _preload_worker(self):
        """预加载工作线程"""
        while not self._preload_stop_event.is_set():
            # 检查是否有帧需要预加载
            frames_to_preload = []
            with self._lock:
                if self._preload_queue:
                    # 取出一批帧进行预加载
                    frames_to_preload = self._preload_queue[:self._preload_batch_size]
                    self._preload_queue = self._preload_queue[self._preload_batch_size:]
            
            if frames_to_preload:
                for frame_index in frames_to_preload:
                    if self._preload_stop_event.is_set():
                        break
                    # 检查是否已经在缓存中
                    with self._lock:
                        if frame_index in self._frame_cache:
                            continue
                    # 预加载帧
                    self.get_frame_by_index(frame_index)
                # 短暂休眠，避免占用过多CPU
                time.sleep(0.01)
            else:
                # 没有需要预加载的帧，休眠一段时间
                time.sleep(0.1)