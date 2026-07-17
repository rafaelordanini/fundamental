import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

from cvm_cashflow import (  # noqa: E402
    parse_cvm_number,
    standalone_quarters_with_cashflow,
    yearly_totals_with_cashflow,
)


class CvmCashFlowTests(unittest.TestCase):
    def test_parse_cvm_decimal_point(self):
        self.assertEqual(parse_cvm_number("15711141.000000"), 15711141.0)
        self.assertEqual(parse_cvm_number("15.711.141,50"), 15711141.5)
        self.assertEqual(parse_cvm_number("123,45"), 123.45)

    def test_cumulative_cash_flow_becomes_standalone(self):
        periods = {
            date(2025, 3, 31): {
                "start_date": "2025-01-01",
                "cashflow_start_date": "2025-01-01",
                "revenue": 100,
                "net_income": 10,
                "operating_cash_flow": 50,
                "investing_cash_flow": -10,
                "equity": 100,
            },
            date(2025, 6, 30): {
                "start_date": "2025-01-01",
                "cashflow_start_date": "2025-01-01",
                "revenue": 220,
                "net_income": 22,
                "operating_cash_flow": 110,
                "investing_cash_flow": -25,
                "equity": 105,
            },
            date(2025, 9, 30): {
                "start_date": "2025-01-01",
                "cashflow_start_date": "2025-01-01",
                "revenue": 350,
                "net_income": 35,
                "operating_cash_flow": 180,
                "investing_cash_flow": -40,
                "equity": 110,
            },
            date(2025, 12, 31): {
                "start_date": "2025-01-01",
                "cashflow_start_date": "2025-01-01",
                "revenue": 500,
                "net_income": 50,
                "operating_cash_flow": 260,
                "investing_cash_flow": -60,
                "equity": 115,
            },
        }
        quarters = standalone_quarters_with_cashflow(periods)
        self.assertEqual(
            [item["operating_cash_flow"] for item in quarters],
            [50, 60, 70, 80],
        )
        self.assertEqual(
            [item["investing_cash_flow"] for item in quarters],
            [-10, -15, -15, -20],
        )
        self.assertEqual(
            [item["free_cash_flow"] for item in quarters],
            [40, 45, 55, 60],
        )

        annual = yearly_totals_with_cashflow(quarters)
        self.assertEqual(annual[0]["free_cash_flow"], 200)
        self.assertEqual(annual[0]["operating_cash_flow"], 260)


if __name__ == "__main__":
    unittest.main()
