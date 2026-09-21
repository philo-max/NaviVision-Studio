# NaviVision Studio (OpenDevelop) 机器视觉平台

<p align="center">
  <b>轻量级交互式机器视觉 IDE · HALCON / HDevelop 开源平替架构</b><br>
  涵盖算子流水线编排、真·亚像素轮廓插值、工业几何度量、子进程安全沙箱与多租户会话隔离
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python 3.12">
  <img src="https://img.shields.io/badge/FastAPI-0.100%2B-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/tests-13%2F13%20passing-brightgreen" alt="Tests passing">
</p>

---

## 目录结构

```text
f:\计算机视觉\
├── app.py                     # FastAPI 服务端核心入口 (REST API / 页面挂载 / 会话路由)
├── requirements.txt           # Python 依赖包清单
├── test_core.py               # 核心算法与引擎自动化测试套件 (13 项全量断言)
├── .gitignore                 # Git 忽略配置
├── README.md                  # 项目架构与使用说明
│
├── core/                      # 视觉处理核心模块包
│   ├── __init__.py            # 包导出入口
│   ├── operators.py           # HALCON 平替核心算子库 (真亚像素边缘/几何度量/二值化/形态学等)
│   ├── pipeline.py            # 级联指纹缓存流水线执行引擎
│   ├── session_manager.py     # 多租户会话隔离管理器 (SessionManager)
│   ├── script_runner.py       # 安全脚本执行器 (AST 静态审查 + 3.0s 超时熔断)
│   ├── script_worker.py       # 独立子进程 Worker 执行沙箱
│   ├── code_generator.py      # 独立 Python / OpenCV 代码自动生成器
│   ├── api_service.py         # 外部工业推理服务调度器
│   └── types.py               # 核心数据结构定义 (Region, RegionObject, XLDContour, StepResult)
│
├── static/                    # 前端 Web IDE 交互界面
│   ├── index.html             # 单页面应用入口
│   ├── css/
│   │   ├── theme.css          # Cyberpunk / Obsidian 风格设计系统与离线字体栈
│   │   └── style.css          # 布局与三栏式工作区样式
│   └── js/
│       ├── app.js             # 主交互编排与会话/工程管理
│       ├── pipeline_ui.js     # 流水线步骤卡片渲染与参数调优面板
│       ├── viewport.js        # Canvas 高性能矢量视口 (无级缩放/图层叠加/轮廓绘制)
│       ├── code_editor.js     # 在线 Python 代码编辑器与虚拟终端
│       └── histogram.js       # 256 级灰度直方图可视化
│
└── docs/                      # 理论参考与课程资料
    ├── 第二章 数字图像基础.pdf
    └── 第三章 了解和熟悉HALCON.pdf
```

---

## 核心特性与架构亮点

### 1. 智能级联指纹增量缓存 (`core/pipeline.py`)
- 每个步骤采用级联哈希计算步骤指纹：
  $$H_i = \text{SHA256}(H_{i-1} + \text{operator} + \text{params} + \text{enabled})$$
- 上游参数被修改时，下游过时缓存瞬间熔断失效，调参即时响应；未变步骤 0ms 复用。

### 2. 真·亚像素边缘插值 (`edges_subpix`)
- 抛弃整像素类型强转假象，基于 **Steger / Facet Model** 实现 Sobel 梯度法向二次抛物线三点插值：
  $$t^* = \frac{M(-1) - M(+1)}{2(M(-1) - 2M(0) + M(+1))}$$
- 产出真浮点坐标 XLD 轮廓（亚像素位移达 0.1~0.8px），精确累加欧氏折线弧长。

### 3. 工业级几何度量算子 (`measure_region`)
- 输出完整工业特征：
  - **最小外接旋转矩形 (OBB / `smallest_rectangle2`)**：中心、主副半长、倾角与 4 角点绝对坐标。
  - **最小外接圆 (`smallest_circle`)**：圆心与外接圆半径。
  - **二阶惯性矩与主轴 (`elliptic_axis`)**：基于中心矩计算主惯性方向与长短轴。
  - **凸度 (Convexity)** 与 **紧致度 (Compactness)**。

