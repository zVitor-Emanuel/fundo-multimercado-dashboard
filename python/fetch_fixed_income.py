import json
from datetime import date, datetime
from pathlib import Path

import polars as pl
import pyield as yd


# =========================
# CONFIGURAÇÃO
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = BASE_DIR / "data" / "history.json"

START_DATE = "2026-08-17"

# Até a última data com dado de ajuste de DI1 já publicado.
END_DATE = datetime.now().strftime("%Y-%m-%d")


DI_CONTRATOS = ["DI1F27", "DI1F31"]

NTNB_VENCIMENTOS = {
    "NTNB2031": date(2031, 5, 15),
    "NTNB2050": date(2050, 8, 15),
}


# =========================
# DATAS DE PREGÃO
# =========================

def carregar_datas_pregao():
    """
    Usa o calendário oficial de negociação do DI1 (B3) como
    referência de dias úteis/pregões válidos, tanto para o
    próprio DI1 quanto para a NTN-B (ANBIMA segue o mesmo
    calendário de dias úteis).
    """

    todas = yd.di1.datas_disponiveis()

    return [
        data
        for data in todas
        if START_DATE <= data.strftime("%Y-%m-%d") <= END_DATE
    ]


# =========================
# DI1
# =========================

def buscar_di(history, datas):

    print("Buscando DI1F27 / DI1F31...")

    df = yd.di1.dados(datas=datas)

    df = df.filter(
        pl.col("codigo_negociacao").is_in(DI_CONTRATOS)
    )

    for row in df.iter_rows(named=True):

        ticker = row["codigo_negociacao"]
        date_str = row["data_referencia"].strftime("%Y-%m-%d")
        pu = float(row["preco_ajuste"])
        taxa = row["taxa_ajuste"]

        if ticker not in history["assets"]:
            history["assets"][ticker] = {
                "type": "di_future",
                "prices": {}
            }

        history["assets"][ticker]["prices"][date_str] = pu

        print(
            f"  {ticker} {date_str}: PU {pu:,.2f} "
            f"(taxa {taxa * 100:.3f}%)"
        )


# =========================
# NTN-B
# =========================

def buscar_ntnb(history, datas):

    print("Buscando NTN-B 2031 / 2050...")

    for ticker, vencimento in NTNB_VENCIMENTOS.items():

        if ticker not in history["assets"]:
            history["assets"][ticker] = {
                "type": "ntnb",
                "prices": {}
            }

        for data in datas:

            date_str = data.strftime("%Y-%m-%d")

            df = yd.ntnb.dados(data)

            linha = df.filter(
                pl.col("data_vencimento") == vencimento
            )

            if linha.is_empty():

                print(
                    f"  {ticker} {date_str}: sem dado "
                    f"(feriado ANBIMA ou vencimento não listado)"
                )

                continue

            pu = float(linha["pu"][0])

            history["assets"][ticker]["prices"][date_str] = pu

            print(f"  {ticker} {date_str}: PU {pu:,.2f}")


# =========================
# MAIN
# =========================

def main():

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        history = json.load(file)

    if "assets" not in history:
        history["assets"] = {}

    datas = carregar_datas_pregao()

    if not datas:
        print("Nenhuma data de pregão encontrada no intervalo.")
        return

    buscar_di(history, datas)
    buscar_ntnb(history, datas)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:

        json.dump(
            history,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\nHistory atualizado com DI1 e NTN-B.")


if __name__ == "__main__":
    main()
