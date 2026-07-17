"""Gera análises fundamentalistas com DeepSeek V4 a partir de fatos calculados.

O modelo não calcula indicadores nem acessa a internet. Ele recebe um pacote de
fatos determinísticos derivado de ``data/latest.json`` e ``data/history.json`` e
devolve JSON estruturado. O resultado é armazenado em ``data/analysis.json``.

Variáveis de ambiente:

- ``DEEPSEEK_API_KEY``: chave da API oficial;
- ``DEEPSEEK_MODEL``: ``deepseek-v4-pro`` (padrão) ou ``deepseek-v4-flash``;
- ``DEEPSEEK_THINKING``: ``enabled`` (padrão) ou ``disabled``;
- ``DEEPSEEK_BASE_URL``: padrão ``https://api.deepseek.com``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
LATEST_PATH = ROOT / "data" / "latest.json"
HISTORY_PATH = ROOT / "data" / "history.json"
DEFAULT_OUTPUT = ROOT / "data" / "analysis.json"

PROMPT_VERSION = "deepseek-analyst-v1"
DEFAULT_MODEL = "deepseek-v4-pro"
ALLOWED_MODELS = {"deepseek-v4-pro", "deepseek-v4-flash"}
FINANCIAL_ACTIVITIES = {
    "Bancos",
    "Seguradoras",
    "Serviços Financeiros Diversos",
    "Holdings Diversificadas",
}

CURRENT_CRITERIA = [
    ("roe", "ROE atual", 0.15, 0.08, "higher"),
    ("roic", "ROIC atual", 0.12, 0.06, "higher"),
    ("mrg_liq", "Margem líquida atual", 0.15, 0.05, "higher"),
    ("liq_corr", "Liquidez corrente", 1.5, 1.0, "higher"),
    ("div_liq_pat", "Dívida líquida/PL", 0.5, 1.0, "lower"),
    ("cresc_rec_5a", "Crescimento da receita em 5 anos", 0.10, 0.0, "higher"),
    ("ev_ebitda", "EV/EBITDA", 6.0, 10.0, "lower_positive"),
]

SYSTEM_PROMPT = """Você é um analista fundamentalista cuidadoso e independente.
Sua tarefa é interpretar SOMENTE o JSON de fatos fornecido pelo sistema.

Regras obrigatórias:
1. Não invente números, notícias, causas, participação de mercado, qualidade da gestão ou perspectivas não presentes nos fatos.
2. Não faça recomendação pessoal de compra ou venda e não prometa retorno.
3. Diferencie claramente qualidade do negócio, riscos financeiros, crescimento e valuation.
4. Quando a causa de uma mudança não estiver nos fatos, diga que ela não pode ser determinada apenas pelos indicadores.
5. Toda afirmação material deve trazer uma ou mais chaves de evidência existentes em fatos.evidencias.
6. Use português brasileiro natural, direto e didático, como um relatório curto de research para investidor de longo prazo.
7. A resposta deve ser um objeto JSON válido, sem markdown e sem texto fora do JSON.

