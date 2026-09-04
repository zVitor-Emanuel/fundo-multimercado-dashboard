"""
calculate_macro.py
==================
Lê macro.json (séries históricas de cada indicador) e gera
macro_output.json com:

  - valor atual e variação de cada indicador
  - status semáforo por fator (Desinflação / Juros / Fiscal / Externo)
  - Tese Score (0-100) com decomposição transparente

LÓGICA DO SCORE
---------------
A tese do Kairos é: desinflação → queda de juros → reprecificação.
O score mede o quanto os dados confirmam (ou ameaçam) essa tese.

Cinco fatores, pesos e regras:

  Fator              Peso  Indicadores
  -----------------  ----  ------------------------------------
  Desinflação         30   IPCA mensal, DI Jan/27
  Ciclo de Juros      25   DI Jan/27, DI Jan/31, NTN-B 2031
  Câmbio/Fiscal       20   USD/BRL, NTN-B 2050
  Externo             15   Brent, Treasury 10Y
  Ibovespa            10   Ibovespa

Cada indicador recebe um sub-score 0-10 conforme move na
direção favorável (queda ou alta) desde o início do período.

Escala de conversão:
  - movimento favorável >= limiar "bom"    → 10
  - neutro (entre -limiar e +limiar)       → 5
  - movimento desfavorável >= limiar "mau" → 0
  - intermediários: interpolação linear

Limiares definidos abaixo em LIMIAR; podem ser ajustados sem
tocar no resto do código.
"""

import json
from pathlib import Path
from datetime import datetime


# ========================================
# CONFIGURAÇÃO
# ========================================

BASE_DIR = Path(__file__).resolve().parent.parent
MACRO_FILE = BASE_DIR / "data" / "macro.json"
OUTPUT_FILE = BASE_DIR / "data" / "macro_output.json"


# Limiar de variação para score máximo/mínimo.
# Chave = indicador em macro.json.
# "bom": variação favorável que rende score 10
# "mau": variação desfavorável que rende score 0
# Variações em valores absolutos do próprio indicador
# (ex: taxa DI em decimal, USD em R$, Brent em USD).
LIMIAR = {
    "ipca_mensal":   {"bom": -0.0010, "mau":  0.0020},   # -0,10 p.p. mensal
    "di_jan27":      {"bom": -0.0050, "mau":  0.0050},   # -50 bps
    "di_jan31":      {"bom": -0.0050, "mau":  0.0050},
    "ntnb_2031":     {"bom": -0.0030, "mau":  0.0030},   # -30 bps
    "ntnb_2050":     {"bom": -0.0030, "mau":  0.0030},
    "usd_brl":       {"bom": -0.1500, "mau":  0.2000},   # -R$0,15 / +R$0,20
    "brent":         {"bom": -5.0,    "mau":  10.0},     # -US$5 / +US$10
    "treasury_10y":  {"bom": -0.0020, "mau":  0.0020},   # -20 bps
    "ibovespa":      {"bom":  3000,   "mau": -5000},     # +3k pts / -5k pts
}


# Estrutura dos fatores: lista de (chave_indicador, peso_dentro_do_fator)
FATORES = {
    "desinflacao": {
        "label": "Desinflação",
        "peso": 0.30,
        "indicadores": [
            ("ipca_mensal", 0.6),
            ("di_jan27",    0.4),
        ],
    },
    "juros": {
        "label": "Ciclo de Juros",
        "peso": 0.25,
        "indicadores": [
            ("di_jan27",  0.40),
            ("di_jan31",  0.30),
            ("ntnb_2031", 0.30),
        ],
    },
    "cambio_fiscal": {
        "label": "Câmbio / Fiscal",
        "peso": 0.20,
        "indicadores": [
            ("usd_brl",   0.55),
            ("ntnb_2050", 0.45),
        ],
    },
    "externo": {
        "label": "Externo",
        "peso": 0.15,
        "indicadores": [
            ("brent",        0.50),
            ("treasury_10y", 0.50),
        ],
    },
    "mercado": {
        "label": "Mercado (Ibovespa)",
        "peso": 0.10,
        "indicadores": [
            ("ibovespa", 1.0),
        ],
    },
}


# ========================================
# HELPERS DE SÉRIE
# ========================================

def ultimo_valor(series: dict):
    """Retorna (data, valor) do registro mais recente."""
    if not series:
        return None, None
    ultima_data = max(series.keys())
    return ultima_data, series[ultima_data]


def primeiro_valor(series: dict):
    """Retorna (data, valor) do primeiro registro."""
    if not series:
        return None, None
    primeira_data = min(series.keys())
    return primeira_data, series[primeira_data]


