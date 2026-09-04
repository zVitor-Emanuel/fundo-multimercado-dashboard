/* =========================================================
   KAIROS · FVS Capital — Dashboard
   ========================================================= */

let portfolioData   = null;
let macroOutputData = null;
let macroRawData    = null;


// ── rótulo de função por ticker ──────────────────────────
const FUNCAO_TESE = {
    DI1F27:   "Desinflação · curto prazo",
    DI1F31:   "Flexibilização monetária",
    NTNB2031: "Queda de juros reais",
    NTNB2050: "Compressão de prêmio longo",
    USD:      "Hedge fiscal / câmbio",
    GGBR4:    "Exposição dólar / EUA",
    PETR4:    "Proteção commodities",
    ITUB4:    "Qualidade · crédito",
    SBSP3:    "Infraestrutura · ESG",
    AXIA3:    "Infraestrutura · ESG",
    ELET6:    "Energia · ESG",
};

// ── indicadores que aparecem no Painel Macro ─────────────
const MACRO_DISPLAY = [
    { key: "selic_meta",   label: "Selic Meta",       fmt: "pct_anual" },
    { key: "ipca_mensal",  label: "IPCA (último mês)", fmt: "pct_mensal" },
    { key: "usd_brl",      label: "USD/BRL",           fmt: "brl" },
    { key: "di_jan27",     label: "DI Jan/27",         fmt: "pct_anual" },
    { key: "di_jan31",     label: "DI Jan/31",         fmt: "pct_anual" },
    { key: "ntnb_2031",    label: "NTN-B 2031",        fmt: "pct_anual" },
    { key: "ntnb_2050",    label: "NTN-B 2050",        fmt: "pct_anual" },
    { key: "brent",        label: "Brent (USD)",       fmt: "usd" },
    { key: "treasury_10y", label: "Treasury 10Y",      fmt: "pct_anual" },
    { key: "ibovespa",     label: "Ibovespa",          fmt: "pts" },
];

const CONFIRMA = ["ipca_mensal","di_jan27","di_jan31","ntnb_2031","selic_meta"];
const AMEACA   = ["brent","treasury_10y","usd_brl","ntnb_2050"];


/* =========================================================
   CARREGAR DADOS
   ========================================================= */

async function loadData() {
    try {
        const [portRes, macroOutRes, macroRawRes] = await Promise.all([
            fetch("data/portfolio.json"),
            fetch("data/macro_output.json"),
            fetch("data/macro.json"),
        ]);

        if (!portRes.ok)     throw new Error(`portfolio.json: ${portRes.status}`);
        if (!macroOutRes.ok) throw new Error(`macro_output.json: ${macroOutRes.status}`);
        if (!macroRawRes.ok) throw new Error(`macro.json: ${macroRawRes.status}`);

        portfolioData   = await portRes.json();
        macroOutputData = await macroOutRes.json();
        macroRawData    = await macroRawRes.json();

        initializeDashboard();

    } catch (err) {
        console.error("Erro ao carregar dados:", err);
        document.querySelector("main").insertAdjacentHTML(
            "afterbegin",
            `<div class="load-error">⚠ Erro ao carregar dados: ${err.message}</div>`
        );
    }
}


/* =========================================================
   INICIALIZAR
   ========================================================= */

function initializeDashboard() {
    renderHeader();
    renderPortfolio();
    renderTese();
    renderMacro();
    renderRisk();
    renderDate();

    renderAttribution();

    // gráficos — charts.js deve estar carregado antes de app.js
    if (typeof renderAllCharts === "function") {
        renderAllCharts(portfolioData, macroOutputData, macroRawData);
    }

    const total   = portfolioData.partial_return;
    const totalEl = document.getElementById("attribution-total");
    if (totalEl) {
        totalEl.textContent = fmtPct(total);
        totalEl.className   = total >= 0 ? "positive-text" : "negative-text";
    }
}


