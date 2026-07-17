"""Executa a coleta CVM com consulta resiliente ao cadastro da B3.

A listagem completa da B3 pode retornar ``results`` vazio quando solicitada com
uma página muito grande. Este wrapper consulta somente os prefixos dos tickers do
IBOV, em páginas pequenas, e aceita variações do formato de resposta.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Iterable

import cvm_history


def _extract_results(data: object) -> list[dict]:
    """Extrai registros das formas de resposta já observadas na API da B3."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("results", "content", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_results(nested)
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    return []


def _payloads(prefix: str) -> Iterable[str]:
    params = {
        "language": "pt-br",
        "pageNumber": 1,
        "pageSize": 20,
        "company": prefix,
    }
    # A API da B3 já aceitou tanto JSON quanto a representação Python do dict.
    # Testar os dois formatos reduz o acoplamento a uma implementação não
    # documentada do frontend.
    raw_candidates = (
        json.dumps(params, separators=(",", ":")),
        str(params),
    )
    for raw in raw_candidates:
        yield base64.b64encode(raw.encode("utf-8")).decode("ascii")


def fetch_b3_companies_by_ticker(session) -> list[dict]:
    prefixes = sorted({cvm_history.ticker_prefix(ticker) for ticker in cvm_history.load_tickers()})
    found: dict[str, dict] = {}
    failures: list[str] = []

    for prefix in prefixes:
        prefix_results: list[dict] = []
        last_error: Exception | None = None
        for payload in _payloads(prefix):
            try:
                response = cvm_history.request_with_retry(
                    session,
                    cvm_history.B3_URL.format(payload=payload),
                )
                prefix_results = _extract_results(response.json())
            except (ValueError, RuntimeError) as exc:
                last_error = exc
                continue
            if prefix_results:
                break

        exact = [
            item for item in prefix_results
            if str(item.get("issuingCompany") or "").strip().upper() == prefix
        ]
        candidates = exact or prefix_results
        for item in candidates:
            issuing = str(item.get("issuingCompany") or "").strip().upper()
            code = str(item.get("codeCVM") or item.get("codeCvm") or "").strip()
            if issuing and code and issuing not in found:
                found[issuing] = item

        if prefix not in found:
            failures.append(prefix)
            if last_error:
                print(f"AVISO B3 {prefix}: {last_error}")

    if not found:
        raise RuntimeError(
            "A B3 não retornou nenhuma companhia nas consultas individuais por ticker."
        )
    if failures:
        print(f"AVISO: {len(failures)} prefixos não encontrados na B3: {failures}")
    print(f"B3: {len(found)}/{len(prefixes)} prefixos encontrados por consulta individual")
    return list(found.values())


def main() -> None:
    cvm_history.fetch_b3_companies = fetch_b3_companies_by_ticker
    cvm_history.main()


if __name__ == "__main__":
    main()
