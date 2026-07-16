# Monitor IBOV — Valuation & Qualidade

Screening quantitativo das ações do IBOV com valuation (Graham/Bazin),
score de qualidade fundamentalista e ranking combinado.
Dados coletados do Fundamentus em dias úteis via GitHub Actions.

## Setup

1. Crie um repositório no GitHub e suba todos os arquivos.
2. Em **Settings → Actions → General → Workflow permissions**, marque
   **Read and write permissions** (necessário para o bot commitar o snapshot).
3. Em **Actions**, rode manualmente o workflow **Snapshot diário Fundamentus**
   (botão *Run workflow*) para gerar o primeiro `data/latest.json`.
4. Importe o repositório na Vercel: Framework Preset **Other**,
   sem build command, output directory **./** (raiz). Cada commit do bot
   redeploya o site automaticamente.

## Manutenção

- **A cada quadrimestre (jan/mai/set):** conferir `scraper/ibov.txt` contra a
  carteira teórica vigente da B3 e `scraper/segmentos.csv` contra os segmentos
  de listagem atuais.
- Se o Fundamentus mudar o layout, o scraper aborta com erro explícito em vez
  de gravar dados ruins (validação de colunas e de cobertura mínima de 80%).
- Instituições financeiras têm indicadores não aplicáveis (EV/EBITDA,
  liquidez corrente etc.) zerados no scraper — lista em `FINANCEIRAS`.

## Metodologia

- **Preço justo:** Graham (√(22,5 · LPA · VPA)) quando P/L e P/VP > 0;
  fallback Bazin (DPA / 6%) para o restante.
- **Qualidade (0–100):** ROE, ROIC, margem líquida, liquidez corrente,
  Dív/PL, crescimento 5a, EV/EBITDA e segmento de listagem, ponderados
  apenas pelos critérios aplicáveis a cada papel.
- **Vetos:** Dív/PL > 3, liq. corrente < 0,8, ROE ou margem negativos.
- **Score de ranking:** 45% margem de segurança + 45% qualidade +
  10% governança, −20 pontos se houver veto.
- **Sinais:** Compra = margem ≥ +25% E qualidade ≥ 60 E zero vetos;
  Venda = margem ≤ −16,7%; caso contrário Neutro.

## Aviso legal

Projeto educacional. Nada aqui constitui recomendação de investimento.
