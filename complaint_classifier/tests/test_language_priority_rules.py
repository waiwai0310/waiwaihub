"""
语言优先级规则专项回归：
1) 否定 + 转折优先
2) 句子切分
3) 程度词加权
4) 类比词加权
5) 对比结构（比XX好 / 不如XX）

运行：
  python -m unittest tests.test_language_priority_rules -v
"""

import json
import os
import unittest

from classifier import ClassifyEngine, KeywordTrie


class TestLanguagePriorityRules(unittest.TestCase):
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

    def test_negation_priority(self):
        r = self.engine.classify("画面不清晰。")
        self.assertEqual(r.get("清晰度/分辨率", ""), "模糊")

    def test_turning_priority(self):
        r = self.engine.classify("清晰但是有点模糊。")
        self.assertEqual(r.get("清晰度/分辨率", ""), "模糊")

    def test_sentence_split(self):
        r = self.engine.classify("第一句说清晰。第二句说风扇噪音很大！")
        self.assertEqual(r.get("清晰度/分辨率", ""), "清晰")
        self.assertIn(r.get("噪音", ""), {"噪音大", "风扇声吵", "很吵", "声音很吵"})

    def test_degree_word_weight(self):
        r = self.engine.classify("风扇声非常大。")
        self.assertIn(r.get("噪音", ""), {"噪音大", "风扇声吵", "很吵", "声音很吵"})

    def test_analogy_word_weight(self):
        r = self.engine.classify("风扇声音像吹风机。")
        self.assertIn(r.get("噪音", ""), {"像吹风机", "噪音大", "风扇声吵"})

    def test_comparison_positive(self):
        r = self.engine.classify("这台比上一台更清晰。")
        self.assertIn(r.get("清晰度/分辨率", ""), {"清晰", "很清楚", "文字清晰"})

    def test_comparison_negative(self):
        r = self.engine.classify("这台不如上一台清晰。")
        self.assertIn(r.get("清晰度/分辨率", ""), {"模糊", "不清楚"})

    def test_suffix_negation_priority(self):
        r = self.engine.classify("色彩准确度不好，画面也有点发灰。")
        self.assertIn(r.get("色彩", ""), {"色彩差", "偏色"})

    def test_claim_mismatch_priority(self):
        r = self.engine.classify("宣传4K/8K，但实际只有1080p。")
        self.assertEqual(r.get("清晰度/分辨率", ""), "分辨率不符")

    def test_price_concession_weak_positive(self):
        r = self.engine.classify("画面不是最好，但以这个价位来说还可以。")
        self.assertIn(r.get("性价比", ""), {"值", "性价比高"})

    def test_resolution_and_delay_mixed_negative(self):
        text = "8K支持不完全正确，4K在PC上能用但鼠标明显有延迟。"
        r = self.engine.classify(text)
        self.assertEqual(r.get("清晰度/分辨率", ""), "分辨率不符")
        self.assertIn(r.get("投屏体验", ""), {"延迟高", "投屏失败", ""})

    def test_compatibility_ps3_hdmi_no_signal(self):
        r = self.engine.classify("PS3无法使用，HDMI无信号。")
        self.assertEqual(r.get("接口与扩展", ""), "不兼容")

    def test_bluetooth_audio_video_delay(self):
        r = self.engine.classify("连接蓝牙扬声器会延迟视频播放。")
        self.assertIn(r.get("投屏体验", ""), {"音画不同步", "延迟高"})

    def test_brightness_positive_with_lights_on(self):
        r = self.engine.classify("即使开灯也能看清。")
        self.assertEqual(r.get("亮度", ""), "亮度满意")

    def test_after_sale_resolved_then_positive(self):
        r = self.engine.classify("收到故障机，替换后现在非常满意。")
        self.assertEqual(r.get("售后体验", ""), "售后好")

    def test_after_sale_no_response_negative(self):
        r = self.engine.classify("客服不回复，支持很差。")
        self.assertEqual(r.get("售后体验", ""), "售后差")

    def test_kw_trie_drops_strictly_inner_shorter_match(self):
        """短词作为长词子串命中时只保留长词区间（引擎层统一去重）。"""
        t = KeywordTrie({"懂参数": "发烧友", "不懂参数": "小白"})
        items = t.collect_match_items("完全不懂参数看着晕")
        kws = {x[2] for x in items}
        self.assertIn("不懂参数", kws)
        self.assertNotIn("懂参数", kws)
        vals = t.collect_all_matches("完全不懂参数看着晕")
        self.assertIn("小白", vals)
        self.assertNotIn("发烧友", vals)

        items2 = t.collect_match_items("我懂参数也看色域")
        self.assertTrue(any(x[2] == "懂参数" for x in items2))

    def test_technical_level_nested_不懂小白(self):
        r = self.engine.classify("完全不懂参数看着晕")
        self.assertEqual(r.get("技术水平", ""), "小白")

    def test_technical_level_懂参数发烧友(self):
        r = self.engine.classify("我懂参数也看色域")
        self.assertEqual(r.get("技术水平", ""), "发烧友")


if __name__ == "__main__":
    unittest.main()

