"""背景去除工作线程"""
from typing import List, Optional
from PySide6.QtCore import QThread, Signal
import numpy as np

from src.core.background_remover import BackgroundRemover, BackgroundMode


class BackgroundWorker(QThread):
    """背景去除工作线程"""
    
    # 信号
    progress = Signal(int, int, float)  # current, total, percent
    frame_processed = Signal(int, object)  # frame_index, processed_image
    status_changed = Signal(str)  # 状态信息
    finished = Signal()
    error = Signal(str)
    
    def __init__(
        self,
        frames: List[tuple],  # List[(frame_index, image)]
        mode: BackgroundMode = BackgroundMode.AI,
        color_params: Optional[dict] = None,
        ai_params: Optional[dict] = None,
        parent=None
    ):
        super().__init__(parent)
        self.frames = frames
        self.mode = mode
        self.color_params = color_params
        self.ai_params = ai_params
        # 不在这里创建，在run中创建以确保在工作线程中初始化
        self._remover = None
    
    def _on_remover_progress(self, message: str):
        """接收BackgroundRemover的进度消息"""
        self.status_changed.emit(message)
    
    def run(self):
        try:
            # 在工作线程中创建BackgroundRemover，并传递进度回调
            self._remover = BackgroundRemover(progress_callback=self._on_remover_progress)
            
            total = len(self.frames)
            
            # 如果是AI模式，先发送加载模型的提示
            if self.mode == BackgroundMode.AI:
                model_name = self.ai_params.get('model', 'u2net') if self.ai_params else 'u2net'
                self.status_changed.emit(f"正在初始化AI模型 ({model_name})...")
            
            for i, (frame_index, image) in enumerate(self.frames):
                if self.isInterruptionRequested():
                    break
                
                # 处理单帧
                result = self._remover.remove_background(
                    image=image,
                    mode=self.mode,
                    color_params=self.color_params,
                    ai_params=self.ai_params
                )
                
                # 复制结果以确保线程安全
                result_copy = result.copy()
                
                # 发送处理结果
                self.frame_processed.emit(frame_index, result_copy)
                
                # 更新进度
                progress = (i + 1) / total * 100
                self.progress.emit(i + 1, total, progress)
                self.status_changed.emit(f"正在去除背景... {i + 1}/{total}")
            
            self.finished.emit()
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)
    
    def cancel(self):
        """取消处理"""
        self.requestInterruption()
        if self._remover:
            self._remover.cancel()
