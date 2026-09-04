import json
import math
from pathlib import Path
from datetime import datetime

import yfinance as yf


# =========================
# CONFIGURAÇÃO
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = BASE_DIR / "data" / "history.json"

START_DATE = "2026-08-17"
END_DATE = datetime.now().strftime("%Y-%m-%d")

ASSETS = {
    "GGBR4": "GGBR4.SA",
    "PETR4": "PETR4.SA",
    "ITUB4": "ITUB4.SA",
    "SBSP3": "SBSP3.SA",
    "AXIA3": "AXIA3.SA",
    "USD": "BRL=X",
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
# CARREGAR HISTORY
# =========================

with open(HISTORY_FILE, "r", encoding="utf-8") as file:
    history = json.load(file)

# Garantir estrutura
if "assets" not in history:
    history["assets"] = {}

# Limpar NaN que possam existir de execuções anteriores
history = sanitize(history)

# Remover entradas None (preços inválidos já salvos)
for ticker_key, asset in history["assets"].items():
    asset["prices"] = {
        d: p for d, p in asset["prices"].items() if p is not None
    }


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

        if date.weekday() >= 5:
            continue

        price = float(price)

        # NaN/Inf não são JSON válidos — descartar
        if math.isnan(price) or math.isinf(price):
            continue

        date_str = date.strftime("%Y-%m-%d")
        history["assets"][ticker]["prices"][date_str] = price
        print(f"  {date_str}: R$ {price:.2f}")


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