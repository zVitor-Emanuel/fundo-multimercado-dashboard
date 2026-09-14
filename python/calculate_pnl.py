"""
calculate_pnl.py
================
Calcula P&L, NAV e drawdown da carteira Kairos com a metodologia
correta por tipo de ativo:

  AÇÕES / FX (equity, fx)
  ────────────────────────
  Retorno simples de preço: (P_t / P_0) - 1

  DI FUTURO (di_future)
  ──────────────────────
  O contrato futuro de DI tem ajuste diário B3. Só ganha quem
  bate o CDI embutido. O P&L acumulado desde a entrada é:

      P&L = soma_diária [ PU_t - PU_{t-1} × (1 + CDI)^(DU/252) ]
                         × quantidade de contratos

  onde quantidade = (weight × NAV_inicial) / PU_entrada.

  O retorno reportado é P&L / (weight × NAV_inicial).

  CAIXA (parte do PL não alocada em NTN-B/ações)
  ────────────────────────────────────────────────
  DI futuro não consome caixa (apenas margem). NTN-B e ações
  consomem. O caixa sobrante rende CDI Meta a.a.:

      caixa = NAV_inicial × (1 - soma dos pesos que consomem caixa)
      rendimento_caixa = caixa × [ (1 + CDI)^(DU_total/252) - 1 ]

  NTN-B (ntnb)
  ─────────────
  O PU do pyield/ANBIMA já é PU_limpo × VNA (em R$). A variação
  de PU entre dois dias captura tanto a mudança de taxa quanto o
  crescimento diário do VNA pelo IPCA. Retorno simples de PU é
  correto.

  Cupom NTN-B 2050: 15/08/2026 era sábado → pago em 17/08 (D+1
  útil), que é exatamente START_DATE. O PU de 17/08 publicado
  pelo pyield/ANBIMA já está ex-cupom (pós-pagamento) — ou seja,
  o próprio PU_entrada já reflete o desconto do cupom. NÃO
  adicionamos nada extra: fazer isso conta o cupom duas vezes
  (bug identificado e corrigido em 13/09 comparando com o
  relatório oficial do Safra — a variação simples de PU bateu
  exatamente com o número oficial, sem qualquer ajuste de cupom).
"""

import json
import math
from datetime import datetime
from pathlib import Path


# ========================================
# CONFIGURAÇÃO
# ========================================

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_FILE  = BASE_DIR / "config" / "portfolio.json"
HISTORY_FILE = BASE_DIR / "data"   / "history.json"
MACRO_FILE   = BASE_DIR / "data"   / "macro.json"
OUTPUT_FILE  = BASE_DIR / "data"   / "portfolio.json"


# ========================================
# CARREGAR DADOS
# ========================================

with open(CONFIG_FILE,  "r", encoding="utf-8") as f: config  = json.load(f)
with open(HISTORY_FILE, "r", encoding="utf-8") as f: history = json.load(f)
with open(MACRO_FILE,   "r", encoding="utf-8") as f: macro   = json.load(f)

fund      = config["fund"]
positions = config["positions"]

START_DATE   = fund["start_date"]
INITIAL_NAV  = fund["initial_nav"]


# ========================================
# PROVENTOS (dividendos / JCP) declarados
# no período — usados para calcular RETORNO
# TOTAL das ações (preço + provento), não só
# variação de preço.
#
# Sem isso, o dia ex-provento mostra uma queda
# de preço sem nenhuma contrapartida — subestima
# o retorno real do acionista.
#
# Tratamento: o provento é creditado na data-ex
# (não na data de pagamento físico, que pode ser
# meses depois) — é quando o direito é adquirido
# e o preço da ação já desconta o valor.
#
# Fontes (fatos relevantes / SEC 6-K oficiais):
#  PETR4 — R$1,34814262/ação, data-base 21/08/2026,
#          ex-direito 24/08/2026. SEC Form 6-K
#          (pbrfs2q26rs_6k.htm), "Date of shareholder
#          position 08.21.2026, Total 1.34814262".
#  GGBR4 — R$0,23/ação, Record Date 08/19/2026,
#          Ex-Dividend Date 08/20/2026. SEC Form 6-K
#          (tm2621830d4_ex99-1.htm).
# ========================================

