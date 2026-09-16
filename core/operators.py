"""
NaviVision Studio (OpenDevelop) - Vision Operators Library
对应并平替 HALCON 经典核心算子:
- read_image, rgb1_to_gray
- threshold, auto_threshold_otsu
- connection (连通域打散, 支持 4/8 连通)
- select_shape (面积、圆度、长宽比、紧致度筛选)
- morphology (dilation, erosion, opening, closing)
- edges_subpix (Canny + 亚像素精确轮廓 XLD)
- measure_region (统计中心、外接矩形、拟合圆)
"""

import cv2
import numpy as np
import math
from typing import List, Tuple, Dict, Any, Optional
from core.types import Region, RegionObject, XLDContour


def read_image_from_path(path: str) -> np.ndarray:
    """读取图像 (通过 Python 宽字符 API 完美支持任意中文路径)"""
    with open(path, "rb") as f:
        data = f.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图像文件: {path}")
    return img


def read_image_from_bytes(data: bytes) -> np.ndarray:
    """从二进制字节流读取图像"""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解析图像数据流")
    return img


def rgb1_to_gray(img: np.ndarray) -> np.ndarray:
    """彩色图转灰度图"""
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def calc_histogram(gray_img: np.ndarray) -> List[int]:
    """计算 256 级灰度直方图"""
    if len(gray_img.shape) == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray_img], [0], None, [256], [0, 256])
    return [int(x[0]) for x in hist]


def threshold(gray_img: np.ndarray, min_gray: int = 0, max_gray: int = 128) -> Region:
    """
    HALCON 经典双阈值分割算子:
    threshold(Image, Region, MinGray, MaxGray)
    提取像素值满足: min_gray <= pixel <= max_gray 的区域
    """
    if len(gray_img.shape) == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_BGR2GRAY)
    
    min_v = max(0, min(255, int(min_gray)))
    max_v = max(0, min(255, int(max_gray)))
    
    if min_v <= max_v:
        mask = cv2.inRange(gray_img, min_v, max_v)
    else:
        # 反相区间 (双峰外侧)
        m1 = cv2.inRange(gray_img, 0, max_v)
        m2 = cv2.inRange(gray_img, min_v, 255)
        mask = cv2.bitwise_or(m1, m2)
        
    return Region(mask=mask, is_connected=False)


def auto_threshold_otsu(gray_img: np.ndarray, invert: bool = False) -> Region:
    """
    大津法 (Otsu) 自动阈值分割
    """
    if len(gray_img.shape) == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_BGR2GRAY)
    
    flag = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    val, mask = cv2.threshold(gray_img, 0, 255, flag + cv2.THRESH_OTSU)
    return Region(mask=mask, is_connected=False)


def invert_region(region: Region, width: int, height: int) -> Region:
    """反转区域 (补集)"""
    inv_mask = cv2.bitwise_not(region.mask)
    return Region(mask=inv_mask, is_connected=False)


