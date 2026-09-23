/**
 * NaviVision Studio - 算法命令手册 (Operator Reference Manual & Cheatsheet)
 * 包含完整 HDevelop 4GL 算子签名、中文描述、参数详解与代码插入模板
 */

const OPERATOR_MANUAL_DATA = [
  // 1. 图像采集与通道
  {
    name: "read_image",
    category: "io",
    categoryName: "图像与通道",
    signature: "read_image (Image, FileName)",
    slots: "(: Image : FileName :)",
    description: "从文件路径载入本地工业相机图片或测试样本，输出图像变量 Image。",
    params: [
      { name: "Image", type: "Iconic (Out)", desc: "输出图像变量名" },
      { name: "FileName", type: "Control (In)", desc: "图像路径 (字符串，如 '4-3.png' 或 'pills')" }
    ],
    snippet: "read_image (Image, '4-3.png')\n"
  },
  {
    name: "rgb1_to_gray",
    category: "io",
    categoryName: "图像与通道",
    signature: "rgb1_to_gray (Image, GrayImage)",
    slots: "(Image : GrayImage : :)",
    description: "将彩色三通道 (RGB/BGR) 图像转换为单通道 8 位灰度图像。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "输入彩色图像" },
      { name: "GrayImage", type: "Iconic (Out)", desc: "输出灰度图像" }
    ],
    snippet: "rgb1_to_gray (Image, GrayImage)\n"
  },
  {
    name: "rgb_to_hsv",
    category: "io",
    categoryName: "图像与通道",
    signature: "rgb_to_hsv (Image, HSVImage)",
    slots: "(Image : HSVImage : :)",
    description: "将 RGB 颜色空间转换为色调(Hue)、饱和度(Sat)、亮度(Val)三通道图像。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "输入彩色图像" },
      { name: "HSVImage", type: "Iconic (Out)", desc: "输出 HSV 图像" }
    ],
    snippet: "rgb_to_hsv (Image, HSVImage)\n"
  },
  {
    name: "reduce_domain",
    category: "io",
    categoryName: "图像与通道",
    signature: "reduce_domain (Image, Region, ImageReduced)",
    slots: "(Image, Region : ImageReduced : :)",
    description: "将图像的计算定义域截断为指定 Region 区域，用于后续高效局部计算 (ROI)。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "原始输入图像" },
      { name: "Region", type: "Iconic (In)", desc: "ROI 截断区域" },
      { name: "ImageReduced", type: "Iconic (Out)", desc: "输出截断后的图像" }
    ],
    snippet: "reduce_domain (Image, ROI_Region, ImageReduced)\n"
  },

  // 2. 阈值与分割
  {
    name: "threshold",
    category: "threshold",
    categoryName: "阈值与分割",
    signature: "threshold (Image, Region, MinGray, MaxGray)",
    slots: "(Image : Region : MinGray, MaxGray :)",
    description: "经典双阈值分割算子，提取灰度值在 [MinGray, MaxGray] 范围内的所有像素集合。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "待分割灰度图像" },
      { name: "Region", type: "Iconic (Out)", desc: "输出的二值区域" },
      { name: "MinGray", type: "Control (In)", desc: "最小灰度阈值 (0-255)" },
      { name: "MaxGray", type: "Control (In)", desc: "最大灰度阈值 (0-255)" }
    ],
    snippet: "threshold (GrayImage, BrightRegions, 160, 255)\n"
  },
  {
    name: "auto_threshold",
    category: "threshold",
    categoryName: "阈值与分割",
    signature: "auto_threshold (Image, Regions, Sigma)",
    slots: "(Image : Regions : Sigma :)",
    description: "基于大津法 (Otsu) 的全局灰度直方图自动双峰阈值分割。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "待分割灰度图像" },
      { name: "Regions", type: "Iconic (Out)", desc: "输出自动二值化区域" },
      { name: "Sigma", type: "Control (In)", desc: "高斯平滑核尺寸 (默认 1.0)" }
    ],
    snippet: "auto_threshold (GrayImage, AutoRegions, 1.0)\n"
  },
  {
    name: "binary_threshold",
    category: "threshold",
    categoryName: "阈值与分割",
    signature: "binary_threshold (Image, Region, Method, LightDark, UsedThreshold)",
    slots: "(Image : Region : Method, LightDark : UsedThreshold)",
    description: "工业级自动双值阈值分割，可选择 'max_separability' 算法及提取暗场/亮场目标。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "待分割灰度图像" },
      { name: "Region", type: "Iconic (Out)", desc: "分割二值区域" },
      { name: "Method", type: "Control (In)", desc: "算法名称，如 'max_separability'" },
      { name: "LightDark", type: "Control (In)", desc: "'light' (亮目标) 或 'dark' (暗目标)" },
      { name: "UsedThreshold", type: "Control (Out)", desc: "实际计算得到的分割阈值输出变量" }
    ],
    snippet: "binary_threshold (GrayImage, Parts, 'max_separability', 'dark', UsedThreshold)\n"
  },
  {
    name: "hsv_threshold",
    category: "threshold",
    categoryName: "阈值与分割",
    signature: "hsv_threshold (Image, Region, HMin, HMax, SMin, SMax, VMin, VMax)",
    slots: "(Image : Region : HMin, HMax, SMin, SMax, VMin, VMax :)",
    description: "针对 HSV 彩色空间多通道联合阈值分割，精确定位特定颜色的工业部件。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "输入彩色图像" },
      { name: "Region", type: "Iconic (Out)", desc: "颜色匹配区域" },
      { name: "HMin, HMax", type: "Control (In)", desc: "色相区间 (0-180)" },
      { name: "SMin, SMax", type: "Control (In)", desc: "饱和度区间 (0-255)" },
      { name: "VMin, VMax", type: "Control (In)", desc: "明度区间 (0-255)" }
    ],
    snippet: "hsv_threshold (Image, ColorRegion, 100, 130, 80, 255, 50, 255)\n"
  },
  {
    name: "connection",
    category: "threshold",
    categoryName: "阈值与分割",
    signature: "connection (Region, ConnectedRegions)",
    slots: "(Region : ConnectedRegions : :)",
    description: "将整张二值区域掩膜打散为多个独立的独立连通域几何对象。",
    params: [
      { name: "Region", type: "Iconic (In)", desc: "待打散的输入区域" },
      { name: "ConnectedRegions", type: "Iconic (Out)", desc: "打散后的连通域列表" }
    ],
    snippet: "connection (BrightRegions, ConnectedRegions)\n"
  },
  {
    name: "select_shape",
    category: "threshold",
    categoryName: "阈值与分割",
    signature: "select_shape (Regions, SelectedRegions, Features, Operation, Min, Max)",
    slots: "(Regions : SelectedRegions : Features, Operation, Min, Max :)",
    description: "按面积、圆度、长宽比或紧致度筛选连通域目标，剔除噪点并保留合格工件。",
    params: [
      { name: "Regions", type: "Iconic (In)", desc: "连通域集合" },
      { name: "SelectedRegions", type: "Iconic (Out)", desc: "筛选后的连通域集合" },
      { name: "Features", type: "Control (In)", desc: "'area' | 'circularity' | 'aspect_ratio' | 'rectangularity'" },
      { name: "Operation", type: "Control (In)", desc: "逻辑运算符，如 'and'" },
      { name: "Min, Max", type: "Control (In)", desc: "取值门槛范围" }
    ],
    snippet: "select_shape (ConnectedRegions, SelectedPills, 'area', 'and', 1000, 3000)\n"
  },

  // 3. 形态学与滤波
  {
    name: "gauss_filter",
    category: "morphology",
    categoryName: "形态学滤波",
    signature: "gauss_filter (Image, ImageGauss, Size)",
    slots: "(Image : ImageGauss : Size :)",
    description: "应用高斯低通平滑滤波器消除图像高频噪点。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "输入图像" },
      { name: "ImageGauss", type: "Iconic (Out)", desc: "高斯平滑后的图像" },
      { name: "Size", type: "Control (In)", desc: "滤波核大小 (奇数，如 3, 5, 7)" }
    ],
    snippet: "gauss_filter (GrayImage, FilteredImage, 5)\n"
  },
  {
    name: "mean_image",
    category: "morphology",
    categoryName: "形态学滤波",
    signature: "mean_image (Image, ImageMean, MaskWidth, MaskHeight)",
    slots: "(Image : ImageMean : MaskWidth, MaskHeight :)",
    description: "均值滤波平滑图像，降低随机高斯与椒盐噪点。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "输入图像" },
      { name: "ImageMean", type: "Iconic (Out)", desc: "均值滤波输出图像" },
      { name: "MaskWidth, MaskHeight", type: "Control (In)", desc: "滤波模板宽高" }
    ],
    snippet: "mean_image (Image, Filtered, 5, 5)\n"
  },
  {
    name: "opening_circle",
    category: "morphology",
    categoryName: "形态学滤波",
    signature: "opening_circle (Region, RegionOpening, Radius)",
    slots: "(Region : RegionOpening : Radius :)",
    description: "圆形结构元开运算 (先腐蚀后膨胀)，平滑区域边缘并去除毛刺细枝。",
    params: [
      { name: "Region", type: "Iconic (In)", desc: "输入二值区域" },
      { name: "RegionOpening", type: "Iconic (Out)", desc: "开运算后区域" },
      { name: "Radius", type: "Control (In)", desc: "圆形结构元半径 (像素)" }
    ],
    snippet: "opening_circle (Region, SmoothedRegion, 3.5)\n"
  },
  {
    name: "closing_circle",
    category: "morphology",
    categoryName: "形态学滤波",
    signature: "closing_circle (Region, RegionClosing, Radius)",
    slots: "(Region : RegionClosing : Radius :)",
    description: "圆形结构元闭运算 (先膨胀后腐蚀)，桥接微小断裂缝隙并填补内部孔洞洞眼。",
    params: [
      { name: "Region", type: "Iconic (In)", desc: "输入二值区域" },
      { name: "RegionClosing", type: "Iconic (Out)", desc: "闭运算后区域" },
      { name: "Radius", type: "Control (In)", desc: "圆形结构元半径 (像素)" }
    ],
    snippet: "closing_circle (Region, SealedRegion, 4.0)\n"
  },
  {
    name: "dilation_circle",
    category: "morphology",
    categoryName: "形态学滤波",
    signature: "dilation_circle (Region, RegionDilation, Radius)",
    slots: "(Region : RegionDilation : Radius :)",
    description: "圆形结构元膨胀算子，扩大区域面积并向外扩张边界。",
    params: [
      { name: "Region", type: "Iconic (In)", desc: "输入区域" },
      { name: "RegionDilation", type: "Iconic (Out)", desc: "膨胀后区域" },
      { name: "Radius", type: "Control (In)", desc: "膨胀半径 (像素)" }
    ],
    snippet: "dilation_circle (Region, ExpandedRegion, 2.0)\n"
  },
  {
    name: "erosion_circle",
    category: "morphology",
    categoryName: "形态学滤波",
    signature: "erosion_circle (Region, RegionErosion, Radius)",
    slots: "(Region : RegionErosion : Radius :)",
    description: "圆形结构元腐蚀算子，收缩区域面积，消除微小凸起与弱连通。",
    params: [
      { name: "Region", type: "Iconic (In)", desc: "输入区域" },
      { name: "RegionErosion", type: "Iconic (Out)", desc: "腐蚀后区域" },
      { name: "Radius", type: "Control (In)", desc: "腐蚀半径 (像素)" }
    ],
    snippet: "erosion_circle (Region, ShrunkRegion, 2.0)\n"
  },

  // 4. 几何测量与拟合
  {
    name: "smallest_rectangle2",
    category: "measure",
    categoryName: "几何测量拟合",
    signature: "smallest_rectangle2 (Regions, Row, Column, Phi, Length1, Length2)",
    slots: "(Regions : : : Row, Column, Phi, Length1, Length2)",
    description: "求解各连通域的最小外接旋转矩形 (Oriented Bounding Box, OBB)，输出中心点、倾斜角及长短半轴。",
    params: [
      { name: "Regions", type: "Iconic (In)", desc: "待测量连通域目标" },
      { name: "Row, Column", type: "Control (Out)", desc: "矩形几何中心坐标" },
      { name: "Phi", type: "Control (Out)", desc: "旋转角度 (弧度)" },
      { name: "Length1, Length2", type: "Control (Out)", desc: "主轴半长与次轴半长" }
    ],
    snippet: "smallest_rectangle2 (SelectedPills, Rows, Cols, Phis, L1, L2)\n"
  },
  {
    name: "smallest_circle",
    category: "measure",
    categoryName: "几何测量拟合",
    signature: "smallest_circle (Regions, Row, Column, Radius)",
    slots: "(Regions : : : Row, Column, Radius)",
    description: "求解各连通域目标的最小外接圆中心坐标与半径大小。",
    params: [
      { name: "Regions", type: "Iconic (In)", desc: "待测量连通域目标" },
      { name: "Row, Column", type: "Control (Out)", desc: "圆心行与列坐标" },
      { name: "Radius", type: "Control (Out)", desc: "外接圆半径" }
    ],
    snippet: "smallest_circle (SelectedPills, CenterRows, CenterCols, Radii)\n"
  },
  {
    name: "area_center",
    category: "measure",
    categoryName: "几何测量拟合",
    signature: "area_center (Regions, Area, Row, Column)",
    slots: "(Regions : : : Area, Row, Column)",
    description: "计算各连通域目标的像素面积与其重心质心坐标。",
    params: [
      { name: "Regions", type: "Iconic (In)", desc: "输入连通域" },
      { name: "Area", type: "Control (Out)", desc: "像素面积数组" },
      { name: "Row, Column", type: "Control (Out)", desc: "重心坐标数组" }
    ],
    snippet: "area_center (SelectedRegions, Areas, Rows, Cols)\n"
  },
  {
    name: "count_obj",
    category: "measure",
    categoryName: "几何测量拟合",
    signature: "count_obj (Objects, Number)",
    slots: "(Objects : : : Number)",
    description: "统计输入 Iconic 目标集合 (Region 连通域或 XLD 轮廓) 的有效对象总数。",
    params: [
      { name: "Objects", type: "Iconic (In)", desc: "待计数的连通域或轮廓变量" },
      { name: "Number", type: "Control (Out)", desc: "目标数量整型输出变量" }
    ],
    snippet: "count_obj (SelectedPills, PillCount)\n"
  },
  {
    name: "distance_pp",
    category: "measure",
    categoryName: "几何测量拟合",
    signature: "distance_pp (Row1, Col1, Row2, Col2, Distance)",
    slots: "(: : Row1, Col1, Row2, Col2 : Distance)",
    description: "计算两点 (Row1, Col1) 与 (Row2, Col2) 之间的欧氏距离。",
    params: [
      { name: "Row1, Col1", type: "Control (In)", desc: "第一个点坐标" },
      { name: "Row2, Col2", type: "Control (In)", desc: "第二个点坐标" },
      { name: "Distance", type: "Control (Out)", desc: "两点间距离" }
    ],
    snippet: "distance_pp (Row1, Col1, Row2, Col2, Distance)\n"
  },
  {
    name: "distance_pl",
    category: "measure",
    categoryName: "几何测量拟合",
    signature: "distance_pl (Row, Col, RowBegin, ColBegin, RowEnd, ColEnd, Distance)",
    slots: "(: : Row, Col, RowBegin, ColBegin, RowEnd, ColEnd : Distance)",
    description: "计算点 (Row, Col) 到由两点确定的无限长直线的垂直距离，常用于测量点相对基准线的偏移量。",
    params: [
      { name: "Row, Col", type: "Control (In)", desc: "待测量点坐标" },
      { name: "RowBegin, ColBegin", type: "Control (In)", desc: "直线起点坐标" },
      { name: "RowEnd, ColEnd", type: "Control (In)", desc: "直线终点坐标" },
      { name: "Distance", type: "Control (Out)", desc: "点到直线的垂直距离" }
    ],
    snippet: "distance_pl (Row, Col, RowBegin, ColBegin, RowEnd, ColEnd, Distance)\n"
  },
  {
    name: "angle_ll",
    category: "measure",
    categoryName: "几何测量拟合",
    signature: "angle_ll (RowA1, ColA1, RowA2, ColA2, RowB1, ColB1, RowB2, ColB2, Angle)",
    slots: "(: : RowA1, ColA1, RowA2, ColA2, RowB1, ColB1, RowB2, ColB2 : Angle)",
    description: "计算直线 A (两点确定) 旋转到直线 B (两点确定) 的夹角，弧度制，范围 (-pi, pi]。",
    params: [
      { name: "RowA1, ColA1, RowA2, ColA2", type: "Control (In)", desc: "直线 A 上的两个点" },
      { name: "RowB1, ColB1, RowB2, ColB2", type: "Control (In)", desc: "直线 B 上的两个点" },
      { name: "Angle", type: "Control (Out)", desc: "直线 A 到直线 B 的夹角 (弧度)" }
    ],
    snippet: "angle_ll (RowA1, ColA1, RowA2, ColA2, RowB1, ColB1, RowB2, ColB2, Angle)\n"
  },

  // 5. 亚像素与 XLD 轮廓
  {
    name: "edges_subpix",
    category: "xld",
    categoryName: "亚像素XLD",
    signature: "edges_subpix (Image, Edges, Filter, Alpha, Low, High)",
    slots: "(Image : Edges : Filter, Alpha, Low, High :)",
    description: "工业级高精度 Canny 亚像素边缘提取，利用抛物线法向拟合获得达到 0.1 像素精度的 XLD 连续轮廓。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "输入图像" },
      { name: "Edges", type: "Iconic (Out)", desc: "输出亚像素 XLD 轮廓列表" },
      { name: "Filter", type: "Control (In)", desc: "滤波器类型，如 'canny'" },
      { name: "Alpha", type: "Control (In)", desc: "平滑参数 (如 1.0)" },
      { name: "Low, High", type: "Control (In)", desc: "滞后阈值高低截断点 (如 40, 100)" }
    ],
    snippet: "edges_subpix (GrayImage, Edges, 'canny', 1.0, 40, 100)\n"
  },
  {
    name: "gen_cross_contour_xld",
    category: "xld",
    categoryName: "亚像素XLD",
    signature: "gen_cross_contour_xld (Crosses, Row, Col, Length, Phi)",
    slots: "(: Crosses : Row, Col, Length, Phi :)",
    description: "在指定坐标中心生成旋转角度为 Phi 的双臂正交相交十字标定 XLD 轮廓标记。",
    params: [
      { name: "Crosses", type: "Iconic (Out)", desc: "输出十字 XLD 矢量轮廓" },
      { name: "Row, Col", type: "Control (In)", desc: "中心坐标数组 (如 [163, 280, 362, 75])" },
      { name: "Length", type: "Control (In)", desc: "十字臂半长 (如 6)" },
      { name: "Phi", type: "Control (In)", desc: "旋转角度弧度 (如 0.78)" }
    ],
    snippet: "gen_cross_contour_xld (Crosses, [163, 280, 362, 75], [125, 120, 361, 340], 6, 0.78)\n"
  },
  {
    name: "gen_contour_polygon_xld",
    category: "xld",
    categoryName: "亚像素XLD",
    signature: "gen_contour_polygon_xld (Contour, Polygons, Type, MaxDistance)",
    slots: "(Contour : Polygons : Type, MaxDistance :)",
    description: "道格拉斯-普克 (Douglas-Peucker) 轮廓多边形简化逼近，将连续弯曲轮廓简化为折线骨架。",
    params: [
      { name: "Contour", type: "Iconic (In)", desc: "输入 XLD 轮廓" },
      { name: "Polygons", type: "Iconic (Out)", desc: "输出多边形折线轮廓" },
      { name: "Type", type: "Control (In)", desc: "逼近算法，如 'ramer'" },
      { name: "MaxDistance", type: "Control (In)", desc: "最大允许偏离容差距离 (像素)" }
    ],
    snippet: "gen_contour_polygon_xld (Edges, Polygons, 'ramer', 2.0)\n"
  },
  {
    name: "fit_line_contour_xld",
    category: "xld",
    categoryName: "亚像素XLD",
    signature: "fit_line_contour_xld (Contours, Algorithm, MaxNumPoints, MaxDistance, ClippingEndPoints, RowBegin, ColBegin, RowEnd, ColEnd, Nr, Nc, Dist)",
    slots: "(Contours : : Algorithm, MaxNumPoints, MaxDistance, ClippingEndPoints : RowBegin, ColBegin, RowEnd, ColEnd, Nr, Nc, Dist)",
    description: "对亚像素 XLD 轮廓做总体最小二乘直线拟合，输出拟合线段端点及法线式方程 (Nr*Row + Nc*Col = Dist)，常用于卡尺测量的基准边定位。",
    params: [
      { name: "Contours", type: "Iconic (In)", desc: "输入 XLD 轮廓 (如 edges_subpix 输出)" },
      { name: "Algorithm", type: "Control (In)", desc: "拟合算法名 (如 'tukey', 当前实现为普通最小二乘)" },
      { name: "MaxNumPoints, MaxDistance, ClippingEndPoints", type: "Control (In)", desc: "抗差迭代相关参数 (占位透传)" },
      { name: "RowBegin, ColBegin, RowEnd, ColEnd", type: "Control (Out)", desc: "拟合线段的起止端点坐标" },
      { name: "Nr, Nc, Dist", type: "Control (Out)", desc: "直线法线式方程系数" }
    ],
    snippet: "fit_line_contour_xld (Edges, 'tukey', -1, 5, 'false', RowBegin, ColBegin, RowEnd, ColEnd, Nr, Nc, Dist)\n"
  },
  {
    name: "fit_circle_contour_xld",
    category: "xld",
    categoryName: "亚像素XLD",
    signature: "fit_circle_contour_xld (Contours, Algorithm, MaxNumPoints, MaxDistance, ClippingEndPoints, Row, Column, Radius, StartPhi, EndPhi, PointOrder)",
    slots: "(Contours : : Algorithm, MaxNumPoints, MaxDistance, ClippingEndPoints : Row, Column, Radius, StartPhi, EndPhi, PointOrder)",
    description: "使用 Kåsa 代数最小二乘法对亚像素 XLD 轮廓拟合圆，输出圆心/半径及轮廓弧段的起止角度与绕行方向，常用于孔径/圆形零件测量。",
    params: [
      { name: "Contours", type: "Iconic (In)", desc: "输入 XLD 轮廓 (圆弧或圆形边缘)" },
      { name: "Algorithm", type: "Control (In)", desc: "拟合算法名 (占位透传，当前为代数最小二乘)" },
      { name: "MaxNumPoints, MaxDistance, ClippingEndPoints", type: "Control (In)", desc: "抗差迭代相关参数 (占位透传)" },
      { name: "Row, Column, Radius", type: "Control (Out)", desc: "拟合圆心坐标与半径" },
      { name: "StartPhi, EndPhi, PointOrder", type: "Control (Out)", desc: "轮廓弧段起止角度 (弧度) 与绕行方向" }
    ],
    snippet: "fit_circle_contour_xld (Edges, 'atukey', -1, 3, 'false', Row, Column, Radius, StartPhi, EndPhi, PointOrder)\n"
  },

  // 6. 投影变换与透视矫正
  {
    name: "hom_vector_to_proj_hom_mat2d",
    category: "homography",
    categoryName: "投影单应性",
    signature: "hom_vector_to_proj_hom_mat2d (Px, Py, Pw, Qx, Qy, Qw, Method, HomMat2D)",
    slots: "(: : Px, Py, Pw, Qx, Qy, Qw, Method : HomMat2D)",
    description: "根据原图倾斜畸变点与目标矫正点对通过归一化 DLT 算法求解 3x3 透视单应性投影矩阵 HomMat2D。",
    params: [
      { name: "Px, Py, Pw", type: "Control (In)", desc: "原图特征点坐标与齐次分量 (如 X, Y, [1,1,1,1])" },
      { name: "Qx, Qy, Qw", type: "Control (In)", desc: "目标投影坐标与齐次分量 (如 QX, QY, [1,1,1,1])" },
      { name: "Method", type: "Control (In)", desc: "'normalized_dlt'" },
      { name: "HomMat2D", type: "Control (Out)", desc: "输出 3x3 矩阵变量名" }
    ],
    snippet: "hom_vector_to_proj_hom_mat2d (X, Y, [1,1,1,1], QX, QY, [1,1,1,1], 'normalized_dlt', HomMat2D)\n"
  },
  {
    name: "projective_trans_image",
    category: "homography",
    categoryName: "投影单应性",
    signature: "projective_trans_image (Image, Image_rectified, HomMat2D, Interpolation, AdaptImageSize, TransformDomain)",
    slots: "(Image : Image_rectified : HomMat2D, Interpolation, AdaptImageSize, TransformDomain :)",
    description: "利用 3x3 投影矩阵对输入图像进行双线性反向几何映射，彻底校正倾斜畸变与透视形变。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "待矫正输入图像" },
      { name: "Image_rectified", type: "Iconic (Out)", desc: "输出校正后的正投影图像" },
      { name: "HomMat2D", type: "Control (In)", desc: "计算好的 3x3 变换矩阵变量" },
      { name: "Interpolation", type: "Control (In)", desc: "'bilinear' (双线性) 或 'nearest_neighbor'" },
      { name: "AdaptImageSize", type: "Control (In)", desc: "'false' 或 'true'" }
    ],
    snippet: "projective_trans_image (Image, Image_rectified, HomMat2D, 'bilinear', 'false', 'false')\n"
  },

  // 7. 视口与显示控制
  {
    name: "dev_display",
    category: "display",
    categoryName: "视口与显示",
    signature: "dev_display (Object)",
    slots: "(Object : : :)",
    description: "指定将哪个 Iconic 对象（底图、彩色掩膜 Region 或 XLD 亚像素轮廓）作为画布的主视口渲染目标。",
    params: [
      { name: "Object", type: "Iconic (In)", desc: "要在画布上高亮显示的图像或几何变量名" }
    ],
    snippet: "dev_display (Image_rectified)\n"
  },
  {
    name: "dev_open_window_fit_image",
    category: "display",
    categoryName: "视口与显示",
    signature: "dev_open_window_fit_image (Image, Row, Column, WidthLimit, HeightLimit, WindowHandle)",
    slots: "(Image : : Row, Column, WidthLimit, HeightLimit : WindowHandle)",
    description: "自动适配图像分辨率与窗口边界，保持长宽比缩放对齐。",
    params: [
      { name: "Image", type: "Iconic (In)", desc: "参考尺寸图像" },
      { name: "Row, Column", type: "Control (In)", desc: "窗口左上角位置" },
      { name: "WindowHandle", type: "Control (Out)", desc: "视口句柄" }
    ],
    snippet: "dev_open_window_fit_image (Image, 0, 0, -1, -1, WindowHandle)\n"
  },
  {
    name: "dev_set_color",
    category: "display",
    categoryName: "视口与显示",
    signature: "dev_set_color (ColorName)",
    slots: "(: : ColorName :)",
    description: "设置视口矢量绘制的默认描边颜色 (如 'red', 'green', 'cyan')。",
    params: [
      { name: "ColorName", type: "Control (In)", desc: "颜色名字符串" }
    ],
    snippet: "dev_set_color ('red')\n"
  },
  {
    name: "dev_set_line_width",
    category: "display",
    categoryName: "视口与显示",
    signature: "dev_set_line_width (LineWidth)",
    slots: "(: : LineWidth :)",
    description: "设置视口矢量轮廓绘制的线宽像素大小。",
    params: [
      { name: "LineWidth", type: "Control (In)", desc: "像素宽度 (如 2)" }
    ],
    snippet: "dev_set_line_width (2)\n"
  },
  {
    name: "dev_update_off",
    category: "display",
    categoryName: "视口与显示",
    signature: "dev_update_off ()",
    slots: "(: : :)",
    description: "关闭过程中的冗余视图刷新，以极致压榨批量工业流水线的解释执行性能。",
    params: [],
    snippet: "dev_update_off ()\n"
  }
];

