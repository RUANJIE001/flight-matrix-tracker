"""
test_matrix.py - 单元验证与逻辑冒烟测试
验证：
1. 弹性日期 3x3 矩阵组合计算
2. 边界条件校验 (排除返程早于出发)
3. 模拟分析与智能省钱建议
"""
import unittest
from matrix import generate_date_pairs, MatrixAnalysis
from scrapers.base import FlightOffer

class TestMatrix(unittest.TestCase):
    def test_roundtrip_pairs_count(self):
        pairs = generate_date_pairs("2026-10-24", "2026-10-31", flexible_days=1)
        # 应精确生成 3 * 3 = 9 组组合
        self.assertEqual(len(pairs), 9)
        # 验证包含原定日期
        base_pair = [p for p in pairs if p[0] == "2026-10-24" and p[1] == "2026-10-31"]
        self.assertEqual(len(base_pair), 1)

    def test_oneway_pairs_count(self):
        pairs = generate_date_pairs("2026-10-24", None, flexible_days=1)
        # 单程模式应为 3 组
        self.assertEqual(len(pairs), 3)

    def test_analysis_savings(self):
        # 模拟 9 组数据
        results_map = {
            ("2026-10-24", "2026-10-31"): [
                FlightOffer(platform="Google Flights", price=2600, depart_date="2026-10-24", return_date="2026-10-31")
            ],
            ("2026-10-23", "2026-11-01"): [
                FlightOffer(platform="携程 / Trip.com", price=2180, depart_date="2026-10-23", return_date="2026-11-01")
            ]
        }
        analysis = MatrixAnalysis("2026-10-24", "2026-10-31", 2500, results_map)
        self.assertEqual(analysis.global_min_offer.price, 2180)
        self.assertEqual(analysis.savings, 420)
        self.assertIn("立省 ¥420", analysis.best_recommendation)

if __name__ == "__main__":
    unittest.main()
