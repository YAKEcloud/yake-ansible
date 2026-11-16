document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("pre > code, .md-typeset__scrollwrap").forEach((el) => el.setAttribute("tabindex", "0"));
  document.querySelectorAll(".md-tabs__item--active > a").forEach((a) => a.setAttribute("aria-current", "true"));
  document.querySelectorAll("a.md-nav__link--active").forEach((a) => a.setAttribute("aria-current", "page"));
  document.querySelectorAll("[data-year]").forEach((el) => (el.textContent = new Date().getFullYear()));
});