### 4. 真实子进程安全沙箱 (`core/script_runner.py`)
- **AST 静态安全审查**：禁止导入危险系统/网络模块（`os`, `sys`, `subprocess`, `shutil`, `socket` 等），禁止探测 `__subclasses__` 等私有反射属性。
- **独立子进程隔离与 3.0s 超时熔断**：主进程独立拉起子进程，一旦出现 `while True` 等死循环，3.0s 强制强杀子进程并回收资源，主服务绝不挂死。

### 5. 多租户会话隔离 (`SessionManager`)
- 移除全局单例 `pipeline`，通过 `X-Session-ID` 路由多实例。多个浏览器标签页或客户端各自拥有独立的图像与算子栈，互不覆盖。

### 6. 视觉工程持久化 (`.nvproj`)
- 支持一键导出/导入 `.nvproj` JSON 工程文件，随时保存并无缝复现流水线参数与处理结果。
### 7. 图像平滑滤波算子 (`filter`)
- 补齐 HALCON 经典的图像预处理能力，对标 `mean_image` / `gauss_filter` / `median_image`：
  - **均值滤波 (Mean)**：快速抑制高斯噪声，计算开销最低。
  - **高斯滤波 (Gaussian)**：各向同性保边平滑，可调核大小与标准差 `sigma`。
  - **中值滤波 (Median)**：对椒盐/脉冲噪声最有效，同时保留边缘锐度。
- 输出保持与原图一致的尺寸与数据类型，可直接级联到阈值分割、亚像素边缘等下游算子。

---

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动服务
```bash
python app.py
```
启动后在浏览器中访问：**[http://127.0.0.1:8080](http://127.0.0.1:8080)**

### 3. 运行全量核心测试套件
```bash
python test_core.py
```

### 4. 构建 Windows 应用程序
```powershell
.\build_windows.ps1
```
构建完成后运行 `dist\NaviVisionStudio\NaviVisionStudio.exe`，再访问 [http://127.0.0.1:8080](http://127.0.0.1:8080)。发布时需保留整个 `NaviVisionStudio` 文件夹及其 `_internal` 子目录。

在线脚本执行默认关闭；它只适合受信任的本机开发环境。确需启用时，先设置 `NAVIVISION_ENABLE_SCRIPT_RUNNER=1`，再启动应用。

### 5. 批量检测与报告
在工作台先配置流水线，再点击“批量检测”选择最多 25 张图像。系统按当前流水线执行检测，以目标数不少于 1 为默认合格规则，并自动下载 CSV 检测报告。外部系统可调用 `POST /api/v1/batch-predict`，以 multipart 的 `files` 字段传图，并用 `rules` 字段传入 JSON 规则，例如 `{"min_objects": 1, "max_objects": 20}`。

---

## 算子映射表 (HALCON 对标)

| NaviVision Studio 算子 | HALCON 对标算子 | 作用说明 |
| :--- | :--- | :--- |
| `read_image` | `read_image` | 读取本地工业相机图片或上传图像矩阵 |
| `rgb1_to_gray` | `rgb1_to_gray` | 彩色图转单通道灰度图并提取直方图 |
| `threshold` | `threshold` | 经典双阈值灰度分割提取二值区域 |
| `auto_threshold` | `auto_threshold (Otsu)` | 大津法自适应双峰全局最佳分割 |
| `connection` | `connection` | 打散独立连通域并提取基础外接矩形与面积 |
| `select_shape` | `select_shape` | 按面积、圆度、长宽比等多维度筛选合格目标 |
| `morphology` | `dilation / erosion / opening / closing` | 形态学膨胀、腐蚀、开运算降噪、闭运算填孔 |
| `filter` | `mean_image / gauss_filter / median_image` | 图像平滑滤波：均值、高斯、中值去噪，作为分割前的噪声抑制预处理 |
| `edges_subpix` | `edges_subpix` | 梯度法向二次抛物线真亚像素 XLD 轮廓提取 |
| `measure_region` | `measure_region / smallest_rectangle2` | 提取旋转外接矩形 OBB、外接圆、二阶矩主轴与凸度 |
