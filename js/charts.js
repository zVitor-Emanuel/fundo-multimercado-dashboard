/* =========================================================
   KAIROS · FVS Capital — Gráficos
   Ativo: apenas NAV (linha).
   Os demais (DI, NTN-B, radar) foram desativados temporariamente.
   ========================================================= */

const _charts = {};

function destroyChart(id) {
    if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
}

// ── paleta ──────────────────────────────────────────────
const AZUL      = "#60a5fa";
const GRID_COLOR = "rgba(37,41,50,0.8)";
const TICK_COLOR = "#5a6272";

Chart.defaults.color                           = TICK_COLOR;
Chart.defaults.font.family                     = "Arial, Helvetica, sans-serif";
Chart.defaults.font.size                       = 11;
Chart.defaults.plugins.legend.labels.color    = "#9299a5";
Chart.defaults.plugins.legend.labels.boxWidth = 10;
Chart.defaults.plugins.tooltip.backgroundColor = "#1e222a";
Chart.defaults.plugins.tooltip.borderColor     = "#2d3340";
Chart.defaults.plugins.tooltip.borderWidth     = 1;
Chart.defaults.plugins.tooltip.titleColor      = "#e8eaed";
Chart.defaults.plugins.tooltip.bodyColor       = "#9299a5";


/* =========================================================
   NAV DO FUNDO
   ========================================================= */

function renderNavChart(portfolioData) {
    const nav_history = portfolioData.nav_history || {};
    const initial_nav = portfolioData.initial_nav;

    const dates  = Object.keys(nav_history).sort();
    const values = dates.map(d => nav_history[d]);
    const baseline = dates.map(() => initial_nav);

    destroyChart("navChart");

    const ctx = document.getElementById("navChart");
    if (!ctx) return;

    _charts["navChart"] = new Chart(ctx, {
        type: "line",
        data: {
            labels: dates.map(d => { const [,m,day] = d.split("-"); return `${day}/${m}`; }),
            datasets: [
                {
                    label: "Kairos FIM",
                    data: values,
                    borderColor: AZUL,
                    backgroundColor: "rgba(96,165,250,0.08)",
                    borderWidth: 2,
                    pointRadius: 3,
                    pointBackgroundColor: AZUL,
                    fill: true,
                    tension: 0.3,
                },
                {
                    label: "Base (R$100k)",
                    data: baseline,
                    borderColor: GRID_COLOR,
                    borderWidth: 1,
                    borderDash: [4, 4],
                    pointRadius: 0,
                    fill: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            scales: {
                x: {
                    grid: { color: GRID_COLOR },
                    ticks: { maxTicksLimit: 8 },
                },
                y: {
                    grid: { color: GRID_COLOR },
                    ticks: {
                        callback: v => "R$ " + new Intl.NumberFormat("pt-BR").format(Math.round(v)),
                    },
                },
            },
            plugins: {
                legend: { position: "top" },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const v = ctx.parsed.y;
                            return ` ${ctx.dataset.label}: R$ ${new Intl.NumberFormat("pt-BR").format(Math.round(v))}`;
                        },
                    },
                },
            },
        },
    });
}


/* =========================================================
   ENTRY POINT — chamado pelo app.js
   ========================================================= */

function renderAllCharts(portfolioData, macroOutputData, macroRaw) {
    renderNavChart(portfolioData);
    // renderDiChart, renderNtnbChart, renderRadarChart, renderAttributionChart
    // desativados — canvas causava overflow; reativar quando o layout estiver pronto
}
