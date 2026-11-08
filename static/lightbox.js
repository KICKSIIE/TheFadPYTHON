/* Full-screen photo viewer. Any link with data-lightbox-urls (a JSON list of image URLs) and
   data-lightbox-index opens it. Without JavaScript the link just opens the image itself. */
(function () {
  "use strict";
  var dlg, img, count, prev, next, urls = [], idx = 0, label = "Photo", pushed = false;

  function build() {
    if (dlg) return;
    dlg = document.createElement("dialog");
    dlg.className = "lightbox";
    dlg.setAttribute("aria-label", "Photo viewer");
    dlg.innerHTML =
      '<div class="lb-stage">' +
      '<img class="lb-img" alt="">' +
      '</div>' +
      '<button type="button" class="lb-btn lb-close">\u2190 Back</button>' +
      '<button type="button" class="lb-btn lb-prev" aria-label="Previous photo">\u2039</button>' +
      '<button type="button" class="lb-btn lb-next" aria-label="Next photo">\u203A</button>' +
      '<p class="lb-count" aria-live="polite"></p>';
    document.body.appendChild(dlg);
    img = dlg.querySelector(".lb-img");
    count = dlg.querySelector(".lb-count");
    prev = dlg.querySelector(".lb-prev");
    next = dlg.querySelector(".lb-next");

    dlg.querySelector(".lb-close").addEventListener("click", close);
    prev.addEventListener("click", function () { show(idx - 1); });
    next.addEventListener("click", function () { show(idx + 1); });
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg || e.target.classList.contains("lb-stage")) close();
    });
    dlg.addEventListener("cancel", function (e) { e.preventDefault(); close(); });   // Esc key
    dlg.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { show(idx - 1); }
      else if (e.key === "ArrowRight") { show(idx + 1); }
    });
  }

  function show(i) {
    var n = urls.length;
    idx = ((i % n) + n) % n;
    img.src = urls[idx];
    img.alt = label + ", photo " + (idx + 1) + " of " + n;
    count.textContent = n > 1 ? (idx + 1) + " / " + n : "";
    prev.hidden = next.hidden = n < 2;
  }

  function open(list, i, name) {
    if (!list.length) return;
    urls = list;
    label = name || "Photo";
    build();
    show(i);
    if (!dlg.open) {
      dlg.showModal();
      history.pushState({ lightbox: 1 }, "");   // so the browser Back button closes the viewer
      pushed = true;
    }
  }

  function close() {
    if (pushed) { history.back(); }              // popstate below closes the dialog
    else if (dlg && dlg.open) { dlg.close(); }
  }

  window.addEventListener("popstate", function () {
    if (dlg && dlg.open) { pushed = false; dlg.close(); }
  });

  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("[data-lightbox-urls]") : null;
    if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var list;
    try { list = JSON.parse(a.getAttribute("data-lightbox-urls")); } catch (err) { return; }
    if (!window.HTMLDialogElement || !Array.isArray(list)) return;   // fall back to opening the image
    e.preventDefault();
    open(list, parseInt(a.getAttribute("data-lightbox-index") || "0", 10),
         a.getAttribute("data-lightbox-name"));
  });

  /* Product page: clicking a thumbnail swaps the big photo without reloading. */
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target.closest(".gallery-thumbs a[data-full]") : null;
    var main = document.getElementById("main-photo-link");
    if (!t || !main || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    var big = main.querySelector("img");
    big.src = t.getAttribute("data-full");
    main.href = t.getAttribute("data-full");
    main.setAttribute("data-lightbox-index", t.getAttribute("data-index"));
    var all = document.querySelectorAll(".gallery-thumbs a");
    for (var i = 0; i < all.length; i++) { all[i].classList.remove("on"); all[i].removeAttribute("aria-current"); }
    t.classList.add("on");
    t.setAttribute("aria-current", "true");
    history.replaceState(history.state, "", t.getAttribute("href"));
  });
})();
