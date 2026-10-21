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
    description: "在图形窗口中显示 Iconic 对象，遵循 HALCON 叠加语义：显示图像会重绘整个画布并清空之前的叠加层，而显示 Region 掩膜或 XLD 轮廓则叠加绘制在当前画布之上，可连续调用多次以同时显示底图+多个 Region+多条轮廓。",
    params: [
      { name: "Object", type: "Iconic (In)", desc: "要叠加显示的图像 / Region / XLD 轮廓变量名" }
    ],
    snippet: "dev_display (Image)\ndev_display (Region)\n"
  },
  {
    name: "dev_clear_window",
    category: "display",
    categoryName: "视口与显示",
    signature: "dev_clear_window ()",
    slots: "(: : :)",
    description: "清空当前图形窗口累积的所有叠加层（底图与已显示的 Region/XLD），常用于在下一轮显示前重置画布。",
    params: [],
    snippet: "dev_clear_window ()\n"
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

// 以下为后续补充的算子 (形态学扩展 / 区域运算 / 仿射变换 / 形状匹配 / 显示补充)
const _manualEntry = (category, categoryName, name, signature, slots, description, params, snippet) =>
  ({ name, category, categoryName, signature, slots, description, params, snippet });
const _p = (name, type, desc) => ({ name, type, desc });

OPERATOR_MANUAL_DATA.push(
  // 图像与通道
  _manualEntry("io", "图像与通道", "get_image_size",
    "get_image_size (Image, Width, Height)", "(Image : : : Width, Height)",
    "取得图像的宽度和高度 (像素)，常用来给 dev_open_window 设置窗口大小。",
    [_p("Image", "Iconic (In)", "输入图像"), _p("Width", "Control (Out)", "图像宽度"), _p("Height", "Control (Out)", "图像高度")],
    "get_image_size (Image, Width, Height)\n"),

  // 形态学：矩形与自定义结构元素
  _manualEntry("morphology", "形态学滤波", "erosion_rectangle1",
    "erosion_rectangle1 (Region, RegionErosion, Width, Height)", "(Region : RegionErosion : Width, Height :)",
    "用宽 Width、高 Height 的矩形结构元素腐蚀区域，参考点为矩形中心。矩形与矩形边缘对齐，腐蚀后直角保持不变。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionErosion", "Iconic (Out)", "腐蚀后的区域"),
     _p("Width, Height", "Control (In)", "矩形结构元素的宽与高 (像素)")],
    "erosion_rectangle1 (Region, RegionErosion, 11, 13)\n"),
  _manualEntry("morphology", "形态学滤波", "dilation_rectangle1",
    "dilation_rectangle1 (Region, RegionDilation, Width, Height)", "(Region : RegionDilation : Width, Height :)",
    "用宽 Width、高 Height 的矩形结构元素膨胀区域。注意参数顺序是先宽后高。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionDilation", "Iconic (Out)", "膨胀后的区域"),
     _p("Width, Height", "Control (In)", "矩形结构元素的宽与高 (像素)")],
    "dilation_rectangle1 (Region, RegionDilation, 11, 13)\n"),
  _manualEntry("morphology", "形态学滤波", "opening_rectangle1",
    "opening_rectangle1 (Region, RegionOpening, Width, Height)", "(Region : RegionOpening : Width, Height :)",
    "矩形结构元素的开运算 (先腐蚀后膨胀)，去掉比矩形小的前景噪点。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionOpening", "Iconic (Out)", "开运算后的区域"),
     _p("Width, Height", "Control (In)", "矩形结构元素的宽与高 (像素)")],
    "opening_rectangle1 (Region, RegionOpening, 11, 11)\n"),
  _manualEntry("morphology", "形态学滤波", "closing_rectangle1",
    "closing_rectangle1 (Region, RegionClosing, Width, Height)", "(Region : RegionClosing : Width, Height :)",
    "矩形结构元素的闭运算 (先膨胀后腐蚀)，填平比矩形小的孔洞。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionClosing", "Iconic (Out)", "闭运算后的区域"),
     _p("Width, Height", "Control (In)", "矩形结构元素的宽与高 (像素)")],
    "closing_rectangle1 (Region, RegionClosing, 9, 9)\n"),
  _manualEntry("morphology", "形态学滤波", "erosion1",
    "erosion1 (Region, StructElement, RegionErosion, Iterations)", "(Region, StructElement : RegionErosion : Iterations :)",
    "以任意区域作结构元素腐蚀，参考点取结构元素的重心。结构元素通常由 gen_ellipse、gen_circle 等生成。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("StructElement", "Iconic (In)", "结构元素区域"),
     _p("RegionErosion", "Iconic (Out)", "腐蚀后的区域"), _p("Iterations", "Control (In)", "重复次数 (默认 1)")],
    "gen_ellipse (Ellipse, 100, 100, 0, 13, 11)\nerosion1 (Region, Ellipse, RegionErosion, 1)\n"),
  _manualEntry("morphology", "形态学滤波", "erosion2",
    "erosion2 (Region, StructElement, RegionErosion, Row, Column, Iterations)", "(Region, StructElement : RegionErosion : Row, Column, Iterations :)",
    "与 erosion1 相同，但参考点由 Row、Column 指定 (与结构元素同一坐标系)。结果形状不变，整体平移 (参考点 − 重心)。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("StructElement", "Iconic (In)", "结构元素区域"),
     _p("RegionErosion", "Iconic (Out)", "腐蚀后的区域"), _p("Row, Column", "Control (In)", "参考点坐标"),
     _p("Iterations", "Control (In)", "重复次数")],
    "erosion2 (Region, Ellipse, RegionErosion, 0, 0, 1)\n"),
  _manualEntry("morphology", "形态学滤波", "dilation1",
    "dilation1 (Region, StructElement, RegionDilation, Iterations)", "(Region, StructElement : RegionDilation : Iterations :)",
    "以任意区域作结构元素膨胀，参考点取结构元素的重心。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("StructElement", "Iconic (In)", "结构元素区域"),
     _p("RegionDilation", "Iconic (Out)", "膨胀后的区域"), _p("Iterations", "Control (In)", "重复次数 (默认 1)")],
    "dilation1 (Region, Ellipse, RegionDilation, 1)\n"),
  _manualEntry("morphology", "形态学滤波", "dilation2",
    "dilation2 (Region, StructElement, RegionDilation, Row, Column, Iterations)", "(Region, StructElement : RegionDilation : Row, Column, Iterations :)",
    "与 dilation1 相同，但参考点由 Row、Column 指定。平移方向与 erosion2 相反 (整体平移 重心 − 参考点)。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("StructElement", "Iconic (In)", "结构元素区域"),
     _p("RegionDilation", "Iconic (Out)", "膨胀后的区域"), _p("Row, Column", "Control (In)", "参考点坐标"),
     _p("Iterations", "Control (In)", "重复次数")],
    "dilation2 (Region, Ellipse, RegionDilation, 0, 0, 1)\n"),
  _manualEntry("morphology", "形态学滤波", "opening",
    "opening (Region, StructElement, RegionOpening)", "(Region, StructElement : RegionOpening : :)",
    "以任意区域作结构元素的开运算，与参考点位置无关。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("StructElement", "Iconic (In)", "结构元素区域"),
     _p("RegionOpening", "Iconic (Out)", "开运算后的区域")],
    "opening (Region, Ellipse, RegionOpening)\n"),
  _manualEntry("morphology", "形态学滤波", "closing",
    "closing (Region, StructElement, RegionClosing)", "(Region, StructElement : RegionClosing : :)",
    "以任意区域作结构元素的闭运算，与参考点位置无关。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("StructElement", "Iconic (In)", "结构元素区域"),
     _p("RegionClosing", "Iconic (Out)", "闭运算后的区域")],
    "closing (Region, Ellipse, RegionClosing)\n")
);

