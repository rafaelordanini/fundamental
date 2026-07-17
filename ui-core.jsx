const { useState, useMemo, useEffect } = React;
const {
  MARGEM_COMPRA,
  MARGEM_VENDA,
  QUALIDADE_MIN,
  HISTORICO_MIN_TRIMESTRES,
  SEGMENTO_LABEL,
  computeDCF,
  getDcfDefaults,
  computeValuation,
} = window.FundamentalScore;

const COLUMNS = [
  { key: "rankScore", label: "Score", fmt: "score" },
  { key: "papel", label: "Papel", fmt: "ticker" },
  { key: "setor", label: "Setor", fmt: "setor" },
  { key: "segmento", label: "Gov.", fmt: "segmento" },
  { key: "cotacao", label: "Cotação", fmt: "brl" },
  { key: "pl", label: "P/L", fmt: "num" },
  { key: "div_yield", label: "DY", fmt: "pct" },
  { key: "roe", label: "ROE", fmt: "pct" },
  { key: "div_liq_pat", label: "DívLíq/PL", fmt: "num" },
  { key: "graham", label: "Justo", fmt: "brl" },
  { key: "margem", label: "Margem", fmt: "pctSigned" },
  { key: "qualidadeHistorica", label: "Hist.", fmt: "history" },
  { key: "qualidade", label: "Qualidade", fmt: "quality" },
  { key: "analysisEntry", label: "Análise", fmt: "analysis" },
  { key: "recomendacao", label: "Sinal", fmt: "badge" },
];

