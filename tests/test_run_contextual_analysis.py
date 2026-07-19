import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

import run_contextual_analysis as runner  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        content,
        *,
        finish_reason="stop",
        status_code=200,
        reasoning_content=None,
        output_text=None,
    ):
        self.status_code = status_code
        self._content = content
        self.finish_reason = finish_reason
        self.reasoning_content = reasoning_content
        self.output_text = output_text
        self.text = content if status_code >= 400 else ""

    def json(self):
        if self.status_code >= 400:
            return {"error": {"message": self._content}}
        message = {"content": self._content}
        if self.reasoning_content is not None:
            message["reasoning_content"] = self.reasoning_content
        if self.output_text is not None:
            message["output_text"] = self.output_text
        return {
            "choices": [
                {
                    "finish_reason": self.finish_reason,
                    "message": message,
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "total_tokens": 300,
            },
        }


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    def post(self, _url, *, headers, json, timeout):
        self.payloads.append(json)
        return self.responses.pop(0)


class ContextualAnalysisRunnerTests(unittest.TestCase):
    def call(self, session):
        return runner.request_deepseek_resilient(
            {"evidencias": {}},
            None,
            api_key="test",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            thinking="enabled",
            session=session,
        )

    def test_extract_json_accepts_markdown_fence(self):
        result = runner.extract_json('```json\n{"ok": true}\n```')
        self.assertEqual(result, {"ok": True})

    def test_content_text_accepts_openai_content_parts(self):
        content = [
            {"type": "text", "text": '{"ok":'},
            {"type": "text", "text": "true}"},
        ]
        self.assertEqual(runner.content_text(content), '{"ok":\ntrue}')

    def test_first_analysis_change_allows_empty_evidence(self):
        result = runner.validate_claim_resilient(
            {
                "texto": "Esta é a primeira análise disponível para a companhia.",
                "evidencias": [],
            },
            "mudancas_desde_anterior",
            {"roe"},
        )
        self.assertEqual(result["evidencias"], [])

    def test_empty_evidence_remains_invalid_for_material_claim(self):
        with self.assertRaisesRegex(ValueError, "lista não vazia"):
            runner.validate_claim_resilient(
                {"texto": "O ROE está elevado.", "evidencias": []},
                "pontos_fortes[0]",
                {"roe"},
            )

    def test_empty_evidence_is_rejected_for_non_initial_change(self):
        with self.assertRaisesRegex(ValueError, "lista não vazia"):
            runner.validate_claim_resilient(
                {
                    "texto": "A dívida aumentou desde a análise anterior.",
                    "evidencias": [],
                },
                "mudancas_desde_anterior",
                {"net_debt_trend"},
            )

    def test_retries_compact_after_truncated_json(self):
        session = FakeSession([
            FakeResponse('{"titulo":"Análise incompleta'),
            FakeResponse(json.dumps({"titulo": "Análise completa"})),
        ])

        result = self.call(session)

        self.assertEqual(result["titulo"], "Análise completa")
        self.assertEqual(len(session.payloads), 2)
        self.assertEqual(session.payloads[0]["thinking"]["type"], "enabled")
        self.assertEqual(session.payloads[1]["thinking"]["type"], "disabled")
        self.assertGreater(session.payloads[1]["max_tokens"], session.payloads[0]["max_tokens"])

    def test_empty_content_moves_to_no_thinking_json(self):
        session = FakeSession([
            FakeResponse("", reasoning_content="raciocínio interno não publicável"),
            FakeResponse(json.dumps({"titulo": "Resposta sem thinking"})),
        ])

        result = self.call(session)

        self.assertEqual(result["titulo"], "Resposta sem thinking")
        self.assertEqual(len(session.payloads), 2)
        self.assertEqual(session.payloads[1]["thinking"]["type"], "disabled")

    def test_compatibility_mode_omits_optional_fields(self):
        session = FakeSession([
            FakeResponse(""),
            FakeResponse(""),
            FakeResponse(json.dumps({"titulo": "Modo compatível"})),
        ])

        result = self.call(session)

        self.assertEqual(result["titulo"], "Modo compatível")
        self.assertEqual(len(session.payloads), 3)
        self.assertNotIn("thinking", session.payloads[2])
        self.assertNotIn("response_format", session.payloads[2])

    def test_finish_reason_length_forces_compact_retry(self):
        session = FakeSession([
            FakeResponse('{"titulo":"completo"}', finish_reason="length"),
            FakeResponse('{"titulo":"compacto"}'),
        ])

        result = self.call(session)

        self.assertEqual(result["titulo"], "compacto")
        self.assertEqual(len(session.payloads), 2)

    @patch("run_contextual_analysis.time.sleep", return_value=None)
    def test_http_error_includes_api_body(self, _sleep):
        session = FakeSession([
            FakeResponse("campo inválido", status_code=400),
            FakeResponse("campo inválido", status_code=400),
            FakeResponse("campo inválido", status_code=400),
            FakeResponse("campo inválido", status_code=400),
            FakeResponse("campo inválido", status_code=400),
        ])
        with self.assertRaisesRegex(RuntimeError, "campo inválido"):
            self.call(session)


if __name__ == "__main__":
    unittest.main()
