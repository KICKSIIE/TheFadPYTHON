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
