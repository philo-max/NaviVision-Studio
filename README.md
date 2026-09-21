# NaviVision Studio (OpenDevelop) 机器视觉平台

<p align="center">
  <b>轻量级交互式机器视觉 IDE · HALCON / HDevelop 开源平替架构</b><br>
  涵盖算子流水线编排、多目标模板匹配、ROI 交互与卡尺测量、分支/多图流水线、子进程安全沙箱与多租户会话隔离
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python 3.12">
  <img src="https://img.shields.io/badge/FastAPI-0.100%2B-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/tests-13%2F13%20passing-brightgreen" alt="Tests passing">
  <img src="https://github.com/philo-max/NaviVision-Studio/actions/workflows/test.yml/badge.svg" alt="CI">
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
├── .github/workflows/test.yml # GitHub Actions CI (自动运行核心与 API 契约测试)
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
├── samples/                   # 预设工业测试用例与样本生成器
│   ├── generate_samples.py    # 合成样本数据生成脚本
│   ├── pills_inspection.png   # 药板药丸瑕疵检测样本 (带缺失/破损)
│   ├── pcb_components.png     # PCB 芯片引脚与贴片电阻样本
│   └── metal_parts.png        # 工业工件与垫圈测量样本
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

### 2. 整像素边缘 + 法向亚像素修正 (`edges_subpix`)
- 先用 Canny 提取整像素边缘轮廓，再沿边缘法向对梯度幅值做二次抛物线三点插值：
  $$t^* = \frac{M(-1) - M(+1)}{2(M(-1) - 2M(0) + M(+1))}$$
- 产出浮点坐标 XLD 轮廓，并累加欧氏折线弧长。
- **能力边界**：这是对整像素边缘的法向插值修正，并非 HALCON 基于 Steger-Hessian 脊线检测的真亚像素边缘；精度受整像素边缘质量限制。

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

### 8. 色彩空间扩展 (`rgb_to_hsv` / `hsv_threshold`)
- 新增 HSV 色彩空间转换与彩色阈值分割，色相/饱和度/明度三维范围筛选，解决彩色目标（如药丸颜色分类）识别需求。

### 9. 形状模板匹配 (`find_shape_model`)
- 灰度 NCC 匹配，支持**同图多目标**（多峰值提取 + 跨尺度/角度统一 NMS 去重）、多尺度、多角度（缺省自动 0~360° 扫描）。
- **图像金字塔（pyrDown）由粗到精搜索**加速，并对相关峰做二次曲面插值给出亚像素中心。
- 支持极性无关匹配（兼容亮目标/暗背景反转）。
- **能力边界**：工作在灰度 NCC 层面，非 HALCON 基于边缘方向的形状匹配，暂不具备其全角度测量与亚像素边缘一致性评分的全部能力。

### 10. 轮廓多边形近似 (`gen_contour_polygon`)
- 封装 `cv2.approxPolyDP`，对 XLD 轮廓做多边形简化并提取拐点序列，配合已有亚像素轮廓完成形状简化与角点提取。

### 11. Blob 特征扩展 (`select_shape`)
- `select_shape` 判据新增 **矩形度 (Rectangularity)** 与 **Hu 七阶不变矩**（可选按参考矩距离筛选），支撑更复杂的缺陷分类规则。

### 12. 条码 / 二维码识别 (`read_barcode`)
- 基于 OpenCV 内置 `QRCodeDetector` 识别 QR 码（零额外依赖）；若安装 `pyzbar` 则额外支持一维条码与 Data Matrix。

### 13. 棋盘格比例标定 (`calibrate`)
- 棋盘格角点检测 + 亚像素细化，输出单一 像素/物理单位 换算系数，使几何度量可换算为真实工业单位。
- **能力边界**：仅输出平面比例系数，不求解相机内参、畸变系数与透视校正，不能替代 HALCON `calibrate_cameras` 的测量级标定。

### 14. OCR 文字识别 (`read_text`)
- 可选接入 Tesseract（`pytesseract`）；未安装时抛出明确提示并优雅降级，不影响其他算子。

### 15. 会话磁盘持久化 (`SessionManager`)
- 可选启用磁盘 JSON 落盘（设置 `NAVIVISION_SESSION_DIR`），会话重启不丢失；支持过期与容量淘汰、启动批量恢复。

