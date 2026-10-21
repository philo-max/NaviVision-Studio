"""
字符识别实训所需功能的测试: 续行符、区域排序、外接矩形、二值化、OCR 训练与保存、文件读写、图像矫正等。
每个测试使用独立的临时工作区, 不会碰用户真实目录。
"""

import math
import os
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from core import hdev_geometry as geo
from core import operators as ops
from core import text_region_ops
from core.hdev_engine import HDevInterpreter, HDevParser, _draw_messages
from core.types import Region
from core.workspace import WORKSPACE_ENV, workspace_path


def _glyph_image(text="369", size=(120, 360)):
    img = np.full(size + (3,), 255, dtype=np.uint8)
    for i, ch in enumerate(text):
        cv2.putText(img, ch, (30 + i * 100, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 4, cv2.LINE_AA)
    return img


def _letters_image(text, thickness=3):
    img = np.full((90, 60 + 70 * len(text), 3), 255, np.uint8)
    for i, ch in enumerate(text):
        cv2.putText(img, ch, (20 + i * 70, 65), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), thickness, cv2.LINE_AA)
    return img


class WorkspaceTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get(WORKSPACE_ENV)
        os.environ[WORKSPACE_ENV] = self._tmp.name
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        if self._old is None:
            os.environ.pop(WORKSPACE_ENV, None)
        else:
            os.environ[WORKSPACE_ENV] = self._old
        self._tmp.cleanup()

    def run_script(self, code, image=None, roi=None):
        it = HDevInterpreter(base_image=image if image is not None else _glyph_image())
        it.roi_geometry = roi
        res = it.execute_script(code, timeout_sec=60)
        return it, res


class ParserContinuationTests(unittest.TestCase):

    def test_trailing_backslash_joins_the_next_line(self):
        code = "disp_message (WindowHandle, 'x', 'image',\\\n10, 20, 'red', 'true')\nX := 1"
        instructions = HDevParser.parse_script(code)
        self.assertEqual(len(instructions), 2)
        self.assertEqual(instructions[0].control_in[3:5], [10, 20])
        self.assertEqual(instructions[0].line_num, 1)
        self.assertEqual(instructions[1].line_num, 3)

    def test_backslash_after_comment_does_not_swallow_code(self):
        instructions = HDevParser.parse_script("* path C:\\dir\\\nX := 1")
        self.assertEqual([i.op_type for i in instructions], ["assign"])

    def test_script_with_continuation_runs(self):
        it = HDevInterpreter(base_image=_glyph_image())
        res = it.execute_script("disp_message (WindowHandle, 'ok', 'image',\\\n10, 20, 'red', 'true')")
        self.assertTrue(res["success"], res.get("error"))


