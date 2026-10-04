document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".formula").forEach(element => {
    if (window.katex) katex.render(element.textContent, element, {displayMode: true, throwOnError: false, trust: false, maxExpand: 1000});
  });
  document.querySelectorAll(".chart").forEach((element, index) => {
    const payload = document.getElementById(String(index + 1));
    if (window.Plotly && payload) {
      const figure = JSON.parse(JSON.parse(payload.textContent));
      Plotly.newPlot(element, figure.data, figure.layout, {responsive: true, displaylogo: false});
      const frame = document.createElement("section");
      frame.className = "chart-frame";
      element.before(frame);
      const controls = document.createElement("div");
      frame.append(controls, element);
      ["Full width", "Expand"].forEach(label => {
        const button = document.createElement("button");
        button.textContent = label;
        controls.append(button);
        button.addEventListener("click", () => {
          if (label === "Full width") {
            frame.classList.toggle("wide-chart");
            Plotly.Plots.resize(element);
          } else {
            const dialog = document.createElement("dialog");
            dialog.className = "chart-dialog";
            const close = document.createElement("button");
            close.textContent = "Close";
            dialog.append(close, element);
            document.body.append(dialog);
            dialog.showModal();
            element.style.height = "80vh";
            Plotly.relayout(element, {height: Math.floor(window.innerHeight * .8)});
            close.onclick = () => dialog.close();
            dialog.addEventListener("close", () => {
              frame.append(element);
              element.style.height = "";
              Plotly.relayout(element, {height: 360});
              Plotly.Plots.resize(element);
              dialog.remove();
              button.focus();
            });
            Plotly.Plots.resize(element);
          }
        });
      });
    }
  });
  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", event => { if (!confirm(form.dataset.confirm)) event.preventDefault(); });
  });
  const picker = document.getElementById("comparison-picker");
  if (picker) picker.addEventListener("submit", () => {
    picker.querySelector("[name=ids]").value = [...document.querySelectorAll(".run-picker:checked")].map(el => el.value).join(",");
  });
  document.querySelectorAll("[data-job-status]").forEach(element => {
    const poll = async () => {
      try {
        const response = await fetch(element.dataset.jobStatus);
        if (!response.ok) throw new Error("Unavailable");
        const value = await response.json();
        element.textContent = `${value.status}${value.health.worker?.available ? "" : " · worker unavailable"}`;
        if (["succeeded", "failed", "canceled"].includes(value.status)) location.reload();
        else setTimeout(poll, 2000);
      } catch (_) { element.textContent = "Unable to read job status. Refresh to retry."; }
    };
    poll();
  });
  document.querySelectorAll("table.sortable > tbody > tr:first-child > th").forEach((head, index) => {
    head.tabIndex = 0;
    head.title = "Sort by this column";
    const sort = () => {
      const body = head.closest("tbody");
      [...body.rows].slice(1).sort((a, b) => a.cells[index].textContent.localeCompare(b.cells[index].textContent, undefined, {numeric: true})).forEach(row => body.append(row));
    };
    head.onclick = sort;
    head.onkeydown = event => { if (event.key === "Enter") sort(); };
  });
});