OPERATOR_MANUAL_DATA.push(
  // 区域生成与集合运算
  _manualEntry("region", "区域生成与运算", "gen_rectangle1",
    "gen_rectangle1 (Rectangle, Row1, Column1, Row2, Column2)", "(: Rectangle : Row1, Column1, Row2, Column2 :)",
    "生成与坐标轴对齐的矩形区域，常用作 ROI。画布尺寸取最近载入的图像。",
    [_p("Rectangle", "Iconic (Out)", "输出矩形区域"), _p("Row1, Column1", "Control (In)", "左上角坐标"),
     _p("Row2, Column2", "Control (In)", "右下角坐标 (含)")],
    "gen_rectangle1 (ROI, 100, 100, 300, 400)\nreduce_domain (Image, ROI, ImageReduced)\n"),
  _manualEntry("region", "区域生成与运算", "gen_circle",
    "gen_circle (Circle, Row, Column, Radius)", "(: Circle : Row, Column, Radius :)",
    "生成实心圆形区域，超出图像的部分被裁掉。",
    [_p("Circle", "Iconic (Out)", "输出圆形区域"), _p("Row, Column", "Control (In)", "圆心坐标"),
     _p("Radius", "Control (In)", "半径 (像素)")],
    "gen_circle (Circle, 240, 320, 80)\n"),
  _manualEntry("region", "区域生成与运算", "gen_ellipse",
    "gen_ellipse (Ellipse, Row, Column, Phi, Radius1, Radius2)", "(: Ellipse : Row, Column, Phi, Radius1, Radius2 :)",
    "生成椭圆区域。Radius1 沿 Phi 方向 (逆时针，弧度)，Radius2 与之垂直。椭圆必须完全落在图像范围内，否则报错。多用作形态学结构元素。",
    [_p("Ellipse", "Iconic (Out)", "输出椭圆区域"), _p("Row, Column", "Control (In)", "中心坐标"),
     _p("Phi", "Control (In)", "Radius1 方向的角度 (弧度)"), _p("Radius1, Radius2", "Control (In)", "两个半轴长度")],
    "gen_ellipse (Ellipse, 100, 100, 0, 13, 11)\n"),
  _manualEntry("region", "区域生成与运算", "fill_up",
    "fill_up (Region, RegionFillUp)", "(Region : RegionFillUp : :)",
    "填充区域内部的所有孔洞。与 difference 配合可提取孔洞：difference (RegionFillUp, Region, Holes)。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionFillUp", "Iconic (Out)", "填充后的区域")],
    "fill_up (Region, RegionFilled)\ndifference (RegionFilled, Region, Holes)\n"),
  _manualEntry("region", "区域生成与运算", "difference",
    "difference (Region, Sub, RegionDifference)", "(Region, Sub : RegionDifference : :)",
    "区域相减：保留 Region 中不属于 Sub 的部分。两个区域的画布尺寸必须一致。",
    [_p("Region", "Iconic (In)", "被减区域"), _p("Sub", "Iconic (In)", "减去的区域"),
     _p("RegionDifference", "Iconic (Out)", "差集")],
    "difference (RegionFilled, Region, Holes)\n"),
  _manualEntry("region", "区域生成与运算", "union1",
    "union1 (Region, RegionUnion)", "(Region : RegionUnion : :)",
    "把一组区域合并为一个区域。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionUnion", "Iconic (Out)", "合并后的区域")],
    "union1 (Regions, RegionUnion)\n"),
  _manualEntry("region", "区域生成与运算", "union2",
    "union2 (Region1, Region2, RegionUnion)", "(Region1, Region2 : RegionUnion : :)",
    "两个区域的并集。",
    [_p("Region1, Region2", "Iconic (In)", "输入的两个区域"), _p("RegionUnion", "Iconic (Out)", "并集")],
    "union2 (RegionA, RegionB, RegionUnion)\n"),
  _manualEntry("region", "区域生成与运算", "intersection",
    "intersection (Region1, Region2, RegionIntersection)", "(Region1, Region2 : RegionIntersection : :)",
    "两个区域的交集。",
    [_p("Region1, Region2", "Iconic (In)", "输入的两个区域"), _p("RegionIntersection", "Iconic (Out)", "交集")],
    "intersection (RegionA, RegionB, RegionIntersection)\n"),
  _manualEntry("region", "区域生成与运算", "complement",
    "complement (Region, RegionComplement)", "(Region : RegionComplement : :)",
    "在图像范围内取区域的补集。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionComplement", "Iconic (Out)", "补集")],
    "complement (Region, Background)\n"),
  _manualEntry("region", "区域生成与运算", "boundary",
    "boundary (Region, RegionBorder, BoundaryType)", "(Region : RegionBorder : BoundaryType :)",
    "提取区域边界像素 (4 邻域)：'inner' 取区域内侧一圈，'outer' 取区域外侧一圈。",
    [_p("Region", "Iconic (In)", "输入区域"), _p("RegionBorder", "Iconic (Out)", "边界区域"),
     _p("BoundaryType", "Control (In)", "'inner' 或 'outer'")],
    "boundary (Region, RegionBorder, 'inner')\n"),
  _manualEntry("measure", "几何测量拟合", "select_obj",
    "select_obj (Objects, ObjectSelected, Index)", "(Objects : ObjectSelected : Index :)",
    "按序号 (从 1 开始) 取出对象集合中的单个对象，常用于 for 循环里逐个处理连通域。",
    [_p("Objects", "Iconic (In)", "对象集合"), _p("ObjectSelected", "Iconic (Out)", "选出的对象"),
     _p("Index", "Control (In)", "序号，从 1 开始")],
    "count_obj (Conn, Number)\nfor I := 1 to Number by 1\n    select_obj (Conn, Obj, I)\nendfor\n")
);

