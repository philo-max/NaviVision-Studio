"""
NaviVision Studio (OpenDevelop) - Vision Operators Library
对应并平替 HALCON 经典核心算子:
- read_image, rgb1_to_gray
- threshold, auto_threshold_otsu
- connection (连通域打散, 支持 4/8 连通)
- select_shape (面积、圆度、长宽比、紧致度筛选)
- morphology (dilation, erosion, opening, closing)
- edges_subpix (Canny 整像素边缘 + 法向抛物线亚像素插值 XLD)
- measure_region (统计中心、外接矩形、拟合圆)
"""

import cv2
import numpy as np
import math
import os
from typing import List, Tuple, Dict, Any, Optional, Union
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

        # 矩形度 Rectangularity = Area / (bbox_w * bbox_h)
        rectangularity = float(area / max(1, w * h))
        rectangularity = min(1.0, max(0.0, rectangularity))

        # Hu 不变矩 (7 维): 基于图像矩, 取 log 尺度压缩数量级
        try:
            mm = cv2.moments(obj_mask, binaryImage=True)
            hu = cv2.HuMoments(mm).flatten()
            hu_moments = [float(-np.sign(v) * math.log10(abs(v) + 1e-30)) for v in hu]
        except Exception:
            hu_moments = []

        obj = RegionObject(
            id=i,
            area=area,
            centroid=(cy, cx),
            bbox=(y, x, y + h, x + w),
            circularity=circularity,
            aspect_ratio=aspect_ratio,
            contours=[contour_points] if contour_points else [],
            rectangularity=rectangularity,
            hu_moments=hu_moments,
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
    max_aspect: float = 100.0,
    min_rectangularity: float = 0.0,
    max_rectangularity: float = 1.0,
    hu_match: Optional[List[float]] = None,
    max_hu_distance: float = 1.0
) -> Region:
    """
    HALCON select_shape 算子:
    根据特征过滤连通域。新增判据:
    - rectangularity (矩形度): area / bbox 面积, 用于区分矩形/非矩形目标
    - Hu 不变矩: 若给定 hu_match (7 维参考向量), 按欧氏距离阈值选择性保留
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
        if not (min_rectangularity <= obj.rectangularity <= max_rectangularity):
            continue
        if hu_match is not None and len(hu_match) == 7:
            if len(obj.hu_moments) != 7:
                continue
            dist = float(np.linalg.norm(np.asarray(obj.hu_moments) - np.asarray(hu_match, dtype=float)))
            if dist > float(max_hu_distance):
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
    edges_subpix 平替 (整像素边缘 + 法向亚像素修正):
    先用 Canny 提取整像素边缘轮廓, 再沿边缘法向对梯度幅值做三点抛物线插值,
    得到浮点坐标的亚像素轮廓 XLD。
    说明: 与 HALCON 基于 Steger-Hessian 脊线检测的真亚像素边缘不同,
    本实现是对整像素边缘的法向插值修正, 精度受整像素边缘质量限制,
    并非其文档早期所称的'工业级真·亚像素'。
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



# ============================================================================
# P0-2 色彩空间扩展: rgb_to_hsv / hsv_threshold (彩色目标 HSV 范围筛选)
# ============================================================================
def rgb_to_hsv(img: np.ndarray) -> np.ndarray:
    """
    HALCON trans_from_rgb 平替: BGR/RGB -> HSV 色彩空间转换。
    返回 H(0-179) / S(0-255) / V(0-255) 三通道 uint8 图像。
    """
    if img is None:
        raise ValueError("色彩空间转换输入图像为空")
    if img.ndim == 2:
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    else:
        bgr = img
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)


def hsv_threshold(
    hsv_img: np.ndarray,
    h_min: int = 0, h_max: int = 179,
    s_min: int = 0, s_max: int = 255,
    v_min: int = 0, v_max: int = 255
) -> Region:
    """
    HALCON 彩色阈值分割平替: 在 HSV 空间按色相/饱和度/明度范围筛选目标。
    适合彩色目标识别 (如药丸颜色分类 / 彩色缺陷分割)。
    """
    if hsv_img is None:
        raise ValueError("HSV 阈值输入图像为空")
    if hsv_img.ndim != 3 or hsv_img.shape[2] != 3:
        raise ValueError("hsv_threshold 需要三通道 HSV 图像, 请先执行 rgb_to_hsv")

    lower = np.array([int(h_min), int(s_min), int(v_min)], dtype=np.uint8)
    upper = np.array([int(h_max), int(s_max), int(v_max)], dtype=np.uint8)
    mask = cv2.inRange(hsv_img, lower, upper)
    return Region(mask=mask, is_connected=False)


# ============================================================================
# P1-4 模板匹配: find_shape_model (多尺度 / 多角度金字塔搜索)
# ============================================================================
# P1-4 模板匹配: find_shape_model
# 基于归一化互相关 (NCC) 的多目标 / 多尺度 / 多角度灰度模板匹配。
#   定位策略: 图像金字塔由粗到精搜索加速 + 相关峰曲面二次插值亚像素定位。
#   能力边界 (避免夸大): 本实现工作在灰度 NCC 层面, 并非 HALCON 基于形状
#   (边缘方向) 的匹配, 不具备 HALCON 的全角度测量、跨尺度不变特征与
#   亚像素边缘一致性评分的全部能力; 对光照/对比度变化有一定鲁棒性。
# ============================================================================
def _rotate_bound_template(tmpl: np.ndarray, angle: float) -> np.ndarray:
    """旋转模板并裁剪回非零最小外接矩形 (border=0 填充)。"""
    h, w = tmpl.shape[:2]
    diag = int(math.ceil(math.sqrt(h * h + w * w)))
    canvas = np.zeros((diag, diag), dtype=tmpl.dtype)
    oy, ox = (diag - h) // 2, (diag - w) // 2
    canvas[oy:oy + h, ox:ox + w] = tmpl
    m = cv2.getRotationMatrix2D((diag / 2.0, diag / 2.0), float(angle), 1.0)
    rotated = cv2.warpAffine(canvas, m, (diag, diag), flags=cv2.INTER_LINEAR, borderValue=0)
    ys, xs = np.where(np.abs(rotated.astype(np.int32)) > 0)
    if len(xs) == 0:
        return rotated
    return rotated[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _build_pyramid(img: np.ndarray, max_levels: int, min_side: int) -> List[np.ndarray]:
    """构建高斯图像金字塔 (pyrDown), 直到最小边小于 min_side 或达到层数。"""
    pyr = [img]
    for _ in range(max(0, int(max_levels) - 1)):
        if min(pyr[-1].shape[:2]) <= int(min_side):
            break
        pyr.append(cv2.pyrDown(pyr[-1]))
    return pyr


def _extract_peaks(corr: np.ndarray, threshold: float, max_peaks: int,
                   min_dist: float) -> List[Tuple[int, int, float]]:
    """从相关度响应图中提取多个非极大值抑制峰值。返回 [(x, y, score)]。"""
    peaks: List[Tuple[int, int, float]] = []
    work = np.array(corr, dtype=np.float32, copy=True)
    md = max(1, int(round(min_dist)))
    for _ in range(max(1, int(max_peaks))):
        _, max_val, _, max_loc = cv2.minMaxLoc(work)
        if max_val < float(threshold):
            break
        x, y = int(max_loc[0]), int(max_loc[1])
        peaks.append((x, y, float(max_val)))
        x0, y0 = max(0, x - md), max(0, y - md)
        x1, y1 = min(work.shape[1], x + md + 1), min(work.shape[0], y + md + 1)
        work[y0:y1, x0:x1] = -1.0
    return peaks


def _subpixel_peak(corr: np.ndarray, x: int, y: int) -> Tuple[float, float]:
    """对相关峰做 3x3 二次曲面拟合, 返回亚像素偏移 (dx, dy)。"""
    h, w = corr.shape
    if x <= 0 or y <= 0 or x >= w - 1 or y >= h - 1:
        return 0.0, 0.0
    c = corr[y - 1:y + 2, x - 1:x + 2].astype(np.float64)
    denom_x = 2.0 * (c[1, 0] - 2.0 * c[1, 1] + c[1, 2])
    denom_y = 2.0 * (c[0, 1] - 2.0 * c[1, 1] + c[2, 1])
    dx = (c[1, 0] - c[1, 2]) / denom_x if abs(denom_x) > 1e-9 else 0.0
    dy = (c[0, 1] - c[2, 1]) / denom_y if abs(denom_y) > 1e-9 else 0.0
    return float(max(-0.5, min(0.5, dx))), float(max(-0.5, min(0.5, dy)))


def _match_one_variant(v_img: np.ndarray, rot: np.ndarray, min_score: float,
                       max_matches: int, nms_distance: float,
                       subpixel: bool, pyramid_levels: int) -> List[Tuple[int, int, float, float, float]]:
    """对单个 (尺度, 角度) 变体做由粗到精的多目标匹配。

    返回 [(top_left_x, top_left_y, score, dx, dy)] (dx/dy 为亚像素修正)。
    """
    if rot.shape[0] >= v_img.shape[0] or rot.shape[1] >= v_img.shape[1]:
        return []
    corr_full = cv2.matchTemplate(v_img, rot, cv2.TM_CCOEFF_NORMED)

    pyr = _build_pyramid(v_img, pyramid_levels, 32)
    L = len(pyr) - 1
    cands: List[Tuple[int, int]] = []
    if L >= 1:
        factor = 2 ** L
        it = pyr[L]
        t = cv2.resize(rot, (max(8, int(round(rot.shape[1] / factor))),
                             max(8, int(round(rot.shape[0] / factor)))),
                       interpolation=cv2.INTER_AREA)
        if t.shape[0] < it.shape[0] and t.shape[1] < it.shape[1]:
            corr_c = cv2.matchTemplate(it, t, cv2.TM_CCOEFF_NORMED)
            coarse_peaks = _extract_peaks(corr_c, float(min_score) * 0.5,
                                          max(max_matches * 6, 12),
                                          max(1, int(round(nms_distance / factor))))
            cands = [(int(round(x * factor)), int(round(y * factor))) for (x, y, _) in coarse_peaks]

    results: List[Tuple[int, int, float, float, float]] = []
    if cands:
        half = 2 ** (L + 1) + 4
        for (cx, cy) in cands:
            x0 = max(0, cx - half); y0 = max(0, cy - half)
            x1 = min(corr_full.shape[1], cx + rot.shape[1] + half)
            y1 = min(corr_full.shape[0], cy + rot.shape[0] + half)
            if x1 - x0 < 1 or y1 - y0 < 1:
                continue
            sub = corr_full[y0:y1, x0:x1]
            for (sx, sy, sv) in _extract_peaks(sub, float(min_score), 4, 1):
                gx, gy = x0 + sx, y0 + sy
                dx, dy = _subpixel_peak(corr_full, gx, gy) if subpixel else (0.0, 0.0)
                results.append((gx, gy, sv, dx, dy))

    if not results:
        # 兜底: 直接在整幅相关图上做多峰提取 (保证不漏检)
        for (gx, gy, sv) in _extract_peaks(corr_full, float(min_score), max_matches, nms_distance):
            dx, dy = _subpixel_peak(corr_full, gx, gy) if subpixel else (0.0, 0.0)
            results.append((gx, gy, sv, dx, dy))

    # 同一变体内去重 (距离过近)
    results.sort(key=lambda r: -r[2])
    dedup: List[Tuple[int, int, float, float, float]] = []
    for r in results:
        if all((r[0] - d[0]) ** 2 + (r[1] - d[1]) ** 2 > float(nms_distance) ** 2 for d in dedup):
            dedup.append(r)
    return dedup


def find_shape_model(
    image: np.ndarray,
    template: np.ndarray,
    min_score: float = 0.5,
    scales: Optional[List[float]] = None,
    angles: Optional[List[float]] = None,
    max_matches: int = 10,
    nms_distance: float = 10.0,
    pyramid_levels: int = 3,
    subpixel: bool = True,
    polarity_invariant: bool = False,
    angle_step: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    多目标 / 多尺度 / 多角度灰度模板匹配。

    与早期单峰实现的关键差异:
      1. 单张图内可返回多个目标: 对每个 (尺度, 角度) 变体提取多个相关峰,
         再做跨尺度/角度统一非极大值抑制, 而非只取全局最高峰。
      2. 由粗到精的图像金字塔加速 (pyrDown 候选 + 全分辨率局部精化)。
      3. 相关峰二次曲面插值, 给出亚像素级中心位置 (subpixel=True)。
      4. 极性无关匹配 (polarity_invariant=True): 同时匹配亮目标与暗目标。
      5. angles 缺省时按 angle_step 自动覆盖 0~360°, 不再默认只搜 0°。

    参数:
      pyramid_levels: 金字塔层数 (>=1)。
      subpixel: 是否启用相关峰亚像素插值。
      polarity_invariant: 是否兼容黑白极性反转。
      angle_step: angles 未显式给出时, 自动角度序列的步长 (度)。
    """
    if image is None or template is None:
        raise ValueError("模板匹配输入为空")

    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    tmpl0 = template if template.ndim == 2 else cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    img = np.ascontiguousarray(img, dtype=np.uint8)
    tmpl0 = np.ascontiguousarray(tmpl0, dtype=np.uint8)

    scale_list = [float(s) for s in scales] if scales else [1.0]
    if angles:
        angle_list = [float(a) for a in angles]
    else:
        step = float(angle_step) if angle_step and float(angle_step) > 0 else 10.0
        angle_list = [float(a) for a in np.arange(0.0, 360.0, step)]

    variants = [("normal", img, tmpl0)]
    if polarity_invariant:
        # 极性无关: 保持原图不变, 额外使用反相模板以命中"暗目标/亮背景"的情形
        variants.append(("inverted", img, cv2.bitwise_not(tmpl0)))

    raw_matches: List[Dict[str, Any]] = []
    for pol_name, v_img, v_tmpl in variants:
        for s in scale_list:
            tw = max(1, int(round(v_tmpl.shape[1] * s)))
            th = max(1, int(round(v_tmpl.shape[0] * s)))
            if tw >= v_img.shape[1] or th >= v_img.shape[0]:
                continue
            base = cv2.resize(v_tmpl, (tw, th), interpolation=cv2.INTER_LINEAR)
            for a in angle_list:
                rot = _rotate_bound_template(base, a)
                if rot.shape[0] >= v_img.shape[0] or rot.shape[1] >= v_img.shape[1]:
                    continue
                found = _match_one_variant(v_img, rot, float(min_score),
                                           int(max_matches), float(nms_distance),
                                           bool(subpixel), int(pyramid_levels))
                for (gx, gy, sv, dx, dy) in found:
                    raw_matches.append({
                        "score": round(float(sv), 4),
                        "center": [round(float(gx) + dx + rot.shape[1] / 2.0, 3),
                                   round(float(gy) + dy + rot.shape[0] / 2.0, 3)],
                        "angle": float(a),
                        "scale": float(s),
                        "polarity": pol_name,
                        "template_size": [int(rot.shape[1]), int(rot.shape[0])],
                        "top_left": [int(gx), int(gy)],
                        "top_left_subpixel": [round(float(gx) + dx, 3), round(float(gy) + dy, 3)],
                    })

    # 跨尺度 / 跨角度 / 跨极性统一 NMS
    raw_matches.sort(key=lambda m: -m["score"])
    kept: List[Dict[str, Any]] = []
    for m in raw_matches:
        if all((m["center"][0] - k["center"][0]) ** 2 + (m["center"][1] - k["center"][1]) ** 2
               > float(nms_distance) ** 2 for k in kept):
            kept.append(m)
        if len(kept) >= int(max_matches):
            break
    return kept