/* =========================================================
   HEADER
   ========================================================= */

function renderHeader() {
    const { partial_nav, partial_return, partial_pnl, start_date, drawdown } = portfolioData;

    setText("nav",       fmtBRL(partial_nav));
    setText("return",    fmtPct(partial_return));
    setText("daily-pnl", fmtBRL(partial_pnl));
    setText("drawdown",  drawdown != null ? fmtPct(drawdown) : "N/D");

    const d = new Date(start_date + "T00:00:00");
    setText("pnl-period", `desde ${d.toLocaleDateString("pt-BR")}`);

    const retEl = document.getElementById("return");
    if (retEl) retEl.className = partial_return >= 0 ? "positive-text" : "negative-text";

    const pnlEl = document.getElementById("daily-pnl");
    if (pnlEl) pnlEl.className = partial_pnl >= 0 ? "positive-text" : "negative-text";

    const ddEl = document.getElementById("drawdown");
    if (ddEl) ddEl.className = "negative-text";
}


/* =========================================================
   CARTEIRA
   ========================================================= */

function renderPortfolio() {
    const tbody = document.getElementById("portfolio-table");
    if (!tbody) return;

    tbody.innerHTML = "";

    portfolioData.positions.forEach(pos => {
        const ok  = pos.status === "OK";
        const cls = ok ? (pos.contribution >= 0 ? "positive-text" : "negative-text") : "";

        const row = document.createElement("tr");
        row.innerHTML = `
            <td><strong>${pos.name}</strong><br><small class="ticker-label">${pos.ticker}</small></td>
            <td>${pos.category}</td>
            <td>${pos.position}</td>
            <td>${(pos.weight * 100).toFixed(0)}%</td>
            <td class="mono">${ok ? fmtPreco(pos.ticker, pos.entry_price) : "—"}</td>
            <td class="mono">${ok ? fmtPreco(pos.ticker, pos.current_price) : "—"}</td>
            <td class="mono ${cls}">${ok ? fmtPct(pos.return) : "—"}</td>
            <td class="mono ${cls}">${ok ? fmtPct(pos.contribution) : "—"}</td>
            <td class="funcao-label">${FUNCAO_TESE[pos.ticker] || "—"}</td>
        `;
        tbody.appendChild(row);
    });
}


/* =========================================================
   ATTRIBUTION — barras HTML puras (sem canvas)
   ========================================================= */

function renderAttribution() {
    const container = document.getElementById("attribution-bars");
    if (!container) return;

    const positions = (portfolioData.positions || [])
        .filter(p => p.status === "OK")
        .sort((a, b) => b.contribution - a.contribution);

    const maxAbs = Math.max(...positions.map(p => Math.abs(p.contribution)));
    container.innerHTML = "";

    positions.forEach(pos => {
        const pct   = pos.contribution;
        const isPos = pct >= 0;
        const barW  = maxAbs > 0 ? Math.abs(pct) / maxAbs * 100 : 0;

        const row = document.createElement("div");
        row.className = "attr-row";
        row.innerHTML = `
            <div class="attr-label">${pos.name}</div>
            <div class="attr-bar-wrap">
                <div class="attr-bar ${isPos ? "attr-pos" : "attr-neg"}"
                     style="width:${barW.toFixed(1)}%"></div>
            </div>
            <div class="attr-value ${isPos ? "positive-text" : "negative-text"}">
                ${fmtPct(pct)}
            </div>
        `;
        container.appendChild(row);
    });
}


/* =========================================================
   TESE DO FUNDO
   ========================================================= */

