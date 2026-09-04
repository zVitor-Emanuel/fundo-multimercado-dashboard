import json
from datetime import date, datetime
from pathlib import Path

import polars as pl
import pyield as yd
import yfinance as yf


# =========================
# CONFIGURAÇÃO
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
MACRO_FILE = BASE_DIR / "data" / "macro.json"

START_DATE = "2026-08-17"
END_DATE = datetime.now().strftime("%Y-%m-%d")


# Ticker (yfinance) e se o valor precisa de ajuste (ex: ^TNX vem *10)
YF_ASSETS = {
    "brent": {
        "ticker": "BZ=F",
        "label": "Brent",
        "direcao_favoravel": "queda",
        "escala": 1,
    },
    "treasury_10y": {
        "ticker": "^TNX",
        "label": "US Treasury 10Y",
        "direcao_favoravel": "queda",
        "escala": 0.1,   # ^TNX retorna o valor x10 (45.2 = 4,52%)
    },
    "ibovespa": {
        "ticker": "^BVSP",
        "label": "Ibovespa",
        "direcao_favoravel": "alta",
        "escala": 1,
    },
}


NTNB_VENCIMENTOS = {
    "ntnb_2031": date(2031, 5, 15),
    "ntnb_2050": date(2050, 8, 15),
}


# =========================
# HELPERS
# =========================

def novo_indicador(label, direcao_favoravel):

    return {
        "label": label,
        "direcao_favoravel": direcao_favoravel,
        "series": {}
    }


def garantir_indicador(indicadores, chave, label, direcao_favoravel):

    if chave not in indicadores:
        indicadores[chave] = novo_indicador(label, direcao_favoravel)

    return indicadores[chave]


# =========================
# IPCA
# =========================

def buscar_ipca(indicadores):

    print("Buscando IPCA...")

    ind = garantir_indicador(
        indicadores, "ipca_mensal", "IPCA (mensal)", "queda"
    )

    try:

        df = yd.ipca.taxas(START_DATE, END_DATE)

        for row in df.iter_rows(named=True):

            periodo = str(row["periodo"])
            periodo_fmt = f"{periodo[:4]}-{periodo[4:]}"

            ind["series"][periodo_fmt] = float(row["taxa"])

        print(f"  {len(df)} meses de IPCA carregados.")

    except Exception as error:

        print(f"  Falha ao buscar IPCA: {error}")


# =========================
# SELIC META
# =========================

def buscar_selic(indicadores):

    print("Buscando Selic Meta...")

    ind = garantir_indicador(
        indicadores, "selic_meta", "Selic Meta", "queda"
    )

    try:

        df = yd.selic.meta_serie(inicio=START_DATE, fim=END_DATE)

        for row in df.iter_rows(named=True):

            date_str = row["data"].strftime("%Y-%m-%d")
            ind["series"][date_str] = float(row["taxa"])

        print(f"  {len(df)} registros de Selic carregados.")

    except Exception as error:

        print(f"  Falha ao buscar Selic: {error}")


# =========================
# USD/BRL (PTAX)
# =========================

def buscar_ptax(indicadores):

    print("Buscando USD/BRL (PTAX)...")

    ind = garantir_indicador(
        indicadores, "usd_brl", "USD/BRL (PTAX)", "queda"
    )

    try:

        df = yd.ptax_serie(inicio=START_DATE, fim=END_DATE)

        for row in df.iter_rows(named=True):

            date_str = row["data"].strftime("%Y-%m-%d")
            ind["series"][date_str] = float(row["cotacao"])

        print(f"  {len(df)} cotações de PTAX carregadas.")

    except Exception as error:

        print(f"  Falha ao buscar PTAX: {error}")


# =========================
# DI1 (taxa, não PU) — reaproveita o mesmo pregão do fetch_fixed_income
# =========================

