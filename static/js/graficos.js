// Graficos dos paineis (Chart.js). Os dados chegam via json_script: {labels, valores, cores}.
(function () {
  const FONTE = "Inter, Segoe UI, sans-serif";

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
      data: { labels: d.labels, datasets: [{ data: d.valores, backgroundColor: d.cores, borderRadius: 6, maxBarThickness: 22 }] },
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

  // Todo <canvas data-grafico="id-dos-dados"> vira grafico de barras automaticamente
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("canvas[data-grafico]").forEach((c) => window.graficoBarras(c.id, c.dataset.grafico));
  });
})();
