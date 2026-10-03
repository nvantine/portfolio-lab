document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".formula").forEach(element => {
    if (window.katex) katex.render(element.textContent, element, {displayMode: true, throwOnError: false, trust: false, maxExpand: 1000});
  });
  document.querySelectorAll(".chart").forEach((element, index) => {
    const payload = document.getElementById(String(index + 1));
    if (window.Plotly && payload) {
      const figure = JSON.parse(JSON.parse(payload.textContent));
      Plotly.newPlot(element, figure.data, figure.layout, {responsive: true, displaylogo: false});
    }
  });
});