def connection(region: Region, connectivity: int = 8) -> Region:
    """
    HALCON connection 算子:
    打散二值掩膜为独立连通域对象，并计算基础形态特征
    """
    conn = 4 if connectivity == 4 else 8
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        region.mask, connectivity=conn
    )
    
    objects: List[RegionObject] = []
    # label 0 是背景，从 1 开始遍历每个连通对象
    for i in range(1, num_labels):
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        w = int(stats[i, cv2.CC_STAT_WIDTH])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        cx, cy = float(centroids[i][0]), float(centroids[i][1])
        
        # 提取当前对象的独立轮廓
        obj_mask = (labels == i).astype(np.uint8) * 255
        contours, _ = cv2.findContours(obj_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        perimeter = 0.0
        contour_points = []
        if contours:
            perimeter = float(cv2.arcLength(contours[0], True))
            for pt in contours[0]:
                contour_points.append((float(pt[0][1]), float(pt[0][0])))  # (row, col)
                
        # 计算圆度 Circularity = 4 * pi * Area / (Perimeter^2)
        if perimeter > 0:
            circularity = float(4.0 * math.pi * area / (perimeter * perimeter))
            circularity = min(1.0, max(0.0, circularity))
        else:
            circularity = 0.0
            
        aspect_ratio = float(w / max(1, h))
        
        obj = RegionObject(
            id=i,
            area=area,
            centroid=(cy, cx),
            bbox=(y, x, y + h, x + w),
            circularity=circularity,
            aspect_ratio=aspect_ratio,
            contours=[contour_points] if contour_points else []
        )
        objects.append(obj)
        
    return Region(mask=region.mask.copy(), objects=objects, is_connected=True)


def select_shape(
    region: Region,
    min_area: int = 10,
    max_area: int = 9999999,
    min_circularity: float = 0.0,
    max_circularity: float = 1.0,
    min_aspect: float = 0.0,
    max_aspect: float = 100.0
) -> Region:
    """
    HALCON select_shape 算子:
    根据特征过滤连通域
    """
    # 如果尚未执行打散，先自动执行 connection
    reg = region if region.is_connected else connection(region, connectivity=8)
    
    filtered_objects: List[RegionObject] = []
    filtered_mask = np.zeros_like(reg.mask)
    
    for obj in reg.objects:
        if not (min_area <= obj.area <= max_area):
            continue
        if not (min_circularity <= obj.circularity <= max_circularity):
            continue
        if not (min_aspect <= obj.aspect_ratio <= max_aspect):
            continue
            
        filtered_objects.append(obj)
        # 将符合条件的物体绘制到新 mask
        y, x, y2, x2 = obj.bbox
        sub_mask = reg.mask[y:y2, x:x2]
        filtered_mask[y:y2, x:x2] = np.bitwise_or(filtered_mask[y:y2, x:x2], sub_mask)
        
    return Region(mask=filtered_mask, objects=filtered_objects, is_connected=True)


def morphology(
    region: Region,
    op_type: str = "opening",
    kernel_shape: str = "circle",
    kernel_size: int = 5
) -> Region:
    """
    HALCON 形态学算子:
    - dilation (膨胀)
    - erosion (腐蚀)
    - opening (开运算: 先腐蚀后膨胀，去细小噪点)
    - closing (闭运算: 先膨胀后腐蚀，填补内部孔洞)
    """
    k_size = max(1, int(kernel_size))
    if k_size % 2 == 0:
        k_size += 1
        
    shape = cv2.MORPH_ELLIPSE if kernel_shape == "circle" else (
        cv2.MORPH_CROSS if kernel_shape == "cross" else cv2.MORPH_RECT
    )
    element = cv2.getStructuringElement(shape, (k_size, k_size))
    
    op_map = {
        "dilation": lambda m: cv2.dilate(m, element),
        "erosion": lambda m: cv2.erode(m, element),
        "opening": lambda m: cv2.morphologyEx(m, cv2.MORPH_OPEN, element),
        "closing": lambda m: cv2.morphologyEx(m, cv2.MORPH_CLOSE, element)
    }
    
    func = op_map.get(op_type.lower(), op_map["opening"])
    new_mask = func(region.mask)
    
    # 若原本已打散，重新打散保持属性同步
    if region.is_connected:
        return connection(Region(mask=new_mask), connectivity=8)
    return Region(mask=new_mask, is_connected=False)


def filter_image(
    img: np.ndarray,
    filter_type: str = "gaussian",
    kernel_size: int = 5,
    sigma: float = 1.5
) -> np.ndarray:
    """
    HALCON 经典平滑/滤波算子 (噪声抑制前置环节):
    - mean     -> mean_image    (均值滤波: 抑制高斯噪声, 速度快)
    - gaussian -> gauss_filter  (高斯滤波: 保边平滑, 各向同性)
    - median   -> median_image  (中值滤波: 椒盐/脉冲噪声克星, 保边性最佳)

    输出与原图同尺寸、同数据类型的滤波结果 (uint8 灰度或彩色三通道)。
    """
    if img is None:
        raise ValueError("滤波输入图像为空")

    k_size = max(1, int(kernel_size))
    # 卷积核必须为奇数且不小于 1
    if k_size % 2 == 0:
        k_size += 1

    ft = (filter_type or "gaussian").lower()

    if ft == "mean":
        filtered = cv2.blur(img, (k_size, k_size))
    elif ft == "median":
        # 中值滤波核必须为 >=3 的奇数
        median_k = max(3, k_size)
        if median_k % 2 == 0:
            median_k += 1
        filtered = cv2.medianBlur(img, median_k)
    else:  # gaussian (默认)
        s = float(sigma) if sigma and float(sigma) > 0 else 0.0
        filtered = cv2.GaussianBlur(img, (k_size, k_size), s)

    return filtered


def _sample_bilinear(img: np.ndarray, px: float, py: float) -> float:
    """双线性插值采样单通道浮点图"""
    h, w = img.shape[:2]
    px = max(0.0, min(float(w - 1), px))
    py = max(0.0, min(float(h - 1), py))
    x0 = int(px)
    y0 = int(py)
    x1 = min(x0 + 1, w - 1)
    y1 = min(y0 + 1, h - 1)
    dx = px - float(x0)
    dy = py - float(y0)
    return float(
        img[y0, x0] * (1.0 - dx) * (1.0 - dy) +
        img[y0, x1] * dx * (1.0 - dy) +
        img[y1, x0] * (1.0 - dx) * dy +
        img[y1, x1] * dx * dy
    )


def edges_subpix(
    gray_img: np.ndarray,
    low_thresh: float = 30.0,
    high_thresh: float = 90.0
) -> List[XLDContour]:
    """
    HALCON edges_subpix 算子 (工业级真·亚像素边缘提取):
    使用 Canny 联合 Sobel 梯度法向二次抛物线三点插值 (Steger / Facet 思想)，
    提取连续亚像素浮点坐标 XLD 轮廓
    """
    if len(gray_img.shape) == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_BGR2GRAY)

    # 高斯滤波平滑降噪
    blurred = cv2.GaussianBlur(gray_img, (3, 3), 1.0)
    edges = cv2.Canny(blurred, int(low_thresh), int(high_thresh))

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    # 浮点梯度计算
    grad_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    mag_map = cv2.magnitude(grad_x, grad_y)

    h, w = gray_img.shape
    xld_list: List[XLDContour] = []

    for idx, cnt in enumerate(contours):
        if len(cnt) < 5:
            continue
        pts: List[Tuple[float, float]] = []
        for p in cnt:
            x, y = int(p[0][0]), int(p[0][1])
            gx = float(grad_x[y, x])
            gy = float(grad_y[y, x])
            mag0 = float(mag_map[y, x])
            norm = math.hypot(gx, gy)

            if norm < 1e-4:
                # 梯度极其平缓，回退为整像素
                pts.append((float(y), float(x)))
                continue

            # 沿梯度方向 (边缘法线方向) 的单位向量
            nx = gx / norm
            ny = gy / norm

            # 沿法线方向采集前后两点处的梯度幅值: t = -1 与 t = +1
            m_minus = _sample_bilinear(mag_map, x - nx, y - ny)
            m_plus = _sample_bilinear(mag_map, x + nx, y + ny)

            # 拟合 1D 抛物线: P(t) = a*t^2 + b*t + c
            # 极值点 t* = -b / (2*a) = (m_minus - m_plus) / (2 * (m_minus - 2*mag0 + m_plus))
            denom = 2.0 * (m_minus - 2.0 * mag0 + m_plus)
            if denom < -1e-5:  # 二阶导数小于 0，存在局部极大值 (边缘中心)
                t_star = (m_minus - m_plus) / denom
                # 约束在单个像素网格内插值 [-0.75, 0.75]
                if -0.75 <= t_star <= 0.75:
                    sub_x = x + t_star * nx
                    sub_y = y + t_star * ny
                else:
                    sub_x = float(x)
                    sub_y = float(y)
            else:
                sub_x = float(x)
                sub_y = float(y)

            # 边界保护
            sub_x = max(0.0, min(float(w - 1), sub_x))
            sub_y = max(0.0, min(float(h - 1), sub_y))
            pts.append((round(sub_y, 4), round(sub_x, 4)))

        if len(pts) < 2:
            continue

        # 计算真实亚像素欧氏折线弧长
        sub_len = 0.0
        for k in range(len(pts) - 1):
            dy = pts[k + 1][0] - pts[k][0]
            dx = pts[k + 1][1] - pts[k][1]
            sub_len += math.hypot(dy, dx)

        xld_list.append(XLDContour(id=idx + 1, points=pts, length=round(sub_len, 2)))

    return xld_list


