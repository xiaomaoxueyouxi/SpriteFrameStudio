"""姿势数据模型"""
from typing import List, Optional, Tuple, ClassVar
from pydantic import BaseModel, Field
import math


class Landmark(BaseModel):
    """单个关键点"""
    x: float = Field(..., description="x坐标 (归一化 0-1)")
    y: float = Field(..., description="y坐标 (归一化 0-1)")
    z: float = Field(default=0.0, description="z坐标 (深度)")
    visibility: float = Field(default=1.0, description="可见度 0-1")
    
    def to_pixel(self, width: int, height: int) -> Tuple[int, int]:
        """转换为像素坐标"""
        return (int(self.x * width), int(self.y * height))
    
    def distance_to(self, other: "Landmark") -> float:
        """计算与另一个关键点的欧氏距离"""
        return math.sqrt(
            (self.x - other.x) ** 2 + 
            (self.y - other.y) ** 2 + 
            (self.z - other.z) ** 2
        )


# MediaPipe Pose 关键点索引常量
NOSE = 0
LEFT_EYE_INNER = 1
LEFT_EYE = 2
LEFT_EYE_OUTER = 3
RIGHT_EYE_INNER = 4
RIGHT_EYE = 5
RIGHT_EYE_OUTER = 6
LEFT_EAR = 7
RIGHT_EAR = 8
MOUTH_LEFT = 9
MOUTH_RIGHT = 10
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_PINKY = 17
RIGHT_PINKY = 18
LEFT_INDEX = 19
RIGHT_INDEX = 20
LEFT_THUMB = 21
RIGHT_THUMB = 22
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32

# 骨架连接定义
POSE_CONNECTIONS = [
    # 头部
    (NOSE, LEFT_EYE_INNER), (LEFT_EYE_INNER, LEFT_EYE), (LEFT_EYE, LEFT_EYE_OUTER),
    (NOSE, RIGHT_EYE_INNER), (RIGHT_EYE_INNER, RIGHT_EYE), (RIGHT_EYE, RIGHT_EYE_OUTER),
    (LEFT_EYE_OUTER, LEFT_EAR), (RIGHT_EYE_OUTER, RIGHT_EAR),
    (MOUTH_LEFT, MOUTH_RIGHT),
    # 躯干
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_HIP), (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    # 左臂
    (LEFT_SHOULDER, LEFT_ELBOW), (LEFT_ELBOW, LEFT_WRIST),
    (LEFT_WRIST, LEFT_PINKY), (LEFT_WRIST, LEFT_INDEX), (LEFT_WRIST, LEFT_THUMB),
    (LEFT_PINKY, LEFT_INDEX),
    # 右臂
    (RIGHT_SHOULDER, RIGHT_ELBOW), (RIGHT_ELBOW, RIGHT_WRIST),
    (RIGHT_WRIST, RIGHT_PINKY), (RIGHT_WRIST, RIGHT_INDEX), (RIGHT_WRIST, RIGHT_THUMB),
    (RIGHT_PINKY, RIGHT_INDEX),
    # 左腿
    (LEFT_HIP, LEFT_KNEE), (LEFT_KNEE, LEFT_ANKLE),
    (LEFT_ANKLE, LEFT_HEEL), (LEFT_ANKLE, LEFT_FOOT_INDEX), (LEFT_HEEL, LEFT_FOOT_INDEX),
    # 右腿
    (RIGHT_HIP, RIGHT_KNEE), (RIGHT_KNEE, RIGHT_ANKLE),
    (RIGHT_ANKLE, RIGHT_HEEL), (RIGHT_ANKLE, RIGHT_FOOT_INDEX), (RIGHT_HEEL, RIGHT_FOOT_INDEX),
]


