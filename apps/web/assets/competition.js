"use strict";

// Base comum dos sites das outras competições (D-043): cabeçalho, abas por rota (#/aba), barra de edição, escudos e
// os blocos da Série A (barras de probabilidade, tabela, jogos). Cada site chama AIndaDaSite.start com as próprias abas.
(function () {
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
  const BADGE_LABEL = /^[\p{Lu}\p{N}]{1,4}$/u;
  const state = { crests: {}, names: {}, shorts: {}, info: new Map(), matches: new Map(), config: null, data: null, history: null, choices: new Map(), widgets: new Map() };

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
  const teamCell = (id, size = 20, extra = "") => `<span class="club-cell club-link" data-club="${escapeHtml(id)}" role="button" tabindex="0" title="${escapeHtml(nameOf(id))}">${crest(id, size)}<span class="name-full">${escapeHtml(nameOf(id))}${extra ? ` ${extra}` : ""}</span><span class="name-short" aria-hidden="true">${escapeHtml(state.shorts[id] || nameOf(id).slice(0, 3).toUpperCase())}</span></span>`;

  function probCell(value, kind, label) {
    const intensity = Math.min(1, Math.max(0, value));
    return `<span class="prob prob-${kind}" style="--p:${intensity}">${label || pct(value)}</span>`;
  }

  // Barras de probabilidade da Série A: uma linha por time, com a barra e o valor (ou o rótulo da certeza aritmética).
  function raceRows(items, kind) {
    return items
      .map((item) => `<div class="race-row" data-club="${escapeHtml(item.id)}">${team(item.id, 18)}<div class="bar-track" aria-hidden="true"><div class="bar-fill ${kind}" style="width:${(item.value * 100).toFixed(1)}%"></div></div><span class="value">${item.label || pct(item.value)}</span></div>`)
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
    const side = (id) => `<span class="mc-team" data-club="${escapeHtml(id)}">${crest(id, 38)}<span class="mc-team-name">${escapeHtml(nameOf(id))}</span></span>`;
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


  /* ---------------- Widgets: chips que trocam só o bloco (sem rolar a página nem refazer a rota) */

  const choiceOf = (key) => state.choices.get(key) || {};

  // `render(choice)` devolve o HTML do bloco. Cada botão [data-cw-set] muda um campo da escolha e refaz só o bloco.
  function widget(key, render) {
    state.widgets.set(key, render);
    return `<div class="cw" data-cw="${escapeHtml(key)}">${render(choiceOf(key))}</div>`;
  }

  const chip = (key, name, value, label, active, extra = "") => `<button type="button" class="chip${extra}" data-cw-set="${escapeHtml(key)}" data-cw-name="${escapeHtml(name)}" data-cw-value="${escapeHtml(value)}" aria-pressed="${active ? "true" : "false"}">${label}</button>`;

  // Mostra o chip escolhido dentro da faixa horizontal, sem mexer na rolagem da página.
  function revealSelected(container) {
    container.querySelectorAll(".chip-strip").forEach((strip) => {
      const active = strip.querySelector('[aria-pressed="true"]');
      if (!active || strip.scrollWidth <= strip.clientWidth) return;
      const target = active.offsetLeft - (strip.clientWidth - active.offsetWidth) / 2;
      strip.scrollLeft = Math.max(0, target);
    });
  }

  function refreshWidget(container, focusSelector) {
    const key = container.dataset.cw;
    const render = state.widgets.get(key);
    if (!render) return;
    const strips = [...container.querySelectorAll(".chip-strip")].map((strip) => strip.scrollLeft);
    container.innerHTML = render(choiceOf(key));
    container.querySelectorAll(".chip-strip").forEach((strip, index) => { if (strips[index] !== undefined) strip.scrollLeft = strips[index]; });
    revealSelected(container);
    if (focusSelector) { const next = container.querySelector(focusSelector); if (next) next.focus({ preventScroll: true }); }
  }

  function setChoice(button) {
    const container = button.closest("[data-cw]");
    if (!container) return;
    const { cwSet: key, cwName: name, cwValue: value } = button.dataset;
    state.choices.set(key, { ...choiceOf(key), [name]: value });
    refreshWidget(container, `[data-cw-set="${key}"][data-cw-name="${name}"][data-cw-value="${CSS.escape(value)}"]`);
  }

  /* ---------------- Classificação por disputa (C2 da Série A) */

  const SURE = 0.99;
  const OUT = 0.01;
  const pointsRange = (club) => (club.interval ? ` · termina com ${Math.round(club.interval[0])}–${Math.round(club.interval[1])}` : "");

  function raceRowCard(club, race) {
    const value = race.value(club);
    const text = race.text ? race.text(club) : null;
    return `<div class="race-row-card" data-club="${escapeHtml(club.id)}" role="button" tabindex="0">
        <span class="rr-pos">${club.position}</span>${crest(club.id, 26)}
        <span class="rr-name">${escapeHtml(club.name)}</span>
        <span class="rr-meta">${escapeHtml(club.meta || `${club.points} pts`)}${pointsRange(club)}</span>
        <strong class="rr-value${text && !/^[<>]?\d/.test(text) ? " is-word" : ""}">${text || pct(value)}</strong>
        <span class="rr-bar" aria-hidden="true"><i style="width:${(Math.min(1, Math.max(0, value)) * 100).toFixed(1)}%;background:var(--${race.color})"></i></span></div>`;
  }

  // Grupos limpos: já garantido (aritmética ou 99% das simulações), na briga e fora (recolhido, abaixo de 1%).
  function raceGroups(clubs, race) {
    const state_ = (club) => (race.state ? race.state(club) : null);
    const ranked = [...clubs].sort((a, b) => race.value(b) - race.value(a) || a.position - b.position);
    const sure = ranked.filter((club) => state_(club) === "in" || (state_(club) !== "out" && race.value(club) >= SURE));
    const out = ranked.filter((club) => state_(club) === "out" || (state_(club) !== "in" && race.value(club) < OUT)).sort((a, b) => a.position - b.position);
    const open = ranked.filter((club) => !sure.includes(club) && !out.includes(club));
    const list = (items) => `<div class="rg-list${items.length > 1 ? " is-two" : ""}">${items.map((club) => raceRowCard(club, race)).join("")}</div>`;
    const group = (title, aside, items) => (items.length ? `<section class="race-group"><h2 class="rg-title">${escapeHtml(title)}<span>${aside}</span></h2>${list(items)}</section>` : "");
    const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;
    return `${group(race.words.sure, "garantido ou em 99% ou mais", sure)}
      ${group(race.words.open, plural(open.length, "clube", "clubes"), open)}
      ${out.length ? `<details class="race-group rg-out"><summary class="rg-title">${escapeHtml(race.words.out)}<span>${plural(out.length, "clube", "clubes")} abaixo de 1%</span></summary>${list(out)}</details>` : ""}`;
  }

  /* `config.clubs`: [{ id, name, position, points, meta, interval }]; `config.races`: [{ id, label, color, value, text?,
     state?, words: { sure, open, out }, info }]; `config.full()` devolve a tabela completa (chip "Tabela completa"). */
  function disputeBoard(key, config) {
    const FULL = "completa";
    const first = config.races[0].id;
    return widget(key, (choice) => {
      const selected = choice.race || first;
      const race = config.races.find((item) => item.id === selected);
      const chips = config.races.map((item) => chip(key, "race", item.id, escapeHtml(item.label), item.id === selected)).join("")
        + chip(key, "race", FULL, "Tabela completa", selected === FULL);
      const body = selected === FULL ? config.full() : raceGroups(config.clubs, race);
      return `<nav class="chip-strip" aria-label="Disputa">${chips}</nav>${body}`;
    });
  }

  /* ---------------- Agenda por dia (A1/B2 da Série A) */

  const MAX_DAYS = 30;

  function dayChip(day, list, selected, key) {
    const date = new Date(`${day}T12:00:00`);
    const weekday = day === isoToday() ? "Hoje" : date.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
    const month = date.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "");
    const label = `${dayLabel(day)}: ${list.length} ${list.length === 1 ? "jogo" : "jogos"}`;
    return `<button type="button" class="day-chip" data-cw-set="${escapeHtml(key)}" data-cw-name="day" data-cw-value="${day}" aria-label="${escapeHtml(label)}" aria-pressed="${day === selected ? "true" : "false"}"><span>${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}</span><strong>${date.getDate()}</strong><small>${month}</small></button>`;
  }

  /* Faixa de dias com jogo e a lista do dia escolhido. `postponed` = jogos sem data (adiados), em chip à parte. */
  function dayAgenda(key, matches, { postponed = [], emptyTitle = "Sem jogos marcados", emptyText = "Os próximos jogos aparecem aqui quando a fonte trouxer as datas." } = {}) {
    const days = new Map();
    [...matches].filter((match) => match.match_date).sort(byKickoff).forEach((match) => {
      if (!days.has(match.match_date)) days.set(match.match_date, []);
      days.get(match.match_date).push(match);
    });
    const keys = [...days.keys()].slice(0, MAX_DAYS);
    if (!keys.length && !postponed.length) return `<div class="state"><p class="state-title">${escapeHtml(emptyTitle)}</p><p class="state-text">${escapeHtml(emptyText)}</p></div>`;
    const today = isoToday();
    return widget(key, (choice) => {
      const fallback = keys.find((day) => day >= today) || keys[keys.length - 1] || "adiados";
      const selected = choice.day === "adiados" && postponed.length ? "adiados" : keys.includes(choice.day) ? choice.day : fallback;
      const strip = `<nav class="chip-strip day-strip" aria-label="Dias com jogos">${keys.map((day) => dayChip(day, days.get(day), selected, key)).join("")}${postponed.length
        ? `<button type="button" class="day-chip is-postponed" data-cw-set="${escapeHtml(key)}" data-cw-name="day" data-cw-value="adiados" aria-pressed="${selected === "adiados" ? "true" : "false"}"><span>Adiados</span><strong>${postponed.length}</strong><small>sem data</small></button>` : ""}</nav>`;
      const list = selected === "adiados" ? postponed : days.get(selected) || [];
      const title = selected === "adiados" ? "Adiados ou cancelados · sem data" : dayLabel(selected);
      const more = days.size > MAX_DAYS ? `<p class="comp-notice">Mostrando os próximos ${MAX_DAYS} dias com jogos.</p>` : "";
      return `${strip}<h2 class="comp-day-title">${escapeHtml(title)}<span>${list.length} ${list.length === 1 ? "jogo" : "jogos"}</span></h2>${matchList(list)}${more}`;
    });
  }

  /* ---------------- Folha do clube */

  function sparkline(values, width = 280, height = 64) {
    const top = Math.max(0.05, ...values);
    const step = values.length > 1 ? (width - 8) / (values.length - 1) : 0;
    const coordinates = values.map((value, index) => [4 + index * step, 4 + (height - 8) * (1 - value / top)]);
    const path = coordinates.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
    const [lastX, lastY] = coordinates[coordinates.length - 1];
    return `<svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true"><path d="${path}" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/><circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="3.5" class="spark-dot"/></svg>`;
  }

  const historyPoints = () => (state.history ? state.history.points : []);
  const metricSeries = (id, metric) => historyPoints().map((point) => (point.teams[id] ? metric.get(point.teams[id]) : null)).filter((value) => value !== null && value !== undefined);

  // A métrica em que o clube mais aparece (a de maior pico): evita mostrar uma curva zerada de título para quem luta contra a queda.
  function evolutionBlock(id) {
    const metrics = state.config.history ? state.config.history.metrics(state.data, state.history) : [];
    if (!metrics.length || historyPoints().length < 2) return "";
    const ranked = metrics.map((metric) => ({ metric, series: metricSeries(id, metric) })).filter((item) => item.series.length > 1)
      .sort((a, b) => Math.max(...b.series) - Math.max(...a.series));
    const best = ranked[0];
    if (!best || Math.max(...best.series) < 0.005) return "";
    const first = best.series[0];
    const last = best.series[best.series.length - 1];
    const rounds = historyPoints();
    return `<section class="club-evolution" aria-label="Evolução: ${escapeHtml(best.metric.label)}">
        <div class="club-evolution-head"><strong>${escapeHtml(best.metric.label)} rodada a rodada</strong><a href="#/rodadas/${encodeURIComponent(id)}">Ver em Rodadas ›</a></div>
        <div class="club-evolution-body">${sparkline(best.series)}<p><span>R${rounds[0].round}: ${pct(first)}</span><span>R${rounds[rounds.length - 1].round}: <b>${pct(last)}</b></span></p></div>
        <p class="note">Reconstruído agora com o modelo de hoje, não é o que foi publicado na época.</p></section>`;
  }

  function nextLines(id, matches) {
    return matches.map((match) => {
      const home = match.home_id === id;
      const rival = home ? match.away_id : match.home_id;
      const chance = home ? match.p_home : match.p_away;
      const when = match.match_date ? `${cardDay(match.match_date)}${match.kickoff_utc ? ` ${kickoff(match)}` : ""}` : "data a definir";
      const odds = [match.p_home, match.p_draw, match.p_away].every(isProbability) ? `<span class="club-next-odds">vitória ${pct(chance)} · empate ${pct(match.p_draw)}</span>` : "";
      return `<li><span class="club-next-when">${escapeHtml(when)}</span><span class="club-next-rival">${crest(rival, 20)}<b>${home ? "" : "@ "}${escapeHtml(nameOf(rival))}</b></span>${odds}</li>`;
    }).join("");
  }

  function openClub(id) {
    const model = state.config.club ? state.config.club(state.data, id) : null;
    if (!model || !window.AIndaDaShell) return;
    const stats = model.stats.map((stat) => `<span class="yt-stat ${stat.tone || ""}${/^[<>]?\d/.test(stat.text) ? "" : " is-word"}"><span>${escapeHtml(stat.label)}</span><strong>${stat.text}</strong></span>`).join("");
    const range = model.interval ? `<p class="club-range"><strong>Faixa provável: ${Math.round(model.interval[0])} a ${Math.round(model.interval[1])} pontos</strong><span>onde terminam 90% das simulações; média ${number.format(model.expectedPoints)}</span></p>` : "";
    const next = model.next && model.next.length ? `<section><h3 class="club-sub">Próximos jogos</h3><ul class="club-next">${nextLines(id, model.next)}</ul></section>` : "";
    window.AIndaDaShell.openSheet(escapeHtml(model.name), `<div class="club-sheet">
        <div class="yt-club">${crest(id, 44)}<span class="yt-name"><span>${escapeHtml(model.meta)}</span></span></div>
        <div class="yt-stats">${stats}</div>
        ${range}${next}${evolutionBlock(id)}</div>`);
  }

  /* ---------------- Rodadas: evolução das probabilidades (history.json) */

  function lineChart(rounds, values, metric) {
    const width = 320;
    const height = 150;
    const pad = { left: 34, right: 10, top: 10, bottom: 22 };
    const peak = Math.max(0.1, ...values);
    const top = peak > 0.5 ? 1 : Math.ceil(peak * 10) / 10;
    const x = (index) => pad.left + (rounds.length > 1 ? (index * (width - pad.left - pad.right)) / (rounds.length - 1) : 0);
    const y = (value) => pad.top + (height - pad.top - pad.bottom) * (1 - value / top);
    const path = values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
    const grid = [0, top / 2, top].map((value) => `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y(value).toFixed(1)}" y2="${y(value).toFixed(1)}" class="lc-grid"/><text x="${pad.left - 5}" y="${(y(value) + 4).toFixed(1)}" text-anchor="end" class="lc-label">${Math.round(value * 100)}%</text>`).join("");
    const every = Math.max(1, Math.ceil(rounds.length / 7));
    const ticks = rounds.map((round, index) => (index % every === 0 || index === rounds.length - 1 ? `<text x="${x(index).toFixed(1)}" y="${height - 5}" text-anchor="middle" class="lc-label">R${round}</text>` : "")).join("");
    const lastIndex = values.length - 1;
    const summary = `${metric.label}: de ${pct(values[0])} na rodada ${rounds[0]} a ${pct(values[lastIndex])} na rodada ${rounds[lastIndex]}; pico de ${pct(Math.max(...values))}`;
    return `<svg class="line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(summary)}">${grid}${ticks}<path d="${path}" class="lc-line" fill="none" stroke-linejoin="round" stroke-linecap="round"/>${values.map((value, index) => `<circle cx="${x(index).toFixed(1)}" cy="${y(value).toFixed(1)}" r="${index === lastIndex ? 4 : 2.2}" class="${index === lastIndex ? "lc-dot is-last" : "lc-dot"}"/>`).join("")}</svg>`;
  }

  function roundsView(data, segments) {
    const config = state.config.history;
    const points = historyPoints();
    const metrics = config.metrics(data, state.history);
    const clubs = config.clubs(data);
    if (segments[0] && clubs.some((club) => club.id === decodeURIComponent(segments[0]))) {
      state.choices.set("rodadas", { mode: "time", club: decodeURIComponent(segments[0]) });
    }
    const info = `<p>Como a chance de cada disputa mudou a cada rodada. Cada ponto é a previsão refeita como se a edição fosse o último jogo daquela rodada, com ${state.history.n_simulations.toLocaleString("pt-BR")} simulações e o modelo de hoje.</p>
      <p>É uma reconstrução: usa só jogos até a data de cada ponto, mas não é o que o site mostrava na época. O último ponto é a edição atual.</p>`;
    return `${screenHead("Rodadas", info)}
      ${widget("rodadas", (choice) => {
        const mode = choice.mode === "time" ? "time" : "rodada";
        const metric = metrics.find((item) => item.id === choice.metric) || metrics[0];
        const modeChips = `<nav class="chip-strip" aria-label="Visão">${chip("rodadas", "mode", "rodada", "Por rodada", mode === "rodada")}${chip("rodadas", "mode", "time", "Por time", mode === "time")}</nav>`;
        const metricChips = `<nav class="chip-strip" aria-label="Disputa">${metrics.map((item) => chip("rodadas", "metric", item.id, escapeHtml(item.label), item.id === metric.id)).join("")}</nav>`;
        const note = `<p class="comp-notice">Reconstruído agora com o modelo de hoje (${state.history.n_simulations.toLocaleString("pt-BR")} simulações por rodada), não é o que foi publicado na época.</p>`;
        if (mode === "time") {
          const club = clubs.find((item) => item.id === choice.club) || clubs[0];
          const series = points.map((point) => (point.teams[club.id] ? metric.get(point.teams[club.id]) : null));
          const rounds = points.map((point) => point.round);
          const clubChips = `<nav class="chip-strip" aria-label="Clube">${clubs.map((item) => chip("rodadas", "club", item.id, `${crest(item.id, 18)}<span>${escapeHtml(shortOf(item.id))}</span>`, item.id === club.id, " chip-club")).join("")}</nav>`;
          const valid = series.every((value) => value !== null);
          const peak = Math.max(...series.filter((value) => value !== null));
          const tiles = valid ? `<div class="yt-stats rd-tiles"><span class="yt-stat"><span>Em R${rounds[0]}</span><strong>${pct(series[0])}</strong></span><span class="yt-stat"><span>Pico</span><strong>${pct(peak)}</strong></span><span class="yt-stat"><span>Agora</span><strong>${pct(series[series.length - 1])}</strong></span></div>` : "";
          return `${modeChips}${clubChips}${metricChips}${valid ? `<section class="card rd-chart"><h2 class="rd-title">${escapeHtml(club.name)} · ${escapeHtml(metric.label)}</h2>${lineChart(rounds, series, metric)}</section>${tiles}` : '<p class="comp-notice">Este clube não está em todas as rodadas da história.</p>'}${note}`;
        }
        const index = Math.min(points.length - 1, Math.max(0, Number.isInteger(Number(choice.round)) && choice.round !== undefined ? Number(choice.round) : points.length - 1));
        const point = points[index];
        const before = index > 0 ? points[index - 1] : null;
        const roundChips = `<nav class="chip-strip" aria-label="Rodada">${points.map((item, position) => chip("rodadas", "round", String(position), `R${item.round}`, position === index)).join("")}</nav>`;
        const rows = clubs.map((club) => {
          const entry = point.teams[club.id];
          const value = entry ? metric.get(entry) : 0;
          const delta = entry && before && before.teams[club.id] ? value - metric.get(before.teams[club.id]) : null;
          return { club, entry, value, delta };
        }).filter((row) => row.entry && row.value >= 0.005).sort((a, b) => b.value - a.value || a.entry.position - b.entry.position).slice(0, 12);
        const list = rows.length ? `<div class="rg-list is-two">${rows.map((row) => `<div class="race-row-card" data-club="${escapeHtml(row.club.id)}" role="button" tabindex="0">
            <span class="rr-pos">${row.entry.position}</span>${crest(row.club.id, 26)}<span class="rr-name">${escapeHtml(row.club.name)}</span>
            <span class="rr-meta">${row.entry.points} pts${row.delta === null ? "" : ` · <b class="${row.delta > 0.0005 ? "is-up" : row.delta < -0.0005 ? "is-down" : ""}">${row.delta > 0.0005 ? "▲" : row.delta < -0.0005 ? "▼" : "="} ${number.format(Math.abs(row.delta) * 100)} p.p.</b>`}</span>
            <strong class="rr-value">${pct(row.value)}</strong><span class="rr-bar" aria-hidden="true"><i style="width:${(Math.min(1, row.value) * 100).toFixed(1)}%;background:var(--${metric.color || "title"})"></i></span></div>`).join("")}</div>` : '<p class="comp-notice">Nenhum clube com chance relevante nesta rodada.</p>';
        return `${modeChips}${roundChips}${metricChips}<h2 class="comp-day-title">${escapeHtml(metric.label)} · rodada ${point.round}<span>${escapeHtml(S_formatShort(point.reference_date))}</span></h2>${list}${note}`;
      })}`;
  }
  const S_formatShort = (iso) => formatDate(iso, { day: "2-digit", month: "2-digit", year: "numeric" });

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
      const choice = event.target.closest("[data-cw-set]");
      if (choice) { setChoice(choice); return; }
      const club = event.target.closest("[data-club]");
      if (club && !event.target.closest("a, [data-cw-set]")) { openClub(club.dataset.club); return; }
      const card = event.target.closest(".mc[data-match-id]");
      if (card && !event.target.closest("a, button")) openMatch(card.dataset.matchId);
    });
    main.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const club = event.target.closest && event.target.closest("[data-club][role='button']");
      if (club && event.target === club) { event.preventDefault(); openClub(club.dataset.club); return; }
      const card = event.target.closest && event.target.closest(".mc[data-match-id]");
      if (card && event.target === card) { event.preventDefault(); openMatch(card.dataset.matchId); }
    });
    const nav = document.getElementById("sections");
    // A aba Rodadas só existe quando há history.json com pelo menos duas rodadas (degradação elegante).
    const roundsRoute = { id: "rodadas", label: "Rodadas", render: roundsView };
    let routes = config.routes;
    const drawNav = () => { nav.innerHTML = routes.map((route) => `<a href="#/${route.id}" data-route="${route.id}">${escapeHtml(route.label)}</a>`).join(""); };
    drawNav();

    function show(data) {
      const [, section = "", ...rest] = location.hash.replace(/^#/, "").split("/");
      const route = routes.find((item) => item.id === section) || routes[0];
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
      state.widgets = new Map();
      main.innerHTML = route.render(data, rest);
      main.querySelectorAll("[data-cw]").forEach(revealSelected);
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
      Promise.all([getJson("data/forecast.json"), getJson("assets/crests/manifest.json").catch(() => ({})), config.history ? getJson("data/history.json").catch(() => null) : null])
        .then(([data, crests, history]) => {
          state.crests = crests;
          state.data = data;
          state.history = history && Array.isArray(history.points) && history.points.length >= 2 ? history : null;
          if (state.history) {
            const at = routes.findIndex((route) => route.id === "metodologia");
            routes = at < 0 ? [...config.routes, roundsRoute] : [...config.routes.slice(0, at), roundsRoute, ...config.routes.slice(at)];
            drawNav();
          }
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

  window.AIndaDaSite = { disputeBoard, dayAgenda, widget, chip, sparkline, escapeHtml, safeUrl, pct, formatDate, shortDate, kickoff, crest, team, teamCell, nameOf, shortOf, probCell, raceRows, heat, matchRow, matchCard, matchList, matchesByDay, screenHead, raceCard, yourTeam, sources, start };
})();
