"""
Generate realistic industrial inspection test samples
"""

import os
import cv2
import numpy as np
import math

os.makedirs("samples", exist_ok=True)

def save_image(rel_path, img):
    success, enc = cv2.imencode(".png", img)
    if success:
        with open(rel_path, "wb") as f:
            f.write(enc.tobytes())
        print(f"Successfully saved {rel_path} (size: {os.path.getsize(rel_path)} bytes)")
    else:
        print(f"Failed to encode {rel_path}")

# 1. Pills (药丸/药片瑕疵检测样本)
def make_pills_sample():
    w, h = 640, 480
    img = np.full((h, w, 3), 45, dtype=np.uint8)  # 深灰工业托盘底色
    noise = np.random.normal(0, 3, (h, w, 3)).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    centers = []
    for r in range(3):
        for c in range(5):
            cx = 100 + c * 110
            cy = 100 + r * 140
            centers.append((cx, cy))
            cv2.circle(img, (cx, cy), 42, (60, 60, 65), -1)
            cv2.circle(img, (cx, cy), 42, (80, 80, 85), 2)
            
    for idx, (cx, cy) in enumerate(centers):
        if idx == 7:
            # 缺失药丸
            continue
        elif idx == 11:
            # 破损/残缺药丸
            pts = np.array([
                [cx - 28, cy - 15], [cx + 10, cy - 25],
                [cx + 25, cy + 10], [cx - 10, cy + 28]
            ], np.int32)
            cv2.fillPoly(img, [pts], (220, 220, 225))
            cv2.polylines(img, [pts], True, (170, 170, 175), 2)
        elif idx == 3:
            # 异物毛刺噪点药丸
            cv2.circle(img, (cx, cy), 28, (230, 230, 235), -1)
            cv2.circle(img, (cx + 20, cy - 20), 6, (120, 120, 130), -1)
        else:
            # 正常白色圆形药片
            cv2.circle(img, (cx, cy), 28, (240, 240, 245), -1)
            cv2.circle(img, (cx - 6, cy - 6), 18, (250, 250, 255), -1)
            cv2.circle(img, (cx, cy), 28, (190, 190, 195), 2)
            
    save_image("samples/pills_inspection.png", img)

# 2. PCB Chips & Pins (PCB 元器件与焊盘引脚)
def make_pcb_sample():
    w, h = 640, 480
    img = np.full((h, w, 3), (25, 75, 30), dtype=np.uint8)  # 绿色 PCB
    
    for y in range(40, h, 60):
        cv2.line(img, (20, y), (w - 20, y), (35, 110, 45), 3)
    for x in range(50, w, 90):
        cv2.line(img, (x, 30), (x, h - 30), (35, 110, 45), 2)
        
    cx, cy = w // 2, h // 2
    chip_size = 140
    x1, y1 = cx - chip_size // 2, cy - chip_size // 2
    x2, y2 = cx + chip_size // 2, cy + chip_size // 2
    cv2.rectangle(img, (x1, y1), (x2, y2), (25, 25, 25), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (50, 50, 50), 2)
    cv2.circle(img, (x1 + 18, y1 + 18), 7, (70, 70, 70), -1)
    
    pin_len = 24
    pin_w = 4
    for i in range(x1 + 15, x2 - 10, 12):
        cv2.rectangle(img, (i, y1 - pin_len), (i + pin_w, y1), (210, 215, 220), -1)
        cv2.rectangle(img, (i, y2), (i + pin_w, y2 + pin_len), (210, 215, 220), -1)
    for j in range(y1 + 15, y2 - 10, 12):
        cv2.rectangle(img, (x1 - pin_len, j), (x1, j + pin_w), (210, 215, 220), -1)
        cv2.rectangle(img, (x2, j), (x2 + pin_len, j + pin_w), (210, 215, 220), -1)
        
    via_positions = [(80, 80), (560, 80), (80, 400), (560, 400), (120, 240), (520, 240)]
    for vx, vy in via_positions:
        cv2.circle(img, (vx, vy), 14, (30, 190, 220), -1)
        cv2.circle(img, (vx, vy), 6, (15, 15, 15), -1)
        
    save_image("samples/pcb_components.png", img)

# 3. Metal Gears & Washers (机械工件与垫圈)
def make_gears_sample():
    w, h = 640, 480
    img = np.full((h, w, 3), 60, dtype=np.uint8)
    
    g1_x, g1_y, r_base, r_outer = 200, 240, 75, 95
    num_teeth = 16
    gear_pts = []
    for i in range(num_teeth * 2):
        angle = i * math.pi / num_teeth
        r = r_outer if (i % 2 == 0) else r_base
        gear_pts.append([int(g1_x + r * math.cos(angle)), int(g1_y + r * math.sin(angle))])
    cv2.fillPoly(img, [np.array(gear_pts, np.int32)], (200, 205, 210))
    cv2.circle(img, (g1_x, g1_y), 28, (60, 60, 60), -1)
    
    washers = [(450, 140, 45, 18), (480, 320, 52, 22), (370, 380, 36, 14)]
    for wx, wy, r_out, r_in in washers:
        cv2.circle(img, (wx, wy), r_out, (190, 195, 200), -1)
        cv2.circle(img, (wx, wy), r_in, (60, 60, 60), -1)
        
    cv2.rectangle(img, (360, 200), (410, 250), (170, 175, 180), -1)
    cv2.rectangle(img, (375, 250), (395, 310), (180, 185, 190), -1)
    
    save_image("samples/metal_parts.png", img)

make_pills_sample()
make_pcb_sample()
make_gears_sample()
print("All samples successfully generated!")
