"""蚂蚁线动画效果 - 选区边界可视化"""
from typing import List, Tuple, Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush
import numpy as np


class MarchingAntsWidget(QWidget):
    """蚂蚁线动画控件 - 显示选区边界的流动虚线"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._boundary_points: List[Tuple[int, int]] = []
        self._boundary_paths: List[QPainterPath] = []
        self._mask: Optional[np.ndarray] = None
        
        self._ant_offset = 0
        self._ant_speed = 2
        self._ant_length = 8
        self._ant_gap = 8
        
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._animate)
        
        self._color1 = QColor(255, 255, 255)
        self._color2 = QColor(0, 0, 0)
        
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
    
    def set_boundary(self, boundary_points: List[Tuple[int, int]]):
        """设置边界点"""
        self._boundary_points = boundary_points
        self._build_paths()
        self.update()
    
    def set_mask(self, mask: np.ndarray):
        """设置选区遮罩并自动提取边界"""
        self._mask = mask
        self._boundary_points = self._extract_boundary(mask)
        self._build_paths()
        self.update()
    
    def _extract_boundary(self, mask: np.ndarray) -> List[Tuple[int, int]]:
        """从遮罩中提取边界点"""
        if mask is None:
            return []
        
        h, w = mask.shape
        boundary = []
        
        for y in range(h):
            for x in range(w):
                if mask[y, x] > 0:
                    is_boundary = False
                    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        ny, nx = y + dy, x + dx
                        if ny < 0 or ny >= h or nx < 0 or nx >= w:
                            is_boundary = True
                            break
                        if mask[ny, nx] == 0:
                            is_boundary = True
                            break
                    if is_boundary:
                        boundary.append((x, y))
        
        return boundary
    
    def _build_paths(self):
        """构建边界路径"""
        self._boundary_paths.clear()
        
        if not self._boundary_points:
            return
        
        points_set = set(self._boundary_points)
        visited = set()
        
        for start_point in self._boundary_points:
            if start_point in visited:
                continue
            
            path = QPainterPath()
            path.moveTo(start_point[0] + 0.5, start_point[1] + 0.5)
            visited.add(start_point)
            
            current = start_point
            while True:
                found_next = False
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                    next_point = (current[0] + dx, current[1] + dy)
                    if next_point in points_set and next_point not in visited:
                        path.lineTo(next_point[0] + 0.5, next_point[1] + 0.5)
                        visited.add(next_point)
                        current = next_point
                        found_next = True
                        break
                
                if not found_next:
                    break
            
            if path.elementCount() > 1:
                self._boundary_paths.append(path)
    
    def start_animation(self):
        """开始动画"""
        if not self._animation_timer.isActive():
            self._animation_timer.start(50)
    
    def stop_animation(self):
        """停止动画"""
        self._animation_timer.stop()
    
    def _animate(self):
        """动画帧更新"""
        self._ant_offset = (self._ant_offset + self._ant_speed) % (self._ant_length + self._ant_gap)
        self.update()
    
    def paintEvent(self, event):
        """绘制蚂蚁线"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        
        for path in self._boundary_paths:
            pen1 = QPen(self._color1, 1, Qt.DashLine)
            pen1.setDashPattern([self._ant_length, self._ant_gap])
            pen1.setDashOffset(self._ant_offset)
            painter.setPen(pen1)
            painter.drawPath(path)
            
            pen2 = QPen(self._color2, 1, Qt.DashLine)
            pen2.setDashPattern([self._ant_length, self._ant_gap])
            pen2.setDashOffset(self._ant_offset + self._ant_length)
            painter.setPen(pen2)
            painter.drawPath(path)
    
    def clear(self):
        """清除边界"""
        self._boundary_points.clear()
        self._boundary_paths.clear()
        self._mask = None
        self.update()


