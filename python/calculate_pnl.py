import json
from pathlib import Path
from datetime import datetime


# ========================================
# CONFIGURAÇÃO
# ========================================

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_FILE = BASE_DIR / "config" / "portfolio.json"
HISTORY_FILE = BASE_DIR / "data" / "history.json"
OUTPUT_FILE = BASE_DIR / "data" / "portfolio.json"


# ========================================
# CARREGAR DADOS
# ========================================

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = json.load(file)

with open(HISTORY_FILE, "r", encoding="utf-8") as file:
    history = json.load(file)


fund = config["fund"]
positions = config["positions"]

start_date = fund["start_date"]
initial_nav = fund["initial_nav"]


# ========================================
# CALCULAR POSIÇÕES
# ========================================

results = []

total_return = 0
covered_weight = 0


for position in positions:

    ticker = position["ticker"]
    weight = position["weight"]

    asset = history["assets"].get(ticker)


    # ====================================
    # ATIVO SEM DADOS
    # ====================================

    if asset is None:

        results.append({
            "ticker": ticker,
            "name": position["name"],
            "category": position["category"],
            "position": position["position"],
            "weight": weight,
            "entry_price": None,
            "current_price": None,
            "entry_date": None,
            "current_date": None,
            "return": None,
            "contribution": None,
            "status": "SEM DADOS"
        })

        continue


    prices = asset["prices"]


    # ====================================
    # PREÇO DE ENTRADA
    # ====================================

    entry_price = prices.get(start_date)


    if entry_price is None:

        results.append({
            "ticker": ticker,
            "name": position["name"],
            "category": position["category"],
            "position": position["position"],
            "weight": weight,
            "entry_price": None,
            "current_price": None,
            "entry_date": start_date,
            "current_date": None,
            "return": None,
            "contribution": None,
            "status": "SEM PREÇO INICIAL"
        })

        continue


    # ====================================
    # ÚLTIMO PREÇO DISPONÍVEL
    # ====================================

    available_dates = [
        date
        for date in prices.keys()
        if date >= start_date
    ]

    if not available_dates:

        results.append({
            "ticker": ticker,
            "name": position["name"],
            "category": position["category"],
            "position": position["position"],
            "weight": weight,
            "entry_price": entry_price,
            "current_price": None,
            "entry_date": start_date,
            "current_date": None,
            "return": None,
            "contribution": None,
            "status": "SEM PREÇO ATUAL"
        })

        continue


    current_date = max(available_dates)
    current_price = prices[current_date]


    # ====================================
    # RETORNO
    # ====================================

    asset_return = (
        current_price / entry_price
    ) - 1


    contribution = (
        asset_return * weight
    )


    total_return += contribution
    covered_weight += weight


    results.append({
        "ticker": ticker,
        "name": position["name"],
        "category": position["category"],
        "position": position["position"],
        "weight": weight,
        "entry_price": entry_price,
        "current_price": current_price,
        "entry_date": start_date,
        "current_date": current_date,
        "return": asset_return,
        "contribution": contribution,
        "status": "OK"
    })


# ========================================
# NAV PARCIAL
# ========================================

partial_nav = (
    initial_nav * (1 + total_return)
)

partial_pnl = partial_nav - initial_nav


# ========================================
# STATUS DA CARTEIRA
# ========================================

total_weight = sum(
    position["weight"]
    for position in positions
)

missing_weight = total_weight - covered_weight


if covered_weight == total_weight:
    portfolio_status = "COMPLETO"
else:
    portfolio_status = "PARCIAL"


# ========================================
# OUTPUT
# ========================================

portfolio = {

    "timestamp": datetime.now().isoformat(),

    "start_date": start_date,

    "initial_nav": initial_nav,

    "covered_weight": covered_weight,

    "missing_weight": missing_weight,

    "status": portfolio_status,

    "partial_return": total_return,

    "partial_nav": partial_nav,

    "partial_pnl": partial_pnl,

    "positions": results
}


# ========================================
# SALVAR
# ========================================

with open(OUTPUT_FILE, "w", encoding="utf-8") as file:

    json.dump(
        portfolio,
        file,
        indent=4,
        ensure_ascii=False
    )


# ========================================
# TERMINAL
# ========================================

print("Portfolio calculado.")
print()

print(f"Status:           {portfolio_status}")
print(f"Peso calculado:   {covered_weight:.2%}")
print(f"Peso sem dados:   {missing_weight:.2%}")

print()

print(f"Retorno parcial:  {total_return:+.4%}")
print(f"NAV parcial:      R$ {partial_nav:,.2f}")
print(f"P&L parcial:      R$ {partial_pnl:,.2f}")

print()

for result in results:

    if result["status"] == "OK":

        print(
            f'{result["ticker"]:10} '
            f'{result["current_date"]} '
            f'{result["return"]:+.2%} '
            f'({result["contribution"]:+.2%})'
        )

    else:

        print(
            f'{result["ticker"]:10} '
            f'{result["status"]}'
        )