OPERATOR_MANUAL_DATA.push(
  // 仿射变换 (HomMat2D 为 6 元组，作用在 (行, 列) 坐标上，正角度为逆时针)
  _manualEntry("affine", "仿射变换", "hom_mat2d_identity",
    "hom_mat2d_identity (HomMat2DIdentity)", "(: : : HomMat2DIdentity)",
    "生成单位矩阵 (不做任何变换)，作为后续 translate / rotate / scale 的起点。矩阵用 6 个数 (a, b, c, d, e, f) 表示 2x3 矩阵，作用在 (行, 列) 坐标上。",
    [_p("HomMat2DIdentity", "Control (Out)", "输出矩阵变量")],
    "hom_mat2d_identity (HomMat2DIdentity)\n"),
  _manualEntry("affine", "仿射变换", "hom_mat2d_translate",
    "hom_mat2d_translate (HomMat2D, Tx, Ty, HomMat2DTranslate)", "(: : HomMat2D, Tx, Ty : HomMat2DTranslate)",
    "在已有变换之后追加平移。Tx 对应行方向，Ty 对应列方向。",
    [_p("HomMat2D", "Control (In)", "输入矩阵"), _p("Tx, Ty", "Control (In)", "行、列方向的平移量"),
     _p("HomMat2DTranslate", "Control (Out)", "输出矩阵")],
    "hom_mat2d_translate (HomMat2DIdentity, Row, Column, HomMat2DTranslate)\n"),
  _manualEntry("affine", "仿射变换", "hom_mat2d_rotate",
    "hom_mat2d_rotate (HomMat2D, Phi, Px, Py, HomMat2DRotate)", "(: : HomMat2D, Phi, Px, Py : HomMat2DRotate)",
    "在已有变换之后追加绕点 (Px, Py) 的旋转，Phi 为弧度，正值为逆时针 (视觉方向)。",
    [_p("HomMat2D", "Control (In)", "输入矩阵"), _p("Phi", "Control (In)", "旋转角 (弧度)"),
     _p("Px, Py", "Control (In)", "旋转中心的行、列坐标"), _p("HomMat2DRotate", "Control (Out)", "输出矩阵")],
    "hom_mat2d_rotate (HomMat2DTranslate, Angle, Row, Column, HomMat2DRotate)\n"),
  _manualEntry("affine", "仿射变换", "hom_mat2d_scale",
    "hom_mat2d_scale (HomMat2D, Sx, Sy, Px, Py, HomMat2DScale)", "(: : HomMat2D, Sx, Sy, Px, Py : HomMat2DScale)",
    "在已有变换之后追加以 (Px, Py) 为不动点的缩放。",
    [_p("HomMat2D", "Control (In)", "输入矩阵"), _p("Sx, Sy", "Control (In)", "行、列方向的缩放比例"),
     _p("Px, Py", "Control (In)", "不动点的行、列坐标"), _p("HomMat2DScale", "Control (Out)", "输出矩阵")],
    "hom_mat2d_scale (HomMat2DRotate, Scale, Scale, Row, Column, HomMat2DScale)\n"),
  _manualEntry("affine", "仿射变换", "vector_angle_to_rigid",
    "vector_angle_to_rigid (Row1, Column1, Angle1, Row2, Column2, Angle2, HomMat2D)", "(: : Row1, Column1, Angle1, Row2, Column2, Angle2 : HomMat2D)",
    "求把位姿 (Row1, Column1, Angle1) 刚体变换到位姿 (Row2, Column2, Angle2) 的矩阵 (先绕点 1 旋转，再平移)。(0, 0, 0) 到 (Row, Column, 0) 即纯平移。",
    [_p("Row1, Column1, Angle1", "Control (In)", "起始位姿"), _p("Row2, Column2, Angle2", "Control (In)", "目标位姿"),
     _p("HomMat2D", "Control (Out)", "输出矩阵")],
    "vector_angle_to_rigid (0, 0, 0, Row, Column, 0, HomMat2D)\n"),
  _manualEntry("affine", "仿射变换", "affine_trans_contour_xld",
    "affine_trans_contour_xld (Contours, ContoursAffineTrans, HomMat2D)", "(Contours : ContoursAffineTrans : HomMat2D :)",
    "对 XLD 轮廓做仿射变换。形状匹配里常用它把以模型原点为 (0, 0) 的模板轮廓变换到找到的目标位置上。",
    [_p("Contours", "Iconic (In)", "输入 XLD 轮廓"), _p("ContoursAffineTrans", "Iconic (Out)", "变换后的轮廓"),
     _p("HomMat2D", "Control (In)", "变换矩阵")],
    "affine_trans_contour_xld (Model, ModelTrans, HomMat2D)\n"),

  // 形状模板匹配
  _manualEntry("matching", "形状匹配", "create_scaled_shape_model",
    "create_scaled_shape_model (Template, NumLevels, AngleStart, AngleExtent, AngleStep, ScaleMin, ScaleMax, ScaleStep, Optimization, Metric, Contrast, MinContrast, ModelID)",
    "(Template : : NumLevels, AngleStart, AngleExtent, AngleStep, ScaleMin, ScaleMax, ScaleStep, Optimization, Metric, Contrast, MinContrast : ModelID)",
    "由带定义域的模板图像创建支持旋转和缩放的形状模型。模型原点取定义域的重心。角度步长、缩放步长可写 'auto'。得分为归一化互相关 (0~1)，与 HALCON 的数值不会逐位一致。",
    [_p("Template", "Iconic (In)", "经 reduce_domain 限定了模板区域的图像"), _p("NumLevels", "Control (In)", "金字塔层数 (或 'auto')"),
     _p("AngleStart, AngleExtent", "Control (In)", "搜索角度起点与范围 (弧度)"), _p("AngleStep", "Control (In)", "角度步长 (弧度) 或 'auto'"),
     _p("ScaleMin, ScaleMax, ScaleStep", "Control (In)", "缩放范围与步长 (或 'auto')"), _p("Optimization", "Control (In)", "优化选项 (当前忽略)"),
     _p("Metric", "Control (In)", "'use_polarity' | 'ignore_global_polarity' | 'ignore_local_polarity'"),
     _p("Contrast, MinContrast", "Control (In)", "Contrast 用于提取模型轮廓；MinContrast 仅记录，不参与匹配"), _p("ModelID", "Control (Out)", "模型句柄")],
    "create_scaled_shape_model (ImageReduced, 5, rad(-45), rad(90), 'auto', 0.8, 1.0, 'auto', 'none', 'ignore_global_polarity', 40, 10, ModelID)\n"),
  _manualEntry("matching", "形状匹配", "create_shape_model",
    "create_shape_model (Template, NumLevels, AngleStart, AngleExtent, AngleStep, Optimization, Metric, Contrast, MinContrast, ModelID)",
    "(Template : : NumLevels, AngleStart, AngleExtent, AngleStep, Optimization, Metric, Contrast, MinContrast : ModelID)",
    "创建只支持旋转 (不含缩放) 的形状模型，参数含义同 create_scaled_shape_model。",
    [_p("Template", "Iconic (In)", "限定了模板区域的图像"), _p("NumLevels", "Control (In)", "金字塔层数 (或 'auto')"),
     _p("AngleStart, AngleExtent, AngleStep", "Control (In)", "角度范围与步长 (弧度)"), _p("Optimization", "Control (In)", "优化选项 (当前忽略)"),
     _p("Metric", "Control (In)", "极性模式"), _p("Contrast, MinContrast", "Control (In)", "Contrast 用于提取模型轮廓；MinContrast 仅记录，不参与匹配"),
     _p("ModelID", "Control (Out)", "模型句柄")],
    "create_shape_model (ImageReduced, 4, rad(-30), rad(60), 'auto', 'none', 'use_polarity', 30, 10, ModelID)\n"),
  _manualEntry("matching", "形状匹配", "find_scaled_shape_model",
    "find_scaled_shape_model (Image, ModelID, AngleStart, AngleExtent, ScaleMin, ScaleMax, MinScore, NumMatches, MaxOverlap, SubPixel, NumLevels, Greediness, Row, Column, Angle, Scale, Score)",
    "(Image : : ModelID, AngleStart, AngleExtent, ScaleMin, ScaleMax, MinScore, NumMatches, MaxOverlap, SubPixel, NumLevels, Greediness : Row, Column, Angle, Scale, Score)",
    "在图像中搜索形状模型，输出每个目标的位置、角度、缩放和得分 (均为元组，可用 Row[I]、|Score| 访问)。采用由粗到细的两级搜索，SubPixel 非 'none' 时对位置做亚像素插值。",
    [_p("Image", "Iconic (In)", "搜索图像"), _p("ModelID", "Control (In)", "模型句柄"),
     _p("AngleStart, AngleExtent", "Control (In)", "搜索角度范围 (弧度)"), _p("ScaleMin, ScaleMax", "Control (In)", "搜索缩放范围"),
     _p("MinScore", "Control (In)", "最低得分 (0~1)"), _p("NumMatches", "Control (In)", "最多返回个数，0 表示全部"),
     _p("MaxOverlap", "Control (In)", "目标之间允许的最大重叠比例"), _p("SubPixel", "Control (In)", "'none' 或 'least_squares' 等 (非 'none' 即亚像素)"),
     _p("NumLevels, Greediness", "Control (In)", "金字塔层数 / 贪心度 (贪心度当前忽略)"),
     _p("Row, Column, Angle, Scale, Score", "Control (Out)", "目标的位置、角度、缩放、得分元组")],
    "find_scaled_shape_model (ImageSearch, ModelID, rad(-45), rad(90), 0.8, 1.0, 0.5, 0, 0.5, 'least_squares', 5, 0.8, Row, Column, Angle, Scale, Score)\n"),
  _manualEntry("matching", "形状匹配", "find_shape_model",
    "find_shape_model (Image, ModelID, AngleStart, AngleExtent, MinScore, NumMatches, MaxOverlap, SubPixel, NumLevels, Greediness, Row, Column, Angle, Score)",
    "(Image : : ModelID, AngleStart, AngleExtent, MinScore, NumMatches, MaxOverlap, SubPixel, NumLevels, Greediness : Row, Column, Angle, Score)",
    "在图像中搜索只含旋转的形状模型，参数含义同 find_scaled_shape_model (无缩放参数与 Scale 输出)。",
    [_p("Image", "Iconic (In)", "搜索图像"), _p("ModelID", "Control (In)", "模型句柄"),
     _p("AngleStart, AngleExtent", "Control (In)", "搜索角度范围 (弧度)"), _p("MinScore, NumMatches, MaxOverlap", "Control (In)", "最低得分 / 最多个数 / 最大重叠"),
     _p("SubPixel, NumLevels, Greediness", "Control (In)", "亚像素、金字塔层数、贪心度"),
     _p("Row, Column, Angle, Score", "Control (Out)", "目标的位置、角度、得分元组")],
    "find_shape_model (ImageSearch, ModelID, rad(-30), rad(60), 0.7, 0, 0.5, 'least_squares', 4, 0.8, Row, Column, Angle, Score)\n"),
  _manualEntry("matching", "形状匹配", "get_shape_model_params",
    "get_shape_model_params (ModelID, NumLevels, AngleStart, AngleExtent, AngleStep, ScaleMin, ScaleMax, ScaleStep, Metric, MinContrast)",
    "(: : ModelID : NumLevels, AngleStart, AngleExtent, AngleStep, ScaleMin, ScaleMax, ScaleStep, Metric, MinContrast)",
    "读取模型的创建参数，包括 'auto' 实际取到的步长，便于调整参数。",
    [_p("ModelID", "Control (In)", "模型句柄"), _p("NumLevels ... MinContrast", "Control (Out)", "依次输出 9 个参数")],
    "get_shape_model_params (ModelID, NumLevels, AngleStart, AngleExtent, AngleStep, ScaleMin, ScaleMax, ScaleStep, Metric, MinContrast)\n"),
  _manualEntry("matching", "形状匹配", "get_shape_model_contours",
    "get_shape_model_contours (ModelContours, ModelID, Level)", "(: ModelContours : ModelID, Level :)",
    "取得模型的边缘轮廓 (XLD)。坐标以模型原点为 (0, 0)，需要用 affine_trans_contour_xld 变换到图像位置后再显示。Level 目前总是返回原分辨率轮廓。",
    [_p("ModelContours", "Iconic (Out)", "模型轮廓"), _p("ModelID", "Control (In)", "模型句柄"),
     _p("Level", "Control (In)", "金字塔层 (1 为原分辨率)")],
    "get_shape_model_contours (Model, ModelID, 1)\n"),
  _manualEntry("matching", "形状匹配", "clear_shape_model",
    "clear_shape_model (ModelID)", "(: : ModelID :)",
    "释放形状模型。", [_p("ModelID", "Control (In)", "模型句柄")],
    "clear_shape_model (ModelID)\n"),

  // 交互与显示补充
  _manualEntry("display", "视口与显示", "draw_circle",
    "draw_circle (WindowHandle, Row, Column, Radius)", "(: : WindowHandle : Row, Column, Radius)",
    "读取你在视口里预先画好的圆形 ROI。脚本一次性运行、不能中途等待鼠标，所以请先点工具栏的“圆”在图上拖出圆，再运行脚本；没画圆会报错提示。",
    [_p("WindowHandle", "Control (In)", "窗口句柄"), _p("Row, Column", "Control (Out)", "圆心坐标"),
     _p("Radius", "Control (Out)", "半径")],
    "draw_circle (WindowHandle, Row, Column, Radius)\ngen_circle (Circle, Row, Column, Radius)\n"),
  _manualEntry("display", "视口与显示", "dev_disp_text",
    "dev_disp_text (String, CoordSystem, Row, Column, Color, GenParamName, GenParamValue)", "(: : String, CoordSystem, Row, Column, Color, GenParamName, GenParamValue :)",
    "在当前窗口显示文字。Row、Column 可写像素坐标；'top'、'left' 等位置关键字一律按左上角处理。显示新图像 (dev_display) 会清掉已显示的文字。",
    [_p("String", "Control (In)", "文字，可用 + 拼接数字，如 '数量:' + |Score|"), _p("CoordSystem", "Control (In)", "'window' 或 'image'"),
     _p("Row, Column", "Control (In)", "位置"), _p("Color", "Control (In)", "文字颜色"),
     _p("GenParamName, GenParamValue", "Control (In)", "附加参数 (当前忽略，写 [] 即可)")],
    "dev_disp_text ('识别到的对象数量:' + |Score|, 'window', 'top', 'left', 'black', [], [])\n"),
  _manualEntry("display", "视口与显示", "disp_message",
    "disp_message (WindowHandle, String, CoordSystem, Row, Column, Color, Box)", "(: : WindowHandle, String, CoordSystem, Row, Column, Color, Box :)",
    "在窗口里显示文字。String、Row、Column 为等长元组时，每条文字显示在各自的位置上，可给每个匹配目标单独标注。",
    [_p("WindowHandle", "Control (In)", "窗口句柄"), _p("String", "Control (In)", "文字或文字元组"),
     _p("CoordSystem", "Control (In)", "'window' 或 'image'"), _p("Row, Column", "Control (In)", "位置，可为元组"),
     _p("Color", "Control (In)", "文字颜色"), _p("Box", "Control (In)", "'true' 时带底框")],
    "disp_message (WindowHandle, 'score:' + Score, 'image', Row, Column - 80, 'black', 'true')\n")
);