class SelectionOverlay(QWidget):
    """选区叠加层 - 显示选区和蚂蚁线"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._mask: Optional[np.ndarray] = None
        self._zoom = 1.0
        self._offset_x = 0
        self._offset_y = 0
        
        self._ant_offset = 0
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._animate)
        
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
    
    def set_selection(self, mask: Optional[np.ndarray], zoom: float = 1.0, offset: Tuple[int, int] = (0, 0)):
        """设置选区"""
        self._mask = mask
        self._zoom = zoom
        self._offset_x, self._offset_y = offset
        self.update()
    
    def set_transform(self, zoom: float, offset: Tuple[int, int]):
        """设置变换参数"""
        self._zoom = zoom
        self._offset_x, self._offset_y = offset
        self.update()
    
    def start_animation(self):
        """开始动画"""
        if not self._animation_timer.isActive():
            self._animation_timer.start(50)
    
    def stop_animation(self):
        """停止动画"""
        self._animation_timer.stop()
    
    def _animate(self):
        """动画帧更新"""
        self._ant_offset = (self._ant_offset + 2) % 16
        self.update()
    
    def paintEvent(self, event):
        """绘制选区边界"""
        if self._mask is None:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        
        h, w = self._mask.shape
        
        boundary = self._extract_boundary(self._mask)
        
        if not boundary:
            return
        
        pen1 = QPen(QColor(255, 255, 255), 1)
        pen2 = QPen(QColor(0, 0, 0), 1)
        
        dash_pattern = [4, 4]
        pen1.setDashPattern(dash_pattern)
        pen2.setDashPattern(dash_pattern)
        pen1.setDashOffset(self._ant_offset)
        pen2.setDashOffset(self._ant_offset + 4)
        
        for x, y in boundary:
            sx = int(x * self._zoom + self._offset_x)
            sy = int(y * self._zoom + self._offset_y)
            
            painter.setPen(pen1)
            painter.drawPoint(sx, sy)
            
            painter.setPen(pen2)
            painter.drawPoint(sx + 1, sy + 1)
    
    def _extract_boundary(self, mask: np.ndarray) -> List[Tuple[int, int]]:
        """提取边界点"""
        h, w = mask.shape
        boundary = []
        
        for y in range(h):
            for x in range(w):
                if mask[y, x] > 0:
                    is_boundary = False
                    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        ny, nx = y + dy, x + dx
                        if ny < 0 or ny >= h or nx < 0 or nx >= w:
                            is_boundary = True
                            break
                        if mask[ny, nx] == 0:
                            is_boundary = True
                            break
                    if is_boundary:
                        boundary.append((x, y))
        
        return boundary
    
    def clear(self):
        """清除选区"""
        self._mask = None
        self.update()


class MarchingAntsHelper:
    """蚂蚁线辅助类 - 用于在任意图像上绘制蚂蚁线"""
    
    @staticmethod
    def draw_marching_ants(
        painter: QPainter,
        mask: np.ndarray,
        zoom: float = 1.0,
        offset: Tuple[int, int] = (0, 0),
        ant_offset: int = 0
    ):
        """
        在指定画布上绘制蚂蚁线
        
        Args:
            painter: QPainter对象
            mask: 选区遮罩
            zoom: 缩放比例
            offset: 偏移量 (x, y)
            ant_offset: 蚂蚁线偏移（用于动画）
        """
        if mask is None:
            return
        
        h, w = mask.shape
        boundary = []
        
        for y in range(h):
            for x in range(w):
                if mask[y, x] > 0:
                    is_boundary = False
                    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        ny, nx = y + dy, x + dx
                        if ny < 0 or ny >= h or nx < 0 or nx >= w:
                            is_boundary = True
                            break
                        if mask[ny, nx] == 0:
                            is_boundary = True
                            break
                    if is_boundary:
                        boundary.append((x, y))
        
        if not boundary:
            return
        
        pen1 = QPen(QColor(255, 255, 255), 1)
        pen2 = QPen(QColor(0, 0, 0), 1)
        
        dash_pattern = [4, 4]
        pen1.setDashPattern(dash_pattern)
        pen2.setDashPattern(dash_pattern)
        pen1.setDashOffset(ant_offset)
        pen2.setDashOffset(ant_offset + 4)
        
        offset_x, offset_y = offset
        
        for x, y in boundary:
            sx = int(x * zoom + offset_x)
            sy = int(y * zoom + offset_y)
            
            painter.setPen(pen1)
            painter.drawPoint(sx, sy)
            
            painter.setPen(pen2)
            painter.drawPoint(sx + 1, sy + 1)
    
    @staticmethod
    def draw_selection_fill(
        painter: QPainter,
        mask: np.ndarray,
        zoom: float = 1.0,
        offset: Tuple[int, int] = (0, 0),
        color: QColor = QColor(0, 120, 215, 50)
    ):
        """
        绘制选区填充
        
        Args:
            painter: QPainter对象
            mask: 选区遮罩
            zoom: 缩放比例
            offset: 偏移量 (x, y)
            color: 填充颜色
        """
        if mask is None:
            return
        
        h, w = mask.shape
        offset_x, offset_y = offset
        
        painter.fillRect(
            int(offset_x),
            int(offset_y),
            int(w * zoom),
            int(h * zoom),
            color
        )
