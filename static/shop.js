/* Catalog cards: hovering or focusing a color dot previews that color's photo. */
(function () {
  "use strict";
  function preview(e) {
    var dot = e.target.closest ? e.target.closest(".dot[data-img]") : null;
    if (!dot) return;
    var img = dot.closest(".card") && dot.closest(".card").querySelector(".card-img img");
    if (img && img.getAttribute("src") !== dot.getAttribute("data-img")) {
      img.setAttribute("src", dot.getAttribute("data-img"));
    }
  }
  // Catalog filters apply as soon as one is changed (the Apply button stays for no-JS use).
  document.addEventListener("change", function (e) {
    var form = e.target.closest ? e.target.closest(".filters") : null;
    if (form && e.target.form === form) { form.submit(); }
  });
  document.addEventListener("mouseover", preview);
  document.addEventListener("focusin", preview);
})();

(function () {
  "use strict";
  const input = document.querySelector("#shop-search");
  if (!input) return;
  const box = document.querySelector("#search-suggestions");
  const status = document.querySelector("#search-status");
  let timer, controller;
  function close() { box.hidden = true; input.setAttribute("aria-expanded", "false"); }
  input.addEventListener("input", function () {
    clearTimeout(timer);
    if (controller) controller.abort();
    const q = input.value.trim();
    close();
    if (q.length < 2) return;
    timer = setTimeout(async function () {
      controller = new AbortController();
      try {
        const params = new URLSearchParams({q: q, category: input.form.elements.category.value});
        const response = await fetch("/search-suggestions?" + params, {signal: controller.signal});
        if (!response.ok) throw new Error("unavailable");
        const rows = await response.json();
        if (input.value.trim() !== q) return;
        box.replaceChildren();
        rows.forEach(function (row) {
          const link = document.createElement("a"); link.href = row.url;
          const name = document.createElement("span"); name.textContent = row.name;
          const price = document.createElement("span"); price.textContent = "₱" + Number(row.price).toFixed(2);
          link.append(name, price); box.append(link);
        });
        if (!rows.length) { const p = document.createElement("p"); p.textContent = "No matching products. Try another name or color."; box.append(p); }
        status.textContent = rows.length + " product suggestions";
        box.hidden = false; input.setAttribute("aria-expanded", "true");
      } catch (error) { if (error.name !== "AbortError") status.textContent = "Suggestions unavailable. Press Search to try again."; }
    }, 180);
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape") close();
    if (event.key === "ArrowDown" && !box.hidden && box.querySelector("a")) { event.preventDefault(); box.querySelector("a").focus(); }
  });
  box.addEventListener("keydown", function (event) {
    const links = Array.from(box.querySelectorAll("a")), index = links.indexOf(document.activeElement);
    if (event.key === "Escape") { close(); input.focus(); }
    if (event.key === "ArrowDown") { event.preventDefault(); links[(index + 1) % links.length]?.focus(); }
    if (event.key === "ArrowUp") { event.preventDefault(); if (index <= 0) input.focus(); else links[index - 1].focus(); }
  });
  document.addEventListener("click", function (event) { if (!input.form.contains(event.target)) close(); });
  input.form.addEventListener("focusout", function () { setTimeout(function () { if (!input.form.contains(document.activeElement)) close(); }, 0); });
})();
