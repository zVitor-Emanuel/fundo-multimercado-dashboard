"""
calculate_pnl.py
================
Calcula P&L, NAV e drawdown do Kairos com CONTABILIDADE POR LOTES.

POR QUE LOTES (e não "fechar tudo e reabrir" a cada rebalanceamento)
---------------------------------------------------------------------
Numa versão anterior, cada rebalanceamento resetava o preço de entrada
de TODAS as posições daquele momento em diante — inclusive posições
que já existiam e só tiveram o peso aumentado. Isso está errado: se o
fundo já tinha 4% em Itaú desde agosto e comprou mais 4% em setembro,
o retorno da carteira precisa refletir DOIS lotes com preços de
entrada diferentes — não 8% comprados do zero em setembro.

Cada rebalanceamento em config/portfolio.json ainda é uma "foto" da
carteira-alvo naquele momento (peso total por ticker). O que muda é
COMO isso é interpretado:

  peso_novo > peso_anterior  -> LOTE NOVO com o incremento
                                 (o lote antigo continua intocado,
                                 com seu preço de entrada original)
  peso_novo < peso_anterior  -> venda parcial/total: reduz os lotes
                                 mais recentes primeiro (LIFO)
  peso_novo == peso_anterior -> nada muda

CAIXA
-----
Caixa não é um "lote" — é o dinheiro que não está alocado em NTN-B ou
ações (que exigem desembolso real). Ele entra/sai conforme lotes de
NTN-B/ações nascem (débito) ou são vendidos (crédito, incluindo o
ganho/perda realizado), e rende CDI sobre o que sobra a cada dia.

Futuros (DI, DOL, Treasury) não desembolsam caixa — o "ajuste diário"
deles é puro ganho/perda acumulado, sem consumir capital físico.

TIPOS DE ATIVO E FÓRMULA DE P&L (por lote)
--------------------------------------------
  di_future  -> ajuste diário B3 vs CDI
  ntnb       -> variação simples de PU (já líquida de cupom, ANBIMA)
  dol_future -> variação simples de preço, com roll de contrato
  (qualquer outro, ex: equity, global) -> preço + proventos + sinal
"""

import json
import math
from pathlib import Path
from datetime import datetime


# ========================================
# CONFIGURAÇÃO
# ========================================

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_FILE  = BASE_DIR / "config" / "portfolio.json"
HISTORY_FILE = BASE_DIR / "data"   / "history.json"
MACRO_FILE   = BASE_DIR / "data"   / "macro.json"
OUTPUT_FILE  = BASE_DIR / "data"   / "portfolio.json"


with open(CONFIG_FILE,  "r", encoding="utf-8") as f: config  = json.load(f)
with open(HISTORY_FILE, "r", encoding="utf-8") as f: history = json.load(f)
with open(MACRO_FILE,   "r", encoding="utf-8") as f: macro   = json.load(f)

FUND        = config["fund"]
START_DATE  = FUND["start_date"]
INITIAL_NAV = FUND["initial_nav"]

REBALANCES = sorted(config["rebalances"], key=lambda r: r["effective_date"])

print(f"Rebalanceamentos carregados: {len(REBALANCES)}")
for r in REBALANCES:
    pesos = sum(p["weight"] for p in r["positions"])
    print(f"  {r['effective_date']}  {r['label']:28} {len(r['positions'])} posições, {pesos:.0%} do PL")


SINAL_POSICAO = {"Aplicado": 1, "Comprado": 1, "Vendido": -1}

CONSOME_CAIXA_TIPOS = {"ntnb", "equity"}

EPS = 1e-9


# ========================================
# PROVENTOS (dividendos/JCP) — fontes: fatos relevantes / SEC 6-K oficiais
# ========================================

PROVENTOS = {
    "PETR4": [{"ex_date": "2026-08-24", "valor": 1.34814262}],
    "GGBR4": [{"ex_date": "2026-08-20", "valor": 0.23}],
}


def proventos_no_intervalo(ticker: str, de: str, ate: str) -> float:
    total = 0.0
    for p in PROVENTOS.get(ticker, []):
        if de <= p["ex_date"] <= ate:
            total += p["valor"]
    return total


# ========================================
# CALENDÁRIO DE DIAS ÚTEIS B3
# ========================================

def du_entre(d0: str, d1: str) -> int:
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
# CDI VIGENTE — forward-fill da série de Selic Meta
# ========================================

