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

    // 单步调试状态: 断点行号集合、当前暂停行、调试会话是否激活、已打印到终端的日志长度
    this.breakpoints = new Set();
    this.debugCurrentLine = null;
    this.debugActive = false;
    this.debugLoggedStdoutLen = 0;
    this.lineNumbers.addEventListener('click', (e) => {
      const target = e.target.closest('[data-line]');
      if (!target) return;
      const line = parseInt(target.dataset.line, 10);
      if (this.breakpoints.has(line)) {
        this.breakpoints.delete(line);
      } else {
        this.breakpoints.add(line);
      }
      this.updateLineNumbers();
    });

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
      this.syncHighlightScroll();
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
    this.refreshHighlight();
    const varBar = document.getElementById('hdevVarBar');
    const syncBtn = document.getElementById('btnSyncToPipeline');
    const termTitle = document.getElementById('terminalTitle');

    if (lang === 'hdev') {
      if (varBar) varBar.style.display = 'flex';
      if (syncBtn) syncBtn.style.display = 'inline-flex';
      if (termTitle) termTitle.textContent = '🖥️ HDevelop 4GL 解释执行沙箱控制台';
      this.logToConsole('🔶 已切换到 HDevelop 4GL 脚本模式，原生支持 HALCON 经典算子与四槽位语法！Image 变量已绑定当前工作区图像，直接编写处理逻辑即可。', 'info');
    } else {
      if (varBar) varBar.style.display = 'none';
      if (syncBtn) syncBtn.style.display = 'none';
      if (termTitle) termTitle.textContent = '🖥️ Python 3.12 沙箱终端控制台';
      this.logToConsole('🐍 已切换到 Python 脚本模式，支持 cv2 / numpy 独立脚本！', 'info');
    }
  }

  updateLineNumbers() {
    const lines = this.editor.value.split('\n').length;
    let numbersHtml = '';
    for (let i = 1; i <= lines; i++) {
      const cls = ['line-num-item'];
      if (this.breakpoints.has(i)) cls.push('has-breakpoint');
      if (this.debugCurrentLine === i) cls.push('is-current-line');
      numbersHtml += `<div class="${cls.join(' ')}" data-line="${i}" title="点击切换断点">${i}</div>`;
    }
    this.lineNumbers.innerHTML = numbersHtml;
    this.refreshHighlight();
  }

  refreshHighlight() {
    const layer = document.getElementById('editorHighlight');
    if (!layer || !window.SyntaxHighlighter) return;
    layer.innerHTML = SyntaxHighlighter.highlight(this.editor.value, this.currentLang);
    this.syncHighlightScroll();
  }

  syncHighlightScroll() {
    const layer = document.getElementById('editorHighlight');
    if (!layer) return;
    layer.scrollTop = this.editor.scrollTop;
    layer.scrollLeft = this.editor.scrollLeft;
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
            display_target: this.currentDisplayTarget,
            roi: this.getRoi ? this.getRoi() : null
          })
        });
        const data = await resp.json();

        if (data.success) {
          this.lastHDevResult = data;
          this.logToConsole(data.stdout || '[OK] 脚本执行完毕。', 'success');
          this.logToConsole(`⏱️ 执行耗时: ${data.duration_ms} ms | 渲染目标: ${data.display_target || 'Image'}`, 'meta');

          this.renderIconicVarPills(data.iconic_vars || [], data.display_target);
          this.renderControlVars(data.control_var_list || []);
          this.renderWindowPills(data.windows || []);

          if (typeof this.onResult === 'function') {
            this.onResult(data);
          }
        } else {
          this.logToConsole(data.error || 'HDevelop 脚本执行出错', 'error');
          if (data.stdout) {
            this.logToConsole(data.stdout, 'error');
          }
          this.renderIconicVarPills(data.iconic_vars || [], data.display_target);
          this.renderControlVars(data.control_var_list || []);
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

  // ------------------------------------------------------------------
  // 单步调试 / 断点续跑 / 变量监视器
  // ------------------------------------------------------------------
  _debugSessionId() {
    return localStorage.getItem('navivision_session_id') || 'default';
  }

  _setDebugButtonsState({ canStart, canStep, canContinue, canStop }) {
    const btnStart = document.getElementById('btnDebugStart');
    const btnStep = document.getElementById('btnDebugStep');
    const btnContinue = document.getElementById('btnDebugContinue');
    const btnStop = document.getElementById('btnDebugStop');
    if (btnStart) btnStart.disabled = !canStart;
    if (btnStep) btnStep.disabled = !canStep;
    if (btnContinue) btnContinue.disabled = !canContinue;
    if (btnStop) btnStop.disabled = !canStop;
  }

  async debugStart() {
    if (this.currentLang !== 'hdev') {
      this.logToConsole('⚠️ 单步调试目前仅支持 HDevelop 4GL 脚本', 'error');
      return;
    }
    const code = this.editor.value;
    this.debugLoggedStdoutLen = 0;
    this.logToConsole('🐞 正在启动单步调试会话...', 'info');
    try {
      const resp = await fetch('/api/hdev/debug/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-ID': this._debugSessionId() },
        body: JSON.stringify({ code, roi: this.getRoi ? this.getRoi() : null })
      });
      const data = await resp.json();
      this.debugActive = true;
      this._setDebugButtonsState({ canStart: false, canStep: true, canContinue: true, canStop: true });
      this._handleDebugState(data);
    } catch (err) {
      this.logToConsole(`[网络异常] 启动调试会话失败: ${err}`, 'error');
    }
  }

  async debugStep() {
    try {
      const resp = await fetch('/api/hdev/debug/step', {
        method: 'POST',
        headers: { 'X-Session-ID': this._debugSessionId() }
      });
      if (resp.status === 404) {
        this.logToConsole('⚠️ 调试会话不存在或已过期，请重新点击"开始调试"', 'error');
        this._onDebugEnded();
        return;
      }
      const data = await resp.json();
      this._handleDebugState(data);
    } catch (err) {
      this.logToConsole(`[网络异常] 单步执行失败: ${err}`, 'error');
    }
  }

  async debugContinue() {
    try {
      const resp = await fetch('/api/hdev/debug/continue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-ID': this._debugSessionId() },
        body: JSON.stringify({ breakpoints: Array.from(this.breakpoints) })
      });
      if (resp.status === 404) {
        this.logToConsole('⚠️ 调试会话不存在或已过期，请重新点击"开始调试"', 'error');
        this._onDebugEnded();
        return;
      }
      const data = await resp.json();
      this._handleDebugState(data);
    } catch (err) {
      this.logToConsole(`[网络异常] 继续执行失败: ${err}`, 'error');
    }
  }

  async debugStop() {
    try {
      await fetch('/api/hdev/debug/stop', {
        method: 'POST',
        headers: { 'X-Session-ID': this._debugSessionId() }
      });
    } catch (err) {
      // 静默忽略网络异常, 前端状态仍需清理
    }
    this.logToConsole('🛑 调试会话已终止', 'info');
    this._onDebugEnded();
  }

  _onDebugEnded() {
    this.debugActive = false;
    this.debugCurrentLine = null;
    this.updateLineNumbers();
    this.renderWatchTable({});
    this._setDebugButtonsState({ canStart: true, canStep: false, canContinue: false, canStop: false });
    const hint = document.getElementById('debugStatusLabel');
    if (hint) hint.textContent = '';
  }

  _handleDebugState(data) {
    // 增量打印本次新增的解释器日志, 避免每次调用都重复刷屏全量 stdout
    const fullStdout = data.stdout || '';
    const newText = fullStdout.slice(this.debugLoggedStdoutLen);
    this.debugLoggedStdoutLen = fullStdout.length;
    if (newText.trim()) {
      this.logToConsole(newText.replace(/\n+$/, ''), data.success === false ? 'error' : 'meta');
    }

    this.debugCurrentLine = data.current_line || null;
    this.updateLineNumbers();
    this.renderWatchTable(data.control_vars || {});
    this.renderIconicVarPills(data.iconic_vars || [], data.display_target);
    this.renderControlVars(data.control_var_list || []);
    this.renderWindowPills(data.windows || []);

    const reasonText = {
      ready: `✅ 调试就绪，共 ${data.total_instructions} 条指令，暂停于第 ${data.current_line} 行`,
      step: `⏭️ 已执行 1 条指令，暂停于第 ${data.current_line ?? '末尾'} 行`,
      breakpoint: `🔴 命中断点，暂停于第 ${data.current_line} 行`,
      max_steps: '⚠️ 已达单次续跑步数上限，暂停执行',
      finished: '🏁 脚本执行完毕',
      error: `❌ 第 ${data.current_line ?? '?'} 行执行出错`
    }[data.stopped_reason] || '';
    if (reasonText) this.logToConsole(reasonText, data.stopped_reason === 'error' ? 'error' : 'success');

    const hint = document.getElementById('debugStatusLabel');
    if (hint) hint.textContent = reasonText;

    if (typeof this.onResult === 'function') {
      this.onResult(data);
    }

    if (data.finished) {
      this._setDebugButtonsState({ canStart: true, canStep: false, canContinue: false, canStop: false });
    }
  }

  renderWatchTable(controlVars) {
    const body = document.getElementById('debugWatchBody');
    if (!body) return;
    const entries = Object.entries(controlVars || {});
    if (entries.length === 0) {
      body.innerHTML = '<tr><td colspan="2" style="color:var(--text-muted);font-style:italic;">暂无控制变量</td></tr>';
      return;
    }
    const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    body.innerHTML = entries.map(([k, v]) => `<tr><td style="color:var(--neon-cyan);">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
  }

  renderControlVars(vars) {
    const body = document.getElementById('hdevCtrlBody');
    if (!body) return;
    const countEl = document.getElementById('hdevCtrlCount');
    if (countEl) countEl.textContent = vars && vars.length ? `${vars.length} 个` : '';
    body.innerHTML = '';

    if (!vars || vars.length === 0) {
      const row = body.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 2;
      cell.className = 'ctrl-var-empty';
      cell.textContent = '暂无控制变量';
      return;
    }

    vars.forEach(v => {
      const row = body.insertRow();
      const nameCell = row.insertCell();
      nameCell.className = 'ctrl-var-name';
      nameCell.textContent = v.name;
      nameCell.title = v.type === 'tuple' ? `${v.name} (tuple, ${v.length} 个元素)` : `${v.name} (${v.type})`;
      const valueCell = row.insertCell();
      valueCell.className = 'ctrl-var-value';
      valueCell.textContent = v.value;
      valueCell.title = v.value;
    });
  }

  renderIconicVarPills(vars, activeTarget) {
    const pillsContainer = document.getElementById('hdevVarPills');
    if (!pillsContainer) return;
    pillsContainer.innerHTML = '';
    const countEl = document.getElementById('hdevVarCount');
    if (countEl) countEl.textContent = vars && vars.length ? `${vars.length} 个` : '';

    if (!vars || vars.length === 0) {
      pillsContainer.innerHTML = '<span class="var-window-empty">无输出变量</span>';
      return;
    }

    vars.forEach(v => {
      const card = document.createElement('button');
      card.className = `var-card ${v.name === activeTarget ? 'active' : ''}`;
      card.title = `${v.name} (${v.type})`;

      const thumb = document.createElement('div');
      thumb.className = 'var-card-thumb';
      if (v.thumbnail) {
        const img = document.createElement('img');
        img.src = v.thumbnail;
        img.alt = v.name;
        thumb.appendChild(img);
      } else {
        thumb.textContent = v.type;
      }

      let meta = v.type;
      if (v.type === 'Image' && v.shape) {
        meta = `${v.shape[1]}×${v.shape[0]}`;
      } else if (v.type === 'Region') {
        meta = `${v.area} px`;
      } else if (v.type === 'XLD' && v.contour_count !== undefined) {
        meta = `${v.contour_count} XLD`;
      }

      const name = document.createElement('div');
      name.className = 'var-card-name';
      name.textContent = v.name;
      const info = document.createElement('div');
      info.className = 'var-card-meta';
      info.textContent = meta;

      card.append(thumb, name, info);
      card.addEventListener('click', () => {
        this.currentDisplayTarget = v.name;
        this.runScript();
      });

      pillsContainer.appendChild(card);
    });
  }

  renderWindowPills(windows) {
    const barEl = document.getElementById('hdevWindowBar');
    const pillsContainer = document.getElementById('hdevWindowPills');
    if (!barEl || !pillsContainer) return;
    pillsContainer.innerHTML = '';

    if (!windows || windows.length < 2) {
      barEl.style.display = 'none';
      return;
    }
    barEl.style.display = 'flex';

    windows.forEach(w => {
      const pill = document.createElement('button');
      pill.className = `btn btn-secondary ${w.active ? 'active' : ''}`;
      pill.style.padding = '2px 8px';
      pill.style.fontSize = '11px';
      pill.style.borderRadius = '12px';
      pill.style.cursor = 'pointer';
      pill.textContent = w.label || `窗口 #${w.handle}`;
      if (w.active) {
        pill.style.borderColor = 'var(--neon-cyan)';
        pill.style.color = 'var(--neon-cyan)';
      }

      pill.addEventListener('click', () => {
        pillsContainer.querySelectorAll('button').forEach(b => {
          b.classList.remove('active');
          b.style.borderColor = '';
          b.style.color = '';
        });
        pill.classList.add('active');
        pill.style.borderColor = 'var(--neon-cyan)';
        pill.style.color = 'var(--neon-cyan)';
        if (typeof this.onWindowSelect === 'function') {
          this.onWindowSelect(w);
        }
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