PROVENTOS = {
    "PETR4": [
        {"ex_date": "2026-08-24", "valor": 1.34814262},
    ],
    "GGBR4": [
        {"ex_date": "2026-08-20", "valor": 0.23},
    ],
}


def proventos_acumulados(ticker: str, ate_data: str) -> float:
    """Soma (R$/ação) de todos os proventos com data-ex <= ate_data."""
    total = 0.0
    for p in PROVENTOS.get(ticker, []):
        if p["ex_date"] <= ate_data:
            total += p["valor"]
    return total


# ========================================
# CDI Meta — série histórica do macro.json
# cdi_vigente(data) retorna a taxa em vigor
# naquela data (último valor conhecido até ela).
# ========================================

selic_series = macro["indicators"].get("selic_meta", {}).get("series", {})

# fallback se não há dado nenhum
_SELIC_FALLBACK = 0.1400

def cdi_vigente(data: str) -> float:
    """Retorna a Selic Meta vigente na data (forward-fill da série do BCB)."""
    if not selic_series:
        return _SELIC_FALLBACK
    datas_conhecidas = [d for d in selic_series if d <= data]
    if not datas_conhecidas:
        # antes do primeiro registro — usa o mais antigo disponível
        return selic_series[min(selic_series.keys())]
    return selic_series[max(datas_conhecidas)]

# Log das taxas vigentes no período
print("Selic Meta por período:")
datas_selic = sorted(selic_series.keys())
for i, d in enumerate(datas_selic):
    fim = datas_selic[i+1] if i+1 < len(datas_selic) else "→ hoje"
    print(f"  {d} {fim}: {selic_series[d]:.4%} a.a.")


# ========================================
# CALENDÁRIO — dias úteis B3
# ========================================

def du_entre(d0: str, d1: str) -> int:
    """Dias úteis B3 no intervalo (d0, d1], exclusive d0, inclusive d1."""
    import pandas as pd

    def pascoa(y):
        a=y%19;b=y//100;c=y%100;d=b//4;e=b%4;f=(b+8)//25;g=(b-f+1)//3
        h=(19*a+b-d-g+15)%30;i=c//4;k=c%4;l=(32+2*e+2*i-h-k)%7
        m=(a+11*h+22*l)//451;mo=(h+l-7*m+114)//31;da=(h+l-7*m+114)%31+1
        return pd.Timestamp(y,mo,da)

    feriados = set()
    for y in range(2026, 2032):
        p = pascoa(y)
        feriados |= {
            pd.Timestamp(y,1,1), pd.Timestamp(y,4,21), pd.Timestamp(y,5,1),
            pd.Timestamp(y,9,7), pd.Timestamp(y,10,12), pd.Timestamp(y,11,2),
            pd.Timestamp(y,11,15), pd.Timestamp(y,11,20), pd.Timestamp(y,12,25),
            p - pd.Timedelta(days=48), p - pd.Timedelta(days=47),
            p - pd.Timedelta(days=2),  p + pd.Timedelta(days=60),
        }

    days = pd.bdate_range(
        pd.Timestamp(d0) + pd.Timedelta(days=1),
        pd.Timestamp(d1)
    )
    return int(sum(1 for d in days if d not in feriados))


# ========================================
# ATIVOS QUE CONSOMEM CAIXA
# ========================================

# DI futuro: posição via margem, não desembolsa o notional
# NTN-B, ações e FX: consomem caixa
CONSOME_CAIXA = {"ntnb", "equity", "fx"}

peso_caixa = INITIAL_NAV
for pos in positions:
    asset_info = history["assets"].get(pos["ticker"])
    if asset_info and asset_info["type"] in CONSOME_CAIXA:
        peso_caixa -= pos["weight"] * INITIAL_NAV

peso_caixa = max(peso_caixa, 0.0)
print(f"Caixa inicial: R$ {peso_caixa:,.2f}")


# ========================================
# HELPER — ordena preços e retorna série
# ========================================

def serie_precos(ticker: str):
    """Retorna dict {data: preco} ordenado, apenas datas >= START_DATE."""
    asset = history["assets"].get(ticker)
    if asset is None:
        return {}
    return {
        d: p
        for d, p in sorted(asset["prices"].items())
        if d >= START_DATE and p is not None
    }


