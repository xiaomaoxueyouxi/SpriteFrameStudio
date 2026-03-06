"""循环过渡工具 - 用于帧动画首尾无缝循环（支持像素混合和轮廓对齐两种模式）"""
from typing import List, Tuple
import numpy as np
import cv2


# ============================================================
# 公共入口
# ============================================================

def apply_loop_transition(
    frames: List[np.ndarray],
    transition_count: int,
    mode: str = "blend"
) -> List[np.ndarray]:
    """
    对帧序列应用循环过渡，使首尾无缝衔接。
    
    Args:
        frames: 帧图像列表 (numpy数组，支持RGB和RGBA)
        transition_count: 过渡帧数（重叠区间长度）
        mode: "blend"=像素混合, "align"=轮廓对齐
    
    Returns:
        过渡后的帧列表，长度为 len(frames) - transition_count
    """
    if mode == "align":
        return apply_loop_align(frames, transition_count)
    else:
        return apply_loop_crossfade(frames, transition_count)


def apply_transition_to_frame_data(frames, transition_count: int, mode: str = "blend"):
    """
    对 FrameData 列表应用循环过渡（用于导出）。
    非破坏性：通过浅拷贝创建新的 FrameData，不修改原始数据。
    
    Args:
        frames: List[FrameData] 帧数据列表
        transition_count: 过渡帧数
        mode: "blend"=像素混合, "align"=轮廓对齐
    
    Returns:
        List[FrameData] 过渡后的帧数据列表
    """
    if not frames or len(frames) <= 1 or transition_count <= 0:
        return list(frames)
    
    total = len(frames)
    T = min(transition_count, total // 2)
    if T <= 0:
        return list(frames)
    
    # 提取所有帧的显示图像
    images = []
    for f in frames:
        img = f.display_image
        if img is None:
            img = f.image
        images.append(img)
    
    if any(img is None for img in images):
        return list(frames)
    
    # 应用过渡
    result_images = apply_loop_transition(images, T, mode)
    
    # 构建输出 FrameData 列表
    result = []
    
    # 混合/形变区帧
    for k in range(T):
        tail_idx = total - T + k
        
        if T == 1:
            alpha = 0.5
        else:
            alpha = k / (T - 1)
        
        if alpha == 0.0:
            result.append(frames[tail_idx])
        elif alpha == 1.0:
            result.append(frames[k])
        else:
            frame_copy = frames[tail_idx].model_copy()
            frame_copy.processed_image = result_images[k]
            result.append(frame_copy)
    
    # 非重叠区帧
    for k in range(T, total - T):
        result.append(frames[k])
    
    return result


# ============================================================
# 模式1：像素混合 (blend)
# ============================================================

def apply_loop_crossfade(
    frames: List[np.ndarray],
    transition_count: int
) -> List[np.ndarray]:
    """
    重叠交叉淡入淡出：将末尾T帧与开头T帧一一对应混合。
    输出序列长度 = N - T。
    """
    if not frames:
        return []
    
    total = len(frames)
    if transition_count <= 0 or total <= 1:
        return list(frames)
    
    T = min(transition_count, total // 2)
    if T <= 0:
        return list(frames)
    
    result = []
    
    for k in range(T):
        tail_frame = frames[total - T + k]
        head_frame = frames[k]
        
        if T == 1:
            alpha = 0.5
        else:
            alpha = k / (T - 1)
        
        if alpha == 0.0:
            result.append(tail_frame)
        elif alpha == 1.0:
            result.append(head_frame)
        else:
            tail_ch = tail_frame.shape[2] if len(tail_frame.shape) == 3 else 1
            head_ch = head_frame.shape[2] if len(head_frame.shape) == 3 else 1
            
            tail_f32, head_f32, need_strip = _match_channels(
                tail_frame.astype(np.float32),
                head_frame.astype(np.float32),
                tail_ch, head_ch
            )
            
            blended = (1.0 - alpha) * tail_f32 + alpha * head_f32
            blended = np.clip(blended, 0, 255).astype(np.uint8)
            if need_strip:
                blended = blended[:, :, :3]
            result.append(blended)
    
    for k in range(T, total - T):
        result.append(frames[k])
    
    return result


# ============================================================
# 模式2：轮廓对齐 (align)
# ============================================================

def apply_loop_align(
    frames: List[np.ndarray],
    transition_count: int
) -> List[np.ndarray]:
    """
    轮廓对齐过渡：通过alpha通道质心对齐 + 仅RGB混合，保留清晰轮廓。
    
    算法：
      - 计算每帧alpha通道的质心（不透明区域的重心）
      - 对于过渡区每一对(尾帧, 头帧)：
        - 根据混合比例，计算中间质心位置
        - 将尾帧和头帧分别平移对齐到中间质心
        - 仅混合RGB通道，alpha通道取两者最大值（保持清晰边缘）
      - 输出序列长度 = N - T
    """
    if not frames:
        return []
    
    total = len(frames)
    if transition_count <= 0 or total <= 1:
        return list(frames)
    
    T = min(transition_count, total // 2)
    if T <= 0:
        return list(frames)
    
    result = []
    
    for k in range(T):
        tail_frame = frames[total - T + k]
        head_frame = frames[k]
        
        if T == 1:
            alpha = 0.5
        else:
            alpha = k / (T - 1)
        
        if alpha == 0.0:
            result.append(tail_frame)
        elif alpha == 1.0:
            result.append(head_frame)
        else:
            aligned = _align_interpolate(tail_frame, head_frame, alpha)
            result.append(aligned)
    
    for k in range(T, total - T):
        result.append(frames[k])
    
    return result


def _alpha_centroid(img: np.ndarray) -> Tuple[float, float]:
    """
    计算图像不透明区域的质心（重心）。
    
    Returns:
        (cx, cy) 质心坐标（亚像素精度）
    """
    h, w = img.shape[:2]
    
    if len(img.shape) == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3].astype(np.float64)
    else:
        # 无alpha通道，返回图像中心
        return (w / 2.0, h / 2.0)
    
    total = alpha.sum()
    if total < 1e-6:
        return (w / 2.0, h / 2.0)
    
    y_coords, x_coords = np.mgrid[0:h, 0:w]
    cx = float((x_coords * alpha).sum() / total)
    cy = float((y_coords * alpha).sum() / total)
    return (cx, cy)


def _shift_image(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """
    亚像素精度平移图像。
    
    Args:
        img: 输入图像（RGB或RGBA）
        dx: 水平偏移（正值向右）
        dy: 垂直偏移（正值向下）
    
    Returns:
        平移后的图像，超出边界的区域填充为透明/黑色
    """
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return img.copy()
    
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    
    has_alpha = len(img.shape) == 3 and img.shape[2] == 4
    border_value = (0, 0, 0, 0) if has_alpha else (0, 0, 0)
    
    return cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value
    )


def _align_interpolate(
    src: np.ndarray,
    dst: np.ndarray,
    alpha: float
) -> np.ndarray:
    """
    对齐两帧的质心位置，然后仅混合RGB通道，alpha通道保持清晰。
    
    alpha=0 → src, alpha=1 → dst
    """
    # 统一通道
    src_ch = src.shape[2] if len(src.shape) == 3 else 1
    dst_ch = dst.shape[2] if len(dst.shape) == 3 else 1
    
    if src_ch != dst_ch:
        src, dst = _ensure_same_channels(src, dst, src_ch, dst_ch)
    
    has_alpha_ch = src.shape[2] == 4 if len(src.shape) == 3 else False
    
    # 计算两帧的质心
    cx_src, cy_src = _alpha_centroid(src)
    cx_dst, cy_dst = _alpha_centroid(dst)
    
    # 目标质心：按alpha比例插值
    cx_target = (1.0 - alpha) * cx_src + alpha * cx_dst
    cy_target = (1.0 - alpha) * cy_src + alpha * cy_dst
    
    # 将src和dst分别平移到目标质心位置
    dx_src = cx_target - cx_src
    dy_src = cy_target - cy_src
    shifted_src = _shift_image(src, dx_src, dy_src)
    
    dx_dst = cx_target - cx_dst
    dy_dst = cy_target - cy_dst
    shifted_dst = _shift_image(dst, dx_dst, dy_dst)
    
    if has_alpha_ch:
        # 仅混合RGB通道
        rgb_src = shifted_src[:, :, :3].astype(np.float32)
        rgb_dst = shifted_dst[:, :, :3].astype(np.float32)
        
        # 使用alpha通道作为权重进行预乘混合，避免透明区域污染颜色
        a_src = shifted_src[:, :, 3:4].astype(np.float32) / 255.0
        a_dst = shifted_dst[:, :, 3:4].astype(np.float32) / 255.0
        
        # 预乘RGB
        premul_src = rgb_src * a_src
        premul_dst = rgb_dst * a_dst
        
        # 混合预乘后的RGB
        blended_premul = (1.0 - alpha) * premul_src + alpha * premul_dst
        
        # alpha通道取两者最大值（保持清晰轮廓，不产生半透明边缘）
        alpha_src = shifted_src[:, :, 3].astype(np.float32)
        alpha_dst = shifted_dst[:, :, 3].astype(np.float32)
        blended_alpha = np.maximum(alpha_src, alpha_dst)
        
        # 反预乘：从预乘RGB恢复到直通RGB
        out_a = blended_alpha[:, :, np.newaxis] / 255.0
        safe_a = np.where(out_a > 1e-6, out_a, 1.0)
        blended_rgb = blended_premul / safe_a
        
        # 组装结果
        result = np.zeros_like(src)
        result[:, :, :3] = np.clip(blended_rgb, 0, 255).astype(np.uint8)
        result[:, :, 3] = np.clip(blended_alpha, 0, 255).astype(np.uint8)
    else:
        # 无alpha通道，直接混合
        result = ((1.0 - alpha) * shifted_src.astype(np.float32) +
                  alpha * shifted_dst.astype(np.float32))
        result = np.clip(result, 0, 255).astype(np.uint8)
    
    return result


def _ensure_same_channels(
    img_a: np.ndarray,
    img_b: np.ndarray,
    ch_a: int,
    ch_b: int
) -> Tuple[np.ndarray, np.ndarray]:
    """确保两个图像通道数一致"""
    if ch_a == 3 and ch_b == 4:
        h, w = img_a.shape[:2]
        alpha = np.full((h, w, 1), 255, dtype=np.uint8)
        img_a = np.concatenate([img_a, alpha], axis=2)
    elif ch_a == 4 and ch_b == 3:
        h, w = img_b.shape[:2]
        alpha = np.full((h, w, 1), 255, dtype=np.uint8)
        img_b = np.concatenate([img_b, alpha], axis=2)
    return img_a, img_b


# ============================================================
# 通道匹配（blend 模式用）
# ============================================================

def _match_channels(
    img_a: np.ndarray,
    img_b: np.ndarray,
    channels_a: int,
    channels_b: int
) -> Tuple[np.ndarray, np.ndarray, bool]:
    """确保两个 float32 图像通道数一致以便混合"""
    if channels_a == channels_b:
        return img_a, img_b, False
    
    if channels_a == 3 and channels_b == 4:
        h, w = img_a.shape[:2]
        alpha = np.full((h, w, 1), 255.0, dtype=np.float32)
        img_a = np.concatenate([img_a, alpha], axis=2)
        return img_a, img_b, False
    
    if channels_a == 4 and channels_b == 3:
        h, w = img_b.shape[:2]
        alpha = np.full((h, w, 1), 255.0, dtype=np.float32)
        img_b = np.concatenate([img_b, alpha], axis=2)
        return img_a, img_b, False
    
    return img_a, img_b, False
