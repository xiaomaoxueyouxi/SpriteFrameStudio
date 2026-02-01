"""图像增强工作线程"""
from typing import List, Optional
from PySide6.QtCore import QThread, Signal
import numpy as np

from src.core.realesrgan_processor import RealESRGANProcessor


class EnhanceWorker(QThread):
    """图像增强工作线程"""
    
    # 信号
    progress = Signal(int, int, float)  # current, total, percent
    frame_processed = Signal(int, object)  # frame_index, enhanced_image
    status_changed = Signal(str)  # 状态信息
    finished = Signal()
    error = Signal(str)
    
    def __init__(
        self,
        frames: List[tuple],  # List[(frame_index, image)]
        model_name: str = "realesrgan-x4plus",
        tile: int = 0,
        parent=None
    ):
        super().__init__(parent)
        self.frames = frames
        self.model_name = model_name
        self.tile = tile
        # 不在这里创建，在run中创建以确保在工作线程中初始化
        self._processor = None
    
    def _on_processor_progress(self, message: str):
        """接收RealESRGANProcessor的进度消息"""
        self.status_changed.emit(message)
    
    def run(self):
        try:
            # 在工作线程中创建RealESRGANProcessor，并传递进度回调
            self._processor = RealESRGANProcessor(progress_callback=self._on_processor_progress)
            
            total = len(self.frames)
            
            # 发送初始化提示
            self.status_changed.emit(f"正在初始化Real-ESRGAN...")
            
            for i, (frame_index, image) in enumerate(self.frames):
                if self.isInterruptionRequested():
                    break
                
                # 发送当前处理的帧信息
                self.status_changed.emit(f"正在处理第 {i + 1}/{total} 帧...")
                
                # 处理单帧
                result = self._processor.process_image(
                    image=image,
                    model_name=self.model_name,
                    tile=self.tile
                )
                
                if result is not None:
                    # 复制结果以确保线程安全
                    result_copy = result.copy()
                    
                    # 发送处理结果
                    self.frame_processed.emit(frame_index, result_copy)
                
                # 更新进度
                progress = (i + 1) / total * 100
                self.progress.emit(i + 1, total, progress)
                self.status_changed.emit(f"已完成第 {i + 1}/{total} 帧")
            
            self.status_changed.emit("所有帧处理完成")
            self.finished.emit()
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)
    
    def cancel(self):
        """取消处理"""
        self.requestInterruption()
        if self._processor:
            self._processor.cancel()
