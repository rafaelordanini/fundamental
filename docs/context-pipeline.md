# Pipeline de análise contextual

1. O snapshot do Fundamentus e o histórico da CVM alimentam os indicadores determinísticos.
2. `sector_context.py` calcula percentis e posições relativas entre pares.
3. `news_context.py` consulta páginas públicas por ticker, identifica notícias específicas e usa `deepseek-v4-flash` para extrair eventos, impacto, horizonte e incerteza.
4. `contextual_analysis.py` entrega fundamentos, comparação setorial e notícias estruturadas ao `deepseek-v4-pro`.
5. A análise final continua sujeita ao validador de evidências e não altera score, valuation ou sinal.

O hash da análise inclui os contextos. Assim, uma mudança material no setor ou uma notícia nova pode atualizar o texto, enquanto dados inalterados reutilizam o relatório anterior.
