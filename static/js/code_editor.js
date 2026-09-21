/**
 * NaviVision Studio - Interactive Code Studio & Live Sandbox Editor
 * 支持 HDevelop 4GL 视觉原生脚本与 Python / OpenCV 双语言模式、
 * 快捷键 Ctrl+Enter 运行、Iconic 变量视口目标监视、一键转译为流水线与终端日志输出
 */

class InteractiveCodeEditor {
  constructor(editorEl, lineNumbersEl, consoleEl, onResultCallback) {
    this.editor = editorEl;
    this.lineNumbers = lineNumbersEl;
    this.console = consoleEl;
    this.onResult = onResultCallback;

    this.currentLang = 'hdev'; // 'hdev' | 'python'
    this.currentDisplayTarget = null;
    this.lastHDevResult = null;

    // HDevelop 经典工业视觉算子模板
    this.hdevTemplates = {
      "pills_inspection": `* ==========================================================
* NaviVision HDevelop: 药板药丸瑕疵与完整度检测
* ==========================================================
read_image (Image, 'pills')
rgb1_to_gray (Image, GrayImage)
threshold (GrayImage, BrightRegions, 180, 255)
connection (BrightRegions, ConnectedRegions)
select_shape (ConnectedRegions, SelectedPills, 'area', 'and', 1000, 3000)
count_obj (SelectedPills, PillCount)
smallest_rectangle2 (SelectedPills, Rows, Cols, Phis, L1, L2)
dev_display (SelectedPills)
`,
      "pcb_subpix": `* ==========================================================
* NaviVision HDevelop: PCB 芯片引脚与亚像素边缘提取
* ==========================================================
read_image (Image, 'pcb')
rgb1_to_gray (Image, GrayImage)
gauss_filter (GrayImage, FilteredImage, 5)
edges_subpix (FilteredImage, Edges, 'canny', 1.0, 40, 100)
threshold (GrayImage, SolderPads, 160, 255)
closing_circle (SolderPads, ClosedPads, 3)
dev_display (Edges)
`,
      "metal_gears": `* ==========================================================
* NaviVision HDevelop: 工业工件与垫圈几何度量
* ==========================================================
read_image (Image, 'metal_parts')
rgb1_to_gray (Image, GrayImage)
binary_threshold (GrayImage, Parts, 'max_separability', 'dark', UsedThreshold)
connection (Parts, ConnectedParts)
select_shape (ConnectedParts, Gears, 'area', 'and', 2000, 50000)
smallest_circle (Gears, CenterRows, CenterCols, Radii)
dev_display (Gears)
`
    };

    // Python / OpenCV 算法模板
    this.pythonTemplates = {
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
      "contours": `import cv2
import numpy as np

# 提取 Canny 边缘与高精度轮廓
blurred = cv2.GaussianBlur(gray, (5, 5), 1.2)
edges = cv2.Canny(blurred, 50, 150)
contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

print(f"[Contour Extractor] 提取到 {len(contours)} 条独立多边形轮廓")
result_contours = contours
`,
      "ai_yolo": `import requests
import json
import cv2
import numpy as np

# 模拟或调用外部工业 YOLOv8 目标检测服务
print("[AI API] 正在打包当前帧图像，发起 HTTP REST 请求...")

success, encoded = cv2.imencode(".jpg", image)
img_bytes = encoded.tobytes()

print("[AI API] 检测服务响应成功: 耗时 18.2ms")
detections = [
    {"class": "defect_chip", "confidence": 0.94, "bbox": [120, 140, 60, 60]},
    {"class": "solder_pin", "confidence": 0.98, "bbox": [280, 210, 40, 30]}
]

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

_, buf = cv2.imencode('.jpg', image)
b64_str = base64.b64encode(buf).decode('utf-8')

payload = {
    "model": "llava:latest",
    "prompt": "请识别并描述图中的工业零部件是否存在外观缺陷或缺失？",
    "images": [b64_str],
    "stream": False
}

print("[Ollama VLM] 提示词: '检测工件缺陷与缺失'")
print("-> [模拟大模型分析结论]: 视野内检测到 14 枚圆形药片，其中第 8 位置药片缺失，第 12 位置药片边缘存在机械破损。建议剔除！")
`
    };

    this.initEvents();
    this.updateLanguageUI('hdev');
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

    // 支持 Tab 缩进 (4 空格) 和 Ctrl+Enter 快捷运行
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

    // 语言选择下拉框
    const langSelect = document.getElementById('codeLangSelect');
    if (langSelect) {
      langSelect.addEventListener('change', (e) => {
        this.updateLanguageUI(e.target.value);
      });
    }

    // 模板选择下拉框
    const tplSelect = document.getElementById('codeTemplateSelect');
    if (tplSelect) {
      tplSelect.addEventListener('change', (e) => {
        this.loadTemplate(e.target.value);
      });
    }

    // 运行按钮
    const runBtn = document.getElementById('btnRunScript');
    if (runBtn) {
      runBtn.addEventListener('click', () => {
        this.runScript();
      });
    }

    // 转译为流水线按钮
    const syncBtn = document.getElementById('btnSyncToPipeline');
    if (syncBtn) {
      syncBtn.addEventListener('click', () => {
        this.syncToPipeline();
      });
    }

    // 清屏按钮
    const clearBtn = document.getElementById('btnClearTerminal');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        this.clearConsole();
      });
    }
  }

  updateLanguageUI(lang) {
    this.currentLang = lang;
    const tplSelect = document.getElementById('codeTemplateSelect');
    const varBar = document.getElementById('hdevVarBar');
    const syncBtn = document.getElementById('btnSyncToPipeline');
    const termTitle = document.getElementById('terminalTitle');

    if (!tplSelect) return;
    tplSelect.innerHTML = '';

    if (lang === 'hdev') {
      tplSelect.innerHTML = `
        <option value="pills_inspection">药丸完整度质检 (Pills)</option>
        <option value="pcb_subpix">PCB 亚像素边缘提取 (PCB)</option>
        <option value="metal_gears">工件几何度量 (Metal)</option>
      `;
      if (varBar) varBar.style.display = 'flex';
      if (syncBtn) syncBtn.style.display = 'inline-flex';
      if (termTitle) termTitle.textContent = '🖥️ HDevelop 4GL 解释执行沙箱控制台';
      this.loadTemplate('pills_inspection');
      this.logToConsole('🔶 已切换到 HDevelop 4GL 脚本模式，原生支持 HALCON 经典算子与四槽位语法！', 'info');
    } else {
      tplSelect.innerHTML = `
        <option value="sobel">Sobel 梯度自定二值化</option>
        <option value="contours">Canny 矢量轮廓提取</option>
        <option value="ai_yolo">调用工业 YOLO AI 检测服务</option>
        <option value="ollama_vlm">接入本地 Ollama 多模态大模型</option>
      `;
      if (varBar) varBar.style.display = 'none';
      if (syncBtn) syncBtn.style.display = 'none';
      if (termTitle) termTitle.textContent = '🖥️ Python 3.12 沙箱终端控制台';
      this.loadTemplate('sobel');
      this.logToConsole('🐍 已切换到 Python 脚本模式，支持 cv2 / numpy 独立脚本！', 'info');
    }
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
    const pool = this.currentLang === 'hdev' ? this.hdevTemplates : this.pythonTemplates;
    if (pool[tplKey]) {
      this.editor.value = pool[tplKey];
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

    const sid = localStorage.getItem('navivision_session_id') || 'default';

    if (this.currentLang === 'hdev') {
      this.logToConsole('⚡ 正在解析并由 HDevInterpreter 解释执行...', 'info');
      try {
        const resp = await fetch('/api/hdev/run', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Session-ID': sid
          },
          body: JSON.stringify({
            code: code,
            display_target: this.currentDisplayTarget
          })
        });
        const data = await resp.json();

        if (data.success) {
          this.lastHDevResult = data;
          this.logToConsole(data.stdout || '[OK] 脚本执行完毕。', 'success');
          this.logToConsole(`⏱️ 执行耗时: ${data.duration_ms} ms | 渲染目标: ${data.display_target || 'Image'}`, 'meta');

          this.renderIconicVarPills(data.iconic_vars || [], data.display_target);

          if (typeof this.onResult === 'function') {
            this.onResult(data);
          }
        } else {
          this.logToConsole(data.error || 'HDevelop 脚本执行出错', 'error');
          if (data.stdout) {
            this.logToConsole(data.stdout, 'error');
          }
        }
      } catch (err) {
        this.logToConsole(`[网络异常] 无法连接 HDevelop 服务端: ${err}`, 'error');
      } finally {
        if (runBtn) {
          runBtn.textContent = '▶ 运行 (Ctrl+Enter)';
          runBtn.disabled = false;
        }
      }
    } else {
      // Python 模式
      this.logToConsole('⚡ 正在编译并提交 Python 沙箱执行...', 'info');
      try {
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
        this.logToConsole(`[网络异常] 无法连接 Python 沙箱服务端: ${err}`, 'error');
      } finally {
        if (runBtn) {
          runBtn.textContent = '▶ 运行 (Ctrl+Enter)';
          runBtn.disabled = false;
        }
      }
    }
  }

  renderIconicVarPills(vars, activeTarget) {
    const pillsContainer = document.getElementById('hdevVarPills');
    if (!pillsContainer) return;
    pillsContainer.innerHTML = '';

    if (!vars || vars.length === 0) {
      pillsContainer.innerHTML = '<span style="color:var(--text-muted);font-style:italic;">无输出变量</span>';
      return;
    }

    vars.forEach(v => {
      const pill = document.createElement('button');
      pill.className = `btn btn-secondary ${v.name === activeTarget ? 'active' : ''}`;
      pill.style.padding = '2px 8px';
      pill.style.fontSize = '11px';
      pill.style.borderRadius = '12px';
      pill.style.cursor = 'pointer';

      let meta = v.type;
      if (v.type === 'Region' && v.object_count !== undefined) {
        meta = `${v.object_count} objs`;
      } else if (v.type === 'XLD' && v.contour_count !== undefined) {
        meta = `${v.contour_count} XLD`;
      }

      pill.innerHTML = `<strong>${v.name}</strong> <span style="opacity:0.75;font-size:10px;">(${meta})</span>`;
      if (v.name === activeTarget) {
        pill.style.borderColor = 'var(--neon-cyan)';
        pill.style.color = 'var(--neon-cyan)';
      }

      pill.addEventListener('click', () => {
        this.currentDisplayTarget = v.name;
        this.runScript();
      });

      pillsContainer.appendChild(pill);
    });
  }

  async syncToPipeline() {
    const code = this.editor.value;
    const sid = localStorage.getItem('navivision_session_id') || 'default';
    this.logToConsole('🧩 正在将当前 HDevelop 脚本转译为可视化算子流水线...', 'info');

    try {
      const resp = await fetch('/api/hdev/to_pipeline', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sid
        },
        body: JSON.stringify({ code })
      });
      const data = await resp.json();

      if (data.success) {
        this.logToConsole(`[✓] 转译成功！共生成 ${data.steps.length} 个流水线算子卡片。`, 'success');
        // 分发全局事件通知流水线 UI 重新渲染
        window.dispatchEvent(new CustomEvent('navivision:pipeline-synced', { detail: data }));
      } else {
        this.logToConsole(`[!] 转译失败: ${data.error || '未知错误'}`, 'error');
      }
    } catch (err) {
      this.logToConsole(`[网络异常] 无法转译到流水线: ${err}`, 'error');
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