selic_series = macro["indicators"].get("selic_meta", {}).get("series", {})
_SELIC_FALLBACK = 0.1400


def cdi_vigente(data: str) -> float:
    if not selic_series:
        return _SELIC_FALLBACK
    datas_conhecidas = [d for d in selic_series if d <= data]
    if not datas_conhecidas:
        return selic_series[min(selic_series.keys())]
    return selic_series[max(datas_conhecidas)]


# ========================================
# HELPERS DE SÉRIE DE PREÇO
# ========================================

def _eh_fim_de_semana(data_str: str) -> bool:
    """
    True se a data cair em sábado ou domingo.

    Alguns ativos globais (ex: Treasury futuro na CME/Globex) têm
    pregão eletrônico que abre domingo à noite — dependendo da
    conversão de fuso, o primeiro candle pode ficar rotulado como
    domingo. B3 nunca negocia nesse dia, então qualquer data de
    fim de semana é descartada aqui, na fonte.
    """
    return datetime.strptime(data_str, "%Y-%m-%d").weekday() >= 5


def serie_precos(ticker: str) -> dict:
    asset = history["assets"].get(ticker)
    if asset is None:
        return {}
    return {
        d: p for d, p in sorted(asset["prices"].items())
        if p is not None and not _eh_fim_de_semana(d)
    }


def serie_contratos(ticker: str) -> dict:
    asset = history["assets"].get(ticker)
    if asset is None:
        return {}
    return asset.get("contracts", {})


def preco_ate(precos: dict, data: str, fallback=None):
    disponiveis = [d for d in precos if d <= data]
    if not disponiveis:
        return fallback
    return precos[max(disponiveis)]


def tipo_do_ticker(ticker: str) -> str:
    return history["assets"].get(ticker, {}).get("type", "desconhecido")


# ========================================
# RETORNO ACUMULADO DE UM TICKER, PARA UM CONJUNTO DE DATAS
# ========================================

def retorno_serie_di_futuro(ticker, entry_data, datas):
    precos = serie_precos(ticker)
    entry = precos.get(entry_data)
    if entry is None:
        return None

    resultado = {}
    pnl_acum_fracao = 0.0
    d_prev = entry_data

    for d in datas:
        if d == entry_data:
            resultado[d] = 0.0
            continue

        pu_t    = precos.get(d)
        pu_prev = precos.get(d_prev)

        if pu_t is None:
            resultado[d] = pnl_acum_fracao
            continue

        if pu_prev is None:
            resultado[d] = pnl_acum_fracao
            d_prev = d
            continue

        n   = du_entre(d_prev, d)
        cdi = cdi_vigente(d_prev)
        pnl_acum_fracao += (pu_t - pu_prev * (1 + cdi) ** (n / 252)) / entry

        resultado[d] = pnl_acum_fracao
        d_prev = d

    return resultado


def retorno_serie_dol_futuro(ticker, entry_data, datas, sinal):
    precos    = serie_precos(ticker)
    contratos = serie_contratos(ticker)
    entry = precos.get(entry_data)
    if entry is None:
        return None

    resultado = {}
    pnl_acum_fracao = 0.0
    d_prev = entry_data

    for d in datas:
        if d == entry_data:
            resultado[d] = 0.0
            continue

        preco_t    = precos.get(d)
        preco_prev = precos.get(d_prev)
        contrato_t    = contratos.get(d)
        contrato_prev = contratos.get(d_prev)

        if preco_t is None:
            resultado[d] = pnl_acum_fracao * sinal
            continue

        if preco_prev is None or (
            contrato_t and contrato_prev and contrato_t != contrato_prev
        ):
            resultado[d] = pnl_acum_fracao * sinal
            d_prev = d
            continue

        pnl_acum_fracao += (preco_t - preco_prev) / entry
        resultado[d] = pnl_acum_fracao * sinal
        d_prev = d

    return resultado


def retorno_serie_ntnb(ticker, entry_data, datas, sinal):
    precos = serie_precos(ticker)
    entry = precos.get(entry_data)
    if entry is None:
        return None

    resultado = {}
    for d in datas:
        atual = preco_ate(precos, d, fallback=entry)
        resultado[d] = sinal * ((atual / entry) - 1)
    return resultado