def gen_contour_polygon(region_or_contour: Any, epsilon: float = 2.0) -> List[Dict[str, Any]]:
    """
    HALCON gen_polygons_xld / approx_chain 平替: 对轮廓做多边形近似, 输出顶点
    (拐点) 序列, 用于形状简化与拐点提取。
    """
    if isinstance(region_or_contour, Region):
        contours, _ = cv2.findContours(region_or_contour.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    else:
        arr = np.asarray(region_or_contour, dtype=np.int32)
        contours = [arr.reshape(-1, 1, 2)]

    polygons: List[Dict[str, Any]] = []
    for idx, cnt in enumerate(contours):
        if cnt is None or len(cnt) < 3:
            continue
        approx = cv2.approxPolyDP(cnt, float(epsilon), True)
        pts = [[int(p[0][0]), int(p[0][1])] for p in approx]
        polygons.append({
            "contour_id": idx,
            "corner_count": len(pts),
            "is_closed": True,
            "corner_points": pts
        })
    return polygons


# ============================================================================
# P2-7 条码 / 二维码识别: read_barcode (OpenCV 内置 + 可选 pyzbar)
# ============================================================================
def read_barcode(img: np.ndarray) -> List[Dict[str, Any]]:
    """
    HALCON find_bar_code / find_data_code_2d 平替:
    - 使用 OpenCV 内置 QRCodeDetector 识别 QR 码 (无额外依赖)
    - 若安装了 pyzbar, 额外支持一维条码 / Data Matrix 等
    """
    if img is None:
        raise ValueError("条码识别输入为空")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

    results: List[Dict[str, Any]] = []

    try:
        qr = cv2.QRCodeDetector()
        data, points, _ = qr.detectAndDecode(gray)
        if data:
            pts = points.reshape(-1, 2).tolist() if points is not None else []
            results.append({"type": "QRCODE", "data": data,
                            "points": [[round(float(x), 2), round(float(y), 2)] for x, y in pts]})
    except Exception:
        pass

    try:
        from pyzbar import pyzbar  # type: ignore
        for sym in pyzbar.decode(gray):
            try:
                payload = sym.data.decode("utf-8")
            except Exception:
                payload = sym.data.decode("latin-1", errors="replace")
            results.append({
                "type": str(sym.type),
                "data": payload,
                "points": [[int(p.x), int(p.y)] for p in sym.polygon]
            })
    except Exception:
        pass

    return results


# ============================================================================
# P2-8 相机标定: 棋盘格像素->物理尺寸换算
# ============================================================================
def estimate_scale_from_checkerboard(
    img: np.ndarray,
    pattern_cols: int = 9,
    pattern_rows: int = 6,
    square_size: float = 1.0
) -> Dict[str, Any]:
    """
    棋盘格比例标定: 通过棋盘格角点估计单一 像素/物理单位 换算系数。
    说明: 仅输出一个平面比例系数, 不求解相机内参、畸变系数与透视校正,
    不能替代 HALCON 完整标定 (calibrate_cameras) 的测量级标定能力。
    返回 {found, pixels_per_unit, avg_square_pixels, corners}。
    """
    if img is None:
        raise ValueError("标定输入图像为空")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    pattern = (int(pattern_cols), int(pattern_rows))
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE

    found, corners = cv2.findChessboardCorners(gray, pattern, flags)
    if not found or corners is None:
        return {"found": False, "pixels_per_unit": None}

    corners = cv2.cornerSubPix(
        gray, corners, (5, 5), (-1, -1),
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    )
    pts = corners.reshape(-1, 2)
    cols = pattern[0]
    dists: List[float] = []
    for r in range(pattern[1]):
        row_pts = pts[r * cols:(r + 1) * cols]
        for c in range(cols - 1):
            dists.append(float(np.linalg.norm(row_pts[c + 1] - row_pts[c])))
    if not dists:
        return {"found": False, "pixels_per_unit": None}

    avg_square_pixels = sum(dists) / len(dists)
    ppu = avg_square_pixels / float(square_size) if float(square_size) > 0 else avg_square_pixels
    return {
        "found": True,
        "pixels_per_unit": round(ppu, 4),
        "avg_square_pixels": round(avg_square_pixels, 3),
        "corners": [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in pts]
    }


# ============================================================================
# P2-9 OCR: read_text (可选依赖 pytesseract, 缺失时优雅降级)
# ============================================================================
def read_text(img: np.ndarray, lang: str = "eng") -> str:
    """
    HALCON read_ocr 平替: 调用 Tesseract OCR 识别图像文字。
    属可选能力, 未安装 pytesseract / 系统 Tesseract 时抛出明确异常。
    """
    try:
        import pytesseract  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "OCR 需要可选依赖 pytesseract (及系统 Tesseract OCR 引擎), 当前环境未安装, 已优雅降级。"
        ) from exc
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return str(pytesseract.image_to_string(gray, lang=lang)).strip()

