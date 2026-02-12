"""图像处理工具"""
from typing import Optional, Tuple
from functools import lru_cache
import numpy as np
from PIL import Image
from PySide6.QtGui import QImage, QPixmap


def numpy_to_qimage(array: np.ndarray) -> QImage:
    """将numpy数组转换为QImage"""
    if array is None:
        return QImage()
    
    # 确保数组是连续的
    if not array.flags['C_CONTIGUOUS']:
        array = np.ascontiguousarray(array)
    
    height, width = array.shape[:2]
    
    if len(array.shape) == 2:
        # 灰度图
        bytes_per_line = width
        qimg = QImage(array.data, width, height, bytes_per_line, QImage.Format_Grayscale8)
    elif array.shape[2] == 3:
        # RGB
        bytes_per_line = 3 * width
        qimg = QImage(array.data, width, height, bytes_per_line, QImage.Format_RGB888)
    elif array.shape[2] == 4:
        # RGBA
        bytes_per_line = 4 * width
        qimg = QImage(array.data, width, height, bytes_per_line, QImage.Format_RGBA8888)
    else:
        return QImage()
    
    # 返回副本，避免数据引用问题
    return qimg.copy()


def numpy_to_qpixmap(array: np.ndarray) -> QPixmap:
    """将numpy数组转换为QPixmap"""
    qimage = numpy_to_qimage(array)
    return QPixmap.fromImage(qimage)


def qimage_to_numpy(qimage: QImage) -> np.ndarray:
    """将QImage转换为numpy数组"""
    qimage = qimage.convertToFormat(QImage.Format_RGBA8888)
    
    width = qimage.width()
    height = qimage.height()
    
    ptr = qimage.bits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 4))
    return arr.copy()


