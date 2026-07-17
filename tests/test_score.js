const assert = require("assert");
const { computeQuality, computeValuation } = require("../score.js");

const base = {
  papel: "TEST3",
  segmento: "NM",
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
console.log("score.js: OK");