### 16. CI 持续集成 (`.github/workflows/test.yml`)
- GitHub Actions 在 push / PR 时自动运行 `test_core.py` 与 `test_api_contract.py`（Python 3.10 / 3.12 矩阵），杜绝"测试形同虚设"。

### 17. ROI 交互与区域归约 (`reduce_domain`)
- 支持矩形 / 圆 / 多边形三种 ROI（前端可在视口直接绘制，后端 `create_mask_from_geometry` 生成掩膜），区域外像素置零、画布尺寸不变，不破坏下游坐标系。

### 18. 一维卡尺测量 (`measure_pos`)
- 沿任意测量线采样灰度剖面，高斯平滑 + 一阶导数极值 + 抛物线插值，输出亚像素边缘点与跨距，用于尺寸/间距测量。

### 19. 流水线分支与多图 (`input_from` / `merge_images`)
- 步骤可声明 `input_from` 引用任意上游步骤输出，实现分支与多图；`merge_images` 负责把两路图像合并；`read_image` 支持流水线中途换图。

### 20. 深度学习推理节点 (`onnx_inference`)
- 通过 ONNX Runtime 运行已训练模型（分类 / 通用）。未安装 `onnxruntime` 或模型缺失时抛出明确提示并优雅降级，不影响整条流水线。

### 21. 原生 HDevelop 4GL 语言引擎与双向转译 (`core/hdev_engine.py`)
- **纯自研语法解析器 (`HDevParser`)**：原生解析 `.hdev` / `.hdvp` XML 与纯文本脚本，支持标准 4 槽位语法 `(In : Out : CtrlIn : CtrlOut)`、标准算子参数自动推导、控制流与注释。
- **解释执行沙箱 (`HDevInterpreter`)**：维护 `Iconic` (Image/Region/XLD) 与 `Control` (元组/标量) 变量空间，支持视口目标切换（如在 Canvas 上直接检查任一阶段中间变量）。
- **双向无损转译器 (`HDevTranspiler`)**：支持将 HDevelop 脚本一键转译并同步至可视化卡片流水线，亦支持将卡片流水线导出为 `.hdev` 标准脚本。

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

### 3. 运行全量核心与 HDevelop 测试套件
```bash
python test_core.py
python test_api_contract.py
python test_hdev.py
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
| `rgb_to_hsv` | `trans_from_rgb (Rgb->Hsv)` | 色彩空间转换，产出 H/S/V 三通道，支撑彩色目标分析 |
| `hsv_threshold` | `threshold (HSV 空间)` | HSV 范围彩色阈值分割，适配药丸颜色分类等彩色目标识别 |
| `find_shape_model` | `find_shape_model` | 多目标 + 多尺度 + 多角度模板匹配，含图像金字塔与相关峰亚像素定位 |
| `gen_contour_polygon` | `gen_polygons_xld / approx_chain` | 轮廓多边形近似，提取拐点并简化形状 |
| `read_barcode` | `find_bar_code / find_data_code_2d` | 条码 / QR / Data Matrix 识别 (OpenCV 内置 + 可选 pyzbar) |
| `calibrate` | `calibrate_cameras` (简化) | 棋盘格比例标定，仅输出 像素→物理尺寸 换算系数（无内参/畸变） |
| `read_text` | `read_ocr` | OCR 文字识别 (可选 pytesseract，缺失时优雅降级) |
| `edges_subpix` | `edges_subpix` | Canny 整像素边缘 + 法向抛物线亚像素修正 XLD 轮廓 |
| `measure_region` | `measure_region / smallest_rectangle2` | 提取旋转外接矩形 OBB、外接圆、二阶矩主轴与凸度 |
| `reduce_domain` | `reduce_domain` | ROI 归约：矩形/圆/多边形 ROI 外像素置零，画布尺寸不变 |
| `measure_pos` | `measure_pos` | 一维卡尺测量：沿测量线定位亚像素边缘点与跨距 |
| `merge_images` | `concat_obj` (分支汇聚) | 多图/分支汇聚：两路图像合并 (blend/add/max/min/absdiff/stack) |
| `onnx_inference` | `deep_*` (深度学习) | ONNX 深度学习推理 (可选 onnxruntime，缺失时优雅降级) |
