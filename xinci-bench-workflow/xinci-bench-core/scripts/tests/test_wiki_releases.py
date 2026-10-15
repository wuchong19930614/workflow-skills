import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wiki_releases as WR
import write_observation as W
from _common import BenchError

WIKITEXT = """===October–December===
{| class="wikitable sortable"
|-
! Release date
! Title
! Platform(s)
! Type(s)
! Genre(s)
|- id="October"
| October 1
| ''Augment Protocol'' (JP)
| NS
| Port
| Visual novel
|-
| rowspan="2" | October 15
| ''[[Castlevania: Belmont's Curse]]''
| WIN, NS, PS5, XBX/S
| Original
| [[Metroidvania]]
|-
| ''[[Enshrouded]]''
| WIN, PS5
| Full release
| Survival, [[Action role-playing game|Action RPG]]
|-
| October 22
| ''{{sort|Jackbox Party Pack 12|The [[Jackbox Party Pack 12]]}}''
| WIN, NS2
| Original
| Party
|-
| October 22
| ''Tiny Indie Thing''
| WIN
| Early access
| Roguelike
|-
| rowspan="2" | October 29
| ''[[Monster Hunter Outlanders]]''
| rowspan="2" | iOS, DROID
| rowspan="2" | Original
| Action RPG
|-
| ''[[Moomins#Video games|Moomin: Midsummer Madness]]''
| WIN
| Original
| Adventure
|-
| October 30
| {{sort|Cat in the Hat: Rainy Day Mayhem|''[[The Cat in the Hat]]: Rainy Day Mayhem''}}
| WIN, NS
| Original
| Party
|-
| November 20
| ''[[Wardogs]]''
| WIN
| Early access
| FPS
|-
| December
| ''Undated Game''
| WIN
| Original
| Action
|}
"""


class ParseTest(unittest.TestCase):
    def test_rows_dates_titles_and_articles(self):
        rows = {r["title"]: r for r in WR.parse_rows(WIKITEXT, 2026)}
        self.assertEqual(rows["Castlevania: Belmont's Curse"]["date"], "2026-10-15")
        self.assertEqual(rows["Enshrouded"]["date"], "2026-10-15")                 # 日期跨行(rowspan)沿用上一行
        self.assertEqual(rows["Enshrouded"]["type"], "Full release")
        self.assertEqual(rows["The Jackbox Party Pack 12"]["article"], "Jackbox Party Pack 12")   # {{sort|键|显示}}
        self.assertIsNone(rows["Tiny Indie Thing"]["article"])                    # 没有独立词条
        self.assertEqual(rows["Monster Hunter Outlanders"]["platforms"], "iOS, DROID")  # 去掉 rowspan 属性
        self.assertIsNone(rows["Moomin: Midsummer Madness"]["article"])           # 链到别的词条的小节,浏览量不代表它
        # 标题里只有一部分是链接(链到原著或系列词条),浏览量不代表这款游戏
        self.assertIsNone(rows["The Cat in the Hat: Rainy Day Mayhem"]["article"])
        self.assertEqual(rows["Augment Protocol"]["region"], "JP")
        self.assertNotIn("Undated Game", rows)                                    # 只有月份没有日的跳过

    def test_window_keeps_new_english_titles(self):
        rows = WR.parse_rows(WIKITEXT, 2026)
        got = [r["title"] for r in WR.window(rows, "2026-10-14", days=30)]
        # 只留原创与抢先体验、有独立词条、英文区能玩的,30 天以内
        self.assertEqual(got, ["Castlevania: Belmont's Curse", "The Jackbox Party Pack 12", "Monster Hunter Outlanders"])
        self.assertIn("Wardogs", [r["title"] for r in WR.window(rows, "2026-10-14", days=60)])


