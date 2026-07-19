import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

import run_news_context  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class RunNewsContextTests(unittest.TestCase):
    def test_parse_json_content_accepts_markdown_fence(self):
        value = run_news_context.parse_json_content('```json\n{"relevante": true}\n```')
        self.assertTrue(value["relevante"])

    def test_reader_retries_without_thinking_after_http_400(self):
        valid = {
            "relevante": True,
            "resumo": "Evento relevante.",
            "evento": "resultado",
            "impacto": "positivo",
            "horizonte": "curto",
            "intensidade": "media",
            "drivers": ["receita"],
            "riscos": [],
            "metricas_afetadas": ["receita"],
            "incerteza": "media",
        }
        session = Mock()
        session.post.side_effect = [
            FakeResponse(400, text='{"error":{"message":"invalid request body"}}'),
            FakeResponse(200, payload={"choices": [{"message": {"content": json.dumps(valid)}}]}),
        ]

        result = run_news_context.resilient_read_with_flash(
            session,
            {"title": "Teste", "description": "", "published": "2026-07-19", "body": "Texto"},
            "TEST3",
            "Empresa Teste",
            "secret",
            "deepseek-v4-flash",
            "https://api.deepseek.com",
        )

        self.assertTrue(result["relevante"])
        self.assertEqual(session.post.call_count, 2)
        first_payload = session.post.call_args_list[0].kwargs["json"]
        second_payload = session.post.call_args_list[1].kwargs["json"]
        self.assertIn("thinking", first_payload)
        self.assertNotIn("thinking", second_payload)

    def test_filtered_loader_limits_latest_rows(self):
        original = run_news_context._ORIGINAL_LOAD_JSON
        try:
            run_news_context._ORIGINAL_LOAD_JSON = lambda path, default: {
                "rows": [{"papel": "AZZA3"}, {"papel": "PETR4"}]
            }
            loader = run_news_context.filtered_loader({"AZZA3"})
            result = loader(run_news_context.base.LATEST_PATH, {})
            self.assertEqual(result["rows"], [{"papel": "AZZA3"}])
        finally:
            run_news_context._ORIGINAL_LOAD_JSON = original


if __name__ == "__main__":
    unittest.main()
