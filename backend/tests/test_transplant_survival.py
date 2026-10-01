"""苗木移植成活率统一口径的回归测试。

覆盖：三处读口径同值、移入位置归一、数量待补录、重复登记只记一次、
成活上报回算、算法调整后历史记录自动重算（无需重做）、看板跟着明细重算。

运行：backend/.venv/bin/python -m unittest discover -s tests
"""
from __future__ import annotations

import unittest

from app.services import transplant_survival as survival
from app.services.transplant import TransplantService
from app.store import store


def reset_transplant(rows):
    table = store.rows("transplant")
    table.clear()
    table.extend(rows)
    return table


class TransplantSurvivalTests(unittest.TestCase):
    def setUp(self):
        reset_transplant([
            {"id": 1, "移植编号": "T-1", "移植树种": "香樟", "移植数量": 100,
             "移入位置": "中心绿地A区", "status": "已成活", "成活数量": 90},
            {"id": 2, "移植编号": "T-2", "移植树种": "桂花", "移植数量": 60,
             "移入位置": " 中心绿地　A区 ", "status": "已移植"},
            {"id": 3, "移植编号": "T-3", "移植树种": "银杏", "移植数量": 50,
             "移入位置": "滨河步道", "status": "已成活", "成活数量": 48},
            {"id": 4, "移植编号": "T-4", "移植树种": "樱花", "移植数量": "",
             "移入位置": "中心绿地A区", "status": "待移植"},
        ])
        self.service = TransplantService()

    def test_location_normalized_and_same_rate_everywhere(self):
        items, _ = self.service.list_entries(page=1, size=100)
        by_id = {item["移植编号"]: item for item in items}
        # 带前后空白和全角空格的位置被归一到同一个名称
        self.assertEqual(by_id["T-1"]["移入位置"], "中心绿地A区")
        self.assertEqual(by_id["T-2"]["移入位置"], "中心绿地A区")
        # 未上报的 T-2 取同位置实测 90%，与 T-1 这个数一致
        self.assertEqual(by_id["T-1"]["成活率"], "90.0%")
        self.assertEqual(by_id["T-2"]["成活率"], "90.0%")
        # 另一位置 48/50 = 96%
        self.assertEqual(by_id["T-3"]["成活率"], "96.0%")
        # 苗木基地/看板读到的分位置率值与明细同一处算法一致
        overview = self.service.survival_overview()
        loc_rates = {item["移入位置"]: item["成活率"] for item in overview["locations"]}
        self.assertEqual(loc_rates["中心绿地A区"], "90.0%")
        # 单条明细接口也是同一个数
        self.assertEqual(self.service.get_entry(2)["成活率"], "90.0%")

    def test_missing_quantity_becomes_pending(self):
        items, _ = self.service.list_entries(page=1, size=100)
        t4 = next(item for item in items if item["移植编号"] == "T-4")
        self.assertEqual(t4["移植数量"], "待补录")
        self.assertEqual(t4["成活率"], "待补录")
        # 数量待补录时不允许上报成活
        entry, message = self.service.run_action(4, "记录成活", {"成活数量": 10})
        self.assertIsNone(entry)
        self.assertIn("待补录", message)

    def test_overall_rate_uses_reported_detail(self):
        overview = self.service.survival_overview()
        # (90 + 48) / (100 + 50) = 92.0%
        self.assertEqual(overview["overallRate"], "92.0%")
        self.assertEqual(overview["pendingQuantityBatches"], 1)

    def test_duplicate_registration_kept_once(self):
        before, total_before = self.service.list_entries(page=1, size=100)
        entry, missing, duplicated = self.service.create_entry({
            "移植编号": "T-1", "移植树种": "香樟", "移植数量": 999,
            "移入位置": "别的位置",
        })
        self.assertEqual(missing, [])
        self.assertTrue(duplicated)
        self.assertEqual(entry["移植数量"], 100)
        _, total_after = self.service.list_entries(page=1, size=100)
        self.assertEqual(total_before, total_after)

    def test_report_survival_recalculates_rate(self):
        entry, message = self.service.run_action(2, "记录成活", {"成活数量": 54})
        self.assertIsNotNone(entry)
        self.assertEqual(entry["成活率"], "90.0%")  # 54/60
        self.assertEqual(entry["status"], "已成活")
        # 重复上报被拦
        again, msg = self.service.run_action(2, "记录成活", {"成活数量": 60})
        self.assertIsNone(again)
        # 看板跟着新明细重算：(90+54+48)/(100+60+50) ≈ 91.4%
        self.assertEqual(self.service.survival_overview()["overallRate"], "91.4%")

    def test_survived_cannot_exceed_quantity(self):
        entry, message = self.service.run_action(2, "记录成活", {"成活数量": 61})
        self.assertIsNone(entry)
        self.assertIn("不能超过", message)

    def test_algorithm_change_recomputes_existing_records(self):
        # 历史记录没有重做：库里只存原始成活数量，率值每次读都由共用算法现算。
        # 模拟算法调整（默认取整/封顶口径改了），只要改共用函数，所有读口径立即生效。
        row = store.find("transplant", 1)
        self.assertNotIn("缓存的成活率", row)
        # 构造存活数超过数量的数据，封顶必须在所有读口径一致生效
        row["成活数量"] = 120
        self.assertEqual(self.service.get_entry(1)["成活率"], "100.0%")

    def test_default_estimate_without_history(self):
        reset_transplant([
            {"id": 1, "移植编号": "N-1", "移植树种": "新树种", "移植数量": 10,
             "移入位置": "  ", "status": "待移植"},
        ])
        items, _ = self.service.list_entries(page=1, size=100)
        item = items[0]
        self.assertEqual(item["移入位置"], survival.UNSPECIFIED_LOCATION)
        self.assertEqual(item["成活率"], "95.0%")

    def test_dashboard_overview_shares_same_rate(self):
        payload = store.overview()
        self.assertEqual(payload["transplantSurvival"]["overallRate"], "92.0%")


if __name__ == "__main__":
    unittest.main()