function renderTese() {
    if (!macroOutputData) return;

    const score  = macroOutputData.tese_score;
    const status = macroOutputData.tese_status;

    setText("tese-score", score !== null ? Math.round(score) : "—");

    const bar = document.getElementById("score-bar");
    if (bar && score !== null) {
        bar.style.width      = `${score}%`;
        bar.style.background = corScore(score);
    }

    const badge = document.getElementById("tese-badge");
    if (badge) {
        badge.textContent = labelStatus(status);
        badge.className   = `badge badge-${status}`;
    }

    const ind  = macroOutputData.indicadores || {};
    const wrap = document.getElementById("tese-confirma-ameaca");
    if (!wrap) return;

    const confirmaHTML = CONFIRMA.map(k => {
        const i = ind[k]; if (!i || i.delta === null) return "";
        const fav = i.direcao_favoravel === "queda" ? i.delta < 0 : i.delta > 0;
        return `<span class="tese-chip ${fav ? "chip-ok" : "chip-warn"}">${i.label} ${fav ? "↓" : "↑"}</span>`;
    }).join("");

    const ameacaHTML = AMEACA.map(k => {
        const i = ind[k]; if (!i || i.delta === null) return "";
        const ameaca = i.direcao_favoravel === "queda" ? i.delta > 0 : i.delta < 0;
        return `<span class="tese-chip ${ameaca ? "chip-risk" : "chip-ok"}">${i.label} ${ameaca ? "↑" : "↓"}</span>`;
    }).join("");

    wrap.innerHTML = `
        <div class="tese-group"><span class="tese-group-label">Confirmam</span>${confirmaHTML}</div>
        <div class="tese-group"><span class="tese-group-label">Monitorar</span>${ameacaHTML}</div>
    `;
}


/* =========================================================
   PAINEL MACRO
   ========================================================= */

function renderMacro() {
    if (!macroOutputData) return;

    const ind  = macroOutputData.indicadores || {};
    const grid = document.getElementById("macro-grid");
    if (!grid) return;

    grid.innerHTML = "";

    MACRO_DISPLAY.forEach(({ key, label, fmt }) => {
        const i = ind[key];
        if (!i) return;

        const valor  = i.valor_atual;
        const delta  = i.delta;
        const status = i.sub_score !== null ? semaforo(i.sub_score / 10) : "cinza";

        const card = document.createElement("div");
        card.className = "macro-card";
        card.innerHTML = `
            <div class="macro-dot dot-${status}"></div>
            <span>${label}</span>
            <strong>${valor !== null ? fmtIndicador(valor, fmt) : "—"}</strong>
            <small class="${deltaClasse(delta, i.direcao_favoravel)}">${delta !== null ? fmtDelta(delta, fmt) : ""}</small>
            <div class="macro-date">${i.data_atual || ""}</div>
        `;
        grid.appendChild(card);
    });

    if (macroOutputData.timestamp) {
        const d = new Date(macroOutputData.timestamp);
        setText("macro-date", `Dados de ${d.toLocaleDateString("pt-BR")}`);
    }
}


/* =========================================================
   RISK MONITOR
   ========================================================= */

function renderRisk() {
    if (!macroOutputData) return;

    const fatores   = macroOutputData.fatores || {};
    const container = document.getElementById("risk-factors");
    if (!container) return;

    container.innerHTML = "";

    Object.values(fatores).forEach(fator => {
        const score = fator.score;
        const card  = document.createElement("div");
        card.className = `risk-card risk-${fator.status}`;
        card.innerHTML = `
            <div class="risk-header">
                <span class="risk-fator-label">${fator.label}</span>
                <span class="risk-semaforo">${emojiStatus(fator.status)}</span>
            </div>
            <div class="risk-score-num">${score !== null ? score.toFixed(1) : "—"}<small>/10</small></div>
            <div class="risk-bar-wrap">
                <div class="risk-bar-fill risk-bar-${fator.status}"
                     style="width:${score !== null ? score * 10 : 0}%"></div>
            </div>
            <div class="risk-status-label">${labelStatus(fator.status)}</div>
        `;
        container.appendChild(card);
    });

    const total       = macroOutputData.tese_score;
    const totalStatus = macroOutputData.tese_status;
    const totalDiv    = document.createElement("div");
    totalDiv.className = "risk-total";
    totalDiv.innerHTML = `
        <span>Tese Score total</span>
        <strong class="risk-total-score" style="color:${corScore(total)}">
            ${total !== null ? Math.round(total) : "—"}<small>/100</small>
        </strong>
        <span class="risk-total-label">${labelStatus(totalStatus)}</span>
    `;
    container.appendChild(totalDiv);
}


