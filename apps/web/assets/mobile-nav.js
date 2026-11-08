"use strict";

/* Barra de navegação no pé da tela, no celular (D-048). Usada pelos sites de todas as competições: lê os links do menu
   do cabeçalho (.masthead nav), mostra até quatro com ícone e põe o resto em "Mais", junto com as outras competições.
   No computador o menu de cima continua igual; a barra só aparece até 560 px (styles.css). */
(function () {
  const ICONS = {
    home: '<path d="M4 11l8-7 8 7v9h-5v-6h-6v6H4z"/>',
    table: '<path d="M4 5h16M4 10h16M4 15h16M4 20h16M9 5v15"/>',
    games: '<circle cx="12" cy="12" r="8"/><path d="M12 8l3 2.5-1.2 3.5h-3.6L9 10.5z"/>',
    simulator: '<path d="M5 6h14M5 12h14M5 18h14"/><circle cx="9" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    clubs: '<path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z"/>',
    rounds: '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>',
    bracket: '<path d="M4 5h5v6h6M4 19h5v-6M15 11v2h5"/>',
    method: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    more: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  };
  const iconFor = (label, route) => {
    const text = `${route || ""} ${label}`.toLowerCase();
    if (/home|início|inicio/.test(text) || route === "") return "home";
    if (/simul/.test(text)) return "simulator";
    if (/tabela|classifica|fase de liga|times/.test(text)) return "table";
    if (/jogos|partidas/.test(text)) return "games";
    if (/clube/.test(text)) return "clubs";
    if (/rodada/.test(text)) return "rounds";
    if (/chave|ligas/.test(text)) return "bracket";
    if (/calcul|metodolog/.test(text)) return "method";
    return "more";
  };
  const svg = (name) => `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
  const SHORT = { "Rodada a rodada": "Rodadas", "Como calculamos": "Método", "Chave provável": "Chave", "Força das ligas": "Ligas" };
  const MAX_ITEMS = 4;

  function build() {
    const nav = document.querySelector(".masthead nav");
    if (!nav || document.querySelector(".tabbar")) return false;
    const links = [...nav.querySelectorAll("a")];
    if (!links.length) return false;
    // Os mais usados no polegar: início, tabela, jogos e simulador; o resto vai para "Mais".
    const PRIORITY = { home: 0, table: 1, games: 2, simulator: 3, bracket: 4, clubs: 5, rounds: 6, more: 7, method: 8 };
    const rank = (link) => PRIORITY[iconFor(link.textContent.trim(), link.dataset.route)];
    // Quatro itens mais "Mais" (que também leva às outras competições): cinco alvos de toque no máximo.
    const chosen = links.length <= MAX_ITEMS ? links : [...links].sort((left, right) => rank(left) - rank(right)).slice(0, MAX_ITEMS);
    const primary = links.filter((link) => chosen.includes(link));
    const extra = links.filter((link) => !chosen.includes(link));
    const leagues = [...document.querySelectorAll(".leagues a")];
    const item = (link) => {
      const label = link.textContent.trim();
      return `<a class="tabbar-item" href="${link.getAttribute("href")}" data-mirror="${link.getAttribute("href")}">${svg(iconFor(label, link.dataset.route))}<span>${SHORT[label] || label}</span></a>`;
    };
    const bar = document.createElement("nav");
    bar.className = "tabbar";
    bar.setAttribute("aria-label", "Navegação principal");
    bar.innerHTML = primary.map(item).join("")
      + (extra.length || leagues.length ? `<button type="button" class="tabbar-item" aria-expanded="false" aria-controls="tabbar-more">${svg("more")}<span>Mais</span></button>` : "");
    const sheet = document.createElement("div");
    sheet.className = "tabbar-sheet";
    sheet.id = "tabbar-more";
    sheet.hidden = true;
    sheet.innerHTML = `<div class="tabbar-sheet-panel" role="dialog" aria-label="Mais">
        ${extra.length ? `<p class="tabbar-sheet-title">Nesta competição</p><div class="tabbar-sheet-links">${extra.map((link) => `<a href="${link.getAttribute("href")}" data-mirror="${link.getAttribute("href")}">${svg(iconFor(link.textContent, link.dataset.route))}<span>${link.textContent.trim()}</span></a>`).join("")}</div>` : ""}
        ${leagues.length ? `<p class="tabbar-sheet-title">Outras competições</p><div class="tabbar-sheet-chips">${leagues.map((link) => `<a href="${link.getAttribute("href")}" ${link.getAttribute("aria-current") ? 'aria-current="page"' : ""}>${link.textContent.trim()}</a>`).join("")}</div>` : ""}
      </div>`;
    document.body.append(bar, sheet);
    document.body.classList.add("has-tabbar");

    const more = bar.querySelector("button");
    const close = () => { sheet.hidden = true; if (more) more.setAttribute("aria-expanded", "false"); };
    if (more) more.addEventListener("click", () => {
      const open = sheet.hidden;
      sheet.hidden = !open;
      more.setAttribute("aria-expanded", String(open));
    });
    sheet.addEventListener("click", (event) => { if (event.target === sheet || event.target.closest("a")) close(); });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });

    // O item ativo segue o menu de cima, que cada site já atualiza a cada troca de página.
    const sync = () => {
      const current = nav.querySelector('[aria-current="page"]');
      const href = current ? current.getAttribute("href") : null;
      document.querySelectorAll("[data-mirror]").forEach((element) => {
        if (element.dataset.mirror === href) element.setAttribute("aria-current", "page"); else element.removeAttribute("aria-current");
      });
      if (more) more.classList.toggle("is-active", Boolean(href) && extra.some((link) => link.getAttribute("href") === href));
    };
    new MutationObserver(sync).observe(nav, { subtree: true, attributes: true, attributeFilter: ["aria-current"] });
    sync();
    return true;
  }

  // Nos sites das outras competições o menu é montado por script: tenta de novo até ele existir.
  if (!build()) {
    const observer = new MutationObserver(() => { if (build()) observer.disconnect(); });
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
