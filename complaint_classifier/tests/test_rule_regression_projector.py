"""
投影仪规则回归测试集（基于真实评论样本）。

运行（项目根目录）：
  python -m unittest tests.test_rule_regression_projector -v
"""

import json
import os
import unittest

from classifier import ClassifyEngine


class TestProjectorRuleRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "投影仪",
            "config.json",
        )
        with open(config_path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        cls.engine = ClassifyEngine.build_from_config(cfg, None)

    def assert_expected_hits(self, text, expected):
        result = self.engine.classify(text)
        for col, expected_values in expected.items():
            actual = str(result.get(col, "")).strip()
            self.assertTrue(
                actual in expected_values,
                msg=f"文本: {text}\n列: {col}\n实际: {actual}\n期望之一: {expected_values}",
            )

    def assert_non_empty_hits(self, text, expected_columns):
        result = self.engine.classify(text)
        for col in expected_columns:
            actual = str(result.get(col, "")).strip()
            self.assertTrue(
                bool(actual),
                msg=f"文本: {text}\n列: {col}\n实际为空，期望非空命中",
            )

    def test_regression_cases(self):
        cases = [
            {"text": "如果你有暗房和光滑的墙面，性价比很高。", "expected": {"性价比": ["性价比高"]}},
            {
                "text": "非常容易使用。非常清晰且响亮。",
                "expected": {"清晰度/分辨率": ["清晰"]},
            },
            {
                "text": "几乎完美，但350流明时画面太暗了。不过音质非常好。",
                "expected": {"亮度": ["亮度不足"]},
            },
            {
                "text": "这是卧室投影仪，自动对焦很好，还能保持画面清晰。",
                "expected": {"卧室投屏": ["卧室"], "对焦/校正": ["自动对焦快", "对焦准"]},
            },
            {
                "text": "支持蓝牙音箱，但接口非常有限，只有HDMI Arc和RCA。",
                "expected": {"接口与扩展": ["接口少"]},
            },
            {
                "text": "这是一台很棒的小型投影仪，非常适合露营、户外、夏夜使用。",
                "expected": {"移动/户外": ["露营", "户外"]},
            },
            {
                "text": "太喜欢了！Roku平台太棒了，内置Roku很方便。",
                "expected": {"系统与生态": ["资源丰富"]},
            },
            {
                "text": "我把它装在天花板上，对准100英寸幕布，卧室里很合适。",
                "expected": {"卧室投屏": ["打到天花板", "卧室"]},
            },
            {
                "text": "最好的生日礼物，送人非常合适。",
                "expected": {"送礼用途": ["礼物", "送礼"]},
            },
            {
                "text": "连接Switch玩游戏延迟低，HDMI 2.1接主机很方便。",
                "expected": {"游戏娱乐": ["主机游戏"]},
            },
            {
                "text": "看球和体育直播很流畅，周末看比赛体验不错。",
                "expected": {"体育赛事": ["看球", "体育"]},
            },
        ]

        for case in cases:
            with self.subTest(text=case["text"][:30]):
                self.assert_expected_hits(case["text"], case["expected"])

        # 额外校验：这些高价值场景语句必须至少在关键列有命中，防止回归到全空。
        self.assert_non_empty_hits("最好的生日礼物，送人非常合适。", ["送礼用途"])


if __name__ == "__main__":
    unittest.main()

