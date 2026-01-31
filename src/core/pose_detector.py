"""姿势检测模块"""
from typing import List, Optional, Callable, Tuple
import numpy as np
import uuid
import cv2
from pathlib import Path
import os


def get_default_rtm_models():
    """获取默认的 RTMPose 模型路径（从项目 models/rtmpose 目录）
    
    Returns:
        tuple: (检测模型路径, 姿态模型路径) 或 (None, None) 如果模型不存在
    """
    # 获取项目根目录
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent
    models_dir = project_root / "models" / "rtmpose"
    
    # 定义模型文件名
    det_model_name = "yolox_m_8xb8-300e_humanart-c2c7a14a.onnx"
    pose_model_name = "rtmw-dw-x-l_simcc-cocktail14_270e-256x192_20231122.onnx"
    
    det_model_path = models_dir / det_model_name
    pose_model_path = models_dir / pose_model_name
    
    # 检查模型文件是否存在
    if det_model_path.exists() and pose_model_path.exists():
        print(f"[INFO] 找到本地 RTMPose 模型:")
        print(f"  检测模型: {det_model_path}")
        print(f"  姿态模型: {pose_model_path}")
        return str(det_model_path), str(pose_model_path)
    else:
        print(f"[WARNING] 本地模型目录不存在或模型文件缺失: {models_dir}")
        if not det_model_path.exists():
            print(f"  缺失检测模型: {det_model_name}")
        if not pose_model_path.exists():
            print(f"  缺失姿态模型: {pose_model_name}")
        return None, None


class ContourData:
    """轮廓数据 - 用于非人形角色的动作比对"""
    
    def __init__(self, frame_index: int, hu_moments: np.ndarray, contour: Optional[np.ndarray] = None):
        self.id = str(uuid.uuid4())
        self.frame_index = frame_index
        self.hu_moments = hu_moments  # Hu矩特征(7维)
        self.contour = contour  # 可选：存储轮廓点
    
    def similarity_to(self, other: "ContourData") -> float:
        """计算与另一个轮廓的相似度 (0-1, 1为完全相同)"""
        if self.hu_moments is None or other.hu_moments is None:
            return 0.0
        
        # 使用OpenCV的matchShapes (Hu矩匹配)
        # 返回值越小越相似，0为完全相同
        # 使用I1方法 (cv2.CONTOURS_MATCH_I1)
        diff = cv2.matchShapes(
            self.hu_moments.reshape(-1, 1).astype(np.float32),
            other.hu_moments.reshape(-1, 1).astype(np.float32),
            cv2.CONTOURS_MATCH_I1, 0
        )
        
        # 将差异转换为相似度：diff=0 -> sim=1, diff越大 sim越小
        # 使用指数衰减，调整系数让差异更明显
        similarity = np.exp(-diff * 2)
        return float(similarity)


class ImageFeatureData:
    """图像特征数据 - 用于通用图像相似度比对"""
    
    def __init__(self, frame_index: int, hist: np.ndarray, phash: Optional[np.ndarray] = None):
        self.id = str(uuid.uuid4())
        self.frame_index = frame_index
        self.hist = hist  # 颜色直方图
        self.phash = phash  # 感知哈希 (可选)
    
    def similarity_to(self, other: "ImageFeatureData") -> float:
        """计算与另一个图像的相似度 (0-1, 1为完全相同)"""
        if self.hist is None or other.hist is None:
            return 0.0
        
        # 使用直方图相关性比对
        # cv2.HISTCMP_CORREL: 返回值 [-1, 1]，1为完全匹配
        correlation = cv2.compareHist(
            self.hist.astype(np.float32),
            other.hist.astype(np.float32),
            cv2.HISTCMP_CORREL
        )
        
        # 如果有感知哈希，混合两种方法
        if self.phash is not None and other.phash is not None:
            # 汉明距离：相同位数
            hamming_dist = np.count_nonzero(self.phash != other.phash)
            # 64位哈希，距离0-64，转换为相似度
            phash_sim = 1.0 - hamming_dist / 64.0
            # 混合：直方图60% + 感知哈希40%
            similarity = 0.6 * max(0, correlation) + 0.4 * phash_sim
        else:
            # 只用直方图，映射到0-1
            similarity = max(0, correlation)
        
        return float(similarity)