Formato JSON obrigatório:
{
  "titulo": "frase curta",
  "resumo": "2 a 4 frases",
  "tese": "1 parágrafo curto",
  "pontos_fortes": [{"texto": "...", "evidencias": ["chave"]}],
  "pontos_atencao": [{"texto": "...", "evidencias": ["chave"]}],
  "valuation": {"texto": "...", "evidencias": ["chave"]},
  "monitorar": ["item", "item"],
  "mudancas_desde_anterior": {"texto": "...", "evidencias": ["chave"]},
  "confianca": "alta|media|baixa",
  "limitacoes": ["item"]
}
"""


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def round_value(value: Any, digits: int = 4) -> float | None:
    number = finite(value)
    return round(number, digits) if number is not None else None


def format_percent(value: Any) -> str | None:
    number = finite(value)
    if number is None:
        return None
    return f"{number * 100:.1f}%".replace(".", ",")


def format_number(value: Any, digits: int = 2) -> str | None:
    number = finite(value)
    if number is None:
        return None
    return f"{number:.{digits}f}".replace(".", ",")


def format_currency(value: Any) -> str | None:
    number = finite(value)
    if number is None:
        return None
    return "R$ " + f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def evaluate_current_metric(key: str, value: float) -> str:
    for criterion_key, _label, good, ok, direction in CURRENT_CRITERIA:
        if criterion_key != key:
            continue
        if direction == "higher":
            return "bom" if value >= good else "ok" if value >= ok else "ruim"
        if direction == "lower":
            return "bom" if value <= good else "ok" if value <= ok else "ruim"
        if direction == "lower_positive":
            return "bom" if 0 < value <= good else "ok" if 0 < value <= ok else "ruim"
    return "sem classificação"


def compute_current_quality(row: dict[str, Any]) -> int | None:
    points = 0
    maximum = 0
    for key, _label, _good, _ok, _direction in CURRENT_CRITERIA:
        value = finite(row.get(key))
        if value is None:
            continue
        maximum += 2
        rating = evaluate_current_metric(key, value)
        points += 2 if rating == "bom" else 1 if rating == "ok" else 0
    segment_points = {"NM": 2, "N2": 1, "N1": 0, "TRAD": 0}
    if row.get("segmento"):
        maximum += 2
        points += segment_points.get(row.get("segmento"), 0)
    return round(points / maximum * 100) if maximum else None


def compute_valuation(row: dict[str, Any]) -> dict[str, Any]:
    quote = finite(row.get("cotacao"))
    pl = finite(row.get("pl"))
    pvp = finite(row.get("pvp"))
    dy = finite(row.get("div_yield"))
    graham = None
    if quote and quote > 0 and pl and pl > 0 and pvp and pvp > 0:
        graham = math.sqrt(22.5 * (quote / pl) * (quote / pvp))
    bazin = None
    if quote and quote > 0 and dy and dy > 0:
        bazin = dy * quote / 0.06
    reference = graham if graham is not None else bazin
    margin = (reference - quote) / quote if reference is not None and quote else None
    return {
        "graham": round_value(graham),
        "bazin": round_value(bazin),
        "reference_model": "Graham" if graham is not None else "Bazin" if bazin is not None else None,
        "reference_price": round_value(reference),
        "margin": round_value(margin),
    }


def current_vetoes(row: dict[str, Any]) -> list[str]:
    vetoes: list[str] = []
    debt = finite(row.get("div_liq_pat"))
    liquidity = finite(row.get("liq_corr"))
    roe = finite(row.get("roe"))
    margin = finite(row.get("mrg_liq"))
    if debt is not None and debt > 3:
        vetoes.append("Alavancagem excessiva: dívida líquida/PL acima de 3")
    if liquidity is not None and liquidity < 0.8:
        vetoes.append("Liquidez corrente crítica abaixo de 0,8")
    if roe is not None and roe < 0:
        vetoes.append("ROE atual negativo")
    if margin is not None and margin < 0:
        vetoes.append("Margem líquida atual negativa")
    return vetoes


def add_evidence(store: dict[str, dict[str, Any]], key: str, label: str, value: Any, formatted: str | None) -> None:
    if value is None:
        return
    store[key] = {"rotulo": label, "valor": value, "formatado": formatted}


def build_facts(row: dict[str, Any], company_history: dict[str, Any] | None) -> dict[str, Any]:
    history = company_history or {}
    summary = history.get("summary") or {}
    valuation = compute_valuation(row)
    current_score = compute_current_quality(row)
    history_score = finite(summary.get("history_score"))
    quarters = int(finite(summary.get("quarters_count")) or 0)
    quality = current_score
    if current_score is not None and history_score is not None and quarters >= 8:
        quality = round(current_score * 0.65 + history_score * 0.35)

    evidence: dict[str, dict[str, Any]] = {}
    metric_labels = {
        "cotacao": "Cotação",
        "pl": "P/L",
        "pvp": "P/VP",
        "div_yield": "Dividend yield",
        "ev_ebitda": "EV/EBITDA",
        "roe": "ROE atual",
        "roic": "ROIC atual",
        "mrg_liq": "Margem líquida atual",
        "liq_corr": "Liquidez corrente",
        "div_liq_pat": "Dívida líquida/PL atual",
        "cresc_rec_5a": "Crescimento da receita em 5 anos",
    }
    percentage_keys = {"div_yield", "roe", "roic", "mrg_liq", "cresc_rec_5a"}
    for key, label in metric_labels.items():
        value = round_value(row.get(key))
        formatted = format_percent(value) if key in percentage_keys else format_currency(value) if key == "cotacao" else format_number(value)
        add_evidence(evidence, key, label, value, formatted)

    history_metrics = {
        "quarters_count": ("Trimestres analisados", quarters, str(quarters)),
        "profitable_quarters_ratio": ("Trimestres com lucro", round_value(summary.get("profitable_quarters_ratio")), format_percent(summary.get("profitable_quarters_ratio"))),
        "revenue_cagr": ("CAGR histórico da receita", round_value(summary.get("revenue_cagr")), format_percent(summary.get("revenue_cagr"))),
        "positive_revenue_years_ratio": ("Anos com receita crescente", round_value(summary.get("positive_revenue_years_ratio")), format_percent(summary.get("positive_revenue_years_ratio"))),
        "margin_volatility": ("Volatilidade histórica da margem", round_value(summary.get("margin_volatility")), format_percent(summary.get("margin_volatility"))),
        "roe_ttm": ("ROE dos últimos 12 meses", round_value(summary.get("roe_ttm")), format_percent(summary.get("roe_ttm"))),
        "net_debt_to_equity": ("Dívida líquida/PL histórica", round_value(summary.get("net_debt_to_equity")), format_number(summary.get("net_debt_to_equity"))),
        "net_debt_trend": ("Variação histórica da dívida líquida", round_value(summary.get("net_debt_trend")), format_percent(summary.get("net_debt_trend"))),
        "positive_fcf_years_ratio": ("Anos com FCL aproximado positivo", round_value(summary.get("positive_free_cash_flow_years_ratio")), format_percent(summary.get("positive_free_cash_flow_years_ratio"))),
        "fcf_years_count": ("Anos completos de fluxo de caixa", int(finite(summary.get("free_cash_flow_years_count")) or 0), str(int(finite(summary.get("free_cash_flow_years_count")) or 0))),
        "normalized_fcf_million": ("FCL aproximado normalizado em milhões", round_value(summary.get("normalized_free_cash_flow_million"), 2), format_number(summary.get("normalized_free_cash_flow_million"), 0)),
    }
    for key, (label, value, formatted) in history_metrics.items():
        add_evidence(evidence, key, label, value, formatted)

    add_evidence(evidence, "quality_current", "Qualidade atual", current_score, str(current_score) if current_score is not None else None)
    add_evidence(evidence, "quality_history", "Qualidade histórica", round_value(history_score, 0), str(round(history_score)) if history_score is not None else None)
    add_evidence(evidence, "quality_combined", "Qualidade consolidada", quality, str(quality) if quality is not None else None)
    add_evidence(evidence, "fair_price_reference", "Preço justo de referência", valuation["reference_price"], format_currency(valuation["reference_price"]))
    add_evidence(evidence, "safety_margin", "Margem de segurança", valuation["margin"], format_percent(valuation["margin"]))

    current_assessments = []
    for key, label, _good, _ok, _direction in CURRENT_CRITERIA:
        value = finite(row.get(key))
        if value is not None:
            current_assessments.append({"chave": key, "rotulo": label, "avaliacao": evaluate_current_metric(key, value)})

    history_vetoes = summary.get("vetos") if isinstance(summary.get("vetos"), list) else []
    all_vetoes = current_vetoes(row) + [str(item) for item in history_vetoes]

    confidence = "alta" if quarters >= 16 else "media" if quarters >= 8 else "baixa"
    if len(evidence) < 10:
        confidence = "baixa"

    return {
        "ticker": row.get("papel"),
        "empresa": history.get("company_name") or row.get("papel"),
        "setor": row.get("setor"),
        "atividade": row.get("atividade"),
        "governanca": row.get("segmento"),
        "data_mercado": row.get("data_coleta"),
        "qualidade": {
            "atual": current_score,
            "historica": round(history_score) if history_score is not None else None,
            "consolidada": quality,
            "confianca_dos_dados": confidence,
        },
        "valuation": valuation,
        "avaliacoes_atuais": current_assessments,
        "vetos": all_vetoes,
        "historico_disponivel": bool(history),
        "evidencias": evidence,
    }


def facts_hash(facts: dict[str, Any], model: str) -> str:
    payload = {"prompt_version": PROMPT_VERSION, "model": model, "facts": facts}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prompt_for(facts: dict[str, Any], previous: dict[str, Any] | None) -> str:
    previous_payload = None
    if previous:
        previous_payload = {
            "fatos_anteriores": previous.get("facts"),
            "analise_anterior": previous.get("analysis"),
        }
    return (
        "Produza a análise em JSON conforme o formato exigido. "
        "Use apenas as chaves disponíveis em fatos.evidencias. "
        "Se não houver análise anterior, mudancas_desde_anterior.texto deve informar que esta é a primeira análise.\n\n"
        + json.dumps({"fatos": facts, "anterior": previous_payload}, ensure_ascii=False, separators=(",", ":"))
    )


def request_deepseek(
    facts: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    api_key: str,
    model: str,
    base_url: str,
    thinking: str,
    session: requests.Session,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_for(facts, previous)},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": thinking},
        "reasoning_effort": "high",
        "max_tokens": 2200,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            response = session.post(url, headers=headers, json=payload, timeout=(20, 240))
            if response.status_code in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"DeepSeek HTTP {response.status_code}: {response.text[:300]}")
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not content:
                raise RuntimeError("DeepSeek retornou conteúdo vazio")
            return json.loads(content)
        except (requests.RequestException, RuntimeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(min(30, attempt * 5))
    raise RuntimeError(f"Falha ao gerar análise no DeepSeek: {last_error}")


def require_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo {field} deve ser texto não vazio")
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) > maximum:
        raise ValueError(f"Campo {field} excede {maximum} caracteres")
    return text


def validate_claim(value: Any, field: str, evidence_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Campo {field} deve ser objeto")
    text = require_text(value.get("texto"), f"{field}.texto", 500)
    evidence = value.get("evidencias")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"Campo {field}.evidencias deve ser lista não vazia")
    cleaned = []
    for key in evidence:
        if not isinstance(key, str) or key not in evidence_keys:
            raise ValueError(f"Evidência inválida em {field}: {key}")
        if key not in cleaned:
            cleaned.append(key)
    return {"texto": text, "evidencias": cleaned}


def validate_analysis(raw: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Resposta da IA deve ser objeto JSON")
    evidence_keys = set(facts.get("evidencias", {}))
    result = {
        "titulo": require_text(raw.get("titulo"), "titulo", 120),
        "resumo": require_text(raw.get("resumo"), "resumo", 900),
        "tese": require_text(raw.get("tese"), "tese", 900),
    }
    for list_field in ("pontos_fortes", "pontos_atencao"):
        values = raw.get(list_field)
        if not isinstance(values, list) or not 1 <= len(values) <= 6:
            raise ValueError(f"Campo {list_field} deve ter de 1 a 6 itens")
        result[list_field] = [validate_claim(item, f"{list_field}[{index}]", evidence_keys) for index, item in enumerate(values)]
    result["valuation"] = validate_claim(raw.get("valuation"), "valuation", evidence_keys)
    result["mudancas_desde_anterior"] = validate_claim(raw.get("mudancas_desde_anterior"), "mudancas_desde_anterior", evidence_keys)

    monitor = raw.get("monitorar")
    if not isinstance(monitor, list) or not 1 <= len(monitor) <= 6:
        raise ValueError("Campo monitorar deve ter de 1 a 6 itens")
    result["monitorar"] = [require_text(item, f"monitorar[{index}]", 220) for index, item in enumerate(monitor)]

    limitations = raw.get("limitacoes")
    if not isinstance(limitations, list):
        raise ValueError("Campo limitacoes deve ser lista")
    result["limitacoes"] = [require_text(item, f"limitacoes[{index}]", 260) for index, item in enumerate(limitations[:6])]

    confidence = raw.get("confianca")
    if confidence not in {"alta", "media", "baixa"}:
        raise ValueError("Confiança deve ser alta, media ou baixa")
    result["confianca"] = confidence

    forbidden = ("compre", "venda imediatamente", "garantido", "vai subir", "vai cair")
    joined = json.dumps(result, ensure_ascii=False).lower()
    if any(term in joined for term in forbidden):
        raise ValueError("Resposta contém linguagem de recomendação ou certeza indevida")
    return result


def generate(
    latest: dict[str, Any],
    history: dict[str, Any],
    previous_output: dict[str, Any],
    *,
    api_key: str,
    model: str,
    base_url: str,
    thinking: str,
    force: bool = False,
    ticker_filter: set[str] | None = None,
    limit: int | None = None,
) -> tuple[dict[str, Any], list[str]]:
    previous_companies = previous_output.get("companies") if isinstance(previous_output.get("companies"), dict) else {}
    companies: dict[str, Any] = dict(previous_companies)
    history_companies = history.get("companies") if isinstance(history.get("companies"), dict) else {}
    rows = latest.get("rows") if isinstance(latest.get("rows"), list) else []
    generated = 0
    errors: list[str] = []

    with requests.Session() as session:
        for row in rows:
            ticker = str(row.get("papel") or "").upper()
            if not ticker or (ticker_filter and ticker not in ticker_filter):
                continue
            facts = build_facts({**row, "data_coleta": latest.get("data_coleta")}, history_companies.get(ticker))
            digest = facts_hash(facts, model)
            previous = previous_companies.get(ticker)
            if not force and previous and previous.get("facts_hash") == digest:
                continue
            if limit is not None and generated >= limit:
                break
            try:
                raw = request_deepseek(
                    facts,
                    previous,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    thinking=thinking,
                    session=session,
                )
                analysis = validate_analysis(raw, facts)
                companies[ticker] = {
                    "data_geracao": date.today().isoformat(),
                    "modelo": model,
                    "prompt_version": PROMPT_VERSION,
                    "facts_hash": digest,
                    "facts": facts,
                    "analysis": analysis,
                }
                generated += 1
                print(f"OK {ticker}: análise gerada com {model}")
            except Exception as exc:  # mantém análise anterior quando possível
                message = f"{ticker}: {exc}"
                errors.append(message)
                print(f"ERRO {message}")

    valid_tickers = {str(row.get("papel") or "").upper() for row in rows}
    companies = {ticker: item for ticker, item in companies.items() if ticker in valid_tickers}
    output = {
        "data_geracao": date.today().isoformat(),
        "fonte": "DeepSeek API sobre fatos determinísticos do projeto",
        "modelo_padrao": model,
        "prompt_version": PROMPT_VERSION,
        "mercado_data": latest.get("data_coleta"),
        "historico_data": history.get("data_coleta"),
        "total": len(companies),
        "geradas_nesta_execucao": generated,
        "erros": errors,
        "companies": companies,
    }
    return output, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    latest = load_json(LATEST_PATH)
    history = load_json(HISTORY_PATH, {"companies": {}, "data_coleta": "seed"})
    previous = load_json(args.output, {"companies": {}})

    if args.validate_only:
        for ticker, item in previous.get("companies", {}).items():
            validate_analysis(item.get("analysis"), item.get("facts") or {})
            print(f"OK {ticker}")
        return

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY não configurada")
    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL).strip()
    if model not in ALLOWED_MODELS:
        raise SystemExit(f"DEEPSEEK_MODEL inválido: {model}. Use {sorted(ALLOWED_MODELS)}")
    thinking = os.environ.get("DEEPSEEK_THINKING", "enabled").strip().lower()
    if thinking not in {"enabled", "disabled"}:
        raise SystemExit("DEEPSEEK_THINKING deve ser enabled ou disabled")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    tickers = {ticker.strip().upper() for ticker in args.ticker if ticker.strip()} or None

    output, errors = generate(
        latest,
        history,
        previous,
        api_key=api_key,
        model=model,
        base_url=base_url,
        thinking=thinking,
        force=args.force,
        ticker_filter=tickers,
        limit=args.limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    print(f"Análises disponíveis: {output['total']}; novas: {output['geradas_nesta_execucao']}")

    attempted = output["geradas_nesta_execucao"] + len(errors)
    if errors and (attempted == 0 or len(errors) / attempted > 0.20):
        raise SystemExit(f"Muitas falhas na geração: {len(errors)}/{attempted}")


if __name__ == "__main__":
    main()
