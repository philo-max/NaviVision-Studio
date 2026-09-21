/**
 * NaviVision Studio - High Performance Multi-Layer Viewport
 * 支持无级缩放、自由平移、图层独立开关、亚像素矢量轮廓、及像素级十字丝探测 HUD
 */

class StudioViewport {
  constructor(containerEl) {
    this.container = containerEl;
    this.stage = containerEl.classList?.contains('viewport-stage') ? containerEl : (containerEl.querySelector('.viewport-stage') || containerEl);
    
    // Canvas 图层
    this.imageCanvas = document.getElementById('imageCanvas');
    this.maskCanvas = document.getElementById('maskCanvas');
    this.vectorCanvas = document.getElementById('vectorCanvas');
    
    this.ctxImg = this.imageCanvas.getContext('2d');
    this.ctxMask = this.maskCanvas.getContext('2d');
    this.ctxVec = this.vectorCanvas.getContext('2d');

    // 变换状态
    this.scale = 1.0;
    this.offsetX = 0;
    this.offsetY = 0;
    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartY = 0;

    // 图层可见性与透明度
    this.showImage = true;
    this.showMask = true;
    this.showContours = true;
    this.showBBoxes = true;
    this.maskOpacity = 0.65;

    // 数据缓存
    this.imgWidth = 640;
    this.imgHeight = 480;
    this.baseImage = null;
    this.maskImage = null;
    this.contours = [];
    this.objects = [];
    this.highlightObjId = null;

    // ROI 交互绘制状态
    this.roiMode = null;         // null | 'rect' | 'circle' | 'polygon'
    this.roiGeometry = null;     // 已完成的 ROI 几何描述
    this.roiPoints = [];         // 多边形绘制过程中的顶点
    this._roiStart = null;       // 拖拽起点 (图像坐标)
    this._roiCurrent = null;     // 拖拽当前点 (图像坐标)
    this.onRoiComplete = null;   // 回调: (geometry) => void

    // HUD 元素
    this.hudCoord = document.getElementById('hudCoord');
    this.hudPixel = document.getElementById('hudPixel');
    this.hudRegion = document.getElementById('hudRegion');

    this.initEvents();
  }

