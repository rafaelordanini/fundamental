"""
Snapshot diário do Fundamentus para os papéis do IBOV.
Lê scraper/ibov.txt e scraper/segmentos.csv, raspa resultado.php
e grava data/latest.json na raiz do repositório.
"""
import csv
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
URL = "https://www.fundamentus.com.br/resultado.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

# cabeçalho totalmente normalizado (só letras/números) -> (chave JSON, é percentual?)
CAMPOS = {
    "cotacao": ("cotacao", False),
    "pl": ("pl", False),
    "pvp": ("pvp", False),
    "divyield": ("div_yield", True),
    "evebit": ("ev_ebit", False),
    "evebitda": ("ev_ebitda", False),
    "roe": ("roe", True),
    "roic": ("roic", True),
    "mrgliq": ("mrg_liq", True),
    "liqcorr": ("liq_corr", False),
    "divbrutpatrim": ("div_brut_pat", False),
    "crescrec5a": ("cresc_rec_5a", True),
}

# Instituições financeiras: EV/EBITDA, liq. corrente etc. não se aplicam.
FINANCEIRAS = {
    "BBAS3", "BBDC4", "BBSE3", "BPAC11", "CXSE3",
    "ITSA4", "ITUB4", "PSSA3", "SANB11",
}
NULOS_FINANCEIRAS = {
    "ev_ebit", "ev_ebitda", "mrg_liq", "liq_corr", "div_brut_pat", "roic",
}


def normaliza(texto: str) -> str:
    """Remove acentos e QUALQUER caractere que não seja letra ou número.
    'Dív.Brut/ Patrim.' -> 'divbrutpatrim'. Imune a espaços extras,
    quebras de linha, pontos e barras."""
    s = unicodedata.normalize("NFKD", texto)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_num(txt: str, pct: bool):
    txt = txt.strip()
    if not txt or txt in {"-", "--"}:
        return None
    txt = txt.replace("%", "").replace(".", "").replace(",", ".")
    try:
        v = float(txt)
    except ValueError:
        return None
    return v / 100 if pct else v


def carrega_ibov() -> list[str]:
    linhas = (BASE / "ibov.txt").read_text(encoding="utf-8").splitlines()
    return [l.strip().upper() for l in linhas if l.strip() and not l.startswith("#")]


def carrega_segmentos() -> dict[str, str]:
    seg = {}
    with open(BASE / "segmentos.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seg[row["ticker"].strip().upper()] = row["segmento"].strip().upper()
    return seg


def main() -> None:
    tickers = set(carrega_ibov())
    segmentos = carrega_segmentos()

    resp = requests.get(URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tabela = soup.find("table", id="resultado") or soup.find("table")
    if tabela is None:
        sys.exit("ERRO: tabela de resultados não encontrada — layout mudou?")

    ths = tabela.find("thead").find_all("th")
    cabecalhos_norm = [normaliza(th.get_text()) for th in ths]

    indices = {}
    for i, h in enumerate(cabecalhos_norm):
        if h in CAMPOS:
            indices[i] = CAMPOS[h]

    esperadas = {k for k, _ in CAMPOS.values()}
    obtidas = {k for k, _ in indices.values()}
    faltando = esperadas - obtidas
    if faltando:
        print("Cabeçalhos originais encontrados no site:")
        for th in ths:
            print(f"  {th.get_text(strip=True)!r} -> {normaliza(th.get_text())!r}")
        sys.exit(f"ERRO: colunas ausentes no Fundamentus: {faltando}")

    rows = []
    for tr in tabela.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        papel = tds[0].get_text(strip=True).upper()
        if papel not in tickers:
            continue
        row = {"papel": papel, "segmento": segmentos.get(papel)}
        for i, (chave, pct) in indices.items():
            row[chave] = parse_num(tds[i].get_text(), pct)
        if papel in FINANCEIRAS:
            for chave in NULOS_FINANCEIRAS:
                row[chave] = None
        rows.append(row)

    encontrados = {r["papel"] for r in rows}
    ausentes = sorted(tickers - encontrados)
    if ausentes:
        print(f"AVISO: {len(ausentes)} tickers não encontrados: {ausentes}")
    if len(rows) < len(tickers) * 0.8:
        sys.exit("ERRO: menos de 80% dos tickers coletados — abortando para não gravar snapshot ruim.")

    rows.sort(key=lambda r: r["papel"])
    out = {
        "data_coleta": date.today().isoformat(),
        "fonte": "fundamentus.com.br",
        "total": len(rows),
        "ausentes": ausentes,
        "rows": rows,
    }
    destino = ROOT / "data" / "latest.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(rows)} papéis gravados em {destino}")


if __name__ == "__main__":
    main()