class RankTest(unittest.TestCase):
    def rows(self):
        return WR.window(WR.parse_rows(WIKITEXT, 2026), "2026-10-14", days=60)

    def test_rank_by_views_serially(self):
        views = {"Castlevania: Belmont's Curse": 82998, "Jackbox Party Pack 12": 900,
                 "Monster Hunter Outlanders": 6741, "Wardogs": 120000}
        pauses = []
        out = WR.rank(self.rows(), lambda art, on: views[art], on="2026-10-14", sleep=pauses.append)
        self.assertEqual([r["title"] for r in out["ranked"]],
                         ["Wardogs", "Castlevania: Belmont's Curse", "Monster Hunter Outlanders", "The Jackbox Party Pack 12"])
        self.assertEqual(out["not_fetched"], [])
        self.assertEqual(len(pauses), 3)                                          # 一条一条查,中间停顿

    def test_rate_limit_stops_and_lists_the_rest(self):
        calls = []

        def fetch(art, on):
            calls.append(art)
            if len(calls) == 2:
                raise WR.RateLimited("429")
            return 10
        out = WR.rank(self.rows(), fetch, on="2026-10-14", sleep=lambda s: None)
        self.assertEqual(len(calls), 2)                                           # 遇到 429 就停,不连续重试
        self.assertEqual(len(out["not_fetched"]), 3)
        # 没取到浏览量的候选照样留在 ranked 里(排在取到的后面),不从原料里丢掉
        self.assertEqual([r["views_30d"] for r in out["ranked"]], [10, None, None, None])
        self.assertEqual(len(WR.to_items(out["ranked"], top=20, seen_at="2026-10-14")), 4)

    def test_missing_article_does_not_stop(self):
        def fetch(art, on):
            if art == "Wardogs":
                raise WR.NotFound(art)
            return 5
        out = WR.rank(self.rows(), fetch, on="2026-10-14", sleep=lambda s: None)
        self.assertEqual(len(out["ranked"]), 4)
        self.assertIsNone(next(r for r in out["ranked"] if r["title"] == "Wardogs")["views_30d"])
        self.assertEqual(out["ranked"][-1]["title"], "Wardogs")                   # 查不到浏览量的排最后

    def test_items_are_valid_quick_signal(self):
        out = WR.rank(self.rows(), lambda art, on: 100, on="2026-10-14", sleep=lambda s: None)
        items = WR.to_items(out["ranked"], top=2, seen_at="2026-10-14")
        self.assertEqual(len(items), 2)
        it = items[0]
        self.assertEqual((it["source"], it["term"]), ("wikipedia", None))
        self.assertIn(it["stage"], WR.NEW_TYPES)
        self.assertTrue(it["url"].startswith("https://en.wikipedia.org/wiki/"))
        self.assertIn("playable_at", it)
        W.validate({"slug": None, "observed_at": "2026-10-14T08:00:00+00:00", "stage": "quick", "kind": "quick_signal",
                    "source_urls": ["https://en.wikipedia.org/wiki/List_of_video_games_released_in_2026"],
                    "semrush_calls": 0, "points": ["x"], "readings": {"items": items}})

    def test_recent_releases_included_when_asked(self):
        text = WIKITEXT.replace("|- id=\"October\"", "|-\n| September 30\n| ''[[Just Out]]''\n| WIN\n| Original\n| RPG\n"
                                "|-\n| September 29\n| ''[[Too Old]]''\n| WIN\n| Original\n| RPG\n|- id=\"October\"")
        rows = WR.parse_rows(text, 2026)
        self.assertNotIn("Just Out", [r["title"] for r in WR.window(rows, "2026-10-14", days=30)])
        got = [r["title"] for r in WR.window(rows, "2026-10-14", days=30, recent_days=14)]
        self.assertEqual(got[0], "Just Out")                                     # 已上线 14 天以内的也算(Q1 游戏窗口)
        self.assertNotIn("Too Old", got)                                          # 第 15 天的不算
        self.assertEqual(WR.sections_for("2026-10-05", 30, recent_days=14), [(2026, "July–September"), (2026, "October–December")])

    def test_footnote_templates_stripped(self):
        text = ("{| class=\"wikitable\"\n|-\n| October 18\n| ''[[Footnote Game]]''{{efn|Released as ''Foo'' in Japan {{sort|a|b}}}}\n| WIN\n"
                "| Original{{efn|Early access since [[2025]]}}\n| RPG<ref>{{cite web|url=x}}</ref>\n")
        r = WR.parse_rows(text, 2026)[0]
        self.assertEqual((r["title"], r["article"], r["type"], r["genre"]), ("Footnote Game", "Footnote Game", "Original", "RPG"))

    def test_platform_cell_shared_with_previous_row(self):
        # 上一行的平台格跨两行(rowspan),这一行少一格:类型不能被读成平台
        text = ("{| class=\"wikitable\"\n|-\n| rowspan=\"2\" | October 15\n| ''[[First Game]]''\n| rowspan=\"2\" | WIN, PS5\n"
                "| Original\n| Action\n|-\n| ''[[Second Game]]''\n| Original\n| Puzzle\n")
        rows = {r["title"]: r for r in WR.parse_rows(text, 2026)}
        self.assertEqual((rows["Second Game"]["platforms"], rows["Second Game"]["type"], rows["Second Game"]["genre"]),
                         ("WIN, PS5", "Original", "Puzzle"))

    def test_section_titles_cover_window(self):
        self.assertEqual(WR.sections_for("2026-10-14", 30), [(2026, "October–December")])
        self.assertEqual(WR.sections_for("2026-12-20", 30), [(2026, "October–December"), (2027, "January–March")])
        with self.assertRaises(BenchError):
            WR.window([], "2026-13-01")


if __name__ == "__main__":
    unittest.main()
