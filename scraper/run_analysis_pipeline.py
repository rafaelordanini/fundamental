"""Executa a análise contextual com bootstrap seguro e validação endurecida.

Esta camada mantém o gerador existente, mas impede que caches vazios ou respostas
malformadas da IA sejam persistidos. A saída é gravada de forma atômica para que
uma interrupção não deixe ``data/analysis.json`` truncado.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import run_contextual_analysis as _resilient  # noqa: F401  # aplica retries e contexto
import deepseek_analysis as base


def load_json_hardened(path: Path, default: Any | None = None) -> Any:
    """Lê JSON e aceita cache ausente ou vazio somente quando há fallback."""
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        if default is not None:
            print(f"AVISO: {path} está vazio; usando estrutura inicial segura.")
            return default
        raise ValueError(f"Arquivo JSON vazio: {path}")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if default is not None and path.resolve() == base.DEFAULT_OUTPUT.resolve():
            print(f"AVISO: {path} está inválido; preservando o pipeline com cache vazio.")
            return default
        raise


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


_EMPTY_CHANGE_PATTERNS = (
    re.compile(r"^esta e a primeira analise(?: disponivel)?(?: para a companhia)?$"),
    re.compile(r"^esta e a primeira analise da companhia$"),
    re.compile(r"^nao ha(?: uma)? analise anterior(?: disponivel)?(?: para comparacao)?$"),
    re.compile(r"^sem analise anterior(?: disponivel)?(?: para comparacao)?$"),
    re.compile(r"^nao houve mudancas? (?:materiais|mensuraveis|relevantes)(?: desde a analise anterior)?$"),
    re.compile(r"^nao foram identificadas mudancas? (?:materiais|mensuraveis|relevantes)(?: nos fatos atuais)?$"),
    re.compile(r"^nenhuma mudanca (?:material|mensuravel|relevante) foi identificada(?: nos fatos atuais)?$"),
)


def allows_empty_change_evidence(text: str) -> bool:
    """Aceita lista vazia apenas para frases puramente metadadas ou sem mudança."""
    normalized = _normalize_text(text)
    return any(pattern.fullmatch(normalized) for pattern in _EMPTY_CHANGE_PATTERNS)


def normalize_evidence_key_hardened(
    key: Any,
    evidence_keys: set[str],
    facts: dict[str, Any],
) -> str | None:
    if not isinstance(key, str):
        return None
    if key in evidence_keys:
        return key

    reference_model = (facts.get("valuation") or {}).get("reference_model")
    if key == "graham":
        return "fair_price_reference" if reference_model == "Graham" and "fair_price_reference" in evidence_keys else None
    if key == "bazin":
        return "fair_price_reference" if reference_model == "Bazin" and "fair_price_reference" in evidence_keys else None

    aliases = {
        "reference_price": "fair_price_reference",
        "margin": "safety_margin",
        "comparacao_setorial": "sector_combined_percentile",
        "melhores_pares": "sector_combined_percentile",
        "posicao_qualidade": "sector_quality_percentile",
        "posicao_valuation": "sector_valuation_percentile",
    }
    normalized = aliases.get(key)
    return normalized if normalized in evidence_keys else None


def validate_claim_hardened(
    value: Any,
    field: str,
    evidence_keys: set[str],
    facts: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Campo {field} deve ser objeto")

    text = base.require_text(value.get("texto"), f"{field}.texto", 500)
    evidence = value.get("evidencias")
    if not isinstance(evidence, list):
        if field == "mudancas_desde_anterior" and allows_empty_change_evidence(text):
            return {"texto": text, "evidencias": []}
        raise ValueError(f"Campo {field}.evidencias deve ser lista não vazia")

    cleaned: list[str] = []
    for key in evidence:
        normalized = normalize_evidence_key_hardened(key, evidence_keys, facts)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)

    if not cleaned:
        if field == "mudancas_desde_anterior" and allows_empty_change_evidence(text):
            return {"texto": text, "evidencias": []}
        raise ValueError(f"Campo {field}.evidencias não contém chave válida")

    return {"texto": text, "evidencias": cleaned}


def validate_analysis_hardened(raw: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Resposta da IA deve ser objeto JSON")

    evidence_keys = set(facts.get("evidencias", {}))
    result = {
        "titulo": base.require_text(raw.get("titulo"), "titulo", 120),
        "resumo": base.require_text(raw.get("resumo"), "resumo", 900),
        "tese": base.require_text(raw.get("tese"), "tese", 900),
    }

    for list_field in ("pontos_fortes", "pontos_atencao"):
        values = raw.get(list_field)
        if not isinstance(values, list) or not 1 <= len(values) <= 6:
            raise ValueError(f"Campo {list_field} deve ter de 1 a 6 itens")
        result[list_field] = [
            validate_claim_hardened(item, f"{list_field}[{index}]", evidence_keys, facts)
            for index, item in enumerate(values)
        ]

    result["valuation"] = validate_claim_hardened(
        raw.get("valuation"), "valuation", evidence_keys, facts
    )
    result["mudancas_desde_anterior"] = validate_claim_hardened(
        raw.get("mudancas_desde_anterior"),
        "mudancas_desde_anterior",
        evidence_keys,
        facts,
    )

    monitor = raw.get("monitorar")
    if not isinstance(monitor, list) or not 1 <= len(monitor) <= 6:
        raise ValueError("Campo monitorar deve ter de 1 a 6 itens")
    result["monitorar"] = [
        base.require_text(item, f"monitorar[{index}]", 220)
        for index, item in enumerate(monitor)
    ]

    limitations = raw.get("limitacoes")
    if not isinstance(limitations, list):
        raise ValueError("Campo limitacoes deve ser lista")
    result["limitacoes"] = [
        base.require_text(item, f"limitacoes[{index}]", 260)
        for index, item in enumerate(limitations[:6])
    ]

    confidence = raw.get("confianca")
    if confidence not in {"alta", "media", "baixa"}:
        raise ValueError("Confiança deve ser alta, media ou baixa")
    result["confianca"] = confidence

    forbidden = ("compre", "venda imediatamente", "garantido", "vai subir", "vai cair")
    joined = json.dumps(result, ensure_ascii=False).lower()
    if any(term in joined for term in forbidden):
        raise ValueError("Resposta contém linguagem de recomendação ou certeza indevida")
    return result


def write_json_atomic(path: Path, value: Any) -> None:
    """Grava JSON no mesmo diretório e troca o arquivo somente após fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=1, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=base.DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    latest = load_json_hardened(base.LATEST_PATH)
    history = load_json_hardened(
        base.HISTORY_PATH, {"companies": {}, "data_coleta": "seed"}
    )
    previous = load_json_hardened(args.output, {"companies": {}})

    if args.validate_only:
        companies = previous.get("companies") if isinstance(previous, dict) else {}
        if not isinstance(companies, dict):
            raise SystemExit("Arquivo de análises não contém objeto companies")
        for ticker, item in companies.items():
            validate_analysis_hardened(item.get("analysis"), item.get("facts") or {})
            print(f"OK {ticker}")
        return

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY não configurada")
    model = os.environ.get("DEEPSEEK_MODEL", base.DEFAULT_MODEL).strip()
    if model not in base.ALLOWED_MODELS:
        raise SystemExit(f"DEEPSEEK_MODEL inválido: {model}. Use {sorted(base.ALLOWED_MODELS)}")
    thinking = os.environ.get("DEEPSEEK_THINKING", "enabled").strip().lower()
    if thinking not in {"enabled", "disabled"}:
        raise SystemExit("DEEPSEEK_THINKING deve ser enabled ou disabled")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    tickers = {ticker.strip().upper() for ticker in args.ticker if ticker.strip()} or None

    base.validate_analysis = validate_analysis_hardened
    output, errors = base.generate(
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
    write_json_atomic(args.output, output)
    print(f"Análises disponíveis: {output['total']}; novas: {output['geradas_nesta_execucao']}")

    attempted = output["geradas_nesta_execucao"] + len(errors)
    if errors and (attempted == 0 or len(errors) / attempted > 0.20):
        raise SystemExit(f"Muitas falhas na geração: {len(errors)}/{attempted}")


if __name__ == "__main__":
    main()