/* =========================================================
   DATA
   ========================================================= */

function renderDate() {
    const pos = portfolioData.positions.find(p => p.status === "OK");
    if (pos && pos.current_date) {
        const d = new Date(pos.current_date + "T00:00:00");
        setText("portfolio-date", `Data-base: ${d.toLocaleDateString("pt-BR")}`);
        setText("last-update",    `Última atualização: ${d.toLocaleDateString("pt-BR")}`);
    }
}


/* =========================================================
   FORMATAÇÃO
   ========================================================= */

function fmtBRL(v) {
    if (v == null || isNaN(v)) return "—";
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
}

function fmtPct(v) {
    if (v == null || isNaN(v)) return "—";
    return (v > 0 ? "+" : "") + (v * 100).toFixed(2).replace(".", ",") + "%";
}

function fmtIndicador(v, fmt) {
    if (v == null) return "—";
    switch (fmt) {
        case "pct_anual":  return (v * 100).toFixed(2).replace(".", ",") + "% a.a.";
        case "pct_mensal": return (v * 100).toFixed(2).replace(".", ",") + "% m.m.";
        case "brl":        return "R$ " + v.toFixed(4).replace(".", ",");
        case "usd":        return "US$ " + v.toFixed(2).replace(".", ",");
        case "pts":        return new Intl.NumberFormat("pt-BR").format(Math.round(v)) + " pts";
        default:           return v.toFixed(4);
    }
}

function fmtDelta(delta, fmt) {
    if (delta == null) return "";
    const sign = delta >= 0 ? "+" : "";
    switch (fmt) {
        case "pct_anual":
        case "pct_mensal":
            return sign + (delta * 10000).toFixed(1) + " bps";
        case "brl":
            return sign + "R$ " + delta.toFixed(4).replace(".", ",");
        case "usd":
            return sign + "US$ " + delta.toFixed(2).replace(".", ",");
        case "pts":
            return sign + new Intl.NumberFormat("pt-BR").format(Math.round(delta)) + " pts";
        default:
            return sign + delta.toFixed(4);
    }
}

function deltaClasse(delta, direcao) {
    if (delta == null) return "";
    return (direcao === "queda" ? delta < 0 : delta > 0) ? "positive-text" : "negative-text";
}

function fmtPreco(ticker, v) {
    if (v == null) return "—";
    if (["DI1F27","DI1F31","NTNB2031","NTNB2050"].includes(ticker))
        return "PU " + v.toFixed(2).replace(".", ",");
    if (ticker === "USD")
        return "R$ " + v.toFixed(4).replace(".", ",");
    return "R$ " + v.toFixed(2).replace(".", ",");
}

function corScore(score) {
    if (score == null) return "#555";
    if (score >= 65)   return "#4ade80";
    if (score >= 35)   return "#facc15";
    return "#f87171";
}

function semaforo(s) {
    if (s == null) return "cinza";
    if (s >= 0.65) return "verde";
    if (s >= 0.35) return "amarelo";
    return "vermelho";
}

function emojiStatus(s) {
    return { verde:"🟢", amarelo:"🟡", vermelho:"🔴", cinza:"⚪" }[s] || "⚪";
}

function labelStatus(s) {
    return { verde:"Favorável", amarelo:"Atenção", vermelho:"Tese ameaçada", cinza:"Sem dados" }[s] || s;
}

function setText(id, txt) {
    const el = document.getElementById(id);
    if (el) el.textContent = txt;
}


/* =========================================================
   START
   ========================================================= */

loadData();
