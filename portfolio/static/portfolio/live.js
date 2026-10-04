// Refresh server-rendered lists, leaving the user's editable forms untouched.
function applyLivePage(page) {
  document.querySelectorAll("[data-live-region]").forEach(region => {
    const incoming = page.querySelector(`[data-live-region="${region.dataset.liveRegion}"]`);
    if (!incoming) throw new Error("Missing page region");
    const open = new Set([...region.querySelectorAll("details[id][open]")].map(el => el.id));
    const checked = new Set([...region.querySelectorAll("input[id]:checked")].map(el => el.id));
    region.innerHTML = incoming.innerHTML;
    region.querySelectorAll("details[id]").forEach(el => { el.open = open.has(el.id); });
    region.querySelectorAll("input[id]").forEach(el => { if (el.type === "checkbox") el.checked = checked.has(el.id); });
  });
  document.querySelectorAll("select[data-live-options]").forEach(select => {
    const incoming = page.getElementById(select.id);
    if (!incoming || select === document.activeElement) return;
    const selected = select.value;
    select.innerHTML = incoming.innerHTML;
    if ([...select.options].some(option => option.value === selected)) select.value = selected;
  });
}

function startLivePage(root) {
  const feedback = document.querySelector("[data-live-feedback]");
  const poll = async () => {
    try {
      if (document.hidden) return;
      const response = await fetch(root.dataset.liveStatus, {cache: "no-store"});
      if (!response.ok || response.redirected) throw new Error("Session or service unavailable");
      const state = await response.json();
      // Avoid replacing a control while the user is interacting with it.
      const busy = document.activeElement?.closest("[data-live-region], select[data-live-options]");
      if (state.revision !== root.dataset.liveRevision && !busy) {
        const refreshed = await fetch(window.location.href, {cache: "no-store"});
        if (!refreshed.ok || refreshed.redirected) throw new Error("Session or service unavailable");
        const page = new DOMParser().parseFromString(await refreshed.text(), "text/html");
        const incoming = page.querySelector("[data-live-status]");
        if (!incoming) throw new Error("Page unavailable");
        if (document.activeElement?.closest("[data-live-region], select[data-live-options]")) return;
        applyLivePage(page);
        root.dataset.liveRevision = incoming.dataset.liveRevision;
      }
      if (feedback) feedback.textContent = state.worker?.available
        ? "Up to date · watching for changes automatically."
        : "Queue worker unavailable · watching for changes. Start the app services or run uv run portfolio-lab jobs work.";
    } catch (_) {
      if (feedback) feedback.textContent = "Update connection interrupted. Retrying automatically; your form has been kept.";
    } finally {
      setTimeout(poll, 2000);
    }
  };
  poll();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-live-status]").forEach(startLivePage);
  document.getElementById("dataset-errors")?.focus();
});
