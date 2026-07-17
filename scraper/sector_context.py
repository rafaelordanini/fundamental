"""Calcula comparação setorial determinística para cada ação monitorada.

A comparação usa preferencialmente empresas da mesma atividade. Quando há menos
de três pares, recua para o setor amplo. Percentil 100 significa melhor posição
relativa no indicador, respeitando se valores maiores ou menores são desejáveis.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "data" / "latest.json"
HISTORY_PATH = ROOT / "data" / "history.json"
OUTPUT_PATH = ROOT / "data" / "sector_context.json"

METRICS = {
    "roe": ("ROE atual", "higher", "quality"),
    "roic": ("ROIC atual", "higher", "quality"),
    "mrg_liq": ("Margem líquida", "higher", "quality"),
    "liq_corr": ("Liquidez corrente", "higher", "quality"),
    "div_liq_pat": ("Dívida líquida/PL", "lower", "quality"),
    "cresc_rec_5a": ("Crescimento da receita em 5 anos", "higher", "quality"),
    "history_score": ("Qualidade histórica", "higher", "quality"),
    "profitable_quarters_ratio": ("Trimestres lucrativos", "higher", "quality"),
    "revenue_cagr": ("CAGR histórico da receita", "higher", "quality"),
    "roe_ttm": ("ROE TTM", "higher", "quality"),
    "net_debt_to_equity": ("Dívida líquida/PL histórica", "lower", "quality"),
    "positive_free_cash_flow_years_ratio": ("Anos com FCL positivo", "higher", "quality"),
    "pl": ("P/L", "lower_positive", "valuation"),
    "pvp": ("P/VP", "lower_positive", "valuation"),
    "ev_ebitda": ("EV/EBITDA", "lower_positive", "valuation"),
    "div_yield": ("Dividend yield", "higher", "valuation"),
}

HISTORY_KEYS = {
    "history_score",
    "profitable_quarters_ratio",
    "revenue_cagr",
    "roe_ttm",
    "net_debt_to_equity",
    "positive_free_cash_flow_years_ratio",
}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def metric_value(row: dict[str, Any], history: dict[str, Any] | None, key: str) -> float | None:
    source = (history or {}).get("summary", {}) if key in HISTORY_KEYS else row
    value = finite(source.get(key))
    direction = METRICS[key][1]
    if value is not None and direction == "lower_positive" and value <= 0:
        return None
    return value


def percentile(values: list[float], value: float, direction: str) -> float:
    """Percentil de qualidade entre 0 e 1, com empate no ponto médio."""
    if not values:
        return 0.5
    better = 0
    equal = 0
    for candidate in values:
        if math.isclose(candidate, value, rel_tol=1e-9, abs_tol=1e-12):
            equal += 1
        elif direction in {"lower", "lower_positive"}:
            better += candidate > value
        else:
            better += candidate < value
    return round((better + equal * 0.5) / len(values), 4)


def choose_group(row: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[str, str, list[dict[str, Any]]]:
    activity = row.get("atividade")
    sector = row.get("setor")
    activity_peers = [item for item in rows if activity and item.get("atividade") == activity]
    if len(activity_peers) >= 3:
        return "atividade", str(activity), activity_peers
    sector_peers = [item for item in rows if sector and item.get("setor") == sector]
    if len(sector_peers) >= 3:
        return "setor", str(sector), sector_peers
    return "mercado", "IBOV monitorado", rows


def average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def build_context(latest: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    rows = latest.get("rows") if isinstance(latest.get("rows"), list) else []
    histories = history.get("companies") if isinstance(history.get("companies"), dict) else {}
    companies: dict[str, Any] = {}

    for row in rows:
        ticker = str(row.get("papel") or "").upper()
        if not ticker:
            continue
        scope, group_name, peers = choose_group(row, rows)
        peer_histories = {str(item.get("papel") or "").upper(): histories.get(str(item.get("papel") or "").upper()) for item in peers}
        metrics: dict[str, Any] = {}
        quality_percentiles: list[float] = []
        valuation_percentiles: list[float] = []

        for key, (label, direction, category) in METRICS.items():
            value = metric_value(row, histories.get(ticker), key)
            if value is None:
                continue
            peer_values = []
            for peer in peers:
                peer_ticker = str(peer.get("papel") or "").upper()
                peer_value = metric_value(peer, peer_histories.get(peer_ticker), key)
                if peer_value is not None:
                    peer_values.append(peer_value)
            if len(peer_values) < 2:
                continue
            pct = percentile(peer_values, value, direction)
            metrics[key] = {
                "label": label,
                "value": round(value, 4),
                "median": round(statistics.median(peer_values), 4),
                "percentile": pct,
                "direction": direction,
                "sample": len(peer_values),
            }
            (quality_percentiles if category == "quality" else valuation_percentiles).append(pct)

        quality = average(quality_percentiles)
        valuation = average(valuation_percentiles)
        combined_parts = []
        combined_weights = []
        if quality is not None:
            combined_parts.append(quality * 0.65)
            combined_weights.append(0.65)
        if valuation is not None:
            combined_parts.append(valuation * 0.35)
            combined_weights.append(0.35)
        combined = round(sum(combined_parts) / sum(combined_weights), 4) if combined_weights else None

        ordered = sorted(metrics.items(), key=lambda item: item[1]["percentile"], reverse=True)
        strengths = [key for key, item in ordered if item["percentile"] >= 0.65][:4]
        weaknesses = [key for key, item in reversed(ordered) if item["percentile"] <= 0.35][:4]
        companies[ticker] = {
            "scope": scope,
            "group": group_name,
            "peer_count": len(peers),
            "quality_percentile": quality,
            "valuation_percentile": valuation,
            "combined_percentile": combined,
            "metrics": metrics,
            "strengths": strengths,
            "weaknesses": weaknesses,
        }

    # Posições relativas calculadas dentro do mesmo grupo escolhido.
    buckets: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    for ticker, item in companies.items():
        buckets.setdefault((item["scope"], item["group"]), []).append((ticker, item))
    for items in buckets.values():
        for score_key, rank_key in (
            ("quality_percentile", "quality_rank"),
            ("valuation_percentile", "valuation_rank"),
            ("combined_percentile", "combined_rank"),
        ):
            ranked = sorted(items, key=lambda pair: (pair[1].get(score_key) is not None, pair[1].get(score_key) or -1), reverse=True)
            for position, (ticker, item) in enumerate(ranked, 1):
                item[rank_key] = position if item.get(score_key) is not None else None
        top = sorted(items, key=lambda pair: pair[1].get("combined_percentile") or -1, reverse=True)[:5]
        top_peers = [{"ticker": ticker, "combined_percentile": item.get("combined_percentile")} for ticker, item in top]
        for _, item in items:
            item["top_peers"] = top_peers

    return {
        "data_geracao": latest.get("data_coleta"),
        "fonte": "Indicadores do projeto; comparação calculada sem IA",
        "metodologia": "atividade com mínimo de 3 pares; fallback setor e mercado; percentil 100 = melhor",
        "total": len(companies),
        "companies": companies,
    }


def main() -> None:
    latest = load_json(LATEST_PATH, {"rows": []})
    history = load_json(HISTORY_PATH, {"companies": {}})
    output = build_context(latest, history)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    print(f"Comparação setorial gerada para {output['total']} empresas")


if __name__ == "__main__":
    main()
