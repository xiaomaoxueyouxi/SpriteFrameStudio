"""历史记录管理模块"""
from dataclasses import dataclass
from typing import List, Dict, Optional
import time
import numpy as np

from src.core.frame_manager import FrameManager
from src.models.frame_data import FrameData


@dataclass
class HistoryEntry:
    """单条历史记录"""
    step_id: int                              # 步骤编号（全局自增）
    operation_name: str                       # 操作名称，如 "批量缩放"
    description: str                          # 详细描述，如 "50帧 512x512→256x256 Lanczos"
    timestamp: float                          # 操作时间戳
    affected_indices: List[int]               # 受影响的帧索引列表
    snapshots: Dict[int, np.ndarray]          # {帧索引: 操作前的图像副本}
    snapshot_states: Dict[int, bool]          # {帧索引: 快照时是否有processed_image}
    memory_bytes: int                         # 本条快照占用内存（字节）


class HistoryManager:
    """历史记录管理器"""
    MAX_STEPS = 10                            # 最大历史步数

    def __init__(self):
        self._entries: List[HistoryEntry] = []  # 历史栈
        self._step_counter: int = 1            # 步骤计数器
        self._total_memory: int = 0            # 当前总内存占用

    def push_snapshot(self, name: str, description: str, frame_indices: List[int], frame_manager: FrameManager) -> int:
        """创建快照并添加到历史记录
        
        Args:
            name: 操作名称
            description: 详细描述
            frame_indices: 受影响的帧索引列表
            frame_manager: 帧管理器
            
        Returns:
            创建的步骤编号
        """
        # 创建快照
        snapshots = {}
        snapshot_states = {}
        memory_bytes = 0
        
        for idx in frame_indices:
            frame = frame_manager.get_frame(idx)
            if frame and frame.display_image is not None:
                # 深拷贝图像
                snapshot = np.copy(frame.display_image)
                snapshots[idx] = snapshot
                # 记录快照时是否有 processed_image
                snapshot_states[idx] = frame.has_processed
                memory_bytes += snapshot.nbytes
        
        # 创建历史条目
        entry = HistoryEntry(
            step_id=self._step_counter,
            operation_name=name,
            description=description,
            timestamp=time.time(),
            affected_indices=frame_indices,
            snapshots=snapshots,
            snapshot_states=snapshot_states,
            memory_bytes=memory_bytes
        )
        
        # 添加到历史栈
        self._entries.append(entry)
        self._total_memory += memory_bytes
        self._step_counter += 1
        
        # 检查并清理超出限制的历史记录
        self._cleanup_history()
        
        return entry.step_id

    def revert_to(self, step_id: int, frame_manager: FrameManager) -> List[int]:
        """回退到指定步骤（恢复到该步骤执行后的状态）
        
        点击"回退到此"意味着保留该步骤及之前的记录，撤销该步骤之后的所有操作。
        
        Args:
            step_id: 目标步骤编号
            frame_manager: 帧管理器
            
        Returns:
            受影响的帧索引列表
        """
        # 找到目标步骤的索引
        target_idx = None
        for i, entry in enumerate(self._entries):
            if entry.step_id == step_id:
                target_idx = i
                break
        
        if target_idx is None:
            return []
        
        # 如果目标步骤已经是最新的，无需回退
        if target_idx == len(self._entries) - 1:
            return []
        
        # 收集受影响的帧索引
        affected_indices = set()
        
        # 按时间倒序恢复快照（从最新到目标步骤之后的第一个，不包含目标步骤本身）
        for i in range(len(self._entries) - 1, target_idx, -1):
            entry = self._entries[i]
            for idx, snapshot in entry.snapshots.items():
                frame = frame_manager.get_frame(idx)
                if frame:
                    # 根据快照时记录的状态恢复
                    was_processed = entry.snapshot_states.get(idx, False)
                    if was_processed:
                        frame.processed_image = snapshot
                    else:
                        # 快照时还没有 processed_image，说明这是原始状态
                        frame.image = snapshot
                        frame.processed_image = None
                    affected_indices.add(idx)
            
            # 释放内存
            self._total_memory -= entry.memory_bytes
            entry.snapshots.clear()
            entry.snapshot_states.clear()
        
        # 保留目标步骤及之前的条目，移除之后的
        self._entries = self._entries[:target_idx + 1]
        
        return list(affected_indices)

    def clear(self):
        """清空历史记录"""
        for entry in self._entries:
            entry.snapshots.clear()
            entry.snapshot_states.clear()
        self._entries.clear()
        self._total_memory = 0
        self._step_counter = 1

    def get_entries(self) -> List[HistoryEntry]:
        """获取历史记录列表
        
        Returns:
            历史记录列表，最新的在最前面
        """
        return list(reversed(self._entries))

    def get_memory_usage(self) -> str:
        """获取内存使用情况
        
        Returns:
            内存使用情况字符串，如 "125.3 MB"
        """
        current_mb = self._total_memory / (1024 * 1024)
        return f"{current_mb:.1f} MB"

    def _cleanup_history(self):
        """清理超出步数限制的历史记录"""
        while len(self._entries) > self.MAX_STEPS:
            oldest_entry = self._entries.pop(0)
            self._total_memory -= oldest_entry.memory_bytes
            # 释放快照引用，让 GC 回收
            oldest_entry.snapshots.clear()
            oldest_entry.snapshot_states.clear()
