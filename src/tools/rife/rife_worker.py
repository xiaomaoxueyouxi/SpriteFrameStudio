"""RIFE补帧后台工作线程"""
from typing import List, Optional
from pathlib import Path
from PySide6.QtCore import QThread, Signal
import numpy as np


class RifeWorker(QThread):
    """RIFE补帧后台线程"""
    
    # 信号定义
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(list)  # List[np.ndarray] 生成的中间帧
    error = Signal(str)  # 错误信息
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._first_frame: Optional[np.ndarray] = None
        self._last_frame: Optional[np.ndarray] = None
        self._num_frames: int = 3
        self._output_dir: Optional[Path] = None
    
    def setup(
        self,
        first_frame: np.ndarray,
        last_frame: np.ndarray,
        num_frames: int,
        output_dir: Path = None
    ):
        """
        设置补帧参数
        
        Args:
            first_frame: 第一帧
            last_frame: 最后一帧
            num_frames: 中间帧数量 (1-7)
            output_dir: 输出目录（可选，如果提供则保存到文件）
        """
        self._first_frame = first_frame
        self._last_frame = last_frame
        self._num_frames = max(1, min(num_frames, 7))
        self._output_dir = output_dir
    
    def run(self):
        """执行补帧"""
        try:
            if self._first_frame is None or self._last_frame is None:
                self.error.emit("未设置首尾帧")
                return
            
            # 进度回调
            def progress_callback(current, total, message):
                self.progress.emit(current, total, message)
            
            # 延迟导入，避免启动时加载模型
            from .rife_interpolator import RIFEInterpolator
            
            # 确保模型已加载
            if not RIFEInterpolator.is_loaded():
                self.progress.emit(0, 1, "加载RIFE模型...")
                if not RIFEInterpolator.load_model():
                    self.error.emit("RIFE模型加载失败")
                    return
            
            # 执行插帧
            frames = RIFEInterpolator.interpolate_frames(
                self._first_frame,
                self._last_frame,
                self._num_frames,
                progress_callback
            )
            
            # 保存到文件（如果指定了输出目录）
            if self._output_dir and frames:
                self._save_frames(frames)
            
            # 发送结果
            self.finished.emit(frames)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))
    
    def _save_frames(self, frames: List[np.ndarray]):
        """保存帧到文件"""
        import cv2
        
        # 确保输出目录存在
        self._output_dir.mkdir(parents=True, exist_ok=True)
        
        # 清空目录中的旧文件
        for old_file in self._output_dir.glob("*.png"):
            old_file.unlink()
        
        # 保存所有中间帧（frames 已经是去除首尾后的中间帧，不需要再删除）
        for i, frame in enumerate(frames):
            filename = self._output_dir / f"rife_{i+1:03d}.png"
            
            # OpenCV使用BGR，需要转换
            if len(frame.shape) == 3 and frame.shape[2] == 4:
                # RGBA -> BGRA
                save_frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGRA)
            elif len(frame.shape) == 3 and frame.shape[2] == 3:
                # RGB -> BGR
                save_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            else:
                save_frame = frame
            
            cv2.imwrite(str(filename), save_frame)
        
        print(f"[RIFE] 已保存 {len(frames)} 帧到 {self._output_dir}")
