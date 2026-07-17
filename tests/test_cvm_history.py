import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

from cvm_history import (  # noqa: E402
    cagr,
    compute_history_summary,
    map_tickers_to_cvm,
    normalize,
    standalone_quarters,
    ticker_prefix,
)


class CvmHistoryTests(unittest.TestCase):
    def test_normalize_and_ticker_prefix(self):
        self.assertEqual(normalize("ÚLTIMO"), "ultimo")
        self.assertEqual(ticker_prefix("BPAC11"), "BPAC")
        self.assertEqual(ticker_prefix("B3SA3"), "B3SA")

    def test_b3_mapping_with_override(self):
        companies = [{"issuingCompany": "PETR", "codeCVM": 9512, "cnpj": "33.000.167/0001-01", "companyName": "PETROBRAS"}]
        mapping, missing = map_tickers_to_cvm(
            ["PETR4", "OLDX3"],
            companies,
            {"OLDX3": {"code_cvm": "123", "cnpj": "1", "company_name": "Antiga"}},
        )
        self.assertEqual(mapping["PETR4"]["code_cvm"], "9512")
        self.assertEqual(mapping["OLDX3"]["code_cvm"], "123")
        self.assertEqual(missing, [])

    def test_cumulative_dre_becomes_standalone_quarters(self):
        periods = {
            date(2025, 3, 31): {"start_date": "2025-01-01", "revenue": 100, "ebit": 20, "net_income": 10, "equity": 100},
            date(2025, 6, 30): {"start_date": "2025-01-01", "revenue": 230, "ebit": 45, "net_income": 24, "equity": 110},
            date(2025, 9, 30): {"start_date": "2025-01-01", "revenue": 360, "ebit": 72, "net_income": 39, "equity": 120},
            date(2025, 12, 31): {"start_date": "2025-01-01", "revenue": 500, "ebit": 100, "net_income": 55, "equity": 130},
        }
        quarters = standalone_quarters(periods)
        self.assertEqual([q["revenue"] for q in quarters], [100, 130, 130, 140])
        self.assertEqual([q["net_income"] for q in quarters], [10, 14, 15, 16])

    def test_history_score_rewards_consistency(self):
        quarters = []
        for index in range(20):
            year = 2021 + index // 4
            month = (index % 4 + 1) * 3
            revenue = 100 + index * 4
            quarters.append({
                "date": f"{year}-{month:02d}-28",
                "revenue": revenue,
                "net_income": revenue * 0.12,
                "equity": 300 + index * 3,
                "net_debt": 100 - index,
            })
        summary = compute_history_summary("WEGE3", quarters)
        self.assertGreaterEqual(summary["history_score"], 80)
        self.assertEqual(summary["vetos"], [])
        self.assertEqual(summary["quarters_count"], 20)

    def test_recurring_losses_create_veto(self):
        quarters = []
        for index in range(8):
            quarters.append({
                "date": f"202{4 + index // 4}-{(index % 4 + 1) * 3:02d}-28",
                "revenue": 100,
                "net_income": -5 if index < 5 else 5,
                "equity": 100,
                "net_debt": 20,
            })
        summary = compute_history_summary("CVCB3", quarters)
        self.assertTrue(any("Prejuízo recorrente" in veto for veto in summary["vetos"]))

    def test_cagr(self):
        self.assertAlmostEqual(cagr(100, 121, 2), 0.1, places=6)
        self.assertIsNone(cagr(-100, 121, 2))


if __name__ == "__main__":
    unittest.main()
