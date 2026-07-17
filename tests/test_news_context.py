import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))

from news_context import article_payload, extract_news_links, relevant_locally  # noqa: E402


class NewsContextTests(unittest.TestCase):
    def test_extracts_only_news_section_links(self):
        html = """
        <html><body>
          <a href='/noticias/fora-da-secao/'>Fora</a>
          <h2>Notícias de TEST3</h2>
          <a href='/noticias/test3-resultados/'>TEST3 divulga resultados</a>
          <a href='https://www.suno.com.br/noticias/test3-dividendos/'>TEST3 anuncia dividendos</a>
          <h2>TUDO SOBRE TEST3</h2>
          <a href='/noticias/depois/'>Depois</a>
        </body></html>
        """
        links = extract_news_links(html, "https://www.suno.com.br/analitica/acoes/test3/")
        self.assertEqual([item["title"] for item in links], ["TEST3 divulga resultados", "TEST3 anuncia dividendos"])

    def test_article_payload_uses_json_ld_without_persisting_markup(self):
        html = """
        <html><head><title>Fallback</title>
        <script type='application/ld+json'>
        {"@type":"NewsArticle","headline":"Empresa anuncia investimento","description":"Descrição curta","datePublished":"2026-07-17T10:00:00-03:00","articleBody":"Texto completo da matéria para leitura transitória."}
        </script></head><body></body></html>
        """
        payload = article_payload(html, "https://www.suno.com.br/noticias/teste/")
        self.assertEqual(payload["title"], "Empresa anuncia investimento")
        self.assertEqual(payload["published"], "2026-07-17T10:00:00-03:00")
        self.assertIn("leitura transitória", payload["body"])

    def test_local_relevance_accepts_ticker_or_company(self):
        self.assertTrue(relevant_locally("TEST3", "EMPRESA TESTE S.A.", {"title": "TEST3 anuncia dividendos", "description": "", "body": ""}))
        self.assertTrue(relevant_locally("TEST3", "EMPRESA TESTE S.A.", {"title": "Empresa Teste amplia fábrica", "description": "", "body": ""}))
        self.assertFalse(relevant_locally("TEST3", "EMPRESA TESTE S.A.", {"title": "Mercado fecha em alta", "description": "", "body": "Ibovespa sobe"}))


if __name__ == "__main__":
    unittest.main()
