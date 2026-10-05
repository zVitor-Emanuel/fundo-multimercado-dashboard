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

# yfinance/Yahoo usa end exclusivo — somamos 1 dia para incluir hoje
END_DATE = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

# Mantemos TODOS os tickers que já entraram na carteira algum dia,
# mesmo os que saíram em rebalanceamentos (ex: GGBR4 zerada em
# setembro) — o histórico de preços continua sendo coletado; o
# calculate_pnl.py que decide quais tickers usar em cada perna.
ASSETS = {
    "GGBR4": ["GGBR4.SA"],
    "PETR4": ["PETR4.SA", "PETR4.SAO"],   # fallback caso um falhe
    "ITUB4": ["ITUB4.SA"],
    "SBSP3": ["SBSP3.SA", "SBSP3.SAO"],   # fallback caso um falhe
    "AXIA3": ["AXIA3.SA"],
    "WEGE3": ["WEGE3.SA"],
    # USD (dólar) não entra aqui — a posição real é FUT DOL, buscada
    # em fetch_fixed_income.py via pyield (B3), com roll de contrato.
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
# yfinance.download() já atribuiu o fechamento de um pregão à data
# errada (bug de timezone: epoch UTC não convertido pro fuso do
# pregão antes de extrair a data). Aqui batemos direto na API JSON
# e convertemos o timestamp explicitamente pro fuso correto de cada
# mercado antes de rotular a data.

def buscar_precos_yahoo(ticker: str, timezone: str, range_str: str = "6mo") -> dict:

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

        data_local = (
            pd.to_datetime(ts, unit="s", utc=True)
              .tz_convert(timezone)
        )
        date_str = data_local.strftime("%Y-%m-%d")

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
# BUSCAR AÇÕES (fuso de São Paulo — pregão B3)
# =========================

for ticker, yf_tickers in ASSETS.items():

    print(f"Buscando histórico de {ticker}...")

    precos = {}
    ticker_usado = None

    for yf_ticker in yf_tickers:
        try:
            precos = buscar_precos_yahoo(yf_ticker, timezone="America/Sao_Paulo")
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
# BUSCAR TREASURY US 10Y (ZN=F — fuso de Chicago, CME)
# =========================
#
# Contrato futuro de Treasury de 10 anos. Posição do fundo é VENDIDA
# (short) — o sinal é aplicado depois, no calculate_pnl.py, com base
# no campo "position" do config (não aqui). Aqui só guardamos o
# preço de mercado, cru, como qualquer outro ativo.

print("Buscando Treasury US 10Y (ZN=F)...")

try:
    precos_ust = buscar_precos_yahoo("ZN=F", timezone="America/Chicago")

    if precos_ust:
        if "UST10Y" not in history["assets"]:
            history["assets"]["UST10Y"] = {"type": "global", "prices": {}}

        for date_str in sorted(precos_ust.keys()):
            preco = precos_ust[date_str]
            history["assets"]["UST10Y"]["prices"][date_str] = preco
            print(f"  {date_str}: US$ {preco:.3f}")
    else:
        print("  Nenhum dado encontrado para UST10Y (ZN=F)")

except Exception as error:
    print(f"  Falha ao buscar UST10Y: {error}")


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