# ========================================
# P&L DO DI FUTURO — acumulado dia a dia
# ========================================

def pnl_di_futuro(ticker: str, weight: float):
    """
    Retorna (pnl_acumulado, retorno_sobre_notional).

    P&L_dia = (PU_t - PU_{t-1} × (1 + CDI)^(DU/252)) × qtd
    qtd = (weight × NAV) / PU_entrada
    """
    precos = serie_precos(ticker)
    if not precos:
        return None, None

    datas = sorted(precos.keys())
    pu_entrada = precos.get(START_DATE)
    if pu_entrada is None:
        return None, None

    notional     = weight * INITIAL_NAV
    qtd          = notional / pu_entrada
    pnl_acum     = 0.0
    data_anterior = START_DATE

    for data in datas:
        if data == START_DATE:
            continue

        pu_atual = precos[data]
        pu_prev  = precos.get(data_anterior)

        if pu_prev is None:
            data_anterior = data
            continue

        n  = du_entre(data_anterior, data)
        # taxa vigente no intervalo — usa a data anterior como referência
        cdi = cdi_vigente(data_anterior)
        fator_cdi = (1 + cdi) ** (n / 252)

        # excesso sobre CDI
        pnl_dia = qtd * (pu_atual - pu_prev * fator_cdi)
        pnl_acum += pnl_dia
        data_anterior = data

    retorno = pnl_acum / notional
    return pnl_acum, retorno


def serie_contratos(ticker: str):
    """Retorna dict {data: codigo_contrato} para ativos com roll (ex: DOL)."""
    asset = history["assets"].get(ticker)
    if asset is None:
        return {}
    return asset.get("contracts", {})


# ========================================
# P&L DO DOL FUTURO — com roll de contrato
# ========================================
#
# Diferente do DI1: o preço do DOL futuro NÃO é um fator de
# desconto (PU = notional/(1+i)^t) — é um preço a termo direto.
# Por isso o ajuste diário é a diferença simples entre os
# preços de ajuste consecutivos, sem correção de CDI.
#
# O contrato vence mensalmente (ver fetch_fixed_income.py).
# No dia do roll, NÃO comparamos o preço do contrato antigo
# com o novo (níveis diferentes só pela curva a termo) — a
# perna nova começa "do zero" a partir do primeiro preço
# publicado para ela, igual ao tratamento de dado ausente
# no DI/NTN-B.
#
# Quantidade fixa em START_DATE (mantém exposição em dólares
# constante ao longo dos rolls, sem re-basear no vencimento).

def pnl_dol_futuro(ticker: str, weight: float):
    """Retorna (pnl_acumulado, retorno_sobre_notional)."""
    precos    = serie_precos(ticker)
    contratos = serie_contratos(ticker)
    if not precos:
        return None, None

    datas = sorted(precos.keys())
    preco_entrada = precos.get(START_DATE)
    if preco_entrada is None:
        return None, None

    notional = weight * INITIAL_NAV
    qtd      = notional / preco_entrada
    pnl_acum = 0.0
    data_anterior = START_DATE

    for data in datas:
        if data == START_DATE:
            continue

        preco_atual = precos[data]
        preco_prev  = precos.get(data_anterior)

        contrato_atual = contratos.get(data)
        contrato_prev  = contratos.get(data_anterior)

        # roll de contrato: não compara preços de contratos diferentes
        if preco_prev is None or (
            contrato_atual and contrato_prev and contrato_atual != contrato_prev
        ):
            data_anterior = data
            continue

        pnl_acum += qtd * (preco_atual - preco_prev)
        data_anterior = data

    retorno = pnl_acum / notional
    return pnl_acum, retorno


# ========================================
# P&L NTN-B — variação simples de PU
# ========================================
# O PU do pyield/ANBIMA já embute VNA e já está ex-cupom nas
# datas em que houve pagamento (ver docstring do módulo).


