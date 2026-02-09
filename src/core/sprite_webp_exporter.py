"""精灵图WebP导出器"""
import numpy as np
from PIL import Image
from typing import List, Tuple, Optional
from pathlib import Path

from src.models.frame_data import FrameData
from src.models.export_config import ExportConfig


def export_sprite_sheet_as_webp(
    frames: List[FrameData],
    config: ExportConfig
) -> Tuple[str, Optional[str]]:
    """导出精灵图为WebP格式"""
    if not frames:
        raise ValueError("没有要导出的帧")
    
    sprite_config = config.sprite_config
    webp_config = config.webp_config
    output_path = config.get_output_file()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 收集图像
    images = []
    for frame in frames:
        img = frame.display_image
        if img is not None:
            # 如果需要调整尺寸
            if sprite_config.frame_width and sprite_config.frame_height:
                pil_img = Image.fromarray(img)
                # 使用精灵图配置的缩放算法
                resample_filter = get_pil_resample_filter(sprite_config.resample_filter)
                pil_img = pil_img.resize(
                    (sprite_config.frame_width, sprite_config.frame_height),
                    resample_filter
                )
                img = np.array(pil_img)
            images.append((frame.index, img))
    
    if not images:
        raise ValueError("没有可导出的图像")
    
    # 获取单帧尺寸
    frame_height, frame_width = images[0][1].shape[:2]
    has_alpha = images[0][1].shape[2] == 4 if len(images[0][1].shape) == 3 else False
    
    # 计算布局
    num_frames = len(images)
    padding = sprite_config.padding
    
    if sprite_config.layout == LayoutMode.HORIZONTAL:
        cols = num_frames
        rows = 1
    elif sprite_config.layout == LayoutMode.VERTICAL:
        cols = 1
        rows = num_frames
    else:  # GRID
        cols = sprite_config.columns or math.ceil(math.sqrt(num_frames))
        rows = math.ceil(num_frames / cols)
    
    # 计算精灵图尺寸
    sheet_width = cols * (frame_width + padding) - padding
    sheet_height = rows * (frame_height + padding) - padding
    
    # 创建精灵图
    if has_alpha:
        sheet = np.zeros((sheet_height, sheet_width, 4), dtype=np.uint8)
    else:
        sheet = np.zeros((sheet_height, sheet_width, 3), dtype=np.uint8)
    
    # 填充帧
    for i, (frame_index, img) in enumerate(images):
        row = i // cols
        col = i % cols
        
        x = col * (frame_width + padding)
        y = row * (frame_height + padding)
        
        # 确保图像通道匹配
        if has_alpha and img.shape[2] == 3:
            alpha = np.full((frame_height, frame_width, 1), 255, dtype=np.uint8)
            img = np.concatenate([img, alpha], axis=2)
        elif not has_alpha and img.shape[2] == 4:
            img = img[:, :, :3]
        
        sheet[y:y+frame_height, x:x+frame_width] = img
    
    # 保存为WebP
    pil_sheet = Image.fromarray(sheet)
    pil_sheet.save(str(output_path), format='WebP', quality=webp_config.quality)
    
    return (str(output_path), None)