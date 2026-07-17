import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRAPER = Path(__file__).resolve().parents[1] / "scraper"
sys.path.insert(0, str(SCRAPER))

import run_cvm_history  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class B3LookupTests(unittest.TestCase):
    def test_extract_results_accepts_nested_data(self):
        payload = {"data": {"content": [{"issuingCompany": "ABEV"}]}}
        self.assertEqual(
            run_cvm_history._extract_results(payload),
            [{"issuingCompany": "ABEV"}],
        )

    def test_payloads_use_small_page_and_company_prefix(self):
        payloads = list(run_cvm_history._payloads("ABEV"))
        self.assertEqual(len(payloads), 2)
        self.assertTrue(all(isinstance(item, str) and item for item in payloads))

    def test_individual_lookup_returns_exact_issuer(self):
        response = FakeResponse({
            "results": [{
                "issuingCompany": "ABEV",
                "codeCVM": "23264",
                "companyName": "AMBEV S.A.",
                "cnpj": "07526557000100",
            }]
        })
        with patch.object(run_cvm_history.cvm_history, "load_tickers", return_value=["ABEV3"]), patch.object(
            run_cvm_history.cvm_history,
            "request_with_retry",
            return_value=response,
        ):
            companies = run_cvm_history.fetch_b3_companies_by_ticker(object())

        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["issuingCompany"], "ABEV")
        self.assertEqual(companies[0]["codeCVM"], "23264")


if __name__ == "__main__":
    unittest.main()
