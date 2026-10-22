"""
实训脚本 (assignment/ocr/*.hdev) 的端到端回归测试: 每个练习脚本在独立的临时工作区里完整运行, 并检查关键结果。
脚本里的图片路径是作者本机的绝对路径, 测试时统一替换为当前项目目录。
"""

import os
import tempfile
import unittest
from pathlib import Path

from core.hdev_engine import HDevInterpreter
from core.workspace import WORKSPACE_ENV

PROJECT = Path(__file__).resolve().parent
SCRIPTS = PROJECT / "assignment" / "ocr"
AUTHOR_ROOT = "F:/计算机视觉/NaviVision_Studio/"
EXAM_TRUTH = ("20160713", "6612A15:36B")


class ExerciseScriptTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._old = os.environ.get(WORKSPACE_ENV)
        os.environ[WORKSPACE_ENV] = cls._tmp.name
        cls.ws = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        if cls._old is None:
            os.environ.pop(WORKSPACE_ENV, None)
        else:
            os.environ[WORKSPACE_ENV] = cls._old
        cls._tmp.cleanup()

    def run_script(self, name, roi=None):
        code = (SCRIPTS / name).read_text(encoding="utf-8").replace(AUTHOR_ROOT, PROJECT.as_posix() + "/")
        it = HDevInterpreter()
        it.roi_geometry = roi
        res = it.execute_script(code, timeout_sec=120)
        self.assertTrue(res["success"], f"{name}: {res.get('error')}")
        return it

    @staticmethod
    def hits(got, truth):
        return sum(1 for a, b in zip(got, truth) if a == b)

    def test_exercise_1_digits_369(self):
        it = self.run_script("L8T2_digits.hdev", {"type": "rect", "x": 15, "y": 40, "w": 130, "h": 65})
        self.assertEqual(it.control_vars["Class"], ["3", "6", "9"])
        self.assertEqual(it.control_vars["strResult"], "369")
        self.assertEqual(it.control_vars["UsedThreshold"], 138)

    def test_exercise_2_original_parameters_miss_the_big_letters(self):
        it = self.run_script("L8T2_abc123.hdev")
        self.assertEqual("".join(it.control_vars["Class"]), "JCIZ3")

    def test_exercise_2_tuned_area_finds_every_character(self):
        it = self.run_script("L8T2_abc123_tuned.hdev")
        self.assertEqual(len(it.control_vars["Class"]), 6)
        self.assertEqual("".join(it.control_vars["Class"])[:3], "ABC")

    def test_exercise_2_rows_use_separate_classifiers(self):
        it = self.run_script("L8T2_abc123_rows.hdev")
        self.assertEqual(it.control_vars["LetterClass"], ["A", "B", "C"])
        self.assertEqual(it.control_vars["DigitClass"], ["1", "2", "3"])

    def test_exercise_3_chinese_characters_train_and_read(self):
        it = self.run_script("L8T3_hanzi.hdev")
        self.assertEqual(it.control_vars["Number"], 4)
        self.assertEqual(it.control_vars["Class"], ["测", "试", "中", "文"])
        self.assertLess(it.control_vars["Error"], 0.05)

    def test_exercise_3_extension_mixed_characters(self):
        it = self.run_script("L8T3_plate.hdev")
        self.assertEqual(it.control_vars["Number"], 7)
        self.assertEqual("".join(it.control_vars["Class"]), "京AT0H69")

    def test_notes_09_train_then_detect(self):
        it = self.run_script("Notes_train.hdev")
        self.assertEqual(it.control_vars["CharacterNames"], [str(d) for d in range(10)])
        self.run_script("Notes_detect.hdev")
        lines = (self.ws / "notes_detect_result.txt").read_text(encoding="utf-8").splitlines()
        results = {line.split("  ->  ")[0].rsplit("/", 1)[-1]: line.split("  ->  ")[1] for line in lines}
        self.assertEqual(results, {"Test1.bmp": "5081372946", "Test2.bmp": "9274650183",
                                   "Test3.jpg": "3615907248", "Traning.bmp": "0123456789"})

    def test_exam_rectification_fixes_the_first_line_and_training_reads_everything(self):
        basic = self.run_script("Exam1_basic.hdev")
        rectified = self.run_script("Exam2_rectify.hdev")
        first = lambda it: "".join(it.control_vars["Class1"])
        self.assertLess(self.hits(first(basic), EXAM_TRUTH[0]), 8)
        self.assertEqual(first(rectified), EXAM_TRUTH[0])
        self.assertAlmostEqual(rectified.control_vars["BlockPhi"][0], 0.0449, places=3)
        final = self.run_script("Exam3_final.hdev")
        self.assertEqual(final.control_vars["str1"], "20160713")
        self.assertEqual(final.control_vars["str2"], "6612A 15:36B")
        saved = (self.ws / "wangzetong_result.txt").read_text(encoding="utf-8")
        self.assertIn("20160713", saved)
        self.assertIn("6612A 15:36B", saved)


if __name__ == "__main__":
    unittest.main()
