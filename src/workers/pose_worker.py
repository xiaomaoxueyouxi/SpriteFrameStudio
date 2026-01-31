"""姿势识别工作线程"""
from typing import List, Tuple
from PySide6.QtCore import QThread, Signal
import numpy as np

from src.core.pose_detector import PoseDetector


class PoseWorker(QThread):
    """姿势识别工作线程"""
    
    # 信号
    progress = Signal(int, int, float)  # current, total, percent
    pose_detected = Signal(int, object)  # frame_index, PoseData/ContourData/RegionalFeatureData
    finished = Signal()
    error = Signal(str)
    
    def __init__(
        self,
        frames: List[Tuple[int, np.ndarray]],  # List[(frame_index, image)]
        mode: str = "pose",  # "pose", "contour", "image", "regional"
        parent=None
    ):
        super().__init__(parent)
        self.frames = frames
        self.mode = mode
        self._detector = PoseDetector()
    
    def run(self):
        try:
            total = len(self.frames)
            
            for i, (frame_index, image) in enumerate(self.frames):
                if self.isInterruptionRequested():
                    break
                
                # 根据模式选择检测方法
                if self.mode == "contour":
                    result = self._detector.extract_contour(image, frame_index)
                elif self.mode == "image":
                    result = self._detector.extract_image_features(image, frame_index)
                elif self.mode == "regional":
                    result = self._detector.extract_regional_features(image, frame_index)
                elif self.mode == "pose_rtm":
                    result = self._detector.detect_pose_rtm(image, frame_index)
                else:
                    result = self._detector.detect_pose(image, frame_index)
                
                # 发送检测结果
                self.pose_detected.emit(frame_index, result)
                
                # 更新进度
                progress = (i + 1) / total * 100
                self.progress.emit(i + 1, total, progress)
            
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self._detector.release()
    
    def cancel(self):
        """取消检测"""
        self.requestInterruption()
        self._detector.cancel()
