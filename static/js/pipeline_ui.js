/**
 * NaviVision Studio - Pipeline UI Controller
 * 管理算子流水线步骤列表、步骤拖拽排序、增删算子、及右侧参数检查器 (Inspector) 动态表单
 */

class PipelineUI {
  constructor(listContainerEl, inspectorContainerEl, onUpdateCallback) {
    this.listEl = listContainerEl;
    this.inspectorEl = inspectorContainerEl;
    this.onUpdate = onUpdateCallback;

    this.steps = [];
    this.results = [];
    this.activeStepId = null;
    this.histogramComponent = null;

    this.updateDebounceTimer = null;
  }

  setPipelineData(steps, results = []) {
    this.steps = steps;
    this.results = results;
    if (!this.activeStepId && this.steps.length > 0) {
      this.activeStepId = this.steps[this.steps.length - 1].id;
    }
    this.renderStepList();
    this.renderInspector();
  }

  updateResults(results = []) {
    this.results = results;
    this.renderStepList();
    this.renderInspector();
  }

  getActiveStep() {
    return this.steps.find(s => s.id === this.activeStepId) || this.steps[0];
  }

  getActiveResult() {
    return this.results.find(r => r.step_id === this.activeStepId) || this.results[this.results.length - 1];
  }

  renderStepList() {
    this.listEl.innerHTML = '';
    const stepCountEl = document.getElementById('stepCountBadge');
    if (stepCountEl) stepCountEl.textContent = `${this.steps.length} 算子`;

    this.steps.forEach((step, idx) => {
      const res = this.results.find(r => r.step_id === step.id);
      const isActive = (step.id === this.activeStepId);
      const isEnabled = step.enabled !== false;

      const card = document.createElement('div');
      card.className = `step-card ${isActive ? 'active' : ''} ${!isEnabled ? 'disabled' : ''}`;
      card.dataset.id = step.id;

      const opIcons = {
        'read_image': '📥',
        'rgb1_to_gray': '🌓',
        'threshold': '🎚️',
        'auto_threshold': '🪄',
        'connection': '🧩',
        'select_shape': '🎯',
        'morphology': '🔬',
        'filter': '🧹',
        'edges_subpix': '〰️',
        'measure_region': '📐'
      };

      const durationText = res ? `${res.duration_ms}ms` : '...';
      const outputType = res ? res.output_type : (step.operator === 'edges_subpix' ? 'xld' : 'region');

      card.innerHTML = `
        <div class="step-card-header">
          <div class="step-info">
            <span class="step-idx">${idx + 1}</span>
            <span>${opIcons[step.operator] || '⚙️'}</span>
            <span class="step-title">${step.operator}</span>
          </div>
          <div class="step-actions">
            <button class="icon-btn toggle-btn" title="${isEnabled ? '禁用' : '启用'}">
              ${isEnabled ? '👁️' : '👁️‍🗨️'}
            </button>
            ${step.operator !== 'read_image' ? `
              <button class="icon-btn danger delete-btn" title="删除">🗑️</button>
            ` : ''}
          </div>
        </div>
        <div class="step-card-footer">
          <span class="step-timing">⚡ ${durationText}</span>
          <span class="step-type-badge">${outputType}</span>
        </div>
      `;

      // 点击选中卡片
      card.addEventListener('click', (e) => {
        if (e.target.closest('.step-actions')) return;
        this.activeStepId = step.id;
        this.renderStepList();
        this.renderInspector();
        if (typeof this.onSelectCallback === 'function') {
          this.onSelectCallback(this.getActiveStep(), this.getActiveResult());
        }
      });

      // 启用/禁用切换
      const toggleBtn = card.querySelector('.toggle-btn');
      toggleBtn.addEventListener('click', () => {
        step.enabled = !isEnabled;
        this.emitUpdate();
      });

      // 删除步骤
      const delBtn = card.querySelector('.delete-btn');
      if (delBtn) {
        delBtn.addEventListener('click', () => {
          this.steps = this.steps.filter(s => s.id !== step.id);
          if (this.activeStepId === step.id) {
            this.activeStepId = this.steps[this.steps.length - 1]?.id || null;
          }
          this.emitUpdate();
        });
      }

      this.listEl.appendChild(card);
    });
  }

