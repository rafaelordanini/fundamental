"""Wrapper resiliente para a coleta de notícias e leitura pelo DeepSeek V4.

Corrige três problemas operacionais do coletor original:

1. permite limitar toda a coleta a um ticker em execuções manuais;
2. tenta formatos compatíveis quando a API responde HTTP 400;
3. preserva contextos anteriores em uma execução filtrada.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

import news_context as base


_ORIGINAL_LOAD_JSON = base.load_json


def parse_json_content(content: str) -> dict[str, Any]:
    """Aceita JSON puro ou cercado por bloco Markdown."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("DeepSeek não retornou um objeto JSON")
    return value


def response_error(response: requests.Response) -> str:
    body = (response.text or "").strip().replace("\n", " ")
    return f"DeepSeek HTTP {response.status_code}: {body[:1000] or 'sem corpo de resposta'}"


def post_variant(
    session: requests.Session,
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> requests.Response:
    response = session.post(url, headers=headers, json=payload, timeout=(20, 180))
    if response.status_code >= 400:
        raise RuntimeError(response_error(response))
    return response


def resilient_read_with_flash(
    session: requests.Session,
    article: dict[str, Any],
    ticker: str,
    company: str,
    api_key: str,
    model: str,
    base_url: str,
) -> dict[str, Any]:
    """Lê uma matéria com fallbacks de formato, sempre mantendo o modelo V4."""
    messages = [
        {"role": "system", "content": base.READER_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "ticker": ticker,
                    "empresa": company,
                    "titulo": article.get("title"),
                    "descricao": article.get("description"),
                    "data": article.get("published"),
                    "texto": article.get("body"),
                },
                ensure_ascii=False,
            ),
        },
    ]
    common = {
        "model": model,
        "messages": messages,
        "max_tokens": 900,
        "stream": False,
    }
    # A primeira variante segue a documentação atual. As demais cobrem contas ou
    # gateways que ainda rejeitam um dos campos opcionais com HTTP 400.
    variants = [
        {**common, "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}},
        {**common, "response_format": {"type": "json_object"}},
        common,
    ]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = base_url.rstrip("/") + "/chat/completions"
    errors: list[str] = []

    for index, payload in enumerate(variants, start=1):
        try:
            response = post_variant(session, url=url, headers=headers, payload=payload)
            content = response.json()["choices"][0]["message"]["content"]
            raw = parse_json_content(content)
            if not isinstance(raw.get("relevante"), bool):
                raise ValueError("Resposta sem campo booleano 'relevante'")
            raw["resumo"] = base.clean_text(raw.get("resumo"), 500)
            for key in ("drivers", "riscos", "metricas_afetadas"):
                raw[key] = [base.clean_text(item, 160) for item in raw.get(key, []) if base.clean_text(item)][:6]
            return raw
        except (requests.RequestException, RuntimeError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            errors.append(f"variante {index}: {exc}")
            if index < len(variants):
                time.sleep(2)

    raise RuntimeError("; ".join(errors))


def filtered_loader(tickers: set[str] | None):
    def load_json(path: Path, default: Any) -> Any:
        value = _ORIGINAL_LOAD_JSON(path, default)
        if tickers and path == base.LATEST_PATH and isinstance(value, dict):
            rows = value.get("rows") if isinstance(value.get("rows"), list) else []
            return {**value, "rows": [row for row in rows if str(row.get("papel") or "").upper() in tickers]}
        return value
    return load_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--max-articles-per-ticker", type=int, default=3)
    parser.add_argument("--max-new-articles", type=int, default=20)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--ticker", action="append", default=[])
    args = parser.parse_args()

    tickers = {item.strip().upper() for item in args.ticker if item.strip()} or None
    previous = _ORIGINAL_LOAD_JSON(base.OUTPUT_PATH, {"companies": {}})

    base.load_json = filtered_loader(tickers)
    base.read_with_flash = resilient_read_with_flash
    output = base.generate(
        metadata_only=args.metadata_only,
        max_articles_per_ticker=max(1, min(args.max_articles_per_ticker, 6)),
        max_new_articles=max(0, args.max_new_articles),
        days=max(1, args.days),
    )

    if tickers:
        merged = dict(previous.get("companies") or {})
        merged.update(output.get("companies") or {})
        output["companies"] = merged
        output["total"] = len(merged)
        output["ticker_filter"] = sorted(tickers)

    base.OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=1, allow_nan=False),
        encoding="utf-8",
    )
    print(
        f"Contexto de notícias: {output['total']} empresas; "
        f"novas leituras Flash: {output['new_reads']}"
    )


if __name__ == "__main__":
    main()
