"""
字符识别分类器: HALCON read_ocr_class_mlp / do_ocr_multi_class_mlp 的平替。
训练样本在首次使用时由多种字体合成 (OpenCV Hershey 字体必有, 安装了 Pillow 时追加系统字体),
以 kNN 对归一化后的二值字形分类, 不依赖外部 OCR 引擎。
"""

import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

from core.operators import connection
from core.types import Region

CHARSET = "0123456789X"
GLYPH_W = 20
GLYPH_H = 28
KNN_K = 3
MIN_REGION_PIXELS = 4

_HERSHEY_FONTS = (
    cv2.FONT_HERSHEY_SIMPLEX,
    cv2.FONT_HERSHEY_DUPLEX,
    cv2.FONT_HERSHEY_TRIPLEX,
    cv2.FONT_HERSHEY_COMPLEX,
    cv2.FONT_HERSHEY_PLAIN,
)
_HERSHEY_THICKNESSES = (1, 2, 3)
_SYSTEM_FONT_FILES = ("arial.ttf", "arialbd.ttf", "cour.ttf", "courbd.ttf", "verdana.ttf", "tahoma.ttf")
_SYSTEM_FONT_DIRS = (r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts")
_PIL_FONT_SIZES = (24, 36, 48)

_classifier_cache: Optional["DigitClassifier"] = None


def _normalize_glyph(binary: np.ndarray) -> Optional[np.ndarray]:
    """裁到前景外接框, 等比缩放并居中到 GLYPH_W x GLYPH_H, 返回 float32 一维特征"""
    ys, xs = np.nonzero(binary)
    if len(ys) < MIN_REGION_PIXELS:
        return None
    crop = binary[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    scale = min((GLYPH_W - 2) / w, (GLYPH_H - 2) / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((GLYPH_H, GLYPH_W), dtype=np.uint8)
    y0 = (GLYPH_H - new_h) // 2
    x0 = (GLYPH_W - new_w) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return (canvas.astype(np.float32) / 255.0).reshape(-1)


def _binarize_rendered(gray: np.ndarray) -> np.ndarray:
    return (gray > 127).astype(np.uint8) * 255


def _render_hershey_samples() -> List[Tuple[str, np.ndarray]]:
    samples = []
    for ch in CHARSET:
        for font in _HERSHEY_FONTS:
            for thickness in _HERSHEY_THICKNESSES:
                canvas = np.zeros((80, 80), dtype=np.uint8)
                cv2.putText(canvas, ch, (10, 60), font, 1.6, 255, thickness, cv2.LINE_AA)
                feat = _normalize_glyph(_binarize_rendered(canvas))
                if feat is not None:
                    samples.append((ch, feat))
    return samples


def _find_system_fonts() -> List[str]:
    found = []
    for directory in _SYSTEM_FONT_DIRS:
        for name in _SYSTEM_FONT_FILES:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                found.append(path)
    return found


def _render_system_font_samples() -> List[Tuple[str, np.ndarray]]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return []
    samples = []
    for font_path in _find_system_fonts():
        for size in _PIL_FONT_SIZES:
            try:
                font = ImageFont.truetype(font_path, size)
            except OSError:
                continue
            for ch in CHARSET:
                img = Image.new("L", (size * 2, size * 2), 0)
                ImageDraw.Draw(img).text((size // 2, size // 4), ch, fill=255, font=font)
                feat = _normalize_glyph(_binarize_rendered(np.array(img)))
                if feat is not None:
                    samples.append((ch, feat))
    return samples


class DigitClassifier:
    """kNN 字符分类器 (对应 HALCON 的 OCR 分类器句柄)"""

    def __init__(self):
        samples = _render_hershey_samples() + _render_system_font_samples()
        self.labels = np.array([CHARSET.index(ch) for ch, _ in samples], dtype=np.int32)
        features = np.stack([f for _, f in samples]).astype(np.float32)
        self.knn = cv2.ml.KNearest_create()
        self.knn.train(features, cv2.ml.ROW_SAMPLE, self.labels)

    def classify(self, binary_glyph: np.ndarray) -> Tuple[str, float]:
        """返回 (字符, 置信度 0~1); 无法形成有效字形时返回 ('?', 0.0)"""
        feat = _normalize_glyph(binary_glyph)
        if feat is None:
            return "?", 0.0
        _, _, neighbours, _ = self.knn.findNearest(feat.reshape(1, -1), KNN_K)
        votes = neighbours[0].astype(np.int32)
        winner = int(np.bincount(votes).argmax())
        confidence = float(np.mean(votes == winner))
        return CHARSET[winner], round(confidence, 3)


def get_classifier() -> DigitClassifier:
    global _classifier_cache
    if _classifier_cache is None:
        _classifier_cache = DigitClassifier()
    return _classifier_cache


def _reading_order(objects) -> List:
    """按阅读顺序排序: 先按行聚类 (纵向中心差小于半个字高视为同一行), 行内从左到右"""
    if not objects:
        return []
    heights = sorted(o.bbox[2] - o.bbox[0] for o in objects)
    line_gap = 0.5 * heights[len(heights) // 2]
    ordered = sorted(objects, key=lambda o: o.centroid[0])
    lines, current = [], [ordered[0]]
    for obj in ordered[1:]:
        if abs(obj.centroid[0] - current[-1].centroid[0]) <= line_gap:
            current.append(obj)
        else:
            lines.append(current)
            current = [obj]
    lines.append(current)
    return [o for line in lines for o in sorted(line, key=lambda o: o.centroid[1])]


def do_ocr_multi_class(region: Region) -> Tuple[List[str], List[float]]:
    """对 Region 中每个连通域单独分类, 按阅读顺序返回 (Class 列表, Confidence 列表)"""
    classifier = get_classifier()
    connected = region if region.is_connected else connection(region)
    classes: List[str] = []
    confidences: List[float] = []
    for obj in _reading_order(connected.objects):
        r0, c0, r1, c1 = obj.bbox
        glyph = connected.mask[r0:r1, c0:c1]
        ch, conf = classifier.classify(glyph)
        classes.append(ch)
        confidences.append(conf)
    return classes, confidences
