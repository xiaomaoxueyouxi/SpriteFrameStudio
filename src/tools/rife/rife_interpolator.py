"""RIFE插帧工具类 - 用于首尾帧之间的AI补帧"""
import os
import cv2
import torch
import numpy as np
from typing import List, Optional
from pathlib import Path
from torch.nn import functional as F


class RIFEInterpolator:
    """RIFE插帧器 - 单例模式"""
    _instance = None
    _model = None
    _loaded = False
    _device = None
    
    # RIFE模型路径（本地目录）
    RIFE_DIR = Path(__file__).parent
    MODEL_DIR = RIFE_DIR / "train_log"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def is_loaded(cls) -> bool:
        """检查模型是否已加载"""
        return cls._loaded
    
    @classmethod
    def load_model(cls) -> bool:
        """加载RIFE模型"""
        if cls._loaded:
            return True
        
        try:
            # 检查模型目录
            if not cls.MODEL_DIR.exists():
                print(f"[RIFE] 模型目录不存在: {cls.MODEL_DIR}")
                return False
            
            # 设置设备
            cls._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            torch.set_grad_enabled(False)
            
            if torch.cuda.is_available():
                torch.backends.cudnn.enabled = True
                torch.backends.cudnn.benchmark = True
            
            # 加载模型（使用相对导入）
            from .train_log.RIFE_HDv3 import Model
            cls._model = Model()
            cls._model.load_model(str(cls.MODEL_DIR), -1)
            cls._model.eval()
            cls._model.device()
            
            cls._loaded = True
            print(f"[RIFE] 模型加载成功，设备: {cls._device}")
            return True
            
        except Exception as e:
            print(f"[RIFE] 模型加载失败: {e}")
            import traceback
            traceback.print_exc()
            cls._loaded = False
            return False
    
    @classmethod
    def interpolate_frames(
        cls,
        first_frame: np.ndarray,
        last_frame: np.ndarray,
        num_frames: int,
        progress_callback=None
    ) -> List[np.ndarray]:
        """
        在首尾帧之间生成指定数量的中间帧（使用递归二分法）
        
        Args:
            first_frame: 第一帧 (numpy数组，支持RGB和RGBA)
            last_frame: 最后一帧 (numpy数组，支持RGB和RGBA)
            num_frames: 需要生成的中间帧数量 (1-7)
            progress_callback: 进度回调函数 callback(current, total, message)
        
        Returns:
            生成的中间帧列表，长度为 num_frames（不包含原始首尾帧）
        """
        if not cls._loaded:
            if not cls.load_model():
                raise RuntimeError("RIFE模型加载失败")
        
        # 确保帧数在合理范围内
        num_frames = max(1, min(num_frames, 7))
        
        # 记录原始信息
        has_alpha = len(first_frame.shape) == 3 and first_frame.shape[2] == 4
        orig_h, orig_w = first_frame.shape[:2]
        
        if progress_callback:
            progress_callback(0, num_frames + 1, "预处理图像...")
        
        # 预处理：转换为tensor
        img0, padding_info = cls._preprocess(first_frame)
        img1, padding_info_last = cls._preprocess(last_frame)
        
        # 如果有 alpha 通道，合并两帧的 alpha（取最小值/交集）
        # 确保两帧中任意一帧透明的像素在插值帧中也保持透明
        if has_alpha:
            ph, pw, h, w, alpha_first = padding_info
            _, _, _, _, alpha_last = padding_info_last
            if alpha_first is not None and alpha_last is not None:
                combined_alpha = np.minimum(alpha_first, alpha_last)
            elif alpha_first is not None:
                combined_alpha = alpha_first
            else:
                combined_alpha = alpha_last
            padding_info = (ph, pw, h, w, combined_alpha)
        
        # 目标总帧数 = 原始2帧 + 中间帧
        total_frames = num_frames + 2
        
        if progress_callback:
            progress_callback(1, num_frames + 1, "生成中间帧...")
        
        # 使用递归二分法生成帧
        img_list = cls._recursive_interpolate([img0, img1], total_frames, progress_callback, num_frames + 1)
        
        # 后处理：转换回numpy数组，只取中间帧
        result_frames = []
        for i, tensor in enumerate(img_list):
            # 跳过首尾帧（只返回中间帧）
            if i == 0 or i == len(img_list) - 1:
                continue
            frame = cls._postprocess(tensor, orig_h, orig_w, has_alpha, padding_info)
            result_frames.append(frame)
        
        if progress_callback:
            progress_callback(num_frames + 1, num_frames + 1, "完成")
        
        return result_frames
    
    @classmethod
    def _preprocess(cls, img: np.ndarray) -> tuple:
        """
        预处理图像为模型输入格式
        
        Returns:
            (tensor, padding_info) 其中 padding_info = (ph, pw, orig_h, orig_w)
        """
        h, w = img.shape[:2]
        
        # 处理alpha通道 - 如果有alpha，先分离出来
        alpha = None
        if len(img.shape) == 3 and img.shape[2] == 4:
            alpha = img[:, :, 3:4]
            img = img[:, :, :3]  # 只取RGB
        elif len(img.shape) == 2:
            # 灰度图转RGB
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif len(img.shape) == 3 and img.shape[2] == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        
        # 确保是RGB
        if len(img.shape) == 3 and img.shape[2] == 3:
            pass  # 已经是RGB
        
        # 转换为tensor
        tensor = torch.from_numpy(img.transpose(2, 0, 1)).to(cls._device).float() / 255.0
        tensor = tensor.unsqueeze(0)  # [1, 3, H, W]
        
        # Padding到64的倍数
        ph = ((h - 1) // 64 + 1) * 64
        pw = ((w - 1) // 64 + 1) * 64
        padding = (0, pw - w, 0, ph - h)
        tensor = F.pad(tensor, padding)
        
        return tensor, (ph, pw, h, w, alpha)
    
    @classmethod
    def _postprocess(cls, tensor: torch.Tensor, orig_h: int, orig_w: int, has_alpha: bool, padding_info: tuple) -> np.ndarray:
        """
        后处理：将tensor转换回numpy数组
        """
        ph, pw, orig_h_tensor, orig_w_tensor, orig_alpha = padding_info
        
        # 移除batch维度并转换
        img = tensor[0].detach().cpu().numpy()  # [3, H, W]
        
        # 裁剪到原始尺寸
        img = img[:, :orig_h, :orig_w]
        
        # 转换为uint8
        img = (img * 255.0).clip(0, 255).astype(np.uint8)
        img = img.transpose(1, 2, 0)  # [H, W, 3]
        
        # 如果原图有alpha通道，使用合并后的 alpha（在 interpolate_frames 中已计算）
        if has_alpha and orig_alpha is not None:
            alpha_channel = orig_alpha
            img = np.concatenate([img, alpha_channel], axis=2)
        
        return img
    
    @classmethod
    def _recursive_interpolate(
        cls,
        frame_list: List[torch.Tensor],
        target_count: int,
        progress_callback=None,
        total_steps: int = 0,
        current_step: int = 0
    ) -> List[torch.Tensor]:
        """
        递归二分法插帧，产生更自然的过渡效果
        """
        if len(frame_list) >= target_count:
            return frame_list
        
        new_list = [frame_list[0]]
        for i in range(len(frame_list) - 1):
            # 在相邻两帧之间插入中间帧
            middle = cls._model.inference(frame_list[i], frame_list[i + 1], 0.5)
            new_list.append(middle)
            new_list.append(frame_list[i + 1])
            
            # 更新进度
            if progress_callback and total_steps > 0:
                current_step += 1
                progress_callback(min(current_step, total_steps), total_steps, f"生成中间帧...")
        
        return cls._recursive_interpolate(new_list, target_count, progress_callback, total_steps, current_step)


# 便捷函数
def interpolate_frames(
    first_frame: np.ndarray,
    last_frame: np.ndarray,
    num_frames: int,
    progress_callback=None
) -> List[np.ndarray]:
    """
    便捷函数：在首尾帧之间生成中间帧
    
    Args:
        first_frame: 第一帧
        last_frame: 最后一帧
        num_frames: 中间帧数量 (1-7)
        progress_callback: 进度回调
    
    Returns:
        中间帧列表（不包含原始首尾帧）
    """
    return RIFEInterpolator.interpolate_frames(first_frame, last_frame, num_frames, progress_callback)