# ============================================================================
# ROI 交互算子: 由几何形状生成区域 + 在区域内归约图像 (reduce_domain)
# 支持矩形 / 圆 / 多边形三种交互绘制的 ROI 形状, 与 HALCON reduce_domain 语义一致:
# 区域外像素被置为填充值, 但画布尺寸保持不变, 从而不破坏下游坐标体系。
# ============================================================================
def create_mask_from_geometry(shape: Tuple[int, int], geometry: Optional[Dict[str, Any]]) -> Region:
    """由几何描述生成 ROI 掩膜区域 (矩形 / 圆 / 多边形)。

    geometry 支持的形态:
      {"type": "rect",    "x": .., "y": .., "w": .., "h": ..}
      {"type": "circle",  "cx": .., "cy": .., "r": ..}
      {"type": "polygon", "points": [[x, y], [x, y], ...]}
    缺省或非法时返回整幅全通区域 (全 1)。
    """
    h, w = int(shape[0]), int(shape[1])
    mask = np.zeros((h, w), dtype=np.uint8)
    if not geometry or not isinstance(geometry, dict):
        mask[:] = 255
        return Region(mask=mask, is_connected=False)

    gtype = str(geometry.get("type", "rect")).lower()
    try:
        if gtype == "rect":
            x = int(geometry.get("x", 0)); y = int(geometry.get("y", 0))
            rw = int(geometry.get("w", w)); rh = int(geometry.get("h", h))
            x0 = max(0, min(w - 1, x)); y0 = max(0, min(h - 1, y))
            x1 = max(0, min(w, x + rw)); y1 = max(0, min(h, y + rh))
            mask[y0:y1, x0:x1] = 255
        elif gtype == "circle":
            cx = int(geometry.get("cx", w // 2)); cy = int(geometry.get("cy", h // 2))
            r = max(1, int(geometry.get("r", min(h, w) // 4)))
            cv2.circle(mask, (cx, cy), r, 255, -1)
        elif gtype == "polygon":
            pts = geometry.get("points") or []
            arr = np.asarray(pts, dtype=np.int32)
            if arr.ndim == 2 and arr.shape[0] >= 3:
                cv2.fillPoly(mask, [arr], 255)
            else:
                mask[:] = 255
        else:
            mask[:] = 255
    except Exception:
        mask[:] = 255
    return Region(mask=mask, is_connected=False)


def reduce_domain(img: np.ndarray, region: Region, fill_value: int = 0) -> np.ndarray:
    """ROI 归约: 保留 region 内像素, 区域外置为 fill_value (画布尺寸不变)。"""
    if img is None:
        raise ValueError("reduce_domain 输入图像为空")
    if region is None or region.mask is None:
        return img.copy()
    mask = region.mask
    if mask.shape[:2] != img.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    m = (mask > 0)
    out = img.copy()
    if img.ndim == 3:
        out[~m] = fill_value
    else:
        out[~m] = fill_value
    return out


# ============================================================================
# 一维卡尺测量: measure_pos
# 沿给定测量线 (x0,y0)->(x1,y1) 采样灰度剖面, 用一维导数 + 抛物线插值定位
# 亚像素边缘点。这是 HALCON 1D 卡尺测量的简化等价物, 用于尺寸/间距测量。
# ============================================================================
def measure_pos(
    img: np.ndarray,
    x0: float, y0: float, x1: float, y1: float,
    sigma: float = 1.0,
    threshold: float = 20.0,
    select: str = "all"
) -> List[Dict[str, Any]]:
    """沿测量线做 1D 卡尺测量, 返回亚像素边缘位置。

    参数:
      sigma: 剖面前的高斯平滑标准差。
      threshold: 一阶导数(边缘强度)阈值, 低于该值不判定为边缘。
      select: "all" | "first" | "last" 返回全部或首/末边缘。
    返回: [{"position": s(沿线的曲线距离), "x": .., "y": .., "amplitude": .., "index": ..}]
    """
    if img is None:
        raise ValueError("measure_pos 输入图像为空")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    gray = gray.astype(np.float32)

    dx = float(x1) - float(x0)
    dy = float(y1) - float(y0)
    length = math.hypot(dx, dy)
    if length < 1.0:
        return []
    n = max(2, int(math.ceil(length)))
    ts = np.linspace(0.0, 1.0, n)
    xs = float(x0) + ts * dx
    ys = float(y0) + ts * dy

    # 双线性采样剖面
    prof = np.array([_sample_bilinear(gray, px, py) for px, py in zip(xs, ys)], dtype=np.float32)
    if sigma and float(sigma) > 0:
        k = max(1, int(round(float(sigma) * 3)))
        prof = cv2.GaussianBlur(prof.reshape(1, -1), (1, 2 * k + 1), float(sigma)).reshape(-1)

    der = np.gradient(prof)
    abs_der = np.abs(der)
    step = length / float(n - 1)

    edges: List[Dict[str, Any]] = []
    for i in range(1, n - 1):
        if abs_der[i] < float(threshold):
            continue
        # 局部极大 (|导数| 峰)
        if abs_der[i] < abs_der[i - 1] or abs_der[i] < abs_der[i + 1]:
            continue
        denom = (abs_der[i - 1] - 2.0 * abs_der[i] + abs_der[i + 1])
        delta = (abs_der[i - 1] - abs_der[i + 1]) / (2.0 * denom) if abs(denom) > 1e-9 else 0.0
        delta = float(max(-0.5, min(0.5, delta)))
        idx = i + delta
        t = idx / float(n - 1)
        edges.append({
            "position": round(float(t) * length, 3),
            "x": round(float(x0) + t * dx, 3),
            "y": round(float(y0) + t * dy, 3),
            "amplitude": round(float(abs_der[i]), 3),
            "index": int(i),
        })

    sel = str(select or "all").lower()
    if sel == "first" and edges:
        return edges[:1]
    if sel == "last" and edges:
        return edges[-1:]
    return edges


# ============================================================================
# 图像合并: merge_images (多图 / 分支汇聚节点)
# ============================================================================
def merge_images(img_a: np.ndarray, img_b: np.ndarray, mode: str = "blend",
                 alpha: float = 0.5) -> np.ndarray:
    """把两路图像合并为一路 (用于流水线多图/分支汇聚)。

    mode: blend(加权) | add | max | min | absdiff | stack_h | stack_v
    """
    if img_a is None or img_b is None:
        raise ValueError("merge_images 需要两路输入图像")
    bb = img_b
    if bb.shape[:2] != img_a.shape[:2]:
        bb = cv2.resize(bb, (img_a.shape[1], img_a.shape[0]), interpolation=cv2.INTER_LINEAR)
    a = img_a.astype(np.float32)
    b = bb.astype(np.float32)
    m = str(mode or "blend").lower()
    if m == "add":
        out = np.clip(a + b, 0, 255)
    elif m == "max":
        out = np.maximum(a, b)
    elif m == "min":
        out = np.minimum(a, b)
    elif m == "absdiff":
        out = np.abs(a - b)
    elif m == "stack_h":
        out = np.hstack([a, b])
    elif m == "stack_v":
        out = np.vstack([a, b])
    else:  # blend
        al = float(max(0.0, min(1.0, alpha)))
        out = np.clip(a * al + b * (1.0 - al), 0, 255)
    return out.astype(np.uint8)


# ============================================================================
# P3-1 深度学习推理节点: onnx_inference (可选依赖 onnxruntime, 缺失时优雅降级)
# 支持分类 (classification) 与通用回归/嵌入输出的最小封装。
# ============================================================================
def onnx_inference(
    img: np.ndarray,
    model_path: str,
    input_size: Optional[List[int]] = None,
    mean: Optional[List[float]] = None,
    std: Optional[List[float]] = None,
    task: str = "classification",
    top_k: int = 5
) -> Dict[str, Any]:
    """通过 ONNX Runtime 运行一个已训练模型 (分类 / 通用)。

    设计为可选能力: 未安装 onnxruntime 或模型文件不存在时抛出明确异常,
    流水线捕获后可优雅降级为占位说明, 不会导致整条流水线崩溃。
    """
    try:
        import onnxruntime as ort  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "ONNX 推理需要可选依赖 onnxruntime, 当前环境未安装, 已优雅降级。"
        ) from exc
    if not model_path or not os.path.exists(model_path):
        raise ValueError(f"ONNX 模型文件不存在: {model_path}")
    if img is None:
        raise ValueError("onnx_inference 输入图像为空")

    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    in_name = inp.name
    shape = inp.shape  # e.g. [N, C, H, W] or [N, 3, H, W]
    # 推断输入尺寸
    h_in, w_in = None, None
    if input_size and len(input_size) == 2:
        h_in, w_in = int(input_size[0]), int(input_size[1])
    else:
        try:
            h_in = int(shape[2]) if isinstance(shape[2], int) else 224
            w_in = int(shape[3]) if isinstance(shape[3], int) else 224
        except Exception:
            h_in, w_in = 224, 224

    ch = 3
    try:
        c_dim = shape[1]
        if isinstance(c_dim, int) and c_dim > 0:
            ch = c_dim
    except Exception:
        ch = 3

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    resized = cv2.resize(rgb, (w_in, h_in), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    if mean is not None and len(mean) == 3:
        resized = resized - np.array(mean, dtype=np.float32).reshape(1, 1, 3)
    if std is not None and len(std) == 3:
        resized = resized / np.maximum(np.array(std, dtype=np.float32).reshape(1, 1, 3), 1e-6)
    else:
        resized = resized / 255.0
    if ch == 1:
        resized = cv2.cvtColor(resized.astype(np.uint8) if resized.max() > 2 else rgb,
                               cv2.COLOR_RGB2GRAY)[:, :, None].astype(np.float32)
    tensor = np.transpose(resized, (2, 0, 1))[None, ...].astype(np.float32)

    outputs = sess.run(None, {in_name: tensor})
    raw = np.asarray(outputs[0]).reshape(-1).astype(np.float64)

    result: Dict[str, Any] = {"task": task, "model": os.path.basename(model_path),
                              "output_dim": int(raw.size)}
    if str(task).lower() == "classification":
        # softmax
        e = np.exp(raw - np.max(raw))
        probs = e / np.sum(e)
        order = np.argsort(-probs)[:max(1, int(top_k))]
        result["predictions"] = [
            {"class_index": int(i), "score": round(float(probs[i]), 5)} for i in order
        ]
        result["top1"] = int(order[0])
        result["top1_score"] = round(float(probs[order[0]]), 5)
    else:
        result["values"] = [round(float(v), 5) for v in raw[:64]]
    return result


def gen_cross_contour_xld(
    rows: Union[List[float], float],
    cols: Union[List[float], float],
    length: float = 6.0,
    phi: float = 0.785398
) -> List[XLDContour]:
    """
    HALCON gen_cross_contour_xld 算子:
    在给定 (Row, Col) 中心点位置生成十字交叉 XLD 矢量轮廓
    """
    contours: List[XLDContour] = []
    if not isinstance(rows, (list, tuple, np.ndarray)):
        r_list = [rows]
    else:
        r_list = list(rows)
    if not isinstance(cols, (list, tuple, np.ndarray)):
        c_list = [cols]
    else:
        c_list = list(cols)

    cnt_id = 1
    for r, c in zip(r_list, c_list):
        r_val, c_val = float(r), float(c)
        dx1 = length * math.cos(phi)
        dy1 = length * math.sin(phi)
        dx2 = length * math.sin(phi)
        dy2 = -length * math.cos(phi)
        # points are in [col, row] for canvas viewport
        arm1 = [[round(c_val - dx1, 2), round(r_val - dy1, 2)], [round(c_val + dx1, 2), round(r_val + dy1, 2)]]
        arm2 = [[round(c_val - dx2, 2), round(r_val - dy2, 2)], [round(c_val + dx2, 2), round(r_val + dy2, 2)]]
        contours.append(XLDContour(id=cnt_id, points=arm1, is_closed=False))
        contours.append(XLDContour(id=cnt_id + 1, points=arm2, is_closed=False))
        cnt_id += 2
    return contours


def hom_vector_to_proj_hom_mat2d(
    px: List[float],
    py: List[float],
    qx: List[float],
    qy: List[float],
    pw: Optional[List[float]] = None,
    qw: Optional[List[float]] = None,
    method: str = "normalized_dlt"
) -> np.ndarray:
    """
    HALCON hom_vector_to_proj_hom_mat2d 算子:
    根据点对对应关系求解 2D 投影变换 (单应性) 矩阵 HomMat2D (3x3)。
    自动兼容 Row/Col 与 Col/Row 双向坐标表达。
    """
    px = [float(v) for v in px]
    py = [float(v) for v in py]
    qx = [float(v) for v in qx]
    qy = [float(v) for v in qy]

    # 判断第一参数是 Row 还是 Col:
    # 若点0和点1在 qy 相同而 qx 变化，说明 qy 是垂直线(Col), qx 是纵轴(Row)
    if len(qx) >= 4 and len(qy) >= 4:
        if abs(qy[0] - qy[1]) < 1e-4 and abs(qx[0] - qx[1]) > 1e-4:
            src_pts = np.float32([[py[i], px[i]] for i in range(4)])
            dst_pts = np.float32([[qy[i], qx[i]] for i in range(4)])
        else:
            src_pts = np.float32([[px[i], py[i]] for i in range(4)])
            dst_pts = np.float32([[qx[i], qy[i]] for i in range(4)])
    else:
        src_pts = np.float32(list(zip(px, py)))
        dst_pts = np.float32(list(zip(qx, qy)))

    H = cv2.getPerspectiveTransform(src_pts, dst_pts)
    return H


def projective_trans_image(
    img: np.ndarray,
    hom_mat: Union[np.ndarray, List[List[float]], Dict[str, Any]],
    interpolation: str = "bilinear",
    adapt_size: bool = False
) -> np.ndarray:
    """
    HALCON projective_trans_image 算子:
    应用投影变换矩阵对图像进行几何透视矫正
    """
    if isinstance(hom_mat, dict) and "matrix" in hom_mat:
        H = np.array(hom_mat["matrix"], dtype=np.float32)
    elif isinstance(hom_mat, (list, np.ndarray)):
        H = np.array(hom_mat, dtype=np.float32)
    else:
        raise ValueError(f"无效的投影变换矩阵: {hom_mat}")

    h, w = img.shape[:2]
    flags = cv2.INTER_LINEAR if "bilinear" in str(interpolation).lower() else cv2.INTER_NEAREST
    warped = cv2.warpPerspective(img, H, (w, h), flags=flags, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    return warped


def distance_pp(row1: float, col1: float, row2: float, col2: float) -> float:
    """HALCON distance_pp 算子: 计算两点之间的欧氏距离"""
    return round(math.hypot(row2 - row1, col2 - col1), 4)


def distance_pl(
    row: float, col: float,
    row_begin: float, col_begin: float,
    row_end: float, col_end: float
) -> float:
    """
    HALCON distance_pl 算子:
    计算点 (Row, Col) 到由两点确定的无限长直线的垂直距离
    """
    dr = row_end - row_begin
    dc = col_end - col_begin
    line_len = math.hypot(dr, dc)
    if line_len < 1e-9:
        return round(math.hypot(row - row_begin, col - col_begin), 4)
    cross = abs(dr * (col - col_begin) - dc * (row - row_begin))
    return round(cross / line_len, 4)


def angle_ll(
    row_a1: float, col_a1: float, row_a2: float, col_a2: float,
    row_b1: float, col_b1: float, row_b2: float, col_b2: float
) -> float:
    """
    HALCON angle_ll 算子:
    计算直线 A (两点确定) 旋转到直线 B (两点确定) 的夹角,
    弧度制, 范围 (-pi, pi]
    """
    angle_a = math.atan2(col_a2 - col_a1, row_a2 - row_a1)
    angle_b = math.atan2(col_b2 - col_b1, row_b2 - row_b1)
    diff = angle_b - angle_a
    while diff > math.pi:
        diff -= 2.0 * math.pi
    while diff <= -math.pi:
        diff += 2.0 * math.pi
    return round(diff, 6)


def fit_line_contour_xld(points: List[Tuple[float, float]]) -> Dict[str, Any]:
    """
    HALCON fit_line_contour_xld 算子 (简化版):
    对亚像素轮廓点集 [(Row, Col), ...] 做总体最小二乘 (正交回归) 直线拟合,
    返回拟合线段的起止端点, 以及法线式方程 Nr*Row + Nc*Col = Dist 的系数。
    说明: 使用 SVD 主方向分解, 未实现 HALCON 原生的 Tukey/Huber 迭代抗差算法。
    """
    pts = np.array(points, dtype=np.float64)
    if len(pts) < 2:
        raise ValueError("拟合直线至少需要 2 个轮廓点")

    mean = pts.mean(axis=0)
    centered = pts - mean
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    direction = vt[0]
    normal = vt[-1]
    normal = normal / (np.linalg.norm(normal) + 1e-12)
    dist = float(normal @ mean)

    proj = centered @ direction
    begin_pt = mean + proj.min() * direction
    end_pt = mean + proj.max() * direction

    return {
        "row_begin": round(float(begin_pt[0]), 3),
        "col_begin": round(float(begin_pt[1]), 3),
        "row_end": round(float(end_pt[0]), 3),
        "col_end": round(float(end_pt[1]), 3),
        "nr": round(float(normal[0]), 6),
        "nc": round(float(normal[1]), 6),
        "dist": round(dist, 4)
    }


def fit_circle_contour_xld(points: List[Tuple[float, float]]) -> Dict[str, Any]:
    """
    HALCON fit_circle_contour_xld 算子 (简化版):
    使用 Kåsa 代数最小二乘法, 对亚像素轮廓点集 [(Row, Col), ...] 拟合圆,
    返回圆心/半径, 以及各轮廓点相对圆心的起止角度范围与绕行方向。
    """
    pts = np.array(points, dtype=np.float64)
    if len(pts) < 3:
        raise ValueError("拟合圆至少需要 3 个轮廓点")

    r = pts[:, 0]
    c = pts[:, 1]
    design = np.column_stack([r, c, np.ones(len(pts))])
    rhs = r ** 2 + c ** 2
    sol, *_ = np.linalg.lstsq(design, rhs, rcond=None)
    a1, a2, a3 = sol
    center_r = a1 / 2.0
    center_c = a2 / 2.0
    radius = math.sqrt(max(a3 + center_r ** 2 + center_c ** 2, 0.0))

    angles = np.arctan2(c - center_c, r - center_r)

    cross_sum = 0.0
    for i in range(len(pts) - 1):
        v1 = pts[i] - [center_r, center_c]
        v2 = pts[i + 1] - [center_r, center_c]
        cross_sum += v1[0] * v2[1] - v1[1] * v2[0]
    point_order = "positive" if cross_sum >= 0 else "negative"

    return {
        "row": round(float(center_r), 3),
        "col": round(float(center_c), 3),
        "radius": round(float(radius), 3),
        "start_phi": round(float(angles.min()), 6),
        "end_phi": round(float(angles.max()), 6),
        "point_order": point_order
    }

