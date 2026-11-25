"use strict";

/* Cabeçalho de um andar e folhas inferiores (REDESIGN_SPEC v2.1 §2.1, D-051), iguais nos seis sites.
   Lê o que cada site já tem no HTML: os links de .leagues viram o chip "Série A ▾" com a folha de competições, e o
   conteúdo de #reference-bar (edição, jogos, simulações) vai para a folha (i). A faixa .leagues e a barra de
   referência ficam no HTML só como fonte e somem da tela (styles.css). */
(function () {
  const SHORT = { "Brasileirão Série A": "Série A", "Premier League": "Premier", "Champions League": "Champions", "Mundial de LoL": "LoL" };
  const ICON = (body, size = 20) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
  const INFO = ICON('<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>');
  const CHEVRON = ICON('<path d="M7 10l5 5 5-5"/>', 16);

  /* Folha inferior no celular, caixa central no computador. <dialog> fecha com Esc e prende o foco. */
  function openSheet(title, body, onReady) {
    let dialog = document.getElementById("app-sheet");
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.id = "app-sheet";
      dialog.className = "sheet";
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog || event.target.closest("[data-sheet-close]") || event.target.closest("a[href]")) dialog.close();
      });
      document.body.append(dialog);
    }
    dialog.innerHTML = `<div class="sheet-panel" role="document">
        <div class="sheet-head"><h2 class="sheet-title">${title}</h2><button type="button" class="icon-button" data-sheet-close aria-label="Fechar">×</button></div>
        <div class="sheet-body">${body}</div>
      </div>`;
    if (onReady) onReady(dialog);
    if (dialog.open) return dialog;
    if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
    return dialog;
  }

  const leagueLinks = () => [...document.querySelectorAll(".leagues a")];

  function openCompetitions() {
    const links = leagueLinks();
    const grid = links.map((link) => {
      const current = link.getAttribute("aria-current") === "page";
      return `<a class="sheet-tile${current ? " is-current" : ""}" href="${link.getAttribute("href")}"${current ? ' aria-current="page"' : ""}>${link.textContent.trim()}</a>`;
    }).join("");
    openSheet("Competições", `<div class="sheet-grid">${grid}</div>`);
  }

  function methodHref() {
    const link = [...document.querySelectorAll(".masthead nav a")].find((item) => /calcul|metodolog/i.test(`${item.textContent} ${item.getAttribute("href")}`));
    return link ? link.getAttribute("href") : "#/metodologia";
  }

  function openInfo() {
    const bar = document.getElementById("reference-bar");
    const content = bar && bar.textContent.trim() ? bar.innerHTML : "<p>Carregando as simulações…</p>";
    openSheet("Sobre esta edição", `<div class="sheet-info">${content}</div>
      <p class="sheet-info-note">Probabilidade não é certeza: os números mudam a cada atualização.</p>
      <a class="btn-secondary sheet-wide" href="${methodHref()}">Como calculamos ›</a>`);
  }

  /* Linha curta com a data da edição, logo abaixo do cabeçalho (princípio 3 do guia de marca). */
  function syncStrip(strip, bar) {
    const edition = bar.querySelector(".edition");
    strip.textContent = bar.dataset.short || (edition ? edition.textContent : bar.textContent).replace(/\s+/g, " ").trim();
  }

  function currentLeagueLink() {
    const links = leagueLinks();
    const marked = links.find((link) => link.getAttribute("aria-current") === "page");
    if (marked) return marked;
    const segments = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
    const slug = segments[segments.length - 1] || "";
    return links.find((link) => link.dataset.league === slug) || null;
  }

  function syncChip(chip) {
    const current = currentLeagueLink();
    const name = current ? current.textContent.trim() : "Competições";
    chip.setAttribute("aria-label", current ? `Competição: ${name}. Trocar de competição` : "Trocar de competição");
    chip.innerHTML = `<span>${SHORT[name] || name}</span>${CHEVRON}`;
  }

  function mount() {
    const inner = document.querySelector(".masthead-inner");
    if (!inner || inner.querySelector(".league-chip")) return;
    const brand = inner.querySelector(".brand");
    const leaguesEl = document.querySelector(".leagues");
    if (leagueLinks().length) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "league-chip";
      syncChip(chip);
      chip.addEventListener("click", openCompetitions);
      (brand || inner.firstChild).after(chip);
      if (leaguesEl) {
        new MutationObserver(() => syncChip(chip)).observe(leaguesEl, { subtree: true, attributes: true, attributeFilter: ["aria-current"] });
      }
    }
    let tools = inner.querySelector(".masthead-tools");
    if (!tools) {
      tools = document.createElement("div");
      tools.className = "masthead-tools";
      inner.append(tools);
    }
    const info = document.createElement("button");
    info.type = "button";
    info.className = "icon-button info-button";
    info.setAttribute("aria-label", "Sobre esta edição: data, jogos e simulações");
    info.innerHTML = INFO;
    info.addEventListener("click", openInfo);
    tools.prepend(info);

    const bar = document.getElementById("reference-bar");
    if (bar) {
      const strip = document.createElement("p");
      strip.className = "edition-strip wrap";
      strip.setAttribute("aria-hidden", "true");
      document.querySelector(".masthead").after(strip);
      syncStrip(strip, bar);
      new MutationObserver(() => syncStrip(strip, bar)).observe(bar, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["data-short"] });
    }
  }

  window.AIndaDaShell = { openSheet, openCompetitions, openInfo };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
