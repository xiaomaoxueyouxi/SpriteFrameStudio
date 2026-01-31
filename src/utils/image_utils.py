"""图像处理工具"""
from typing import Optional, Tuple
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


def create_checkerboard(
    width: int,
    height: int,
    square_size: int = 10,
    color1: Tuple[int, int, int] = (200, 200, 200),
    color2: Tuple[int, int, int] = (255, 255, 255)
) -> np.ndarray:
    """创建棋盘格背景(用于显示透明图像)"""
    board = np.zeros((height, width, 3), dtype=np.uint8)
    
    for y in range(0, height, square_size):
        for x in range(0, width, square_size):
            if ((x // square_size) + (y // square_size)) % 2 == 0:
                color = color1
            else:
                color = color2
            
            y_end = min(y + square_size, height)
            x_end = min(x + square_size, width)
            board[y:y_end, x:x_end] = color
    
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
