import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

import run_analysis_pipeline as pipeline  # noqa: E402


FACTS_GRAHAM = {
    "valuation": {"reference_model": "Graham"},
    "evidencias": {
        "roe": {"valor": 0.2},
        "fair_price_reference": {"valor": 15},
        "safety_margin": {"valor": 0.5},
    },
}


def valid_analysis():
    return {
        "titulo": "Empresa rentável com valuation atrativo",
        "resumo": "Os indicadores quantitativos mostram rentabilidade e desconto.",
        "tese": "A leitura depende da manutenção da rentabilidade e da confirmação dos dados.",
        "pontos_fortes": [
            {"texto": "O ROE está em nível elevado.", "evidencias": ["roe"]}
        ],
        "pontos_atencao": [
            {
                "texto": "O preço justo é apenas uma referência quantitativa.",
                "evidencias": ["fair_price_reference"],
            }
        ],
        "valuation": {
            "texto": "A referência de Graham está acima da cotação.",
            "evidencias": ["graham", "safety_margin"],
        },
        "monitorar": ["Evolução do ROE"],
        "mudancas_desde_anterior": {
            "texto": "Esta é a primeira análise disponível.",
            "evidencias": [],
        },
        "confianca": "media",
        "limitacoes": ["Análise baseada apenas nos fatos estruturados."],
    }


class PipelineIntegrityTests(unittest.TestCase):
    def test_analysis_file_is_valid_json(self):
        data = json.loads((ROOT / "data" / "analysis.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data.get("companies"), dict)
        self.assertEqual(data.get("total"), len(data["companies"]))
        self.assertIsInstance(data.get("erros"), list)

    def test_empty_cache_uses_safe_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text("", encoding="utf-8")
            result = pipeline.load_json_hardened(path, {"companies": {}})
            self.assertEqual(result, {"companies": {}})

    def test_malformed_required_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                pipeline.load_json_hardened(path)

    def test_first_analysis_allows_empty_change_evidence(self):
        result = pipeline.validate_analysis_hardened(valid_analysis(), FACTS_GRAHAM)
        self.assertEqual(result["mudancas_desde_anterior"]["evidencias"], [])

    def test_material_change_without_evidence_is_rejected(self):
        analysis = valid_analysis()
        analysis["mudancas_desde_anterior"] = {
            "texto": "A dívida aumentou desde a análise anterior.",
            "evidencias": [],
        }
        with self.assertRaisesRegex(ValueError, "não contém chave válida"):
            pipeline.validate_analysis_hardened(analysis, FACTS_GRAHAM)

    def test_graham_alias_is_rejected_when_reference_is_bazin(self):
        analysis = valid_analysis()
        facts = {
            **FACTS_GRAHAM,
            "valuation": {"reference_model": "Bazin"},
        }
        with self.assertRaisesRegex(ValueError, "valuation.evidencias"):
            pipeline.validate_analysis_hardened(analysis, facts)

    def test_bazin_alias_is_accepted_only_for_bazin(self):
        analysis = valid_analysis()
        analysis["valuation"]["texto"] = "A referência de Bazin está acima da cotação."
        analysis["valuation"]["evidencias"] = ["bazin", "safety_margin"]
        facts = {
            **FACTS_GRAHAM,
            "valuation": {"reference_model": "Bazin"},
        }
        result = pipeline.validate_analysis_hardened(analysis, facts)
        self.assertEqual(
            result["valuation"]["evidencias"],
            ["fair_price_reference", "safety_margin"],
        )

    def test_atomic_write_produces_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            pipeline.write_json_atomic(path, {"companies": {}, "total": 0})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"companies": {}, "total": 0},
            )
            self.assertEqual(list(path.parent.glob(".analysis.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
