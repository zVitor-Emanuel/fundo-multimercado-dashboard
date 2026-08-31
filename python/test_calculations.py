from calculations import (
    asset_return,
    contribution,
    portfolio_return
)


entry_prices = {

    "GGBR4": 24.78,
    "PETR4": 42.47,
    "ITUB4": 38.38,
    "SBSP3": 23.80,
    "AXIA3": 50.18,
    "USD": 5.2014

}


weights = {

    "GGBR4": 0.09,
    "PETR4": 0.04,
    "ITUB4": 0.04,
    "SBSP3": 0.04,
    "AXIA3": 0.04,
    "USD": 0.15

}


current_prices = {

    "GGBR4": 23.80,
    "PETR4": 42.70,
    "ITUB4": 39.19,
    "SBSP3": 25.24,
    "AXIA3": 53.10,
    "USD": 5.1999

}


returns = {}


for ticker in entry_prices:

    returns[ticker] = asset_return(
        entry_prices[ticker],
        current_prices[ticker]
    )


for ticker in returns:

    print(
        ticker,
        f"{returns[ticker] * 100:.2f}%"
    )


print(
    "\nContribuição:"
)


for ticker in returns:

    value = contribution(
        returns[ticker],
        weights[ticker]
    )

    print(
        ticker,
        f"{value * 100:.2f} p.p."
    )


total = portfolio_return(
    returns,
    weights
)


print(
    "\nRetorno parcial:",
    f"{total * 100:.2f}%"
)