def pnl_ntnb(ticker: str, weight: float):
    """
    Retorna (pnl_acumulado, retorno).

    Variação de PU é suficiente: o pyield entrega PU já
    ponderado pelo VNA e já líquido de cupons pagos.
    """
    precos = serie_precos(ticker)
    if not precos:
        return None, None

    pu_entrada = precos.get(START_DATE)
    if pu_entrada is None:
        return None, None

    notional = weight * INITIAL_NAV
    qtd      = notional / pu_entrada

    datas = sorted(precos.keys())
    pu_atual = precos[datas[-1]]

    pnl_total = qtd * (pu_atual - pu_entrada)
    retorno   = pnl_total / notional
    return pnl_total, retorno


# ========================================
# RENDIMENTO DO CAIXA
# ========================================

def rendimento_caixa():
    """
    CDI sobre o caixa desde START_DATE até a última data disponível.
    Acumula por sub-período para respeitar mudanças de taxa ao longo
    do tempo (ex: corte do Copom no meio do challenge).
    """
    todas_datas = []
    for pos in positions:
        p = serie_precos(pos["ticker"])
        if p:
            todas_datas.extend(p.keys())

    if not todas_datas:
        return 0.0, 0.0

    ultima_data = max(todas_datas)

    # quebra nos pontos de mudança da Selic + início + fim
    pontos = sorted({START_DATE, ultima_data} | {
        d for d in selic_series if START_DATE <= d <= ultima_data
    })

    fator_acum = 1.0
    for i in range(len(pontos) - 1):
        d0  = pontos[i]
        d1  = pontos[i + 1]
        n   = du_entre(d0, d1)
        cdi = cdi_vigente(d0)
        fator_acum *= (1 + cdi) ** (n / 252)

    ret = fator_acum - 1.0
    pnl = peso_caixa * ret
    return pnl, ret


# ========================================
# CALCULAR CADA POSIÇÃO
# ========================================

results       = []
total_pnl     = 0.0
covered_weight = 0.0


for position in positions:

    ticker   = position["ticker"]
    weight   = position["weight"]
    asset    = history["assets"].get(ticker)

    if asset is None:
        results.append({**position, "entry_price": None, "current_price": None,
                        "entry_date": START_DATE, "current_date": None,
                        "return": None, "contribution": None, "pnl": None,
                        "status": "SEM DADOS"})
        continue

    tipo   = asset["type"]
    precos = serie_precos(ticker)

    if not precos or START_DATE not in precos:
        results.append({**position, "entry_price": None, "current_price": None,
                        "entry_date": START_DATE, "current_date": None,
                        "return": None, "contribution": None, "pnl": None,
                        "status": "SEM PREÇO INICIAL"})
        continue

    entry_price   = precos[START_DATE]
    current_date  = max(precos.keys())
    current_price = precos[current_date]
    notional      = weight * INITIAL_NAV

    # ── P&L por tipo ──────────────────────────────────────
    if tipo == "di_future":
        pnl, ret = pnl_di_futuro(ticker, weight)
    elif tipo == "ntnb":
        pnl, ret = pnl_ntnb(ticker, weight)
    elif tipo == "dol_future":
        pnl, ret = pnl_dol_futuro(ticker, weight)
    else:
        # equity / fx — variação de preço + proventos (dividendo/JCP)
        # creditados na data-ex, mesmo que o pagamento físico seja depois
        provento = proventos_acumulados(ticker, current_date)
        ret = ((current_price + provento) / entry_price) - 1
        pnl = ret * notional

    if pnl is None or ret is None:
        results.append({**position, "entry_price": entry_price,
                        "current_price": current_price,
                        "entry_date": START_DATE, "current_date": current_date,
                        "return": None, "contribution": None, "pnl": None,
                        "status": "ERRO CÁLCULO"})
        continue

    contribution   = pnl / INITIAL_NAV
    total_pnl     += pnl
    covered_weight += weight

    results.append({
        "ticker":        ticker,
        "name":          position["name"],
        "category":      position["category"],
        "position":      position["position"],
        "weight":        weight,
        "entry_price":   entry_price,
        "current_price": current_price,
        "entry_date":    START_DATE,
        "current_date":  current_date,
        "return":        ret,
        "contribution":  contribution,
        "pnl":           pnl,
        "status":        "OK",
    })


