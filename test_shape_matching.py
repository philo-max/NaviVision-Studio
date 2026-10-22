"""
形状模板匹配与仿射变换测试: 用合成字形验证位置 / 角度 / 缩放的还原精度,
并检查 "找到的位姿 + 轮廓仿射变换" 画出的轮廓与图像边缘重合 (验证角度方向约定一致)。
"""

import math
import unittest

import cv2
import numpy as np

from core import hdev_geometry as geo
from core.shape_model import create_shape_model
from core.shape_search import find_shape_models

GLYPH = [(-40, -30), (-40, 30), (-10, 30), (-10, 0), (40, 0), (40, -30)]
CENTER = (150, 150)
DOMAIN_RADIUS = 70


def _draw_glyph(canvas, row, col, angle, scale):
    mat = geo.translate(geo.scale(geo.rotate(geo.identity(), angle, 0, 0), scale, scale, 0, 0), row, col)
    pts = np.array([geo.apply_to_point(mat, r, c) for r, c in GLYPH])
    cv2.fillPoly(canvas, [np.round(pts[:, ::-1]).astype(np.int32)], 40, lineType=cv2.LINE_AA)


def _scene(placements, shape=(400, 500)):
    img = np.full(shape, 220, dtype=np.uint8)
    for row, col, angle, scale in placements:
        _draw_glyph(img, row, col, angle, scale)
    return img


def _model(**overrides):
    template = _scene([(*CENTER, 0.0, 1.0)], shape=(300, 300))
    domain = np.zeros(template.shape, dtype=bool)
    cv2.circle(domain.view(np.uint8), (CENTER[1], CENTER[0]), DOMAIN_RADIUS, 1, -1)
    params = dict(num_levels=5, angle_start=-math.radians(45), angle_extent=math.radians(90),
                  angle_step="auto", scale_min=0.8, scale_max=1.0, scale_step="auto",
                  metric="ignore_global_polarity", contrast=40, min_contrast=10)
    params.update(overrides)
    return create_shape_model(template, domain, params["num_levels"], params["angle_start"],
                              params["angle_extent"], params["angle_step"], params["scale_min"],
                              params["scale_max"], params["scale_step"], params["metric"],
                              params["contrast"], params["min_contrast"])


def _search(img, model, min_score=0.8, num_matches=0):
    return find_shape_models(img, model, -math.radians(45), math.radians(90), 0.8, 1.0,
                             min_score, num_matches, 0.5, "least_squares", 5)


class ShapeMatchingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.model = _model()

    def test_model_origin_is_domain_centre_and_contours_exist(self):
        self.assertAlmostEqual(self.model.origin[0], DOMAIN_RADIUS, delta=1.0)
        self.assertGreater(len(self.model.contours), 0)

    def test_finds_rotated_and_scaled_instance(self):
        for angle_deg, scale in ((30, 0.9), (-20, 1.0), (0, 0.8), (44, 0.85)):
            img = _scene([(190, 310, math.radians(angle_deg), scale)])
            found = _search(img, self.model)
            self.assertEqual(len(found), 1, (angle_deg, scale))
            hit = found[0]
            self.assertAlmostEqual(hit["row"], 190, delta=2.0, msg=(angle_deg, scale))
            self.assertAlmostEqual(hit["column"], 310, delta=2.0, msg=(angle_deg, scale))
            self.assertAlmostEqual(hit["angle"], math.radians(angle_deg), delta=math.radians(2.5), msg=(angle_deg, scale))
            self.assertAlmostEqual(hit["scale"], scale, delta=0.05, msg=(angle_deg, scale))
            self.assertGreater(hit["score"], 0.8)

    def test_two_instances_and_empty_scene(self):
        img = _scene([(100, 120, math.radians(15), 0.95), (280, 360, math.radians(-30), 0.85)])
        found = _search(img, self.model)
        self.assertEqual(len(found), 2)
        rows = sorted(round(f["row"]) for f in found)
        self.assertAlmostEqual(rows[0], 100, delta=2)
        self.assertAlmostEqual(rows[1], 280, delta=2)
        self.assertEqual(len(_search(img, self.model, num_matches=1)), 1)
        blank = np.random.default_rng(0).integers(200, 230, (400, 500)).astype(np.uint8)
        self.assertEqual(_search(blank, self.model), [])

    def test_inverted_polarity_is_found_when_ignoring_global_polarity(self):
        img = 255 - _scene([(200, 250, math.radians(10), 0.9)])
        self.assertEqual(len(_search(img, self.model)), 1)
        strict = _model(metric="use_polarity")
        self.assertEqual(_search(img, strict), [])

    def test_transformed_model_contours_lie_on_image_edges(self):
        placed = (200, 260, math.radians(25), 0.9)
        img = _scene([placed])
        hit = _search(img, self.model)[0]
        mat = geo.identity()
        mat = geo.translate(mat, hit["row"], hit["column"])
        mat = geo.rotate(mat, hit["angle"], hit["row"], hit["column"])
        mat = geo.scale(mat, hit["scale"], hit["scale"], hit["row"], hit["column"])
        contours = geo.affine_trans_contours(self.model.contours, mat)
        edges = cv2.Canny(img, 40, 120)
        distance = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 3)
        pts = np.array([p for c in contours for p in c.points])
        rows = np.clip(np.round(pts[:, 0]).astype(int), 0, img.shape[0] - 1)
        cols = np.clip(np.round(pts[:, 1]).astype(int), 0, img.shape[1] - 1)
        self.assertLess(float(np.mean(distance[rows, cols])), 2.5)


SCRIPT = """
get_image_size (Image, Width, Height)
draw_circle (WindowHandle, Rowl, Columnl, Radius)
gen_circle (Circle, Rowl, Columnl, Radius)
reduce_domain (Image, Circle, ImageReduced)
create_scaled_shape_model (ImageReduced, 5, rad(-45), rad(90), 'auto', 0.8, 1.0, 'auto', 'none', 'ignore_global_polarity', 40, 10, ModelID)
get_shape_model_contours (Model, ModelID, 1)
find_scaled_shape_model (ImageSearch, ModelID, rad(-45), rad(90), 0.8, 1.0, 0.5, 0, 0.5, 'least_squares', 5, 0.8, Row, Column, Angle, Scale, Score)
dev_display (ImageSearch)
dev_disp_text ('count:' + |Score|, 'window', 'top', 'left', 'black', [], [])
for I := 0 to |Score| - 1 by 1
    hom_mat2d_identity (HomMat2DIdentity)
    hom_mat2d_translate (HomMat2DIdentity, Row[I], Column[I], HomMat2DTranslate)
    hom_mat2d_rotate (HomMat2DTranslate, Angle[I], Row[I], Column[I], HomMat2DRotate)
    hom_mat2d_scale (HomMat2DRotate, Scale[I], Scale[I], Row[I], Column[I], HomMat2DScale)
    affine_trans_contour_xld (Model, ModelTrans, HomMat2DScale)
    dev_display (ModelTrans)
endfor
disp_message (WindowHandle, 'score:' + Score, 'image', Row, Column - 80, 'black', 'true')
"""