class RegionalFeatureData:
    """分区域特征数据 - 适合动漫角色的精确动作比对
    
    将图像分为上/中/下三个区域，分别计算SSIM结构相似度
    可以单独关注脚部动作变化
    """
    
    # 区域权重：上部(头)/中部(躯干)/下部(腿脚)
    DEFAULT_WEIGHTS = (0.2, 0.3, 0.5)  # 默认重点关注下半身
    
    def __init__(self, frame_index: int, 
                 upper_gray: np.ndarray,
                 middle_gray: np.ndarray, 
                 lower_gray: np.ndarray,
                 weights: Tuple[float, float, float] = None):
        self.id = str(uuid.uuid4())
        self.frame_index = frame_index
        self.upper_gray = upper_gray    # 上部灰度图 (头/肩)
        self.middle_gray = middle_gray  # 中部灰度图 (躯干)
        self.lower_gray = lower_gray    # 下部灰度图 (腿/脚)
        self.weights = weights or self.DEFAULT_WEIGHTS
    
    @staticmethod
    def compute_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
        """计算两张灰度图的SSIM结构相似度"""
        if img1 is None or img2 is None:
            return 0.0
        if img1.shape != img2.shape:
            # 尺寸不同时resize到相同大小
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
        
        # SSIM参数
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        img1 = img1.astype(np.float64)
        img2 = img2.astype(np.float64)
        
        # 均值
        mu1 = cv2.GaussianBlur(img1, (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(img2, (11, 11), 1.5)
        
        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2
        
        # 方差和协方差
        sigma1_sq = cv2.GaussianBlur(img1 ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(img2 ** 2, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(img1 * img2, (11, 11), 1.5) - mu1_mu2
        
        # SSIM公式
        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                   ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
        
        return float(np.mean(ssim_map))
    
    def similarity_to(self, other: "RegionalFeatureData") -> float:
        """计算与另一帧的分区域加权相似度 (0-1, 1为完全相同)"""
        # 分别计算三个区域的SSIM
        upper_ssim = self.compute_ssim(self.upper_gray, other.upper_gray)
        middle_ssim = self.compute_ssim(self.middle_gray, other.middle_gray)
        lower_ssim = self.compute_ssim(self.lower_gray, other.lower_gray)
        
        # 加权平均 (默认重点关注下半身)
        w_upper, w_middle, w_lower = self.weights
        weighted_ssim = w_upper * upper_ssim + w_middle * middle_ssim + w_lower * lower_ssim
        
        # 确保返回值在0-1范围
        return float(max(0.0, min(1.0, weighted_ssim)))
    
    def get_region_similarities(self, other: "RegionalFeatureData") -> dict:
        """获取各区域的详细相似度，用于调试"""
        return {
            'upper': self.compute_ssim(self.upper_gray, other.upper_gray),
            'middle': self.compute_ssim(self.middle_gray, other.middle_gray),
            'lower': self.compute_ssim(self.lower_gray, other.lower_gray),
            'weights': self.weights
        }


class PoseDetector:
    """姿势检测器 - 使用MediaPipe Pose"""
    
    def __init__(self, rtm_det_model: str = None, rtm_pose_model: str = None):
        self._pose = None
        self._cancel_flag = False
        self._rtm_model = None
        self._rtm_backend = 'onnxruntime'
        self._rtm_device = 'cpu'
        
        # 如果没有指定模型路径，尝试使用项目本地模型
        if rtm_det_model is None or rtm_pose_model is None:
            default_det, default_pose = get_default_rtm_models()
            self._rtm_det_model = rtm_det_model or default_det
            self._rtm_pose_model = rtm_pose_model or default_pose
        else:
            self._rtm_det_model = rtm_det_model
            self._rtm_pose_model = rtm_pose_model
    
    def cancel(self):
        """取消操作"""
        self._cancel_flag = True
    
    def _init_mediapipe(self):
        """初始化MediaPipe(懒加载)"""
        if self._pose is None:
            try:
                import mediapipe as mp
                self._mp_pose = mp.solutions.pose
                self._mp_drawing = mp.solutions.drawing_utils
                self._pose = self._mp_pose.Pose(
                    static_image_mode=True,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.5
                )
            except ImportError:
                raise ImportError("请安装mediapipe: pip install mediapipe")
    
    def _init_rtm_model(self):
        """初始化 rtmlib Wholebody 模型(懒加载)"""
        if self._rtm_model is None:
            try:
                # 尝试先从本地 rtmlib 目录导入（如果存在）
                import sys
                from pathlib import Path
                project_root = Path(__file__).parent.parent.parent
                rtmlib_path = project_root / "rtmlib"
                # rtmlib 是单层目录结构，需要把 project_root 加入 sys.path
                if rtmlib_path.exists() and str(project_root) not in sys.path:
                    sys.path.insert(0, str(project_root))
                    print(f"[INFO] 添加本地 rtmlib 路径: {project_root}")
                
                from rtmlib import Wholebody
            except ImportError as e:
                import traceback
                error_detail = traceback.format_exc()
                print(f"[DEBUG] rtmlib 导入失败详情:\n{error_detail}", file=sys.stderr)
                print(f"[DEBUG] 当前 Python 路径: {sys.executable}", file=sys.stderr)
                print(f"[DEBUG] sys.path: {sys.path}", file=sys.stderr)
                raise ImportError(
                    f"请安装 rtmlib 及其依赖后再使用 RTMPose 姿态检测。\n"
                    f"原始错误: {str(e)}\n"
                    f"Python 环境: {sys.executable}"
                ) from e

            # 如果指定了自定义模型路径,使用自定义路径;否则使用默认模式
            if self._rtm_det_model and self._rtm_pose_model:
                print(f"[INFO] 使用本地模型路径(离线模式)")
                print(f"  检测模型: {self._rtm_det_model}")
                print(f"  姿态模型: {self._rtm_pose_model}")
                            
                # 根据模型文件名推断输入尺寸
                det_input_size = (640, 640)  # yolox_m 默认尺寸
                            
                # 从姿态模型文件名中提取尺寸信息
                if '256x192' in self._rtm_pose_model:
                    pose_input_size = (192, 256)  # (width, height)
                elif '384x288' in self._rtm_pose_model:
                    pose_input_size = (288, 384)
                else:
                    pose_input_size = (192, 256)  # 默认尺寸
                            
                print(f"  检测输入尺寸: {det_input_size}")
                print(f"  姿态输入尺寸: {pose_input_size}")
                            
                self._rtm_model = Wholebody(
                    det=self._rtm_det_model,
                    det_input_size=det_input_size,
                    pose=self._rtm_pose_model,
                    pose_input_size=pose_input_size,
                    to_openpose=False,
                    backend=self._rtm_backend,
                    device=self._rtm_device,
                )
            else:
                print(f"[INFO] 本地模型未找到,使用 balanced 模式(将从网络下载)")
                print(f"  缓存目录: C:\\Users\\PC\\.cache\\rtmlib\\hub\\checkpoints\\")
                self._rtm_model = Wholebody(
                    to_openpose=False,
                    mode='balanced',
                    backend=self._rtm_backend,
                    device=self._rtm_device,
                )
    
    def detect_pose(self, image: np.ndarray, frame_index: int = 0):
        """
        检测单张图像中的姿势
        
        Args:
            image: RGB格式图像
            frame_index: 帧索引
        
        Returns:
            PoseData对象或None
        """
        from src.models.pose_data import PoseData, Landmark
        
        self._init_mediapipe()
        
        # 运行姿势检测
        results = self._pose.process(image)
        
        if results.pose_landmarks is None:
            return None
        
        # 转换关键点数据
        landmarks = []
        for lm in results.pose_landmarks.landmark:
            landmarks.append(Landmark(
                x=lm.x,
                y=lm.y,
                z=lm.z,
                visibility=lm.visibility
            ))
        
        # 计算整体置信度(可见关键点的平均可见度)
        visible_landmarks = [lm for lm in landmarks if lm.visibility > 0.5]
        confidence = sum(lm.visibility for lm in visible_landmarks) / len(visible_landmarks) if visible_landmarks else 0
        
        return PoseData(
            id=str(uuid.uuid4()),
            frame_index=frame_index,
            landmarks=landmarks,
            confidence=confidence
        )
    
    def detect_pose_rtm(self, image: np.ndarray, frame_index: int = 0):
        """使用 rtmlib RTMPose Wholebody 进行姿势检测"""
        from src.models.pose_data import PoseData, Landmark

        self._init_rtm_model()

        if image is None:
            return None

        # rtmlib 期望 BGR 图像
        bgr_image = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2BGR)

        keypoints, scores = self._rtm_model(bgr_image)

        if keypoints is None or len(keypoints) == 0:
            return None

        # 只取第一个人体
        if keypoints.ndim == 3:
            kpts = keypoints[0]
            kpt_scores = scores[0] if scores is not None and scores.ndim >= 2 else None
        else:
            kpts = keypoints
            kpt_scores = scores

        h, w = image.shape[:2]

        # COCO17 -> MediaPipe33 近似映射
        coco_to_mediapipe = {
            0: 0,   # nose
            1: 2,   # left_eye
            2: 5,   # right_eye
            3: 7,   # left_ear
            4: 8,   # right_ear
            5: 11,  # left_shoulder
            6: 12,  # right_shoulder
            7: 13,  # left_elbow
            8: 14,  # right_elbow
            9: 15,  # left_wrist
            10: 16, # right_wrist
            11: 23, # left_hip
            12: 24, # right_hip
            13: 25, # left_knee
            14: 26, # right_knee
            15: 27, # left_ankle
            16: 28, # right_ankle
        }

        num_landmarks = 33
        landmarks: List[Landmark] = []
        for _ in range(num_landmarks):
            landmarks.append(Landmark(x=0.0, y=0.0, z=0.0, visibility=0.0))

        for coco_idx, mp_idx in coco_to_mediapipe.items():
            if coco_idx >= len(kpts) or mp_idx >= num_landmarks:
                continue

            x, y = kpts[coco_idx][:2]
            if w > 0 and h > 0:
                x_norm = float(x) / float(w)
                y_norm = float(y) / float(h)
            else:
                x_norm = 0.0
                y_norm = 0.0

            if kpt_scores is not None and len(kpt_scores) > coco_idx:
                vis = float(kpt_scores[coco_idx])
            else:
                vis = 1.0

            landmarks[mp_idx] = Landmark(
                x=x_norm,
                y=y_norm,
                z=0.0,
                visibility=vis,
            )

        visible_landmarks = [lm for lm in landmarks if lm.visibility > 0.5]
        confidence = sum(lm.visibility for lm in visible_landmarks) / len(visible_landmarks) if visible_landmarks else 0.0

        return PoseData(
            id=str(uuid.uuid4()),
            frame_index=frame_index,
            landmarks=landmarks,
            confidence=confidence
        )
    
    def batch_detect(
        self,
        images: List[Tuple[np.ndarray, int]],  # (image, frame_index)
        progress_callback: Optional[Callable[[int, int, float], None]] = None
    ) -> list:
        """
        批量检测姿势
        
        Args:
            images: (图像, 帧索引)元组列表
            progress_callback: 进度回调
        
        Returns:
            PoseData列表(检测失败的为None)
        """
        self._cancel_flag = False
        results = []
        total = len(images)
        
        for i, (image, frame_index) in enumerate(images):
            if self._cancel_flag:
                break
            
            pose = self.detect_pose(image, frame_index)
            results.append(pose)
            
            if progress_callback:
                progress = (i + 1) / total * 100
                progress_callback(i + 1, total, progress)
        
        return results
    
    def draw_pose_on_image(
        self,
        image: np.ndarray,
        pose_data,
        draw_landmarks: bool = True,
        draw_connections: bool = True,
        landmark_color: Tuple[int, int, int] = (0, 184, 212), # Cyan
        connection_color: Tuple[int, int, int] = (255, 255, 255),
        thickness: int = 2
    ) -> np.ndarray:
        """
        在图像上绘制姿势骨架
        
        Args:
            image: RGB图像
            pose_data: PoseData对象
            draw_landmarks: 是否绘制关键点
            draw_connections: 是否绘制连接线
            landmark_color: 关键点颜色(RGB)
            connection_color: 连接线颜色(RGB)
            thickness: 线条粗细
        
        Returns:
            绘制后的图像
        """
        from src.models.pose_data import PoseData
        
        if pose_data is None:
            return image.copy()
        
        result = image.copy()
        h, w = image.shape[:2]
        
        # 绘制连接线
        if draw_connections:
            for start_idx, end_idx in PoseData.POSE_CONNECTIONS:
                start_lm = pose_data.get_landmark(start_idx)
                end_lm = pose_data.get_landmark(end_idx)
                
                if start_lm and end_lm:
                    if start_lm.visibility > 0.5 and end_lm.visibility > 0.5:
                        start_point = start_lm.to_pixel(w, h)
                        end_point = end_lm.to_pixel(w, h)
                        
                        # 使用cv2绘制
                        import cv2
                        cv2.line(result, start_point, end_point, connection_color, thickness)
        
        # 绘制关键点
        if draw_landmarks:
            import cv2
            for lm in pose_data.landmarks:
                if lm.visibility > 0.5:
                    point = lm.to_pixel(w, h)
                    cv2.circle(result, point, thickness + 2, landmark_color, -1)
        
        return result
    
    def compare_poses(self, pose1, pose2) -> float:
        """
        对比两个姿势的相似度
        
        Returns:
            相似度 0-1 (1为完全相同)
        """
        if pose1 is None or pose2 is None:
            return 0.0
        return pose1.similarity_to(pose2)
    
    def extract_contour(self, image: np.ndarray, frame_index: int = 0) -> Optional[ContourData]:
        """
        提取图像轮廓特征（用于非人形角色）
        
        Args:
            image: RGB或RGBA图像
            frame_index: 帧索引
        
        Returns:
            ContourData对象或None
        """
        # 如果是RGBA，使用alpha通道作为掩码
        if image.shape[2] == 4:
            alpha = image[:, :, 3]
            # 二值化alpha通道
            _, mask = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
        else:
            # RGB图像，转灰度后边缘检测
            gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2GRAY)
            # 使用Canny边缘检测
            edges = cv2.Canny(gray, 50, 150)
            # 膨胀以连接边缘
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.dilate(edges, kernel, iterations=2)
        
        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # 找最大轮廓（主体）
        main_contour = max(contours, key=cv2.contourArea)
        
        # 计算Hu矩
        moments = cv2.moments(main_contour)
        hu_moments = cv2.HuMoments(moments).flatten()
        
        # 对Hu矩取对数（因为原始值差异很大）
        # 避免log(0)
        hu_moments = np.sign(hu_moments) * np.log10(np.abs(hu_moments) + 1e-10)
        
        return ContourData(
            frame_index=frame_index,
            hu_moments=hu_moments,
            contour=main_contour
        )
    
    def batch_extract_contours(
        self,
        images: List[Tuple[np.ndarray, int]],
        progress_callback: Optional[Callable[[int, int, float], None]] = None
    ) -> List[Optional[ContourData]]:
        """
        批量提取轮廓特征
        
        Args:
            images: (图像, 帧索引)元组列表
            progress_callback: 进度回调
        
        Returns:
            ContourData列表
        """
        self._cancel_flag = False
        results = []
        total = len(images)
        
        for i, (image, frame_index) in enumerate(images):
            if self._cancel_flag:
                break
            
            contour_data = self.extract_contour(image, frame_index)
            results.append(contour_data)
            
            if progress_callback:
                progress = (i + 1) / total * 100
                progress_callback(i + 1, total, progress)
        
        return results
    
    def compare_contours(self, contour1: ContourData, contour2: ContourData) -> float:
        """
        对比两个轮廓的相似度
        
        Returns:
            相似度 0-1 (1为完全相同)
        """
        if contour1 is None or contour2 is None:
            return 0.0
        return contour1.similarity_to(contour2)
    
    def _compute_phash(self, image: np.ndarray, hash_size: int = 8) -> np.ndarray:
        """计算感知哈希 (pHash)"""
        # 转灰度
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            gray = image
        
        # 缩放到 (hash_size+1) x hash_size
        resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
        
        # 计算差异：比较相邻像素
        diff = resized[:, 1:] > resized[:, :-1]
        
        return diff.flatten()
    
    def extract_image_features(self, image: np.ndarray, frame_index: int = 0) -> Optional[ImageFeatureData]:
        """
        提取图像特征（颜色直方图 + 感知哈希）
        
        Args:
            image: RGB或RGBA图像
            frame_index: 帧索引
        
        Returns:
            ImageFeatureData对象或None
        """
        if image is None:
            return None
        
        # 获取RGB部分
        rgb = image[:, :, :3] if image.shape[2] >= 3 else image
        
        # 转换到HSV空间计算直方图（对光照变化更鲁棒）
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        
        # 计算H和S通道的联合直方图
        # H: 0-180, S: 0-256
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        
        # 归一化
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        hist = hist.flatten()
        
        # 计算感知哈希
        phash = self._compute_phash(rgb)
        
        return ImageFeatureData(
            frame_index=frame_index,
            hist=hist,
            phash=phash
        )
    
    def batch_extract_image_features(
        self,
        images: List[Tuple[np.ndarray, int]],
        progress_callback: Optional[Callable[[int, int, float], None]] = None
    ) -> List[Optional[ImageFeatureData]]:
        """
        批量提取图像特征
        
        Args:
            images: (图像, 帧索引)元组列表
            progress_callback: 进度回调
        
        Returns:
            ImageFeatureData列表
        """
        self._cancel_flag = False
        results = []
        total = len(images)
        
        for i, (image, frame_index) in enumerate(images):
            if self._cancel_flag:
                break
            
            feature_data = self.extract_image_features(image, frame_index)
            results.append(feature_data)
            
            if progress_callback:
                progress = (i + 1) / total * 100
                progress_callback(i + 1, total, progress)
        
        return results
    
    def compare_image_features(self, feat1: ImageFeatureData, feat2: ImageFeatureData) -> float:
        """
        对比两个图像特征的相似度
        
        Returns:
            相似度 0-1 (1为完全相同)
        """
        if feat1 is None or feat2 is None:
            return 0.0
        return feat1.similarity_to(feat2)
    
    def extract_regional_features(
        self, 
        image: np.ndarray, 
        frame_index: int = 0,
        weights: Tuple[float, float, float] = None
    ) -> Optional[RegionalFeatureData]:
        """
        提取分区域特征（上/中/下三个区域的灰度图）
        适合动漫角色的精确动作检测，特别是脚部动作
        
        Args:
            image: RGB或RGBA图像
            frame_index: 帧索引
            weights: 区域权重 (上, 中, 下)，默认(0.2, 0.3, 0.5)重点关注下半身
        
        Returns:
            RegionalFeatureData对象或None
        """
        if image is None:
            return None
        
        h, w = image.shape[:2]
        
        # 转为灰度图
        if len(image.shape) == 3:
            if image.shape[2] == 4:
                # RGBA: 使用alpha通道作为掩码，只对前景区域计算
                gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2GRAY)
                alpha = image[:, :, 3]
                # 将背景区域设置为固定值，避免干扰
                gray = np.where(alpha > 10, gray, 128).astype(np.uint8)
            else:
                gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            gray = image
        
        # 分割为三个区域 (上33%, 中34%, 下33%)
        h1 = h // 3
        h2 = h1 * 2
        
        upper_gray = gray[:h1, :]
        middle_gray = gray[h1:h2, :]
        lower_gray = gray[h2:, :]
        
        # 统一尺寸以便后续比较
        target_size = (128, 64)  # 宽 x 高
        upper_gray = cv2.resize(upper_gray, target_size, interpolation=cv2.INTER_AREA)
        middle_gray = cv2.resize(middle_gray, target_size, interpolation=cv2.INTER_AREA)
        lower_gray = cv2.resize(lower_gray, target_size, interpolation=cv2.INTER_AREA)
        
        return RegionalFeatureData(
            frame_index=frame_index,
            upper_gray=upper_gray,
            middle_gray=middle_gray,
            lower_gray=lower_gray,
            weights=weights
        )
    
    def batch_extract_regional_features(
        self,
        images: List[Tuple[np.ndarray, int]],
        weights: Tuple[float, float, float] = None,
        progress_callback: Optional[Callable[[int, int, float], None]] = None
    ) -> List[Optional[RegionalFeatureData]]:
        """
        批量提取分区域特征
        
        Args:
            images: (图像, 帧索引)元组列表
            weights: 区域权重
            progress_callback: 进度回调
        
        Returns:
            RegionalFeatureData列表
        """
        self._cancel_flag = False
        results = []
        total = len(images)
        
        for i, (image, frame_index) in enumerate(images):
            if self._cancel_flag:
                break
            
            feature_data = self.extract_regional_features(image, frame_index, weights)
            results.append(feature_data)
            
            if progress_callback:
                progress = (i + 1) / total * 100
                progress_callback(i + 1, total, progress)
        
        return results
    
    def compare_regional_features(self, feat1: RegionalFeatureData, feat2: RegionalFeatureData) -> float:
        """
        对比两个分区域特征的相似度
        
        Returns:
            相似度 0-1 (1为完全相同)
        """
        if feat1 is None or feat2 is None:
            return 0.0
        return feat1.similarity_to(feat2)
    
    def release(self):
        """释放资源"""
        if self._pose is not None:
            self._pose.close()
            self._pose = None
