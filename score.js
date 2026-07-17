(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.FundamentalScore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const BAZIN_YIELD_MIN = 0.06;
  const MARGEM_COMPRA = 0.25;
  const MARGEM_VENDA = -0.1667;
  const QUALIDADE_MIN = 60;
  const HISTORICO_MIN_TRIMESTRES = 8;

  const SEGMENTO_LABEL = { NM: "Novo Mercado", N2: "Nível 2", N1: "Nível 1", TRAD: "Tradicional" };
  const SEGMENTO_PTS = { NM: 2, N2: 1, N1: 0, TRAD: 0 };

  const QUALITY_CRITERIA = [
    { key: "roe", label: "ROE atual", good: v => v >= 0.15, ok: v => v >= 0.08 },
    { key: "roic", label: "ROIC atual", good: v => v >= 0.12, ok: v => v >= 0.06 },
    { key: "mrg_liq", label: "Margem líquida atual", good: v => v >= 0.15, ok: v => v >= 0.05 },
    { key: "liq_corr", label: "Liquidez corrente", good: v => v >= 1.5, ok: v => v >= 1.0 },
    { key: "div_liq_pat", label: "Dív. líquida/PL", good: v => v <= 0.5, ok: v => v <= 1.0 },
    { key: "cresc_rec_5a", label: "Crescimento atual 5a", good: v => v >= 0.10, ok: v => v >= 0.0 },
    { key: "ev_ebitda", label: "EV/EBITDA", good: v => v > 0 && v <= 6, ok: v => v > 0 && v <= 10 },
  ];

  const VETOES = [
    { key: "div_liq_pat", label: "Alavancagem excessiva (DívLíq/PL > 3)", test: v => v !== null && v !== undefined && v > 3 },
    { key: "liq_corr", label: "Liquidez corrente crítica (< 0,8)", test: v => v !== null && v !== undefined && v < 0.8 },
    { key: "roe", label: "ROE atual negativo", test: v => v !== null && v !== undefined && v < 0 },
    { key: "mrg_liq", label: "Margem líquida atual negativa", test: v => v !== null && v !== undefined && v < 0 },
  ];

  function computeCurrentQuality(row) {
    let points = 0;
    let maxPoints = 0;
    const breakdown = [];
    for (const criterion of QUALITY_CRITERIA) {
      const value = row[criterion.key];
      if (value === null || value === undefined) continue;
      maxPoints += 2;
      const pts = criterion.good(value) ? 2 : criterion.ok(value) ? 1 : 0;
      points += pts;
      breakdown.push({ label: criterion.label, pts, group: "Atual" });
    }
    if (row.segmento) {
      maxPoints += 2;
      const pts = SEGMENTO_PTS[row.segmento] ?? 0;
      points += pts;
      breakdown.push({
        label: "Governança (" + (SEGMENTO_LABEL[row.segmento] ?? row.segmento) + ")",
        pts,
        group: "Atual",
      });
    }
    return {
      score: maxPoints > 0 ? Math.round((points / maxPoints) * 100) : null,
      breakdown,
      applicable: maxPoints / 2,
    };
  }

  function computeQuality(row) {
    const current = computeCurrentQuality(row);
    const summary = row.history && row.history.summary ? row.history.summary : null;
    const historyScore = summary && Number.isFinite(summary.history_score) ? summary.history_score : null;
    const historyQuarters = summary && Number.isFinite(summary.quarters_count) ? summary.quarters_count : 0;
    const historyReady = historyScore !== null && historyQuarters >= HISTORICO_MIN_TRIMESTRES;
    let score = current.score;
    if (historyReady && current.score !== null) score = Math.round(current.score * 0.65 + historyScore * 0.35);
    else if (historyReady) score = historyScore;

    const historyBreakdown = summary && Array.isArray(summary.breakdown)
      ? summary.breakdown.map(item => ({ ...item, group: "Histórico" }))
      : [];
    return {
      score,
      currentScore: current.score,
      historyScore,
      historyReady,
      historyQuarters,
      breakdown: current.breakdown.concat(historyBreakdown),
      applicable: current.applicable + historyBreakdown.length,
    };
  }

  function computeValuation(row) {
    const { cotacao, pl, pvp, div_yield } = row;
    let graham = null;
    if (cotacao > 0 && pl !== null && pl > 0 && pvp !== null && pvp > 0) {
      graham = Math.sqrt(22.5 * (cotacao / pl) * (cotacao / pvp));
    }
    let bazin = null;
    if (cotacao > 0 && div_yield !== null && div_yield > 0) {
      bazin = (div_yield * cotacao) / BAZIN_YIELD_MIN;
    }
    const referencia = graham ?? bazin;
    const modeloUsado = graham !== null ? "Graham" : bazin !== null ? "Bazin" : null;
    const margem = referencia !== null ? (referencia - cotacao) / cotacao : null;
    const quality = computeQuality(row);
    const currentVetos = VETOES.filter(veto => veto.test(row[veto.key])).map(veto => veto.label);
    const historyVetos = row.history && row.history.summary && Array.isArray(row.history.summary.vetos)
      ? row.history.summary.vetos
      : [];
    const vetos = currentVetos.concat(historyVetos);

    let recomendacao = "N/A";
    let alerta = false;
    const alertReasons = [];
    if (margem !== null) {
      if (margem <= MARGEM_VENDA) recomendacao = "Venda";
      else if (margem >= MARGEM_COMPRA) {
        if (!quality.historyReady) alertReasons.push("Histórico CVM insuficiente (mínimo de 8 trimestres)");
        if (quality.score === null || quality.score < QUALIDADE_MIN) alertReasons.push("Qualidade consolidada abaixo de 60");
        if (vetos.length) alertReasons.push("Há vetos fundamentalistas ativos");
        if (alertReasons.length === 0) recomendacao = "Compra";
        else {
          recomendacao = "Neutro";
          alerta = true;
        }
      } else recomendacao = "Neutro";
    }

    let rankScore = null;
    if (margem !== null) {
      const margemNorm = Math.max(0, Math.min(100, ((margem + 0.5) / 2) * 100));
      const gov = row.segmento === "NM" ? 100 : row.segmento === "N2" ? 50 : 0;
      rankScore = Math.round(0.45 * margemNorm + 0.45 * (quality.score ?? 0) + 0.10 * gov);
      if (vetos.length > 0) rankScore = Math.max(0, rankScore - 20);
      if (!quality.historyReady) rankScore = Math.max(0, rankScore - 5);
    }

    return {
      ...row,
      graham,
      bazin,
      margem,
      qualidade: quality.score,
      qualidadeAtual: quality.currentScore,
      qualidadeHistorica: quality.historyScore,
      historicoPronto: quality.historyReady,
      trimestresHistoricos: quality.historyQuarters,
      breakdown: quality.breakdown,
      applicable: quality.applicable,
      vetos,
      recomendacao,
      alerta,
      alertReasons,
      modeloUsado,
      rankScore,
    };
  }

  return {
    BAZIN_YIELD_MIN,
    MARGEM_COMPRA,
    MARGEM_VENDA,
    QUALIDADE_MIN,
    HISTORICO_MIN_TRIMESTRES,
    SEGMENTO_LABEL,
    computeCurrentQuality,
    computeQuality,
    computeValuation,
  };
});
