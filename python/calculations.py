def asset_return(entry_price, current_price):
    """
    Retorno simples de um ativo.
    """

    if entry_price == 0:
        return 0

    return (current_price / entry_price) - 1


def contribution(asset_return_value, weight):
    """
    Contribuição do ativo para o retorno da carteira.
    """

    return asset_return_value * weight


def portfolio_return(returns, weights):
    """
    Retorno ponderado da carteira.
    """

    total = 0

    for ticker in returns:

        total += (
            returns[ticker]
            * weights[ticker]
        )

    return total

def di_return(entry_pu, current_pu):
    """
    Retorno aproximado da posição em DI
    através da variação do PU.
    """

    if entry_pu == 0:
        return 0

    return (current_pu / entry_pu) - 1