  initEvents() {
    // 鼠标拖拽平移
    this.stage.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return; // 仅左键
      // ROI 绘制模式: 拦截左键, 不触发平移
      if (this.roiMode) {
        const p = this._stageToImage(e);
        if (this.roiMode === 'polygon') {
          this.roiPoints.push([p.x, p.y]);
          this.redrawContours();
          this._vertexModeArmed = true;
        } else {
          this._roiStart = p;
          this._roiCurrent = p;
        }
        return;
      }
      this.isDragging = true;
      this.dragStartX = e.clientX - this.offsetX;
      this.dragStartY = e.clientY - this.offsetY;
    });

    window.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        this.offsetX = e.clientX - this.dragStartX;
        this.offsetY = e.clientY - this.dragStartY;
        this.applyTransform();
      }
      if (this.roiMode && (this.roiMode === 'rect' || this.roiMode === 'circle') && this._roiStart) {
        this._roiCurrent = this._stageToImage(e);
        this.redrawContours();
      }
      this.updateCursorHUD(e);
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
      if (this.roiMode && this.roiMode !== 'polygon' && this._roiStart && this._roiCurrent) {
        this._finalizeRoiDrag();
      }
    });

    // 滚轮缩放 (以鼠标指针为中心缩放)
    this.stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = this.stage.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      const newScale = Math.min(Math.max(0.1, this.scale * zoomFactor), 20.0);

      this.offsetX = mouseX - (mouseX - this.offsetX) * (newScale / this.scale);
      this.offsetY = mouseY - (mouseY - this.offsetY) * (newScale / this.scale);
      this.scale = newScale;

      this.applyTransform();
    });

    // 窗口尺寸变化
    window.addEventListener('resize', () => {
      this.fitToWindow();
    });
  }

  applyTransform() {
    const transform = `translate(${this.offsetX}px, ${this.offsetY}px) scale(${this.scale})`;
    this.imageCanvas.style.transform = transform;
    this.maskCanvas.style.transform = transform;
    this.vectorCanvas.style.transform = transform;

    const zoomIndicator = document.getElementById('hudZoom');
    if (zoomIndicator) {
      zoomIndicator.textContent = `${Math.round(this.scale * 100)}%`;
    }
  }

  fitToWindow() {
    if (!this.imgWidth || !this.imgHeight) return;
    const stageW = this.stage.clientWidth;
    const stageH = this.stage.clientHeight;

    const scaleX = (stageW - 60) / this.imgWidth;
    const scaleY = (stageH - 60) / this.imgHeight;
    this.scale = Math.min(scaleX, scaleY, 1.5);

    this.offsetX = (stageW - this.imgWidth * this.scale) / 2;
    this.offsetY = (stageH - this.imgHeight * this.scale) / 2;
    this.applyTransform();
  }

  resetZoom() {
    this.scale = 1.0;
    const stageW = this.stage.clientWidth;
    const stageH = this.stage.clientHeight;
    this.offsetX = (stageW - this.imgWidth) / 2;
    this.offsetY = (stageH - this.imgHeight) / 2;
    this.applyTransform();
  }

  setDimensions(w, h) {
    this.imgWidth = w;
    this.imgHeight = h;
    [this.imageCanvas, this.maskCanvas, this.vectorCanvas].forEach(c => {
      c.width = w;
      c.height = h;
    });
  }

  renderImage(imgSrc) {
    const img = new Image();
    img.onload = () => {
      this.baseImage = img;
      this.setDimensions(img.width, img.height);
      this.ctxImg.clearRect(0, 0, img.width, img.height);
      if (this.showImage) {
        this.ctxImg.drawImage(img, 0, 0);
      }
      this.fitToWindow();
    };
    img.src = imgSrc;
  }

  renderMask(maskSrc, objects = []) {
    this.objects = objects;
    if (!maskSrc) {
      this.ctxMask.clearRect(0, 0, this.imgWidth, this.imgHeight);
      this.maskImage = null;
      return;
    }
    const mask = new Image();
    mask.onload = () => {
      this.maskImage = mask;
      this.redrawMask();
    };
    mask.src = maskSrc;
  }

  redrawMask() {
    this.ctxMask.clearRect(0, 0, this.imgWidth, this.imgHeight);
    if (!this.showMask || !this.maskImage) return;

    this.ctxMask.globalAlpha = this.maskOpacity;
    this.ctxMask.drawImage(this.maskImage, 0, 0);
    this.ctxMask.globalAlpha = 1.0;

    // 绘制连通域外接矩形与中心十字
    if (this.showBBoxes && this.objects && this.objects.length > 0) {
      this.ctxMask.lineWidth = 1.5;
      this.ctxMask.font = '11px monospace';
      
      this.objects.forEach(obj => {
        const [y1, x1, y2, x2] = obj.bbox;
        const w = x2 - x1;
        const h = y2 - y1;
        
        const isTarget = (this.highlightObjId === obj.id);
        this.ctxMask.strokeStyle = isTarget ? '#ff3366' : 'rgba(0, 240, 255, 0.7)';
        this.ctxMask.fillStyle = isTarget ? '#ff3366' : 'rgba(0, 240, 255, 0.9)';
        
        this.ctxMask.strokeRect(x1, y1, w, h);
        this.ctxMask.fillText(`#${obj.id}`, x1 + 2, y1 - 4);

        // 绘制质心
        if (obj.centroid) {
          const cy = obj.centroid[0];
          const cx = obj.centroid[1];
          this.ctxMask.beginPath();
          this.ctxMask.arc(cx, cy, 3, 0, Math.PI * 2);
          this.ctxMask.fill();
        }
      });
    }
  }

  renderContours(contours = []) {
    this.contours = contours;
    this.redrawContours();
  }

  redrawContours() {
    this.ctxVec.clearRect(0, 0, this.imgWidth, this.imgHeight);
    this._drawRoiOverlay();
    if (!this.showContours || !this.contours || this.contours.length === 0) return;

    this.ctxVec.lineWidth = 1.5;
    this.ctxVec.strokeStyle = '#ffb800'; // 亚像素轮廓琥珀金
    this.ctxVec.shadowColor = 'rgba(255, 184, 0, 0.8)';
    this.ctxVec.shadowBlur = 4;

    this.contours.forEach(cnt => {
      if (cnt.length < 2) return;
      this.ctxVec.beginPath();
      this.ctxVec.moveTo(cnt[0][0], cnt[0][1]);
      for (let i = 1; i < cnt.length; i++) {
        this.ctxVec.lineTo(cnt[i][0], cnt[i][1]);
      }
      this.ctxVec.stroke();
    });
    this.ctxVec.shadowBlur = 0;
  }

  updateCursorHUD(e) {
    const rect = this.stage.getBoundingClientRect();
    const stageX = e.clientX - rect.left;
    const stageY = e.clientY - rect.top;

    // 变换为图像局部像素坐标
    const imgX = Math.floor((stageX - this.offsetX) / this.scale);
    const imgY = Math.floor((stageY - this.offsetY) / this.scale);

    if (imgX >= 0 && imgX < this.imgWidth && imgY >= 0 && imgY < this.imgHeight) {
      if (this.hudCoord) this.hudCoord.textContent = `X: ${imgX}, Y: ${imgY}`;
      
      try {
        const pixel = this.ctxImg.getImageData(imgX, imgY, 1, 1).data;
        const gray = Math.round(0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2]);
        if (this.hudPixel) {
          this.hudPixel.textContent = `RGB: (${pixel[0]}, ${pixel[1]}, ${pixel[2]}) | Gray: ${gray}`;
        }
        
        // 检查 Mask 图层对应位置
        const maskPixel = this.ctxMask.getImageData(imgX, imgY, 1, 1).data;
        const inMask = maskPixel[3] > 0;
        if (this.hudRegion) {
          this.hudRegion.textContent = inMask ? 'ACTIVE REGION' : 'BACKGROUND';
          this.hudRegion.style.color = inMask ? 'var(--neon-cyan)' : 'var(--text-muted)';
        }
      } catch (err) {
        // ImageData 安全保护
      }
    }
  }

  highlightObject(id) {
    this.highlightObjId = id;
    this.redrawMask();
  }

  // ---------------- ROI 交互 ----------------
  _stageToImage(e) {
    const rect = this.stage.getBoundingClientRect();
    const x = ((e.clientX - rect.left) - this.offsetX) / this.scale;
    const y = ((e.clientY - rect.top) - this.offsetY) / this.scale;
    return { x: Math.max(0, Math.min(this.imgWidth, x)), y: Math.max(0, Math.min(this.imgHeight, y)) };
  }

  setRoiMode(mode) {
    this.roiMode = (this.roiMode === mode) ? null : mode;
    this.roiPoints = [];
    this._roiStart = null;
    this._roiCurrent = null;
    this.stage.style.cursor = this.roiMode ? 'crosshair' : 'grab';
    this.redrawContours();
    return this.roiMode;
  }

  clearRoi() {
    this.roiGeometry = null;
    this.roiPoints = [];
    this._roiStart = null;
    this._roiCurrent = null;
    this.redrawContours();
    if (this.onRoiComplete) this.onRoiComplete(null);
  }

  _finalizeRoiDrag() {
    const a = this._roiStart, b = this._roiCurrent;
    const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
    const w = Math.abs(b.x - a.x), h = Math.abs(b.y - a.y);
    if (this.roiMode === 'circle') {
      const r = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y));
      this.roiGeometry = { type: 'circle', cx: Math.round(a.x), cy: Math.round(a.y), r: Math.round(r) };
    } else if (w >= 2 && h >= 2) {
      this.roiGeometry = { type: 'rect', x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
    } else {
      this.roiGeometry = null;
    }
    this.roiMode = null;
    this._roiStart = null;
    this._roiCurrent = null;
    this.stage.style.cursor = 'grab';
    this.redrawContours();
    if (this.roiGeometry && this.onRoiComplete) this.onRoiComplete(this.roiGeometry);
  }

  finishPolygon() {
    if (this.roiPoints.length >= 3) {
      this.roiGeometry = { type: 'polygon', points: this.roiPoints.map(pt => [Math.round(pt[0]), Math.round(pt[1])]) };
      if (this.onRoiComplete) this.onRoiComplete(this.roiGeometry);
    }
    this.roiMode = null;
    this.roiPoints = [];
    this.stage.style.cursor = 'grab';
    this.redrawContours();
  }

  _drawRoiOverlay() {
    const ctx = this.ctxVec;
    ctx.save();
    ctx.lineWidth = 1.5 / this.scale;
    ctx.strokeStyle = '#ff2fd0';
    ctx.setLineDash([6 / this.scale, 4 / this.scale]);

    const drawGeom = (g) => {
      if (!g) return;
      ctx.beginPath();
      if (g.type === 'rect') {
        ctx.rect(g.x, g.y, g.w, g.h);
      } else if (g.type === 'circle') {
        ctx.arc(g.cx, g.cy, g.r, 0, Math.PI * 2);
      } else if (g.type === 'polygon' && g.points) {
        g.points.forEach((pt, i) => { if (i === 0) ctx.moveTo(pt[0], pt[1]); else ctx.lineTo(pt[0], pt[1]); });
        ctx.closePath();
      }
      ctx.stroke();
    };

    if (this.roiGeometry) drawGeom(this.roiGeometry);

    if (this._roiStart && this._roiCurrent) {
      const a = this._roiStart, b = this._roiCurrent;
      if (this.roiMode === 'circle') {
        const r = Math.hypot(b.x - a.x, b.y - a.y);
        ctx.beginPath(); ctx.arc(a.x, a.y, r, 0, Math.PI * 2); ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.rect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
        ctx.stroke();
      }
    }

    if (this.roiMode === 'polygon' && this.roiPoints.length) {
      ctx.beginPath();
      this.roiPoints.forEach((pt, i) => { if (i === 0) ctx.moveTo(pt[0], pt[1]); else ctx.lineTo(pt[0], pt[1]); });
      ctx.stroke();
      ctx.setLineDash([]);
      this.roiPoints.forEach(pt => {
        ctx.beginPath(); ctx.arc(pt[0], pt[1], 3 / this.scale, 0, Math.PI * 2); ctx.fillStyle = '#ff2fd0'; ctx.fill();
      });
    }
    ctx.restore();
  }
}
