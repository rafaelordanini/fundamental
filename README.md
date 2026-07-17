# Monitor IBOV — Valuation, Qualidade & Histórico

Screening quantitativo das ações do IBOV com valuation por Graham/Bazin,
fluxo de caixa descontado, indicadores atuais do Fundamentus, classificação
setorial e até 20 trimestres de demonstrações consolidadas da CVM.

## Como funciona

- **Diariamente:** `scraper/fundamentus_snapshot.py` atualiza cotação, múltiplos,
  indicadores correntes, setor e atividade em `data/latest.json`.
- **Semanalmente:** `scraper/run_cvm_history.py` cruza os tickers com o cadastro da
  B3, baixa ITR/DFP de até dez anos-calendário, transforma valores acumulados em
  trimestres isolados e grava `data/history.json`.
- **Fluxo de caixa:** `scraper/cvm_cashflow.py` acrescenta as demonstrações DFC-MI
  e DFC-MD, corrige a escala numérica dos CSVs da CVM e calcula uma aproximação
  conservadora do fluxo de caixa livre.
- **No navegador:** `score.js` calcula qualidade, ranking, sinais e o modelo FCD.

## Filtros e ranking

A tabela pode ser filtrada por:

- setor econômico amplo;
- atividade específica;
- Novo Mercado;
- disponibilidade mínima de histórico;
- ticker, empresa, setor ou atividade pela busca textual.

Ao escolher setor ou atividade, a ordenação volta automaticamente para o score
combinado de qualidade e preço. A posição e o troféu são recalculados dentro do
recorte selecionado. Os desempates consideram qualidade consolidada, margem de
segurança e ticker.

A classificação setorial fica em `scraper/classificacao_setorial.csv`. Ela segue
a estrutura de setores da B3 e deve ser conferida quando a carteira do IBOV ou a
classificação oficial forem revisadas.

## Valuation

### Graham e Bazin

O ranking principal continua utilizando Graham quando P/L e P/VP são positivos,
com Bazin como alternativa para empresas pagadoras de dividendos. Essa referência
é usada para a margem de segurança e para o sinal geral.

### Fluxo de Caixa Descontado

A página individual possui uma aba **Fluxo de Caixa Descontado** com:

- cenário conservador, base e otimista;
- crescimento anual editável;
- taxa de desconto editável;
- crescimento na perpetuidade editável;
- período explícito entre 3 e 10 anos;
- projeção anual dos fluxos;
- valor presente do período explícito e da perpetuidade;
- margem sobre a cotação;
- tabela de sensibilidade.

O fluxo de caixa livre usado é uma aproximação:

```text
FCL aproximado = caixa líquido das atividades operacionais (6.01)
               + caixa líquido das atividades de investimento (6.02)
```

Como a conta 6.02 inclui aquisições, aplicações, alienações e outros movimentos
de investimento, o valor é tratado como uma aproximação conservadora. A base da
projeção é a mediana dos últimos três anos completos disponíveis, com fallback
para os últimos doze meses.

A quantidade de ações é estimada prioritariamente por patrimônio líquido e VPA,
com alternativa por lucro TTM e LPA. Bancos, seguradoras e holdings financeiras
não recebem esse FCD, pois seus fluxos operacionais e de financiamento exigem
modelos próprios, como desconto de dividendos ou excesso de capital.

O FCD é exibido como ferramenta exploratória e **não altera o ranking principal**
nesta versão. Isso impede que premissas subjetivas de crescimento e desconto
mudem silenciosamente o sinal de compra ou venda.

## Setup

1. Em **Settings → Actions → General → Workflow permissions**, habilite
   **Read and write permissions**.
2. Rode manualmente **Snapshot diário Fundamentus** para atualizar
   `data/latest.json`.
3. Rode manualmente **Histórico semanal CVM** para gerar o histórico e os fluxos
   de caixa. A primeira execução baixa aproximadamente dez anos-calendário de
   arquivos ITR/DFP e pode levar vários minutos.
4. Na Vercel, use Framework Preset **Other**, sem build command, com output na raiz.

## Metodologia do score

### Qualidade consolidada

- **65% indicadores atuais:** ROE, ROIC, margem líquida, liquidez corrente,
  dívida líquida/PL, crescimento de receita, EV/EBITDA e governança.
- **35% histórico CVM:** cobertura, lucros recorrentes, crescimento da receita,
  estabilidade da margem, ROE TTM, dívida e frequência de FCL anual positivo.
- Bancos e seguradoras não recebem critérios de dívida ou FCL que não sejam
  diretamente comparáveis a empresas não financeiras.

### Sinais

- **Compra:** margem de segurança ≥ 25%, qualidade consolidada ≥ 60, pelo menos
  8 trimestres de histórico e nenhum veto.
- **Venda:** margem de segurança ≤ −16,7%.
- **Neutro:** demais casos.

### Vetos históricos

- patrimônio líquido negativo;
- prejuízo em mais da metade dos trimestres, desde que existam ao menos oito.

O histórico não substitui análise contábil. Reapresentações, mudanças de estrutura
societária, fusões e alterações de ticker exigem revisão humana. Aliases podem ser
registrados em `scraper/cvm_overrides.csv`.

## Dados e atualização

- Fundamentus: dias úteis, via GitHub Actions.
- CVM: ITR e DFP consolidados, incluindo DFC-MI e DFC-MD, atualizados semanalmente.
- B3: cadastro de companhias e estrutura de classificação setorial.

As coletas abortam quando a cobertura cai abaixo dos limites mínimos, evitando
que arquivos parciais substituam snapshots válidos.

## Testes

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
node tests/test_score.js
```

## Aviso legal

Projeto educacional. Nada aqui constitui recomendação de investimento.
