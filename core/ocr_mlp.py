"""
可训练的 OCR MLP 分类器 (HALCON append_ocr_trainf / create_ocr_class_mlp / trainf_ocr_class_mlp /
write_ocr_class_mlp / read_ocr_class_mlp 的平替)。

- 训练文件 .trf: 每行一个 JSON 样本 {"c": 字符, "d": 归一化字形 (base64)}, 可反复追加
- 分类器 .omc: 一个 JSON 文件, 含字符表与 OpenCV ANN_MLP 的 XML 序列化文本 (不使用 pickle, 读取别人的文件也不会执行代码)
- 特征为归一化后的二值字形 (与内置分类器一致), 训练时对每个样本做轻微平移 / 旋转 / 缩放增强, 使小样本也能泛化
"""

import base64
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.ocr_chars import GLYPH_H, GLYPH_W, _normalize_glyph

FORMAT_TAG = "navivision-ocr-mlp-1"
ERROR_LOG_POINTS = 20
ACTIVATION_SLOPE = 0.05  # 输入有 560 维, 默认斜率 (2/3) 会让隐藏层饱和、几乎学不动
AUGMENT_COPIES = 24
AUGMENT_SHIFT_PX = 1.0
AUGMENT_ROTATE_DEG = 6.0
AUGMENT_SCALE = 0.08
SOFTMAX_TEMPERATURE = 3.0
TARGET_ON, TARGET_OFF = 1.0, -1.0
DEFAULT_SEED = 42


def glyph_feature(binary: np.ndarray) -> Optional[np.ndarray]:
    """二值字形 -> 归一化特征向量 (GLYPH_W*GLYPH_H, 0~1); 像素太少时返回 None"""
    return _normalize_glyph(binary)


# ---------------------------------------------------------------- 训练文件 (.trf)

def append_samples(path: Path, features: List[np.ndarray], classes: List[str]) -> None:
    if len(features) != len(classes):
        raise ValueError(f"字符区域数 ({len(features)}) 与 Class 个数 ({len(classes)}) 不一致")
    with open(path, "a", encoding="utf-8") as handle:
        for feat, cls in zip(features, classes):
            data = base64.b64encode((feat * 255.0).round().astype(np.uint8).tobytes()).decode("ascii")
            handle.write(json.dumps({"c": str(cls), "d": data}, ensure_ascii=False) + "\n")


def load_samples(path: Path) -> Tuple[np.ndarray, List[str]]:
    if not path.exists():
        raise FileNotFoundError(f"训练文件不存在: {path.name}")
    feats, labels = [], []
    with open(path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                raw = np.frombuffer(base64.b64decode(item["d"]), dtype=np.uint8)
                if raw.size != GLYPH_W * GLYPH_H:
                    raise ValueError("字形尺寸不符")
                feats.append(raw.astype(np.float32) / 255.0)
                labels.append(str(item["c"]))
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"训练文件 {path.name} 第 {line_no} 行格式错误: {exc}") from exc
    if not feats:
        raise ValueError(f"训练文件 {path.name} 中没有样本")
    return np.stack(feats), labels


def read_names(path: Path) -> Tuple[List[str], List[int]]:
    """返回 (字符名列表, 每个字符的样本数), 字符名按首次出现的顺序"""
    _, labels = load_samples(path)
    counts: Dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return list(counts.keys()), list(counts.values())


# ---------------------------------------------------------------- 分类器

def _augment(feat: np.ndarray, rng: np.random.RandomState) -> np.ndarray:
    canvas = feat.reshape(GLYPH_H, GLYPH_W)
    angle = rng.uniform(-AUGMENT_ROTATE_DEG, AUGMENT_ROTATE_DEG)
    scale = 1.0 + rng.uniform(-AUGMENT_SCALE, AUGMENT_SCALE)
    mat = cv2.getRotationMatrix2D((GLYPH_W / 2.0, GLYPH_H / 2.0), angle, scale)
    mat[:, 2] += rng.uniform(-AUGMENT_SHIFT_PX, AUGMENT_SHIFT_PX, size=2)
    warped = cv2.warpAffine(canvas, mat, (GLYPH_W, GLYPH_H), flags=cv2.INTER_LINEAR)
    return warped.reshape(-1).astype(np.float32)


