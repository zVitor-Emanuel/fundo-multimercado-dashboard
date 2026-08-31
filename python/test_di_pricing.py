from di_pricing import di_pu


rate = 0.1376
business_days = 92

pu = di_pu(
    rate,
    business_days
)

print(f"Taxa: {rate * 100:.3f}%")
print(f"Dias úteis: {business_days}")
print(f"PU: {pu:,.2f}")

entry_rate = 0.1376
current_rate = 0.1350

entry_pu = di_pu(
    entry_rate,
    92
)

current_pu = di_pu(
    current_rate,
    92
)

print()
print("Cenário de queda dos juros")
print("---------------------------")

print(
    f"PU inicial: {entry_pu:,.2f}"
)

print(
    f"PU atual:   {current_pu:,.2f}"
)

print(
    f"Variação PU: "
    f"{current_pu - entry_pu:,.2f}"
)

from calculations import di_return


entry_pu = 95402.41
current_pu = 95738.80

retorno = di_return(
    entry_pu,
    current_pu
)

print()
print("Retorno pelo PU")
print("----------------")

print(
    f"{retorno * 100:.4f}%"
)