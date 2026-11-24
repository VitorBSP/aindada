"use strict";

/* Tema claro/escuro (REDESIGN_SPEC T4, §1.1). O escuro é o padrão; a escolha do visitante fica só neste aparelho
   (localStorage) e vale para os sites de todas as competições, que carregam este arquivo no <head> para aplicar o
   tema antes da primeira pintura. A assinatura do cabeçalho troca sozinha pelo CSS (.logo-dark / .logo-light). */
(function () {
  const KEY = "ainda-da:tema";
  const COLORS = { dark: "#17191c", light: "#fafaf7" };
  const root = document.documentElement;

  const saved = () => {
    try { return window.localStorage.getItem(KEY); } catch (error) { return null; }
  };
  const current = () => (root.dataset.theme === "light" ? "light" : "dark");

  function apply(theme) {
    root.dataset.theme = theme;
    document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
      meta.setAttribute("content", COLORS[theme]);
      meta.removeAttribute("media");
    });
    const button = document.querySelector(".theme-toggle");
    if (button) {
      const toLight = theme === "dark";
      button.setAttribute("aria-label", toLight ? "Usar tema claro" : "Usar tema escuro");
      button.setAttribute("title", toLight ? "Tema claro" : "Tema escuro");
      button.innerHTML = toLight ? SUN : MOON;
    }
  }

  const ICON = (body) => `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
  const SUN = ICON('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>');
  const MOON = ICON('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>');

  root.dataset.theme = saved() === "light" ? "light" : "dark";

  function mount() {
    const inner = document.querySelector(".masthead-inner");
    if (!inner || inner.querySelector(".theme-toggle")) return;
    let tools = inner.querySelector(".masthead-tools");
    if (!tools) {
      tools = document.createElement("div");
      tools.className = "masthead-tools";
      const brand = inner.querySelector(".brand");
      if (brand) brand.after(tools); else inner.prepend(tools);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "theme-toggle";
    button.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      try { window.localStorage.setItem(KEY, next); } catch (error) { /* sem armazenamento: vale só nesta visita */ }
      apply(next);
    });
    tools.append(button);
    apply(current());
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
  window.addEventListener("storage", (event) => { if (event.key === KEY) apply(event.newValue === "light" ? "light" : "dark"); });
})();
