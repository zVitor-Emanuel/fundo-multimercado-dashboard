import json
from pathlib import Path

import yfinance as yf


# =========================
# CONFIGURAÇÃO
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = BASE_DIR / "data" / "history.json"

START_DATE = "2026-08-17"
END_DATE = "2026-09-01"

ASSETS = {
    "GGBR4": "GGBR4.SA",
    "PETR4": "PETR4.SA",
    "ITUB4": "ITUB4.SA",
    "SBSP3": "SBSP3.SA",
    "AXIA3": "AXIA3.SA",
    "USD": "BRL=X",
}


# =========================
# CARREGAR HISTORY
# =========================

with open(HISTORY_FILE, "r", encoding="utf-8") as file:
    history = json.load(file)


# Garantir estrutura
if "assets" not in history:
    history["assets"] = {}


# =========================
# BUSCAR DADOS
# =========================

for ticker, yf_ticker in ASSETS.items():

    print(f"Buscando histórico de {ticker}...")

    data = yf.download(
        yf_ticker,
        start=START_DATE,
        end=END_DATE,
        auto_adjust=False,
        progress=False
    )

    if data.empty:
        print(f"  Nenhum dado encontrado para {ticker}")
        continue

    # =========================
    # PREPARAR COLUNA CLOSE
    # =========================

    close = data["Close"]

    # Compatibilidade com MultiIndex do yfinance
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    # =========================
    # CRIAR ATIVO NO HISTORY
    # =========================

    if ticker not in history["assets"]:

        asset_type = "fx" if ticker == "USD" else "equity"

        history["assets"][ticker] = {
            "type": asset_type,
            "prices": {}
        }

    # =========================
    # SALVAR CADA PREGÃO
    # =========================

    for date, price in close.items():

        # Ignorar sábados e domingos
        if date.weekday() >= 5:
            continue

        date_str = date.strftime("%Y-%m-%d")

        price = float(price)

        history["assets"][ticker]["prices"][date_str] = price

        print(
            f"  {date_str}: R$ {price:.2f}"
        )


# =========================
# SALVAR HISTORY
# =========================

with open(HISTORY_FILE, "w", encoding="utf-8") as file:

    json.dump(
        history,
        file,
        indent=4,
        ensure_ascii=False
    )


print("\nHistory atualizado com sucesso.")