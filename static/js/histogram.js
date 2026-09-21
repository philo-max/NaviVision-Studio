/**
 * NaviVision Studio - Interactive 256-Bin Grayscale Histogram
 * 绘制灰度分布直方图，支持在波形图上直接鼠标拖拽 MinGray / MaxGray 双阈值游标
 */

class InteractiveHistogram {
  constructor(canvasEl, onChangeCallback) {
    this.canvas = canvasEl;
    this.ctx = canvasEl.getContext('2d');
    this.onChange = onChangeCallback;

    this.histogramData = new Array(256).fill(0);
    this.minVal = 0;
    this.maxVal = 128;
    this.activeDragging = null; // 'min' | 'max' | null

    this.initEvents();
  }

  initEvents() {
    this.canvas.addEventListener('mousedown', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const grayPos = Math.round((clickX / rect.width) * 255);

      // 判断离 min 还是 max 更近
      const distMin = Math.abs(grayPos - this.minVal);
      const distMax = Math.abs(grayPos - this.maxVal);

      if (distMin < 15 && distMin <= distMax) {
        this.activeDragging = 'min';
      } else if (distMax < 15) {
        this.activeDragging = 'max';
      } else {
        // 点击空白处直接移动较近的游标
        if (grayPos < (this.minVal + this.maxVal) / 2) {
          this.minVal = Math.max(0, Math.min(grayPos, this.maxVal));
          this.activeDragging = 'min';
        } else {
          this.maxVal = Math.min(255, Math.max(grayPos, this.minVal));
          this.activeDragging = 'max';
        }
        this.emitChange();
      }
      this.draw();
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.activeDragging) return;
      const rect = this.canvas.getBoundingClientRect();
      const clickX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
      const grayPos = Math.round((clickX / rect.width) * 255);

      if (this.activeDragging === 'min') {
        this.minVal = Math.max(0, Math.min(grayPos, this.maxVal));
      } else if (this.activeDragging === 'max') {
        this.maxVal = Math.min(255, Math.max(grayPos, this.minVal));
      }
      this.draw();
      this.emitChange();
    });

    window.addEventListener('mouseup', () => {
      this.activeDragging = null;
    });
  }

  setData(data = []) {
    if (data && data.length === 256) {
      this.histogramData = data;
    }
    this.draw();
  }

  setThresholds(minV, maxV) {
    this.minVal = Math.max(0, Math.min(255, parseInt(minV)));
    this.maxVal = Math.max(0, Math.min(255, parseInt(maxV)));
    this.draw();
  }

  emitChange() {
    if (typeof this.onChange === 'function') {
      this.onChange(this.minVal, this.maxVal);
    }
  }

  draw() {
    const w = this.canvas.width = this.canvas.clientWidth * window.devicePixelRatio;
    const h = this.canvas.height = this.canvas.clientHeight * window.devicePixelRatio;
    this.ctx.clearRect(0, 0, w, h);

    if (!this.histogramData || this.histogramData.length === 0) return;

    const tokens = getComputedStyle(document.documentElement);
    const token = (name) => tokens.getPropertyValue(name).trim();
    const colorAccent = token('--accent');
    const colorDanger = token('--danger');

    const maxCount = Math.max(...this.histogramData, 1);
    const barWidth = w / 256;

    // 1. 绘制背景区域与阈值高亮区间
    const minPx = (this.minVal / 255) * w;
    const maxPx = (this.maxVal / 255) * w;

    this.ctx.fillStyle = token('--accent-soft');
    this.ctx.fillRect(minPx, 0, maxPx - minPx, h);

    // 2. 绘制直方图柱体/折线
    for (let i = 0; i < 256; i++) {
      const val = this.histogramData[i];
      const barH = (val / maxCount) * (h - 10);
      const x = i * barWidth;
      const y = h - barH;

      // 在区间内的柱子使用主色，区间外变淡
      if (i >= this.minVal && i <= this.maxVal) {
        this.ctx.fillStyle = colorAccent;
      } else {
        this.ctx.fillStyle = token('--border-bright');
      }
      this.ctx.fillRect(x, y, Math.max(1, barWidth), barH);
    }

    // 3. 绘制 Min 游标 (主色)
    this.ctx.strokeStyle = colorAccent;
    this.ctx.lineWidth = 2 * window.devicePixelRatio;
    this.ctx.beginPath();
    this.ctx.moveTo(minPx, 0);
    this.ctx.lineTo(minPx, h);
    this.ctx.stroke();

    // 4. 绘制 Max 游标 (警示色)
    this.ctx.strokeStyle = colorDanger;
    this.ctx.lineWidth = 2 * window.devicePixelRatio;
    this.ctx.beginPath();
    this.ctx.moveTo(maxPx, 0);
    this.ctx.lineTo(maxPx, h);
    this.ctx.stroke();

    // 绘制游标数值标签
    this.ctx.font = `${10 * window.devicePixelRatio}px monospace`;
    this.ctx.fillStyle = colorAccent;
    this.ctx.fillText(`Min: ${this.minVal}`, Math.min(minPx + 4, w - 80), 14 * window.devicePixelRatio);
    this.ctx.fillStyle = colorDanger;
    this.ctx.fillText(`Max: ${this.maxVal}`, Math.max(maxPx - 60, 4), h - 6);
  }
}
