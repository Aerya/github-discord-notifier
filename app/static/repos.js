(() => {
  const search = document.getElementById("repo-search");
  const rows = [...document.querySelectorAll(".repo-selection-row")];
  const selectors = [...document.querySelectorAll(".repo-selector")];
  const counter = document.getElementById("selection-counter");
  const visibleRows = () => rows.filter(row => row.style.display !== "none");
  const update = () => {
    const count = selectors.filter(input => input.checked).length;
    if (counter) counter.textContent = `${count} sélectionné${count > 1 ? "s" : ""}`;
    rows.forEach(row => {
      const input = row.querySelector(".repo-selector");
      const badge = row.querySelector(".repo-state");
      if (!input || !badge) return;
      badge.textContent = input.checked ? "Surveillé" : "Inactif";
      badge.classList.toggle("active", input.checked);
    });
  };
  search?.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    rows.forEach(row => row.style.display = row.dataset.name.includes(q) ? "" : "none");
  });
  document.getElementById("select-all")?.addEventListener("click", () => {
    visibleRows().forEach(row => { const input = row.querySelector(".repo-selector"); if (input) input.checked = true; });
    update();
  });
  document.getElementById("select-none")?.addEventListener("click", () => {
    visibleRows().forEach(row => { const input = row.querySelector(".repo-selector"); if (input) input.checked = false; });
    update();
  });
  selectors.forEach(input => input.addEventListener("change", update));
  update();
})();
