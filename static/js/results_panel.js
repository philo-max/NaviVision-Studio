/**
 * 结果面板 (视口下方停靠): 目标特征表 + 识别结果 (OCR)
 * 负责表格渲染 / 列排序 / 汇总统计 / CSV 导出 / 折叠与拖拽调高
 */
const DOCK_STORAGE_KEY = 'navivision_results_dock';
const DOCK_DEFAULT_HEIGHT = 240;
const DOCK_MIN_HEIGHT = 120;
const DOCK_MAX_RATIO = 0.7;
const DOCK_HEADER_HEIGHT = 38;

const fmtNum = (digits) => (v) => (v === undefined || v === null ? '—' : Number(v).toFixed(digits));
const fmtPair = (v) => (v ? `${Math.round(v[0])}, ${Math.round(v[1])}` : '—');
const fmtBox = (v) => (v ? `[${v.join(', ')}]` : '—');

const OBJECT_COLUMNS = [
  { key: 'id', label: 'ID', fmt: (v) => `#${v}`, cls: 'col-id' },
  { key: 'area', label: '面积 (px)', fmt: (v) => v, num: true },
  { key: 'circularity', label: '圆度', fmt: fmtNum(3), num: true },
  { key: 'rectangularity', label: '矩形度', fmt: fmtNum(3), num: true },
  { key: 'aspect_ratio', label: '长宽比', fmt: fmtNum(2), num: true },
  { key: 'centroid', label: '质心 (Y, X)', fmt: fmtPair, sortBy: (o) => (o.centroid ? o.centroid[0] : null) },
  { key: 'bbox', label: '外接框 [Y1, X1, Y2, X2]', fmt: fmtBox, cls: 'col-dim', sortBy: (o) => (o.bbox ? o.bbox[0] : null) },
];

const OCR_COLUMNS = [
  { key: 'index', label: '序号', fmt: (v) => v, num: true },
  { key: 'char', label: '字符', fmt: (v) => v, cls: 'col-char' },
  { key: 'confidence', label: '置信度', fmt: (v) => v, num: true, bar: true },
  { key: 'centroid', label: '位置 (Y, X)', fmt: fmtPair, sortBy: (o) => (o.centroid ? o.centroid[1] : null) },
  { key: 'bbox', label: '外接框 [Y1, X1, Y2, X2]', fmt: fmtBox, cls: 'col-dim', sortBy: (o) => (o.bbox ? o.bbox[1] : null) },
  { key: 'area', label: '面积 (px)', fmt: (v) => v, num: true },
];

class ResultsPanel {
  constructor(root, { onHighlight } = {}) {
    this.root = root;
    this.onHighlight = onHighlight || (() => {});
    this.data = { objects: [], ocr: null };
    this.sort = { objects: null, ocr: null };
    this.activePane = 'objects';
    this.state = this.loadState();
    this.els = {
      body: root.querySelector('.dock-body'),
      summary: root.querySelector('#dockSummary'),
      objCount: root.querySelector('#dockObjCount'),
      ocrCount: root.querySelector('#dockOcrCount'),
      objTable: root.querySelector('#objectResultTable'),
      ocrTable: root.querySelector('#ocrResultTable'),
      ocrText: root.querySelector('#ocrText'),
      ocrMeta: root.querySelector('#ocrMeta'),
      toggle: root.querySelector('#btnDockToggle'),
    };
    this.bindEvents();
    this.applyLayout();
    this.render();
  }

  loadState() {
    try {
      const saved = JSON.parse(localStorage.getItem(DOCK_STORAGE_KEY) || '{}');
      return { height: saved.height || DOCK_DEFAULT_HEIGHT, collapsed: !!saved.collapsed };
    } catch (e) {
      return { height: DOCK_DEFAULT_HEIGHT, collapsed: false };
    }
  }

  saveState() {
    try {
      localStorage.setItem(DOCK_STORAGE_KEY, JSON.stringify(this.state));
    } catch (e) { /* 存储不可用时忽略, 面板仍可正常使用 */ }
  }

  bindEvents() {
    this.root.querySelectorAll('.dock-tab').forEach((btn) => {
      btn.addEventListener('click', () => this.showPane(btn.dataset.pane));
    });
    this.els.toggle.addEventListener('click', () => this.setCollapsed(!this.state.collapsed));
    this.root.querySelector('#btnDockExport').addEventListener('click', () => this.exportCsv());
    this.bindResizer(this.root.querySelector('#dockResizer'));
  }

  bindResizer(handle) {
    handle.addEventListener('pointerdown', (e) => {
      if (this.state.collapsed) return;
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      const startY = e.clientY;
      const startHeight = this.state.height;
      const maxHeight = this.root.parentElement.clientHeight * DOCK_MAX_RATIO;
      const onMove = (ev) => {
        this.state.height = Math.max(DOCK_MIN_HEIGHT, Math.min(maxHeight, startHeight + startY - ev.clientY));
        this.applyLayout();
      };
      const onUp = () => {
        handle.removeEventListener('pointermove', onMove);
        handle.removeEventListener('pointerup', onUp);
        this.saveState();
      };
      handle.addEventListener('pointermove', onMove);
      handle.addEventListener('pointerup', onUp);
    });
  }

  applyLayout() {
    const { collapsed, height } = this.state;
    this.root.classList.toggle('collapsed', collapsed);
    this.root.style.height = `${collapsed ? DOCK_HEADER_HEIGHT : height}px`;
    this.els.toggle.textContent = collapsed ? '▴' : '▾';
    this.els.toggle.title = collapsed ? '展开结果面板' : '折叠结果面板';
    window.dispatchEvent(new Event('resize'));
  }