class PoseData(BaseModel):
    """姿势数据模型 - MediaPipe Pose 33个关键点"""
    id: str = Field(..., description="姿势数据唯一ID")
    frame_index: int = Field(..., description="关联的帧序号")
    
    # 33个关键点
    landmarks: List[Landmark] = Field(default_factory=list, description="关键点列表")
    
    # 整体置信度
    confidence: float = Field(default=0.0, description="检测置信度")
    
    # 类变量引用模块级常量
    POSE_CONNECTIONS: ClassVar[List[Tuple[int, int]]] = POSE_CONNECTIONS
    
    def get_landmark(self, index: int) -> Optional[Landmark]:
        """获取指定索引的关键点"""
        if 0 <= index < len(self.landmarks):
            return self.landmarks[index]
        return None
    
    def _calc_angle(self, p1: Landmark, p2: Landmark, p3: Landmark) -> Optional[float]:
        """计算三个点形成的角度（p2为顶点），返回弧度"""
        if p1.visibility < 0.5 or p2.visibility < 0.5 or p3.visibility < 0.5:
            return None
        
        # 向量 p2->p1 和 p2->p3
        v1 = (p1.x - p2.x, p1.y - p2.y)
        v2 = (p3.x - p2.x, p3.y - p2.y)
        
        # 计算点积和模
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
        mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
        
        if mag1 < 1e-6 or mag2 < 1e-6:
            return None
        
        cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        return math.acos(cos_angle)
    
    def get_pose_angles(self) -> List[Tuple[str, Optional[float]]]:
        """获取关键骨骼角度列表（位置无关特征）"""
        angles = []
        
        # 定义需要计算角度的关节 (三个点索引, p2为顶点)
        joint_angles = [
            ("left_elbow", LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
            ("right_elbow", RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST),
            ("left_shoulder", LEFT_ELBOW, LEFT_SHOULDER, LEFT_HIP),
            ("right_shoulder", RIGHT_ELBOW, RIGHT_SHOULDER, RIGHT_HIP),
            ("left_hip", LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE),
            ("right_hip", RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE),
            ("left_knee", LEFT_HIP, LEFT_KNEE, LEFT_ANKLE),
            ("right_knee", RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE),
            # 躯干角度
            ("torso_left", RIGHT_SHOULDER, LEFT_SHOULDER, LEFT_HIP),
            ("torso_right", LEFT_SHOULDER, RIGHT_SHOULDER, RIGHT_HIP),
        ]
        
        for name, i1, i2, i3 in joint_angles:
            if i1 < len(self.landmarks) and i2 < len(self.landmarks) and i3 < len(self.landmarks):
                angle = self._calc_angle(self.landmarks[i1], self.landmarks[i2], self.landmarks[i3])
                angles.append((name, angle))
            else:
                angles.append((name, None))
        
        return angles
    
    def similarity_to(self, other: "PoseData") -> float:
        """计算与另一个姿势的相似度 (0-1, 1为完全相同)
        
        使用骨骼角度特征而非绝对坐标，这样姿势相似度与人物位置无关
        相似度映射更陡峭，让差异更明显
        """
        if len(self.landmarks) != len(other.landmarks) or len(self.landmarks) < 33:
            return 0.0
        
        angles1 = self.get_pose_angles()
        angles2 = other.get_pose_angles()
        
        total_diff = 0.0
        valid_count = 0
        
        for (name1, a1), (name2, a2) in zip(angles1, angles2):
            if a1 is not None and a2 is not None:
                # 角度差的绝对值（弧度）
                diff = abs(a1 - a2)
                total_diff += diff
                valid_count += 1
        
        if valid_count == 0:
            return 0.0
        
        # 平均角度差（弧度）
        avg_diff = total_diff / valid_count
        
        # 转换为度数，更直观
        avg_diff_deg = math.degrees(avg_diff)
        
        # 线性映射：0度差=100%相似，30度差=0%相似
        # 这样 5度差 ≈ 83%, 10度差 ≈ 67%, 15度差 ≈ 50%
        similarity = max(0.0, 1.0 - avg_diff_deg / 30.0)
        
        return similarity
    
    def to_vector(self) -> List[float]:
        """转换为特征向量（用于对比）"""
        vector = []
        for lm in self.landmarks:
            vector.extend([lm.x, lm.y, lm.z])
        return vector
