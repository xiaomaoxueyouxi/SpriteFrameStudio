"""帧编辑器模块 - 提供像素级编辑功能"""
from typing import Optional, List, Tuple
from enum import Enum
import numpy as np
import cv2


class EditTool(Enum):
    """编辑工具类型"""
    MAGIC_WAND = "magic_wand"  # 魔棒工具
    ERASER = "eraser"          # 橡皮擦
    BRUSH = "brush"            # 画笔
    MOVE = "move"              # 移动/选择


class FrameEditor:
    """帧编辑器 - 提供像素级编辑功能"""
    
    def __init__(self, image: np.ndarray, max_history: int = 20):
        """
        初始化帧编辑器
        
        Args:
            image: 输入图像 (RGBA格式)
            max_history: 最大历史记录数
        """
        # 确保图像是RGBA格式
        if len(image.shape) == 3 and image.shape[2] == 3:
            # 添加Alpha通道
            alpha = np.full((image.shape[0], image.shape[1], 1), 255, dtype=np.uint8)
            image = np.concatenate([image, alpha], axis=2)
        
        self.original_image = image.copy()
        self.current_image = image.copy()
        self.selection_mask = np.zeros(image.shape[:2], dtype=np.uint8)  # 选区掩码
        self.max_history = max_history
        self.history: List[np.ndarray] = []
        self.history_index = -1
        
        # 保存初始状态
        self._save_state()
        
        # 编辑参数
        self.tolerance = 30  # 魔棒容差
        self.brush_size = 10  # 画笔/橡皮擦大小
        self.connectivity = 8  # 连通性 (4或8)
        self.current_tool = EditTool.MOVE
    
    def _save_state(self):
        """保存当前状态到历史记录"""
        # 删除当前索引之后的历史记录
        self.history = self.history[:self.history_index + 1]
        
        # 添加新状态
        self.history.append(self.current_image.copy())
        
        # 限制历史记录数量
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.history_index += 1
    
    def undo(self) -> bool:
        """
        撤销操作
        
        Returns:
            是否成功撤销
        """
        if self.history_index > 0:
            self.history_index -= 1
            self.current_image = self.history[self.history_index].copy()
            self.clear_selection()
            return True
        return False
    
    def redo(self) -> bool:
        """
        重做操作
        
        Returns:
            是否成功重做
        """
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.current_image = self.history[self.history_index].copy()
            self.clear_selection()
            return True
        return False
    
    def can_undo(self) -> bool:
        """是否可以撤销"""
        return self.history_index > 0
    
    def can_redo(self) -> bool:
        """是否可以重做"""
        return self.history_index < len(self.history) - 1
    
    def magic_wand_select(self, x: int, y: int, tolerance: Optional[int] = None) -> np.ndarray:
        """
        魔棒选择 - 基于颜色容差的区域选择
        使用OpenCV的floodFill算法，性能优化版本
        
        Args:
            x: 点击位置X坐标
            y: 点击位置Y坐标
            tolerance: 颜色容差 (默认使用self.tolerance)
        
        Returns:
            选区掩码 (二值图像)
        """
        if tolerance is None:
            tolerance = self.tolerance
        
        h, w = self.current_image.shape[:2]
        
        # 检查坐标范围
        if x < 0 or x >= w or y < 0 or y >= h:
            return self.selection_mask
        
        # 获取RGB图像（忽略Alpha通道用于颜色匹配）
        rgb_image = self.current_image[:, :, :3]
        
        # 创建掩码（floodFill需要比原图大2像素的掩码）
        mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        
        # 设置连通性
        flags = 4 if self.connectivity == 4 else 8
        
        # 使用floodFill填充
        # 注意：OpenCV的floodFill使用(B,G,R)顺序
        seed_color = rgb_image[y, x].tolist()
        
        # 执行floodFill
        _, _, fill_mask, _ = cv2.floodFill(
            rgb_image.copy(),
            mask,
            (x, y),
            newVal=(255, 255, 255),
            loDiff=(tolerance, tolerance, tolerance),
            upDiff=(tolerance, tolerance, tolerance),
            flags=flags | (255 << 8)  # 填充值设为255
        )

        # 提取选区（去掉边界）
        selection = fill_mask[1:-1, 1:-1]

        # 边缘优化：使用形态学操作减少毛刺
        # 先进行开运算（腐蚀+膨胀）去除小噪点
        kernel_size = 2
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size * 2 + 1, kernel_size * 2 + 1))
        selection = cv2.morphologyEx(selection, cv2.MORPH_OPEN, kernel)

        # 再进行闭运算（膨胀+腐蚀）填充小空洞，平滑边缘
        selection = cv2.morphologyEx(selection, cv2.MORPH_CLOSE, kernel)

        # 轻微羽化边缘（可选，如果需要更柔和的边缘）
        # 使用高斯模糊轻微柔化边缘
        selection = cv2.GaussianBlur(selection, (3, 3), 0.5)
        # 重新二值化
        _, selection = cv2.threshold(selection, 127, 255, cv2.THRESH_BINARY)

        self.selection_mask = selection

        return self.selection_mask
    
    def add_to_selection(self, x: int, y: int, tolerance: Optional[int] = None) -> np.ndarray:
        """
        添加到当前选区
        
        Args:
            x: 点击位置X坐标
            y: 点击位置Y坐标
            tolerance: 颜色容差
        
        Returns:
            选区掩码
        """
        new_selection = self.magic_wand_select(x, y, tolerance)
        self.selection_mask = np.maximum(self.selection_mask, new_selection)
        return self.selection_mask
    
    def subtract_from_selection(self, x: int, y: int, tolerance: Optional[int] = None) -> np.ndarray:
        """
        从当前选区中减去
        
        Args:
            x: 点击位置X坐标
            y: 点击位置Y坐标
            tolerance: 颜色容差
        
        Returns:
            选区掩码
        """
        new_selection = self.magic_wand_select(x, y, tolerance)
        self.selection_mask = np.where(new_selection > 0, 0, self.selection_mask)
        return self.selection_mask
    
    def clear_selection(self):
        """清除选区"""
        self.selection_mask.fill(0)
    
    def invert_selection(self):
        """反选"""
        self.selection_mask = np.where(self.selection_mask > 0, 0, 255).astype(np.uint8)
    
    def select_all(self):
        """全选"""
        self.selection_mask.fill(255)
    
    def delete_selection(self):
        """
        删除选区内容（设为透明）
        
        Returns:
            编辑后的图像
        """
        if np.any(self.selection_mask > 0):
            # 保存状态
            self._save_state()
            
            # 将选区设为透明
            self.current_image[self.selection_mask > 0, 3] = 0
            
            # 清除选区
            self.clear_selection()
        
        return self.current_image
    
    def erase_at(self, x: int, y: int, size: Optional[int] = None):
        """
        在指定位置擦除（圆形橡皮擦）
        
        Args:
            x: 中心X坐标
            y: 中心Y坐标
            size: 橡皮擦大小 (默认使用self.brush_size)
        
        Returns:
            编辑后的图像
        """
        if size is None:
            size = self.brush_size
        
        h, w = self.current_image.shape[:2]
        
        # 计算擦除区域
        y1 = max(0, y - size)
        y2 = min(h, y + size + 1)
        x1 = max(0, x - size)
        x2 = min(w, x + size + 1)
        
        # 创建圆形遮罩
        yy, xx = np.ogrid[y1:y2, x1:x2]
        dist = np.sqrt((xx - x)**2 + (yy - y)**2)
        mask = dist <= size
        
        # 擦除像素
        self.current_image[y1:y2, x1:x2][mask] = [0, 0, 0, 0]
        
        return self.current_image
    
    def start_eraser_stroke(self):
        """开始橡皮擦涂抹（用于连续擦除）"""
        self._save_state()
    
    def get_selection_overlay(self, color: Tuple[int, int, int, int] = (0, 255, 0, 128)) -> np.ndarray:
        """
        获取选区叠加层（用于显示）
        
        Args:
            color: 选区颜色 (RGBA)
        
        Returns:
            叠加层图像
        """
        overlay = np.zeros_like(self.current_image)
        overlay[self.selection_mask > 0] = color
        return overlay
    
    def get_display_image(self, show_selection: bool = True) -> np.ndarray:
        """
        获取显示图像
        
        Args:
            show_selection: 是否显示选区
        
        Returns:
            显示图像
        """
        if not show_selection or not np.any(self.selection_mask > 0):
            return self.current_image
        
        # 创建叠加图像
        overlay = self.get_selection_overlay()
        
        # Alpha混合
        alpha = overlay[:, :, 3:4] / 255.0
        result = (1 - alpha) * self.current_image + alpha * overlay
        result = result.astype(np.uint8)
        
        return result
    
    def reset(self):
        """重置到原始图像"""
        self.current_image = self.original_image.copy()
        self.clear_selection()
        self.history.clear()
        self.history_index = -1
        self._save_state()
    
    def commit(self) -> np.ndarray:
        """
        提交编辑结果
        
        Returns:
            最终编辑后的图像
        """
        return self.current_image.copy()