  renderInspector() {
    const step = this.getActiveStep();
    const res = this.getActiveResult();
    if (!step) {
      this.inspectorEl.innerHTML = '<div style="color:var(--text-muted);font-size:13px;">请选择一个算子步骤</div>';
      return;
    }

    const p = step.params || (step.params = {});
    let html = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
        <h4 style="font-size:14px;color:var(--neon-cyan);display:flex;align-items:center;gap:6px;">
          <span>⚙️</span> ${step.operator} 参数设定
        </h4>
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);">${step.id}</span>
      </div>
    `;

    // 根据具体算子渲染参数控件
    if (step.operator === 'threshold') {
      const minG = p.min_gray !== undefined ? p.min_gray : 0;
      const maxG = p.max_gray !== undefined ? p.max_gray : 128;
      html += `
        <div class="control-group">
          <div class="histogram-container">
            <div class="histogram-header">
              <span>交互式灰度直方图 (可直接在波形上拖拽双游标)</span>
              <span id="histRangeText">${minG} ~ ${maxG}</span>
            </div>
            <div class="histogram-canvas-wrapper">
              <canvas id="histCanvas"></canvas>
            </div>
          </div>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>MinGray (最小灰度下限)</span>
            <span class="control-val" id="lblMinGray">${minG}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderMinGray" min="0" max="255" value="${minG}">
            <input type="number" id="numMinGray" min="0" max="255" value="${minG}">
          </div>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>MaxGray (最大灰度上限)</span>
            <span class="control-val" id="lblMaxGray">${maxG}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderMaxGray" min="0" max="255" value="${maxG}">
            <input type="number" id="numMaxGray" min="0" max="255" value="${maxG}">
          </div>
        </div>
      `;
    } else if (step.operator === 'auto_threshold') {
      const inv = p.invert || false;
      html += `
        <div class="control-group">
          <div class="control-label">
            <span>自适应算法</span>
            <span class="control-val">Otsu 大津双峰法</span>
          </div>
          <label style="font-size:13px;display:flex;align-items:center;gap:8px;margin-top:6px;cursor:pointer;">
            <input type="checkbox" id="chkInvert" ${inv ? 'checked' : ''}> 反相二值化 (Invert Mask)
          </label>
        </div>
      `;
    } else if (step.operator === 'connection') {
      const conn = p.connectivity || 8;
      html += `
        <div class="control-group">
          <div class="control-label">
            <span>拓扑邻域连通度 (Connectivity)</span>
            <span class="control-val">${conn}-连通</span>
          </div>
          <div style="display:flex;gap:12px;margin-top:8px;">
            <label style="font-size:13px;cursor:pointer;display:flex;align-items:center;gap:4px;">
              <input type="radio" name="radConn" value="4" ${conn === 4 ? 'checked' : ''}> 4-邻接
            </label>
            <label style="font-size:13px;cursor:pointer;display:flex;align-items:center;gap:4px;">
              <input type="radio" name="radConn" value="8" ${conn === 8 ? 'checked' : ''}> 8-邻接 (消除对角断裂)
            </label>
          </div>
        </div>
      `;
    } else if (step.operator === 'select_shape') {
      const minA = p.min_area !== undefined ? p.min_area : 20;
      const maxA = p.max_area !== undefined ? p.max_area : 100000;
      const minC = p.min_circularity !== undefined ? p.min_circularity : 0.0;
      const maxC = p.max_circularity !== undefined ? p.max_circularity : 1.0;

      html += `
        <div class="control-group">
          <div class="control-label">
            <span>Min Area (最小面积像素数)</span>
            <span class="control-val" id="lblMinArea">${minA}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderMinArea" min="0" max="10000" step="10" value="${minA}">
            <input type="number" id="numMinArea" min="0" max="1000000" value="${minA}">
          </div>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>Max Area (最大面积像素数)</span>
            <span class="control-val" id="lblMaxArea">${maxA}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderMaxArea" min="100" max="50000" step="100" value="${maxA}">
            <input type="number" id="numMaxArea" min="100" max="1000000" value="${maxA}">
          </div>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>Min Circularity (最小圆度 0~1)</span>
            <span class="control-val" id="lblMinCirc">${minC}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderMinCirc" min="0.0" max="1.0" step="0.02" value="${minC}">
            <input type="number" id="numMinCirc" min="0.0" max="1.0" step="0.05" value="${minC}">
          </div>
        </div>
      `;
    } else if (step.operator === 'morphology') {
      const opType = p.op_type || 'opening';
      const shape = p.kernel_shape || 'circle';
      const kSize = p.kernel_size || 5;

      html += `
        <div class="control-group">
          <div class="control-label">
            <span>运算类型 (Operation)</span>
            <span class="control-val">${opType}</span>
          </div>
          <select id="selMorphOp" style="width:100%;padding:6px;background:var(--bg-input);border:1px solid var(--border-bright);color:var(--text-main);border-radius:4px;margin-top:6px;">
            <option value="opening" ${opType === 'opening' ? 'selected' : ''}>Opening (开运算: 消除细微毛刺噪点)</option>
            <option value="closing" ${opType === 'closing' ? 'selected' : ''}>Closing (闭运算: 填补内部微小孔洞)</option>
            <option value="dilation" ${opType === 'dilation' ? 'selected' : ''}>Dilation (膨胀: 向外扩张区域)</option>
            <option value="erosion" ${opType === 'erosion' ? 'selected' : ''}>Erosion (腐蚀: 向内收缩边界)</option>
          </select>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>结构元形状 (Structuring Element)</span>
          </div>
          <select id="selMorphShape" style="width:100%;padding:6px;background:var(--bg-input);border:1px solid var(--border-bright);color:var(--text-main);border-radius:4px;margin-top:6px;">
            <option value="circle" ${shape === 'circle' ? 'selected' : ''}>Circle (圆形结构元)</option>
            <option value="rect" ${shape === 'rect' ? 'selected' : ''}>Rectangle (矩形结构元)</option>
            <option value="cross" ${shape === 'cross' ? 'selected' : ''}>Cross (十字结构元)</option>
          </select>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>核半径/大小 (Kernel Size)</span>
            <span class="control-val" id="lblKernelSize">${kSize}px</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderKernelSize" min="1" max="31" step="2" value="${kSize}">
            <input type="number" id="numKernelSize" min="1" max="99" step="2" value="${kSize}">
          </div>
        </div>
      `;
    } else if (step.operator === 'filter') {
      const fType = p.filter_type || 'gaussian';
      const kSize = p.kernel_size || 5;
      const sig = p.sigma !== undefined ? p.sigma : 1.5;

      html += `
        <div class="control-group">
          <div class="control-label">
            <span>滤波类型 (Filter Type)</span>
            <span class="control-val">${fType}</span>
          </div>
          <select id="selFilterType" style="width:100%;padding:6px;background:var(--bg-input);border:1px solid var(--border-bright);color:var(--text-main);border-radius:4px;margin-top:6px;">
            <option value="gaussian" ${fType === 'gaussian' ? 'selected' : ''}>Gaussian (高斯滤波: 保边平滑去噪)</option>
            <option value="mean" ${fType === 'mean' ? 'selected' : ''}>Mean (均值滤波: 快速抑制高斯噪声)</option>
            <option value="median" ${fType === 'median' ? 'selected' : ''}>Median (中值滤波: 椒盐脉冲噪声克星)</option>
          </select>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>卷积核大小 (Kernel Size)</span>
            <span class="control-val" id="lblFilterKernel">${kSize}px</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderFilterKernel" min="3" max="31" step="2" value="${kSize}">
            <input type="number" id="numFilterKernel" min="1" max="99" step="2" value="${kSize}">
          </div>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>高斯标准差 Sigma (仅高斯生效)</span>
            <span class="control-val" id="lblFilterSigma">${sig}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderFilterSigma" min="0" max="10" step="0.1" value="${sig}">
            <input type="number" id="numFilterSigma" min="0" max="50" step="0.1" value="${sig}">
          </div>
        </div>
      `;
    } else if (step.operator === 'edges_subpix') {
      const lowT = p.low_threshold || 30;
      const highT = p.high_threshold || 90;

      html += `
        <div class="control-group">
          <div class="control-label">
            <span>Canny Low Threshold</span>
            <span class="control-val" id="lblLowT">${lowT}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderLowT" min="5" max="200" value="${lowT}">
            <input type="number" id="numLowT" min="0" max="255" value="${lowT}">
          </div>
        </div>

