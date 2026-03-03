"""魔棒选区工具 - 基于颜色容差的选区算法（性能优化版）"""
from typing import Optional, Tuple, List
from dataclasses import dataclass
import numpy as np


@dataclass
class Selection:
    """选区数据"""
    mask: np.ndarray
    bounds: Tuple[int, int, int, int]
    area: int
    seed_point: Tuple[int, int]
    tolerance: int
    contiguous: bool
    
    @property
    def x(self) -> int:
        return self.bounds[0]
    
    @property
    def y(self) -> int:
        return self.bounds[1]
    
    @property
    def width(self) -> int:
        return self.bounds[2]
    
    @property
    def height(self) -> int:
        return self.bounds[3]


class MagicWand:
    """魔棒选区工具 - 性能优化版"""
    
    def __init__(self):
        self._selection: Optional[Selection] = None
    
    @property
    def selection(self) -> Optional[Selection]:
        return self._selection
    
    @property
    def has_selection(self) -> bool:
        return self._selection is not None and self._selection.area > 0
    
    def select(
        self,
        image: np.ndarray,
        seed_x: int,
        seed_y: int,
        tolerance: int = 32,
        contiguous: bool = True,
        anti_alias: bool = True
    ) -> Selection:
        h, w = image.shape[:2]
        
        if seed_x < 0 or seed_x >= w or seed_y < 0 or seed_y >= h:
            raise ValueError(f"种子点 ({seed_x}, {seed_y}) 超出图像范围")
        
        if len(image.shape) == 3 and image.shape[2] == 4:
            rgb = image[:, :, :3]
        else:
            rgb = image[:, :, :3] if len(image.shape) == 3 else np.stack([image]*3, axis=2)
        
        seed_color = rgb[seed_y, seed_x].astype(np.int16)
        
        if contiguous:
            mask = self._flood_fill_optimized(rgb, seed_x, seed_y, seed_color, tolerance, anti_alias)
        else:
            mask = self._select_all_similar_optimized(rgb, seed_color, tolerance, anti_alias)
        
        bounds = self._get_bounds_fast(mask)
        area = int(np.count_nonzero(mask > 0))
        
        self._selection = Selection(
            mask=mask,
            bounds=bounds,
            area=area,
            seed_point=(seed_x, seed_y),
            tolerance=tolerance,
            contiguous=contiguous
        )
        
        return self._selection
    
    def _flood_fill_optimized(
        self,
        rgb: np.ndarray,
        seed_x: int,
        seed_y: int,
        seed_color: np.ndarray,
        tolerance: int,
        anti_alias: bool
    ) -> np.ndarray:
        """优化的洪水填充算法"""
        h, w = rgb.shape[:2]
        
        color_diff = np.abs(rgb.astype(np.int16) - seed_color)
        color_dist = np.max(color_diff, axis=2)
        
        if anti_alias:
            in_range = color_dist <= tolerance
            edge_factor = np.clip((tolerance - color_dist) / max(tolerance, 1), 0, 1).astype(np.float32)
        else:
            in_range = color_dist <= tolerance
            edge_factor = None
        
        mask = np.zeros((h, w), dtype=np.float32 if anti_alias else np.uint8)
        visited = np.zeros((h, w), dtype=np.uint8)
        
        if not in_range[seed_y, seed_x]:
            return mask
        
        stack = [seed_y * w + seed_x]
        
        while stack:
            pos = stack.pop()
            y, x = divmod(pos, w)
            
            if visited[y, x]:
                continue
            
            left = x
            while left > 0 and not visited[y, left - 1] and in_range[y, left - 1]:
                left -= 1
            
            right = x
            while right < w - 1 and not visited[y, right + 1] and in_range[y, right + 1]:
                right += 1
            
            visited[y, left:right + 1] = 1
            
            if anti_alias:
                mask[y, left:right + 1] = edge_factor[y, left:right + 1]
            else:
                mask[y, left:right + 1] = 1
            
            if y > 0:
                row = y - 1
                for xx in range(left, right + 1):
                    if not visited[row, xx] and in_range[row, xx]:
                        stack.append(row * w + xx)
            
            if y < h - 1:
                row = y + 1
                for xx in range(left, right + 1):
                    if not visited[row, xx] and in_range[row, xx]:
                        stack.append(row * w + xx)
        
        return mask
    
    def _select_all_similar_optimized(
        self,
        rgb: np.ndarray,
        seed_color: np.ndarray,
        tolerance: int,
        anti_alias: bool
    ) -> np.ndarray:
        """优化的非连续选区"""
        color_diff = np.abs(rgb.astype(np.int16) - seed_color)
        color_dist = np.max(color_diff, axis=2)
        
        if anti_alias:
            return np.clip((tolerance - color_dist) / max(tolerance, 1), 0, 1).astype(np.float32)
        else:
            return (color_dist <= tolerance).astype(np.uint8)
    
    def _get_bounds_fast(self, mask: np.ndarray) -> Tuple[int, int, int, int]:
        """快速获取边界框"""
        rows = np.any(mask > 0, axis=1)
        cols = np.any(mask > 0, axis=0)
        
        if not np.any(rows) or not np.any(cols):
            return (0, 0, 0, 0)
        
        y_indices = np.where(rows)[0]
        x_indices = np.where(cols)[0]
        
        y_min, y_max = y_indices[0], y_indices[-1]
        x_min, x_max = x_indices[0], x_indices[-1]
        
        return (int(x_min), int(y_min), int(x_max - x_min + 1), int(y_max - y_min + 1))
    
    def add_to_selection(self, other: Selection) -> bool:
        if self._selection is None:
            self._selection = other
            return True
        
        if self._selection.mask.shape != other.mask.shape:
            return False
        
        self._selection.mask = np.maximum(self._selection.mask, other.mask)
        self._selection.area = int(np.count_nonzero(self._selection.mask > 0))
        self._selection.bounds = self._get_bounds_fast(self._selection.mask)
        
        return True
    
    def subtract_from_selection(self, other: Selection) -> bool:
        if self._selection is None:
            return False
        
        if self._selection.mask.shape != other.mask.shape:
            return False
        
        self._selection.mask = np.clip(self._selection.mask - other.mask, 0, 1)
        self._selection.area = int(np.count_nonzero(self._selection.mask > 0))
        self._selection.bounds = self._get_bounds_fast(self._selection.mask)
        
        return True
    
    def intersect_selection(self, other: Selection) -> bool:
        if self._selection is None:
            return False
        
        if self._selection.mask.shape != other.mask.shape:
            return False
        
        self._selection.mask = np.minimum(self._selection.mask, other.mask)
        self._selection.area = int(np.count_nonzero(self._selection.mask > 0))
        self._selection.bounds = self._get_bounds_fast(self._selection.mask)
        
        return True
    
    def invert_selection(self, image_shape: Tuple[int, int]):
        if self._selection is None:
            h, w = image_shape
            self._selection = Selection(
                mask=np.ones((h, w), dtype=np.uint8),
                bounds=(0, 0, w, h),
                area=h * w,
                seed_point=(0, 0),
                tolerance=0,
                contiguous=False
            )
            return
        
        self._selection.mask = 1.0 - self._selection.mask
        self._selection.area = int(np.count_nonzero(self._selection.mask > 0))
        self._selection.bounds = self._get_bounds_fast(self._selection.mask)
    
    def clear_selection(self):
        self._selection = None
    
    def apply_to_image(
        self,
        image: np.ndarray,
        operation: str = "delete",
        fill_color: Optional[Tuple[int, int, int, int]] = None
    ) -> np.ndarray:
        if self._selection is None:
            return image.copy()
        
        result = image.copy()
        mask = self._selection.mask
        
        if len(result.shape) == 2:
            result = np.stack([result]*3 + [np.full_like(result, 255)], axis=2)
        elif result.shape[2] == 3:
            result = np.concatenate([result, np.full((*result.shape[:2], 1), 255, dtype=np.uint8)], axis=2)
        
        if operation == "delete":
            inv_mask = 1.0 - mask
            for c in range(4):
                result[:, :, c] = (result[:, :, c] * inv_mask).astype(np.uint8)
        
        elif operation == "fill" and fill_color is not None:
            for c in range(4):
                result[:, :, c] = (
                    result[:, :, c] * (1 - mask) + fill_color[c] * mask
                ).astype(np.uint8)
        
        return result
    
    def copy_selection(self, image: np.ndarray) -> Optional[np.ndarray]:
        if self._selection is None:
            return None
        
        bounds = self._selection.bounds
        x, y, w, h = bounds
        
        if w == 0 or h == 0:
            return None
        
        cropped_mask = self._selection.mask[y:y+h, x:x+w]
        cropped_image = image[y:y+h, x:x+w].copy()
        
        if len(cropped_image.shape) == 3 and cropped_image.shape[2] == 4:
            cropped_image[:, :, 3] = (cropped_image[:, :, 3] * cropped_mask).astype(np.uint8)
        elif len(cropped_image.shape) == 3:
            alpha = (255 * cropped_mask).astype(np.uint8)[:, :, np.newaxis]
            cropped_image = np.concatenate([cropped_image, alpha], axis=2)
        
        return cropped_image