class RegionOperatorTests(WorkspaceTestCase):

    def test_smallest_rectangle1_is_inclusive(self):
        mask = np.zeros((20, 30), np.uint8)
        mask[2:5, 3:8] = 255
        mask[10:15, 20:22] = 255
        it = HDevInterpreter(base_image=_glyph_image())
        it.iconic_vars["R"] = Region(mask=mask)
        res = it.execute_script("connection (R, C)\nsmallest_rectangle1 (C, Row1, Column1, Row2, Column2)")
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.control_vars["Row1"], [2, 10])
        self.assertEqual(it.control_vars["Column1"], [3, 20])
        self.assertEqual(it.control_vars["Row2"], [4, 14])
        self.assertEqual(it.control_vars["Column2"], [7, 21])

    def test_sort_region_character_orders_lines_then_columns(self):
        mask = np.zeros((60, 100), np.uint8)
        for row, col in ((5, 60), (5, 10), (35, 40), (35, 5)):
            mask[row:row + 12, col:col + 10] = 255
        region = ops.connection(Region(mask=mask))
        by_row = text_region_ops.sort_region(region, "character", "true", "row")
        self.assertEqual([o.bbox[1] for o in by_row.objects], [10, 60, 5, 40])
        reverse = text_region_ops.sort_region(region, "character", "false", "row")
        self.assertEqual([o.bbox[1] for o in reverse.objects], [40, 5, 60, 10])
        # 按列: 水平中心相差不超过半个字宽的块算同一列 (左边界 5 和 10 同列, 列内自上而下)
        by_col = text_region_ops.sort_region(region, "character", "true", "column")
        self.assertEqual([o.bbox[1] for o in by_col.objects], [10, 5, 40, 60])
        self.assertTrue(by_row.ordered)
        with self.assertRaises(ValueError):
            text_region_ops.sort_region(region, "nonsense", "true", "row")

    def test_select_shape_does_not_pull_in_pixels_of_neighbours_with_overlapping_bboxes(self):
        mask = np.zeros((40, 40), np.uint8)
        mask[5:30, 5:9] = 255
        mask[26:30, 5:30] = 255
        mask[8:11, 20:23] = 255
        region = ops.connection(Region(mask=mask))
        self.assertEqual(len(region.objects), 2)
        big = ops.select_shape(region, min_area=50)
        self.assertEqual(len(big.objects), 1)
        self.assertFalse(big.mask[8:11, 20:23].any(), "邻近噪点落在 L 形外接框内, 不应被带回来")

    def test_binary_threshold_honours_dark_light_and_domain(self):
        img = np.full((60, 80, 3), 230, np.uint8)
        img[20:40, 20:40] = 30
        script = ("rgb1_to_gray (Image, Gray)\nbinary_threshold (Gray, Dark, 'max_separability', 'dark', T1)\n"
                  "binary_threshold (Gray, Light, 'max_separability', 'light', T2)")
        it, res = self.run_script(script, image=img)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(int(np.count_nonzero(it.iconic_vars["Dark"].mask)), 20 * 20)
        self.assertEqual(int(np.count_nonzero(it.iconic_vars["Light"].mask)), 60 * 80 - 20 * 20)
        self.assertEqual(it.control_vars["T1"], it.control_vars["T2"])
        it, res = self.run_script(
            "gen_rectangle1 (R, 0, 0, 59, 79)\nreduce_domain (Image, R, IR)\nrgb1_to_gray (IR, G)\n"
            "binary_threshold (G, D, 'smooth_histo', 'dark', T)", image=img)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(int(np.count_nonzero(it.iconic_vars["D"].mask)), 20 * 20)
        self.assertFalse(self.run_script("binary_threshold (Image, D, 'bogus', 'dark', T)")[1]["success"])

    def test_binary_threshold_ignores_pixels_outside_the_roi(self):
        img = np.full((60, 80, 3), 230, np.uint8)
        img[20:40, 20:40] = 30
        script = ("gen_rectangle1 (R, 10, 10, 50, 50)\nreduce_domain (Image, R, IR)\nrgb1_to_gray (IR, G)\n"
                  "binary_threshold (G, D, 'max_separability', 'dark', T)")
        it, res = self.run_script(script, image=img)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(int(np.count_nonzero(it.iconic_vars["D"].mask)), 20 * 20, "ROI 外被置 0 的像素不能算作暗目标")

    def test_char_threshold_finds_dark_characters(self):
        it, res = self.run_script(
            "rgb1_to_gray (Image, G)\nchar_threshold (G, G, Chars, 2, 95, Thr)\nconnection (Chars, C)\ncount_obj (C, N)")
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.control_vars["N"], 3)
        self.assertTrue(0 < it.control_vars["Thr"] < 255)

    def test_draw_rectangle1_reads_the_drawn_rectangle(self):
        roi = {"type": "rect", "x": 10, "y": 20, "w": 30, "h": 40}
        it, res = self.run_script("draw_rectangle1 (W, R1, C1, R2, C2)", roi=roi)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual([it.control_vars[k] for k in ("R1", "C1", "R2", "C2")], [20, 10, 59, 39])
        self.assertFalse(self.run_script("draw_rectangle1 (W, R1, C1, R2, C2)")[1]["success"])
        circle = {"type": "circle", "cx": 1, "cy": 1, "r": 3}
        self.assertFalse(self.run_script("draw_rectangle1 (W, R1, C1, R2, C2)", roi=circle)[1]["success"])