def retorno_serie_generico(ticker, entry_data, datas, sinal):
    """Ações e ativos globais (ex: Treasury): preço + proventos + sinal."""
    precos = serie_precos(ticker)
    entry = precos.get(entry_data)
    if entry is None:
        return None

    resultado = {}
    for d in datas:
        atual = preco_ate(precos, d, fallback=entry)
        provento = proventos_no_intervalo(ticker, entry_data, d)
        resultado[d] = sinal * (((atual + provento) / entry) - 1)
    return resultado


def calcular_retorno_serie(ticker, tipo, entry_data, datas, sinal):
    if tipo == "di_future":
        return retorno_serie_di_futuro(ticker, entry_data, datas)
    if tipo == "dol_future":
        return retorno_serie_dol_futuro(ticker, entry_data, datas, sinal)
    if tipo == "ntnb":
        return retorno_serie_ntnb(ticker, entry_data, datas, sinal)
    return retorno_serie_generico(ticker, entry_data, datas, sinal)


# ========================================
# TODAS AS DATAS DE PREGÃO DISPONÍVEIS
# ========================================

todas_as_datas = set()
for asset in history["assets"].values():
    todas_as_datas.update(
        d for d, p in asset["prices"].items()
        if p is not None and not _eh_fim_de_semana(d)
    )

todas_as_datas = sorted(d for d in todas_as_datas if d >= START_DATE)

if not todas_as_datas:
    raise RuntimeError("Nenhuma data de pregão encontrada em history.json.")


# ========================================
# MAPEAR CADA effective_date NOMINAL PRA UMA DATA DE PREGÃO REAL
# ========================================

data_real_do_rebalance = {}
for leg in REBALANCES:
    candidatos = [d for d in todas_as_datas if d >= leg["effective_date"]]
    data_real_do_rebalance[leg["effective_date"]] = (
        candidatos[0] if candidatos else leg["effective_date"]
    )


# ========================================
# CONSTRUIR OS LOTES — diffing de pesos entre rebalanceamentos
# consecutivos. Uma compra adicional gera lote novo; o lote antigo
# nunca tem seu preço de entrada alterado.
# ========================================

def construir_lotes():

    lotes = {}
    peso_anterior = {}
    contador_lotes = {}

    for leg in REBALANCES:
        data_nominal = leg["effective_date"]
        data_real    = data_real_do_rebalance[data_nominal]

        pesos_atuais = {}
        metadata     = {}
        for p in leg["positions"]:
            pesos_atuais[p["ticker"]] = p["weight"]
            metadata[p["ticker"]] = {
                "name": p["name"], "category": p["category"], "position": p["position"],
            }

        todos_tickers = set(peso_anterior) | set(pesos_atuais)

        for ticker in todos_tickers:
            peso_novo  = pesos_atuais.get(ticker, 0.0)
            peso_velho = peso_anterior.get(ticker, 0.0)
            delta = peso_novo - peso_velho

            if delta > EPS:
                contador_lotes[ticker] = contador_lotes.get(ticker, 0) + 1
                lotes.setdefault(ticker, []).append({
                    "entry_date": data_real,
                    "weight": delta,
                    "end_date": None,
                    "lote_num": contador_lotes[ticker],
                    **metadata[ticker],
                })

            elif delta < -EPS:
                a_reduzir = -delta
                for lote in reversed(lotes.get(ticker, [])):
                    if lote["end_date"] is not None:
                        continue
                    if a_reduzir <= EPS:
                        break
                    if lote["weight"] <= a_reduzir + EPS:
                        a_reduzir -= lote["weight"]
                        lote["end_date"] = data_real
                    else:
                        lote["weight"] -= a_reduzir
                        a_reduzir = 0.0

        peso_anterior = pesos_atuais

    return lotes


lotes_por_ticker = construir_lotes()

print("\nLotes construídos:")
for ticker, lista in lotes_por_ticker.items():
    for lote in lista:
        fim = lote["end_date"] or "ativo"
        print(f"  {ticker} lote {lote['lote_num']}: peso {lote['weight']:.2%}  "
              f"{lote['entry_date']} -> {fim}")


# ========================================
# PRÉ-COMPUTAR A SÉRIE DE RETORNO DE CADA LOTE
# ========================================

