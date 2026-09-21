/**
 * NaviVision Studio - Main App Entry Point
 * 协调 Viewport, PipelineUI, API 通信, 代码生成器与全局快捷键
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. 初始化 Viewport
  const viewportStage = document.getElementById('viewportStage');
  const viewport = new StudioViewport(viewportStage);

  // 2. 初始化 Pipeline UI
  const pipelineListEl = document.getElementById('pipelineList');
  const inspectorContentEl = document.getElementById('inspectorContent');

  let currentSamples = [];
  let currentResults = [];

  // 0. 多租户会话 ID 管理
  let sessionId = localStorage.getItem('navivision_session_id');
  if (!sessionId) {
    sessionId = 'sess_' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    localStorage.setItem('navivision_session_id', sessionId);
  }

  async function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (!(options.body instanceof FormData)) {
      options.headers['Content-Type'] = options.headers['Content-Type'] || 'application/json';
    }
    options.headers['X-Session-ID'] = sessionId;
    return fetch(url, options);
  }

  const pipelineUI = new PipelineUI(pipelineListEl, inspectorContentEl, async (steps) => {
    // 步骤或参数发生变更，上报服务端执行重算
    try {
      const t0 = performance.now();
      const resp = await apiFetch('/api/pipeline/update', {
        method: 'POST',
        body: JSON.stringify({ steps })
      });
      const data = await resp.json();
      if (data.success) {
        currentResults = data.results;
        pipelineUI.updateResults(currentResults);
        updateViewportFromActiveStep();
        updateObjectTable();

        const latency = Math.round(performance.now() - t0);
        const fpsEl = document.getElementById('hudLatency');
        if (fpsEl) fpsEl.textContent = `${latency}ms`;
      }
    } catch (err) {
      console.error('Pipeline update failed:', err);
    }
  });

  pipelineUI.onSelectCallback = (step, res) => {
    updateViewportFromActiveStep();
    updateObjectTable();
  };

  // 3. 根据当前激活步骤刷新视口与空工作区状态
  const emptyStateEl = document.getElementById('emptyState');
  function syncEmptyState() {
    if (emptyStateEl) {
      emptyStateEl.hidden = currentResults.length > 0 || !!viewport.baseImage;
    }
  }
  const btnEmptyOpen = document.getElementById('btnEmptyOpen');
  if (btnEmptyOpen) {
    btnEmptyOpen.addEventListener('click', () => {
      document.getElementById('uploadInput').click();
    });
  }

  function updateViewportFromActiveStep() {
    syncEmptyState();
    const step = pipelineUI.getActiveStep();
    const res = pipelineUI.getActiveResult();
    if (!res) return;

    // 底图
    const readStepRes = currentResults.find(r => r.operator === 'read_image');
    if (readStepRes && readStepRes.preview_base64) {
      if (!viewport.baseImage) {
        viewport.renderImage(readStepRes.preview_base64);
      }
    }

    // 检查 Mask 掩膜与对象列表
    const objects = res.summary?.objects || res.summary?.objects_info || [];
    if (res.mask_base64) {
      viewport.renderMask(res.mask_base64, objects);
    } else {
      // 若当前步骤不是 Region 产出，查找最近的前置 Region 步骤显示
      const lastRegionRes = [...currentResults].reverse().find(r => r.mask_base64);
      if (lastRegionRes) {
        viewport.renderMask(lastRegionRes.mask_base64, lastRegionRes.summary?.objects || []);
      } else {
        viewport.renderMask(null);
      }
    }

    // 检查 XLD 亚像素轮廓
    if (res.contours && res.contours.length > 0) {
      viewport.renderContours(res.contours);
    } else {
      const lastXld = [...currentResults].reverse().find(r => r.contours && r.contours.length > 0);
      viewport.renderContours(lastXld ? lastXld.contours : []);
    }
  }

  // 4. 更新特征数据表 (Tab 2)
  function updateObjectTable() {
    const tableBody = document.getElementById('objectTableBody');
    const tableContainer = document.getElementById('tableContainer');
    if (!tableBody) return;

    // 查找包含对象列表的最近结果
    const targetRes = [...currentResults].reverse().find(r => r.summary?.objects || r.summary?.objects_info);
    const objects = targetRes?.summary?.objects || targetRes?.summary?.objects_info || [];

    const countBadge = document.getElementById('tabObjCount');
    if (countBadge) countBadge.textContent = `(${objects.length})`;

    if (objects.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px;">当前步骤无连通域对象</td></tr>';
      return;
    }

    let html = '';
    objects.forEach(obj => {
      const circ = obj.circularity !== undefined ? obj.circularity : 'N/A';
      const centroidStr = obj.centroid ? `(${obj.centroid[0]}, ${obj.centroid[1]})` : 'N/A';
      html += `
        <tr data-obj-id="${obj.id}">
          <td style="color:var(--neon-cyan);font-weight:bold;">#${obj.id}</td>
          <td>${obj.area}</td>
          <td>${circ}</td>
          <td>${centroidStr}</td>
          <td style="font-size:10px;color:var(--text-muted);">${obj.bbox ? `[${obj.bbox.join(',')}]` : ''}</td>
        </tr>
      `;
    });
    tableBody.innerHTML = html;

    // 表格行点击高亮对应连通域
    tableBody.querySelectorAll('tr').forEach(row => {
      row.addEventListener('mouseenter', () => {
        const id = parseInt(row.dataset.objId);
        viewport.highlightObject(id);
      });
      row.addEventListener('mouseleave', () => {
        viewport.highlightObject(null);
      });
    });
  }

  // 5. 恢复会话流水线 (若已有会话)
  async function restoreSession() {
    try {
      const exported = await (await apiFetch('/api/project/export')).json();
      if (!Array.isArray(exported.steps) || exported.steps.length === 0) return;

      const resp = await apiFetch('/api/project/import', {
        method: 'POST',
        body: JSON.stringify({ steps: exported.steps })
      });
      const data = await resp.json();
      if (data.success) {
        currentResults = data.results;
        viewport.baseImage = null;
        pipelineUI.setPipelineData(data.steps, data.results);
        updateViewportFromActiveStep();
        updateObjectTable();
      }
    } catch (err) {
      console.error('Failed to restore session:', err);
    }
  }

  // 6. 本地图片上传
  const uploadInput = document.getElementById('uploadInput');
  document.getElementById('btnUpload').addEventListener('click', () => {
    uploadInput.click();
  });
  uploadInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const resp = await apiFetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      if (data.success) {
        currentResults = data.results;
        viewport.baseImage = null;
        pipelineUI.setPipelineData(data.steps, data.results);
        updateViewportFromActiveStep();
        updateObjectTable();
      } else {
        alert('图片上传失败: ' + (data.detail || data.error || '未知错误'));
      }
    } catch (err) {
      alert('图片上传失败: ' + err);
    }
  });

  const batchInput = document.getElementById('batchInput');
  const btnBatchInspect = document.getElementById('btnBatchInspect');
  btnBatchInspect.addEventListener('click', () => batchInput.click());
  batchInput.addEventListener('change', async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('rules', JSON.stringify({ min_objects: 1 }));
    btnBatchInspect.disabled = true;
    btnBatchInspect.textContent = '⏳ 检测中...';

    try {
      const response = await apiFetch('/api/v1/batch-predict', { method: 'POST', body: formData });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.detail || data.error || '批量检测失败');

      const report = await apiFetch('/api/report/csv', {
        method: 'POST',
        body: JSON.stringify({ records: data.records })
      });
      if (!report.ok) throw new Error('检测完成，但报告导出失败');
      const url = URL.createObjectURL(await report.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `navivision_report_${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
      alert(`批量检测完成：${data.summary.total} 张，合格 ${data.summary.passed}，不合格 ${data.summary.failed}，异常 ${data.summary.errors}。报告已下载。`);
    } catch (err) {
      alert('批量检测失败: ' + err.message);
    } finally {
      btnBatchInspect.disabled = false;
      btnBatchInspect.textContent = '🏭 批量检测';
      batchInput.value = '';
    }
  });

  // 7. 添加算子下拉菜单
  const btnAddOp = document.getElementById('btnAddOp');
  const addOpMenu = document.getElementById('addOpMenu');
  btnAddOp.addEventListener('click', (e) => {
    e.stopPropagation();
    addOpMenu.style.display = (addOpMenu.style.display === 'block') ? 'none' : 'block';
  });
  document.addEventListener('click', () => {
    addOpMenu.style.display = 'none';
  });
  addOpMenu.querySelectorAll('button').forEach(btn => {
    btn.addEventListener('click', () => {
      const op = btn.dataset.op;
      pipelineUI.addStep(op);
      addOpMenu.style.display = 'none';
    });
  });

  // 8. 视口控制工具栏
  document.getElementById('btnZoomIn').addEventListener('click', () => {
    viewport.scale = Math.min(viewport.scale * 1.25, 20.0);
    viewport.applyTransform();
  });
  document.getElementById('btnZoomOut').addEventListener('click', () => {
    viewport.scale = Math.max(viewport.scale * 0.8, 0.1);
    viewport.applyTransform();
  });
  document.getElementById('btnZoomFit').addEventListener('click', () => {
    viewport.fitToWindow();
  });
  document.getElementById('btnZoom100').addEventListener('click', () => {
    viewport.resetZoom();
  });

  // 8b. ROI 绘制工具栏
  const _setRoiBtn = (activeMode) => {
    ['btnRoiRect', 'btnRoiCircle', 'btnRoiPoly'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('active', id === activeMode);
    });
  };
  document.getElementById('btnRoiRect').addEventListener('click', () => {
    const m = viewport.setRoiMode('rect'); _setRoiBtn(m === 'rect' ? 'btnRoiRect' : null);
  });
  document.getElementById('btnRoiCircle').addEventListener('click', () => {
    const m = viewport.setRoiMode('circle'); _setRoiBtn(m === 'circle' ? 'btnRoiCircle' : null);
  });
  document.getElementById('btnRoiPoly').addEventListener('click', () => {
    const m = viewport.setRoiMode('polygon'); _setRoiBtn(m === 'polygon' ? 'btnRoiPoly' : null);
  });
  document.getElementById('btnRoiClear').addEventListener('click', () => {
    viewport.clearRoi(); _setRoiBtn(null);
  });
  // 多边形: 双击 / Enter 闭合
  viewport.stage.addEventListener('dblclick', () => {
    if (viewport.roiMode === 'polygon') { viewport.finishPolygon(); _setRoiBtn(null); }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && viewport.roiMode === 'polygon') { viewport.finishPolygon(); _setRoiBtn(null); }
  });
  // ROI 绘制完成 -> 写入当前激活的 reduce_domain 步骤
  viewport.onRoiComplete = (geometry) => {
    const step = pipelineUI.steps.find(st => st.id === pipelineUI.activeStepId);
    if (step && step.operator === 'reduce_domain') {
      step.params = step.params || {};
      if (geometry) {
        step.params.geometry = geometry;
        step.params.roi_type = geometry.type;
      } else {
        delete step.params.geometry;
      }
      pipelineUI.renderInspector?.();
      pipelineUI.emitUpdateDebounced();
    }
  };

  // 图层开关
  document.getElementById('chkLayerImage').addEventListener('change', (e) => {
    viewport.showImage = e.target.checked;
    viewport.ctxImg.clearRect(0, 0, viewport.imgWidth, viewport.imgHeight);
    if (viewport.showImage && viewport.baseImage) {
      viewport.ctxImg.drawImage(viewport.baseImage, 0, 0);
    }
  });
  document.getElementById('chkLayerMask').addEventListener('change', (e) => {
    viewport.showMask = e.target.checked;
    viewport.redrawMask();
  });
  document.getElementById('chkLayerContours').addEventListener('change', (e) => {
    viewport.showContours = e.target.checked;
    viewport.redrawContours();
  });
  document.getElementById('chkLayerBBox').addEventListener('change', (e) => {
    viewport.showBBoxes = e.target.checked;
    viewport.redrawMask();
  });
  document.getElementById('rangeOpacity').addEventListener('input', (e) => {
    viewport.maskOpacity = parseFloat(e.target.value) / 100;
    viewport.redrawMask();
  });

  // 9. 右侧 Tab 切换
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabInspector = document.getElementById('tabInspector');
  const tabObjects = document.getElementById('tabObjects');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.dataset.tab;
      if (target === 'inspector') {
        tabInspector.style.display = 'flex';
        tabObjects.style.display = 'none';
      } else {
        tabInspector.style.display = 'none';
        tabObjects.style.display = 'flex';
      }
    });
  });

  // 10. 代码导出模态框 (Code Exporter)
  const codeModal = document.getElementById('codeModal');
  const codeViewer = document.getElementById('codeViewer');
  const btnExportCode = document.getElementById('btnExportCode');
  const btnCloseModal = document.getElementById('btnCloseModal');
  const btnCopyCode = document.getElementById('btnCopyCode');
  const btnDownloadPy = document.getElementById('btnDownloadPy');

  btnExportCode.addEventListener('click', async () => {
    try {
      const resp = await apiFetch('/api/pipeline/export', {
        method: 'POST',
        body: JSON.stringify({ steps: pipelineUI.steps })
      });
      const data = await resp.json();
      if (data.success) {
        codeViewer.textContent = data.code;
        codeModal.classList.add('open');
      }
    } catch (err) {
      alert('导出代码失败: ' + err);
    }
  });

  btnCloseModal.addEventListener('click', () => {
    codeModal.classList.remove('open');
  });

  btnCopyCode.addEventListener('click', async () => {
    await navigator.clipboard.writeText(codeViewer.textContent);
    btnCopyCode.textContent = '✅ 已复制到剪贴板！';
    setTimeout(() => {
      btnCopyCode.textContent = '📋 复制代码';
    }, 2000);
  });

  btnDownloadPy.addEventListener('click', () => {
    const blob = new Blob([codeViewer.textContent], { type: 'text/x-python' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'navivision_pipeline.py';
    a.click();
    URL.revokeObjectURL(url);
  });

  // 导出 HDevelop (.hdev) 脚本
  const btnExportHdev = document.getElementById('btnExportHdev');
  if (btnExportHdev) {
    btnExportHdev.addEventListener('click', async () => {
      try {
        const resp = await apiFetch('/api/hdev/from_pipeline', {
          method: 'POST',
          body: JSON.stringify({ format: 'plain' })
        });
        const data = await resp.json();
        if (data.success) {
          const blob = new Blob([data.code], { type: 'text/plain;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'navivision_script.hdev';
          a.click();
          URL.revokeObjectURL(url);
        }
      } catch (err) {
        alert('导出 HDevelop 脚本失败: ' + err);
      }
    });
  }

  // 导入 HDevelop (.hdev / .hdvp) 脚本
  const btnUploadHdev = document.getElementById('btnUploadHdev');
  const hdevFileInput = document.getElementById('hdevFileInput');
  if (btnUploadHdev && hdevFileInput) {
    btnUploadHdev.addEventListener('click', () => {
      hdevFileInput.click();
    });
    hdevFileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        const resp = await fetch('/api/hdev/upload', {
          method: 'POST',
          body: formData
        });
        const data = await resp.json();
        if (data.success) {
          btnModeCode.click();
          const langSelect = document.getElementById('codeLangSelect');
          if (langSelect) {
            langSelect.value = 'hdev';
            codeEditor.updateLanguageUI('hdev');
          }
          codeEditor.editor.value = data.code;
          codeEditor.updateLineNumbers();
          codeEditor.logToConsole(`[✓] 成功载入外部 HDevelop 脚本 '${data.filename}' (共 ${data.instruction_count} 条有效指令)`, 'success');
          codeEditor.runScript();
        }
      } catch (err) {
        alert('导入并解析 .hdev 文件失败: ' + err);
      } finally {
        hdevFileInput.value = '';
      }
    });
  }

  // 监听 HDevelop 脚本转译同步到流水线事件
  window.addEventListener('navivision:pipeline-synced', (e) => {
    const data = e.detail;
    if (data && data.steps) {
      pipelineUI.steps = data.steps;
      pipelineUI.renderSteps();
      if (data.results) {
        currentResults = data.results;
        updateDisplay();
      }
      btnModePipeline.click();
    }
  });

  // 11. 初始化交互式代码工作室 (Code Mode)
  const scriptEditorEl = document.getElementById('scriptEditor');
  const lineNumbersEl = document.getElementById('editorLineNumbers');
  const terminalLogsEl = document.getElementById('terminalLogs');

  const codeEditor = new InteractiveCodeEditor(scriptEditorEl, lineNumbersEl, terminalLogsEl, (result) => {
    // 脚本沙箱返回结果，投射到 Viewport
    if (result.preview_base64) {
      viewport.renderImage(result.preview_base64);
    }
    if (result.mask_base64) {
      viewport.renderMask(result.mask_base64, result.objects || []);
    }
    if (result.contours && result.contours.length > 0) {
      viewport.renderContours(result.contours);
    }
    if (result.objects && result.objects.length > 0) {
      const tableBody = document.getElementById('objectTableBody');
      const countBadge = document.getElementById('tabObjCount');
      if (countBadge) countBadge.textContent = `(${result.objects.length})`;
      if (tableBody) {
        let html = '';
        result.objects.forEach(obj => {
          const circ = obj.circularity !== undefined ? obj.circularity : 'N/A';
          const centroidStr = obj.centroid ? `(${Math.round(obj.centroid[0])}, ${Math.round(obj.centroid[1])})` : 'N/A';
          html += `
            <tr data-obj-id="${obj.id}">
              <td style="color:var(--neon-cyan);font-weight:bold;">#${obj.id}</td>
              <td>${obj.area}</td>
              <td>${circ}</td>
              <td>${centroidStr}</td>
              <td style="font-size:10px;color:var(--text-muted);">${obj.bbox ? `[${obj.bbox.join(',')}]` : ''}</td>
            </tr>
          `;
        });
        tableBody.innerHTML = html;
      }
    }
  });

  // 运行代码按钮
  document.getElementById('btnRunScript').addEventListener('click', () => {
    codeEditor.runScript();
  });

  // 模板切换
  document.getElementById('codeTemplateSelect').addEventListener('change', (e) => {
    codeEditor.loadTemplate(e.target.value);
  });

  // 清屏按钮
  document.getElementById('btnClearTerminal').addEventListener('click', () => {
    codeEditor.clearConsole();
  });

  // 模式切换: 流水线 vs 代码工作室
  const btnModePipeline = document.getElementById('btnModePipeline');
  const btnModeCode = document.getElementById('btnModeCode');
  const panelPipeline = document.getElementById('panelPipeline');
  const panelCodeStudio = document.getElementById('panelCodeStudio');

  btnModePipeline.addEventListener('click', () => {
    btnModePipeline.classList.add('active');
    btnModeCode.classList.remove('active');
    panelPipeline.style.display = 'flex';
    panelCodeStudio.style.display = 'none';
  });

  btnModeCode.addEventListener('click', () => {
    btnModeCode.classList.add('active');
    btnModePipeline.classList.remove('active');
    panelPipeline.style.display = 'none';
    panelCodeStudio.style.display = 'flex';
    codeEditor.updateLineNumbers();
  });

  // 12. 开放 API 接入中心模态框
  const apiModal = document.getElementById('apiModal');
  const btnOpenApiHub = document.getElementById('btnOpenApiHub');
  const btnCloseApiModal = document.getElementById('btnCloseApiModal');
  const btnCloseApiModalBtn = document.getElementById('btnCloseApiModalBtn');

  btnOpenApiHub.addEventListener('click', () => {
    apiModal.classList.add('open');
  });
  btnCloseApiModal.addEventListener('click', () => {
    apiModal.classList.remove('open');
  });
  btnCloseApiModalBtn.addEventListener('click', () => {
    apiModal.classList.remove('open');
  });

  // 13. 视觉工程持久化 (.nvproj) 导出与导入
  const btnSaveProject = document.getElementById('btnSaveProject');
  const btnOpenProject = document.getElementById('btnOpenProject');
  const projectFileInput = document.getElementById('projectFileInput');

  if (btnSaveProject) {
    btnSaveProject.addEventListener('click', async () => {
      try {
        const resp = await apiFetch('/api/project/export');
        const data = await resp.json();
        const jsonStr = JSON.stringify(data, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        a.download = `navivision_project_${timestamp}.nvproj`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (err) {
        alert('导出工程失败: ' + err);
      }
    });
  }

  if (btnOpenProject && projectFileInput) {
    btnOpenProject.addEventListener('click', () => {
      projectFileInput.click();
    });

    projectFileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async (event) => {
        try {
          const projectData = JSON.parse(event.target.result);
          if (!projectData.steps || !Array.isArray(projectData.steps)) {
            alert('无效的工程文件：未找到 steps 步骤配置列表！');
            return;
          }
          const resp = await apiFetch('/api/project/import', {
            method: 'POST',
            body: JSON.stringify({ steps: projectData.steps })
          });
          const data = await resp.json();
          if (data.success) {
            currentResults = data.results;
            pipelineUI.setPipelineData(data.steps, data.results);
            updateViewportFromActiveStep();
            updateObjectTable();
            alert(`视觉工程恢复成功！共加载 ${data.steps.length} 个算子步骤。`);
          } else {
            alert('导入工程失败: ' + (data.error || '未知错误'));
          }
        } catch (err) {
          alert('解析工程文件失败: ' + err);
        } finally {
          projectFileInput.value = '';
        }
      };
      reader.readAsText(file);
    });
  }

  // 启动: 空工作区, 若服务端会话已有流水线则恢复
  syncEmptyState();
  restoreSession();
});
