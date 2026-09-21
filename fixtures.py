import cv2
import numpy as np

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
NOISE_SEED = 20240915
NOISE_SIGMA = 3


def make_blob_image() -> np.ndarray:
    rng = np.random.default_rng(NOISE_SEED)
    img = np.full((IMAGE_HEIGHT, IMAGE_WIDTH, 3), 45, dtype=np.uint8)
    noise = rng.normal(0, NOISE_SIGMA, img.shape).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    centers = [(100 + col * 110, 100 + row * 140) for row in range(3) for col in range(5)]
    for cx, cy in centers:
        cv2.circle(img, (cx, cy), 42, (60, 60, 65), -1)
        cv2.circle(img, (cx, cy), 42, (80, 80, 85), 2)

    for idx, (cx, cy) in enumerate(centers):
        if idx == 7:
            continue
        if idx == 11:
            pts = np.array([[cx - 28, cy - 15], [cx + 10, cy - 25], [cx + 25, cy + 10], [cx - 10, cy + 28]], np.int32)
            cv2.fillPoly(img, [pts], (220, 220, 225))
            cv2.polylines(img, [pts], True, (170, 170, 175), 2)
        elif idx == 3:
            cv2.circle(img, (cx, cy), 28, (230, 230, 235), -1)
            cv2.circle(img, (cx + 20, cy - 20), 6, (120, 120, 130), -1)
        else:
            cv2.circle(img, (cx, cy), 28, (240, 240, 245), -1)
            cv2.circle(img, (cx - 6, cy - 6), 18, (250, 250, 255), -1)
            cv2.circle(img, (cx, cy), 28, (190, 190, 195), 2)
    return img


def encode_png(img: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", img)
    assert ok, "PNG 编码失败"
    return buffer.tobytes()
