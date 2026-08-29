const portfolio = [

    {
        ticker: "DI1F27",
        name: "DI Jan/27",
        category: "Juros",
        position: "Aplicado",
        weight: 20,
        pnl: 0.00
    },

    {
        ticker: "DI1F31",
        name: "DI Jan/31",
        category: "Juros",
        position: "Aplicado",
        weight: 10,
        pnl: 0.00
    },

    {
        ticker: "NTNB2031",
        name: "NTN-B 2031",
        category: "Inflação",
        position: "Aplicado",
        weight: 20,
        pnl: 0.00
    },

    {
        ticker: "NTNB2050",
        name: "NTN-B 2050",
        category: "Inflação",
        position: "Aplicado",
        weight: 10,
        pnl: 0.00
    },

    {
        ticker: "USD",
        name: "Dólar",
        category: "Câmbio",
        position: "Comprado",
        weight: 15,
        pnl: 0.00
    },

    {
        ticker: "GGBR4",
        name: "Gerdau",
        category: "Ações",
        position: "Comprado",
        weight: 9,
        pnl: 0.00
    },

    {
        ticker: "PETR4",
        name: "Petrobras",
        category: "Ações",
        position: "Comprado",
        weight: 4,
        pnl: 0.00
    },

    {
        ticker: "ITUB4",
        name: "Itaú",
        category: "Ações",
        position: "Comprado",
        weight: 4,
        pnl: 0.00
    },

    {
        ticker: "SBSP3",
        name: "Sabesp",
        category: "Ações",
        position: "Comprado",
        weight: 4,
        pnl: 0.00
    },

    {
        ticker: "AXIA",
        name: "AXIA Energia",
        category: "Ações",
        position: "Comprado",
        weight: 4,
        pnl: 0.00
    }

];


function renderPortfolio() {

    const table =
        document.getElementById("portfolio-table");


    table.innerHTML = "";


    portfolio.forEach(asset => {

        const row =
            document.createElement("tr");


        const pnlClass =
            asset.pnl >= 0
                ? "positive-text"
                : "warning-text";


        row.innerHTML = `

            <td>
                <strong>${asset.name}</strong>
                <br>
                <small>${asset.ticker}</small>
            </td>

            <td>${asset.category}</td>

            <td>${asset.position}</td>

            <td>${asset.weight.toFixed(0)}%</td>

            <td class="${pnlClass}">
                ${asset.pnl >= 0 ? "+" : ""}
                ${asset.pnl.toFixed(2)}%
            </td>

            <td>
                <span class="positive-text">
                    MONITORANDO
                </span>
            </td>

        `;


        table.appendChild(row);

    });

}


function updateMacro() {

    document.getElementById("inflation")
        .textContent = "4,64%";

    document.getElementById("inflation-status")
        .textContent = "Desaceleração";

    document.getElementById("selic")
        .textContent = "14,00%";

    document.getElementById("selic-status")
        .textContent = "Política restritiva";

    document.getElementById("usd")
        .textContent = "—";

    document.getElementById("usd-status")
        .textContent = "Aguardando dados";

    document.getElementById("brent")
        .textContent = "—";

    document.getElementById("brent-status")
        .textContent = "Aguardando dados";

}


function updateDate() {

    const now = new Date();


    const formatted =
        now.toLocaleString("pt-BR");


    document.getElementById("last-update")
        .textContent =
        `Última atualização: ${formatted}`;


    document.getElementById("portfolio-date")
        .textContent =
        `Atualização: ${formatted}`;

}


renderPortfolio();

updateMacro();

updateDate();