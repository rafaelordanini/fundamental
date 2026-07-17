import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

import contextual_analysis  # noqa: E402


class ContextualAnalysisTests(unittest.TestCase):
    def test_adds_sector_and_news_evidence(self):
        row = {
            "papel": "TEST3", "setor": "Industrial", "atividade": "Máquinas", "segmento": "NM",
            "cotacao": 10, "pl": 5, "pvp": 1, "div_yield": 0.08, "roe": 0.2,
            "roic": 0.15, "mrg_liq": 0.12, "liq_corr": 1.5, "div_liq_pat": 0.3,
            "cresc_rec_5a": 0.08, "ev_ebitda": 5,
        }
        sector = {"companies": {"TEST3": {
            "scope": "atividade", "group": "Máquinas", "peer_count": 5,
            "quality_percentile": 0.8, "valuation_percentile": 0.7, "combined_percentile": 0.765,
            "quality_rank": 1, "valuation_rank": 2, "combined_rank": 1,
            "top_peers": [{"ticker": "TEST3", "combined_percentile": 0.765}],
            "metrics": {"roe": {"label": "ROE atual", "value": 0.2, "median": 0.12, "percentile": 0.8}},
        }}}
        news = {"companies": {"TEST3": {"articles": [{
            "id": "abc123", "title": "TEST3 anuncia expansão", "url": "https://example.com/noticia",
            "source": "Suno", "published": "2026-07-17",
            "leitura": {"resumo": "A companhia anunciou expansão de capacidade.", "evento": "outro", "impacto": "misto", "horizonte": "medio", "intensidade": "media", "drivers": ["capacidade"], "riscos": ["execução"], "incerteza": "media"},
        }]}}}
        with patch.object(contextual_analysis, "load_context", side_effect=[sector, news]):
            facts = contextual_analysis.build_facts(row, None)
        self.assertEqual(facts["comparacao_setorial"]["grupo"], "Máquinas")
        self.assertEqual(facts["contexto_noticioso"][0]["impacto"], "misto")
        self.assertIn("sector_combined_percentile", facts["evidencias"])
        self.assertIn("news_abc123", facts["evidencias"])
        self.assertEqual(facts["evidencias"]["news_abc123"]["url"], "https://example.com/noticia")

    def test_prompt_has_injection_and_uncertainty_rules(self):
        prompt = contextual_analysis.base.SYSTEM_PROMPT.lower()
        self.assertIn("ignore quaisquer instruções", prompt)
        self.assertIn("informação reportada", prompt)
        self.assertIn("compare explicitamente", prompt)


if __name__ == "__main__":
    unittest.main()