def extract_boundary_fast(mask: np.ndarray) -> np.ndarray:
    """快速提取边界 - 使用NumPy向量化操作"""
    if mask is None or not np.any(mask > 0):
        return np.zeros((0, 2), dtype=np.int32)
    
    h, w = mask.shape
    
    binary = (mask > 0)
    
    boundary_mask = np.zeros_like(binary, dtype=bool)
    
    boundary_mask[1:, :] |= binary[1:, :] & (~binary[:-1, :])
    boundary_mask[:-1, :] |= binary[:-1, :] & (~binary[1:, :])
    boundary_mask[:, 1:] |= binary[:, 1:] & (~binary[:, :-1])
    boundary_mask[:, :-1] |= binary[:, :-1] & (~binary[:, 1:])
    
    points = np.argwhere(boundary_mask)
    
    return points[:, [1, 0]]


def trace_boundary_contours(mask: np.ndarray) -> List[np.ndarray]:
    """追踪边界轮廓，返回有序的轮廓点列表"""
    if mask is None or not np.any(mask > 0):
        return []
    
    h, w = mask.shape
    binary = (mask > 0).astype(np.uint8)
    
    contours = []
    visited = np.zeros_like(binary, dtype=bool)
    
    directions = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
    
    for start_y in range(h):
        for start_x in range(w):
            if binary[start_y, start_x] and not visited[start_y, start_x]:
                is_boundary = False
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = start_y + dy, start_x + dx
                    if ny < 0 or ny >= h or nx < 0 or nx >= w or not binary[ny, nx]:
                        is_boundary = True
                        break
                
                if not is_boundary:
                    visited[start_y, start_x] = True
                    continue
                
                contour = []
                y, x = start_y, start_x
                dir_idx = 0
                
                max_iter = h * w * 2
                iter_count = 0
                
                while iter_count < max_iter:
                    iter_count += 1
                    
                    if visited[y, x] and len(contour) > 0:
                        break
                    
                    contour.append((x, y))
                    visited[y, x] = True
                    
                    found = False
                    search_dir = (dir_idx + 5) % 8
                    
                    for i in range(8):
                        check_dir = (search_dir + i) % 8
                        dy, dx = directions[check_dir]
                        ny, nx = y + dy, x + dx
                        
                        if 0 <= ny < h and 0 <= nx < w and binary[ny, nx]:
                            y, x = ny, nx
                            dir_idx = check_dir
                            found = True
                            break
                    
                    if not found:
                        break
                
                if len(contour) >= 3:
                    contours.append(np.array(contour, dtype=np.int32))
    
    return contours