OPERATOR_MANUAL_DATA.push(
  // 字符识别 (OCR)
  _manualEntry("ocr", "字符识别", "read_ocr_class_mlp",
    "read_ocr_class_mlp (FileName, OCRHandle)", "(: : FileName : OCRHandle)",
    "读取 OCR 分类器。文件名是 Industrial_0-9+_NoRej.omc 这类 HALCON 内置字库名时载入本平台的内置字符分类器 (用多种字体合成样本训练的 kNN，对点阵喷码等特殊字体识别较差)；"
    + "否则从工作区读取用 write_ocr_class_mlp 保存的分类器，文件不存在会报错。",
    [_p("FileName", "Control (In)", "字库名或分类器文件名 (路径只取文件名部分)"), _p("OCRHandle", "Control (Out)", "分类器句柄")],
    "read_ocr_class_mlp ('Industrial_0-9+_NoRej.omc', OCRHandle)\n"),
  _manualEntry("ocr", "字符识别", "do_ocr_multi_class_mlp",
    "do_ocr_multi_class_mlp (Character, Image, OCRHandle, Class, Confidence)", "(Character, Image : : OCRHandle : Class, Confidence)",
    "对区域里的每个字符分别分类，输出文字和置信度 (0~1)。区域经 sort_region 排过序时严格按该顺序识别，否则按阅读顺序。错误结果的置信度通常明显偏低，可用来拒识。",
    [_p("Character", "Iconic (In)", "字符区域 (已 connection 打散)"), _p("Image", "Iconic (In)", "字符所在图像"),
     _p("OCRHandle", "Control (In)", "分类器句柄"), _p("Class", "Control (Out)", "识别出的字符 (元组)"),
     _p("Confidence", "Control (Out)", "每个字符的置信度 (元组)")],
    "do_ocr_multi_class_mlp (SortedRegions, GrayImage, OCRHandle, Class, Confidence)\n"),
  _manualEntry("ocr", "字符识别", "sort_region",
    "sort_region (Regions, SortedRegions, SortMode, Order, RowOrCol)", "(Regions : SortedRegions : SortMode, Order, RowOrCol :)",
    "给一组区域排序。SortMode 为 'character' 时按书写顺序 (row 先分行再从左到右，column 先分列再从上到下)，"
    + "或按外接矩形的角点排序 ('upper_left'、'upper_right'、'lower_left'、'lower_right'、'first_point'、'last_point')；Order 为 'true' 升序、'false' 降序。",
    [_p("Regions", "Iconic (In)", "待排序的区域"), _p("SortedRegions", "Iconic (Out)", "排序后的区域"),
     _p("SortMode", "Control (In)", "排序方式"), _p("Order", "Control (In)", "'true' 或 'false'"),
     _p("RowOrCol", "Control (In)", "'row' 或 'column'")],
    "sort_region (ConnectedRegions, SortedRegions, 'character', 'true', 'row')\n"),
  _manualEntry("ocr", "字符识别", "append_ocr_trainf",
    "append_ocr_trainf (Character, Image, Class, TrainingFile)", "(Character, Image : : Class, TrainingFile :)",
    "把字符区域和对应的文字追加到训练文件 (.trf)，文件不存在时自动创建；Class 的个数必须与区域个数一致。训练文件保存在工作区。",
    [_p("Character", "Iconic (In)", "字符区域"), _p("Image", "Iconic (In)", "字符所在图像"),
     _p("Class", "Control (In)", "字符文字 (单个或元组)"), _p("TrainingFile", "Control (In)", "训练文件名")],
    "append_ocr_trainf (ObjectSelected, ImageReduced, words[Index - 1], 'my.trf')\n"),
  _manualEntry("ocr", "字符识别", "read_ocr_trainf_names",
    "read_ocr_trainf_names (TrainingFile, CharacterNames, CharacterCount)", "(: : TrainingFile : CharacterNames, CharacterCount)",
    "读出训练文件里有哪些字符 (按首次出现的顺序) 以及每个字符的样本数。",
    [_p("TrainingFile", "Control (In)", "训练文件名"), _p("CharacterNames", "Control (Out)", "字符名元组"),
     _p("CharacterCount", "Control (Out)", "每个字符的样本数")],
    "read_ocr_trainf_names ('my.trf', CharacterNames, CharacterCount)\n"),
  _manualEntry("ocr", "字符识别", "create_ocr_class_mlp",
    "create_ocr_class_mlp (WidthCharacter, HeightCharacter, Interpolation, Features, Characters, NumHidden, Preprocessing, NumComponents, RandSeed, OCRHandle)",
    "(: : WidthCharacter, HeightCharacter, Interpolation, Features, Characters, NumHidden, Preprocessing, NumComponents, RandSeed : OCRHandle)",
    "创建可训练的 MLP 分类器。本平台由内部固定的字形归一化代替字符宽高、插值、特征和预处理参数，这几个参数被接受但不起作用；"
    + "Characters (至少 2 个类别)、NumHidden (隐藏单元数)、RandSeed (随机种子) 起作用。",
    [_p("WidthCharacter, HeightCharacter", "Control (In)", "字符宽高 (不起作用)"), _p("Interpolation, Features", "Control (In)", "插值与特征 (不起作用)"),
     _p("Characters", "Control (In)", "要识别的全部字符 (元组)"), _p("NumHidden", "Control (In)", "隐藏单元数"),
     _p("Preprocessing, NumComponents", "Control (In)", "预处理 (不起作用)"), _p("RandSeed", "Control (In)", "随机种子"),
     _p("OCRHandle", "Control (Out)", "分类器句柄")],
    "create_ocr_class_mlp (8, 10, 'constant', 'default', CharacterNames, 80, 'none', 10, 42, OCRHandle)\n"),
  _manualEntry("ocr", "字符识别", "trainf_ocr_class_mlp",
    "trainf_ocr_class_mlp (OCRHandle, TrainingFile, MaxIterations, WeightTolerance, ErrorTolerance, Error, ErrorLog)",
    "(: : OCRHandle, TrainingFile, MaxIterations, WeightTolerance, ErrorTolerance : Error, ErrorLog)",
    "用训练文件训练分类器 (对每个样本做轻微平移、旋转、缩放增强)。训练误差降到 ErrorTolerance 以下时提前结束；Error 是训练集平均平方误差，ErrorLog 是误差随迭代的记录。WeightTolerance 不起作用。",
    [_p("OCRHandle", "Control (In)", "分类器句柄"), _p("TrainingFile", "Control (In)", "训练文件名"),
     _p("MaxIterations", "Control (In)", "最大迭代次数"), _p("WeightTolerance", "Control (In)", "不起作用"),
     _p("ErrorTolerance", "Control (In)", "达到该误差即停止"), _p("Error, ErrorLog", "Control (Out)", "最终误差与误差记录")],
    "trainf_ocr_class_mlp (OCRHandle, 'my.trf', 200, 1, 0.01, Error, ErrorLog)\n"),
  _manualEntry("ocr", "字符识别", "write_ocr_class_mlp",
    "write_ocr_class_mlp (OCRHandle, FileName)", "(: : OCRHandle, FileName :)",
    "把训练好的分类器保存成 .omc 文件 (JSON 加 OpenCV MLP 序列化，不使用 pickle)，保存在工作区。",
    [_p("OCRHandle", "Control (In)", "分类器句柄"), _p("FileName", "Control (In)", "分类器文件名")],
    "write_ocr_class_mlp (OCRHandle, 'my.omc')\n"),
  _manualEntry("ocr", "字符识别", "clear_ocr_class_mlp",
    "clear_ocr_class_mlp (OCRHandle)", "(: : OCRHandle :)",
    "释放分类器句柄。", [_p("OCRHandle", "Control (In)", "分类器句柄")],
    "clear_ocr_class_mlp (OCRHandle)\n"),

  // 分割与测量补充
  _manualEntry("threshold", "阈值与分割", "char_threshold",
    "char_threshold (Image, HistoRegion, Characters, Sigma, Percent, Threshold)", "(Image, HistoRegion : Characters : Sigma, Percent : Threshold)",
    "为深色字符、浅色背景自动定阈值并提取字符区域。近似实现：先用 Sigma 平滑直方图，再按大津法定阈值；Percent 不参与计算。",
    [_p("Image", "Iconic (In)", "灰度图像"), _p("HistoRegion", "Iconic (In)", "统计直方图的区域或图像 (可与 Image 相同)"),
     _p("Characters", "Iconic (Out)", "字符区域"), _p("Sigma", "Control (In)", "直方图平滑系数"),
     _p("Percent", "Control (In)", "不参与计算"), _p("Threshold", "Control (Out)", "实际使用的阈值")],
    "char_threshold (GrayImage, GrayImage, Characters, 2, 95, Threshold)\n"),
  _manualEntry("measure", "几何测量拟合", "smallest_rectangle1",
    "smallest_rectangle1 (Regions, Row1, Column1, Row2, Column2)", "(Regions : : : Row1, Column1, Row2, Column2)",
    "每个目标与坐标轴对齐的最小外接矩形，返回左上角和右下角坐标 (含端点)，常用来确定字符的显示位置。",
    [_p("Regions", "Iconic (In)", "区域"), _p("Row1, Column1", "Control (Out)", "左上角"), _p("Row2, Column2", "Control (Out)", "右下角")],
    "smallest_rectangle1 (SortedRegions, Row1, Column1, Row2, Column2)\n"),

  // 图像矫正
  _manualEntry("affine", "仿射变换", "affine_trans_image",
    "affine_trans_image (Image, ImageAffinTrans, HomMat2D, Interpolation, AdaptImageSize)", "(Image : ImageAffinTrans : HomMat2D, Interpolation, AdaptImageSize :)",
    "按 HomMat2D 对整幅图像做仿射变换，区域外填 0。配合 smallest_rectangle2 测得的 Phi，可以把倾斜的文字转正。AdaptImageSize 为 'true' 时扩大画布以容纳全部内容。",
    [_p("Image", "Iconic (In)", "输入图像"), _p("ImageAffinTrans", "Iconic (Out)", "变换后的图像"), _p("HomMat2D", "Control (In)", "变换矩阵"),
     _p("Interpolation", "Control (In)", "'nearest_neighbor'、'bilinear'、'bicubic'"), _p("AdaptImageSize", "Control (In)", "'true' 或 'false'")],
    "hom_mat2d_rotate (HomMat2DIdentity, -Phi, Row, Column, HomMat2DRotate)\naffine_trans_image (GrayImage, GrayRect, HomMat2DRotate, 'bilinear', 'false')\n"),
  _manualEntry("affine", "仿射变换", "rotate_image",
    "rotate_image (Image, ImageRotate, Phi, Interpolation)", "(Image : ImageRotate : Phi, Interpolation :)",
    "绕图像中心旋转，Phi 为角度 (不是弧度)，逆时针为正，画布大小不变。",
    [_p("Image", "Iconic (In)", "输入图像"), _p("ImageRotate", "Iconic (Out)", "旋转后的图像"),
     _p("Phi", "Control (In)", "旋转角 (度)"), _p("Interpolation", "Control (In)", "插值方式")],
    "rotate_image (Image, ImageRotate, 5, 'bilinear')\n"),

  // 交互与流程
  _manualEntry("display", "视口与显示", "draw_rectangle1",
    "draw_rectangle1 (WindowHandle, Row1, Column1, Row2, Column2)", "(: : WindowHandle : Row1, Column1, Row2, Column2)",
    "读取运行前在视口里用“矩形”工具画好的矩形 ROI (脚本一次性运行，不能中途等鼠标)。没画矩形会报错提示。",
    [_p("WindowHandle", "Control (In)", "窗口句柄"), _p("Row1, Column1", "Control (Out)", "左上角"), _p("Row2, Column2", "Control (Out)", "右下角")],
    "draw_rectangle1 (WindowHandle, Row1, Column1, Row2, Column2)\ngen_rectangle1 (Rectangle1, Row1, Column1, Row2, Column2)\n"),
  _manualEntry("display", "视口与显示", "dev_get_window",
    "dev_get_window (WindowHandle)", "(: : : WindowHandle)",
    "取得当前活动图形窗口的句柄。", [_p("WindowHandle", "Control (Out)", "窗口句柄")],
    "dev_get_window (WindowHandle)\n"),
  _manualEntry("file", "文件与流程", "stop",
    "stop ()", "(: : :)",
    "让程序在这里停止，其后的语句不再执行 (HDevelop 里是暂停，本平台一次性运行，直接结束)。常用于检查失败时的保护，如分割个数不对就报错并 stop。",
    [], "if (Number # 10)\n    disp_message (WindowHandle, 'error', 'window', 0, 0, 'red', 'false')\n    stop ()\nendif\n"),
  _manualEntry("file", "文件与流程", "open_file",
    "open_file (FileName, Mode, FileHandle)", "(: : FileName, Mode : FileHandle)",
    "在工作区打开文本文件，Mode 为 'output' (覆盖写) 或 'append' (追加)。脚本给出的路径只取文件名部分；脚本结束时没有关闭的文件会自动关闭。",
    [_p("FileName", "Control (In)", "文件名"), _p("Mode", "Control (In)", "'output' 或 'append'"), _p("FileHandle", "Control (Out)", "文件句柄")],
    "open_file ('result.txt', 'output', FileHandle)\n"),
  _manualEntry("file", "文件与流程", "fwrite_string",
    "fwrite_string (FileHandle, String)", "(: : FileHandle, String :)",
    "向文件写入文字 (UTF-8)，String 可以是元组，各项直接连接。",
    [_p("FileHandle", "Control (In)", "文件句柄"), _p("String", "Control (In)", "文字")],
    "fwrite_string (FileHandle, 'date: ' + str1)\n"),
  _manualEntry("file", "文件与流程", "fnew_line",
    "fnew_line (FileHandle)", "(: : FileHandle :)",
    "写入一个换行。", [_p("FileHandle", "Control (In)", "文件句柄")], "fnew_line (FileHandle)\n"),
  _manualEntry("file", "文件与流程", "close_file",
    "close_file (FileHandle)", "(: : FileHandle :)",
    "关闭文件。", [_p("FileHandle", "Control (In)", "文件句柄")], "close_file (FileHandle)\n"),
  _manualEntry("file", "文件与流程", "list_files",
    "list_files (Directory, Options, Files)", "(: : Directory, Options : Files)",
    "列出目录下的文件 (不递归，只含文件)，返回以斜杠分隔的完整路径，按文件名排序。'files'、'follow_links' 选项被接受；暂不支持 'directories'、'recursive'。",
    [_p("Directory", "Control (In)", "目录"), _p("Options", "Control (In)", "选项"), _p("Files", "Control (Out)", "文件路径元组")],
    "list_files (Path, ['files', 'follow_links'], ImageFiles)\n"),
  _manualEntry("file", "文件与流程", "tuple_regexp_select",
    "tuple_regexp_select (Data, Expression, Selected)", "(: : Data, Expression : Selected)",
    "从字符串元组里选出匹配正则表达式的项。Expression 可写成 [正则, 'ignore_case']。HALCON 字符串里两个反斜杠表示一个反斜杠，本平台按同样规则处理。",
    [_p("Data", "Control (In)", "字符串元组"), _p("Expression", "Control (In)", "正则表达式"), _p("Selected", "Control (Out)", "匹配的项")],
    "tuple_regexp_select (ImageFiles, ['[.](bmp|jpg|jpeg)$', 'ignore_case'], ImageFiles)\n")
);

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
