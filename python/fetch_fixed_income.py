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
    df = df.filter(pl.col("codigo_negociacao").is_in(DI_CONTRATOS))

    for row in df.iter_rows(named=True):

        ticker   = row["codigo_negociacao"]
        date_str = row["data_referencia"].strftime("%Y-%m-%d")
        pu       = float(row["preco_ajuste"])
        taxa     = row["taxa_ajuste"]

        if ticker not in history["assets"]:
            history["assets"][ticker] = {"type": "di_future", "prices": {}}

        history["assets"][ticker]["prices"][date_str] = pu

        print(f"  {ticker} {date_str}: PU {pu:,.2f} (taxa {taxa * 100:.3f}%)")


# =========================
# NTN-B
# =========================

def buscar_ntnb(history, datas):

    print("Buscando NTN-B 2031 / 2050...")

    for ticker, vencimento in NTNB_VENCIMENTOS.items():

        if ticker not in history["assets"]:
            history["assets"][ticker] = {"type": "ntnb", "prices": {}}

        for data in datas:

            date_str = data.strftime("%Y-%m-%d")
            df = yd.ntnb.dados(data)
            linha = df.filter(pl.col("data_vencimento") == vencimento)

            if linha.is_empty():
                print(f"  {ticker} {date_str}: sem dado (feriado ANBIMA ou vencimento não listado)")
                continue

            pu = float(linha["pu"][0])
            history["assets"][ticker]["prices"][date_str] = pu

            print(f"  {ticker} {date_str}: PU {pu:,.2f}")


# =========================
# DOL (dólar futuro) — com roll de contrato
# =========================
#
# O DOL vence mensalmente (diferente do DI, que vence em 2027/2031 e
# não precisa rolar dentro da janela do fundo). Usa o contrato
# corrente (front-month) até vencer; no dia seguinte, passa pro
# próximo. O P&L é somado "por perna": diferença dia-a-dia dentro de
# cada contrato, sem comparar preços de contratos diferentes.
#
# Preço do DOL é cotado em R$ por US$ 1.000 — dividimos por 1000.

def buscar_dol(history, datas):

    print("Buscando FUT DOL (com roll mensal de contrato)...")

    ticker = "USD"

    if ticker not in history["assets"]:
        history["assets"][ticker] = {"type": "dol_future", "prices": {}, "contracts": {}}
    else:
        history["assets"][ticker]["type"] = "dol_future"
        if "contracts" not in history["assets"][ticker]:
            history["assets"][ticker]["contracts"] = {}

    df_full = yd.futuro.historico(datas, "DOL")
    df_full = df_full.filter(pl.col("codigo_negociacao").str.starts_with("DOL"))

    contrato_atual = None

    for data in datas:

        date_str = data.strftime("%Y-%m-%d")
        linha_dia = df_full.filter(pl.col("data_referencia") == data)

        if linha_dia.is_empty():
            continue

        if contrato_atual is None:
            candidatos = linha_dia.sort("data_vencimento")
            contrato_atual = candidatos["codigo_negociacao"][0]
        else:
            ainda_negociado = linha_dia.filter(pl.col("codigo_negociacao") == contrato_atual)
            if ainda_negociado.is_empty():
                candidatos = linha_dia.sort("data_vencimento")
                novo_contrato = candidatos["codigo_negociacao"][0]
                print(f"  Roll: {contrato_atual} → {novo_contrato} em {date_str}")
                contrato_atual = novo_contrato

        linha = linha_dia.filter(pl.col("codigo_negociacao") == contrato_atual)

        if linha.is_empty():
            continue

        preco = float(linha["preco_ajuste"][0]) / 1000.0

        history["assets"][ticker]["prices"][date_str] = preco
        history["assets"][ticker]["contracts"][date_str] = contrato_atual

        print(f"  {date_str} [{contrato_atual}]: R$ {preco:.4f}")


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
    buscar_dol(history, datas)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=4, ensure_ascii=False, allow_nan=False)

    print("\nhistory.json atualizado com DI1 e NTN-B.")


if __name__ == "__main__":
    main()
