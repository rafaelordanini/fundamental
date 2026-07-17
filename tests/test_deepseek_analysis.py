import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

from deepseek_analysis import (  # noqa: E402
    PROMPT_VERSION,
    build_facts,
    facts_hash,
    generate,
    validate_analysis,
)


ROW = {
    "papel": "TEST3",
    "segmento": "NM",
    "setor": "Bens Industriais",
    "atividade": "Máquinas e Equipamentos",
    "cotacao": 10,
    "pl": 5,
    "pvp": 1,
    "div_yield": 0.08,
    "ev_ebitda": 5,
    "roe": 0.20,
    "roic": 0.15,
    "mrg_liq": 0.16,
    "liq_corr": 1.8,
    "div_liq_pat": 0.3,
    "cresc_rec_5a": 0.12,
    "data_coleta": "2026-07-17",
}

HISTORY = {
    "company_name": "EMPRESA TESTE S.A.",
    "summary": {
        "history_score": 90,
        "quarters_count": 20,
        "profitable_quarters_ratio": 0.95,
        "revenue_cagr": 0.08,
        "positive_revenue_years_ratio": 0.75,
        "margin_volatility": 0.03,
        "roe_ttm": 0.18,
        "net_debt_to_equity": 0.25,
        "net_debt_trend": -0.15,
        "positive_free_cash_flow_years_ratio": 1.0,
        "free_cash_flow_years_count": 4,
        "normalized_free_cash_flow_million": 100,
        "vetos": [],
    },
}


def valid_analysis():
    return {
        "titulo": "Negócio rentável com crescimento consistente",
        "resumo": "A empresa combina retornos elevados, crescimento e balanço controlado. O valuation de referência indica desconto, mas deve ser acompanhado com os riscos do setor.",
        "tese": "A consistência dos resultados e do caixa sustenta uma leitura favorável da qualidade do negócio, sem eliminar a necessidade de acompanhar execução e preço.",
        "pontos_fortes": [
            {"texto": "ROE e ROIC estão em faixas consideradas boas pelo projeto.", "evidencias": ["roe", "roic"]},
            {"texto": "A empresa apresentou lucro na maior parte dos trimestres.", "evidencias": ["profitable_quarters_ratio"]},
        ],
        "pontos_atencao": [
            {"texto": "O valuation depende de premissas e não deve ser lido isoladamente.", "evidencias": ["fair_price_reference", "safety_margin"]}
        ],
        "valuation": {"texto": "A referência de preço está acima da cotação atual.", "evidencias": ["cotacao", "fair_price_reference", "safety_margin"]},
        "monitorar": ["Manutenção do crescimento da receita", "Evolução do fluxo de caixa livre"],
        "mudancas_desde_anterior": {"texto": "Esta é a primeira análise disponível.", "evidencias": ["quarters_count"]},
        "confianca": "alta",
        "limitacoes": ["A análise utiliza apenas dados quantitativos do projeto."],
    }


class DeepSeekAnalysisTests(unittest.TestCase):
    def test_build_facts_contains_only_known_evidence(self):
        facts = build_facts(ROW, HISTORY)
        self.assertEqual(facts["ticker"], "TEST3")
        self.assertEqual(facts["qualidade"]["consolidada"], 96)
        self.assertEqual(facts["valuation"]["reference_model"], "Graham")
        self.assertIn("roe", facts["evidencias"])
        self.assertIn("normalized_fcf_million", facts["evidencias"])

    def test_hash_changes_with_material_fact(self):
        first = build_facts(ROW, HISTORY)
        second = build_facts({**ROW, "cotacao": 11}, HISTORY)
        self.assertNotEqual(facts_hash(first, "deepseek-v4-pro"), facts_hash(second, "deepseek-v4-pro"))
        self.assertEqual(facts_hash(first, "deepseek-v4-pro"), facts_hash(first, "deepseek-v4-pro"))

    def test_validator_rejects_unknown_evidence(self):
        facts = build_facts(ROW, HISTORY)
        analysis = valid_analysis()
        analysis["pontos_fortes"][0]["evidencias"] = ["noticia_inventada"]
        with self.assertRaises(ValueError):
            validate_analysis(analysis, facts)

    def test_validator_accepts_structured_output(self):
        facts = build_facts(ROW, HISTORY)
        result = validate_analysis(valid_analysis(), facts)
        self.assertEqual(result["confianca"], "alta")
        self.assertEqual(len(result["pontos_fortes"]), 2)

    @patch("deepseek_analysis.request_deepseek")
    def test_generate_reuses_unchanged_analysis(self, mocked_request):
        latest = {"data_coleta": "2026-07-17", "rows": [ROW]}
        history = {"data_coleta": "2026-07-17", "companies": {"TEST3": HISTORY}}
        facts = build_facts(ROW, HISTORY)
        digest = facts_hash(facts, "deepseek-v4-pro")
        previous = {
            "companies": {
                "TEST3": {
                    "facts_hash": digest,
                    "facts": facts,
                    "analysis": valid_analysis(),
                    "modelo": "deepseek-v4-pro",
                }
            }
        }
        output, errors = generate(
            latest,
            history,
            previous,
            api_key="test",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            thinking="enabled",
        )
        mocked_request.assert_not_called()
        self.assertEqual(output["total"], 1)
        self.assertEqual(output["geradas_nesta_execucao"], 0)
        self.assertEqual(errors, [])

    @patch("deepseek_analysis.request_deepseek", return_value=valid_analysis())
    def test_generate_validates_and_stores_new_analysis(self, mocked_request):
        latest = {"data_coleta": "2026-07-17", "rows": [ROW]}
        history = {"data_coleta": "2026-07-17", "companies": {"TEST3": HISTORY}}
        output, errors = generate(
            latest,
            history,
            {"companies": {}},
            api_key="test",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            thinking="enabled",
        )
        mocked_request.assert_called_once()
        self.assertEqual(output["geradas_nesta_execucao"], 1)
        self.assertEqual(output["companies"]["TEST3"]["prompt_version"], PROMPT_VERSION)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
