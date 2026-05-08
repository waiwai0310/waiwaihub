"""
ResultSaver 自检：一律写入系统临时目录，勿向 output/ 写测试文件。

运行（项目根目录）：
  python -m unittest tests.test_result_saver -v
"""

import os
import tempfile
import unittest

import pandas as pd

from result_saver import ResultSaver


class TestResultSaver(unittest.TestCase):
    def test_save_result_freeze_and_filter_in_temp_dir(self):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("需要 openpyxl")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saver = ResultSaver(base_path=tmp)
            df = pd.DataFrame({"列a": [1], "列b": [2]})
            out = saver.save_result(df, "result_saver_selftest.xlsx")

            self.assertEqual(os.path.dirname(os.path.abspath(out)), os.path.abspath(tmp))

            wb = load_workbook(out)
            ws = wb.active
            self.assertEqual(ws.freeze_panes, "A2")
            self.assertIsNotNone(ws.auto_filter.ref)
            wb.close()


if __name__ == "__main__":
    unittest.main()
