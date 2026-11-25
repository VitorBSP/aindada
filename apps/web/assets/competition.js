"use strict";

// Base comum dos sites das outras competições (D-043): cabeçalho, abas por rota (#/aba), barra de edição, escudos e
// os blocos da Série A (barras de probabilidade, tabela, jogos). Cada site chama AIndaDaSite.start com as próprias abas.
(function () {
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
  const BADGE_LABEL = /^[\p{Lu}\p{N}]{1,4}$/u;
  const state = { crests: {}, names: {}, shorts: {}, info: new Map(), matches: new Map(), config: null, data: null };

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

  // Célula de clube das tabelas: nome inteiro no computador, sigla no celular (mesmo padrão da Série A).
  const teamCell = (id, size = 20, extra = "") => `<span class="club-cell" title="${escapeHtml(nameOf(id))}">${crest(id, size)}<span class="name-full">${escapeHtml(nameOf(id))}${extra ? ` ${extra}` : ""}</span><span class="name-short" aria-hidden="true">${escapeHtml(state.shorts[id] || nameOf(id).slice(0, 3).toUpperCase())}</span></span>`;

  function probCell(value, kind, label) {
    const intensity = Math.min(1, Math.max(0, value));
    return `<span class="prob prob-${kind}" style="--p:${intensity}">${label || pct(value)}</span>`;
  }

  // Barras de probabilidade da Série A: uma linha por time, com a barra e o valor (ou o rótulo da certeza aritmética).
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

  /* ---------------- Componentes v2.1 (REDESIGN_SPEC, D-051), iguais aos da Série A */

  const shortOf = (id) => state.shorts[id] || nameOf(id).slice(0, 3).toUpperCase();
  const isProbability = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  const isoToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());

  function cardDay(iso) {
    const weekday = formatDate(iso, { weekday: "short" }).replace(".", "");
    return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)} ${formatDate(iso, { day: "2-digit", month: "2-digit" })}`;
  }

  function dayLabel(iso) {
    const today = isoToday();
    const shift = (days) => { const date = new Date(`${today}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + days); return date.toISOString().slice(0, 10); };
    const relative = iso === today ? "Hoje · " : iso === shift(1) ? "Amanhã · " : "";
    return `${relative}${cardDay(iso)}`;
  }

  // Match Card v2.1: rodada e horário, escudos, "VS" e as 3 pílulas 1X2 com a sigla dos clubes. O card inteiro abre o
  // detalhe do jogo (match-popup.js). Sem placar aqui: estes sites só listam jogos ainda por disputar.
  function matchCard(match) {
    state.matches.set(match.match_id, match);
    const clock = match.kickoff_utc ? kickoff(match) : "";
    const when = match.match_date ? `${cardDay(match.match_date)}${clock ? ` ${clock}` : ""}` : "data a definir na fonte";
    const round = Number.isInteger(match.round) ? `R${match.round} · ` : "";
    const values = [match.p_home, match.p_draw, match.p_away];
    const top = Math.max(...values);
    const pill = (value, label) => `<span class="mc-odd${value === top ? " is-top" : ""}"><strong>${pct(value)}</strong><span>${escapeHtml(label)}</span></span>`;
    const odds = values.every(isProbability)
      ? `<p class="mc-caption">Probabilidade do modelo</p><div class="mc-odds">${pill(match.p_home, shortOf(match.home_id))}${pill(match.p_draw, "Empate")}${pill(match.p_away, shortOf(match.away_id))}</div>` : "";
    const side = (id) => `<span class="mc-team">${crest(id, 38)}<span class="mc-team-name">${escapeHtml(nameOf(id))}</span></span>`;
    const spoken = `${nameOf(match.home_id)} contra ${nameOf(match.away_id)}, ${when}${values.every(isProbability) ? `. Probabilidade do modelo: ${nameOf(match.home_id)} ${pct(match.p_home)}, empate ${pct(match.p_draw)}, ${nameOf(match.away_id)} ${pct(match.p_away)}` : ""}. Ver detalhes`;
    return `<article class="mc" data-match-id="${escapeHtml(match.match_id)}" tabindex="0" role="button" aria-label="${escapeHtml(spoken)}">
        <div class="mc-top"><span>${round}${escapeHtml(when)}</span><span class="mc-top-end"><span class="mc-go" aria-hidden="true">›</span></span></div>
        <div class="mc-teams" aria-hidden="true">${side(match.home_id)}<span class="mc-center is-vs">VS</span>${side(match.away_id)}</div>
        <div aria-hidden="true">${odds}</div>
      </article>`;
  }

  const matchList = (matches) => `<div class="mc-list">${matches.map(matchCard).join("")}</div>`;
  const byKickoff = (left, right) => String(left.match_date || "~").localeCompare(String(right.match_date || "~"))
    || (Date.parse(left.kickoff_utc || "") || Infinity) - (Date.parse(right.kickoff_utc || "") || Infinity);

  // Próximos jogos agrupados por dia real (não pela rodada), em ordem cronológica.
  function matchesByDay(matches) {
    const groups = new Map();
    [...matches].sort(byKickoff).forEach((match) => {
      const day = match.match_date || "";
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(match);
    });
    return [...groups.entries()].map(([day, list]) => `<section class="comp-day" aria-label="${escapeHtml(day ? dayLabel(day) : "Sem data")}">
        <h2 class="comp-day-title">${day ? dayLabel(day) : "Sem data na fonte"}<span>${list.length} ${list.length === 1 ? "jogo" : "jogos"}</span></h2>${matchList(list)}</section>`).join("");
  }

  function openMatch(matchId) {
    const match = state.matches.get(matchId);
    if (!match || !window.MatchPopup) return;
    const when = match.match_date ? `${escapeHtml(dayLabel(match.match_date))}${match.kickoff_utc ? ` · ${escapeHtml(kickoff(match))}` : ""}` : "Data a definir na fonte";
    const goals = Number.isFinite(match.expected_home_goals) && Number.isFinite(match.expected_away_goals)
      ? `<p class="match-popup-line"><strong>Gols esperados:</strong> ${number.format(match.expected_home_goals)} × ${number.format(match.expected_away_goals)}</p>` : "";
    window.MatchPopup.open(`${escapeHtml(nameOf(match.home_id))} × ${escapeHtml(nameOf(match.away_id))}`, `
      <p class="match-popup-line"><strong>Ainda não jogado.</strong> ${when}${Number.isInteger(match.round) ? ` · rodada ${match.round}` : ""}.</p>
      <div class="match-popup-triple"><span><strong>${pct(match.p_home)}</strong>${escapeHtml(nameOf(match.home_id))}</span><span><strong>${pct(match.p_draw)}</strong>empate</span><span><strong>${pct(match.p_away)}</strong>${escapeHtml(nameOf(match.away_id))}</span></div>
      ${goals}
      <p class="note">Probabilidade do modelo, em simulações a partir da força de cada clube na data da edição.</p>`);
  }

  // Título de tela com o botão (i): a explicação sai do corpo da tela e vai para a folha (D-051).
  function screenHead(title, info = "", { hidden = false } = {}) {
    let button = "";
    if (info) {
      const id = `info-${state.info.size + 1}`;
      state.info.set(id, { title: `Sobre: ${title}`, body: info });
      button = `<button type="button" class="icon-button" data-screen-info="${id}" aria-label="Como ler: ${escapeHtml(title)}"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg></button>`;
    }
    return `<div class="screen-head${hidden ? " is-compact" : ""}"><h1 class="${hidden ? "visually-hidden" : "screen-title"}">${escapeHtml(title)}</h1>${button}</div>`;
  }

  // Card de disputa (Home): título, (i) com a regra e as linhas com barra.
  function raceCard(title, info, rows) {
    let button = "";
    if (info) {
      const id = `info-${state.info.size + 1}`;
      state.info.set(id, { title, body: `<p>${info}</p>` });
      button = `<button type="button" class="icon-button" data-screen-info="${id}" aria-label="Como ler: ${escapeHtml(title)}"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg></button>`;
    }
    return `<section class="race comp-race"><div class="block-head"><h2>${escapeHtml(title)}</h2>${button}</div>${rows}</section>`;
  }

  /* Card "Seu Time" por competição: o clube fica salvo neste aparelho (localStorage), um por competição. */
  const favoriteKey = (code) => `ainda-da:meu-time:${code}`;
  function favoriteId(code) {
    try { return window.localStorage.getItem(favoriteKey(code)) || ""; } catch (error) { return ""; }
  }
  function setFavorite(code, id) {
    try { window.localStorage.setItem(favoriteKey(code), id); } catch (error) { /* sem armazenamento: vale só nesta visita */ }
  }

  function yourTeam(data) {
    const favorite = state.config && state.config.favorite;
    if (!favorite) return "";
    const code = favorite.code(data);
    const clubs = favorite.clubs(data);
    const club = clubs.find((item) => item.id === favoriteId(code));
    if (!club) {
      return `<section class="card your-team is-empty" aria-label="Seu time"><p class="yt-empty">Escolha seu time</p><button type="button" class="btn-secondary btn-sm" data-open-teams>Escolher</button></section>`;
    }
    // Rótulo de certeza aritmética ("não dá mais", "não cai mais") vai em fonte menor que o número.
    const stats = favorite.stats(data, club.id).map((stat) => `<span class="yt-stat ${stat.tone || ""}${/^[<>]?\d/.test(stat.text) ? "" : " is-word"}"><span>${escapeHtml(stat.label)}</span><strong>${stat.text}</strong></span>`).join("");
    const next = favorite.next ? favorite.next(data, club.id) : null;
    return `<section class="card your-team" aria-label="Seu time">
      <div class="yt-head">
        <span class="yt-club">${crest(club.id, 40)}<span class="yt-name"><strong>${escapeHtml(club.name)}</strong><span>${escapeHtml(club.meta)}</span></span></span>
        <button type="button" class="chip chip-sm" data-open-teams>Trocar</button>
      </div>
      <div class="yt-stats">${stats}</div>
      ${next ? `<p class="mc-caption comp-next-label">Próximo jogo</p>${matchList([next])}` : ""}
    </section>`;
  }

  function openTeamSheet(rerender) {
    const favorite = state.config.favorite;
    const code = favorite.code(state.data);
    const current = favoriteId(code);
    const grid = favorite.clubs(state.data).map((club) => `<button type="button" class="team-tile${club.id === current ? " is-current" : ""}" data-pick="${escapeHtml(club.id)}"${club.id === current ? ' aria-pressed="true"' : ""}>${crest(club.id, 32)}<span>${escapeHtml(club.name)}</span></button>`).join("");
    if (!window.AIndaDaShell) return;
    window.AIndaDaShell.openSheet("Escolha seu time", `<div class="sheet-grid sheet-grid-teams">${grid}</div>`, (dialog) => {
      dialog.querySelectorAll("[data-pick]").forEach((button) => button.addEventListener("click", () => {
        setFavorite(code, button.dataset.pick);
        dialog.close();
        rerender();
      }));
    });
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
    state.config = config;
    main.addEventListener("click", (event) => {
      const card = event.target.closest(".mc[data-match-id]");
      if (card && !event.target.closest("a, button")) openMatch(card.dataset.matchId);
    });
    main.addEventListener("keydown", (event) => {
      const card = event.target.closest && event.target.closest(".mc[data-match-id]");
      if (card && event.target === card && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openMatch(card.dataset.matchId); }
    });
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
      state.info = new Map();
      state.matches = new Map();
      main.innerHTML = route.render(data, rest);
      main.querySelectorAll("[data-screen-info]").forEach((button) => button.addEventListener("click", () => {
        const info = state.info.get(button.dataset.screenInfo);
        if (info && window.AIndaDaShell) window.AIndaDaShell.openSheet(escapeHtml(info.title), `<div class="sheet-info">${info.body}</div>`);
      }));
      main.querySelectorAll("[data-open-teams]").forEach((button) => button.addEventListener("click", () => openTeamSheet(() => show(data))));
      if (route.after) route.after(data, main);
      if (section) main.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }

    // Carrega a edição; em erro, "Tentar novamente" refaz a busca sem recarregar a página.
    function load() {
      main.innerHTML = `<div class="skeleton-page" aria-busy="true"><span class="visually-hidden">Carregando as probabilidades…</span><span class="skeleton sk-team"></span><span class="skeleton sk-card"></span><span class="skeleton sk-card"></span></div>`;
      Promise.all([getJson("data/forecast.json"), getJson("assets/crests/manifest.json").catch(() => ({}))])
        .then(([data, crests]) => {
          state.crests = crests;
          state.data = data;
          state.names = config.names(data);
          state.shorts = config.shorts ? config.shorts(data) : {};
          document.getElementById("reference-bar").innerHTML = config.edition(data);
          document.getElementById("footer-sources").innerHTML = config.footer(data);
          show(data);
          window.addEventListener("hashchange", () => show(data));
        })
        .catch(() => {
          document.getElementById("reference-bar").textContent = "";
          main.innerHTML = `<div class="state" role="alert"><p class="state-title">Não deu para carregar as probabilidades</p><p class="state-text">A conexão falhou ou a atualização ainda não está no ar. Confira a internet e tente de novo.</p><button type="button" class="state-action btn-primary" id="retry">Tentar novamente</button></div>`;
          document.getElementById("retry").addEventListener("click", load);
        });
    }
    load();
  }

  window.AIndaDaSite = { escapeHtml, safeUrl, pct, formatDate, shortDate, kickoff, crest, team, teamCell, nameOf, shortOf, probCell, raceRows, heat, matchRow, matchCard, matchList, matchesByDay, screenHead, raceCard, yourTeam, sources, start };
})();