        <div class="control-group">
          <div class="control-label">
            <span>Canny High Threshold</span>
            <span class="control-val" id="lblHighT">${highT}</span>
          </div>
          <div class="slider-row">
            <input type="range" id="sliderHighT" min="20" max="255" value="${highT}">
            <input type="number" id="numHighT" min="0" max="255" value="${highT}">
          </div>
        </div>
      `;
    } else {
      html += `
        <div class="control-group">
          <div style="font-size:12px;color:var(--text-muted);">此算子无需额外调节参数，直接产生输出。</div>
        </div>
      `;
    }

    // 统计摘要展示卡片
    if (res && res.summary) {
      html += `
        <div class="control-group" style="margin-top:12px;">
          <div class="control-label">
            <span>📊 算子输出遥测</span>
            <span class="control-val">${res.duration_ms}ms</span>
          </div>
          <pre style="font-family:var(--font-mono);font-size:11px;color:var(--neon-green);line-height:1.5;background:#06080e;padding:8px;border-radius:4px;overflow-x:auto;">${JSON.stringify(res.summary, null, 2)}</pre>
        </div>
      `;
    }

    this.inspectorEl.innerHTML = html;
    this.bindInspectorEvents(step);
  }

  bindInspectorEvents(step) {
    const p = step.params;

    if (step.operator === 'threshold') {
      const histCanvas = document.getElementById('histCanvas');
      const sliderMin = document.getElementById('sliderMinGray');
      const numMin = document.getElementById('numMinGray');
      const sliderMax = document.getElementById('sliderMaxGray');
      const numMax = document.getElementById('numMaxGray');
      const lblMin = document.getElementById('lblMinGray');
      const lblMax = document.getElementById('lblMaxGray');
      const histRangeText = document.getElementById('histRangeText');

      const syncThresholds = (minV, maxV) => {
        p.min_gray = minV;
        p.max_gray = maxV;
        sliderMin.value = numMin.value = lblMin.textContent = minV;
        sliderMax.value = numMax.value = lblMax.textContent = maxV;
        if (histRangeText) histRangeText.textContent = `${minV} ~ ${maxV}`;
        this.emitUpdateDebounced();
      };

      if (histCanvas) {
        this.histogramComponent = new InteractiveHistogram(histCanvas, (minV, maxV) => {
          syncThresholds(minV, maxV);
        });
        const res = this.getActiveResult();
        if (res && res.histogram) {
          this.histogramComponent.setData(res.histogram);
        }
        this.histogramComponent.setThresholds(p.min_gray, p.max_gray);
      }

      sliderMin.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        this.histogramComponent.setThresholds(val, p.max_gray);
        syncThresholds(val, p.max_gray);
      });
      numMin.addEventListener('change', (e) => {
        const val = parseInt(e.target.value);
        this.histogramComponent.setThresholds(val, p.max_gray);
        syncThresholds(val, p.max_gray);
      });

      sliderMax.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        this.histogramComponent.setThresholds(p.min_gray, val);
        syncThresholds(p.min_gray, val);
      });
      numMax.addEventListener('change', (e) => {
        const val = parseInt(e.target.value);
        this.histogramComponent.setThresholds(p.min_gray, val);
        syncThresholds(p.min_gray, val);
      });
    } else if (step.operator === 'auto_threshold') {
      const chk = document.getElementById('chkInvert');
      if (chk) {
        chk.addEventListener('change', (e) => {
          p.invert = e.target.checked;
          this.emitUpdate();
        });
      }
    } else if (step.operator === 'connection') {
      const radios = document.querySelectorAll('input[name="radConn"]');
      radios.forEach(r => {
        r.addEventListener('change', (e) => {
          p.connectivity = parseInt(e.target.value);
          this.emitUpdate();
        });
      });
    } else if (step.operator === 'select_shape') {
      const sMinA = document.getElementById('sliderMinArea');
      const nMinA = document.getElementById('numMinArea');
      const lMinA = document.getElementById('lblMinArea');
      sMinA.addEventListener('input', (e) => {
        p.min_area = parseInt(e.target.value);
        nMinA.value = lMinA.textContent = p.min_area;
        this.emitUpdateDebounced();
      });
      nMinA.addEventListener('change', (e) => {
        p.min_area = parseInt(e.target.value);
        sMinA.value = lMinA.textContent = p.min_area;
        this.emitUpdateDebounced();
      });

      const sMaxA = document.getElementById('sliderMaxArea');
      const nMaxA = document.getElementById('numMaxArea');
      const lMaxA = document.getElementById('lblMaxArea');
      sMaxA.addEventListener('input', (e) => {
        p.max_area = parseInt(e.target.value);
        nMaxA.value = lMaxA.textContent = p.max_area;
        this.emitUpdateDebounced();
      });
      nMaxA.addEventListener('change', (e) => {
        p.max_area = parseInt(e.target.value);
        sMaxA.value = lMaxA.textContent = p.max_area;
        this.emitUpdateDebounced();
      });

      const sMinC = document.getElementById('sliderMinCirc');
      const nMinC = document.getElementById('numMinCirc');
      const lMinC = document.getElementById('lblMinCirc');
      sMinC.addEventListener('input', (e) => {
        p.min_circularity = parseFloat(e.target.value);
        nMinC.value = lMinC.textContent = p.min_circularity;
        this.emitUpdateDebounced();
      });
      nMinC.addEventListener('change', (e) => {
        p.min_circularity = parseFloat(e.target.value);
        sMinC.value = lMinC.textContent = p.min_circularity;
        this.emitUpdateDebounced();
      });
    } else if (step.operator === 'morphology') {
      const selOp = document.getElementById('selMorphOp');
      const selShape = document.getElementById('selMorphShape');
      const sK = document.getElementById('sliderKernelSize');
      const nK = document.getElementById('numKernelSize');
      const lK = document.getElementById('lblKernelSize');

      selOp.addEventListener('change', (e) => {
        p.op_type = e.target.value;
        this.emitUpdate();
      });
      selShape.addEventListener('change', (e) => {
        p.kernel_shape = e.target.value;
        this.emitUpdate();
      });
      sK.addEventListener('input', (e) => {
        p.kernel_size = parseInt(e.target.value);
        nK.value = p.kernel_size;
        lK.textContent = `${p.kernel_size}px`;
        this.emitUpdateDebounced();
      });
      nK.addEventListener('change', (e) => {
        p.kernel_size = parseInt(e.target.value);
        sK.value = p.kernel_size;
        lK.textContent = `${p.kernel_size}px`;
        this.emitUpdateDebounced();
      });
    } else if (step.operator === 'filter') {
      const selF = document.getElementById('selFilterType');
      const sFK = document.getElementById('sliderFilterKernel');
      const nFK = document.getElementById('numFilterKernel');
      const lFK = document.getElementById('lblFilterKernel');
      const sFS = document.getElementById('sliderFilterSigma');
      const nFS = document.getElementById('numFilterSigma');
      const lFS = document.getElementById('lblFilterSigma');

      selF.addEventListener('change', (e) => {
        p.filter_type = e.target.value;
        this.emitUpdate();
      });
      sFK.addEventListener('input', (e) => {
        p.kernel_size = parseInt(e.target.value);
        nFK.value = p.kernel_size;
        lFK.textContent = `${p.kernel_size}px`;
        this.emitUpdateDebounced();
      });
      nFK.addEventListener('change', (e) => {
        p.kernel_size = parseInt(e.target.value);
        sFK.value = p.kernel_size;
        lFK.textContent = `${p.kernel_size}px`;
        this.emitUpdateDebounced();
      });
      sFS.addEventListener('input', (e) => {
        p.sigma = parseFloat(e.target.value);
        nFS.value = p.sigma;
        lFS.textContent = p.sigma;
        this.emitUpdateDebounced();
      });
      nFS.addEventListener('change', (e) => {
        p.sigma = parseFloat(e.target.value);
        sFS.value = p.sigma;
        lFS.textContent = p.sigma;
        this.emitUpdateDebounced();
      });
    } else if (step.operator === 'edges_subpix') {
      const sL = document.getElementById('sliderLowT');
      const nL = document.getElementById('numLowT');
      const lL = document.getElementById('lblLowT');
      const sH = document.getElementById('sliderHighT');
      const nH = document.getElementById('numHighT');
      const lH = document.getElementById('lblHighT');

      sL.addEventListener('input', (e) => {
        p.low_threshold = parseFloat(e.target.value);
        nL.value = lL.textContent = p.low_threshold;
        this.emitUpdateDebounced();
      });
      sH.addEventListener('input', (e) => {
        p.high_threshold = parseFloat(e.target.value);
        nH.value = lH.textContent = p.high_threshold;
        this.emitUpdateDebounced();
      });
    }
  }

  addStep(operator) {
    const newId = `s_${operator}_${Date.now().toString().slice(-4)}`;
    const defaultParams = {
      'threshold': { min_gray: 120, max_gray: 255 },
      'auto_threshold': { invert: false },
      'connection': { connectivity: 8 },
      'select_shape': { min_area: 50, max_area: 50000, min_circularity: 0.5 },
      'morphology': { op_type: 'opening', kernel_shape: 'circle', kernel_size: 5 },
      'filter': { filter_type: 'gaussian', kernel_size: 5, sigma: 1.5 },
      'edges_subpix': { low_threshold: 40, high_threshold: 100 },
      'measure_region': {}
    };

    const newStep = {
      id: newId,
      operator: operator,
      enabled: true,
      params: defaultParams[operator] || {}
    };

    this.steps.push(newStep);
    this.activeStepId = newId;
    this.emitUpdate();
  }

  emitUpdate() {
    if (typeof this.onUpdate === 'function') {
      this.onUpdate(this.steps);
    }
  }

  emitUpdateDebounced() {
    clearTimeout(this.updateDebounceTimer);
    this.updateDebounceTimer = setTimeout(() => {
      this.emitUpdate();
    }, 60);
  }
}