def clean_small_regions(mask: np.ndarray, min_area: int = 10) -> np.ndarray:
    """清理小的孤立区域"""
    if mask is None or not np.any(mask > 0):
        return mask
    
    binary = (mask > 0.5).astype(np.uint8)
    h, w = binary.shape
    visited = np.zeros_like(binary)
    result = np.zeros_like(binary)
    
    for y in range(h):
        for x in range(w):
            if binary[y, x] and not visited[y, x]:
                stack = [(y, x)]
                region = []
                
                while stack:
                    cy, cx = stack.pop()
                    if visited[cy, cx]:
                        continue
                    visited[cy, cx] = 1
                    region.append((cy, cx))
                    
                    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and binary[ny, nx] and not visited[ny, nx]:
                            stack.append((ny, nx))
                
                if len(region) >= min_area:
                    for ry, rx in region:
                        result[ry, rx] = 1
    
    return result.astype(np.float32)


def grow_selection(mask: np.ndarray, pixels: int = 1) -> np.ndarray:
    """扩大选区 - 几何膨胀，向外扩展指定像素数
    
    Args:
        mask: 当前选区mask
        pixels: 扩展的像素数（默认1）
    
    Returns:
        扩展后的mask
    """
    if mask is None or not np.any(mask > 0):
        return mask
    
    binary = (mask > 0.5)
    
    # 使用膨胀操作扩展选区
    for _ in range(pixels):
        padded = np.pad(binary, 1, mode='constant', constant_values=False)
        # 3x3邻域，只要有一个邻居是True，当前就是True
        binary = (
            padded[:-2, :-2] | padded[:-2, 1:-1] | padded[:-2, 2:] |
            padded[1:-1, :-2] | padded[1:-1, 1:-1] | padded[1:-1, 2:] |
            padded[2:, :-2] | padded[2:, 1:-1] | padded[2:, 2:]
        )
    
    return binary.astype(np.float32)


