# 「为什么是这个词」这一节:全部从结构化字段派生,措辞随数据变化,不是模板填空。
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import narrative as N


BASE = {
    "primary_keyword": "wire size",
    "cluster": {"total_volume": 310300, "keywords": [
        {"term": "wire size chart", "volume": 8100, "kd": 31},
        {"term": "what size wire for 50 amp", "volume": 2900, "kd": 14},
        {"term": "what size wire for 200 amp service", "volume": 1900, "kd": 15},
        {"term": "wire size", "volume": 1300, "kd": 29}]},
    "proxy": {"kd": 29},
    "form": "tool",
    "revenue": {"downside": 117.29, "base": 234.59, "upside": 351.88,
                "threshold": 200, "volume_needed_for_threshold": 264550,
                "assumptions_version": "2026-09-09.2",
                "inputs": {"form": "tool", "cluster_volume": 310300, "niche": "home",
                           "aio_present": True, "strong_complete_count": 1}},
    "seed": {"type": "forum", "value": "https://www.google.com/search?q=site:reddit.com/r/electricians"},
}
SERP = [
    {"pos": 1, "domain": "paigeconnected.com", "dr": 28, "type": "tool", "completes_task": True},
    {"pos": 2, "domain": "facebook.com", "dr": None, "type": "video", "completes_task": False},
    {"pos": 3, "domain": "chiefdelphi.com", "dr": None, "type": "forum", "completes_task": False},
    {"pos": 5, "domain": "omnicalculator.com", "dr": 84, "type": "tool", "completes_task": True},
    {"pos": 6, "domain": "cerrowire.com", "dr": 39, "type": "official", "completes_task": True},
]


def obs(**over):
    o = {"ai_overview": {"present": True, "completes_task": False,
                         "excerpt": "给了 14G/15A 一类标准电路速查,但自己索要设备、安培与距离才肯给确切值"},
         "serp_top10": SERP, "trends_12m": "未取得数值证据", "query_url": "https://g/?q=x"}
    o.update(over)
    return o


class NarrativeTest(unittest.TestCase):
    def test_has_four_questions_and_verdict(self):
        text = N.build(BASE, obs())
        for h in ("### 有人在搜吗", "### Google 会不会自己答完", "### 打得过吗", "### 能赚多少", "### 最大的风险"):
            self.assertIn(h, text)
        # 结论句必须出现主词与门槛比较
        self.assertIn("wire size", text)
        self.assertIn("$235", text)
        self.assertIn("$200", text)

    def test_volume_sentence_uses_longtail(self):
        text = N.build(BASE, obs())
        self.assertIn("310,300", text)
        self.assertIn("what size wire for 50 amp", text)   # 最大的长尾问法要被点名
        self.assertIn("1,300", text)                        # 主词本身的量

    def test_aio_absent_wording(self):
        text = N.build(BASE, obs(ai_overview={"present": False}))
        self.assertIn("没有出现 AI 摘要", text)
        self.assertNotIn("只答了一半", text)

    def test_aio_incomplete_does_not_dump_raw_excerpt(self):
        """叙述节只讲判断,不把执行者写的观察原文(常是中英夹杂的长句)倒进来。"""
        text = N.build(BASE, obs())
        self.assertIn("只答了一半", text)
        self.assertNotIn("自己索要设备、安培与距离", text)   # 原文不进叙述
        self.assertIn("第 5 节", text)                        # 指向原文所在

    def test_lowkd_count_matches_listed_numbers(self):
        """说了几个就得列几个,不能说 5 个只列 4 个。"""
        text = N.build(BASE, obs())
        import re as _re
        m = _re.search(r"其中 (\d+) 个问法的关键词难度只有 ([\d、]+)", text)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), len(m.group(2).split("、")))

    def test_beatability_names_the_small_site_on_top(self):
        """最有说服力的一句:排第 1 的是个低权重小站。"""
        text = N.build(BASE, obs())
        self.assertIn("paigeconnected.com", text)
        self.assertIn("28", text)
        self.assertIn("omnicalculator.com", text)
        self.assertIn("84", text)

    def test_beatability_when_no_strong_rival(self):
        serp = [dict(r, dr=20) for r in SERP]
        text = N.build(BASE, obs(serp_top10=serp))
        self.assertIn("没有一个", text)

    def test_revenue_sentence_explains_haircuts(self):
        text = N.build(BASE, obs())
        self.assertIn("6 折", text)   # AIO 折减
        self.assertIn("7 折", text)   # 强占位折减
        self.assertIn("$117", text)
        self.assertIn("$352", text)

    def test_no_haircut_wording_when_clean(self):
        rec = dict(BASE, revenue=dict(BASE["revenue"],
                   inputs=dict(BASE["revenue"]["inputs"], aio_present=False, strong_complete_count=0)))
        text = N.build(rec, obs(ai_overview={"present": False},
                                serp_top10=[dict(r, dr=20) for r in SERP]))
        self.assertIn("没有打任何折", text)

    def test_risk_section_lists_real_gaps(self):
        text = N.build(BASE, obs())
        self.assertIn("季节性", text)          # trends 未取得数值
        self.assertIn("AI 摘要", text)          # AIO 在场是风险
        self.assertIn("cluster_expansion", text)  # play 也要说人话

    def test_margin_sentence(self):
        """余量:实测簇量比到门槛所需高多少。"""
        text = N.build(BASE, obs())
        self.assertIn("17%", text)   # 310300/264550-1 = 17.3%


if __name__ == "__main__":
    unittest.main()