def buscar_di_taxas(indicadores):

    print("Buscando taxas de DI1F27 / DI1F31...")

    ind_27 = garantir_indicador(
        indicadores, "di_jan27", "DI Jan/27", "queda"
    )

    ind_31 = garantir_indicador(
        indicadores, "di_jan31", "DI Jan/31", "queda"
    )

    try:

        todas_datas = yd.di1.datas_disponiveis()

        datas = [
            d for d in todas_datas
            if START_DATE <= d.strftime("%Y-%m-%d") <= END_DATE
        ]

        df = yd.di1.dados(datas=datas)

        df = df.filter(
            pl.col("codigo_negociacao").is_in(["DI1F27", "DI1F31"])
        )

        for row in df.iter_rows(named=True):

            date_str = row["data_referencia"].strftime("%Y-%m-%d")
            taxa = float(row["taxa_ajuste"])

            if row["codigo_negociacao"] == "DI1F27":
                ind_27["series"][date_str] = taxa
            else:
                ind_31["series"][date_str] = taxa

        print(f"  {len(df)} linhas de DI1 carregadas.")

    except Exception as error:

        print(f"  Falha ao buscar taxas de DI1: {error}")


# =========================
# NTN-B (taxa indicativa)
# =========================

def buscar_ntnb_taxas(indicadores):

    print("Buscando taxas de NTN-B 2031 / 2050...")

    for chave, vencimento in NTNB_VENCIMENTOS.items():

        label = f"NTN-B {vencimento.year}"

        ind = garantir_indicador(
            indicadores, chave, label, "queda"
        )

        try:

            todas_datas = yd.di1.datas_disponiveis()

            datas = [
                d for d in todas_datas
                if START_DATE <= d.strftime("%Y-%m-%d") <= END_DATE
            ]

            for data in datas:

                date_str = data.strftime("%Y-%m-%d")

                df = yd.ntnb.dados(data)

                linha = df.filter(
                    pl.col("data_vencimento") == vencimento
                )

                if linha.is_empty():
                    continue

                ind["series"][date_str] = float(
                    linha["taxa_indicativa"][0]
                )

            print(f"  {chave}: {len(ind['series'])} pontos carregados.")

        except Exception as error:

            print(f"  Falha ao buscar {chave}: {error}")


# =========================
# BRENT / TREASURY 10Y / IBOVESPA (yfinance)
# =========================

def buscar_yfinance(indicadores):

    for chave, info in YF_ASSETS.items():

        print(f"Buscando {info['label']}...")

        ind = garantir_indicador(
            indicadores, chave, info["label"], info["direcao_favoravel"]
        )

        try:

            data = yf.download(
                info["ticker"],
                start=START_DATE,
                end=END_DATE,
                auto_adjust=False,
                progress=False,
            )

            if data.empty:
                print(f"  Nenhum dado encontrado para {info['label']}.")
                continue

            close = data["Close"]

            if hasattr(close, "columns"):
                close = close.iloc[:, 0]

            for date_idx, valor in close.items():

                if date_idx.weekday() >= 5:
                    continue

                date_str = date_idx.strftime("%Y-%m-%d")
                ind["series"][date_str] = float(valor) * info["escala"]

            print(f"  {len(ind['series'])} pontos carregados.")

        except Exception as error:

            print(f"  Falha ao buscar {info['label']}: {error}")


# =========================
# MAIN
# =========================

def main():

    if MACRO_FILE.exists():

        with open(MACRO_FILE, "r", encoding="utf-8") as file:
            macro = json.load(file)

    else:
        macro = {}

    if "indicators" not in macro:
        macro["indicators"] = {}

    indicadores = macro["indicators"]

    buscar_ipca(indicadores)
    buscar_selic(indicadores)
    buscar_ptax(indicadores)
    buscar_di_taxas(indicadores)
    buscar_ntnb_taxas(indicadores)
    buscar_yfinance(indicadores)

    macro["timestamp"] = datetime.now().isoformat()

    with open(MACRO_FILE, "w", encoding="utf-8") as file:

        json.dump(
            macro,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\nmacro.json atualizado.")


if __name__ == "__main__":
    main()
