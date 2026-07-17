"""
Snapshot diário do Fundamentus para os papéis do IBOV.

Lê ``scraper/ibov.txt``, ``scraper/segmentos.csv`` e
``scraper/classificacao_setorial.csv``, raspa ``resultado.php`` e grava
``data/latest.json`` na raiz do repositório.
"""
import csv
import json
import os
import re
import sys
import time
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
    "divliqpatrim": ("div_liq_pat", False),
    "crescrec5a": ("cresc_rec_5a", True),
}

# Instituições financeiras: EV/EBITDA, liq. corrente etc. não se aplicam.
FINANCEIRAS = {
    "BBAS3", "BBDC4", "BBSE3", "BPAC11", "CXSE3",
    "ITSA4", "ITUB4", "PSSA3", "SANB11",
}
NULOS_FINANCEIRAS = {
    "ev_ebit", "ev_ebitda", "mrg_liq", "liq_corr", "div_liq_pat", "roic",
}


def normaliza(texto: str) -> str:
    """Remove acentos e qualquer caractere que não seja letra ou número."""
    s = unicodedata.normalize("NFKD", texto)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_num(txt: str, pct: bool):
    txt = txt.strip()
    if not txt or txt in {"-", "--"}:
        return None
    txt = txt.replace("%", "").replace(".", "").replace(",", ".")
    try:
        value = float(txt)
    except ValueError:
        return None
    return value / 100 if pct else value


def carrega_ibov() -> list[str]:
    linhas = (BASE / "ibov.txt").read_text(encoding="utf-8").splitlines()
    return [linha.strip().upper() for linha in linhas if linha.strip() and not linha.startswith("#")]


def carrega_segmentos() -> dict[str, str]:
    segmentos: dict[str, str] = {}
    with (BASE / "segmentos.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            segmentos[row["ticker"].strip().upper()] = row["segmento"].strip().upper()
    return segmentos


def carrega_classificacao_setorial() -> dict[str, dict[str, str]]:
    classificacao: dict[str, dict[str, str]] = {}
    path = BASE / "classificacao_setorial.csv"
    if not path.exists():
        return classificacao
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ticker = row.get("ticker", "").strip().upper()
            if not ticker:
                continue
            classificacao[ticker] = {
                "setor": row.get("setor", "").strip() or "Não classificado",
                "atividade": row.get("atividade", "").strip() or "Não classificada",
            }
    return classificacao


def main() -> None:
    tickers = set(carrega_ibov())
    segmentos = carrega_segmentos()
    classificacao = carrega_classificacao_setorial()
    sem_setor = sorted(tickers - set(classificacao))
    if sem_setor:
        print(f"AVISO: {len(sem_setor)} tickers sem classificação setorial: {sem_setor}")

    def fetch_html() -> str:
        # Se definido, usa um proxy próprio (plano B — ver instruções).
        url_base = os.environ.get("FUNDAMENTUS_PROXY") or URL
        ultimo_erro = None
        for tentativa in range(1, 6):
            try:
                response = requests.get(url_base, headers=HEADERS, timeout=(15, 60))
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                ultimo_erro = exc
                espera = tentativa * 20
                print(f"Tentativa {tentativa}/5 falhou: {exc}. Aguardando {espera}s...")
                time.sleep(espera)
        sys.exit(f"ERRO: Fundamentus inacessível após 5 tentativas: {ultimo_erro}")

    html = fetch_html()
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.find("table")
    if not tabela:
        sys.exit("ERRO: Nenhuma tabela encontrada no HTML.")

    ths = tabela.find("thead").find_all("th")
    cabecalhos_norm = [normaliza(th.get_text()) for th in ths]

    indices = {}
    for index, header in enumerate(cabecalhos_norm):
        if header in CAMPOS:
            indices[index] = CAMPOS[header]

    esperadas = {key for key, _ in CAMPOS.values()}
    obtidas = {key for key, _ in indices.values()}
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
        setor = classificacao.get(papel, {})
        row = {
            "papel": papel,
            "segmento": segmentos.get(papel),
            "setor": setor.get("setor", "Não classificado"),
            "atividade": setor.get("atividade", "Não classificada"),
        }
        for index, (chave, percentual) in indices.items():
            row[chave] = parse_num(tds[index].get_text(), percentual)
        if papel in FINANCEIRAS:
            for chave in NULOS_FINANCEIRAS:
                row[chave] = None
        rows.append(row)

    encontrados = {row["papel"] for row in rows}
    ausentes = sorted(tickers - encontrados)
    if ausentes:
        print(f"AVISO: {len(ausentes)} tickers não encontrados: {ausentes}")
    if len(rows) < len(tickers) * 0.8:
        sys.exit("ERRO: menos de 80% dos tickers coletados — abortando para não gravar snapshot ruim.")

    rows.sort(key=lambda row: row["papel"])
    out = {
        "data_coleta": date.today().isoformat(),
        "fonte": "fundamentus.com.br",
        "classificacao_setorial_fonte": "B3 — classificação revisada periodicamente",
        "total": len(rows),
        "ausentes": ausentes,
        "sem_classificacao_setorial": sem_setor,
        "rows": rows,
    }
    destino = ROOT / "data" / "latest.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(rows)} papéis gravados em {destino}")


if __name__ == "__main__":
    main()