def shrink_selection(mask: np.ndarray, pixels: int = 1) -> np.ndarray:
    """缩小选区 - 几何腐蚀，向内收缩指定像素数
    
    Args:
        mask: 当前选区mask
        pixels: 收缩的像素数（默认1）
    
    Returns:
        收缩后的mask
    """
    if mask is None or not np.any(mask > 0):
        return mask
    
    binary = (mask > 0.5)
    
    # 使用腐蚀操作收缩选区
    for _ in range(pixels):
        padded = np.pad(binary, 1, mode='constant', constant_values=False)
        # 3x3邻域，所有邻居都是True，当前才是True
        binary = (
            padded[:-2, :-2] & padded[:-2, 1:-1] & padded[:-2, 2:] &
            padded[1:-1, :-2] & padded[1:-1, 1:-1] & padded[1:-1, 2:] &
            padded[2:, :-2] & padded[2:, 1:-1] & padded[2:, 2:]
        )
    
    return binary.astype(np.float32)


def expand_selection_by_color(image: np.ndarray, mask: np.ndarray, tolerance: int = 32, 
                               contiguous: bool = True) -> np.ndarray:
    """基于颜色相似性扩展选区（更智能的版本）
    
    分析选区边缘每个像素的颜色，然后在图像中查找相似颜色
    
    Args:
        image: RGB或RGBA图像
        mask: 当前选区mask
        tolerance: 颜色容差
        contiguous: 是否只扩展与选区相邻的区域
    
    Returns:
        扩展后的mask
    """
    if mask is None or not np.any(mask > 0):
        return mask
    
    h, w = mask.shape
    binary = (mask > 0.5)
    
    # 提取边缘像素坐标
    padded = np.pad(binary, 1, mode='constant', constant_values=False)
    edge_mask = (
        (padded[:-2, 1:-1] & ~binary) |
        (padded[2:, 1:-1] & ~binary) |
        (padded[1:-1, :-2] & ~binary) |
        (padded[1:-1, 2:] & ~binary)
    )
    
    edge_points = np.argwhere(edge_mask)
    if len(edge_points) == 0:
        return mask
    
    # 获取图像RGB
    if len(image.shape) == 3 and image.shape[2] >= 3:
        rgb = image[:, :, :3].astype(np.int16)
    else:
        return mask
    
    # 收集边缘颜色
    edge_colors = []
    for y, x in edge_points:
        edge_colors.append(rgb[y, x])
    
    if len(edge_colors) == 0:
        return mask
    
    edge_colors = np.array(edge_colors)
    
    # 计算每个非选区像素与最近边缘颜色的距离
    non_selected = ~binary
    non_selected_points = np.argwhere(non_selected)
    
    if len(non_selected_points) == 0:
        return mask
    
    new_mask = binary.copy()
    
    # 批量处理以提高性能
    for y, x in non_selected_points:
        pixel_color = rgb[y, x]
        # 计算与所有边缘颜色的最小距离
        color_diff = np.abs(edge_colors - pixel_color)
        min_dist = np.min(np.max(color_diff, axis=1))
        
        if min_dist <= tolerance:
            if contiguous:
                # 检查是否与现有选区相邻
                has_neighbor = False
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and binary[ny, nx]:
                        has_neighbor = True
                        break
                if has_neighbor:
                    new_mask[y, x] = True
            else:
                new_mask[y, x] = True
    
    return new_mask.astype(np.float32)
