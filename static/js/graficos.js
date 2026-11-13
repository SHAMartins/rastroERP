// Graficos dos paineis (Chart.js). Os dados chegam via json_script: {labels, valores, cores}.
(function () {
  const FONTE = "Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif";

  function dados(id) {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  }

  // Barras horizontais: comparar status e categorias lado a lado
  window.graficoBarras = function (canvasId, dadosId) {
    const d = dados(dadosId);
    const canvas = document.getElementById(canvasId);
    if (!d || !canvas) return;
    new Chart(canvas, {
      type: "bar",
      data: { labels: d.labels, datasets: [{ data: d.valores, backgroundColor: d.cores, borderRadius: 2, maxBarThickness: 18 }] },
      options: {
        indexAxis: "y", maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, ticks: { precision: 0, font: { family: FONTE } }, grid: { color: "#eef2f6" } },
          y: { ticks: { font: { family: FONTE } }, grid: { display: false } },
        },
      },
    });
  };

  // Barras + linhas no tempo (evolucao semanal). Dados: {labels, series: [{nome, tipo, cor, valores, eixo}],
  // eixo_porcentagem}. Serie com eixo "porcentagem" usa o eixo da direita, de 0 a 100%.
  window.graficoCombinado = function (canvasId, dadosId) {
    const d = dados(dadosId);
    const canvas = document.getElementById(canvasId);
    if (!d || !canvas) return;
    const escalas = {
      x: { ticks: { font: { family: FONTE } }, grid: { display: false } },
      y: { beginAtZero: true, ticks: { precision: 0, font: { family: FONTE } }, grid: { color: "#eef2f6" } },
    };
    if (d.eixo_porcentagem) {
      escalas.porcentagem = { position: "right", min: 0, max: 100, grid: { display: false },
                              ticks: { callback: (v) => `${v}%`, font: { family: FONTE } } };
    }
    new Chart(canvas, {
      data: {
        labels: d.labels,
        datasets: d.series.map((s) => ({
          type: s.tipo, label: s.nome, data: s.valores, yAxisID: s.eixo || "y",
          backgroundColor: s.cor, borderColor: s.cor, borderRadius: 2, maxBarThickness: 16,
          tension: 0, spanGaps: true, pointRadius: 2.5,   // linha reta: nao inventa valores entre as semanas (Tufte)
        })),
      },
      options: {
        maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom", labels: { font: { family: FONTE }, boxWidth: 12 } } },
        scales: escalas,
      },
    });
  };

  // <canvas data-grafico="id-dos-dados"> vira grafico de barras; com data-grafico-tipo="combinado", barras + linhas
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("canvas[data-grafico]").forEach((c) => {
      const desenhar = c.dataset.graficoTipo === "combinado" ? window.graficoCombinado : window.graficoBarras;
      desenhar(c.id, c.dataset.grafico);
    });
  });
})();
