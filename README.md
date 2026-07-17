# Monitor IBOV — Valuation, Qualidade & Histórico

Screening quantitativo das ações do IBOV com valuation (Graham/Bazin),
indicadores atuais do Fundamentus e até 20 trimestres de demonstrações
consolidadas da CVM.

## Como funciona

- **Diariamente:** `scraper/fundamentus_snapshot.py` atualiza cotação, múltiplos e
  indicadores correntes em `data/latest.json`.
- **Semanalmente:** `scraper/cvm_history.py` cruza os tickers com o cadastro da B3,
  baixa ITR/DFP dos últimos seis anos, transforma valores acumulados em trimestres
  isolados e grava `data/history.json`.
- **No navegador:** `score.js` combina os dois conjuntos sem backend e calcula o
  ranking, os vetos e o sinal final.

## Setup

1. Em **Settings → Actions → General → Workflow permissions**, habilite
   **Read and write permissions**.
2. Rode manualmente **Snapshot diário Fundamentus** para atualizar
   `data/latest.json`.
3. Rode manualmente **Histórico semanal CVM** para gerar o primeiro histórico.
   A primeira execução baixa aproximadamente seis anos de arquivos ITR/DFP e pode
   levar alguns minutos.
4. Na Vercel, use Framework Preset **Other**, sem build command, com output na raiz.

## Metodologia do score

### Qualidade consolidada

- **65% indicadores atuais:** ROE, ROIC, margem líquida, liquidez corrente,
  dívida líquida/PL, crescimento de receita, EV/EBITDA e governança.
- **35% histórico CVM:** cobertura, proporção de trimestres lucrativos, CAGR da
  receita, frequência de crescimento anual, estabilidade da margem, ROE TTM e
  tendência da dívida líquida.
- Bancos e seguradoras não recebem o critério histórico de dívida, pois sua
  estrutura de balanço não é comparável à de companhias não financeiras.

### Sinais

- **Compra:** margem de segurança ≥ 25%, qualidade consolidada ≥ 60, pelo menos
  8 trimestres de histórico e nenhum veto.
- **Venda:** margem de segurança ≤ −16,7%.
- **Neutro:** demais casos.

### Vetos históricos

- patrimônio líquido negativo;
- prejuízo em mais da metade dos trimestres, desde que existam ao menos oito.

O histórico não tenta substituir análise contábil. Reapresentações, mudanças de
estrutura societária, fusões e alterações de ticker exigem revisão humana.
Aliases decorrentes de mudanças societárias podem ser registrados em
`scraper/cvm_overrides.csv`.

## Dados e atualização

- Fundamentus: dias úteis, via GitHub Actions.
- CVM: conjuntos públicos ITR e DFP consolidados, atualizados semanalmente.
- B3: cadastro de companhias usado para cruzar o prefixo do ticker com o código CVM.

A coleta aborta quando a cobertura cai abaixo dos limites mínimos, evitando que
um arquivo parcial substitua um snapshot válido.

## Testes

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
node tests/test_score.js
```

## Aviso legal

Projeto educacional. Nada aqui constitui recomendação de investimento.
