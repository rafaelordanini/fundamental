const assert = require("assert");
const {
  computeQuality,
  computeValuation,
  computeDCF,
  getDcfDefaults,
} = require("../score.js");

const base = {
  papel: "TEST3",
  segmento: "NM",
  setor: "Consumo não Cíclico",
  atividade: "Alimentos e Bebidas",
  cotacao: 10,
  pl: 5,
  pvp: 1,
  div_yield: 0.08,
  roe: 0.20,
  roic: 0.15,
  mrg_liq: 0.16,
  liq_corr: 1.8,
  div_liq_pat: 0.3,
  cresc_rec_5a: 0.12,
  ev_ebitda: 5,
};

const withoutHistory = computeValuation(base);
assert.strictEqual(withoutHistory.recomendacao, "Neutro");
assert.strictEqual(withoutHistory.historicoPronto, false);

const withHistory = computeValuation({
  ...base,
  history: {
    summary: {
      history_score: 90,
      quarters_count: 20,
      breakdown: [{ label: "Consistência", pts: 2, value: "95%" }],
      vetos: [],
    },
  },
});
assert.strictEqual(withHistory.recomendacao, "Compra");
assert.strictEqual(withHistory.historicoPronto, true);
assert.ok(withHistory.qualidade >= 80);

const lossHistory = computeValuation({
  ...base,
  history: {
    summary: {
      history_score: 70,
      quarters_count: 20,
      breakdown: [],
      vetos: ["Prejuízo recorrente"],
    },
  },
});
assert.strictEqual(lossHistory.recomendacao, "Neutro");
assert.ok(lossHistory.vetos.includes("Prejuízo recorrente"));

const blended = computeQuality({
  ...base,
  history: { summary: { history_score: 0, quarters_count: 20, breakdown: [], vetos: [] } },
});
assert.ok(blended.score < blended.currentScore);

const dcfRow = {
  ...base,
  history: {
    summary: {
      history_score: 80,
      quarters_count: 20,
      breakdown: [],
      vetos: [],
      revenue_cagr: 0.08,
      normalized_free_cash_flow_million: 100,
      free_cash_flow_years_count: 5,
      positive_free_cash_flow_years_ratio: 0.8,
      latest_equity_million: 500,
      ttm_net_income_million: 50,
      free_cash_flow_method: "Caixa operacional + caixa de investimentos",
    },
  },
};

const defaults = getDcfDefaults(dcfRow);
assert.strictEqual(defaults.growthRate, 0.08);
assert.strictEqual(defaults.discountRate, 0.12);

const baseDcf = computeDCF(dcfRow);
assert.strictEqual(baseDcf.available, true);
assert.ok(baseDcf.fairPrice > 0);
assert.ok(baseDcf.sharesMillion > 0);
assert.strictEqual(baseDcf.projection.length, 5);
assert.strictEqual(baseDcf.confidence, "Alta");

const higherDiscountDcf = computeDCF(dcfRow, {
  ...defaults,
  discountRate: 0.16,
});
assert.ok(higherDiscountDcf.fairPrice < baseDcf.fairPrice);

const invalidDcf = computeDCF(dcfRow, {
  ...defaults,
  discountRate: 0.03,
  terminalGrowthRate: 0.04,
});
assert.strictEqual(invalidDcf.available, false);
assert.ok(invalidDcf.reason.includes("superior"));

const bankDcf = computeDCF({ ...dcfRow, atividade: "Bancos" });
assert.strictEqual(bankDcf.available, false);
assert.ok(bankDcf.reason.includes("bancos"));

console.log("score.js: OK");
