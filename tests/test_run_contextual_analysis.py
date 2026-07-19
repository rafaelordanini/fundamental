import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

import run_contextual_analysis as runner  # noqa: E402


class FakeResponse:
    def __init__(self, content, *, finish_reason="stop", status_code=200):
        self.status_code = status_code
        self._content = content
        self.text = content if status_code >= 400 else ""

    def json(self):
        if self.status_code >= 400:
            return {"error": {"message": self._content}}
        return {
            "choices": [
                {
                    "finish_reason": self._finish_reason,
                    "message": {"content": self._content},
                }
            ]
        }

    @property
    def _finish_reason(self):
        return getattr(self, "finish_reason", "stop")

    @_finish_reason.setter
    def _finish_reason(self, value):
        self.finish_reason = value


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    def post(self, _url, *, headers, json, timeout):
        self.payloads.append(json)
        response = self.responses.pop(0)
        # Compatibilidade com a construção simples de FakeResponse.
        if not hasattr(response, "finish_reason"):
            response.finish_reason = "stop"
        return response


class ContextualAnalysisRunnerTests(unittest.TestCase):
    def test_extract_json_accepts_markdown_fence(self):
        result = runner.extract_json('```json\n{"ok": true}\n```')
        self.assertEqual(result, {"ok": True})

    def test_retries_compact_after_truncated_json(self):
        truncated = FakeResponse('{"titulo":"Análise incompleta')
        valid = FakeResponse(json.dumps({"titulo": "Análise completa"}))
        session = FakeSession([truncated, valid])

        result = runner.request_deepseek_resilient(
            {"evidencias": {}},
            None,
            api_key="test",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            thinking="enabled",
            session=session,
        )

        self.assertEqual(result["titulo"], "Análise completa")
        self.assertEqual(len(session.payloads), 2)
        self.assertEqual(session.payloads[0]["thinking"]["type"], "enabled")
        self.assertEqual(session.payloads[1]["thinking"]["type"], "disabled")
        self.assertGreater(session.payloads[1]["max_tokens"], session.payloads[0]["max_tokens"])

    def test_finish_reason_length_forces_compact_retry(self):
        first = FakeResponse('{"titulo":"completo"}')
        first.finish_reason = "length"
        second = FakeResponse('{"titulo":"compacto"}')
        session = FakeSession([first, second])

        result = runner.request_deepseek_resilient(
            {"evidencias": {}},
            None,
            api_key="test",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            thinking="enabled",
            session=session,
        )

        self.assertEqual(result["titulo"], "compacto")
        self.assertEqual(len(session.payloads), 2)

    def test_http_error_includes_api_body(self):
        session = FakeSession([
            FakeResponse("campo inválido", status_code=400),
            FakeResponse("campo inválido", status_code=400),
            FakeResponse("campo inválido", status_code=400),
            FakeResponse("campo inválido", status_code=400),
        ])
        with self.assertRaisesRegex(RuntimeError, "campo inválido"):
            runner.request_deepseek_resilient(
                {"evidencias": {}},
                None,
                api_key="test",
                model="deepseek-v4-pro",
                base_url="https://api.deepseek.com",
                thinking="enabled",
                session=session,
            )


if __name__ == "__main__":
    unittest.main()
