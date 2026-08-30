let portfolioData = null;
let marketData = null;
let historyData = null;
let macroData = null;


// ========================================
// CARREGAR DADOS
// ========================================

async function loadData() {

    try {

        const portfolioResponse =
            await fetch("config/portfolio.json");

        const marketResponse =
            await fetch("data/market.json");

        const historyResponse =
            await fetch("data/history.json");

        const macroResponse =
            await fetch("data/macro.json");


        portfolioData =
            await portfolioResponse.json();

        marketData =
            await marketResponse.json();

        historyData =
            await historyResponse.json();

        macroData =
            await macroResponse.json();


        initializeDashboard();

    } catch (error) {

        console.error(
            "Erro ao carregar dados:",
            error
        );

    }

}


// ========================================
// INICIALIZAR DASHBOARD
// ========================================

function initializeDashboard() {

    renderPortfolio();

    updateFundInfo();

    updateMacro();

    updateDate();

}


// ========================================
// CARTEIRA
// ========================================

function renderPortfolio() {

    const table =
        document.getElementById(
            "portfolio-table"
        );


    table.innerHTML = "";


    portfolioData.positions.forEach(
        asset => {

            const row =
                document.createElement("tr");


            row.innerHTML = `

                <td>

                    <strong>
                        ${asset.name}
                    </strong>

                    <br>

                    <small>
                        ${asset.ticker}
                    </small>

                </td>


                <td>
                    ${asset.category}
                </td>


                <td>
                    ${asset.position}
                </td>


                <td>
                    ${(asset.weight * 100).toFixed(0)}%
                </td>


                <td>
                    --
                </td>


                <td>

                    <span class="positive-text">
                        MONITORANDO
                    </span>

                </td>

            `;


            table.appendChild(row);

        }
    );

}


// ========================================
// INFORMAÇÕES DO FUNDO
// ========================================

function updateFundInfo() {

    const nav =
        portfolioData.fund.initial_nav;


    document.getElementById("nav")
        .textContent =
        formatCurrency(nav);


    document.getElementById("return")
        .textContent =
        "+0,00%";


    document.getElementById("daily-pnl")
        .textContent =
        formatCurrency(0);


    document.getElementById("drawdown")
        .textContent =
        "0,00%";

}


// ========================================
// MACRO
// ========================================

function updateMacro() {

    document.getElementById("inflation")
        .textContent = "--";

    document.getElementById("inflation-status")
        .textContent =
        "Aguardando dados";


    document.getElementById("selic")
        .textContent = "--";

    document.getElementById("selic-status")
        .textContent =
        "Aguardando dados";


    document.getElementById("usd")
        .textContent = "--";

    document.getElementById("usd-status")
        .textContent =
        "Aguardando dados";


    document.getElementById("brent")
        .textContent = "--";

    document.getElementById("brent-status")
        .textContent =
        "Aguardando dados";

}


// ========================================
// DATA
// ========================================

function updateDate() {

    const startDate =
        new Date(
            portfolioData.fund.start_date
        );


    const formattedStartDate =
        startDate.toLocaleDateString(
            "pt-BR"
        );


    document.getElementById(
        "portfolio-date"
    ).textContent =
        `Entrada: ${formattedStartDate}`;


    document.getElementById(
        "last-update"
    ).textContent =
        `Data-base: ${formattedStartDate}`;

}


// ========================================
// FORMATAÇÃO
// ========================================

function formatCurrency(value) {

    return new Intl.NumberFormat(
        "pt-BR",
        {
            style: "currency",
            currency: "BRL"
        }
    ).format(value);

}


// ========================================
// START
// ========================================

loadData();