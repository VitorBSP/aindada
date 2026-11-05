"use strict";

// Base comum dos sites das outras competições (D-043): cabeçalho, abas por rota (#/aba), barra de edição, escudos e
// os blocos da Série A (barras de chance, tabela, jogos). Cada site chama AIndaDaSite.start com as próprias abas.
(function () {
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
  const BADGE_LABEL = /^[\p{Lu}\p{N}]{1,4}$/u;
  const state = { crests: {}, names: {} };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  // Certeza só quando a aritmética decide; simulação nunca vira certeza (CONTENT_GUIDELINES).
  function pct(value) {
    if (value === 0) return "0%";
    if (value < 0.001) return "<0,1%";
    if (value > 0.999) return ">99,9%";
    if (value < 0.01 || value > 0.99) return number.format(Math.round(value * 1000) / 10) + "%";
    return Math.round(value * 100) + "%";
  }

  function formatDate(iso, options = { day: "numeric", month: "long", year: "numeric" }) {
    const [year, month, day] = iso.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("pt-BR", options);
  }

  const shortDate = (iso) => formatDate(iso, { weekday: "short", day: "numeric", month: "short" });

  function kickoff(match) {
    if (match.kickoff_utc) {
      return new Date(match.kickoff_utc).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
    }
    return "a definir";
  }

  // Escudo livre (Commons, domínio público ou CC0) ou marcador com a sigla e a cor oficial (D-028, D-043).
  function crest(id, size = 20) {
    const entry = state.crests[id];
    if (entry && entry.file) {
      // Logo claro (feito para fundo escuro) vai sobre um quadrado em tinta, sem alterar a imagem.
      return `<img class="crest${entry.dark === true ? " crest-on-dark" : ""}" src="assets/crests/${encodeURIComponent(entry.file)}" alt="" width="${size}" height="${size}" loading="lazy" decoding="async">`;
    }
    const badge = entry && entry.badge;
    if (badge && BADGE_LABEL.test(badge.label) && HEX_COLOR.test(badge.bg) && HEX_COLOR.test(badge.fg)) {
      const text = size < 32 ? badge.label.charAt(0) : badge.label;
      const fontSize = Math.round(size * (size < 32 ? 0.6 : 0.32));
      return `<span class="crest crest-badge" aria-hidden="true" style="width:${size}px;height:${size}px;font-size:${fontSize}px;--badge-bg:${badge.bg};--badge-fg:${badge.fg}">${escapeHtml(text)}</span>`;
    }
    return `<span class="crest-spacer" style="width:${size}px" aria-hidden="true"></span>`;
  }

  const nameOf = (id) => state.names[id] || id;
  const team = (id, size = 20, trailing = false) =>
    `<span class="club-cell">${trailing ? "" : crest(id, size)}<span>${escapeHtml(nameOf(id))}</span>${trailing ? crest(id, size) : ""}</span>`;

  function probCell(value, kind, label) {
    const intensity = Math.min(1, Math.max(0, value));
    return `<span class="prob prob-${kind}" style="--p:${intensity}">${label || pct(value)}</span>`;
  }

  // Barras de chance da Série A: uma linha por time, com a barra e o valor (ou o rótulo da certeza aritmética).
  function raceRows(items, kind) {
    return items
      .map((item) => `<div class="race-row">${team(item.id, 18)}<div class="bar-track" aria-hidden="true"><div class="bar-fill ${kind}" style="width:${(item.value * 100).toFixed(1)}%"></div></div><span class="value">${item.label || pct(item.value)}</span></div>`)
      .join("");
  }

  function heat(probabilities, name) {
    const cells = probabilities
      .map((value, index) => `<i style="opacity:${value === 0 ? 0.06 : (0.12 + 0.88 * Math.min(1, value * 1.6)).toFixed(2)}" title="${index + 1}º: ${pct(value)}"></i>`)
      .join("");
    return `<span class="heat" role="img" aria-label="Distribuição da posição final de ${escapeHtml(name)}">${cells}</span>`;
  }

  // Jogo com a barra 1X2 da Série A: mandante em tinta, empate em cinza, visitante em azul (D-038).
  function matchRow(match) {
    const shares = [match.p_home, match.p_draw, match.p_away];
    const cells = ["t-home", "t-draw", "t-away"]
      .map((cls, index) => `<span class="${cls}" style="flex:${Math.max(shares[index], 0.0001)}">${shares[index] >= 0.12 ? pct(shares[index]) : ""}</span>`)
      .join("");
    return `<div class="match">
      <div class="home">${team(match.home_id, 20, true)}</div>
      <div class="triple-cell"><div class="triple" role="img" aria-label="${escapeHtml(nameOf(match.home_id))} ${pct(match.p_home)}, empate ${pct(match.p_draw)}, ${escapeHtml(nameOf(match.away_id))} ${pct(match.p_away)}">${cells}</div></div>
      <div class="away">${team(match.away_id, 20)}</div>
      <div class="match-meta">${match.match_date ? `${escapeHtml(shortDate(match.match_date))} · ${escapeHtml(kickoff(match))} · ` : ""}vitória ${pct(match.p_home)} · empate ${pct(match.p_draw)} · derrota ${pct(match.p_away)}</div>
    </div>`;
  }

  // Só links http(s): o endereço vem do manifesto da fonte, mas nunca entra como javascript: ou data:.
  const safeUrl = (url) => (/^https?:\/\//i.test(String(url)) ? escapeHtml(url) : "#");

  function sources(list) {
    return list
      .map((source) => `<li><a href="${safeUrl(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>, versão ${escapeHtml(source.version)}.</li>`)
      .join("");
  }

  function getJson(path) {
    return fetch(path, { cache: "no-cache" }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    });
  }

  function start(config) {
    const main = document.getElementById("main");
    const nav = document.getElementById("sections");
    nav.innerHTML = config.routes.map((route) => `<a href="#/${route.id}" data-route="${route.id}">${escapeHtml(route.label)}</a>`).join("");

    function show(data) {
      const [, section = "", ...rest] = location.hash.replace(/^#/, "").split("/");
      const route = config.routes.find((item) => item.id === section) || config.routes[0];
      nav.querySelectorAll("a").forEach((link) => {
        if (link.dataset.route === route.id) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      [nav, document.querySelector(".leagues")].forEach((strip) => {
        const active = strip && strip.querySelector('[aria-current="page"]');
        if (!active || strip.scrollWidth <= strip.clientWidth) return;
        const hidden = active.offsetLeft < strip.scrollLeft || active.offsetLeft + active.offsetWidth > strip.scrollLeft + strip.clientWidth;
        if (hidden) strip.scrollLeft = Math.max(0, active.offsetLeft - 16);
      });
      main.innerHTML = route.render(data, rest);
      if (route.after) route.after(data, main);
      if (section) main.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }

    Promise.all([getJson("data/forecast.json"), getJson("assets/crests/manifest.json").catch(() => ({}))])
      .then(([data, crests]) => {
        state.crests = crests;
        state.names = config.names(data);
        document.getElementById("reference-bar").innerHTML = config.edition(data);
        document.getElementById("footer-sources").innerHTML = config.footer(data);
        show(data);
        window.addEventListener("hashchange", () => show(data));
      })
      .catch(() => {
        document.getElementById("reference-bar").textContent = "";
        main.innerHTML = '<p class="loading">Não foi possível carregar as simulações agora. Tente de novo em alguns minutos.</p>';
      });
  }

  window.AIndaDaSite = { escapeHtml, safeUrl, pct, formatDate, shortDate, kickoff, crest, team, nameOf, probCell, raceRows, heat, matchRow, sources, start };
})();