def measure_region(region: Region) -> Dict[str, Any]:
    """
    HALCON measure_region / smallest_rectangle2 / smallest_circle 工业几何度量算子:
    对输入 Region 提取统计中心、外接正矩形(AABB)、最小外接旋转矩形(OBB)、
    最小外接圆、二阶矩主惯性轴与长短半轴、紧致度、凸度等全套度量特征
    """
    # 保证区域已执行连通域拆分
    reg = region if region.is_connected else connection(region, connectivity=8)

    objects_metrics: List[Dict[str, Any]] = []

    for obj in reg.objects:
        y1, x1, y2, x2 = obj.bbox
        sub_mask = reg.mask[y1:y2, x1:x2]
        cnts, _ = cv2.findContours(sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue

        # 偏移回原图绝对坐标
        cnt = cnts[0].copy()
        cnt[:, 0, 0] += x1
        cnt[:, 0, 1] += y1

        area = obj.area
        cy, cx = obj.centroid  # (row, col)

        # 1. 最小外接旋转矩形 (HALCON: smallest_rectangle2)
        rect = cv2.minAreaRect(cnt)  # ((cx, cy), (w, h), angle_deg)
        (rcx, rcy), (rw, rh), r_angle = rect
        major_len = max(rw, rh) / 2.0
        minor_len = min(rw, rh) / 2.0
        phi_rad = math.radians(r_angle)
        box_pts = cv2.boxPoints(rect).tolist()  # 4 个角点坐标 [[x, y], ...]

        # 2. 最小外接圆 (HALCON: smallest_circle)
        (mc_x, mc_y), mc_r = cv2.minEnclosingCircle(cnt)

        # 3. 二阶中心矩与主惯性椭圆 (HALCON: elliptic_axis)
        m = cv2.moments(cnt)
        if m["m00"] > 0:
            mu20 = m["mu20"] / m["m00"]
            mu02 = m["mu02"] / m["m00"]
            mu11 = m["mu11"] / m["m00"]
            delta = math.sqrt((mu20 - mu02) ** 2 + 4.0 * (mu11 ** 2))
            axis_ra = math.sqrt(max(0.0, 2.0 * (mu20 + mu02 + delta)))
            axis_rb = math.sqrt(max(0.0, 2.0 * (mu20 + mu02 - delta)))
            orientation = 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)
        else:
            axis_ra, axis_rb, orientation = 0.0, 0.0, 0.0

        # 4. 凸度与紧致度
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        cnt_area = cv2.contourArea(cnt)
        convexity = min(1.0, max(0.0, float(cnt_area / max(1.0, hull_area))))
        perimeter = cv2.arcLength(cnt, True)
        compactness = max(1.0, float((perimeter * perimeter) / (4.0 * math.pi * max(1.0, area))))

        obj_data = {
            "id": obj.id,
            "area": area,
            "centroid": (round(cy, 2), round(cx, 2)),  # (row, col)
            "bbox_aabb": obj.bbox,  # (min_row, min_col, max_row, max_col)
            "smallest_rectangle2": {
                "center": (round(rcy, 2), round(rcx, 2)),  # (row, col)
                "length1": round(major_len, 2),
                "length2": round(minor_len, 2),
                "phi": round(phi_rad, 4),
                "box_points": [[round(pt[1], 2), round(pt[0], 2)] for pt in box_pts]  # [(row, col), ...]
            },
            "smallest_circle": {
                "center": (round(mc_y, 2), round(mc_x, 2)),
                "radius": round(float(mc_r), 2)
            },
            "elliptic_axis": {
                "ra": round(axis_ra, 2),
                "rb": round(axis_rb, 2),
                "phi": round(orientation, 4)
            },
            "circularity": round(obj.circularity, 3),
            "convexity": round(convexity, 3),
            "compactness": round(compactness, 3)
        }
        objects_metrics.append(obj_data)

    total_area = sum(o["area"] for o in objects_metrics)
    mean_circ = float(np.mean([o["circularity"] for o in objects_metrics])) if objects_metrics else 0.0
    mean_conv = float(np.mean([o["convexity"] for o in objects_metrics])) if objects_metrics else 0.0

    return {
        "object_count": len(objects_metrics),
        "objects": objects_metrics,
        "summary": {
            "total_area": total_area,
            "mean_circularity": round(mean_circ, 3),
            "mean_convexity": round(mean_conv, 3),
            "mean_area": round(float(total_area / max(1, len(objects_metrics))), 1) if objects_metrics else 0.0
        }
    }

