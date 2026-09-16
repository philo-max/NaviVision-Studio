/**
 * NaviVision Studio - Interactive Code Studio & Live Sandbox Editor
 * 支持手写 Python / OpenCV 代码、Tab 缩进、快捷键 Ctrl+Enter 运行、预设 AI / 算法模板与黑客终端日志输出
 */

class InteractiveCodeEditor {
  constructor(editorEl, lineNumbersEl, consoleEl, onResultCallback) {
    this.editor = editorEl;
    this.lineNumbers = lineNumbersEl;
    this.console = consoleEl;
    this.onResult = onResultCallback;

    this.templates = {
      "sobel": `import cv2
import numpy as np

# 1. 计算 Sobel 边缘梯度
grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
abs_grad_x = cv2.convertScaleAbs(grad_x)
abs_grad_y = cv2.convertScaleAbs(grad_y)
grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)

# 2. 对梯度进行大津法自适应二值化
_, result_mask = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

# 3. 闭运算桥接边缘断裂
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
result_mask = cv2.morphologyEx(result_mask, cv2.MORPH_CLOSE, kernel)

print(f"[Sobel Gradient] Active edge pixels: {np.count_nonzero(result_mask)}")
print("[Info] 自定义算子计算完毕，结果已投射到中心画布！")
`,
      "ai_yolo": `import requests
import json
import cv2
import numpy as np

# 模拟或调用外部工业 YOLOv8 目标检测服务
print("[AI API] 正在打包当前帧图像，发起 HTTP REST 请求...")

# 提取当前图像编码为 JPEG 二进制
success, encoded = cv2.imencode(".jpg", image)
img_bytes = encoded.tobytes()

# 示例: 向本地或远程 YOLO / 深度学习服务发送检测请求
# resp = requests.post("http://localhost:8000/v1/object-detect", files={"file": img_bytes})
# detections = resp.json().get("detections", [])

# 模拟 API 返回的检测框结果:
print("[AI API] 检测服务响应成功: 耗时 18.2ms")
detections = [
    {"class": "defect_chip", "confidence": 0.94, "bbox": [120, 140, 60, 60]},
    {"class": "solder_pin", "confidence": 0.98, "bbox": [280, 210, 40, 30]}
]

# 在画布上绘制 AI 预测框与置信度标签
result_image = image.copy()
for det in detections:
    x, y, w, h = det["bbox"]
    label = f"{det['class']} {det['confidence']*100:.1f}%"
    cv2.rectangle(result_image, (x, y), (x + w, y + h), (0, 50, 255), 2)
    cv2.putText(result_image, label, (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 50, 255), 2)
    print(f"  -> 识别目标: {label} @ [{x}, {y}, {w}, {h}]")
`,
      "ollama_vlm": `import requests
import json
import base64
import cv2

print("[Ollama VLM] 连接本地多模态大模型 API (http://localhost:11434/api/generate)...")

# 将图像转为 Base64
_, buf = cv2.imencode('.jpg', image)
b64_str = base64.b64encode(buf).decode('utf-8')

payload = {
    "model": "llava:latest",  # 或 qwen2-vl
    "prompt": "请识别并描述图中的工业零部件是否存在外观缺陷或缺失？",
    "images": [b64_str],
    "stream": False
}

print("[Ollama VLM] 提示词: '检测工件缺陷与缺失'")
print("[Ollama VLM] (如本地已安装 Ollama 即可解开请求直连):")
# r = requests.post("http://localhost:11434/api/generate", json=payload)
# print(r.json().get("response"))

# 演示输出
print("-> [模拟大模型分析结论]: 视野内检测到 14 枚圆形药片，其中第 8 位置药片缺失，第 12 位置药片边缘存在机械破损。建议剔除！")
`,
      "contours": `import cv2
import numpy as np

# 提取 Canny 边缘与高精度轮廓
blurred = cv2.GaussianBlur(gray, (5, 5), 1.2)
edges = cv2.Canny(blurred, 50, 150)
contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

print(f"[Contour Extractor] 提取到 {len(contours)} 条独立多边形轮廓")
result_contours = contours
`
    };

    this.initEvents();
    this.loadTemplate("sobel");
  }

  initEvents() {
    // 监听输入更新行号
    this.editor.addEventListener('input', () => {
      this.updateLineNumbers();
    });

    // 滚动同步
    this.editor.addEventListener('scroll', () => {
      this.lineNumbers.scrollTop = this.editor.scrollTop;
    });

    // 支持 Tab 缩进 (插入 4 个空格) 和 Ctrl+Enter 运行
    this.editor.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = this.editor.selectionStart;
        const end = this.editor.selectionEnd;
        this.editor.value = this.editor.value.substring(0, start) + '    ' + this.editor.value.substring(end);
        this.editor.selectionStart = this.editor.selectionEnd = start + 4;
        this.updateLineNumbers();
      } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        this.runScript();
      }
    });

    this.updateLineNumbers();
  }

  updateLineNumbers() {
    const lines = this.editor.value.split('\n').length;
    let numbersHtml = '';
    for (let i = 1; i <= lines; i++) {
      numbersHtml += `<div>${i}</div>`;
    }
    this.lineNumbers.innerHTML = numbersHtml;
  }

  loadTemplate(tplKey) {
    if (this.templates[tplKey]) {
      this.editor.value = this.templates[tplKey];
      this.updateLineNumbers();
    }
  }

  async runScript() {
    const code = this.editor.value;
    const runBtn = document.getElementById('btnRunScript');
    if (runBtn) {
      runBtn.textContent = '⏳ 执行中...';
      runBtn.disabled = true;
    }

    this.logToConsole('⚡ 正在编译并提交 Python 沙箱执行...', 'info');

    try {
      const sid = localStorage.getItem('navivision_session_id') || 'default';
      const resp = await fetch('/api/script/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sid
        },
        body: JSON.stringify({ code })
      });
      const data = await resp.json();

      if (data.success) {
        this.logToConsole(data.stdout || '[OK] 代码执行完毕，无 print 输出。', 'success');
        this.logToConsole(`⏱️ 执行耗时: ${data.duration_ms} ms`, 'meta');

        if (typeof this.onResult === 'function') {
          this.onResult(data);
        }
      } else {
        this.logToConsole(data.detail || data.error || '执行出错', 'error');
        if (data.stdout) {
          this.logToConsole(data.stdout, 'error');
        }
      }
    } catch (err) {
      this.logToConsole(`[网络异常] 无法连接沙箱服务端: ${err}`, 'error');
    } finally {
      if (runBtn) {
        runBtn.textContent = '▶ 运行代码 (Ctrl+Enter)';
        runBtn.disabled = false;
      }
    }
  }

  logToConsole(text, level = 'normal') {
    const entry = document.createElement('div');
    entry.className = `console-entry ${level}`;
    const timeStr = new Date().toLocaleTimeString();
    entry.textContent = `[${timeStr}] ${text}`;
    this.console.appendChild(entry);
    this.console.scrollTop = this.console.scrollHeight;
  }

  clearConsole() {
    this.console.innerHTML = '';
  }
}
