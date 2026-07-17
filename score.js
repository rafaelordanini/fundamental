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
  const DCF_DEFAULT_DISCOUNT_RATE = 0.12;
  const DCF_DEFAULT_TERMINAL_GROWTH = 0.03;
  const DCF_DEFAULT_YEARS = 5;

  const SEGMENTO_LABEL = { NM: "Novo Mercado", N2: "Nível 2", N1: "Nível 1", TRAD: "Tradicional" };
  const SEGMENTO_PTS = { NM: 2, N2: 1, N1: 0, TRAD: 0 };
  const DCF_DISABLED_ACTIVITIES = new Set(["Bancos", "Seguradoras", "Holdings financeiras"]);

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

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

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

  function getDcfDefaults(row) {
    const summary = row && row.history && row.history.summary ? row.history.summary : {};
    const historicalGrowth = Number.isFinite(summary.revenue_cagr) ? summary.revenue_cagr : 0.04;
    return {
      growthRate: clamp(historicalGrowth, -0.05, 0.10),
      discountRate: DCF_DEFAULT_DISCOUNT_RATE,
      terminalGrowthRate: DCF_DEFAULT_TERMINAL_GROWTH,
      years: DCF_DEFAULT_YEARS,
    };
  }

  function estimateSharesMillion(row) {
    const summary = row && row.history && row.history.summary ? row.history.summary : {};
    const cotacao = Number(row && row.cotacao);
    const pvp = Number(row && row.pvp);
    const equity = Number(summary.latest_equity_million);
    if (cotacao > 0 && pvp > 0 && equity > 0) {
      const bookValuePerShare = cotacao / pvp;
      const shares = equity / bookValuePerShare;
      if (Number.isFinite(shares) && shares > 0) {
        return { sharesMillion: shares, method: "Patrimônio líquido ÷ VPA estimado" };
      }
    }

    const pl = Number(row && row.pl);
    const ttmProfit = Number(summary.ttm_net_income_million);
    if (cotacao > 0 && pl > 0 && ttmProfit > 0) {
      const earningsPerShare = cotacao / pl;
      const shares = ttmProfit / earningsPerShare;
      if (Number.isFinite(shares) && shares > 0) {
        return { sharesMillion: shares, method: "Lucro TTM ÷ LPA estimado" };
      }
    }
    return { sharesMillion: null, method: null };
  }

  function computeDCF(row, assumptions) {
    const defaults = getDcfDefaults(row || {});
    const chosen = assumptions || {};
    const summary = row && row.history && row.history.summary ? row.history.summary : null;
    const activity = row && row.atividade ? row.atividade : "";

    if (DCF_DISABLED_ACTIVITIES.has(activity)) {
      return {
        available: false,
        reason: "O FCD por fluxo de caixa livre não é adequado para bancos, seguradoras e holdings financeiras.",
        defaults,
      };
    }
    if (!summary) {
      return { available: false, reason: "Histórico CVM indisponível.", defaults };
    }

    const normalizedFcf = Number(summary.normalized_free_cash_flow_million);
    if (!Number.isFinite(normalizedFcf) || normalizedFcf <= 0) {
      return {
        available: false,
        reason: "Não há fluxo de caixa livre normalizado positivo suficiente para projetar.",
        defaults,
      };
    }

    const shareEstimate = estimateSharesMillion(row);
    if (!Number.isFinite(shareEstimate.sharesMillion) || shareEstimate.sharesMillion <= 0) {
      return {
        available: false,
        reason: "Não foi possível estimar a quantidade de ações com os dados atuais.",
        defaults,
      };
    }

    const growthRate = Number.isFinite(chosen.growthRate) ? chosen.growthRate : defaults.growthRate;
    const discountRate = Number.isFinite(chosen.discountRate) ? chosen.discountRate : defaults.discountRate;
    const terminalGrowthRate = Number.isFinite(chosen.terminalGrowthRate) ? chosen.terminalGrowthRate : defaults.terminalGrowthRate;
    const years = clamp(Math.round(Number.isFinite(chosen.years) ? chosen.years : defaults.years), 3, 10);

    if (growthRate <= -1) return { available: false, reason: "A taxa de crescimento deve ser superior a -100%.", defaults };
    if (discountRate <= 0 || discountRate <= terminalGrowthRate) {
      return {
        available: false,
        reason: "A taxa de desconto deve ser positiva e superior ao crescimento na perpetuidade.",
        defaults,
      };
    }

    const projection = [];
    let presentValueExplicit = 0;
    let projectedFcf = normalizedFcf;
    for (let year = 1; year <= years; year += 1) {
      projectedFcf *= 1 + growthRate;
      const presentValue = projectedFcf / Math.pow(1 + discountRate, year);
      presentValueExplicit += presentValue;
      projection.push({ year, freeCashFlowMillion: projectedFcf, presentValueMillion: presentValue });
    }

    const terminalValue = projectedFcf * (1 + terminalGrowthRate) / (discountRate - terminalGrowthRate);
    const terminalPresentValue = terminalValue / Math.pow(1 + discountRate, years);
    const equityValueMillion = presentValueExplicit + terminalPresentValue;
    const fairPrice = equityValueMillion / shareEstimate.sharesMillion;
    const currentPrice = Number(row.cotacao);
    const margin = currentPrice > 0 ? (fairPrice - currentPrice) / currentPrice : null;
    const terminalWeight = equityValueMillion > 0 ? terminalPresentValue / equityValueMillion : null;

    const fcfYears = Number(summary.free_cash_flow_years_count) || 0;
    const positiveRatio = Number(summary.positive_free_cash_flow_years_ratio);
    let confidence = "Baixa";
    if (fcfYears >= 4 && positiveRatio >= 0.75) confidence = "Alta";
    else if (fcfYears >= 2 && positiveRatio >= 0.50) confidence = "Média";

    return {
      available: Number.isFinite(fairPrice) && fairPrice > 0,
      reason: Number.isFinite(fairPrice) && fairPrice > 0 ? null : "O cálculo não produziu um valor válido.",
      fairPrice,
      margin,
      baseFreeCashFlowMillion: normalizedFcf,
      sharesMillion: shareEstimate.sharesMillion,
      sharesMethod: shareEstimate.method,
      growthRate,
      discountRate,
      terminalGrowthRate,
      years,
      projection,
      presentValueExplicitMillion: presentValueExplicit,
      terminalValueMillion: terminalValue,
      terminalPresentValueMillion: terminalPresentValue,
      terminalWeight,
      equityValueMillion,
      confidence,
      freeCashFlowYears: fcfYears,
      positiveFreeCashFlowYearsRatio: Number.isFinite(positiveRatio) ? positiveRatio : null,
      method: summary.free_cash_flow_method || "Caixa operacional + caixa de investimentos",
      defaults,
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
      dcfBase: computeDCF(row),
    };
  }

  return {
    BAZIN_YIELD_MIN,
    MARGEM_COMPRA,
    MARGEM_VENDA,
    QUALIDADE_MIN,
    HISTORICO_MIN_TRIMESTRES,
    DCF_DEFAULT_DISCOUNT_RATE,
    DCF_DEFAULT_TERMINAL_GROWTH,
    DCF_DEFAULT_YEARS,
    SEGMENTO_LABEL,
    computeCurrentQuality,
    computeQuality,
    getDcfDefaults,
    estimateSharesMillion,
    computeDCF,
    computeValuation,
  };
});