  setCollapsed(collapsed) {
    this.state.collapsed = collapsed;
    this.applyLayout();
    this.saveState();
  }

  showPane(name) {
    this.activePane = name;
    this.root.querySelectorAll('.dock-tab').forEach((b) => b.classList.toggle('active', b.dataset.pane === name));
    this.root.querySelectorAll('.dock-pane').forEach((p) => { p.hidden = p.dataset.pane !== name; });
    this.renderSummary();
    if (this.state.collapsed) this.setCollapsed(false);
  }

  setObjects(objects) {
    this.data.objects = Array.isArray(objects) ? objects : [];
    this.renderObjects();
    this.renderSummary();
  }

  setOcr(ocr) {
    this.data.ocr = ocr && ocr.chars && ocr.chars.length ? ocr : null;
    this.renderOcr();
    this.renderSummary();
    if (this.data.ocr) this.showPane('ocr');
    else if (this.activePane === 'ocr') this.showPane('objects');
  }

  render() {
    this.renderObjects();
    this.renderOcr();
    this.renderSummary();
  }

  sortedRows(name, columns) {
    const rows = name === 'objects' ? this.data.objects : (this.data.ocr ? this.data.ocr.chars : []);
    const s = this.sort[name];
    if (!s) return rows;
    const col = columns.find((c) => c.key === s.key);
    const valueOf = (r) => (col.sortBy ? col.sortBy(r) : r[col.key]);
    return [...rows].sort((a, b) => {
      const x = valueOf(a);
      const y = valueOf(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x > y ? 1 : -1) * s.dir;
    });
  }

  renderTable(table, name, columns, emptyHint) {
    const rows = this.sortedRows(name, columns);
    const s = this.sort[name];
    const head = columns.map((c) => {
      const arrow = s && s.key === c.key ? (s.dir === 1 ? ' ▲' : ' ▼') : '';
      return `<th data-key="${c.key}" class="${c.num ? 'num' : ''}">${c.label}${arrow}</th>`;
    }).join('');
    const body = rows.length === 0
      ? `<tr><td class="empty" colspan="${columns.length}">${emptyHint}</td></tr>`
      : rows.map((r) => `<tr data-id="${r.id ?? ''}">${columns.map((c) => this.cell(c, r)).join('')}</tr>`).join('');
    table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
    table.querySelectorAll('th').forEach((th) => th.addEventListener('click', () => {
      const key = th.dataset.key;
      const cur = this.sort[name];
      this.sort[name] = cur && cur.key === key ? (cur.dir === 1 ? { key, dir: -1 } : null) : { key, dir: 1 };
      this.render();
    }));
  }

  cell(col, row) {
    const raw = row[col.key];
    const text = raw === undefined || raw === null ? '—' : col.fmt(raw);
    if (col.bar && raw !== undefined && raw !== null) {
      return `<td class="num"><span class="conf-bar"><i style="width:${Math.round(raw * 100)}%"></i></span>${(raw * 100).toFixed(0)}%</td>`;
    }
    return `<td class="${[col.num ? 'num' : '', col.cls || ''].join(' ')}">${text}</td>`;
  }

  renderObjects() {
    this.renderTable(this.els.objTable, 'objects', OBJECT_COLUMNS, '当前步骤没有连通域对象');
    this.els.objCount.textContent = this.data.objects.length;
    this.els.objTable.querySelectorAll('tbody tr[data-id]').forEach((tr) => {
      const id = parseInt(tr.dataset.id, 10);
      tr.addEventListener('mouseenter', () => this.onHighlight(id));
      tr.addEventListener('mouseleave', () => this.onHighlight(null));
    });
  }

  renderOcr() {
    const ocr = this.data.ocr;
    this.renderTable(this.els.ocrTable, 'ocr', OCR_COLUMNS, '运行含 do_ocr_multi_class_mlp 的脚本后显示识别结果');
    this.els.ocrCount.textContent = ocr ? ocr.chars.length : 0;
    this.els.ocrText.textContent = ocr ? ocr.text : '—';
    this.els.ocrMeta.textContent = ocr ? `${ocr.chars.length} 个字符 · 平均置信度 ${(ocr.mean_confidence * 100).toFixed(1)}%` : '尚无识别结果';
  }

  renderSummary() {
    const chips = [];
    if (this.activePane === 'objects') {
      const areas = this.data.objects.map((o) => o.area).filter((a) => typeof a === 'number');
      chips.push(['目标数', this.data.objects.length]);
      if (areas.length) {
        chips.push(['面积均值', Math.round(areas.reduce((a, b) => a + b, 0) / areas.length)]);
        chips.push(['最小', Math.min(...areas)], ['最大', Math.max(...areas)]);
      }
    } else if (this.data.ocr) {
      chips.push(['字符数', this.data.ocr.chars.length], ['平均置信度', `${(this.data.ocr.mean_confidence * 100).toFixed(1)}%`]);
    }
    this.els.summary.innerHTML = chips.map(([k, v]) => `<span class="chip"><em>${k}</em>${v}</span>`).join('');
  }

  exportCsv() {
    const isObjects = this.activePane === 'objects';
    const columns = isObjects ? OBJECT_COLUMNS : OCR_COLUMNS;
    const rows = this.sortedRows(isObjects ? 'objects' : 'ocr', columns);
    if (rows.length === 0) return;
    const cell = (c, r) => {
      const v = r[c.key];
      if (v === undefined || v === null) return '';
      return Array.isArray(v) ? `"${v.join(' ')}"` : String(v);
    };
    const lines = [columns.map((c) => c.label).join(',')].concat(rows.map((r) => columns.map((c) => cell(c, r)).join(',')));
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = isObjects ? 'objects.csv' : 'ocr_result.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }
}