class EngineScriptTests(unittest.TestCase):

    def _interpreter(self, roi, placements):
        from core.hdev_engine import HDevInterpreter
        template = cv2.cvtColor(_scene([(*CENTER, 0.0, 1.0)], shape=(300, 300)), cv2.COLOR_GRAY2BGR)
        it = HDevInterpreter(base_image=template)
        it.iconic_vars["ImageSearch"] = cv2.cvtColor(_scene(placements), cv2.COLOR_GRAY2BGR)
        it.roi_geometry = roi
        return it

    def test_full_script_finds_and_annotates_every_instance(self):
        roi = {"type": "circle", "cx": CENTER[1], "cy": CENTER[0], "r": DOMAIN_RADIUS}
        it = self._interpreter(roi, [(100, 120, math.radians(15), 0.95), (280, 360, math.radians(-30), 0.85)])
        res = it.execute_script(SCRIPT, timeout_sec=30)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(len(it.control_vars["Score"]), 2)
        self.assertEqual(it.control_vars["Rowl"], float(CENTER[0]))
        self.assertTrue(all(isinstance(v, float) for v in it.control_vars["Row"]))
        sent = np.array([pt for contour in res["contours"] for pt in contour])
        self.assertAlmostEqual(sent[:, 0].mean(), (120 + 360) / 2, delta=25, msg="轮廓点应以 [列, 行] 即 [x, y] 发送给画布")
        self.assertAlmostEqual(sent[:, 1].mean(), (100 + 280) / 2, delta=25)
        per_model = len(it.shape_models[0].contours)
        self.assertGreater(per_model, 0)
        self.assertEqual(len(res["contours"]), 2 * per_model)
        window = it._cur_win()
        self.assertEqual(len(window.messages), 3)
        self.assertEqual(window.messages[0]["text"], "count:2")
        self.assertEqual(len(window.xld_names), 2)

    def test_draw_circle_without_a_drawn_circle_explains_what_to_do(self):
        it = self._interpreter(None, [(100, 120, 0.0, 1.0)])
        res = it.execute_script("draw_circle (WindowHandle, R, C, Rad)")
        self.assertFalse(res["success"])
        self.assertIn("圆", res["error"])
        it.roi_geometry = {"type": "rect", "x": 0, "y": 0, "w": 5, "h": 5}
        self.assertFalse(it.execute_script("draw_circle (WindowHandle, R, C, Rad)")["success"])

    def test_unknown_dev_operators_are_no_longer_swallowed(self):
        it = self._interpreter(None, [])
        self.assertFalse(it.execute_script("dev_made_up_operator (1)")["success"])
        self.assertTrue(it.execute_script("dev_update_off ()\ndev_set_part (0, 0, 100, 100)")["success"])


class HomMat2DTests(unittest.TestCase):

    def test_identity_translate_rotate_scale_compose(self):
        mat = geo.translate(geo.identity(), 10, 20)
        self.assertEqual(geo.apply_to_point(mat, 0, 0), (10.0, 20.0))
        mat = geo.rotate(mat, math.pi / 2, 10, 20)
        row, col = geo.apply_to_point(mat, 0, 0)
        self.assertAlmostEqual(row, 10.0)
        self.assertAlmostEqual(col, 20.0)
        row, col = geo.apply_to_point(geo.rotate(geo.identity(), math.pi / 2, 0, 0), 1, 0)
        self.assertAlmostEqual(row, 0.0, places=9)
        self.assertAlmostEqual(col, 1.0)
        scaled = geo.scale(geo.identity(), 2, 2, 5, 5)
        self.assertEqual(geo.apply_to_point(scaled, 5, 5), (5.0, 5.0))
        self.assertEqual(geo.apply_to_point(scaled, 6, 5), (7.0, 5.0))

    def test_vector_angle_to_rigid_maps_pose(self):
        mat = geo.vector_angle_to_rigid(0, 0, 0, 30, 40, 0)
        self.assertEqual(geo.apply_to_point(mat, 1, 1), (31.0, 41.0))
        mat = geo.vector_angle_to_rigid(10, 10, 0, 50, 60, math.pi / 2)
        row, col = geo.apply_to_point(mat, 10, 10)
        self.assertAlmostEqual(row, 50.0)
        self.assertAlmostEqual(col, 60.0)

    def test_invalid_matrix_is_rejected(self):
        with self.assertRaises(ValueError):
            geo.translate([1, 2, 3], 0, 0)


if __name__ == "__main__":
    unittest.main()
