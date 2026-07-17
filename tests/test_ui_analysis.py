import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AnalysisUiTests(unittest.TestCase):
    def test_index_loads_modular_scripts_in_order(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        core = html.index('src="ui-core.jsx"')
        panels = html.index('src="ui-panels.jsx"')
        context = html.index('src="ui-context.jsx"')
        app = html.index('src="app.jsx"')
        self.assertLess(core, panels)
        self.assertLess(panels, context)
        self.assertLess(context, app)

    def test_application_fetches_analysis_json(self):
        app = (ROOT / "app.jsx").read_text(encoding="utf-8")
        self.assertIn('getDataUrl("analysis.json")', app)
        self.assertIn("AnalysisBadge", app)
        self.assertIn("Análise DeepSeek V4", app)

    def test_analysis_panel_displays_evidence_and_metadata(self):
        panels = (ROOT / "ui-panels.jsx").read_text(encoding="utf-8")
        self.assertIn("EvidenceChips", panels)
        self.assertIn("entry.modelo", panels)
        self.assertIn("entry.prompt_version", panels)
        self.assertIn("mudancas_desde_anterior", panels)

    def test_context_ui_shows_sector_and_source_links(self):
        context = (ROOT / "ui-context.jsx").read_text(encoding="utf-8")
        self.assertIn("Comparação com o setor", context)
        self.assertIn("Notícias consideradas", context)
        self.assertIn('target="_blank"', context)
        self.assertIn("contexto_noticioso", context)

    def test_client_does_not_contain_api_credentials_or_endpoint_calls(self):
        for filename in ("index.html", "ui-core.jsx", "ui-panels.jsx", "ui-context.jsx", "app.jsx"):
            content = (ROOT / filename).read_text(encoding="utf-8")
            self.assertNotIn("api.deepseek.com", content, filename)
            self.assertNotIn("Authorization", content, filename)
            self.assertNotRegex(content, re.compile(r"sk-[A-Za-z0-9_-]{12,}"), filename)


if __name__ == "__main__":
    unittest.main()