function formatValue(value, fmt) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (fmt === "text" || fmt === "badge") return value;
  if (fmt === "brl") return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  if (fmt === "pct") return (value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
  if (fmt === "pctSigned") {
    const sign = value > 0 ? "+" : "";
    return sign + (value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
  }
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

function formatMillion(value) {
  if (!Number.isFinite(value)) return "—";
  return "R$ " + value.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " mi";
}

function formatDate(value) {
  if (!value || value === "seed") return "—";
  return new Date(value + "T12:00:00").toLocaleDateString("pt-BR");
}

function valueColor(key, value) {
  if (value === null || value === undefined) return "text-gray-400";
  if (key === "margem") {
    if (value >= MARGEM_COMPRA) return "text-emerald-600 font-semibold";
    if (value <= MARGEM_VENDA) return "text-red-600 font-semibold";
    return "text-gray-600";
  }
  if ((key === "roe" || key === "pl") && value < 0) return "text-red-600";
  if (key === "div_liq_pat" && value > 3) return "text-red-600 font-semibold";
  return "text-gray-800";
}

function compareRank(a, b) {
  const scoreDiff = (b.rankScore ?? -1) - (a.rankScore ?? -1);
  if (scoreDiff !== 0) return scoreDiff;
  const qualityDiff = (b.qualidade ?? -1) - (a.qualidade ?? -1);
  if (qualityDiff !== 0) return qualityDiff;
  const marginDiff = (b.margem ?? -Infinity) - (a.margem ?? -Infinity);
  if (marginDiff !== 0) return marginDiff;
  return a.papel.localeCompare(b.papel);
}

function SegmentoBadge({ value }) {
  if (!value) return <span className="text-gray-400">—</span>;
  const styles = {
    NM: "bg-emerald-100 text-emerald-700 border-emerald-300",
    N2: "bg-blue-100 text-blue-700 border-blue-200",
    N1: "bg-gray-100 text-gray-600 border-gray-200",
    TRAD: "bg-gray-50 text-gray-500 border-gray-200",
  };
  return <span className={"inline-flex items-center gap-0.5 rounded border px-1.5 py-0.5 text-xs font-semibold " + (styles[value] ?? styles.TRAD)} title={SEGMENTO_LABEL[value] ?? value}>{value === "NM" ? "🛡 " : ""}{value}</span>;
}

function SectorCell({ row }) {
  return <div className="max-w-48 whitespace-normal leading-tight" title={`${row.setor} — ${row.atividade}`}>
    <div className="text-xs font-semibold text-gray-700">{row.setor}</div>
    <div className="mt-0.5 text-[11px] text-gray-400">{row.atividade}</div>
  </div>;
}

function ScoreBadge({ value, rank }) {
  if (value === null) return <span className="text-gray-400">—</span>;
  const style = value >= 65 ? "text-emerald-700 bg-emerald-50 border-emerald-200" : value >= 45 ? "text-gray-700 bg-gray-50 border-gray-200" : "text-red-600 bg-red-50 border-red-100";
  return <span className={"inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 text-sm font-bold " + style} title={rank ? `${rank}º no recorte atual` : ""}>{rank !== null && rank <= 3 ? "🏆 " : ""}{value}</span>;
}

function QualityBar({ score }) {
  if (score === null) return <span className="text-gray-400">—</span>;
  const color = score >= 60 ? "bg-emerald-500" : score >= 40 ? "bg-amber-400" : "bg-red-400";
  return <div className="flex items-center gap-2">
    <div className="h-2 w-16 overflow-hidden rounded-full bg-gray-200"><div className={"h-full " + color} style={{ width: score + "%" }} /></div>
    <span className="text-xs font-medium text-gray-600">{score}</span>
  </div>;
}

function HistoryBadge({ row }) {
  if (!row.history) return <span className="text-xs text-gray-400" title="Histórico CVM indisponível">—</span>;
  const ready = row.historicoPronto;
  return <span className={"inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold " + (ready ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-amber-200 bg-amber-50 text-amber-700")} title={`${row.trimestresHistoricos} trimestres`}>{row.qualidadeHistorica ?? "—"} · {row.trimestresHistoricos}t</span>;
}

function AnalysisBadge({ entry }) {
  if (!entry?.analysis) return <span className="text-xs text-gray-400">—</span>;
  const confidence = entry.analysis.confianca;
  const style = confidence === "alta" ? "border-violet-200 bg-violet-50 text-violet-700" : confidence === "media" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-gray-200 bg-gray-50 text-gray-500";
  return <span className={"inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold " + style} title={`${entry.modelo} · ${formatDate(entry.data_geracao)}`}>IA · {confidence}</span>;
}

function RecomendacaoBadge({ row, onDetail }) {
  const styles = { Compra: "bg-emerald-100 text-emerald-700 border-emerald-200", Venda: "bg-red-100 text-red-700 border-red-200", Neutro: "bg-gray-100 text-gray-600 border-gray-200", "N/A": "bg-gray-50 text-gray-400 border-gray-100" };
  return <button onClick={() => onDetail(row)} className={"inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-transform hover:scale-105 " + styles[row.recomendacao]}>{row.recomendacao}{row.alerta ? " ⚠" : ""}</button>;
}

function Sparkline({ values, label }) {
  const clean = (values || []).filter(value => Number.isFinite(value));
  if (clean.length < 2) return <p className="text-xs text-gray-400">Série insuficiente.</p>;
  const width = 360, height = 82, pad = 7;
  const min = Math.min(...clean, 0), max = Math.max(...clean, 0), span = max - min || 1;
  const points = clean.map((value, index) => `${pad + index * (width - 2 * pad) / (clean.length - 1)},${pad + (max - value) * (height - 2 * pad) / span}`).join(" ");
  const zeroY = pad + max * (height - 2 * pad) / span;
  return <svg viewBox={`0 0 ${width} ${height}`} className="h-24 w-full rounded bg-gray-50" role="img" aria-label={label}>
    <line x1={pad} y1={zeroY} x2={width - pad} y2={zeroY} stroke="#d1d5db" strokeWidth="1"/>
    <polyline points={points} fill="none" stroke="#4f46e5" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"/>
  </svg>;
}

function Breakdown({ items, group }) {
  const filtered = items.filter(item => item.group === group);
  if (!filtered.length) return <p className="text-xs text-gray-400">Sem critérios aplicáveis.</p>;
  return <div className="space-y-1">{filtered.map(item => <div key={group + item.label} className="flex items-center justify-between gap-3 text-sm">
    <span className="text-gray-600">{item.label}{item.value ? ` · ${item.value}` : ""}</span>
    <span className={item.pts === 2 ? "whitespace-nowrap text-emerald-600" : item.pts === 1 ? "whitespace-nowrap text-amber-500" : "whitespace-nowrap text-red-500"}>{item.pts === 2 ? "●● bom" : item.pts === 1 ? "●○ ok" : "○○ ruim"}</span>
  </div>)}</div>;
}

function AssumptionInput({ label, value, onChange, suffix, min, max, step }) {
  return <label className="text-xs font-semibold text-gray-500">{label}
    <div className="mt-1 flex items-center rounded-lg border border-gray-300 bg-white">
      <input type="number" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))} className="w-full rounded-l-lg px-3 py-2 text-sm font-normal text-gray-800 outline-none"/>
      <span className="pr-3 text-xs text-gray-400">{suffix}</span>
    </div>
  </label>;
}

Object.assign(window.FundamentalUI = window.FundamentalUI || {}, {
  React, useState, useMemo, useEffect,
  MARGEM_COMPRA, MARGEM_VENDA, QUALIDADE_MIN, HISTORICO_MIN_TRIMESTRES,
  SEGMENTO_LABEL, computeDCF, getDcfDefaults, computeValuation,
  COLUMNS, formatValue, formatMillion, formatDate, valueColor, compareRank,
  SegmentoBadge, SectorCell, ScoreBadge, QualityBar, HistoryBadge,
  AnalysisBadge, RecomendacaoBadge, Sparkline, Breakdown, AssumptionInput,
});
