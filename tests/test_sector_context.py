import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

from sector_context import build_context, percentile  # noqa: E402


class SectorContextTests(unittest.TestCase):
    def test_percentile_respects_direction(self):
        values = [1, 2, 3, 4]
        self.assertGreater(percentile(values, 4, "higher"), percentile(values, 1, "higher"))
        self.assertGreater(percentile(values, 1, "lower"), percentile(values, 4, "lower"))

    def test_activity_group_and_ranking(self):
        latest = {
            "data_coleta": "2026-07-17",
            "rows": [
                {"papel": "AAA3", "setor": "Industrial", "atividade": "Máquinas", "roe": 0.20, "roic": 0.18, "pl": 8, "pvp": 1.2, "ev_ebitda": 5, "div_yield": 0.05},
                {"papel": "BBB3", "setor": "Industrial", "atividade": "Máquinas", "roe": 0.12, "roic": 0.10, "pl": 12, "pvp": 1.8, "ev_ebitda": 8, "div_yield": 0.03},
                {"papel": "CCC3", "setor": "Industrial", "atividade": "Máquinas", "roe": 0.08, "roic": 0.06, "pl": 18, "pvp": 2.4, "ev_ebitda": 12, "div_yield": 0.01},
            ],
        }
        history = {"companies": {}}
        output = build_context(latest, history)
        first = output["companies"]["AAA3"]
        self.assertEqual(first["scope"], "atividade")
        self.assertEqual(first["peer_count"], 3)
        self.assertEqual(first["combined_rank"], 1)
        self.assertGreater(first["quality_percentile"], output["companies"]["CCC3"]["quality_percentile"])
        self.assertGreater(first["valuation_percentile"], output["companies"]["CCC3"]["valuation_percentile"])

    def test_fallback_to_sector_when_activity_is_small(self):
        latest = {
            "rows": [
                {"papel": "AAA3", "setor": "Financeiro", "atividade": "Banco A", "roe": 0.20},
                {"papel": "BBB3", "setor": "Financeiro", "atividade": "Banco B", "roe": 0.15},
                {"papel": "CCC3", "setor": "Financeiro", "atividade": "Seguros", "roe": 0.10},
            ]
        }
        output = build_context(latest, {"companies": {}})
        self.assertEqual(output["companies"]["AAA3"]["scope"], "setor")
        self.assertEqual(output["companies"]["AAA3"]["peer_count"], 3)


if __name__ == "__main__":
    unittest.main()