# ── caixa ────────────────────────────────────────────────
caixa_pnl, caixa_ret = rendimento_caixa()
total_pnl += caixa_pnl
caixa_contribution = caixa_pnl / INITIAL_NAV

results.append({
    "ticker":        "CAIXA",
    "name":          "Caixa (CDI)",
    "category":      "Caixa",
    "position":      "Aplicado",
    "weight":        peso_caixa / INITIAL_NAV,
    "entry_price":   None,
    "current_price": None,
    "entry_date":    START_DATE,
    "current_date":  None,
    "return":        caixa_ret,
    "contribution":  caixa_contribution,
    "pnl":           caixa_pnl,
    "status":        "OK",
})

print(f"Rendimento caixa: {caixa_ret:+.4%}  P&L R$ {caixa_pnl:,.2f}")


# ========================================
# NAV E RETORNO TOTAL
# ========================================

total_weight = sum(p["weight"] for p in positions)
missing_weight = total_weight - covered_weight
portfolio_status = "COMPLETO" if covered_weight == total_weight else "PARCIAL"

partial_nav    = INITIAL_NAV + total_pnl
partial_return = total_pnl / INITIAL_NAV
partial_pnl    = total_pnl


# ========================================
# NAV HISTÓRICO DIÁRIO
# Para cada data de pregão, reconstrói o
# NAV com a metodologia correta por tipo.
# ========================================

all_dates = set()
for pos in positions:
    p = serie_precos(pos["ticker"])
    all_dates.update(p.keys())

all_dates = sorted(all_dates)
nav_history = {}

# histórico diário completo: {data: {ticker: {price, pnl, return, contribution}}}
daily_history = {}

for data_alvo in all_dates:

    nav_dia   = INITIAL_NAV
    dia_detail = {}   # detalhes de cada posição nesta data

    # ── caixa ──────────────────────────────────────────────
    pontos_caixa = sorted({START_DATE, data_alvo} | {
        d for d in selic_series if START_DATE <= d <= data_alvo
    })
    fator_caixa = 1.0
    for i in range(len(pontos_caixa) - 1):
        d0 = pontos_caixa[i]
        d1 = pontos_caixa[i + 1]
        n_sub = du_entre(d0, d1)
        fator_caixa *= (1 + cdi_vigente(d0)) ** (n_sub / 252)

    caixa_pnl_dia  = peso_caixa * (fator_caixa - 1.0)
    caixa_ret_dia  = fator_caixa - 1.0
    nav_dia       += caixa_pnl_dia

    dia_detail["CAIXA"] = {
        "price":        None,
        "entry_price":  None,
        "pnl":          round(caixa_pnl_dia, 2),
        "return":       caixa_ret_dia,
        "contribution": caixa_pnl_dia / INITIAL_NAV,
    }

    for pos in positions:
        ticker = pos["ticker"]
        weight = pos["weight"]
        asset  = history["assets"].get(ticker)
        if asset is None:
            continue

        tipo   = asset["type"]
        precos = serie_precos(ticker)
        pu0    = precos.get(START_DATE)
        if pu0 is None:
            continue

        notional = weight * INITIAL_NAV
        qtd      = notional / pu0

        if tipo == "di_future":
            datas_ativo = sorted(d for d in precos if d <= data_alvo)
            pnl_acum = 0.0
            d_prev = START_DATE
            for d in datas_ativo:
                if d == START_DATE:
                    continue
                pu_t    = precos.get(d)
                pu_prev = precos.get(d_prev)
                if pu_t is None or pu_prev is None:
                    d_prev = d
                    continue
                n   = du_entre(d_prev, d)
                cdi = cdi_vigente(d_prev)
                pnl_acum += qtd * (pu_t - pu_prev * (1 + cdi) ** (n / 252))
                d_prev = d
            nav_dia += pnl_acum
            pu_atual = precos.get(max(d for d in precos if d <= data_alvo), pu0)
            dia_detail[ticker] = {
                "price":        pu_atual,
                "entry_price":  pu0,
                "pnl":          round(pnl_acum, 2),
                "return":       pnl_acum / notional,
                "contribution": pnl_acum / INITIAL_NAV,
            }

        elif tipo == "ntnb":
            datas_ativo = sorted(d for d in precos if d <= data_alvo)
            if not datas_ativo:
                continue
            pu_t = precos[datas_ativo[-1]]
            pnl  = qtd * (pu_t - pu0)
            nav_dia += pnl
            dia_detail[ticker] = {
                "price":        pu_t,
                "entry_price":  pu0,
                "pnl":          round(pnl, 2),
                "return":       pnl / notional,
                "contribution": pnl / INITIAL_NAV,
            }

        elif tipo == "dol_future":
            contratos_ativo = serie_contratos(ticker)
            datas_ativo = sorted(d for d in precos if d <= data_alvo)
            pnl_acum = 0.0
            d_prev = START_DATE
            for d in datas_ativo:
                if d == START_DATE:
                    continue
                preco_t    = precos.get(d)
                preco_prev = precos.get(d_prev)
                contrato_t    = contratos_ativo.get(d)
                contrato_prev = contratos_ativo.get(d_prev)
                if preco_t is None or preco_prev is None or (
                    contrato_t and contrato_prev and contrato_t != contrato_prev
                ):
                    d_prev = d
                    continue
                pnl_acum += qtd * (preco_t - preco_prev)
                d_prev = d
            nav_dia += pnl_acum
            preco_atual = precos.get(max(d for d in precos if d <= data_alvo), pu0)
            dia_detail[ticker] = {
                "price":        preco_atual,
                "entry_price":  pu0,
                "pnl":          round(pnl_acum, 2),
                "return":       pnl_acum / notional,
                "contribution": pnl_acum / INITIAL_NAV,
            }

        else:
            datas_ativo = sorted(d for d in precos if d <= data_alvo)
            if not datas_ativo:
                continue
            pu_t     = precos[datas_ativo[-1]]
            provento = proventos_acumulados(ticker, data_alvo)
            ret_t    = ((pu_t + provento) / pu0) - 1
            pnl      = notional * ret_t
            nav_dia += pnl
            dia_detail[ticker] = {
                "price":        pu_t,
                "entry_price":  pu0,
                "pnl":          round(pnl, 2),
                "return":       ret_t,
                "contribution": pnl / INITIAL_NAV,
            }

    nav_history[data_alvo]  = round(nav_dia, 2)
    daily_history[data_alvo] = dia_detail


