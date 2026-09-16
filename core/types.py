"""
NaviVision Studio (OpenDevelop) - Core Data Types
仿照 HALCON 视觉对象哲学:
- Image: 多通道或单通道图像数据矩阵 (NumPy uint8 / float32)
- Region: 区域/掩膜对象 (基于二值图与连通标签，支持游程与独立连通域)
- XLD: 亚像素轮廓对象 (连续坐标多边形与亚像素线段)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


@dataclass
class RegionObject:
    """单个连通域或合并区域特征"""
    id: int
    area: int
    centroid: Tuple[float, float]  # (y, x) 即 (row, col)
    bbox: Tuple[int, int, int, int]  # (min_row, min_col, max_row, max_col)
    circularity: float  # 圆度: 4 * pi * area / (perimeter ** 2)
    aspect_ratio: float  # 长宽比
    contours: List[List[Tuple[float, float]]] = field(default_factory=list)


@dataclass
class Region:
    """
    Region 区域对象:
    存储二值掩膜，并维护连通域打散后的子对象列表
    """
    mask: np.ndarray  # uint8: 0 or 255
    objects: List[RegionObject] = field(default_factory=list)
    is_connected: bool = False  # 是否已执行 connection 打散

    @property
    def count(self) -> int:
        return len(self.objects) if self.is_connected else (1 if np.any(self.mask) else 0)


@dataclass
class XLDContour:
    """亚像素边缘轮廓 (Extended Line Description)"""
    id: int
    points: List[Tuple[float, float]]  # [(row, col), ...] 亚像素浮点坐标
    is_closed: bool = False
    length: float = 0.0


@dataclass
class StepResult:
    """单个算子执行后的输出快照"""
    step_id: str
    operator: str
    duration_ms: float
    output_type: str  # 'image' | 'region' | 'xld' | 'tuple'
    preview_base64: Optional[str] = None
    mask_base64: Optional[str] = None
    histogram: Optional[List[int]] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    contours: Optional[List[List[Tuple[float, float]]]] = None