def resize_image(
    image: np.ndarray,
    target_size: Tuple[int, int],
    keep_aspect: bool = True
) -> np.ndarray:
    """
    调整图像大小
    
    Args:
        image: 原图
        target_size: 目标尺寸 (width, height)
        keep_aspect: 是否保持宽高比
    """
    pil_image = Image.fromarray(image)
    
    if keep_aspect:
        pil_image.thumbnail(target_size, Image.Resampling.LANCZOS)
        # 创建目标尺寸的背景
        result = Image.new('RGBA', target_size, (0, 0, 0, 0))
        # 居中粘贴
        offset = ((target_size[0] - pil_image.width) // 2,
                  (target_size[1] - pil_image.height) // 2)
        if pil_image.mode == 'RGBA':
            result.paste(pil_image, offset, pil_image)
        else:
            result.paste(pil_image, offset)
        return np.array(result)
    else:
        resized = pil_image.resize(target_size, Image.Resampling.LANCZOS)
        return np.array(resized)


def create_thumbnail(
    image: np.ndarray,
    max_size: int = 128
) -> np.ndarray:
    """创建缩略图"""
    pil_image = Image.fromarray(image)
    pil_image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return np.array(pil_image)


@lru_cache(maxsize=32)
def create_checkerboard(
    width: int,
    height: int,
    square_size: int = 10,
    color1: Tuple[int, int, int] = (200, 200, 200),
    color2: Tuple[int, int, int] = (255, 255, 255)
) -> np.ndarray:
    """创建棋盘格背景(用于显示透明图像) - 带缓存"""
    board = np.zeros((height, width, 3), dtype=np.uint8)
    
    # 使用 numpy 向量化操作代替循环，大幅提升性能
    # 创建坐标网格
    y_coords, x_coords = np.ogrid[:height, :width]
    # 计算每个格子是否使用 color1
    grid_x = x_coords // square_size
    grid_y = y_coords // square_size
    use_color1 = ((grid_x + grid_y) % 2 == 0)
    # 使用广播填充颜色
    board[:] = np.where(use_color1[:, :, np.newaxis], color1, color2)
    
    return board


def composite_on_checkerboard(
    image: np.ndarray,
    square_size: int = 10
) -> np.ndarray:
    """将带透明通道的图像合成到棋盘格背景上"""
    if image is None:
        return None
    
    if len(image.shape) != 3 or image.shape[2] != 4:
        return image
    
    h, w = image.shape[:2]
    checkerboard = create_checkerboard(w, h, square_size)
    
    # 使用alpha混合
    alpha = image[:, :, 3:4] / 255.0
    rgb = image[:, :, :3]
    
    result = (rgb * alpha + checkerboard * (1 - alpha)).astype(np.uint8)
    return result


def blend_with_overlay(
    base_image: np.ndarray,
    overlay: np.ndarray,
    mask: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    将叠加层混合到基础图像上
    
    Args:
        base_image: 基础图像
        overlay: 叠加层图像 (RGBA)
        mask: 可选的遮罩
    
    Returns:
        混合后的图像
    """
    if base_image is None or overlay is None:
        return base_image
    
    # 确保尺寸匹配
    if base_image.shape[:2] != overlay.shape[:2]:
        overlay = Image.fromarray(overlay)
        overlay = overlay.resize((base_image.shape[1], base_image.shape[0]), Image.Resampling.NEAREST)
        overlay = np.array(overlay)
    
    # 提取叠加层的alpha通道
    if overlay.shape[2] == 4:
        overlay_alpha = overlay[:, :, 3] / 255.0
        overlay_rgb = overlay[:, :, :3]
    else:
        overlay_alpha = np.ones(overlay.shape[:2])
        overlay_rgb = overlay
    
    # 应用遮罩
    if mask is not None:
        overlay_alpha = overlay_alpha * (mask / 255.0)
    
    # 扩展alpha维度
    overlay_alpha = overlay_alpha[:, :, np.newaxis]
    
    # Alpha混合
    if base_image.shape[2] == 4:
        base_rgb = base_image[:, :, :3]
        base_alpha = base_image[:, :, 3:4] / 255.0
        
        # 计算最终alpha
        out_alpha = overlay_alpha + base_alpha * (1 - overlay_alpha)
        
        # 计算最终RGB
        out_rgb = (overlay_rgb * overlay_alpha + base_rgb * base_alpha * (1 - overlay_alpha)) / (out_alpha + 1e-6)
        
        result = np.concatenate([out_rgb, out_alpha * 255], axis=2).astype(np.uint8)
    else:
        result = (overlay_rgb * overlay_alpha + base_image * (1 - overlay_alpha)).astype(np.uint8)
    
    return result


def create_selection_overlay(
    mask: np.ndarray,
    color: Tuple[int, int, int, int] = (0, 255, 0, 128),
    feather: int = 0
) -> np.ndarray:
    """
    创建选区叠加层
    
    Args:
        mask: 选区掩码 (二值图像)
        color: 叠加层颜色 (RGBA)
        feather: 羽化半径
    
    Returns:
        叠加层图像 (RGBA)
    """
    if mask is None or not np.any(mask > 0):
        return np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
    
    h, w = mask.shape[:2]
    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    
    # 应用羽化
    if feather > 0:
        from scipy.ndimage import gaussian_filter
        mask_float = mask.astype(np.float32) / 255.0
        mask_blurred = gaussian_filter(mask_float, sigma=feather)
        mask = (mask_blurred * 255).astype(np.uint8)
    
    # 填充颜色
    overlay[mask > 0] = color
    
    # 根据mask调整alpha
    overlay[:, :, 3] = (overlay[:, :, 3] * (mask / 255.0)).astype(np.uint8)
    
    return overlay


def flood_fill_select(
    image: np.ndarray,
    seed_point: Tuple[int, int],
    tolerance: int,
    connectivity: int = 8
) -> np.ndarray:
    """
    洪水填充选择算法 (魔棒工具核心算法)
    
    Args:
        image: 输入图像
        seed_point: 种子点 (x, y)
        tolerance: 颜色容差
        connectivity: 连通性 (4或8)
    
    Returns:
        选区掩码
    """
    from collections import deque
    
    h, w = image.shape[:2]
    x, y = seed_point
    
    # 检查坐标范围
    if x < 0 or x >= w or y < 0 or y >= h:
        return np.zeros((h, w), dtype=np.uint8)
    
    # 获取种子点颜色
    if len(image.shape) == 3:
        seed_color = image[y, x, :3].astype(np.int16)
    else:
        seed_color = np.array([int(image[y, x])])
    
    # 创建访问标记和选区
    visited = np.zeros((h, w), dtype=np.bool_)
    selection = np.zeros((h, w), dtype=np.uint8)
    
    # BFS队列
    queue = deque()
    queue.append((x, y))
    visited[y, x] = True
    selection[y, x] = 255
    
    # 邻居偏移
    if connectivity == 8:
        neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    else:
        neighbors = [(-1, 0), (0, -1), (0, 1), (1, 0)]
    
    while queue:
        cx, cy = queue.popleft()
        
        for dx, dy in neighbors:
            nx, ny = cx + dx, cy + dy
            
            # 检查边界
            if nx < 0 or nx >= w or ny < 0 or ny >= h:
                continue
            
            if visited[ny, nx]:
                continue
            
            # 计算颜色差异
            if len(image.shape) == 3:
                current_color = image[ny, nx, :3].astype(np.int16)
            else:
                current_color = np.array([int(image[ny, nx])])
            
            color_diff = np.abs(current_color - seed_color).max()
            
            if color_diff <= tolerance:
                visited[ny, nx] = True
                selection[ny, nx] = 255
                queue.append((nx, ny))
    
    return selection