# ========================================
# DRAWDOWN MÁXIMO
# ========================================

drawdown = 0.0
peak     = INITIAL_NAV

for data in sorted(nav_history):
    nav = nav_history[data]
    if nav > peak:
        peak = nav
    dd = (nav - peak) / peak
    if dd < drawdown:
        drawdown = dd


# ========================================
# SANITIZAR — NaN/Inf não são JSON válidos
# ========================================

def sanitize(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


# ========================================
# OUTPUT
# ========================================

portfolio = sanitize({
    "timestamp":      datetime.now().isoformat(),
    "start_date":     START_DATE,
    "initial_nav":    INITIAL_NAV,
    "selic_serie":    selic_series,
    "covered_weight": covered_weight,
    "missing_weight": missing_weight,
    "status":         portfolio_status,
    "partial_return": partial_return,
    "partial_nav":    partial_nav,
    "partial_pnl":    partial_pnl,
    "drawdown":       drawdown,
    "nav_history":    nav_history,
    "daily_history":  daily_history,
    "positions":      results,
})

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(portfolio, f, indent=4, ensure_ascii=False, allow_nan=False)


# ========================================
# TERMINAL
# ========================================

print()
print(f"Status:           {portfolio_status}")
print(f"Caixa inicial:    R$ {peso_caixa:,.2f}")
print()
print(f"Retorno parcial:  {partial_return:+.4%}")
print(f"NAV parcial:      R$ {partial_nav:,.2f}")
print(f"P&L parcial:      R$ {partial_pnl:,.2f}")
print(f"Drawdown máx:     {drawdown:.4%}")
print(f"Datas no NAV:     {len(nav_history)}")
print()
for r in results:
    if r["status"] == "OK" and r["return"] is not None:
        print(f'{r["ticker"]:12} ret={r["return"]:+.4%}  contrib={r["contribution"]:+.4%}')
    else:
        print(f'{r["ticker"]:12} {r["status"]}')
