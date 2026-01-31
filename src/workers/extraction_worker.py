"""帧提取工作线程"""
from typing import List
from PySide6.QtCore import QThread, Signal

from src.models.frame_data import FrameData, VideoInfo
from src.core.frame_extractor import FrameExtractor


class ExtractionWorker(QThread):
    """帧提取工作线程"""
    
    # 信号
    progress = Signal(int, int, float)  # current, total, percent
    finished = Signal(list)  # List[FrameData]
    error = Signal(str)
    
    def __init__(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        extract_fps: float,
        video_info: VideoInfo,
        parent=None
    ):
        super().__init__(parent)
        self.video_path = video_path
        self.start_time = start_time
        self.end_time = end_time
        self.extract_fps = extract_fps
        self.video_info = video_info
        self._extractor = FrameExtractor()
    
    def run(self):
        try:
            frames = self._extractor.extract_frames(
                video_path=self.video_path,
                start_time=self.start_time,
                end_time=self.end_time,
                extract_fps=self.extract_fps,
                video_info=self.video_info,
                progress_callback=self._on_progress
            )
            self.finished.emit(frames)
        except Exception as e:
            self.error.emit(str(e))
    
    def _on_progress(self, current: int, total: int, percent: float):
        self.progress.emit(current, total, percent)
    
    def cancel(self):
        """取消提取"""
        self._extractor.cancel()