class ScriptSemanticsTests(WorkspaceTestCase):

    def test_stop_ends_the_script_without_error(self):
        it, res = self.run_script("A := 1\nstop ()\nB := 2")
        self.assertTrue(res["success"], res.get("error"))
        self.assertIn("A", it.control_vars)
        self.assertNotIn("B", it.control_vars)

    def test_tuple_index_out_of_range_is_an_error_not_a_string(self):
        _, res = self.run_script("T := [1, 2]\nfor I := 0 to 3 by 1\nV := T[I]\nendfor")
        self.assertFalse(res["success"])
        self.assertIn("下标越界", res["error"])
        it, res = self.run_script("P := samples/a.png\nName := 'x'")
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.control_vars["P"], "samples/a.png")

    def test_dev_get_window_returns_current_window(self):
        it, res = self.run_script("dev_open_window (0, 0, 10, 10, 'black', W)\ndev_get_window (Handle)")
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.control_vars["Handle"], it.control_vars["W"])


class FileAndOcrTests(WorkspaceTestCase):

    def test_file_output_is_confined_to_the_workspace(self):
        script = ("open_file ('../../escape/result.txt', 'output', F)\nfwrite_string (F, 'ABC')\nfnew_line (F)\n"
                  "fwrite_string (F, ['1', '2'])\nclose_file (F)")
        _, res = self.run_script(script)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual((self.ws / "result.txt").read_text(encoding="utf-8"), "ABC\n12")
        self.assertFalse(self.run_script("open_file ('a.txt', 'weird', F)")[1]["success"])
        self.assertFalse(self.run_script("fwrite_string (99, 'x')")[1]["success"])

    def test_unclosed_files_are_flushed_when_the_script_ends(self):
        self.run_script("open_file ('keep.txt', 'output', F)\nfwrite_string (F, 'data')")
        self.assertEqual((self.ws / "keep.txt").read_text(encoding="utf-8"), "data")

    def test_workspace_path_drops_directories(self):
        self.assertEqual(workspace_path("C:/Users/x/Desktop/model.omc").parent, self.ws)
        self.assertEqual(workspace_path("..\\..\\evil.trf").name, "evil.trf")
        with self.assertRaises(ValueError):
            workspace_path("..")

    def test_train_save_reload_and_recognise_custom_characters(self):
        train = ("rgb1_to_gray (Image, G)\nthreshold (G, R, 0, 128)\nconnection (R, C)\n"
                 "sort_region (C, S, 'character', 'true', 'row')\ncount_obj (S, N)\nwords := ['K', 'M', 'W', 'Q']\n"
                 "for I := 1 to N by 1\n    select_obj (S, O, I)\n    append_ocr_trainf (O, G, words[I - 1], 'my.trf')\nendfor\n"
                 "read_ocr_trainf_names ('my.trf', Names, Counts)\n"
                 "create_ocr_class_mlp (8, 10, 'constant', 'default',\\\nNames, 80, 'none', 10, 42, H)\n"
                 "trainf_ocr_class_mlp (H, 'my.trf', 200, 1, 0.01, Error, ErrorLog)\n"
                 "write_ocr_class_mlp (H, 'my.omc')\nclear_ocr_class_mlp (H)")
        it, res = self.run_script(train, image=_letters_image("KMWQ"))
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.control_vars["Names"], ["K", "M", "W", "Q"])
        self.assertEqual(it.control_vars["Counts"], [1, 1, 1, 1])
        self.assertLess(it.control_vars["Error"], 0.05)
        self.assertTrue((self.ws / "my.trf").exists() and (self.ws / "my.omc").exists())
        self.assertNotIn(0, it.ocr_handles)

        recognise = ("rgb1_to_gray (Image, G)\nthreshold (G, R, 0, 128)\nconnection (R, C)\n"
                     "sort_region (C, S, 'character', 'true', 'row')\nread_ocr_class_mlp ('my.omc', H)\n"
                     "do_ocr_multi_class_mlp (S, G, H, Class, Confidence)")
        it, res = self.run_script(recognise, image=_letters_image("KWMQ", thickness=4))
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.control_vars["Class"], ["K", "W", "M", "Q"])
        self.assertTrue(all(c > 0.5 for c in it.control_vars["Confidence"]))

    def test_sort_region_order_is_honoured_by_ocr(self):
        train = ("rgb1_to_gray (Image, G)\nthreshold (G, R, 0, 128)\nconnection (R, C)\n"
                 "sort_region (C, S, 'character', 'true', 'row')\nwords := ['K', 'M']\n"
                 "for I := 1 to 2 by 1\n    select_obj (S, O, I)\n    append_ocr_trainf (O, G, words[I - 1], 't.trf')\nendfor\n"
                 "read_ocr_trainf_names ('t.trf', Names, Counts)\n"
                 "create_ocr_class_mlp (8, 10, 'constant', 'default', Names, 40, 'none', 10, 42, H)\n"
                 "trainf_ocr_class_mlp (H, 't.trf', 100, 1, 0.01, Err, Log)\nwrite_ocr_class_mlp (H, 't.omc')")
        self.assertTrue(self.run_script(train, image=_letters_image("KM"))[1]["success"])
        script = ("rgb1_to_gray (Image, G)\nthreshold (G, R, 0, 128)\nconnection (R, C)\nread_ocr_class_mlp ('t.omc', H)\n"
                  "sort_region (C, S, 'character', 'false', 'row')\ndo_ocr_multi_class_mlp (S, G, H, Class, Conf)")
        it, res = self.run_script(script, image=_letters_image("KM"))
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.control_vars["Class"], ["M", "K"])

    def test_error_cases_for_ocr_operators(self):
        _, res = self.run_script("read_ocr_class_mlp ('missing_font.omc', H)")
        self.assertFalse(res["success"])
        self.assertIn("找不到分类器文件", res["error"])
        _, res = self.run_script("read_ocr_class_mlp ('Industrial_0-9+_NoRej.omc', H)")
        self.assertTrue(res["success"], res.get("error"))
        self.assertFalse(self.run_script("trainf_ocr_class_mlp (7, 'x.trf', 10, 1, 0.01, E, L)")[1]["success"])
        too_few = "create_ocr_class_mlp (8, 10, 'constant', 'default', ['A'], 80, 'none', 10, 42, H)"
        self.assertFalse(self.run_script(too_few)[1]["success"])
        (self.ws / "bad.omc").write_text("not json", encoding="utf-8")
        self.assertFalse(self.run_script("read_ocr_class_mlp ('bad.omc', H)")[1]["success"])
        (self.ws / "evil.omc").write_text('{"format": "other"}', encoding="utf-8")
        self.assertFalse(self.run_script("read_ocr_class_mlp ('evil.omc', H)")[1]["success"])

    def test_append_requires_matching_class_count(self):
        script = ("rgb1_to_gray (Image, G)\nthreshold (G, R, 0, 128)\nconnection (R, C)\n"
                  "append_ocr_trainf (C, G, ['A', 'B'], 'x.trf')")
        _, res = self.run_script(script)
        self.assertFalse(res["success"])
        self.assertIn("不一致", res["error"])