for ticker, lista in lotes_por_ticker.items():
    tipo = tipo_do_ticker(ticker)

    for lote in lista:
        datas_do_lote = [d for d in todas_as_datas if d >= lote["entry_date"]]
        sinal = SINAL_POSICAO.get(lote["position"], 1)

        serie = calcular_retorno_serie(ticker, tipo, lote["entry_date"], datas_do_lote, sinal)

        lote["_retorno_serie"] = serie if serie is not None else {}
        lote["_tipo"] = tipo
        lote["notional_reais"] = None


def retorno_do_lote_na_data(lote, d):
    """Retorno acumulado do lote na data d, travado no valor do end_date se já encerrado."""
    serie = lote["_retorno_serie"]
    if lote["end_date"] is not None and d >= lote["end_date"]:
        d_ref = max((x for x in serie if x < lote["end_date"]), default=None)
    else:
        d_ref = max((x for x in serie if x <= d), default=None)
    if d_ref is None:
        return 0.0
    return serie.get(d_ref, 0.0)


# ========================================
# LOOP DIA-A-DIA — computa NAV e daily_history
# ========================================

nav_history   = {}
daily_history = {}

caixa_pnl_acumulado  = 0.0
caixa_notional_livre = INITIAL_NAV

nav_ontem = INITIAL_NAV
d_prev = None

for d in todas_as_datas:

    # ── 1) nascimentos de HOJE: dimensiona notional com base no NAV de ontem ──
    for ticker, lista in lotes_por_ticker.items():
        for lote in lista:
            if lote["entry_date"] == d and lote["notional_reais"] is None:
                lote["notional_reais"] = lote["weight"] * nav_ontem
                if lote["_tipo"] in CONSOME_CAIXA_TIPOS:
                    caixa_notional_livre -= lote["notional_reais"]

    # ── 2) encerramentos de HOJE: devolve o valor final ao caixa ──
    for ticker, lista in lotes_por_ticker.items():
        for lote in lista:
            if lote["end_date"] == d and lote["_tipo"] in CONSOME_CAIXA_TIPOS:
                ret_final = retorno_do_lote_na_data(lote, d)
                valor_final = (lote["notional_reais"] or 0.0) * (1 + ret_final)
                caixa_notional_livre += valor_final

    # ── 3) CDI de hoje sobre o caixa livre (pós ajustes de hoje) ──
    if d_prev is not None:
        n   = du_entre(d_prev, d)
        cdi = cdi_vigente(d_prev)
        pnl_caixa_hoje = caixa_notional_livre * ((1 + cdi) ** (n / 252) - 1)
    else:
        pnl_caixa_hoje = 0.0
    caixa_pnl_acumulado += pnl_caixa_hoje

    # ── 4) soma o pnl acumulado de cada lote ──
    dia_detail = {}
    pnl_lotes_total = 0.0

    for ticker, lista in lotes_por_ticker.items():
        for lote in lista:
            if lote["notional_reais"] is None:
                continue
            if d < lote["entry_date"]:
                continue

            ret_atual = retorno_do_lote_na_data(lote, d)
            pnl_reais = lote["notional_reais"] * ret_atual
            pnl_lotes_total += pnl_reais

            precos = serie_precos(ticker)
            data_preco = min(d, lote["end_date"]) if lote["end_date"] else d
            preco_no_dia  = preco_ate(precos, data_preco, fallback=None)
            preco_entrada = precos.get(lote["entry_date"])

            chave = f'{ticker}#{lote["lote_num"]}' if lote["lote_num"] > 1 else ticker

            dia_detail[chave] = {
                "ticker_base": ticker,
                "lote_num": lote["lote_num"],
                "name": lote["name"], "category": lote["category"], "position": lote["position"],
                "weight": lote["weight"],
                "entry_date": lote["entry_date"], "end_date": lote["end_date"],
                "price": preco_no_dia,
                "entry_price": preco_entrada,
                "pnl": round(pnl_reais, 2),
                "return": ret_atual,
                "contribution": pnl_reais / INITIAL_NAV,
            }

    nav_hoje = INITIAL_NAV + caixa_pnl_acumulado + pnl_lotes_total

    dia_detail["CAIXA"] = {
        "ticker_base": "CAIXA",
        "name": "Caixa (CDI)", "category": "Caixa", "position": "Aplicado",
        "weight": (caixa_notional_livre / nav_hoje) if nav_hoje else 0.0,
        "price": None, "entry_price": None,
        "pnl": round(caixa_pnl_acumulado, 2),
        "return": (caixa_pnl_acumulado / INITIAL_NAV) if INITIAL_NAV else 0.0,
        "contribution": caixa_pnl_acumulado / INITIAL_NAV,
    }

    nav_history[d]   = round(nav_hoje, 2)
    daily_history[d] = dia_detail

    nav_ontem = nav_hoje
    d_prev = d