def variacao(v_atual, v_inicial):
    """Variação absoluta (atual - inicial)."""
    if v_atual is None or v_inicial is None:
        return None
    return v_atual - v_inicial


# ========================================
# SUB-SCORE POR INDICADOR
# ========================================

def sub_score(chave: str, delta, direcao_favoravel: str) -> float | None:
    """
    Retorna score 0-10 para um indicador.

    delta: variação atual - inicial (absoluta).
    direcao_favoravel: "queda" ou "alta".

    Para "queda": delta negativo é favorável.
    Para "alta":  delta positivo é favorável.
    """
    if delta is None:
        return None

    lim = LIMIAR.get(chave)
    if lim is None:
        return 5.0  # sem limiar definido → neutro

    bom = lim["bom"]
    mau = lim["mau"]

    # Normaliza: movimento_favoravel > 0 é bom
    if direcao_favoravel == "queda":
        movimento = -delta   # queda → delta negativo → positivo após inversão
        lim_bom = -bom       # bom é negativo em valor original → positivo aqui
        lim_mau = -mau
    else:
        movimento = delta
        lim_bom = bom
        lim_mau = mau

    # Clamp e interpolação linear entre lim_mau (0) e lim_bom (10)
    if lim_bom == lim_mau:
        return 5.0

    score = 10 * (movimento - lim_mau) / (lim_bom - lim_mau)
    return max(0.0, min(10.0, score))


# ========================================
# STATUS SEMÁFORO
# ========================================

def semaforo(score_fator: float | None) -> str:
    if score_fator is None:
        return "cinza"
    if score_fator >= 6.5:
        return "verde"
    if score_fator >= 3.5:
        return "amarelo"
    return "vermelho"


# ========================================
# CALCULAR TUDO
# ========================================

def calcular(macro: dict) -> dict:

    indicadores_raw = macro.get("indicators", {})

    # ---- resumo de cada indicador ----
    indicadores_out = {}

    for chave, ind in indicadores_raw.items():

        series = ind.get("series", {})
        data_atual, valor_atual = ultimo_valor(series)
        data_inicial, valor_inicial = primeiro_valor(series)
        delta = variacao(valor_atual, valor_inicial)

        score = sub_score(chave, delta, ind.get("direcao_favoravel", "queda"))

        indicadores_out[chave] = {
            "label":               ind.get("label", chave),
            "direcao_favoravel":   ind.get("direcao_favoravel", "queda"),
            "data_inicial":        data_inicial,
            "valor_inicial":       valor_inicial,
            "data_atual":          data_atual,
            "valor_atual":         valor_atual,
            "delta":               delta,
            "sub_score":           score,
        }

    # ---- fatores ----
    fatores_out = {}
    score_total = 0.0
    peso_com_dados = 0.0

    for fator_chave, fator in FATORES.items():

        numerador = 0.0
        denominador = 0.0

        for (ind_chave, peso_ind) in fator["indicadores"]:

            ind_out = indicadores_out.get(ind_chave)

            if ind_out is None or ind_out["sub_score"] is None:
                continue

            numerador  += ind_out["sub_score"] * peso_ind
            denominador += peso_ind

        if denominador == 0:
            score_fator = None
        else:
            score_fator = numerador / denominador

        status = semaforo(score_fator)

        fatores_out[fator_chave] = {
            "label":       fator["label"],
            "peso":        fator["peso"],
            "score":       score_fator,
            "status":      status,
        }

        if score_fator is not None:
            score_total += score_fator * fator["peso"]
            peso_com_dados += fator["peso"]

    # normaliza se faltar dados em algum fator
    if 0 < peso_com_dados < 1:
        score_total = score_total / peso_com_dados

    tese_score = round(score_total * 10, 1)   # 0-100

    return {
        "timestamp":   datetime.now().isoformat(),
        "tese_score":  tese_score,
        "tese_status": semaforo(tese_score / 10),
        "fatores":     fatores_out,
        "indicadores": indicadores_out,
    }


# ========================================
# MAIN
# ========================================

def main():

    with open(MACRO_FILE, "r", encoding="utf-8") as file:
        macro = json.load(file)

    output = calcular(macro)

    import math

    def sanitize(obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize(v) for v in obj]
        return obj

    output = sanitize(output)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False, allow_nan=False)

    score = output["tese_score"]
    print(f"\nTese Score: {score}/100  [{output['tese_status'].upper()}]")
    print()

    for fator_chave, f in output["fatores"].items():
        s = f["score"]
        s_str = f"{s:.1f}/10" if s is not None else "s/d"
        print(f"  {f['label']:25} {s_str:8}  {f['status']}")

    print()
    print("macro_output.json gerado.")


if __name__ == "__main__":
    main()
