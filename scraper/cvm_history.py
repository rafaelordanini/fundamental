"""Coleta histórico trimestral de companhias do IBOV nos dados abertos da CVM.

O script cruza o prefixo do ticker com o cadastro de companhias listadas da B3,
baixa ITR/DFP consolidados dos últimos anos, converte demonstrações acumuladas
em trimestres isolados e grava ``data/history.json``.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import re
import statistics
import tempfile
import time
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import requests

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
B3_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/{payload}"
CVM_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{kind}/DADOS/{kind_lower}_cia_aberta_{year}.zip"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}
FINANCEIRAS = {
    "BBAS3", "BBDC4", "BBSE3", "BPAC11", "CXSE3", "ITSA4", "ITUB4", "PSSA3", "SANB11",
}
ACCOUNT_CODES = {
    "revenue": "3.01",
    "ebit": "3.05",
    "net_income": "3.11",
    "assets": "1",
    "cash": "1.01.01",
    "current_assets": "1.01",
    "current_liabilities": "2.01",
    "equity": "2.03",
    "short_debt": "2.01.04",
    "long_debt": "2.02.01",
}


@dataclass(frozen=True)
class StatementValue:
    company_code: str
    company_name: str
    cnpj: str
    reference_date: date
    start_date: date | None
    account: str
    value_million: float
    version: int
    source: str


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def ticker_prefix(ticker: str) -> str:
    match = re.match(r"([A-Z]{4})", ticker.upper())
    return match.group(1) if match else ticker.upper()[:4]


def parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_number(value: str) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(".", "").replace(",", ".")
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_millions(value: float, scale: str) -> float:
    scale_norm = normalize(scale)
    if scale_norm.startswith("mil"):
        return value / 1_000
    return value / 1_000_000


def request_with_retry(session: requests.Session, url: str, *, stream: bool = False) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = session.get(url, headers=HEADERS, timeout=(20, 120), stream=stream)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(attempt * 10)
    raise RuntimeError(f"Falha ao acessar {url}: {last_error}")


def load_tickers() -> list[str]:
    lines = (BASE / "ibov.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip().upper() for line in lines if line.strip() and not line.startswith("#")]


def load_overrides() -> dict[str, dict[str, str]]:
    path = BASE / "cvm_overrides.csv"
    if not path.exists():
        return {}
    result: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ticker = row.get("ticker", "").strip().upper()
            if ticker:
                result[ticker] = {
                    "code_cvm": row.get("code_cvm", "").strip(),
                    "cnpj": re.sub(r"\D", "", row.get("cnpj", "")),
                    "company_name": row.get("company_name", "").strip(),
                }
    return result


def fetch_b3_companies(session: requests.Session) -> list[dict]:
    params = {"language": "pt-br", "pageNumber": 1, "pageSize": 2000, "company": ""}
    payload = base64.b64encode(json.dumps(params, separators=(",", ":")).encode()).decode()
    response = request_with_retry(session, B3_URL.format(payload=payload))
    data = response.json()
    results = data.get("results") or []
    if not results:
        raise RuntimeError("A B3 não retornou o cadastro de companhias listadas.")
    return results


def map_tickers_to_cvm(tickers: Iterable[str], companies: Iterable[dict], overrides: dict[str, dict[str, str]]) -> tuple[dict[str, dict], list[str]]:
    by_prefix: dict[str, dict] = {}
    for company in companies:
        prefix = str(company.get("issuingCompany") or "").strip().upper()
        code = str(company.get("codeCVM") or company.get("codeCvm") or "").strip()
        if prefix and code and prefix not in by_prefix:
            by_prefix[prefix] = {
                "code_cvm": str(int(float(code))) if code.replace(".", "", 1).isdigit() else code,
                "cnpj": re.sub(r"\D", "", str(company.get("cnpj") or "")),
                "company_name": str(company.get("companyName") or company.get("tradingName") or "").strip(),
            }

    mapped: dict[str, dict] = {}
    missing: list[str] = []
    for ticker in tickers:
        item = overrides.get(ticker) or by_prefix.get(ticker_prefix(ticker))
        if item and item.get("code_cvm"):
            mapped[ticker] = item
        else:
            missing.append(ticker)
    return mapped, missing


def download_zip(session: requests.Session, kind: str, year: int) -> Path:
    url = CVM_URL.format(kind=kind.upper(), kind_lower=kind.lower(), year=year)
    response = request_with_retry(session, url, stream=True)
    temp = tempfile.NamedTemporaryFile(prefix=f"{kind.lower()}_{year}_", suffix=".zip", delete=False)
    with temp:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                temp.write(chunk)
    return Path(temp.name)


def choose_member(archive: zipfile.ZipFile, kind: str, statement: str, year: int) -> str | None:
    expected = f"{kind.lower()}_cia_aberta_{statement}_con_{year}.csv".lower()
    for name in archive.namelist():
        if name.lower().endswith(expected):
            return name
    return None


def iter_statement_rows(zip_path: Path, kind: str, year: int, statement: str, account_codes: set[str], company_codes: set[str]) -> Iterable[StatementValue]:
    with zipfile.ZipFile(zip_path) as archive:
        member = choose_member(archive, kind, statement, year)
        if not member:
            return
        with archive.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            reader = csv.DictReader(text, delimiter=";")
            for row in reader:
                code = str(row.get("CD_CVM") or "").strip()
                try:
                    code = str(int(float(code)))
                except ValueError:
                    pass
                if code not in company_codes:
                    continue
                if normalize(row.get("ORDEM_EXERC", "")) not in {"ultimo", ""}:
                    continue
                account = str(row.get("CD_CONTA") or "").strip()
                if account not in account_codes:
                    continue
                value = parse_number(row.get("VL_CONTA", ""))
                reference = parse_date(row.get("DT_REFER", "") or row.get("DT_FIM_EXERC", ""))
                if value is None or reference is None:
                    continue
                start = parse_date(row.get("DT_INI_EXERC", ""))
                try:
                    version = int(float(row.get("VERSAO") or 0))
                except ValueError:
                    version = 0
                yield StatementValue(
                    company_code=code,
                    company_name=str(row.get("DENOM_CIA") or "").strip(),
                    cnpj=re.sub(r"\D", "", str(row.get("CNPJ_CIA") or "")),
                    reference_date=reference,
                    start_date=start,
                    account=account,
                    value_million=to_millions(value, row.get("ESCALA_MOEDA", "")),
                    version=version,
                    source=kind.upper(),
                )


def collect_statements(session: requests.Session, years: Iterable[int], company_codes: set[str]) -> dict[str, dict[date, dict]]:
    records: dict[tuple[str, date, str, date | None], StatementValue] = {}
    statements = {
        "DRE": {ACCOUNT_CODES["revenue"], ACCOUNT_CODES["ebit"], ACCOUNT_CODES["net_income"]},
        "BPA": {ACCOUNT_CODES["assets"], ACCOUNT_CODES["cash"], ACCOUNT_CODES["current_assets"]},
        "BPP": {ACCOUNT_CODES["current_liabilities"], ACCOUNT_CODES["equity"], ACCOUNT_CODES["short_debt"], ACCOUNT_CODES["long_debt"]},
    }
    for year in years:
        for kind in ("ITR", "DFP"):
            path = download_zip(session, kind, year)
            try:
                for statement, accounts in statements.items():
                    for item in iter_statement_rows(path, kind, year, statement, accounts, company_codes):
                        key = (item.company_code, item.reference_date, item.account, item.start_date)
                        old = records.get(key)
                        source_rank = 1 if item.source == "DFP" else 0
                        old_rank = 1 if old and old.source == "DFP" else 0
                        if old is None or (item.version, source_rank) >= (old.version, old_rank):
                            records[key] = item
            finally:
                path.unlink(missing_ok=True)

    grouped: dict[str, dict[date, dict]] = defaultdict(lambda: defaultdict(dict))
    selected: dict[tuple[str, date, str], StatementValue] = {}
    for item in records.values():
        key = (item.company_code, item.reference_date, item.account)
        old = selected.get(key)
        item_start = item.start_date or item.reference_date
        old_start = (old.start_date or old.reference_date) if old else item.reference_date
        if old is None or item_start < old_start or (item_start == old_start and item.version >= old.version):
            selected[key] = item

    reverse_accounts = {value: key for key, value in ACCOUNT_CODES.items()}
    for item in selected.values():
        period = grouped[item.company_code][item.reference_date]
        period[reverse_accounts[item.account]] = item.value_million
        period["company_name"] = item.company_name
        period["cnpj"] = item.cnpj
        if item.account in {ACCOUNT_CODES["revenue"], ACCOUNT_CODES["ebit"], ACCOUNT_CODES["net_income"]}:
            period["start_date"] = item.start_date.isoformat() if item.start_date else None
    return grouped


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def cagr(first: float | None, last: float | None, years: float) -> float | None:
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def standalone_quarters(periods: dict[date, dict]) -> list[dict]:
    result: list[dict] = []
    previous_cumulative: dict[tuple[int, str], float] = {}
    for reference in sorted(periods):
        period = periods[reference]
        quarter = {"date": reference.isoformat()}
        start = parse_date(period.get("start_date") or "")
        year_key = start.year if start else reference.year
        for metric in ("revenue", "ebit", "net_income"):
            cumulative = period.get(metric)
            if cumulative is None:
                quarter[metric] = None
                continue
            key = (year_key, metric)
            prior = previous_cumulative.get(key)
            standalone = cumulative - prior if prior is not None else cumulative
            previous_cumulative[key] = cumulative
            quarter[metric] = round(standalone, 3)
        for metric in ("assets", "cash", "current_assets", "current_liabilities", "equity"):
            value = period.get(metric)
            quarter[metric] = round(value, 3) if value is not None else None
        short_debt = period.get("short_debt")
        long_debt = period.get("long_debt")
        gross_debt = None if short_debt is None and long_debt is None else (short_debt or 0) + (long_debt or 0)
        cash = period.get("cash")
        quarter["gross_debt"] = round(gross_debt, 3) if gross_debt is not None else None
        quarter["net_debt"] = round(gross_debt - cash, 3) if gross_debt is not None and cash is not None else None
        quarter["net_margin"] = safe_div(quarter.get("net_income"), quarter.get("revenue"))
        result.append(quarter)
    return result[-20:]


def yearly_totals(quarters: list[dict]) -> list[dict]:
    by_year: dict[int, list[dict]] = defaultdict(list)
    for quarter in quarters:
        by_year[int(quarter["date"][:4])].append(quarter)
    result = []
    for year, items in sorted(by_year.items()):
        if len(items) < 4:
            continue
        revenue_values = [q["revenue"] for q in items if q.get("revenue") is not None]
        profit_values = [q["net_income"] for q in items if q.get("net_income") is not None]
        revenue = sum(revenue_values) if revenue_values else None
        profit = sum(profit_values) if profit_values else None
        result.append({"year": year, "revenue": revenue, "net_income": profit, "net_margin": safe_div(profit, revenue)})
    return result


def criterion(label: str, value: float | int | None, good, ok, formatted: str | None = None) -> dict | None:
    if value is None:
        return None
    points = 2 if good(value) else 1 if ok(value) else 0
    return {"label": label, "pts": points, "value": formatted}


def compute_history_summary(ticker: str, quarters: list[dict]) -> dict:
    annual = yearly_totals(quarters)
    profits = [q.get("net_income") for q in quarters if q.get("net_income") is not None]
    profitable_ratio = sum(1 for value in profits if value > 0) / len(profits) if profits else None
    revenue_cagr = None
    if len(annual) >= 2:
        span = annual[-1]["year"] - annual[0]["year"]
        revenue_cagr = cagr(annual[0].get("revenue"), annual[-1].get("revenue"), span)
    positive_revenue_years = None
    if len(annual) >= 2:
        comparisons = [annual[i]["revenue"] > annual[i - 1]["revenue"] for i in range(1, len(annual)) if annual[i]["revenue"] is not None and annual[i - 1]["revenue"] is not None]
        positive_revenue_years = sum(comparisons) / len(comparisons) if comparisons else None
    margins = [item["net_margin"] for item in annual if item.get("net_margin") is not None]
    median_margin = statistics.median(margins) if margins else None
    margin_volatility = statistics.pstdev(margins) if len(margins) >= 2 else None

    latest_four = quarters[-4:]
    ttm_profit_values = [q.get("net_income") for q in latest_four if q.get("net_income") is not None]
    ttm_profit = sum(ttm_profit_values) if len(ttm_profit_values) >= 3 else None
    latest_equity = next((q.get("equity") for q in reversed(quarters) if q.get("equity") is not None), None)
    ttm_start_equity = next((q.get("equity") for q in reversed(quarters[:-4]) if q.get("equity") is not None), None) if len(quarters) > 4 else None
    initial_equity = next((q.get("equity") for q in quarters if q.get("equity") is not None), None)
    average_equity = (latest_equity + ttm_start_equity) / 2 if latest_equity is not None and ttm_start_equity is not None else latest_equity
    roe_ttm = safe_div(ttm_profit, average_equity)

    latest_debt = next((q.get("net_debt") for q in reversed(quarters) if q.get("net_debt") is not None), None)
    first_debt = next((q.get("net_debt") for q in quarters if q.get("net_debt") is not None), None)
    debt_to_equity = safe_div(latest_debt, latest_equity)
    debt_trend = safe_div(latest_debt - first_debt, abs(first_debt)) if first_debt not in (None, 0) and latest_debt is not None else None

    breakdown = [
        criterion("Cobertura histórica", len(quarters), lambda v: v >= 16, lambda v: v >= 8, f"{len(quarters)} tri"),
        criterion("Lucros trimestrais positivos", profitable_ratio, lambda v: v >= 0.85, lambda v: v >= 0.65, f"{profitable_ratio:.0%}" if profitable_ratio is not None else None),
        criterion("CAGR da receita", revenue_cagr, lambda v: v >= 0.08, lambda v: v >= 0, f"{revenue_cagr:.1%}" if revenue_cagr is not None else None),
        criterion("Anos com receita crescente", positive_revenue_years, lambda v: v >= 0.75, lambda v: v >= 0.50, f"{positive_revenue_years:.0%}" if positive_revenue_years is not None else None),
        criterion("Estabilidade da margem", margin_volatility, lambda v: v <= 0.04, lambda v: v <= 0.10, f"σ {margin_volatility:.1%}" if margin_volatility is not None else None),
        criterion("ROE TTM histórico", roe_ttm, lambda v: v >= 0.15, lambda v: v >= 0.08, f"{roe_ttm:.1%}" if roe_ttm is not None else None),
    ]
    if ticker not in FINANCEIRAS:
        breakdown.append(criterion("Tendência da dívida líquida", debt_trend, lambda v: v <= -0.10, lambda v: v <= 0.10, f"{debt_trend:+.1%}" if debt_trend is not None else None))
    breakdown = [item for item in breakdown if item is not None]
    score = round(sum(item["pts"] for item in breakdown) / (2 * len(breakdown)) * 100) if breakdown else None

    vetos = []
    if latest_equity is not None and latest_equity <= 0:
        vetos.append("Patrimônio líquido histórico negativo")
    if len(profits) >= 8 and profitable_ratio is not None and profitable_ratio < 0.50:
        vetos.append("Prejuízo recorrente em mais da metade dos trimestres")

    return {
        "quarters_count": len(quarters), "years_count": len(annual),
        "profitable_quarters_ratio": profitable_ratio, "revenue_cagr": revenue_cagr,
        "positive_revenue_years_ratio": positive_revenue_years, "median_net_margin": median_margin,
        "margin_volatility": margin_volatility, "roe_ttm": roe_ttm,
        "net_debt_to_equity": debt_to_equity, "net_debt_trend": debt_trend,
        "latest_equity_million": latest_equity, "history_score": score,
        "breakdown": breakdown, "vetos": vetos,
    }


def build_output(tickers: list[str], mapping: dict[str, dict], grouped: dict[str, dict[date, dict]], missing_mapping: list[str], years: list[int]) -> dict:
    companies: dict[str, dict] = {}
    for ticker in tickers:
        registration = mapping.get(ticker)
        if not registration:
            continue
        code = registration["code_cvm"]
        quarters = standalone_quarters(grouped.get(code, {}))
        if not quarters:
            continue
        latest_period = grouped[code][max(grouped[code])]
        companies[ticker] = {
            "code_cvm": code,
            "cnpj": registration.get("cnpj") or latest_period.get("cnpj"),
            "company_name": registration.get("company_name") or latest_period.get("company_name"),
            "quarters": quarters,
            "summary": compute_history_summary(ticker, quarters),
        }
    return {
        "data_coleta": date.today().isoformat(), "fonte": "CVM ITR/DFP consolidados + cadastro B3",
        "years": years, "total": len(companies), "missing_mapping": missing_mapping,
        "missing_history": sorted(set(tickers) - set(companies) - set(missing_mapping)), "companies": companies,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=6, help="Quantidade de anos-calendário, incluindo o atual")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "history.json")
    args = parser.parse_args()
    current_year = date.today().year
    years = list(range(current_year - args.years + 1, current_year + 1))
    tickers = load_tickers()

    with requests.Session() as session:
        companies = fetch_b3_companies(session)
        mapping, missing = map_tickers_to_cvm(tickers, companies, load_overrides())
        if len(mapping) < len(tickers) * 0.75:
            raise SystemExit(f"ERRO: somente {len(mapping)}/{len(tickers)} tickers foram mapeados para a CVM.")
        grouped = collect_statements(session, years, {item["code_cvm"] for item in mapping.values()})

    output = build_output(tickers, mapping, grouped, missing, years)
    if output["total"] < len(tickers) * 0.65:
        raise SystemExit(f"ERRO: histórico obtido para somente {output['total']}/{len(tickers)} tickers.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    print(f"OK: histórico de {output['total']} empresas gravado em {args.output}")
    if output["missing_mapping"]:
        print("Sem mapeamento B3/CVM:", output["missing_mapping"])
    if output["missing_history"]:
        print("Sem demonstrações consolidadas:", output["missing_history"])


if __name__ == "__main__":
    main()