ultima_data = todas_as_datas[-1]


# ========================================
# CARTEIRA ATIVA (snapshot do dia mais recente, pro dashboard)
# ========================================

snap_final = daily_history[ultima_data]

leg_ativa = REBALANCES[0]
for leg in REBALANCES:
    if data_real_do_rebalance[leg["effective_date"]] <= ultima_data:
        leg_ativa = leg

results = []
covered_weight = 0.0
total_weight   = 0.0

for chave, snap in snap_final.items():
    if chave == "CAIXA":
        continue
    total_weight += snap["weight"]
    status = "OK" if snap["pnl"] is not None else "SEM DADOS"
    if status == "OK":
        covered_weight += snap["weight"]

    results.append({
        "ticker":        snap["ticker_base"],
        "lote":          snap["lote_num"],
        "name":          snap["name"] + (f" (lote {snap['lote_num']})" if snap["lote_num"] > 1 else ""),
        "category":      snap["category"],
        "position":      snap["position"],
        "weight":        snap["weight"],
        "entry_price":   snap["entry_price"],
        "current_price": snap["price"],
        "entry_date":    snap["entry_date"],
        "current_date":  ultima_data,
        "return":        snap["return"],
        "contribution":  snap["contribution"],
        "pnl":           snap["pnl"],
        "status":        status,
    })

caixa_snap = snap_final["CAIXA"]
results.append({
    "ticker": "CAIXA", "lote": 1, "name": "Caixa (CDI)", "category": "Caixa",
    "position": "Aplicado", "weight": caixa_snap["weight"],
    "entry_price": None, "current_price": None,
    "entry_date": START_DATE, "current_date": ultima_data,
    "return": caixa_snap["return"], "contribution": caixa_snap["contribution"],
    "pnl": caixa_snap["pnl"], "status": "OK",
})

portfolio_status = "COMPLETO" if abs(total_weight - covered_weight) < 1e-6 else "PARCIAL"

partial_nav    = nav_history[ultima_data]
partial_pnl    = partial_nav - INITIAL_NAV
partial_return = partial_pnl / INITIAL_NAV


# ========================================
# DRAWDOWN MÁXIMO
# ========================================

drawdown = 0.0
peak     = INITIAL_NAV
for d in sorted(nav_history):
    nav = nav_history[d]
    if nav > peak:
        peak = nav
    dd = (nav - peak) / peak
    if dd < drawdown:
        drawdown = dd


# ========================================
# SANITIZAR
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
    "timestamp":        datetime.now().isoformat(),
    "start_date":       START_DATE,
    "initial_nav":      INITIAL_NAV,
    "selic_serie":      selic_series,
    "covered_weight":   covered_weight,
    "missing_weight":   total_weight - covered_weight,
    "status":           portfolio_status,
    "partial_return":   partial_return,
    "partial_nav":      partial_nav,
    "partial_pnl":      partial_pnl,
    "drawdown":         drawdown,
    "active_leg":       leg_ativa["label"],
    "active_leg_since": data_real_do_rebalance[leg_ativa["effective_date"]],
    "nav_history":      nav_history,
    "daily_history":    daily_history,
    "positions":        results,
})

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(portfolio, f, indent=4, ensure_ascii=False, allow_nan=False)


# ========================================
# TERMINAL
# ========================================

print(f"\nPerna ativa: {leg_ativa['label']} (desde {data_real_do_rebalance[leg_ativa['effective_date']]})")
print(f"Status:           {portfolio_status}")
print(f"Retorno total:    {partial_return:+.4%}")
print(f"NAV atual:        R$ {partial_nav:,.2f}")
print(f"Drawdown máx:     {drawdown:.4%}")
print(f"Datas no NAV:     {len(nav_history)}  (desde {START_DATE} até {ultima_data})")
print()
for r in results:
    if r["status"] == "OK" and r["return"] is not None:
        print(f'{r["ticker"]:10} lote {r["lote"]}  {r["position"]:9} '
              f'entrada={r["entry_date"]}  ret={r["return"]:+.4%}  contrib={r["contribution"]:+.4%}')
    else:
        print(f'{r["ticker"]:10} {r["status"]}')