class TrainedOcrClassifier:
    """对应 HALCON 的 OCR MLP 分类器句柄: 创建后先训练, 再识别 / 保存"""

    def __init__(self, characters: List[str], num_hidden: int = 80, seed: int = DEFAULT_SEED):
        names = [str(c) for c in characters]
        if len(names) < 2:
            raise ValueError("分类器至少需要 2 个字符类别")
        if len(set(names)) != len(names):
            raise ValueError("Characters 中有重复的字符")
        self.characters = names
        self.num_hidden = max(2, int(num_hidden))
        self.seed = int(seed)
        self.model = None

    def _new_model(self) -> "cv2.ml_ANN_MLP":
        model = cv2.ml.ANN_MLP_create()
        model.setLayerSizes(np.array([GLYPH_W * GLYPH_H, self.num_hidden, len(self.characters)]))
        model.setActivationFunction(cv2.ml.ANN_MLP_SIGMOID_SYM, ACTIVATION_SLOPE, 1.7159)
        model.setTrainMethod(cv2.ml.ANN_MLP_RPROP)
        return model

    def _targets(self, labels: List[str]) -> np.ndarray:
        index = {c: i for i, c in enumerate(self.characters)}
        unknown = sorted({l for l in labels if l not in index})
        if unknown:
            raise ValueError(f"训练文件中的字符 {unknown} 不在分类器的字符表里")
        targets = np.full((len(labels), len(self.characters)), TARGET_OFF, dtype=np.float32)
        for row, label in enumerate(labels):
            targets[row, index[label]] = TARGET_ON
        return targets

    def train(self, features: np.ndarray, labels: List[str], max_iterations: int, error_tolerance: float
              ) -> Tuple[float, List[float]]:
        """训练并返回 (训练集平均平方误差, 误差随迭代的变化记录)"""
        rng = np.random.RandomState(self.seed)
        samples, sample_labels = [features], list(labels)
        for feat, label in zip(features, labels):
            for _ in range(AUGMENT_COPIES):
                samples.append(_augment(feat, rng)[None, :])
                sample_labels.append(label)
        data = np.vstack(samples).astype(np.float32)
        targets = self._targets(sample_labels)

        train_data = cv2.ml.TrainData_create(data, cv2.ml.ROW_SAMPLE, targets)
        total = max(1, int(max_iterations))
        checkpoints = sorted({max(1, round(total * k / ERROR_LOG_POINTS)) for k in range(1, ERROR_LOG_POINTS + 1)})
        error_log: List[float] = []
        for iterations in checkpoints:
            # 固定随机种子下训练是确定性的: 从头训练 N 次迭代 == 完整训练过程的前 N 次迭代,
            # 所以在每个检查点各自从头训练, 就得到一条干净的误差下降曲线 (续训会重置 RPROP 步长状态而抖动)
            cv2.setRNGSeed(self.seed)
            self.model = self._new_model()
            self.model.setTermCriteria((cv2.TERM_CRITERIA_COUNT, iterations, 0.0))
            self.model.train(train_data)
            error_log.append(float(np.mean((self.model.predict(data)[1] - targets) ** 2)))
            if error_log[-1] <= float(error_tolerance):
                break
        return error_log[-1], error_log

    def classify(self, binary_glyph: np.ndarray) -> Tuple[str, float]:
        if self.model is None or not self.model.isTrained():
            raise ValueError("OCR 分类器尚未训练: 请先调用 trainf_ocr_class_mlp 或 read_ocr_class_mlp 载入已训练的分类器")
        feat = glyph_feature(binary_glyph)
        if feat is None:
            return "?", 0.0
        out = self.model.predict(feat.reshape(1, -1))[1][0]
        weights = np.exp((out - out.max()) * SOFTMAX_TEMPERATURE)
        best = int(np.argmax(out))
        return self.characters[best], round(float(weights[best] / weights.sum()), 3)

    # ---- 保存 / 读取 (.omc)
    def to_json(self) -> str:
        if self.model is None or not self.model.isTrained():
            raise ValueError("OCR 分类器尚未训练, 无法保存")
        store = cv2.FileStorage("model.xml", cv2.FileStorage_WRITE | cv2.FileStorage_MEMORY)
        self.model.write(store)
        return json.dumps({
            "format": FORMAT_TAG, "characters": self.characters, "num_hidden": self.num_hidden,
            "seed": self.seed, "model": store.releaseAndGetString(),
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "TrainedOcrClassifier":
        try:
            info = json.loads(text)
            if info.get("format") != FORMAT_TAG:
                raise ValueError("不是 NaviVision 的 OCR 分类器文件")
            clf = cls(info["characters"], info["num_hidden"], info["seed"])
            store = cv2.FileStorage(info["model"], cv2.FileStorage_READ | cv2.FileStorage_MEMORY)
            model = clf._new_model()
            model.read(store.root())
        except (ValueError, KeyError, TypeError, cv2.error) as exc:
            raise ValueError(f"无法读取 OCR 分类器文件: {exc}") from exc
        if not model.isTrained():
            raise ValueError("OCR 分类器文件中没有训练好的模型")
        clf.model = model
        return clf

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "TrainedOcrClassifier":
        return cls.from_json(path.read_text(encoding="utf-8"))