class RectificationAndDisplayTests(WorkspaceTestCase):

    def test_affine_trans_image_moves_a_pixel_like_the_matrix_says(self):
        img = np.zeros((60, 80), np.uint8)
        img[10, 20] = 255
        mat = geo.rotate(geo.translate(geo.identity(), 5, 7), math.radians(30), 30, 40)
        out = geo.affine_trans_image(img, mat, "nearest_neighbor")
        row, col = geo.apply_to_point(mat, 10, 20)
        ys, xs = np.nonzero(out)
        self.assertEqual((int(ys[0]), int(xs[0])), (round(row), round(col)))

    def test_rotate_image_is_counter_clockwise_and_scripts_can_chain_it(self):
        img = np.zeros((101, 101), np.uint8)
        img[50, 90] = 255
        out = geo.rotate_image(img, 90, "nearest_neighbor")
        ys, xs = np.nonzero(out)
        self.assertEqual((int(ys[0]), int(xs[0])), (10, 50))
        it, res = self.run_script(
            "hom_mat2d_identity (M0)\nhom_mat2d_rotate (M0, rad(10), 60, 180, M1)\n"
            "affine_trans_image (Image, Out, M1, 'bilinear', 'false')\nrotate_image (Image, Out2, 5, 'bilinear')")
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(it.iconic_vars["Out"].shape, it.iconic_vars["Image"].shape)
        self.assertFalse(self.run_script("rotate_image (Image, O, 5, 'sinc')")[1]["success"])

    def test_chinese_messages_are_drawn(self):
        img = np.full((60, 200, 3), 255, np.uint8)
        out = _draw_messages(img, [{"text": "结果: 测试", "row": 5, "col": 5, "color": "red", "box": False}])
        self.assertGreater(int((out != 255).any(axis=2).sum()), 200)


if __name__ == "__main__":
    unittest.main()
