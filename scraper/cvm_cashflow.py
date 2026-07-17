"""Extensões do coletor CVM para fluxo de caixa e FCD.

A CVM publica DFC pelo método direto (DFC_MD) e indireto (DFC_MI). Este módulo
adiciona ao histórico os totais padronizados 6.01 (atividades operacionais) e
6.02 (atividades de investimento). O fluxo de caixa livre usado no projeto é
uma aproximação conservadora: FCL = caixa operacional + caixa de investimentos.
Isso inclui aquisições e outros investimentos, não apenas CAPEX.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from typing import Iterable

import cvm_history

OPERATING_CASH_FLOW = "6.01"
INVESTING_CASH_FLOW = "6.02"

_ORIGINAL_COMPUTE_SUMMARY = cvm_history.compute_history_summary
_ORIGINAL_BUILD_OUTPUT = cvm_history.build_output


def parse_cvm_number(value: str) -> float | None:
    """Converte números da CVM sem destruir o separador decimal.

    Os CSVs atuais normalmente usam ponto decimal, enquanto alguns arquivos e
    testes podem trazer vírgula decimal. A implementação anterior removia todo
    ponto e inflava os valores históricos em várias ordens de grandeza.
    """
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text or text in {"-", "--"}:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")

    try:
        return float(text)
    except ValueError:
        return None


def collect_statements_with_cashflow(
    session,
    years: Iterable[int],
    company_codes: set[str],
) -> dict[str, dict[date, dict]]:
    records: dict[tuple[str, date, str, date | None], cvm_history.StatementValue] = {}
    statements = {
        "DRE": {
            cvm_history.ACCOUNT_CODES["revenue"],
            cvm_history.ACCOUNT_CODES["ebit"],
            cvm_history.ACCOUNT_CODES["net_income"],
        },
        "BPA": {
            cvm_history.ACCOUNT_CODES["assets"],
            cvm_history.ACCOUNT_CODES["cash"],
            cvm_history.ACCOUNT_CODES["current_assets"],
        },
        "BPP": {
            cvm_history.ACCOUNT_CODES["current_liabilities"],
            cvm_history.ACCOUNT_CODES["equity"],
            cvm_history.ACCOUNT_CODES["short_debt"],
            cvm_history.ACCOUNT_CODES["long_debt"],
        },
        "DFC_MI": {OPERATING_CASH_FLOW, INVESTING_CASH_FLOW},
        "DFC_MD": {OPERATING_CASH_FLOW, INVESTING_CASH_FLOW},
    }

    for year in years:
        for kind in ("ITR", "DFP"):
            path = cvm_history.download_zip(session, kind, year)
            try:
                for statement, accounts in statements.items():
                    for item in cvm_history.iter_statement_rows(
                        path, kind, year, statement, accounts, company_codes
                    ):
                        key = (
                            item.company_code,
                            item.reference_date,
                            item.account,
                            item.start_date,
                        )
                        old = records.get(key)
                        source_rank = 1 if item.source == "DFP" else 0
                        old_rank = 1 if old and old.source == "DFP" else 0
                        if old is None or (item.version, source_rank) >= (
                            old.version,
                            old_rank,
                        ):
                            records[key] = item
            finally:
                path.unlink(missing_ok=True)

    grouped: dict[str, dict[date, dict]] = defaultdict(lambda: defaultdict(dict))
    selected: dict[tuple[str, date, str], cvm_history.StatementValue] = {}
    for item in records.values():
        key = (item.company_code, item.reference_date, item.account)
        old = selected.get(key)
        item_start = item.start_date or item.reference_date
        old_start = (old.start_date or old.reference_date) if old else item.reference_date
        if old is None or item_start < old_start or (
            item_start == old_start and item.version >= old.version
        ):
            selected[key] = item

    reverse_accounts = {
        value: key for key, value in cvm_history.ACCOUNT_CODES.items()
    }
    dre_codes = {
        cvm_history.ACCOUNT_CODES["revenue"],
        cvm_history.ACCOUNT_CODES["ebit"],
        cvm_history.ACCOUNT_CODES["net_income"],
    }
    cashflow_codes = {OPERATING_CASH_FLOW, INVESTING_CASH_FLOW}

    for item in selected.values():
        period = grouped[item.company_code][item.reference_date]
        metric = reverse_accounts.get(item.account)
        if not metric:
            continue
        period[metric] = item.value_million
        period["company_name"] = item.company_name
        period["cnpj"] = item.cnpj
        if item.account in dre_codes:
            period["start_date"] = item.start_date.isoformat() if item.start_date else None
        if item.account in cashflow_codes:
            period["cashflow_start_date"] = (
                item.start_date.isoformat() if item.start_date else None
            )
    return grouped


def standalone_quarters_with_cashflow(periods: dict[date, dict]) -> list[dict]:
    result: list[dict] = []
    previous_cumulative: dict[tuple[int, str], float] = {}
    flow_fields = {
        "revenue": "start_date",
        "ebit": "start_date",
        "net_income": "start_date",
        "operating_cash_flow": "cashflow_start_date",
        "investing_cash_flow": "cashflow_start_date",
    }

    for reference in sorted(periods):
        period = periods[reference]
        quarter = {"date": reference.isoformat()}
        for metric, start_field in flow_fields.items():
            cumulative = period.get(metric)
            if cumulative is None:
                quarter[metric] = None
                continue
            start = cvm_history.parse_date(period.get(start_field) or "")
            year_key = start.year if start else reference.year
            key = (year_key, metric)
            prior = previous_cumulative.get(key)
            standalone = cumulative - prior if prior is not None else cumulative
            previous_cumulative[key] = cumulative
            quarter[metric] = round(standalone, 3)

        for metric in (
            "assets",
            "cash",
            "current_assets",
            "current_liabilities",
            "equity",
        ):
            value = period.get(metric)
            quarter[metric] = round(value, 3) if value is not None else None

        short_debt = period.get("short_debt")
        long_debt = period.get("long_debt")
        gross_debt = (
            None
            if short_debt is None and long_debt is None
            else (short_debt or 0) + (long_debt or 0)
        )
        cash = period.get("cash")
        quarter["gross_debt"] = (
            round(gross_debt, 3) if gross_debt is not None else None
        )
        quarter["net_debt"] = (
            round(gross_debt - cash, 3)
            if gross_debt is not None and cash is not None
            else None
        )
        quarter["net_margin"] = cvm_history.safe_div(
            quarter.get("net_income"), quarter.get("revenue")
        )
        operating = quarter.get("operating_cash_flow")
        investing = quarter.get("investing_cash_flow")
        quarter["free_cash_flow"] = (
            round(operating + investing, 3)
            if operating is not None and investing is not None
            else None
        )
        result.append(quarter)
    return result[-20:]


def yearly_totals_with_cashflow(quarters: list[dict]) -> list[dict]:
    by_year: dict[int, list[dict]] = defaultdict(list)
    for quarter in quarters:
        by_year[int(quarter["date"][:4])].append(quarter)

    result: list[dict] = []
    for year, items in sorted(by_year.items()):
        if len(items) < 4:
            continue
        record: dict = {"year": year}
        for metric in (
            "revenue",
            "net_income",
            "operating_cash_flow",
            "investing_cash_flow",
            "free_cash_flow",
        ):
            values = [item[metric] for item in items if item.get(metric) is not None]
            record[metric] = sum(values) if len(values) >= 3 else None
        record["net_margin"] = cvm_history.safe_div(
            record.get("net_income"), record.get("revenue")
        )
        result.append(record)
    return result


def compute_history_summary_with_cashflow(ticker: str, quarters: list[dict]) -> dict:
    summary = _ORIGINAL_COMPUTE_SUMMARY(ticker, quarters)
    annual = yearly_totals_with_cashflow(quarters)
    annual_cash_flow = [
        {
            "year": item["year"],
            "operating_cash_flow": item.get("operating_cash_flow"),
            "investing_cash_flow": item.get("investing_cash_flow"),
            "free_cash_flow": item.get("free_cash_flow"),
        }
        for item in annual
        if item.get("free_cash_flow") is not None
    ]
    annual_fcfs = [item["free_cash_flow"] for item in annual_cash_flow]
    positive_ratio = (
        sum(1 for value in annual_fcfs if value > 0) / len(annual_fcfs)
        if annual_fcfs
        else None
    )

    latest_four = quarters[-4:]
    ttm_fcfs = [
        item.get("free_cash_flow")
        for item in latest_four
        if item.get("free_cash_flow") is not None
    ]
    ttm_fcf = sum(ttm_fcfs) if len(ttm_fcfs) >= 3 else None
    ttm_profits = [
        item.get("net_income")
        for item in latest_four
        if item.get("net_income") is not None
    ]
    ttm_profit = sum(ttm_profits) if len(ttm_profits) >= 3 else None

    recent_annual = annual_fcfs[-3:]
    normalized_fcf = (
        statistics.median(recent_annual)
        if len(recent_annual) >= 2
        else ttm_fcf
    )
    cashflow_quarters = sum(
        1 for item in quarters if item.get("free_cash_flow") is not None
    )

    if ticker not in cvm_history.FINANCEIRAS and positive_ratio is not None:
        criterion = cvm_history.criterion(
            "FCL anual positivo",
            positive_ratio,
            lambda value: value >= 0.80,
            lambda value: value >= 0.50,
            f"{positive_ratio:.0%}",
        )
        if criterion:
            summary["breakdown"].append(criterion)
            breakdown = summary["breakdown"]
            summary["history_score"] = round(
                sum(item["pts"] for item in breakdown) / (2 * len(breakdown)) * 100
            )

    summary.update(
        {
            "cashflow_quarters_count": cashflow_quarters,
            "free_cash_flow_years_count": len(annual_fcfs),
            "positive_free_cash_flow_years_ratio": positive_ratio,
            "free_cash_flow_ttm_million": ttm_fcf,
            "normalized_free_cash_flow_million": normalized_fcf,
            "ttm_net_income_million": ttm_profit,
            "annual_cash_flow": annual_cash_flow,
            "free_cash_flow_method": "Caixa operacional + caixa de investimentos",
        }
    )
    return summary


def build_output_with_cashflow(*args, **kwargs) -> dict:
    output = _ORIGINAL_BUILD_OUTPUT(*args, **kwargs)
    output["fonte"] = "CVM ITR/DFP consolidados (inclui DFC) + cadastro B3"
    output["cash_flow_method"] = "FCL aproximado = 6.01 + 6.02"
    return output


def install() -> None:
    """Instala as extensões no módulo original antes de executar ``main``."""
    cvm_history.ACCOUNT_CODES.update(
        {
            "operating_cash_flow": OPERATING_CASH_FLOW,
            "investing_cash_flow": INVESTING_CASH_FLOW,
        }
    )
    cvm_history.parse_number = parse_cvm_number
    cvm_history.collect_statements = collect_statements_with_cashflow
    cvm_history.standalone_quarters = standalone_quarters_with_cashflow
    cvm_history.yearly_totals = yearly_totals_with_cashflow
    cvm_history.compute_history_summary = compute_history_summary_with_cashflow
    cvm_history.build_output = build_output_with_cashflow
