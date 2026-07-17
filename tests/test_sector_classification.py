import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRAPER = ROOT / "scraper"


class SectorClassificationTests(unittest.TestCase):
    def test_all_ibov_tickers_have_sector_and_activity(self):
        tickers = {
            line.strip().upper()
            for line in (SCRAPER / "ibov.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        with (SCRAPER / "classificacao_setorial.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        by_ticker = {row["ticker"].strip().upper(): row for row in rows}
        self.assertEqual(tickers - set(by_ticker), set(), "Há tickers do IBOV sem classificação")
        self.assertEqual(set(by_ticker) - tickers, set(), "Há classificações órfãs fora da lista do IBOV")

        for ticker in sorted(tickers):
            self.assertTrue(by_ticker[ticker]["setor"].strip(), f"Setor vazio para {ticker}")
            self.assertTrue(by_ticker[ticker]["atividade"].strip(), f"Atividade vazia para {ticker}")

    def test_classification_has_useful_sector_diversity(self):
        with (SCRAPER / "classificacao_setorial.csv").open(encoding="utf-8") as handle:
            sectors = {row["setor"].strip() for row in csv.DictReader(handle)}
        self.assertGreaterEqual(len(sectors), 8)
        self.assertIn("Financeiro e Outros", sectors)
        self.assertIn("Utilidade Pública", sectors)
        self.assertIn("Materiais Básicos", sectors)


if __name__ == "__main__":
    unittest.main()
