def di_pu(rate, business_days, face_value=100_000):
    """
    Calcula o PU teórico de um contrato futuro de DI1.

    rate:
        taxa anual em formato decimal.
        Exemplo: 13,76% = 0.1376

    business_days:
        número de dias úteis até o vencimento.

    face_value:
        valor no vencimento do contrato.
    """

    return face_value / (
        (1 + rate) ** (business_days / 252)
    )