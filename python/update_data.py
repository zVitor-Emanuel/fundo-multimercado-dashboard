import json
import math
from pathlib import Path
from datetime import datetime, timedelta

import requests
import pandas as pd


# =========================
# CONFIGURAÇÃO
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = BASE_DIR / "data" / "history.json"

START_DATE = "2026-08-17"
END_DATE   = datetime.now().strftime("%Y-%m-%d")

ASSETS = {
    "GGBR4": ["GGBR4.SA"],
    "PETR4": ["PETR4.SA", "PETR4.SAO"],   # fallback caso um falhe
    "ITUB4": ["ITUB4.SA"],
    "SBSP3": ["SBSP3.SA", "SBSP3.SAO"],   # fallback caso um falhe
    "AXIA3": ["AXIA3.SA"],
    # USD removido daqui — a posição real é FUT DOL, não dólar à
    # vista. Buscado em fetch_fixed_income.py via pyield (B3),
    # com roll de contrato mensal e ajuste correto do futuro.
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


# =========================
# SANITIZAR — remove NaN/Inf de qualquer objeto aninhado
# =========================

def sanitize(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


# =========================
# BUSCAR PREÇOS — API JSON crua do Yahoo Finance
# =========================
#
# yfinance.download() já causou pelo menos um caso de fechamento
# atribuído à data errada — o timestamp que a Yahoo retorna é um
# epoch UTC, e se não for explicitamente convertido para o fuso
# de negociação (America/Sao_Paulo) antes de extrair a data, o
# pregão pode "vazar" para o dia seguinte ou anterior dependendo
# do horário de corte do fechamento em UTC.
#
# Aqui batemos direto na API JSON e fazemos a conversão de fuso
# manualmente, igual à correção validada por um teste independente
# que bateu 1:1 com os números oficiais do relatório do Safra.

def buscar_precos_yahoo(ticker: str, range_str: str = "6mo") -> dict:

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval=1d"

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    result_list = payload.get("chart", {}).get("result")
    if not result_list:
        return {}

    result     = result_list[0]
    timestamps = result.get("timestamp", [])
    closes     = result["indicators"]["quote"][0].get("close", [])

    precos = {}

    for ts, close in zip(timestamps, closes):

        if close is None:
            continue

        # epoch UTC -> data no fuso de São Paulo (é isso que corrige
        # o problema de fechamento indo pro dia errado)
        data_sp = (
            pd.to_datetime(ts, unit="s", utc=True)
              .tz_convert("America/Sao_Paulo")
        )
        date_str = data_sp.strftime("%Y-%m-%d")

        if date_str < START_DATE or date_str > END_DATE:
            continue

        preco = float(close)
        if math.isnan(preco) or math.isinf(preco):
            continue

        precos[date_str] = preco

    return precos


# =========================
# CARREGAR HISTORY
# =========================

with open(HISTORY_FILE, "r", encoding="utf-8") as file:
    history = json.load(file)

if "assets" not in history:
    history["assets"] = {}

history = sanitize(history)

for ticker_key, asset in history["assets"].items():
    asset["prices"] = {
        d: p for d, p in asset["prices"].items() if p is not None
    }


# =========================
# BUSCAR DADOS
# =========================

for ticker, yf_tickers in ASSETS.items():

    print(f"Buscando histórico de {ticker}...")

    precos = {}
    ticker_usado = None

    for yf_ticker in yf_tickers:
        try:
            precos = buscar_precos_yahoo(yf_ticker)
            if precos:
                ticker_usado = yf_ticker
                break
            print(f"  {yf_ticker}: sem dados, tentando próximo...")
        except Exception as error:
            print(f"  {yf_ticker}: falhou ({error}), tentando próximo...")

    if not precos:
        print(f"  Nenhum dado encontrado para {ticker} (todos os tickers falharam)")
        continue

    print(f"  ticker usado: {ticker_usado}")

    if ticker not in history["assets"]:
        history["assets"][ticker] = {"type": "equity", "prices": {}}

    for date_str in sorted(precos.keys()):
        preco = precos[date_str]
        history["assets"][ticker]["prices"][date_str] = preco
        print(f"  {date_str}: R$ {preco:.2f}")


# =========================
# SALVAR HISTORY
# =========================

with open(HISTORY_FILE, "w", encoding="utf-8") as file:

    json.dump(
        history,
        file,
        indent=4,
        ensure_ascii=False,
        allow_nan=False
    )


print("\nHistory atualizado com sucesso.")