class OperatorManualManager {
  constructor(modalEl, codeEditorInstance) {
    this.modal = modalEl;
    this.editor = codeEditorInstance;
    this.currentCategory = "all";
    this.searchQuery = "";

    this.searchInput = document.getElementById("manualSearchInput");
    this.cardList = document.getElementById("manualCardList");
    this.pillsContainer = document.getElementById("manualCategoryPills");

    this.initEvents();
    this.render();
  }

  initEvents() {
    if (this.searchInput) {
      this.searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value.trim().toLowerCase();
        this.render();
      });
    }

    if (this.pillsContainer) {
      this.pillsContainer.addEventListener("click", (e) => {
        const btn = e.target.closest(".cat-pill");
        if (!btn) return;
        this.pillsContainer.querySelectorAll(".cat-pill").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        this.currentCategory = btn.dataset.cat || "all";
        this.render();
      });
    }
  }

  open() {
    if (this.modal) {
      this.modal.classList.add("open");
      if (this.searchInput) {
        this.searchInput.value = "";
        this.searchQuery = "";
        setTimeout(() => this.searchInput.focus(), 100);
      }
      this.render();
    }
  }

  close() {
    if (this.modal) {
      this.modal.classList.remove("open");
    }
  }

  insertSnippet(snippetText) {
    const textarea = document.getElementById("scriptEditor");
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const val = textarea.value;

    textarea.value = val.substring(0, start) + snippetText + val.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start + snippetText.length;
    textarea.focus();

    // 触发行号更新
    if (this.editor && typeof this.editor.updateLineNumbers === "function") {
      this.editor.updateLineNumbers();
    }

    // 关闭手册弹窗
    this.close();

    // 控制台提示
    if (this.editor && typeof this.editor.logToConsole === "function") {
      this.editor.logToConsole(`[代码插入] 成功插入算子: ${snippetText.trim()}`, "info");
    }
  }

  copySnippet(snippetText, btnEl) {
    navigator.clipboard.writeText(snippetText).then(() => {
      const origText = btnEl.innerHTML;
      btnEl.innerHTML = "<span>✓ 已复制</span>";
      btnEl.style.borderColor = "var(--success)";
      btnEl.style.color = "var(--success)";
      setTimeout(() => {
        btnEl.innerHTML = origText;
        btnEl.style.borderColor = "";
        btnEl.style.color = "";
      }, 1500);
    });
  }

  render() {
    if (!this.cardList) return;

    const filtered = OPERATOR_MANUAL_DATA.filter(op => {
      const matchCat = (this.currentCategory === "all") || (op.category === this.currentCategory);
      if (!matchCat) return false;

      if (!this.searchQuery) return true;

      const q = this.searchQuery;
      return op.name.toLowerCase().includes(q) ||
             op.description.toLowerCase().includes(q) ||
             op.signature.toLowerCase().includes(q) ||
             op.categoryName.toLowerCase().includes(q);
    });

    if (filtered.length === 0) {
      this.cardList.innerHTML = `
        <div style="text-align:center;padding:48px 20px;color:var(--text-dim);">
          <div style="font-size:32px;margin-bottom:8px;">🔍</div>
          <div>未找到匹配的机器视觉算子</div>
          <div style="font-size:12px;margin-top:4px;">请尝试输入更简短的关键词，如 'threshold' 或 'xld'</div>
        </div>
      `;
      return;
    }

    this.cardList.innerHTML = filtered.map(op => `
      <div class="manual-op-card">
        <div class="op-card-header">
          <div class="op-title-row">
            <span class="op-badge-cat">${op.categoryName}</span>
            <span class="op-name">${op.name}</span>
            <span class="op-slots">${op.slots}</span>
          </div>
          <div class="op-card-actions">
            <button class="btn btn-secondary btn-xs btn-copy-op" data-snippet="${encodeURIComponent(op.snippet)}" title="复制代码指令">
              📋 复制
            </button>
            <button class="btn btn-accent btn-xs btn-insert-op" data-snippet="${encodeURIComponent(op.snippet)}" title="插入到当前光标位置">
              ➕ 插入到编辑器
            </button>
          </div>
        </div>
        
        <div class="op-desc">${op.description}</div>
        
        <div class="op-signature-box">
          <code>${op.signature}</code>
        </div>

        ${op.params && op.params.length > 0 ? `
          <div class="op-params-list">
            ${op.params.map(p => `
              <div class="op-param-item">
                <span class="op-param-name">${p.name}</span>
                <span class="op-param-type">${p.type}</span>
                <span class="op-param-desc">${p.desc}</span>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `).join('');

    // 绑定事件
    this.cardList.querySelectorAll(".btn-insert-op").forEach(btn => {
      btn.addEventListener("click", () => {
        const snip = decodeURIComponent(btn.dataset.snippet);
        this.insertSnippet(snip);
      });
    });

    this.cardList.querySelectorAll(".btn-copy-op").forEach(btn => {
      btn.addEventListener("click", () => {
        const snip = decodeURIComponent(btn.dataset.snippet);
        this.copySnippet(snip, btn);
      });
    });
  }
}

// 导出全局构造器
window.OperatorManualManager = OperatorManualManager;
