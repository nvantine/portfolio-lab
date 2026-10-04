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
            dialog.setAttribute("aria-label", figure.layout.title?.text || "Expanded chart");
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
  let syncing = false;
  document.querySelectorAll(".chart").forEach(element => {
    // newPlot is asynchronous; attach handlers after rendering is complete.
    const attach = () => {
      if (!element.on) { setTimeout(attach, 100); return; }
      element.on("plotly_relayout", event => {
        if (syncing || !element.layout?.meta?.sync_time) return;
        let update;
        if (event["xaxis.range[0]"] !== undefined) update = {"xaxis.range": [event["xaxis.range[0]"], event["xaxis.range[1]"]]};
        else if (event["xaxis.autorange"]) update = {"xaxis.autorange": true};
        else return;
        syncing = true;
        Promise.all([...document.querySelectorAll(".chart")].filter(other => other !== element && other.layout?.meta?.sync_time).map(other => Plotly.relayout(other, update))).finally(() => { syncing = false; });
      });
    };
    if (window.Plotly) attach();
  });
  document.addEventListener("submit", event => {
    const form = event.target;
    if (form.matches("form[data-confirm]") && !confirm(form.dataset.confirm)) event.preventDefault();
  });
  const picker = document.getElementById("comparison-picker");
  if (picker) picker.addEventListener("submit", () => {
    picker.querySelector("[name=ids]").value = [...document.querySelectorAll(".run-picker:checked")].map(el => el.value).join(",");
  });
  document.querySelectorAll("[data-job-status]").forEach(element => {
    const poll = async () => {
      try {
        const response = await fetch(element.dataset.jobStatus, {cache: "no-store"});
        if (!response.ok || response.redirected) throw new Error("Unavailable");
        const value = await response.json();
        element.textContent = `${value.status}${value.health?.worker?.available ? "" : " · worker unavailable"}`;
        if (["succeeded", "failed", "canceled"].includes(value.status)) {
          window.location.replace(window.location.href);
          return;
        }
      } catch (_) { element.textContent = "Unable to read job status. Retrying automatically…"; }
      setTimeout(poll, 2000);
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
