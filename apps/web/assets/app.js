(function () {
  "use strict";

  const SEASON = 2026;
  const state = { live: new Map(), prediction: null, whatIf: null, snapshot: null, history: [], metrics: null, rounds: null, currentRound: null, insights: [], crests: {}, apiMode: false, scenarioChoice: {}, historyMode: null };
  const main = document.getElementById("main");

  const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));

  function pct(value) {
    if (value === null || value === undefined) return "–";
    if (value === 0) return "0%";
    if (value < 0.001) return "<0,1%";
    if (value < 0.01) return (value * 100).toFixed(1).replace(".", ",") + "%";
    if (value > 0.999 && value < 1) return ">99,9%";
    if (value > 0.99 && value < 1) return (value * 100).toFixed(1).replace(".", ",") + "%";
    return Math.round(value * 100) + "%";
  }
  const num = (value, digits = 1) => Number(value).toFixed(digits).replace(".", ",");
  const formatDate = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
  const formatTimestampDate = (timestamp) => new Date(timestamp).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric", timeZone: "America/Sao_Paulo" });
  const formatShortDate = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" });

  async function fetchJson(path) {
    const candidates = [{ url: "/api" + path, api: true }, { url: "data/api" + path + ".json", api: false }];
    for (const candidate of candidates) {
      try {
        const response = await fetch(candidate.url, { headers: { Accept: "application/json" } });
        const type = response.headers.get("content-type") || "";
        if (response.ok && type.includes("json")) {
          state.apiMode = state.apiMode || candidate.api;
          return await response.json();
        }
      } catch (error) { /* tenta a próxima origem */ }
    }
    return null;
  }

  const teamById = (clubId) => state.snapshot.teams.find((team) => team.club_id === clubId);

  function reconstructionInfo() {
    if (state.historyMode !== "reconstructed" || !state.history.length) return null;
    const modelVersion = state.snapshot.model.model_version;
    const stamps = state.history.map((point) => point.generated_at).filter((stamp) => stamp && !Number.isNaN(Date.parse(stamp)));
    const latestStamp = stamps.length ? stamps.reduce((left, right) => (Date.parse(right) > Date.parse(left) ? right : left)) : state.snapshot.generated_at;
    return {
      consistent: state.history.every((point) => point.model_version === modelVersion),
      modelVersion: escapeHtml(modelVersion),
      generatedAt: escapeHtml(formatTimestampDate(latestStamp)),
    };
  }

  function sameModel(left, right) {
    return Boolean(left && right && left.model_version && left.model_version === right.model_version);
  }

  function reconstructionNote(info) {
    if (!info) return "";
    if (!info.consistent) return `<p class="note">Atenção: parte desta curva foi calculada com outra versão do modelo, então as variações entre pontos podem vir da troca de modelo, e não dos jogos.</p>`;
    return `<p class="note">Curva recalculada do zero em ${info.generatedAt}, com o modelo atual (versão ${info.modelVersion}). Cada ponto usa só os resultados conhecidos até aquela data, mas não é uma previsão feita na época. Quando o modelo muda, ou quando um resultado é corrigido na fonte, a curva inteira é refeita.</p>`;
  }
  const nameOf = (clubId) => (teamById(clubId) || { name: clubId }).name;

  const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
  const BADGE_LABEL = /^[A-Z]{2,4}$/;

  function crest(clubId, size = 20) {
    const entry = state.crests[clubId];
    if (entry && entry.file) {
      return `<img class="crest" src="assets/crests/${encodeURIComponent(entry.file)}" alt="" width="${size}" height="${size}" loading="lazy" decoding="async">`;
    }
    const badge = entry && entry.badge;
    if (badge && typeof badge.label === "string" && BADGE_LABEL.test(badge.label) && HEX_COLOR.test(badge.bg) && HEX_COLOR.test(badge.fg)) {
      const text = size < 32 ? badge.label.charAt(0) : badge.label;
      const fontSize = Math.round(size * (size < 32 ? 0.6 : 0.32));
      return `<span class="crest crest-badge" aria-hidden="true" style="width:${size}px;height:${size}px;font-size:${fontSize}px;--badge-bg:${badge.bg};--badge-fg:${badge.fg}">${escapeHtml(text)}</span>`;
    }
    return `<span class="crest-spacer" style="width:${size}px" aria-hidden="true"></span>`;
  }

  const clubLink = (clubId, size = 18, trailing = false) => `<a class="club-cell" href="#/clubes/${encodeURIComponent(clubId)}">${trailing ? "" : crest(clubId, size)}<span>${escapeHtml(nameOf(clubId))}</span>${trailing ? crest(clubId, size) : ""}</a>`;

  const DAY_MS = 86400000;
  const POSTPONED_AFTER_DAYS = 7;
  const daysBefore = (iso, reference) => (new Date(reference + "T12:00:00") - new Date(iso + "T12:00:00")) / DAY_MS;
  const isPostponed = (match) => match.status !== "finished" && daysBefore(match.match_date, state.snapshot.reference_date) > POSTPONED_AFTER_DAYS;

  const SCENARIO_KEYS = [
    ["libertadores_champion", "Campeão da Libertadores"],
    ["sudamericana_champion", "Campeão da Sul-Americana"],
    ["cup_champion", "Campeão da Copa do Brasil"],
    ["cup_runner_up", "Vice da Copa do Brasil"],
  ];

  const matchingScenarios = (choice = state.scenarioChoice) => state.snapshot.scenarios
    .filter((scenario) => Object.entries(choice).every(([key, value]) => scenario[key] === value));

  function scenarioBounds(range) {
    if (!Object.keys(state.scenarioChoice).length) return [range.min, range.max];
    const values = matchingScenarios().map((scenario) => range.by_scenario[scenario.scenario_id]).filter((value) => value !== undefined);
    if (!values.length) return [range.min, range.max];
    return [Math.min(...values), Math.max(...values)];
  }

  function scenarioValue(range) {
    const [low, high] = scenarioBounds(range);
    if (Math.abs(high - low) < 0.005) return pct(high);
    return `${pct(low)} a ${pct(high)}`;
  }
  const scenarioMid = (range) => { const [low, high] = scenarioBounds(range); return (low + high) / 2; };

  function probCell(value, kind) {
    const intensity = Math.min(1, Math.max(0, value));
    return `<span class="prob prob-${kind}" style="--p:${intensity}">${pct(value)}</span>`;
  }

  const formatEditionDate = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  function editionRound(snapshot) {
    const views = state.rounds && state.rounds.rounds;
    const latest = views && views[views.length - 1];
    if (!latest || latest.reference_date !== snapshot.reference_date || !latest.round_number) return "";
    return latest.partial ? ` · rodada ${latest.round_number} em andamento` : ` · depois da rodada ${latest.round_number}`;
  }

  function renderReferenceBar() {
    const snapshot = state.snapshot;
    const bar = document.getElementById("reference-bar");
    bar.innerHTML = `
      <p class="edition"><span class="edition-name">Edição de ${formatEditionDate(snapshot.reference_date)}</span>${editionRound(snapshot)}</p>
      <p class="edition-facts"><strong>${snapshot.observed_matches}</strong> de ${snapshot.observed_matches + snapshot.remaining_matches} jogos disputados ·
        <strong>${snapshot.n_simulations.toLocaleString("pt-BR")}</strong> simulações do resto do campeonato ·
        <span class="pill">modelo experimental</span></p>`;
    const views = state.rounds && state.rounds.rounds;
    const latest = views && views[views.length - 1];
    const round = editionRound(snapshot) && latest ? `Rodada ${latest.round_number} · ` : "";
    bar.dataset.short = `${round}dados até ${formatDay(snapshot.reference_date)}`;
  }

  const matchName = (match) => `${escapeHtml(nameOf(match.home_id))} x ${escapeHtml(nameOf(match.away_id))}`;

  function overdueWarning() {
    const stamp = Date.parse(state.snapshot.generated_at);
    const generated = Number.isNaN(stamp) ? state.snapshot.generated_at.slice(0, 10) : window.CurrentRound.brasiliaDay(stamp);
    const pending = state.snapshot.matches.filter((match) => match.status === "scheduled" && !isPostponed(match) && match.match_date < generated);
    if (!pending.length) return "";
    const list = pending.map((match) => `${matchName(match)} (${formatShortDate(match.match_date)})`).join("; ");
    const count = pending.length === 1 ? "1 jogo recente ainda está" : `${pending.length} jogos recentes ainda estão`;
    return `<details class="warning"><summary><strong>${count} sem placar na fonte de dados.</strong> Entram na simulação como não disputados até o placar chegar.</summary><p>${list}.</p></details>`;
  }

  function currentInsights() {
    return (state.insights || []).filter((insight) => insight.snapshot_ref.reference_date === state.snapshot.reference_date);
  }

  function insightLinks(insight, onRoundsPage = false) {
    const links = insight.subjects.map((subject) => subject.kind === "club"
      ? `<a href="#/clubes/${encodeURIComponent(subject.id)}">Ver ${escapeHtml(subject.label || nameOf(subject.id))}</a>`
      : subject.kind === "match" && !onRoundsPage ? `<a href="#/rodadas">Ver a rodada</a>` : "");
    const unique = [...new Set(links.filter(Boolean))];
    return unique.length ? `<p class="highlight-links">${unique.join(" · ")}</p>` : "";
  }

  function insightArticle(insight, onRoundsPage = false) {
    return `<article class="highlight">
      <h3>${escapeHtml(insight.headline)}</h3>
      <p>${escapeHtml(insight.body)}</p>
      ${insightLinks(insight, onRoundsPage)}
    </article>`;
  }

  function roundHighlights(view) {
    const latest = state.rounds && state.rounds.rounds[state.rounds.rounds.length - 1];
    const insights = currentInsights();
    if (!insights.length || !latest || view.round_number !== latest.round_number || view.reference_date !== state.snapshot.reference_date) return "";
    return `<section class="highlights-block" aria-labelledby="round-highlights">
      <h2 id="round-highlights">Destaques desta rodada</h2>
      <div class="highlights">${insights.map((insight) => insightArticle(insight, true)).join("")}</div>
      <p class="note">Histórias escolhidas e revisadas a partir das simulações de ${formatDate(state.snapshot.reference_date)}. Cada número vem dessas simulações.</p>
    </section>`;
  }

  const BLOCK_SIDE = 10;
  const BLOCK_DOTS = BLOCK_SIDE * BLOCK_SIDE;
  const NARROW_LAYOUT = 560;

  const RACES = {
    titulo: { key: "title", label: "Título", noun: "título", slots: 1, color: "var(--title)", table: "titulo", briga: "briga-titulo" },
    g4: { key: "top4", label: "G4", noun: "G4", slots: 4, color: "var(--libertadores)", table: "libertadores", briga: "briga-g4" },
    rebaixamento: { key: "relegation", label: "Z4", noun: "rebaixamento", slots: 4, color: "var(--danger)", table: "rebaixamento", briga: "briga-z4" },
  };
  const RACE_MOVEMENT_THRESHOLD = 0.05;

  /* Uma bolinha por ponto percentual; o maior resto fecha exatamente 100 por vaga da disputa. */
  function allocateDots(teams, key, total) {
    const allocated = teams.map((team) => ({ team, dots: Math.floor(team[key] * 100), rest: team[key] * 100 - Math.floor(team[key] * 100) }));
    let missing = total - allocated.reduce((sum, item) => sum + item.dots, 0);
    [...allocated].sort((left, right) => right.rest - left.rest).forEach((item) => { if (missing > 0) { item.dots += 1; missing -= 1; } });
    return allocated.filter((item) => item.dots > 0);
  }

  const raceTeams = (race) => state.snapshot.teams.filter((team) => team[race.key] > 0).sort((left, right) => right[race.key] - left[race.key]);
  const BLACK = "#16171a", WHITE = "#ffffff";
  const CLUB_DOTS = {
    "athletico-pr": { split: [BLACK, "#c8102e"] },
    "atletico-mg": { fill: BLACK },
    bahia: { hbands: ["#0057a8", "#d7192a", WHITE] },
    botafogo: { fill: BLACK, center: WHITE },
    bragantino: { fill: WHITE, ring: "#d7192a", center: "#f6c400" },
    chapecoense: { split: ["#00843d", WHITE] },
    corinthians: { split: [BLACK, WHITE], ring: "#d7192a", ringWidth: 0.8 },
    coritiba: { split: [WHITE, "#00543c"] },
    cruzeiro: { fill: "#1b4da0" },
    flamengo: { split: ["#c8102e", BLACK] },
    fluminense: { vbands: ["#00613c", WHITE, "#8b1e3f"] },
    gremio: { vbands: ["#0d80bf", BLACK, WHITE] },
    internacional: { fill: "#e2231a" },
    mirassol: { fill: "#f7d117" },
    palmeiras: { fill: "#006437" },
    remo: { fill: "#3b2c7a" },
    santos: { split: [WHITE, BLACK] },
    "sao-paulo": { hbands: ["#e30613", WHITE, BLACK] },
    vasco: { diagonal: [BLACK, WHITE], center: "#d7192a" },
    vitoria: { split: ["#d7192a", BLACK] },
  };
  const DOT_RADIUS = 5;
  const dotId = (clubId) => `dot-${clubId.replace(/[^a-z0-9-]/g, "")}`;

  function bands(colors, vertical) {
    const size = (DOT_RADIUS * 2) / colors.length;
    return colors.map((color, index) => {
      const start = -DOT_RADIUS + index * size;
      return vertical
        ? `<rect x="${start}" y="-${DOT_RADIUS}" width="${size}" height="${DOT_RADIUS * 2}" fill="${color}"/>`
        : `<rect x="-${DOT_RADIUS}" y="${start}" width="${DOT_RADIUS * 2}" height="${size}" fill="${color}"/>`;
    }).join("");
  }

  function dotShapes(clubId) {
    const spec = CLUB_DOTS[clubId] || { fill: "var(--ink-faint)" };
    const r = DOT_RADIUS, d = (r * Math.SQRT1_2).toFixed(3);
    let shapes = "";
    if (spec.fill) shapes += `<circle r="${r}" fill="${spec.fill}"/>`;
    if (spec.split) shapes += `<path d="M-${r},0A${r},${r} 0 0 1 ${r},0Z" fill="${spec.split[0]}"/><path d="M-${r},0A${r},${r} 0 0 0 ${r},0Z" fill="${spec.split[1]}"/>`;
    if (spec.diagonal) shapes += `<circle r="${r}" fill="${spec.diagonal[1]}"/><path d="M-${d},-${d}A${r},${r} 0 0 1 ${d},${d}Z" fill="${spec.diagonal[0]}"/>`;
    if (spec.hbands || spec.vbands) shapes += `<g clip-path="url(#dot-clip)">${bands(spec.hbands || spec.vbands, Boolean(spec.vbands))}</g>`;
    if (spec.ring) {
      const ringWidth = spec.ringWidth || 1.6;
      shapes += `<circle r="${r - ringWidth / 2}" fill="none" stroke="${spec.ring}" stroke-width="${ringWidth}"/>`;
    }
    if (spec.center) shapes += `<circle r="${spec.ring ? 1.9 : 1.6}" fill="${spec.center}"/>`;
    return `${shapes}<circle class="dot-outline" r="${r - 0.2}" fill="none"/>`;
  }

  const dotDefs = (clubIds) => `<defs><clipPath id="dot-clip"><circle r="${DOT_RADIUS}"/></clipPath>${clubIds.map((clubId) =>
    `<symbol id="${dotId(clubId)}" viewBox="-${DOT_RADIUS} -${DOT_RADIUS} ${DOT_RADIUS * 2} ${DOT_RADIUS * 2}">${dotShapes(clubId)}</symbol>`).join("")}</defs>`;
  const dotSwatch = (clubId) => `<svg class="mosaic-swatch" viewBox="-${DOT_RADIUS} -${DOT_RADIUS} ${DOT_RADIUS * 2} ${DOT_RADIUS * 2}" width="14" height="14" aria-hidden="true"><use href="#${dotId(clubId)}" x="-${DOT_RADIUS}" y="-${DOT_RADIUS}" width="${DOT_RADIUS * 2}" height="${DOT_RADIUS * 2}"/></svg>`;

  function raceMosaic(race) {
    const contenders = raceTeams(race);
    if (!contenders.length) return "";
    const total = race.slots * BLOCK_DOTS;
    const groups = allocateDots(contenders, race.key, total);
    const blocksPerRow = main.clientWidth < NARROW_LAYOUT ? Math.min(2, race.slots) : race.slots;
    const pitch = 10, size = 8, gap = 14;
    const blockSize = BLOCK_SIDE * pitch;
    const blockRows = Math.ceil(race.slots / blocksPerRow);
    const width = blocksPerRow * blockSize + (blocksPerRow - 1) * gap;
    const height = blockRows * blockSize + (blockRows - 1) * gap;
    const position = (index) => {
      const block = Math.floor(index / BLOCK_DOTS), inside = index % BLOCK_DOTS;
      const left = (block % blocksPerRow) * (blockSize + gap), top = Math.floor(block / blocksPerRow) * (blockSize + gap);
      return [left + (inside % BLOCK_SIDE) * pitch + (pitch - size) / 2, top + Math.floor(inside / BLOCK_SIDE) * pitch + (pitch - size) / 2];
    };
    let index = 0;
    const dots = groups.map((group) => {
      const href = `#${dotId(group.team.club_id)}`;
      const uses = [];
      for (let count = 0; count < group.dots; count += 1, index += 1) {
        const [x, y] = position(index);
        uses.push(`<use href="${href}" x="${x}" y="${y}" width="${size}" height="${size}"/>`);
      }
      return uses.join("");
    }).join("");
    const legend = groups.map((group) => `<li>${dotSwatch(group.team.club_id)}
      <a class="club-cell" href="#/clubes/${encodeURIComponent(group.team.club_id)}"><span>${escapeHtml(group.team.name)}</span></a> <strong>${pct(group.team[race.key])}</strong></li>`).join("");
    const hidden = contenders.length - groups.length;
    const key = race.slots > 1
      ? `cada quadro de 100 bolinhas, 100% · ${race.slots} clubes ${race.key === "relegation" ? "caem" : "terminam no G4"} em cada simulação, então o mosaico tem ${race.slots} quadros: ${total}%`
      : "o quadro todo, 100%: um campeão em cada simulação";
    const description = groups.map((group) => `${group.team.name}: ${group.dots} bolinhas`).join("; ");
    const simulations = state.snapshot.n_simulations.toLocaleString("pt-BR");
    return `<figure class="mosaic">
      <p class="mosaic-key"><svg class="mosaic-swatch" viewBox="-${DOT_RADIUS} -${DOT_RADIUS} ${DOT_RADIUS * 2} ${DOT_RADIUS * 2}" aria-hidden="true"><circle r="${DOT_RADIUS - 0.4}" fill="currentColor"/></svg>
        <span><strong>cada bolinha, 1%</strong> de probabilidade · ${key}</span></p>
      <svg class="mosaic-chart mosaic-blocks-${blocksPerRow}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Mosaico de ${escapeHtml(race.noun)} com ${total} bolinhas de 1%. ${escapeHtml(description)}.">${dotDefs(groups.map((group) => group.team.club_id))}${dots}</svg>
      <figcaption>
        <ul class="mosaic-legend">${legend}</ul>
        <p class="note">Probabilidade em ${simulations} simulações do resto do campeonato, em bolinhas de 1 ponto percentual (arredondadas para fechar ${total}).${hidden > 0 ? ` ${hidden} clube(s) com menos de meio ponto não aparecem.` : ""}</p>
      </figcaption>
    </figure>`;
  }

  function raceMovement(race) {
    const latest = state.history[state.history.length - 1];
    const previous = state.history[state.history.length - 2];
    if (!latest || !previous || latest.reference_date !== state.snapshot.reference_date) return 0;
    return Object.entries(latest.teams).reduce((sum, [clubId, values]) => {
      const before = previous.teams[clubId];
      return before ? sum + Math.abs(values[race.key] - before[race.key]) : sum;
    }, 0) / race.slots;
  }

  const raceOpenness = (race) => state.snapshot.teams.reduce((sum, team) => sum + team[race.key] * (1 - team[race.key]), 0) / race.slots;

  function featuredRace() {
    const ranked = Object.entries(RACES).map(([id, race]) => ({ id, movement: raceMovement(race), openness: raceOpenness(race) }));
    const moved = ranked.filter((item) => item.movement >= RACE_MOVEMENT_THRESHOLD).sort((left, right) => right.movement - left.movement);
    if (moved.length) return { id: moved[0].id, reason: "movement" };
    return { id: ranked.sort((left, right) => right.openness - left.openness)[0].id, reason: "openness" };
  }

  /* ---------------- Seu time e convites para explorar (D-048) */

  // Preferência do visitante, só neste aparelho: o clube que ele segue abre a home.
  const FAVORITE_KEY = "ainda-da:meu-time:serie-a";
  function favoriteClub() {
    try { return window.localStorage.getItem(FAVORITE_KEY) || ""; } catch (error) { return ""; }
  }
  function setFavoriteClub(clubId) {
    try {
      if (clubId) window.localStorage.setItem(FAVORITE_KEY, clubId); else window.localStorage.removeItem(FAVORITE_KEY);
    } catch (error) { /* sem armazenamento: a escolha vale só nesta visita */ }
  }
  const STAR = (filled) => `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" fill="${filled ? "currentColor" : "none"}" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>`;

  // Um botão só, com o estado escrito: "Tornar meu time" ou "Meu time (trocar)". Sem o nome dos botões, o visitante
  // não sabe o que acontece ao tocar.
  function followButton(clubId) {
    const following = favoriteClub() === clubId;
    const label = following ? "Este é o meu time · trocar" : "Tornar este o meu time";
    const hint = following
      ? "Ele aparece no topo da home. Toque em outro clube para trocar."
      : "Ao escolher, a home passa a abrir com ele.";
    return `<div class="follow-box"><button type="button" class="follow-button${following ? " is-following" : ""}" data-follow="${escapeHtml(clubId)}" aria-pressed="${following}">${STAR(following)}<span>${label}</span></button><p class="follow-hint">${hint}</p></div>`;
  }

  function bindFollow(rerender) {
    main.querySelectorAll("[data-follow]").forEach((button) => button.addEventListener("click", () => {
      const clubId = button.dataset.follow;
      setFavoriteClub(favoriteClub() === clubId ? "" : clubId);
      rerender();
    }));
  }

  /* Home centrada no seu time (opção B3 do canvas de UI, escolhida pelo dono em 2026-11-25): a probabilidade da
     disputa em destaque, a variação desde a atualização anterior, a curva recente, o próximo jogo e o simulador. */
  const HERO_LABEL = { titulo: "Título", g4: "G4", rebaixamento: "Queda" };
  const HERO_NOUN = { titulo: "título", g4: "G4", rebaixamento: "queda" };
  const HERO_TONE = { titulo: "", g4: "is-g4", rebaixamento: "is-z4" };
  const HISTORY_POINTS = 10;
  const FEMININE_CLUBS = new Set(["chapecoense"]);

  function openTeamSheet() {
    const teams = [...state.snapshot.teams].sort((left, right) => left.current_position - right.current_position);
    const current = favoriteClub();
    const grid = teams.map((team) => `<button type="button" class="team-tile${team.club_id === current ? " is-current" : ""}" data-pick-club="${escapeHtml(team.club_id)}"${team.club_id === current ? ' aria-pressed="true"' : ""}>${crest(team.club_id, 32)}<span>${escapeHtml(team.name)}</span></button>`).join("");
    window.AIndaDaShell.openSheet("Escolha seu time", `<div class="sheet-grid sheet-grid-teams">${grid}</div>`, (dialog) => {
      dialog.querySelectorAll("[data-pick-club]").forEach((button) => button.addEventListener("click", () => {
        setFavoriteClub(button.dataset.pickClub);
        dialog.close();
        route();
      }));
    });
  }

  /* A disputa que mais diz sobre o time: a mais aberta (p·(1−p)), com o título na frente no empate. */
  function openRaceFor(team) {
    const spread = (id) => { const value = team[RACES[id].key]; return value * (1 - value); };
    return Object.keys(RACES).reduce((best, id) => (spread(id) > spread(best) + 1e-9 ? id : best), "titulo");
  }

  function teamHistory(clubId, key) {
    return state.history
      .map((point) => ({ date: point.reference_date, value: point.teams && point.teams[clubId] ? point.teams[clubId][key] : null }))
      .filter((point) => isProbability(point.value));
  }

  function heroDelta(points, key) {
    if (points.length < 2) return "";
    const [previous, latest] = points.slice(-2);
    const delta = latest.value - previous.value;
    const since = formatDay(previous.date);
    if (Math.abs(delta) < 0.005) return `<span class="hero-delta">estável desde ${since}</span>`;
    const good = key === "relegation" ? delta < 0 : delta > 0;
    return `<span class="hero-delta ${good ? "is-good" : "is-bad"}">${delta > 0 ? "+" : "−"}${Math.round(Math.abs(delta) * 100)} p.p. desde ${since}</span>`;
  }

  /* Curva das últimas atualizações, na escala de 0 a 100% (sem esticar variações pequenas). */
  function sparkline(points, noun) {
    const recent = points.slice(-HISTORY_POINTS);
    if (recent.length < 2) return "";
    const width = 150, height = 64, pad = 5;
    const x = (index) => pad + (index * (width - 2 * pad)) / (recent.length - 1);
    const y = (value) => pad + (1 - value) * (height - 2 * pad);
    const line = recent.map((point, index) => `${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
    const last = recent[recent.length - 1];
    const label = `Probabilidade de ${noun} de ${formatDay(recent[0].date)} a ${formatDay(last.date)}: de ${pct(recent[0].value)} para ${pct(last.value)}`;
    return `<svg class="hero-spark" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${escapeHtml(label)}">
        <line x1="${pad}" x2="${width - pad}" y1="${y(0)}" y2="${y(0)}" class="hero-spark-axis"/><line x1="${pad}" x2="${width - pad}" y1="${y(1)}" y2="${y(1)}" class="hero-spark-axis"/>
        <polyline points="${line}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
        <circle cx="${x(recent.length - 1).toFixed(1)}" cy="${y(last.value).toFixed(1)}" r="3.5" class="hero-spark-dot"/></svg>`;
  }

  function teamHeroSummaryCards(team) {
    return `<div class="whatif"><p class="mc-label">Resumo nas disputas</p><div class="whatif-row">
      <span class="whatif-cell"><span>Título</span><strong>${pct(team.title)}</strong></span>
      <span class="whatif-cell"><span>G4</span><strong>${pct(team.top4)}</strong></span>
      <span class="whatif-cell"><span>Queda</span><strong>${pct(team.relegation)}</strong></span>
    </div></div>`;
  }

  function teamHero(team, raceId, nextMatch = null, ctaHtml = "") {
    const key = RACES[raceId].key;
    const points = teamHistory(team.club_id, key);
    const remaining = state.snapshot.matches.filter((match) => match.status !== "finished" && (match.home_id === team.club_id || match.away_id === team.club_id)).length;
    const chips = Object.keys(RACES).map((id) => `<a class="chip chip-sm" href="#/inicio/${id}"${id === raceId ? ' aria-current="page"' : ""}>${HERO_LABEL[id]}</a>`).join("");
    const sideCards = (nextMatch && nextMatchWhatIf(team, nextMatch, raceId, true)) || teamHeroSummaryCards(team);
    return `<section class="card team-hero" aria-label="Seu time">
      <div class="yt-head">
        <a class="yt-club" href="#/clubes/${encodeURIComponent(team.club_id)}">${crest(team.club_id, 44)}<span class="yt-name"><strong>${escapeHtml(team.name)}</strong><span>${team.current_position}º lugar · ${team.current_points} pts · ${remaining} ${remaining === 1 ? "jogo" : "jogos"}</span></span></a>
        <button type="button" class="chip chip-sm" data-open-teams>Trocar</button>
      </div>
      <nav class="chip-row" aria-label="Disputa">${chips}</nav>
      <div class="hero-grid">
        <div class="hero-main">
          <p class="hero-number ${HERO_TONE[raceId]}"><span class="hero-label">Probabilidade de ${HERO_NOUN[raceId]}</span><strong>${pct(team[key])}</strong>${heroDelta(points, key)}</p>
          ${sparkline(points, HERO_NOUN[raceId])}
        </div>
        <div class="home-pc-hero-side">
          ${sideCards}
          ${ctaHtml}
        </div>
      </div>
    </section>`;
  }

  function teamNextMatch(team, raceId) {
    const match = upcomingMatches().find((item) => !isPostponed(item) && (item.home_id === team.club_id || item.away_id === team.club_id));
    if (!match) return "";
    const mobWhatIf = nextMatchWhatIf(team, match, raceId, false);
    return `<section class="home-block home-next" aria-labelledby="home-next">
      <div class="block-head"><h2 id="home-next">Próximo jogo</h2><a class="block-link" href="#/clubes/${encodeURIComponent(team.club_id)}">Todos os jogos ›</a></div>
      ${matchList([match])}
      ${mobWhatIf ? `<div class="home-mob-whatif">${mobWhatIf}</div>` : ""}
    </section>`;
  }

  /* ---------------- "E se…" do seu time (ADR-0016): probabilidades condicionadas calculadas no navegador, com o
     motor do modo Ao vivo (window.LiveRound.simulate, semente fixa) sobre as probabilidades publicadas no snapshot.
     Uma única rodada de simulações acompanha os próximos jogos: para cada resultado de cada jogo, a fração das
     simulações em que o seu time terminou campeão, no G4 ou rebaixado. Não substitui o número publicado. */
  const WHAT_IF_MATCHES = 20;
  const WHAT_IF_MIN_SAMPLES = 300;
  const WHAT_IF_MIN_SWING = 0.01;
  const WHAT_IF_SHOWN = 3;

  const whatIfKey = (team) => `${team.club_id}|${state.snapshot.generated_at}|${[...state.live.values()].map((row) => `${row.match_id}:${row.status}:${row.home_goals}:${row.away_goals}`).sort().join(",")}`;

  async function computeWhatIf(team) {
    const live = window.LiveRound;
    if (!live || typeof live.simulate !== "function" || !window.Simulator) return;
    const key = whatIfKey(team);
    if (state.whatIf && state.whatIf.key === key) return;
    state.whatIf = { key, status: "loading" };
    try {
      const model = live.prepare(state.snapshot, [...state.live.values()]);
      const matchIds = upcomingMatches().filter((match) => !isPostponed(match)).slice(0, WHAT_IF_MATCHES).map((match) => match.match_id);
      const own = upcomingMatches().find((match) => !isPostponed(match) && (match.home_id === team.club_id || match.away_id === team.club_id));
      if (own && !matchIds.includes(own.match_id)) matchIds.push(own.match_id);
      const result = await live.simulate(model, { track: { clubId: team.club_id, matchIds } });
      if (!state.whatIf || state.whatIf.key !== key) return;
      state.whatIf = { key, status: "done", simulations: result.simulations, byMatch: new Map(result.track.map((entry) => [entry.match_id, entry.outcomes])) };
    } catch (error) {
      if (state.whatIf && state.whatIf.key === key) state.whatIf = { key, status: "error" };
    }
    const [, section = ""] = location.hash.replace(/^#/, "").split("/");
    if (!section || section === "inicio") route();
  }

  const whatIfReady = (team) => state.whatIf && state.whatIf.key === whatIfKey(team) && state.whatIf.status === "done";
  const usable = (bucket, key) => bucket && bucket.n >= WHAT_IF_MIN_SAMPLES && isProbability(bucket[key]);

  /* Os três finais possíveis do próximo jogo, do ponto de vista do seu time. */
  function nextMatchWhatIf(team, match, raceId, showMatch = false) {
    if (!match) return "";
    const key = RACES[raceId].key;
    const prefix = showMatch ? `Se ${escapeHtml(shortOf(match.home_id))} × ${escapeHtml(shortOf(match.away_id))} terminar em…` : "Se o jogo terminar em…";
    if (!whatIfReady(team)) {
      return state.whatIf && state.whatIf.status === "loading" ? `<div class="whatif" aria-busy="true"><p class="mc-label">${prefix}</p><span class="skeleton sk-chips"></span></div>` : "";
    }
    const outcomes = state.whatIf.byMatch.get(match.match_id);
    if (!outcomes) return "";
    const home = match.home_id === team.club_id;
    const options = [["Vitória", home ? "H" : "A"], ["Empate", "D"], ["Derrota", home ? "A" : "H"]];
    const status = matchState(match);
    const current = status.kind === "live" ? engineOutcome(status.home, status.away) : null;
    const cells = options.map(([label, outcome]) => {
      const bucket = outcomes[outcome];
      const value = usable(bucket, key) ? pct(bucket[key]) : "–";
      const now = current === outcome ? `<small>como está</small>` : "";
      return `<span class="whatif-cell${current === outcome ? " is-now" : ""}"><span>${label}</span><strong>${value}</strong>${now}</span>`;
    }).join("");
    return `<div class="whatif"><p class="mc-label">${prefix} · probabilidade de ${HERO_NOUN[raceId]}</p><div class="whatif-row">${cells}</div></div>`;
  }

  const engineOutcome = (home, away) => (home > away ? "H" : home < away ? "A" : "D");

  /* Os jogos cujo resultado mais muda a probabilidade do seu time na disputa escolhida. */
  function mostImpactful(team, raceId) {
    const key = RACES[raceId].key;
    const noun = HERO_NOUN[raceId];
    if (!whatIfReady(team)) {
      if (!state.whatIf || state.whatIf.status !== "loading") return "";
      return `<section class="card home-block impact" aria-busy="true"><h2 class="impact-title">O que mais mexe na sua probabilidade de ${noun}</h2><span class="skeleton sk-row"></span><span class="skeleton sk-row"></span><span class="skeleton sk-row"></span></section>`;
    }
    const byId = new Map(state.snapshot.matches.map((match) => [match.match_id, match]));
    const good = raceId === "rebaixamento" ? (left, right) => left < right : (left, right) => left > right;
    const rows = [...state.whatIf.byMatch.entries()].map(([matchId, outcomes]) => {
      const match = byId.get(matchId);
      const valid = Object.entries(outcomes).filter(([, bucket]) => usable(bucket, key));
      if (!match || valid.length < 2) return null;
      const sorted = [...valid].sort(([, left], [, right]) => (good(left[key], right[key]) ? -1 : good(right[key], left[key]) ? 1 : 0));
      const best = sorted[0], worst = sorted[sorted.length - 1];
      return { match, best, worst, swing: Math.abs(best[1][key] - worst[1][key]) };
    }).filter((row) => row && row.swing >= WHAT_IF_MIN_SWING).sort((left, right) => right.swing - left.swing).slice(0, WHAT_IF_SHOWN);
    const outcomeText = (match, outcome) => (outcome === "D" ? "empate" : `vitória do ${escapeHtml(shortOf(outcome === "H" ? match.home_id : match.away_id))}`);
    const list = rows.map((row) => `<div class="impact-row">
        <span class="impact-match">${escapeHtml(nameOf(row.match.home_id))} × ${escapeHtml(nameOf(row.match.away_id))}<small>${cardDay(row.match.match_date)} · R${row.match.round ?? "?"}</small></span>
        <span class="impact-outcomes"><span class="is-best">${outcomeText(row.match, row.best[0])}: <strong>${pct(row.best[1][key])}</strong></span><span class="is-worst">${outcomeText(row.match, row.worst[0])}: <strong>${pct(row.worst[1][key])}</strong></span></span>
      </div>`).join("");
    const empty = `<p class="state-text">Nenhum dos próximos ${WHAT_IF_MATCHES} jogos muda a sua probabilidade de ${noun} em 1 ponto percentual ou mais.</p>`;
    return `<section class="card home-block impact" aria-labelledby="impact-title">
      <div class="block-head"><h2 class="impact-title" id="impact-title">O que mais mexe na sua probabilidade de ${noun}</h2>${infoButton("Como este cálculo é feito")}</div>
      ${list || empty}
      <p class="impact-note">Calculado no seu navegador: ${state.whatIf.simulations.toLocaleString("pt-BR")} simulações dos próximos jogos.</p>
    </section>`;
  }

  const WHAT_IF_EXPLANATION = `<p>Estes números são calculados no seu navegador, com o mesmo motor do modo Ao vivo: ele sorteia o resto do campeonato com as probabilidades de cada jogo publicadas nesta edição (e, se houver, com o placar ao vivo).</p>
    <p>Para cada resultado de um jogo, mostramos em que fração das simulações com aquele resultado o seu time terminou campeão, no G4 ou rebaixado. São probabilidades condicionadas: valem se aquele resultado acontecer.</p>
    <p>Como é outra rodada de simulações, os números podem diferir um pouco do número grande publicado acima. Resultados com menos de ${WHAT_IF_MIN_SAMPLES} simulações aparecem como "–".</p>`;

  function emptyTeamCard() {
    return `<section class="card your-team is-empty" aria-label="Seu time"><p class="yt-empty">Escolha seu time</p><button type="button" class="btn-secondary btn-sm" data-open-teams>Escolher</button></section>`;
  }

  /* Estados de carregamento, vazio e erro (REDESIGN_SPEC v2.1 §3.7). */
  const STATE_ICONS = {
    calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    offline: '<path d="M3 9a14 14 0 0 1 18 0M6.5 12.5a9 9 0 0 1 11 0M10 16a4 4 0 0 1 4 0"/><path d="M4 4l16 16"/>',
    table: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16M4 14h16M10 9v11"/>',
  };
  function stateBlock({ icon, title, text, action = "", role = "" }) {
    return `<div class="state"${role ? ` role="${role}"` : ""}>
      <svg viewBox="0 0 24 24" width="36" height="36" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${STATE_ICONS[icon]}</svg>
      <p class="state-title">${title}</p>${text ? `<p class="state-text">${text}</p>` : ""}${action}</div>`;
  }

  function skeleton(section) {
    if (section === "simular" && window.AIndaDaLoading) {
      return window.AIndaDaLoading.html("Carregando o simulador…", { page: true, detail: "Buscando as probabilidades de cada jogo." });
    }
    const chips = `<span class="skeleton sk-chips"></span>`;
    let body;
    if (section === "classificacao") body = `<span class="skeleton sk-title"></span>${chips}${Array.from({ length: 10 }, () => `<span class="skeleton sk-row"></span>`).join("")}`;
    else if (section === "partidas" || section === "jogos") body = `<span class="skeleton sk-title"></span>${chips}<div class="mc-list">${Array.from({ length: 4 }, () => `<span class="skeleton sk-card"></span>`).join("")}</div>`;
    else body = `<span class="skeleton sk-team"></span><span class="skeleton sk-title"></span><div class="mc-list">${Array.from({ length: 2 }, () => `<span class="skeleton sk-card"></span>`).join("")}</div><span class="skeleton sk-block"></span>`;
    return `<div class="skeleton-page" aria-busy="true"><span class="visually-hidden">Carregando as probabilidades…</span>${body}</div>`;
  }

  const ROUND_TAB = "rodada";
  const TOP_RACE_ROWS = 5;
  const HOME_MATCHES = 4;

  // Mesmo dia: por horário de início; jogo sem horário confirmado vai para o fim do dia.
  const kickoffStamp = (match) => { const stamp = Date.parse(match.kickoff_utc || ""); return Number.isNaN(stamp) ? Infinity : stamp; };
  const byKickoff = (left, right) => String(left.match_date).localeCompare(String(right.match_date))
    || (kickoffStamp(left) === kickoffStamp(right) ? 0 : kickoffStamp(left) < kickoffStamp(right) ? -1 : 1);

  const HOME_FINISHED = 4;

  /* Próximos jogos da Home: os HOME_MATCHES mais cedo, agrupados por dia; no PC equilibra com a coluna esquerda. */
  function homeMatches(skipId = null) {
    const upcoming = upcomingMatches().filter((match) => !isPostponed(match) && match.match_id !== skipId);
    const recent = finishedMatches().slice(0, HOME_FINISHED);
    const list = upcoming.length ? upcoming.slice(0, HOME_MATCHES) : recent;
    if (!list.length) return "";
    const pcList = list.slice(0, skipId ? 2 : 3);
    const analysis = state.currentRound ? `<a class="block-link" href="#/inicio/${ROUND_TAB}">O que mudou na rodada ${state.currentRound.number} ›</a>` : "";
    const title = upcoming.length ? "Próximos jogos" : "Últimos resultados";
    return `<section class="home-block home-matches" aria-labelledby="home-round">
      <div class="block-head"><h2 id="home-round">${title}</h2><a class="block-link" href="#/jogos">Ver a agenda ›</a></div>
      ${predictionNote()}
      <div class="home-matches-mob">${matchesByDay(list)}</div>
      <div class="home-matches-pc">${matchesByDay(pcList)}</div>
      ${analysis}
    </section>`;
  }

  function disputesCard(raceId) {
    const race = RACES[raceId];
    const top = raceTeams(race).slice(0, TOP_RACE_ROWS);
    const chips = Object.entries(RACES).map(([id, item]) => `<a class="chip" href="#/inicio/${id}"${id === raceId ? ' aria-current="page"' : ""}>${item.label}</a>`).join("");
    const rows = top.map((team) => `<a class="race-line" href="#/clubes/${encodeURIComponent(team.club_id)}">
        ${crest(team.club_id, 26)}<span class="race-line-name">${escapeHtml(team.name)}</span><strong>${pct(team[race.key])}</strong>
        <span class="race-line-bar" aria-hidden="true"><i style="width:${(team[race.key] * 100).toFixed(1)}%;background:${race.color}"></i></span></a>`).join("");
    return `<section class="card home-block disputes" aria-labelledby="home-races">
      <div class="block-head"><h2 id="home-races">Disputas</h2><a class="block-link" href="#/classificacao/${race.briga}">Tabela ›</a></div>
      <nav class="chip-row" aria-label="Escolha a disputa">${chips}</nav>
      <div class="race-lines">${rows || `<p class="state-text">Nenhum clube com probabilidade nesta disputa.</p>`}</div>
      <details class="mosaic-details"><summary>Ver o mosaico da disputa</summary>${raceMosaic(race)}</details>
    </section>`;
  }

  function bindHome() {
    main.querySelectorAll("[data-open-teams]").forEach((button) => button.addEventListener("click", openTeamSheet));
  }

  function renderRoundAnalysis() {
    const renderer = window.CurrentRound.createRenderer({ escapeHtml, pct, crest, clubLink, nameOf, shortOf, formatDate });
    main.innerHTML = `<a class="back-link" href="#/">‹ Início</a>${renderer.render(state.currentRound, state.snapshot, Date.now(), overdueWarning(), false)}`;
  }

  function renderHome(requested) {
    if (requested === ROUND_TAB && state.currentRound) {
      renderRoundAnalysis();
      return;
    }
    const team = teamById(favoriteClub());
    if (!team) {
      const raceId = RACES[requested] ? requested : featuredRace().id;
      main.innerHTML = `<h1 class="visually-hidden">Início</h1><div class="home-v43-empty">${emptyTeamCard()}${homeMatches()}${disputesCard(raceId)}</div>`;
      bindHome();
      return;
    }
    const raceId = RACES[requested] ? requested : openRaceFor(team);
    const next = upcomingMatches().find((item) => !isPostponed(item) && (item.home_id === team.club_id || item.away_id === team.club_id));
    const article = FEMININE_CLUBS.has(team.club_id) ? "da" : "do";
    const ctaHtml = `<a class="btn-primary yt-cta" href="#/simular">Simular jogos ${article} ${escapeHtml(team.name)}</a>`;
    const nextBlock = teamNextMatch(team, raceId);
    const impactBlock = mostImpactful(team, raceId);
    const matchesBlock = homeMatches(next ? next.match_id : null);
    main.innerHTML = `<h1 class="visually-hidden">Início</h1>
      <div class="home-v43${nextBlock ? "" : " no-next"}">
        ${teamHero(team, raceId, next, ctaHtml)}
        ${nextBlock}
        <div class="home-pc-left">${impactBlock}<div class="home-pc-disputes">${disputesCard(raceId)}</div></div>
        <a class="btn-primary yt-cta home-cta" href="#/simular">Simular jogos ${article} ${escapeHtml(team.name)}</a>
        ${matchesBlock}
      </div>`;
    bindHome();
    bindScreenInfo("Como este cálculo é feito", WHAT_IF_EXPLANATION);
    computeWhatIf(team);
  }

  /* Cenários externos em chips (REDESIGN_SPEC v2.1 §3.4): só os torneios ainda em aberto aparecem. */
  function scenarioStatus() {
    const chosen = Object.keys(state.scenarioChoice).length;
    const remaining = matchingScenarios().length;
    if (!chosen) return `Faixa entre ${state.snapshot.scenarios.length} cenários`;
    if (remaining === 1) return "Cenário completo";
    return `Faixa entre ${remaining} cenários`;
  }

  function scenarioPanel() {
    const choice = state.scenarioChoice;
    const open = SCENARIO_KEYS.filter(([key]) => new Set(state.snapshot.scenarios.map((scenario) => scenario[key])).size > 1);
    if (!open.length) return "";
    const LABELS = { libertadores_champion: "Liberta", sudamericana_champion: "Sul-Americana", cup_champion: "Copa BR", cup_runner_up: "Vice Copa BR" };
    const rowFor = ([key]) => {
      const others = Object.fromEntries(Object.entries(choice).filter(([other]) => other !== key));
      const options = [...new Set(matchingScenarios(others).map((scenario) => scenario[key]))].sort((left, right) => left.localeCompare(right, "pt-BR"));
      const chip = (value, label) => `<button type="button" class="chip chip-sm" data-scenario-key="${key}" data-scenario-value="${escapeHtml(value)}" aria-pressed="${(choice[key] || "") === value}">${escapeHtml(label)}</button>`;
      return `<div class="scenario-row"><span class="scenario-label">${LABELS[key]}</span><div class="chip-row">${chip("", "Em aberto")}${options.map((value) => chip(value, value)).join("")}</div></div>`;
    };
    return `<section class="card scenario-card" aria-labelledby="scenario-title">
      <div class="block-head"><h2 id="scenario-title">Vagas extras</h2><span class="scenario-status" aria-live="polite">${scenarioStatus()}</span></div>
      ${open.map(rowFor).join("")}
    </section>`;
  }

  function bindScenarioPanel(rerender) {
    main.querySelectorAll("[data-scenario-key]").forEach((button) => button.addEventListener("click", () => {
      const { scenarioKey, scenarioValue: value } = button.dataset;
      if (value) state.scenarioChoice[scenarioKey] = value;
      else delete state.scenarioChoice[scenarioKey];
      rerender();
      const again = main.querySelector(`[data-scenario-key="${scenarioKey}"][data-scenario-value="${CSS.escape(value)}"]`);
      if (again) again.focus();
    }));
  }

  const elo = (team) => Math.round(team.ratings.elo);
  const rankOf = (team, accessor) => [...state.snapshot.teams].sort((left, right) => accessor(right) - accessor(left)).indexOf(team) + 1;

  const TABLE_VIEWS = {
    geral: {
      label: "Geral",
      head: ["Título", "G4", "Z4"],
      sort: [(team) => team.title, (team) => team.top4, (team) => team.relegation],
      cells: (team) => [probCell(team.title, "title"), probCell(team.top4, "lib"), probCell(team.relegation, "danger")],
    },
    titulo: {
      label: "Título",
      head: ["Título"],
      sort: [(team) => team.title],
      cells: (team) => [probCell(team.title, "title")],
    },
    libertadores: {
      label: "Libertadores",
      scenarios: true,
      head: ["G4", "Liberta. grupos", "Liberta. total"],
      sort: [(team) => team.top4, (team) => scenarioMid(team.libertadores_groups), (team) => scenarioMid(team.libertadores_total)],
      cells: (team) => [probCell(team.top4, "lib"), scenarioValue(team.libertadores_groups), scenarioValue(team.libertadores_total)],
      caption: "G4 = terminar entre os quatro primeiros. Liberta. grupos e total incluem as vagas que dependem de Libertadores, Sul-Americana e Copa do Brasil: sem cenário escolhido, mostramos a faixa entre todos os cenários.",
    },
    "sul-americana": {
      label: "Sul-Americana",
      scenarios: true,
      head: ["Corrida", "Sul-Americana", "Vale em todos os cenários"],
      sort: [
        { value: (team) => (team.sudamericana_race ? team.sudamericana_race.rank : 99), ascending: true },
        (team) => scenarioMid(team.sudamericana),
        (team) => (team.sudamericana_race ? team.sudamericana_race.all_scenarios : -1),
      ],
      order: (team) => (team.sudamericana_race ? team.sudamericana_race.rank : team.current_position),
      cells: (team) => {
        const race = team.sudamericana_race;
        if (!race) return ["–", scenarioValue(team.sudamericana), "–"];
        const spread = race.rank_best === race.rank_worst ? "" : ` <span class="rank">${race.rank_best}º a ${race.rank_worst}º</span>`;
        return [`<strong>${race.rank}º</strong>${spread}`, scenarioValue(team.sudamericana), pct(race.all_scenarios)];
      },
      caption: "Ordenada pela corrida da Sul-Americana: a vaga depende de quem ganha Libertadores, Sul-Americana e Copa do Brasil, então a coluna Sul-Americana mostra a faixa entre os cenários (ou só os que combinam com a sua escolha), e Corrida mostra a posição do clube nessa disputa e, em cinza, a melhor e a pior conforme o cenário. Vale em todos os cenários = probabilidade de terminar com a vaga seja quem for campeão desses torneios.",
    },
    rebaixamento: {
      label: "Z4",
      head: ["Rebaix."],
      sort: [(team) => team.relegation],
      cells: (team) => [probCell(team.relegation, "danger")],
    },
    forca: {
      label: "Força",
      head: ["Elo", "Ataque", "Defesa"],
      sort: [(team) => team.ratings.elo, (team) => team.ratings.attack, (team) => team.ratings.defense],
      cells: (team) => [
        `${elo(team)} <span class="rank">${rankOf(team, (item) => item.ratings.elo)}º</span>`,
        `${signedPercent(team.ratings.attack)} <span class="rank">${rankOf(team, (item) => item.ratings.attack)}º</span>`,
        `${signedPercent(team.ratings.defense)} <span class="rank">${rankOf(team, (item) => item.ratings.defense)}º</span>`,
      ],
      caption: "Elo: força geral; 1500 é a média da liga. Ataque: gols marcados em relação à média, já descontada a força dos adversários. Defesa: positivo significa sofrer menos gols que a média. Em cinza, a posição do clube em cada quesito.",
    },
    dificuldade: {
      label: "Dificuldade da tabela",
      head: ["Dificuldade", "Em casa", "Fora", "Pts esp. casa", "Pts esp. fora", "Próximos jogos"],
      sort: [
        (team) => (team.schedule ? team.schedule.difficulty : -1),
        (team) => (team.schedule && team.schedule.difficulty_home !== null ? team.schedule.difficulty_home : -1),
        (team) => (team.schedule && team.schedule.difficulty_away !== null ? team.schedule.difficulty_away : -1),
        (team) => (team.schedule ? team.schedule.expected_points_home : -1),
        (team) => (team.schedule ? team.schedule.expected_points_away : -1),
        null,
      ],
      order: (team) => (team.schedule ? team.schedule.difficulty_rank : team.current_position),
      cells: (team) => {
        const schedule = team.schedule;
        const upcoming = upcomingCrests(team);
        if (!schedule) return ["–", "–", "–", "–", "–", upcoming];
        return [
          difficultyCell(schedule.difficulty, schedule.difficulty_rank),
          difficultyCell(schedule.difficulty_home, schedule.difficulty_home_rank),
          difficultyCell(schedule.difficulty_away, schedule.difficulty_away_rank),
          `${num(schedule.expected_points_home)} <span class="rank">em ${schedule.home_matches}</span>`,
          `${num(schedule.expected_points_away)} <span class="rank">em ${schedule.away_matches}</span>`,
          upcoming,
        ];
      },
    },
  };
  const standingOf = (team) => state.snapshot.standings.find((entry) => entry.club_id === team.club_id);
  const FIXED_COLUMNS = [
    { id: "pos", label: "#", value: (team) => team.current_position, ascending: true },
    { id: "clube", label: "Clube", left: true, value: (team) => team.name, ascending: true },
    { id: "pts", label: "Pts", value: (team) => standingOf(team).points },
    { id: "j", label: "J", value: (team) => standingOf(team).played },
    { id: "v", label: "V", value: (team) => standingOf(team).wins },
    { id: "sg", label: "SG", value: (team) => standingOf(team).goal_difference },
    { id: "proj", label: "Pts proj.", value: (team) => team.expected_points },
    { id: "posmedia", label: "Pos. média", value: (team) => team.expected_position, ascending: true },
  ];

  function tableColumns(view) {
    const extra = view.head.map((label, index) => {
      const spec = view.sort ? view.sort[index] : null;
      if (!spec) return { id: null, label };
      const sorter = typeof spec === "function" ? { value: spec } : spec;
      return { id: `v${index}`, label, value: sorter.value, ascending: Boolean(sorter.ascending) };
    });
    // Colunas da visão logo depois de Pts: no celular o percentual principal aparece sem rolar a tabela de lado.
    return [...FIXED_COLUMNS.slice(0, LEAD_COLUMNS), ...extra, ...FIXED_COLUMNS.slice(LEAD_COLUMNS)];
  }
  const LEAD_COLUMNS = 3;

  function compareBy(column, direction) {
    return (left, right) => {
      const a = column.value(left), b = column.value(right);
      const base = typeof a === "string" ? a.localeCompare(b, "pt-BR") : a - b;
      return base * direction || left.current_position - right.current_position;
    };
  }

  const UPCOMING_SHOWN = 5;

  function difficultyCell(value, rank = null) {
    if (value === null || value === undefined) return "–";
    return `<span class="difficulty" style="--d:${Math.min(1, Math.max(0, value / 100))}">${Math.round(value)}</span>${rank ? ` <span class="rank">${rank}º</span>` : ""}`;
  }

  const matchById = (matchId) => state.snapshot.matches.find((match) => match.match_id === matchId);

  function upcomingCrests(team) {
    const clubId = team.club_id;
    const fromSchedule = team.schedule && team.schedule.matches
      ? team.schedule.matches.map((item) => ({ ...item, match: matchById(item.match_id) })).filter((item) => !item.match || !isPostponed(item.match))
      : state.snapshot.matches.filter((match) => match.status !== "finished" && !isPostponed(match) && (match.home_id === clubId || match.away_id === clubId))
        .map((match) => ({ opponent_id: match.home_id === clubId ? match.away_id : match.home_id, venue: match.home_id === clubId ? "home" : "away", difficulty: null }));
    return `<span class="upcoming">${fromSchedule.slice(0, UPCOMING_SHOWN).map((item) => {
      const home = item.venue === "home";
      const level = item.difficulty === null || item.difficulty === undefined ? "" : ` · dificuldade ${Math.round(item.difficulty)}`;
      const tint = level ? ` style="--d:${Math.min(1, Math.max(0, item.difficulty / 100))}"` : "";
      return `<span class="upcoming-match${level ? " rated" : ""}"${tint} title="${home ? "Em casa" : "Fora"} contra ${escapeHtml(nameOf(item.opponent_id))}${level}">${crest(item.opponent_id, 18)}<span class="venue">${home ? "C" : "F"}</span></span>`;
    }).join("")}</span>`;
  }

  function difficultyNote() {
    const sample = state.snapshot.teams.find((team) => team.schedule);
    if (!sample) return `<p class="note">O índice de dificuldade da tabela ainda não está nesta atualização. Por enquanto, a coluna mostra os próximos adversários (C = em casa, F = fora).</p>`;
    return `<p class="note">Dificuldade de 0 a 100: 50 é uma tabela média do campeonato; quanto maior, menos pontos um time comum faria nesses jogos. Jogar fora é sempre mais difícil que em casa, por isso compare casa com casa e fora com fora (em cinza, a posição entre os 20; 1º = mais difícil). Pts esp. = pontos esperados nos jogos que faltam, já com a força do clube. Próximos jogos: C = em casa, F = fora; fundo mais forte = jogo mais difícil.</p>`;
  }

  function tableTabs(selected) {
    return `<nav class="chip-strip" aria-label="Visão da tabela"><a class="chip" href="#/classificacao">‹ Disputas</a>${Object.entries(TABLE_VIEWS).map(([id, view]) =>
      `<a class="chip" href="#/classificacao/${id}"${id === selected ? ' aria-current="page"' : ""}>${view.label}</a>`).join("")}</nav>`;
  }

  const infoButton = (label) => `<button type="button" class="icon-button" data-screen-info aria-label="${label}"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg></button>`;

  function bindScreenInfo(title, body) {
    const button = main.querySelector("[data-screen-info]");
    if (button) button.addEventListener("click", () => window.AIndaDaShell.openSheet(title, `<div class="sheet-info">${body}</div>`));
  }

  /* Classificação por disputa (opção C2): quem já está garantido nas simulações, quem está na briga e quem está fora.
     A tabela completa continua a um toque (#/classificacao/geral e as outras visões). */
  const SURE = 0.99;
  const OUT = 0.01;
  const BRIGA_RACE = { "briga-titulo": "titulo", "briga-g4": "g4", "briga-z4": "rebaixamento" };
  const RACE_GROUPS = {
    titulo: { sure: "Campeão em quase todas as simulações", open: "Na briga pelo título", out: "Sem probabilidade relevante de título", unit: ["vaga", "vagas"] },
    g4: { sure: "No G4 em quase todas as simulações", open: "Na briga pelo G4", out: "Fora da briga pelo G4", unit: ["vaga", "vagas"] },
    rebaixamento: { sure: "Caem em quase todas as simulações", open: "Ainda correm risco de queda", out: "Longe da queda", unit: ["queda", "quedas"] },
  };

  function raceRow(team, race, withNext) {
    const mine = team.club_id === favoriteClub();
    const next = withNext ? upcomingMatches().find((match) => !isPostponed(match) && (match.home_id === team.club_id || match.away_id === team.club_id)) : null;
    const nextText = next ? ` · próximo: ${escapeHtml(shortOf(next.home_id === team.club_id ? next.away_id : next.home_id))} (${next.home_id === team.club_id ? "casa" : "fora"})` : "";
    const [low, high] = team.points_interval_90 || [];
    const range = Number.isFinite(low) && Number.isFinite(high) ? ` · termina com ${Math.round(low)} a ${Math.round(high)}` : "";
    const value = team[race.key];
    return `<a class="race-row-card${mine ? " is-mine" : ""}" href="#/clubes/${encodeURIComponent(team.club_id)}">
        <span class="rr-pos">${team.current_position}</span>${crest(team.club_id, 26)}
        <span class="rr-name">${escapeHtml(team.name)}${mine ? ` <span class="rr-mine">· seu time</span>` : ""}</span>
        <span class="rr-meta">${team.current_points} pts${withNext ? nextText : range}</span>
        <strong class="rr-value">${pct(value)}</strong>
        <span class="rr-bar" aria-hidden="true"><i style="width:${(Math.min(1, Math.max(0, value)) * 100).toFixed(1)}%;background:${race.color}"></i></span></a>`;
  }

  function renderRaces(raceId) {
    const race = RACES[raceId];
    const words = RACE_GROUPS[raceId];
    const teams = [...state.snapshot.teams].sort((left, right) => right[race.key] - left[race.key] || left.current_position - right.current_position);
    const sure = teams.filter((team) => team[race.key] >= SURE);
    const open = teams.filter((team) => team[race.key] >= OUT && team[race.key] < SURE);
    const out = teams.filter((team) => team[race.key] < OUT).sort((left, right) => left.current_position - right.current_position);
    const left = Math.max(0, race.slots - sure.length);
    const chips = Object.entries(RACES).map(([id, item]) => `<a class="chip" href="#/classificacao/${item.briga}"${id === raceId ? ' aria-current="page"' : ""}>${item.label}</a>`).join("")
      + `<a class="chip" href="#/classificacao/geral">Tabela completa</a>`;
    const group = (title, aside, list, withNext) => (list.length
      ? `<section class="race-group"><h2 class="rg-title">${title}<span>${aside}</span></h2><div class="rg-list">${list.map((team) => raceRow(team, race, withNext)).join("")}</div></section>` : "");
    const outBlock = out.length
      ? `<details class="race-group rg-out"><summary class="rg-title">${words.out}<span>${out.length} ${out.length === 1 ? "clube" : "clubes"} abaixo de 1%</span></summary><div class="rg-list">${out.map((team) => raceRow(team, race, false)).join("")}</div></details>` : "";
    const explanation = `<p>Cada porcentagem diz em quantas das ${state.snapshot.n_simulations.toLocaleString("pt-BR")} simulações do resto do campeonato o clube terminou com ${race.noun}.</p>
      <p>"Em quase todas as simulações" = 99% ou mais. Isso não é certeza matemática: o clube só está garantido quando a tabela não permite outro resultado.</p>
      <p>"Na briga" = de 1% a 99%. Abaixo de 1%, o clube fica no grupo recolhido; 0% quer dizer que não aconteceu em nenhuma simulação, não que seja impossível.</p>
      <p>"Termina com" = faixa de pontos onde terminam 90% das simulações.</p>`;
    main.innerHTML = `
      <div class="screen-head"><h1 class="screen-title">Classificação</h1>${infoButton("Como ler a classificação por disputa")}</div>
      <nav class="chip-strip" aria-label="Disputa">${chips}</nav>
      ${group(words.sure, "em 99% ou mais", sure, false)}
      ${group(words.open, `${left} ${left === 1 ? words.unit[0] : words.unit[1]} · ${open.length} ${open.length === 1 ? "clube" : "clubes"}`, open, true)}
      ${outBlock}`;
    bindScreenInfo("Como ler a classificação por disputa", explanation);
  }

  function renderStandings(requested) {
    const snapshot = state.snapshot;
    if (snapshot.teams.length && !TABLE_VIEWS[requested]) {
      const team = teamById(favoriteClub());
      renderRaces(BRIGA_RACE[requested] || (team ? openRaceFor(team) : featuredRace().id));
      return;
    }
    if (!snapshot.teams.length || !snapshot.standings.length) {
      main.innerHTML = `<div class="screen-head"><h1 class="screen-title">Tabela</h1></div>
        ${stateBlock({ icon: "table", title: "A tabela ainda não está nesta atualização", text: "Ela aparece aqui assim que a fonte de dados registrar os primeiros jogos.", action: `<a class="state-action btn-secondary" href="#/">Voltar ao início</a>` })}`;
      return;
    }
    const viewId = TABLE_VIEWS[requested] ? requested : "geral";
    const view = TABLE_VIEWS[viewId];
    const columns = tableColumns(view);
    const chosen = state.tableSort && state.tableSort.view === viewId ? columns.find((column) => column.id === state.tableSort.id) : null;
    const order = view.order || ((team) => team.current_position);
    const teams = chosen
      ? [...snapshot.teams].sort(compareBy(chosen, state.tableSort.direction))
      : [...snapshot.teams].sort((left, right) => order(left) - order(right) || left.current_position - right.current_position);
    const viewCount = view.head.length;
    const restStart = LEAD_COLUMNS + viewCount;
    const lastIsUpcoming = viewId === "dificuldade";
    const cellClass = (index) => [
      viewCount && index === LEAD_COLUMNS ? "view-start" : "",
      viewCount && index === restStart ? "rest-start" : "",
      lastIsUpcoming && index === restStart - 1 ? "left" : "",
    ].filter(Boolean).join(" ");
    const rows = teams.map((team) => {
      const zone = team.current_position <= 5 ? "zone-lib" : team.current_position <= 11 ? "zone-sula" : team.current_position > 16 ? "zone-z4" : "";
      const standing = standingOf(team);
      return `<tr class="${zone}">
        <td class="pos">${team.current_position}</td>
        <td class="left club"><a class="club-cell" href="#/clubes/${encodeURIComponent(team.club_id)}" title="${escapeHtml(team.name)}">${crest(team.club_id, 22)}<span class="name-full">${escapeHtml(team.name)}</span><span class="name-short" aria-hidden="true">${escapeHtml(shortOf(team.club_id))}</span></a></td>
        <td><strong>${standing.points}</strong></td>
        ${view.cells(team).map((cell, index) => `<td class="${cellClass(LEAD_COLUMNS + index)}">${cell}</td>`).join("")}
        <td class="${cellClass(restStart)}">${standing.played}</td><td>${standing.wins}</td><td>${standing.goal_difference > 0 ? "+" : ""}${standing.goal_difference}</td>
        <td><strong>${num(team.expected_points)}</strong><div class="range" title="Faixa provável">${Math.round(team.points_interval_90[0])}–${Math.round(team.points_interval_90[1])}</div></td>
        <td>${num(team.expected_position)}</td>
      </tr>`;
    }).join("");
    const head = columns.map((column, index) => {
      const classes = `${column.left ? "left " : ""}${cellClass(index)}`.trim();
      if (!column.id) return `<th class="${classes}">${column.label}</th>`;
      const active = chosen && chosen.id === column.id;
      const ariaSort = active ? (state.tableSort.direction > 0 ? "ascending" : "descending") : "none";
      const mark = active ? (state.tableSort.direction > 0 ? "▲" : "▼") : "";
      return `<th class="${classes}" aria-sort="${ariaSort}"><button type="button" class="sort-button" data-sort="${column.id}">${column.label}<span class="sort-mark" aria-hidden="true">${mark}</span></button></th>`;
    }).join("");
    const explanation = `<p>A tabela real em ${formatDate(snapshot.reference_date)} ao lado do que as simulações projetam para o fim. Toque no nome de uma coluna para ordenar.</p>
      <p>Pts proj. = média simulada de pontos no fim; embaixo, a faixa provável, onde terminam 90% das simulações. Nas temporadas passadas, a pontuação final ficou dentro dela menos vezes que isso. Pos. média = posição final média nas simulações.</p>
      <p>Faixa lateral: azul = G5 (Libertadores pelo Brasileirão), âmbar = faixa típica da Sul-Americana, vermelho = Z4.</p>
      ${view.caption ? `<p>${view.caption}</p>` : ""}${viewId === "dificuldade" ? difficultyNote() : ""}`;
    main.innerHTML = `
      <div class="screen-head"><h1 class="screen-title">Tabela</h1>${infoButton("Como ler a tabela")}</div>
      ${tableTabs(viewId)}
      ${view.scenarios ? scenarioPanel() : ""}
      <div class="table-scroll table-card"><table class="standings">
        <thead><tr>${head}</tr></thead>
        <tbody>${rows}</tbody></table></div>
      ${chosen ? `<button type="button" class="chip chip-sm table-reset" id="sort-reset">Voltar à ordem padrão</button>` : ""}`;
    bindScreenInfo("Como ler a tabela", explanation);
    main.querySelector("thead").addEventListener("click", (event) => {
      const button = event.target.closest("[data-sort]");
      if (!button) return;
      const column = columns.find((item) => item.id === button.dataset.sort);
      const same = chosen && chosen.id === column.id;
      const direction = same ? -state.tableSort.direction : (column.ascending ? 1 : -1);
      state.tableSort = { view: viewId, id: column.id, direction };
      renderStandings(viewId);
      const again = main.querySelector(`[data-sort="${column.id}"]`);
      if (again) again.focus();
    });
    const reset = document.getElementById("sort-reset");
    if (reset) reset.addEventListener("click", () => { state.tableSort = null; renderStandings(viewId); });
    if (view.scenarios) bindScenarioPanel(() => renderStandings(viewId));
  }

  const NOISE_Z = 3;
  const MIN_ANNOTATED_JUMP = 0.05;
  const formatDay = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

  function openMetric(history) {
    const latest = history[history.length - 1] || {};
    return ["title", "top4", "relegation"].sort((left, right) => {
      const spread = (key) => (latest[key] || 0) * (1 - (latest[key] || 0));
      return spread(right) - spread(left) || (latest[right] || 0) - (latest[left] || 0);
    })[0];
  }

  function chartAnnotations(values) {
    const notes = [];
    let jump = null;
    for (let index = 1; index < values.length; index += 1) {
      const before = values[index - 1], after = values[index];
      const n0 = state.history[index - 1].n_simulations, n1 = state.history[index].n_simulations;
      const noise = Math.sqrt(before * (1 - before) / n0 + after * (1 - after) / n1);
      const delta = after - before;
      if (Math.abs(delta) < Math.max(MIN_ANNOTATED_JUMP, NOISE_Z * noise)) continue;
      if (!jump || Math.abs(delta) > Math.abs(jump.delta)) jump = { index, delta };
    }
    if (jump) {
      const sign = jump.delta > 0 ? "+" : "−";
      notes.push({ index: jump.index, above: jump.delta > 0, text: `maior ${jump.delta > 0 ? "alta" : "queda"}: ${sign}${Math.round(Math.abs(jump.delta) * 100)} p.p. em ${formatDay(state.history[jump.index].reference_date)}` });
    }
    const peakIndex = values.reduce((best, value, index) => (value > values[best] ? index : best), 0);
    const isLast = peakIndex === values.length - 1;
    if (values[peakIndex] >= 0.05 && !isLast && (!jump || Math.abs(peakIndex - jump.index) > 2)) {
      notes.push({ index: peakIndex, above: true, text: `pico: ${pct(values[peakIndex])} em ${formatDay(state.history[peakIndex].reference_date)}` });
    }
    return notes;
  }

  const NARROW = 560;
  const isNarrow = () => main.clientWidth < NARROW;

  function revealActive(strip) {
    const active = strip && strip.querySelector('[aria-current="page"]');
    if (!active || strip.scrollWidth <= strip.clientWidth) return;
    const hidden = active.offsetLeft < strip.scrollLeft || active.offsetLeft + active.offsetWidth > strip.scrollLeft + strip.clientWidth;
    if (hidden) strip.scrollLeft = Math.max(0, active.offsetLeft - 16);
  }

  function lineChart(series, height = 240, annotated = null) {
    if (!state.history.length) return "<p class='note'>Sem histórico.</p>";
    const width = isNarrow() ? 380 : 640, left = 36, right = isNarrow() ? 112 : 128, top = 26, bottom = 28;
    const points = state.history.length;
    const x = (index) => left + (points === 1 ? 0 : (index / (points - 1)) * (width - left - right));
    const y = (value) => top + (1 - value) * (height - top - bottom);
    const grid = [0, 0.25, 0.5, 0.75, 1].map((value) => `<line class="axis" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"/><text x="4" y="${y(value) + 4}">${Math.round(value * 100)}%</text>`).join("");
    const first = state.history[0].reference_date, last = state.history[points - 1].reference_date;
    const lines = series.map((item) => {
      const path = item.values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join("");
      return `<path d="${path}" fill="none" stroke="${item.color}" stroke-width="2.5"/>`;
    }).join("");
    const ends = series.map((item) => ({ item, y: y(item.values[item.values.length - 1]) })).sort((a, b) => a.y - b.y);
    for (let index = 1; index < ends.length; index += 1) ends[index].y = Math.max(ends[index].y, ends[index - 1].y + 14);
    const floor = height - bottom;
    for (let index = ends.length - 1; index >= 0; index -= 1) {
      const limit = index === ends.length - 1 ? floor : ends[index + 1].y - 14;
      ends[index].y = Math.min(ends[index].y, limit);
    }
    const labels = ends.map(({ item, y: labelY }) => `<text class="series-end" x="${width - right + 8}" y="${(labelY + 4).toFixed(1)}" style="fill:${item.color}">${escapeHtml(isNarrow() && item.short ? item.short : item.label)} ${pct(item.values[item.values.length - 1])}</text>`).join("");
    const notes = annotated ? chartAnnotations(annotated.values).slice(0, isNarrow() ? 1 : 2).map((note) => {
      const px = x(note.index), py = y(annotated.values[note.index]);
      const above = note.above && annotated.values[note.index] < 0.85;
      const toLeft = px > left + (width - left - right) * 0.6;
      const tx = toLeft ? px - 14 : px + 14, ty = above ? py - 16 : py + 22;
      return `<g class="annotation"><circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3.5"/>
        <path d="M${px.toFixed(1)},${(py + (above ? -5 : 5)).toFixed(1)} Q${px.toFixed(1)},${ty.toFixed(1)} ${(tx + (toLeft ? 4 : -4)).toFixed(1)},${(ty - 4).toFixed(1)}" fill="none"/>
        <text x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" text-anchor="${toLeft ? "end" : "start"}">${escapeHtml(note.text)}</text></g>`;
    }).join("") : "";
    const description = series.map((item) => `${item.label} ${pct(item.values[item.values.length - 1])}`).join(", ");
    const hitWidth = (width - left - right) / Math.max(points - 1, 1);
    const hits = state.history.map((entry, index) => {
      const tip = `<strong>${formatDate(entry.reference_date)}</strong>${series.map((item) => `<br>${escapeHtml(item.label)}: ${pct(item.values[index])}`).join("")}`;
      return `<rect class="hit" x="${(x(index) - hitWidth / 2).toFixed(1)}" y="${top}" width="${hitWidth.toFixed(1)}" height="${height - top - bottom}" fill="transparent" data-tip="${escapeHtml(tip)}"></rect>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolução das probabilidades de ${formatDate(first)} a ${formatDate(last)}: ${escapeHtml(description)}${reconstructionInfo() ? " (curva recalculada com o modelo atual)" : ""}">${grid}${lines}${notes}${labels}${hits}
      <text x="${left}" y="${height - 6}">${formatDate(first)}</text><text x="${width - right}" y="${height - 6}" text-anchor="end">${formatDate(last)}</text></svg>
      ${annotated ? `<p class="note">Anotações marcam o pico e a maior virada em ${escapeHtml(annotated.label.toLowerCase())}; só aparecem variações acima de ${Math.round(MIN_ANNOTATED_JUMP * 100)} pontos percentuais e de ${NOISE_Z} vezes o erro da simulação.</p>` : ""}`;
  }

  function positionChart(probabilities) {
    const width = isNarrow() ? 380 : 640, height = isNarrow() ? 150 : 180, left = 8, bottom = 22, top = 8;
    const barWidth = (width - left * 2) / probabilities.length;
    const peak = Math.max(...probabilities, 0.01);
    const bars = probabilities.map((value, index) => {
      const barHeight = (value / peak) * (height - top - bottom);
      const color = index < 5 ? "var(--libertadores)" : index >= probabilities.length - 4 ? "var(--danger)" : "var(--ink-faint)";
      return `<rect x="${left + index * barWidth + 2}" y="${height - bottom - barHeight}" width="${barWidth - 4}" height="${barHeight}" fill="${color}" data-tip="${escapeHtml(`<strong>${index + 1}º lugar</strong><br>${pct(value)} das simulações`)}"></rect>
        <text x="${left + index * barWidth + barWidth / 2}" y="${height - 6}" text-anchor="middle">${index + 1}</text>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Distribuição da posição final">${bars}</svg>`;
  }

  /* Popup de jogo (D-049): o que o modelo dizia antes, o resultado e quanto ele mexeu nas chances de cada clube. */
  function findRoundMatch(matchId) {
    const views = state.rounds ? state.rounds.rounds : [];
    for (let index = views.length - 1; index >= 0; index -= 1) {
      const match = views[index].matches.find((item) => item.match_id === matchId);
      if (match) return { match, view: views[index] };
    }
    return null;
  }

  function openMatchDetail(matchId) {
    const found = findRoundMatch(matchId);
    const upcoming = state.snapshot.matches.find((item) => item.match_id === matchId);
    const source = found ? found.match : upcoming;
    if (!source) return;
    const title = `${escapeHtml(nameOf(source.home_id))} × ${escapeHtml(nameOf(source.away_id))}`;
    const when = `${formatShortDate(source.match_date)}${source.round ? ` · rodada ${source.round}` : ""}`;
    let body;
    if (found && found.match.pre_match && source.home_goals !== null && source.home_goals !== undefined) {
      const pre = found.match.pre_match;
      const winner = source.home_goals > source.away_goals ? `vitória do ${escapeHtml(nameOf(source.home_id))}`
        : source.home_goals < source.away_goals ? `vitória do ${escapeHtml(nameOf(source.away_id))}` : "empate";
      body = `<p class="match-popup-score">${source.home_goals} × ${source.away_goals}<span>${when}</span></p>
        <p class="match-popup-line"><strong>Resultado:</strong> ${winner}.</p>
        <p class="match-popup-line"><strong>Antes do jogo, o modelo dava:</strong> ${escapeHtml(nameOf(source.home_id))} ${pct(pre.home)} · empate ${pct(pre.draw)} · ${escapeHtml(nameOf(source.away_id))} ${pct(pre.away)}.</p>
        <h3 class="match-popup-sub">O que o jogo mexeu nas probabilidades</h3>
        ${window.MatchPopup.effectRows(found.match.impacts, nameOf, [source.home_id, source.away_id])}
        ${found.match.stakes ? `<h3 class="match-popup-sub">O que estava em jogo</h3>${window.MatchPopup.effectRows(found.match.stakes, nameOf, [source.home_id, source.away_id], 2)}` : ""}
        <p class="match-popup-links">${clubLink(source.home_id)} · ${clubLink(source.away_id)}</p>`;
    } else if (upcoming && upcoming.status !== "finished") {
      const scores = (upcoming.top_scores || []).map((score) => `${score.home_goals} × ${score.away_goals} (${pct(score.probability)})`).join(" · ");
      body = `<p class="match-popup-line"><strong>Ainda não jogado.</strong> ${when}.</p>
        <div class="match-popup-triple"><span><strong>${pct(upcoming.p_home)}</strong>${escapeHtml(nameOf(upcoming.home_id))}</span><span><strong>${pct(upcoming.p_draw)}</strong>empate</span><span><strong>${pct(upcoming.p_away)}</strong>${escapeHtml(nameOf(upcoming.away_id))}</span></div>
        <p class="match-popup-line"><strong>Gols esperados:</strong> ${num(upcoming.xg_home)} × ${num(upcoming.xg_away)}</p>
        ${scores ? `<p class="match-popup-line"><strong>Placares mais prováveis:</strong> ${scores}</p>` : ""}
        ${upcoming.p_three_plus_goals !== null && upcoming.p_three_plus_goals !== undefined ? `<p class="match-popup-line"><strong>3 gols ou mais:</strong> ${pct(upcoming.p_three_plus_goals)}</p>` : ""}
        <p class="match-popup-links">${clubLink(upcoming.home_id)} · ${clubLink(upcoming.away_id)}</p>`;
    } else {
      body = `<p class="match-popup-score">${source.home_goals} × ${source.away_goals}<span>${when}</span></p>
        <p class="note">Não temos as probabilidades desta rodada para mostrar o efeito no jogo.</p>`;
    }
    window.MatchPopup.open(title, body);
  }

  // O card inteiro é o alvo de toque (REDESIGN_SPEC v2.1 §3.1); os botões antigos de Rodada a rodada seguem valendo.
  main.addEventListener("click", (event) => {
    const button = event.target.closest(".match-open");
    if (button) { openMatchDetail(button.dataset.matchId); return; }
    const card = event.target.closest(".mc[data-match-id]");
    if (card && !event.target.closest("a, button")) openMatchDetail(card.dataset.matchId);
  });
  main.addEventListener("keydown", (event) => {
    const card = event.target.closest && event.target.closest(".mc[data-match-id]");
    if (card && event.target === card && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      openMatchDetail(card.dataset.matchId);
    }
  });

  /* Match Card v2.1 (REDESIGN_SPEC v2.1 §3.2): rodada e horário, escudos, placar ou "VS" e as 3 pílulas 1X2 com a
     sigla dos clubes. Sem botão nem linha de gols esperados: o card inteiro abre o detalhe (xG, placares, impacto). */
  const kickoffClock = (match) => {
    const stamp = match.kickoff_utc ? Date.parse(match.kickoff_utc) : NaN;
    return Number.isNaN(stamp) ? "" : new Date(stamp).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  };
  const cardDay = (iso) => {
    const date = new Date(iso + "T12:00:00");
    const weekday = date.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
    return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)} ${date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`;
  };
  const isProbability = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  const shortOf = (clubId) => { const team = teamById(clubId); return team && team.short_name ? team.short_name : nameOf(clubId); };

  function oddsPills(match, values, caption) {
    const [home, draw, away] = values;
    if (![home, draw, away].every(isProbability)) return "";
    const top = Math.max(home, draw, away);
    const pill = (value, label) => `<span class="mc-odd${value === top ? " is-top" : ""}"><strong>${pct(value)}</strong><span>${escapeHtml(label)}</span></span>`;
    return `<div class="mc-section"><p class="mc-label">${caption}</p><div class="mc-odds">${pill(home, shortOf(match.home_id))}${pill(draw, "Empate")}${pill(away, shortOf(match.away_id))}</div></div>`;
  }

  const cardTeam = (clubId) => `<span class="mc-team">${crest(clubId, 38)}<span class="mc-team-name">${escapeHtml(nameOf(clubId))}</span></span>`;

  /* ---------------- Placar ao vivo (live_round_scores, o mesmo do modo Ao vivo) e palpite salvo no aparelho */

  const LIVE_STATES = new Set(["live", "ht"]);
  const todayBrasilia = () => window.CurrentRound.brasiliaDay(Date.now());

  /* Estado do jogo para o card: placar oficial (snapshot), placar ao vivo (provisório) ou ainda sem placar. */
  function matchState(match) {
    if (match.status === "finished") return { kind: "final", home: match.home_goals, away: match.away_goals };
    const row = state.live.get(match.match_id);
    const scored = row && Number.isInteger(row.home_goals) && Number.isInteger(row.away_goals);
    if (scored && LIVE_STATES.has(row.status)) {
      const minute = row.status === "ht" ? "Intervalo" : Number.isFinite(row.minute) ? `${row.minute}'` : "";
      return { kind: "live", home: row.home_goals, away: row.away_goals, minute };
    }
    if (scored && row.status === "finished") return { kind: "ended", home: row.home_goals, away: row.away_goals };
    if (isPostponed(match)) return { kind: "postponed" };
    const kickoff = match.kickoff_utc ? Date.parse(match.kickoff_utc) : NaN;
    const started = Number.isNaN(kickoff) ? match.match_date < todayBrasilia() : Date.now() >= kickoff;
    return { kind: started ? "waiting" : "upcoming" };
  }

  /* Busca o placar ao vivo uma vez por carga, só se algum jogo sem placar oficial já pode ter começado. */
  async function loadLive() {
    const live = window.LiveRound;
    if (!live || typeof live.fetchLiveRows !== "function") return;
    const today = todayBrasilia();
    if (!state.snapshot.matches.some((match) => match.status !== "finished" && !isPostponed(match) && match.match_date <= today)) return;
    try {
      const rows = await live.fetchLiveRows(state.snapshot.season);
      state.live = new Map((Array.isArray(rows) ? rows : []).filter((row) => row && row.match_id).map((row) => [row.match_id, row]));
      if (state.live.size) route();
    } catch (error) { /* sem servidor ou sem rede: os cards ficam só com a edição publicada */ }
  }

  const SIMULATOR_KEY = (season) => `ainda-da:simulador:serie-a:${season}:v2`;
  const PICK_MODES = { placar: "Placar", vencedor: "Vencedor" };
  const validPick = (mode, pick) => (mode === "vencedor"
    ? pick === "H" || pick === "D" || pick === "A"
    : Array.isArray(pick) && pick.length === 2 && pick.every((goals) => Number.isInteger(goals) && goals >= 0));
  const stampOf = (value) => { const stamp = Date.parse(value || ""); return Number.isNaN(stamp) ? 0 : stamp; };

  /* A simulação de Placar ou Vencedor mais recente deste aparelho (salva ou rascunho em andamento). Classificação não
     tem palpite por jogo e fica de fora. Só lê o que o simulador gravou: não altera nada. */
  function latestPrediction() {
    let store = null;
    try { store = JSON.parse(window.localStorage.getItem(SIMULATOR_KEY(state.snapshot.season)) || "null"); } catch (error) { return null; }
    if (!store || store.version !== 2) return null;
    const candidates = (Array.isArray(store.saved) ? store.saved : [])
      .filter((item) => item && PICK_MODES[item.mode] && item.entry)
      .map((item) => ({ mode: item.mode, entry: item.entry, at: stampOf(item.updated_at || item.created_at), draft: false }));
    const active = store.active;
    if (active && PICK_MODES[active.mode] && active.entry) candidates.push({ mode: active.mode, entry: active.entry, at: stampOf(active.updated_at || active.started_at), draft: true });
    const withPicks = candidates.filter((item) => Object.keys({ ...(item.entry.sampled || {}), ...(item.entry.picks || {}) }).length);
    return withPicks.sort((left, right) => right.at - left.at)[0] || null;
  }

  function predictionNote() {
    const prediction = state.prediction;
    if (!prediction) return "";
    const when = prediction.at ? ` de ${new Date(prediction.at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}` : "";
    return `<p class="pick-note">Seu palpite nos cards: ${prediction.draft ? "rascunho" : "simulação"} de ${PICK_MODES[prediction.mode]}${when} · <a href="#/simular">abrir ›</a></p>`;
  }

  /* Rodapé do card com o palpite. A pontuação é a do simulador (window.Simulator.engine.matchPoints, igual ao banco). */
  function pickLine(match, status) {
    const prediction = state.prediction;
    if (!prediction) return "";
    const own = (prediction.entry.picks || {})[match.match_id];
    const sampled = (prediction.entry.sampled || {})[match.match_id];
    const pick = own !== undefined ? own : sampled;
    if (pick === undefined || !validPick(prediction.mode, pick)) return "";
    const value = prediction.mode === "placar" ? `${pick[0]} × ${pick[1]}` : pick === "D" ? "Empate" : escapeHtml(shortOf(pick === "H" ? match.home_id : match.away_id));
    const origin = own === undefined ? `<span class="mc-pick-origin">sorteado pelo modelo</span>` : "";
    const engine = window.Simulator && window.Simulator.engine;
    if (status.kind === "final" && engine && typeof engine.matchPoints === "function") {
      const points = engine.matchPoints(prediction.mode, pick, status.home, status.away);
      const pickOutcome = prediction.mode === "placar" ? engine.outcomeOf(pick[0], pick[1]) : pick;
      const realOutcome = engine.outcomeOf(status.home, status.away);
      const verdict = points === 0 ? "Errou"
        : prediction.mode === "placar" && pick[0] === status.home && pick[1] === status.away ? "Acertou o placar"
        : pickOutcome === realOutcome ? (realOutcome === "D" ? "Acertou o empate" : "Acertou o vencedor")
        : "Placar invertido";
      return `<p class="mc-pick ${points ? "is-hit" : "is-miss"}"><span class="mc-pick-label">Seu palpite (${PICK_MODES[prediction.mode]})</span><strong>${value}</strong>${origin}<span class="mc-pick-result">${verdict}${points ? ` (+${points})` : ""}</span></p>`;
    }
    const pending = status.kind === "live" ? "em andamento" : status.kind === "ended" || status.kind === "waiting" ? "aguarda o placar oficial" : "";
    return `<p class="mc-pick"><span class="mc-pick-label">Seu palpite (${PICK_MODES[prediction.mode]})</span><strong>${value}</strong>${origin}${pending ? `<span class="mc-pick-result is-pending">${pending}</span>` : ""}</p>`;
  }

  /* Match Card com três partes rotuladas: o realizado (placar e selo), a probabilidade do modelo e o seu palpite. */
  function matchRow(match) {
    const status = matchState(match);
    const clock = kickoffClock(match);
    const when = status.kind === "postponed" ? "data a definir" : `${cardDay(match.match_date)}${clock ? ` ${clock}` : ""}`;
    const BADGES = {
      final: `<span class="mc-badge is-final">Final</span>`,
      live: `<span class="mc-badge is-live">Ao vivo${status.minute ? ` · ${status.minute}` : ""}</span>`,
      ended: `<span class="mc-badge">Fim · placar provisório</span>`,
      waiting: `<span class="mc-badge">Aguardando placar</span>`,
      postponed: `<span class="mc-badge is-alert">Adiado</span>`,
      upcoming: "",
    };
    const scored = status.kind === "final" || status.kind === "live" || status.kind === "ended";
    const center = scored
      ? `<span class="mc-result"><span class="mc-center">${status.home} × ${status.away}</span>${BADGES[status.kind]}</span>`
      : `<span class="mc-result"><span class="mc-center is-vs">VS</span>${BADGES[status.kind]}</span>`;
    const finished = status.kind === "final";
    const found = finished ? findRoundMatch(match.match_id) : null;
    const pre = found && found.match.pre_match;
    const odds = finished
      ? (pre ? oddsPills(match, [pre.home, pre.draw, pre.away], "Antes do jogo · modelo") : "")
      : oddsPills(match, [match.p_home, match.p_draw, match.p_away], status.kind === "upcoming" || status.kind === "postponed" ? "Probabilidade do modelo" : "Antes do jogo · modelo");
    const result = scored ? `${nameOf(match.home_id)} ${status.home}, ${nameOf(match.away_id)} ${status.away}, ${finished ? "placar final" : "placar ao vivo"}` : `${nameOf(match.home_id)} contra ${nameOf(match.away_id)}`;
    const model = isProbability(match.p_home) && !finished ? `. Probabilidade do modelo: ${nameOf(match.home_id)} ${pct(match.p_home)}, empate ${pct(match.p_draw)}, ${nameOf(match.away_id)} ${pct(match.p_away)}` : "";
    const pick = pickLine(match, status);
    return `<article class="mc" data-match-id="${escapeHtml(match.match_id)}" tabindex="0" role="button" aria-label="${escapeHtml(`Rodada ${match.round ?? "?"}, ${when}. ${result}${model}. Ver detalhes`)}">
        <div class="mc-top"><span>R${match.round ?? "?"} · ${when}</span><span class="mc-go" aria-hidden="true">›</span></div>
        <div class="mc-teams" aria-hidden="true">${cardTeam(match.home_id)}${center}${cardTeam(match.away_id)}</div>
        <div aria-hidden="true">${odds}</div>
        ${pick}
      </article>`;
  }

  /* ---------------- Jogos por dia */

  const upcomingMatches = () => state.snapshot.matches.filter((match) => match.status !== "finished" && match.status !== "cancelled").sort(byKickoff);
  const finishedMatches = () => state.snapshot.matches.filter((match) => match.status === "finished").sort((left, right) => byKickoff(right, left));

  function dayLabel(iso) {
    const today = todayBrasilia();
    const shift = (days) => { const date = new Date(`${today}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + days); return date.toISOString().slice(0, 10); };
    const relative = iso === today ? "Hoje · " : iso === shift(1) ? "Amanhã · " : iso === shift(-1) ? "Ontem · " : "";
    return `${relative}${cardDay(iso)}`;
  }

  /* Agrupa por data real (não pela rodada): jogos atrasados ou de rodadas misturadas aparecem no dia em que caem.
     Adiados sem data ficam num grupo próprio no fim. */
  function matchesByDay(matches) {
    const groups = new Map();
    const postponed = matches.filter((match) => match.status !== "finished" && isPostponed(match));
    matches.filter((match) => !postponed.includes(match)).forEach((match) => {
      if (!groups.has(match.match_date)) groups.set(match.match_date, []);
      groups.get(match.match_date).push(match);
    });
    const sections = [...groups.entries()].map(([day, list]) => `<section class="match-day" aria-label="${escapeHtml(dayLabel(day))}">
        <h3 class="day-title">${dayLabel(day)}</h3>${matchList(list)}</section>`);
    if (postponed.length) sections.push(`<section class="match-day" aria-label="Adiados"><h3 class="day-title">Adiados · data a definir</h3>${matchList(postponed)}</section>`);
    return sections.join("");
  }

  const matchList = (matches) => `<div class="mc-list">${matches.map(matchRow).join("")}</div>`;

  function signedPercent(value) {
    const rounded = Math.round(value * 100);
    return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${Math.abs(rounded)}%`;
  }

  function renderClub(clubId) {
    const snapshot = state.snapshot;
    const byPosition = [...snapshot.teams].sort((left, right) => left.current_position - right.current_position);
    const team = teamById(clubId);
    if (!team) {
      const favorite = favoriteClub();
      const tiles = byPosition.map((item) => `<li><a class="club-tile${item.club_id === favorite ? " is-favorite" : ""}" href="#/clubes/${encodeURIComponent(item.club_id)}">
        ${crest(item.club_id, 40)}<span class="club-tile-name">${escapeHtml(item.name)}${item.club_id === favorite ? ` <span class="club-tile-star" aria-label="seu time">${STAR(true)}</span>` : ""}</span>
        <span class="club-tile-meta">${item.current_position}º · ${item.current_points} pts</span></a></li>`).join("");
      main.innerHTML = `<span class="kicker">Clubes</span><h1>Escolha um clube</h1>
        <p class="lede">Toque num clube para ver as probabilidades e os próximos jogos.</p>
        <ul class="club-grid">${tiles}</ul>`;
      return;
    }
    const picker = `<nav class="club-strip" aria-label="Trocar de clube">${byPosition.map((item) => `<a href="#/clubes/${encodeURIComponent(item.club_id)}" title="${escapeHtml(item.name)}" aria-label="${escapeHtml(item.name)}" ${item.club_id === clubId ? 'aria-current="page"' : ""}>${crest(item.club_id, 26)}</a>`).join("")}</nav>`;
    const remaining = snapshot.matches.filter((match) => match.status !== "finished" && (match.home_id === clubId || match.away_id === clubId));
    const recentResults = snapshot.matches.filter((match) => match.status === "finished" && (match.home_id === clubId || match.away_id === clubId)).slice(-6).reverse();
    const upcoming = [...remaining.filter((match) => !isPostponed(match)).slice(0, 6), ...remaining.filter(isPostponed)];
    const scenarioRows = snapshot.scenarios.map((scenario) => ({ scenario, value: team.libertadores_total.by_scenario[scenario.scenario_id] }))
      .sort((left, right) => right.value - left.value);
    const describe = (scenario) => `Liberta: ${escapeHtml(scenario.libertadores_champion)} · Sul-Americana: ${escapeHtml(scenario.sudamericana_champion)} · Copa do Brasil: ${escapeHtml(scenario.cup_champion)} (vice ${escapeHtml(scenario.cup_runner_up)})`;
    const variesByScenario = team.libertadores_total.max - team.libertadores_total.min >= 0.01;
    const history = state.history.map((entry) => entry.teams[clubId] || { title: 0, top4: 0, relegation: 0 });
    main.innerHTML = `
      ${picker}
      <div class="club-title"><h1 class="club-heading">${crest(clubId, 48)}<span>${escapeHtml(team.name)}</span></h1>${followButton(clubId)}</div>
      <p class="lede">${team.current_position}º lugar com ${team.current_points} pontos em ${team.played} jogos. Projeção: ${num(team.expected_points)} pontos (faixa provável de ${Math.round(team.points_interval_90[0])} a ${Math.round(team.points_interval_90[1])}).</p>
      <div class="stat-row">
        <div class="stat"><span class="label">Título</span><span class="big">${pct(team.title)}</span></div>
        <div class="stat"><span class="label">G4</span><span class="big">${pct(team.top4)}</span></div>
        <div class="stat"><span class="label">Libertadores</span><span class="big">${scenarioValue(team.libertadores_total)}</span><span class="sub">grupos ${scenarioValue(team.libertadores_groups)} · prévia ${scenarioValue(team.libertadores_prelim)}</span></div>
        <div class="stat"><span class="label">Sul-Americana</span><span class="big">${scenarioValue(team.sudamericana)}</span>${team.sudamericana_race ? `<span class="sub"><a href="#/classificacao/sul-americana">${team.sudamericana_race.rank}º na corrida</a></span>` : ""}</div>
        <div class="stat"><span class="label">Rebaixamento</span><span class="big">${pct(team.relegation)}</span></div>
      </div>
      <nav class="jump-chips" aria-label="Nesta página">
        <a href="#club-jogos" data-jump-to="club-jogos">Próximos jogos</a><a href="#club-resultados" data-jump-to="club-resultados">Resultados</a><a href="#club-posicao" data-jump-to="club-posicao">Posição final</a><a href="#club-evolucao" data-jump-to="club-evolucao">Evolução</a><a href="#club-forca" data-jump-to="club-forca">Força</a>${team.schedule ? `<a href="#club-dificuldade" data-jump-to="club-dificuldade">Dificuldade</a>` : ""}<a href="#club-cenarios" data-jump-to="club-cenarios">Cenários</a>
      </nav>
      <h2 id="club-jogos">Próximos jogos</h2>${upcoming.length ? matchList(upcoming) : "<p class='note'>Sem jogos restantes.</p>"}
      <h2 id="club-resultados">Últimos resultados</h2>${recentResults.length ? matchList(recentResults) : "<p class='note'>Nenhum jogo encerrado ainda.</p>"}
      <h2 id="club-posicao">Distribuição da posição final</h2>${positionChart(team.position_probabilities)}
      <h2 id="club-evolucao">Evolução ao longo da temporada</h2>
      ${(() => {
        const series = [
          { key: "title", label: "Título", color: "var(--title)", values: history.map((item) => item.title) },
          { key: "top4", label: "G4", color: "var(--libertadores)", values: history.map((item) => item.top4) },
          { key: "relegation", label: "Rebaixamento", short: "Queda", color: "var(--danger)", values: history.map((item) => item.relegation) },
        ];
        const focus = openMetric(history);
        return lineChart(series, 240, series.find((item) => item.key === focus));
      })()}
      ${reconstructionNote(reconstructionInfo())}
      <h2 id="club-forca">Força estimada</h2>
      <div class="stat-row">
        <div class="stat"><span class="label">Elo</span><span class="big">${Math.round(team.ratings.elo)}</span><span class="sub">média da liga = 1500</span></div>
        <div class="stat"><span class="label">Ataque</span><span class="big">${signedPercent(team.ratings.attack)}</span><span class="sub">gols marcados vs. média</span></div>
        <div class="stat"><span class="label">Defesa</span><span class="big">${signedPercent(team.ratings.defense)}</span><span class="sub">positivo = sofre menos</span></div>
        <div class="stat"><span class="label">Gols projetados</span><span class="big">${Math.round(team.expected_goals_for)}–${Math.round(team.expected_goals_against)}</span><span class="sub">pró–contra no fim</span></div>
      </div>
      ${clubSchedule(team)}
      <h2 id="club-cenarios">Cenários externos</h2>
      ${variesByScenario ? `<p class="note">A probabilidade de Libertadores depende dos torneios ainda em disputa.</p>
        <h3>Mais favorável: ${pct(scenarioRows[0].value)}</h3><p class="note">${describe(scenarioRows[0].scenario)}</p>
        <h3>Menos favorável: ${pct(scenarioRows[scenarioRows.length - 1].value)}</h3><p class="note">${describe(scenarioRows[scenarioRows.length - 1].scenario)}</p>`
        : `<p class="note">Os resultados de Libertadores, Sul-Americana e Copa do Brasil praticamente não alteram a probabilidade de vaga deste clube (${scenarioValue(team.libertadores_total)}).</p>`}`;
    bindFollow(() => renderClub(clubId));
    main.querySelectorAll("[data-jump-to]").forEach((link) => link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = document.getElementById(link.dataset.jumpTo);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
  }

  function clubSchedule(team) {
    const schedule = team.schedule;
    if (!schedule) return "";
    const venueStat = (label, value, rank, points, games) => (value === null || value === undefined ? "" : `<div class="stat"><span class="label">${label}</span><span class="big">${Math.round(value)}</span><span class="sub">${rank === 1 ? "a mais difícil" : `${rank}ª mais difícil`} · ${num(points)} pts esperados em ${games} ${games === 1 ? "jogo" : "jogos"}</span></div>`);
    const gap = schedule.expected_points - schedule.average_team_points;
    return `<h2 id="club-dificuldade">Dificuldade do que falta</h2>
      <div class="stat-row">
        <div class="stat"><span class="label">Tabela</span><span class="big">${Math.round(schedule.difficulty)}</span><span class="sub">${schedule.difficulty_rank === 1 ? "a mais difícil das 20" : `${schedule.difficulty_rank}ª mais difícil das 20`}</span></div>
        ${venueStat("Em casa", schedule.difficulty_home, schedule.difficulty_home_rank, schedule.expected_points_home, schedule.home_matches)}
        ${venueStat("Fora", schedule.difficulty_away, schedule.difficulty_away_rank, schedule.expected_points_away, schedule.away_matches)}
      </div>
      <p>Nos ${schedule.remaining_matches} jogos que faltam, ${escapeHtml(team.name)} deve somar <strong>${num(schedule.expected_points)} pontos</strong>. Um time de força média faria ${num(schedule.average_team_points)} contra os mesmos adversários${Math.abs(gap) >= 0.5 ? `: a força do clube ${gap > 0 ? "soma" : "tira"} ${num(Math.abs(gap))} ${Math.abs(gap) >= 1.5 ? "pontos" : "ponto"}` : ""}.</p>
      <p class="upcoming-line">Próximos adversários ${upcomingCrests(team)}</p>
      ${difficultyNote()}`;
  }

  /* Jogos (#/jogos e #/partidas): agenda de dias (opção B2) com os Match Cards (opção A1). Cada dia com jogo vira um
     botão na faixa; o padrão é hoje, ou o próximo dia com jogo a disputar. Adiados sem data ficam num botão próprio. */
  const POSTPONED_DAY = "adiados";
  const ISO_DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

  function agendaDays() {
    const days = new Map();
    state.snapshot.matches.filter((match) => match.status !== "cancelled" && !(match.status !== "finished" && isPostponed(match))).forEach((match) => {
      if (!days.has(match.match_date)) days.set(match.match_date, []);
      days.get(match.match_date).push(match);
    });
    return new Map([...days.entries()].sort(([left], [right]) => left.localeCompare(right)));
  }

  function defaultDay(days) {
    const today = todayBrasilia();
    if (days.has(today)) return today;
    const keys = [...days.keys()];
    const pending = keys.filter((day) => days.get(day).some((match) => match.status !== "finished"));
    return pending.find((day) => day >= today) || pending[pending.length - 1] || keys[keys.length - 1] || null;
  }

  function dayChip(day, matches, selected) {
    const date = new Date(`${day}T12:00:00`);
    const weekday = day === todayBrasilia() ? "Hoje" : date.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
    const month = date.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "");
    const live = matches.some((match) => matchState(match).kind === "live");
    const done = matches.every((match) => match.status === "finished");
    const label = `${dayLabel(day)}: ${matches.length} ${matches.length === 1 ? "jogo" : "jogos"}${live ? ", com jogo ao vivo" : done ? ", todos encerrados" : ""}`;
    return `<a class="day-chip${done ? " is-done" : ""}" href="#/jogos/${day}" aria-label="${escapeHtml(label)}"${day === selected ? ' aria-current="page"' : ""}>
        <span>${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}</span><strong>${date.getDate()}</strong><small>${live ? '<i class="day-live" aria-hidden="true"></i>ao vivo' : month}</small></a>`;
  }

  function renderMatches(requested) {
    const days = agendaDays();
    const postponed = upcomingMatches().filter(isPostponed);
    const keys = [...days.keys()];
    let selected;
    if (requested === POSTPONED_DAY && postponed.length) selected = POSTPONED_DAY;
    else if (ISO_DAY_PATTERN.test(requested || "") && days.has(requested)) selected = requested;
    else if (requested === "encerrados") selected = [...keys].reverse().find((day) => days.get(day).every((match) => match.status === "finished")) || defaultDay(days);
    else selected = defaultDay(days);
    const strip = `<nav class="chip-strip day-strip" aria-label="Dias com jogos">${keys.map((day) => dayChip(day, days.get(day), selected)).join("")}${postponed.length
      ? `<a class="day-chip is-postponed" href="#/jogos/${POSTPONED_DAY}"${selected === POSTPONED_DAY ? ' aria-current="page"' : ""}><span>Adiados</span><strong>${postponed.length}</strong><small>sem data</small></a>` : ""}</nav>`;
    const list = selected === POSTPONED_DAY ? postponed : selected ? [...days.get(selected)].sort(byKickoff) : [];
    const title = selected === POSTPONED_DAY ? "Adiados · data a definir" : selected ? dayLabel(selected) : "";
    const action = state.prediction ? "" : `<a class="block-link" href="#/simular">Fazer meus palpites ›</a>`;
    main.innerHTML = `
      <div class="screen-head"><h1 class="screen-title">Jogos</h1>${action}</div>
      ${keys.length || postponed.length ? strip : ""}
      ${predictionNote()}
      ${selected && selected !== POSTPONED_DAY && selected <= todayBrasilia() ? overdueWarning() : ""}
      ${list.length
        ? `<h2 class="day-title">${title}<span>${list.length} ${list.length === 1 ? "jogo" : "jogos"}</span></h2>${matchList(list)}`
        : stateBlock({ icon: "calendar", title: "Sem jogos para mostrar", text: "A agenda aparece aqui quando a tabela da temporada estiver na edição." })}`;
  }

  const PUBLISHABLE_LICENSES = ["verified_open", "licensed_with_attribution"];
  const LICENSE_LABELS = {
    verified_open: "Licença aberta",
    licensed_with_attribution: "Uso permitido com atribuição",
    research_only_unverified: "Só para pesquisa local, licença não verificada",
    requires_agreement: "Exige acordo com a fonte",
    blocked: "Uso bloqueado",
  };
  const SOURCE_LINKS = {
    football_data_org: { home: "https://www.football-data.org/", terms: ["termos de uso", "https://www.football-data.org/client/register"] },
    adaoduque_kaggle: { home: "https://www.kaggle.com/datasets/adaoduque/campeonato-brasileiro-de-futebol", terms: ["texto da GPL-2.0", "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html"] },
  };

  function isPublishable(data) {
    return data.composition_mode === "publication" && PUBLISHABLE_LICENSES.includes(data.license_status);
  }

  function dataSources(data) {
    if (Array.isArray(data.sources)) return data.sources;
    return data.source ? [{ source_name: data.source, license_status: data.license_status, version: data.version, retrieved_at: data.retrieved_at }] : [];
  }

  function seasonRange(seasons) {
    if (!seasons || !seasons.length) return "temporadas não informadas";
    const sorted = [...seasons].sort((a, b) => a - b);
    return sorted.length === 1 ? String(sorted[0]) : `${sorted[0]}–${sorted[sorted.length - 1]}`;
  }

  function sourceItem(source) {
    const links = SOURCE_LINKS[source.source_name] || {};
    const credit = escapeHtml(source.attribution || source.source_name);
    const named = links.home ? `<a href="${links.home}"${source.source_name === "football_data_org" ? ' lang="en"' : ""}>${credit}</a>` : credit;
    const terms = links.terms ? ` (<a href="${links.terms[1]}">${links.terms[0]}</a>)` : "";
    const license = escapeHtml(LICENSE_LABELS[source.license_status] || source.license_status);
    return `<li>${named}. Temporadas usadas: <strong>${seasonRange(source.seasons)}</strong>. ${license}${terms}. Versão <code class="data-version">${escapeHtml(source.version)}</code>, coletada em ${escapeHtml(String(source.retrieved_at).slice(0, 10))}.</li>`;
  }

  const seasonRangeText = (seasons) => (Array.isArray(seasons) && seasons.length ? `${escapeHtml(seasons[0])}–${escapeHtml(seasons[seasons.length - 1])}` : "");

  function coverageVerdict(coverage) {
    if (coverage < 0.87) return ": ela é mais estreita do que deveria, e o resultado final cai fora dela mais vezes do que os 90% sugerem.";
    if (coverage > 0.93) return ": ela é mais larga do que precisaria.";
    return ", perto dos 90% esperados.";
  }

  function seasonSimulationText(metrics, snapshot, context) {
    if (!metrics.model_version) return "";
    if (!context.sameModelVersion) {
      return `<p class="note">O relatório de testes disponível é da versão ${escapeHtml(metrics.model_version)} do modelo, e o site usa a ${escapeHtml(snapshot.model.model_version)}. Os números de acerto da versão em uso ainda não foram publicados.</p>`;
    }
    const { finalTest, finalValidation, fixedRatings } = context;
    const usable = (entry) => Boolean(entry) && typeof entry.points_interval_90_coverage === "number" && typeof entry.points_mae === "number";
    if (!usable(finalTest) || !usable(finalValidation)) return "";
    const rounds = Array.isArray(metrics.season_simulation.rounds) ? metrics.season_simulation.rounds.map(escapeHtml).join(", ") : "";
    const mode = fixedRatings ? "ratings fixos: a força de cada clube não muda durante a simulação" : "ratings dinâmicos: a força de cada clube é atualizada a cada rodada simulada";
    const shortMode = fixedRatings ? "os ratings fixos" : "os ratings dinâmicos";
    return `<p>Para medir a projeção de pontos, refizemos temporadas passadas a partir das rodadas ${rounds}, com o mesmo modelo usado aqui (${mode}). Nas temporadas de teste (${seasonRangeText(metrics.test_seasons)}), a projeção errou a pontuação final por ${num(finalTest.points_mae)} pontos em média.</p>
        <p>A faixa provável de pontos é onde terminam 90% das simulações. Se ela fosse exata, a pontuação final cairia dentro dela 90% das vezes. Com ${shortMode} usados aqui, caiu ${pct(finalTest.points_interval_90_coverage)} das vezes nas temporadas de teste e ${pct(finalValidation.points_interval_90_coverage)} nas de validação (${seasonRangeText(metrics.validation_seasons)})${coverageVerdict(finalTest.points_interval_90_coverage)}</p>`;
  }

  function historySection(reconstruction) {
    if (reconstruction) {
      const version = reconstruction.consistent
        ? `Versão do modelo da curva atual: ${reconstruction.modelVersion}, recalculada em ${reconstruction.generatedAt}.`
        : `Versão do modelo atual: ${reconstruction.modelVersion}, recalculada em ${reconstruction.generatedAt}. Atenção: parte da curva ainda foi calculada com outra versão do modelo.`;
      return `<h2>Histórico das probabilidades</h2>
      <p>O gráfico de evolução de cada clube não guarda as previsões antigas. A cada atualização, refazemos a temporada inteira: para cada data de referência, o modelo atual roda as simulações usando só os resultados conhecidos até aquela data. Por isso a curva inteira muda quando o modelo muda ou quando um placar é corrigido na fonte, e um ponto antigo pode não bater com o que este site mostrou naquele dia. ${version} A aba Rodada a rodada é feita do mesmo jeito.</p>`;
    }
    if (state.rounds) {
      return `<h2>Histórico das probabilidades</h2><p>A aba Rodada a rodada não guarda as previsões antigas. A cada atualização, o modelo atual refaz a véspera de cada rodada usando só os resultados conhecidos até ali.</p>`;
    }
    return "";
  }

  function renderMethodology() {
    const snapshot = state.snapshot;
    const metrics = state.metrics;
    const labels = { base_rate: "Taxa-base (frequências históricas)", intercept_only: "Poisson sem variáveis", elo_only: "Elo", attack_defense_only: "Ataque/defesa", elo_attack_defense: "Elo + ataque/defesa (escolhido)", full: "Elo + ataque/defesa + forma", elo_attack_defense_sem_dixon_coles: "Escolhido sem Dixon-Coles" };
    const metricRows = metrics ? Object.entries(metrics.test_metrics).map(([name, values]) => `<tr><td class="left">${labels[name] || escapeHtml(name)}</td><td>${num(values.log_loss, 4)}</td><td>${num(values.brier, 4)}</td><td>${num(values.rps, 4)}</td></tr>`).join("") : "";
    const finalSimulation = metrics && metrics.season_simulation ? metrics.season_simulation.uncertainty : null;
    const chosenVariant = finalSimulation ? finalSimulation.selected : null;
    const finalTest = chosenVariant && finalSimulation.test ? finalSimulation.test[chosenVariant] : null;
    const finalValidation = chosenVariant && finalSimulation.validation ? finalSimulation.validation[chosenVariant] : null;
    const sameModelVersion = Boolean(metrics && metrics.model_version === snapshot.model.model_version);
    const fixedRatings = !snapshot.dynamic_ratings;
    const reconstruction = reconstructionInfo();
    main.innerHTML = `
      <span class="kicker">Como calculamos</span>
      <h1>De onde saem as porcentagens</h1>
      <p class="lede">O modelo, as regras do regulamento, os testes com temporadas passadas, de onde vêm os dados e o que o modelo não sabe.</p>
      <h2>Modelo</h2>
      <p>Cada clube tem um <strong>rating Elo</strong> (força geral, com vantagem de mando e peso pelo saldo de gols) e <strong>ratings de ataque e defesa</strong> atualizados jogo a jogo, ajustados pela força do adversário. Duas regressões de Poisson convertem esses ratings em gols esperados do mandante e do visitante.</p>
      <p>A simulação de Monte Carlo parte da tabela real, preserva os jogos já disputados e sorteia placares para os ${snapshot.remaining_matches} restantes. ${fixedRatings ? "Durante a simulação, a força de cada clube fica fixa no valor da data de referência: só os jogos reais mudam os ratings." : "Dentro de cada simulação, os ratings são atualizados após cada rodada simulada. Jogos da mesma data usam os ratings da véspera."} Cada temporada simulada é independente. A classificação aplica os critérios do Art. 15 do regulamento: pontos, vitórias, saldo, gols pró, confronto direto (só entre dois clubes), cartões e sorteio.</p>
      <p class="note">Versão ${escapeHtml(snapshot.model.model_version)} · variáveis: ${escapeHtml(snapshot.model.feature_set)} · treino: ${snapshot.model.training_seasons[0]}–${snapshot.model.training_seasons[snapshot.model.training_seasons.length - 1]} · semente ${snapshot.seed} · ratings na simulação: ${snapshot.dynamic_ratings ? "dinâmicos" : "fixos"}.</p>
      <h2>Vagas continentais</h2>
      <p>Pelo <a href="${escapeHtml(snapshot.regulation.url)}">${escapeHtml(snapshot.regulation.title)}</a> (${escapeHtml(snapshot.regulation.date)}): do 1º ao 4º vão à fase de grupos da Libertadores 2027 e o 5º à fase preliminar. O campeão da Copa do Brasil vai à fase de grupos e o vice à preliminar. Os campeões da Libertadores e da Sul-Americana 2026 também se classificam, e as vagas liberadas descem para o melhor colocado ainda não classificado. A Sul-Americana fica com os seis melhores restantes. Os quatro últimos são rebaixados.</p>
      <p>Situação em ${escapeHtml(snapshot.external_context.as_of)}: ${snapshot.external_context.notes.map(escapeHtml).join(" ")} Como esses torneios não têm vencedor definido, mostramos faixas entre os ${snapshot.scenarios.length} cenários possíveis. Não estimamos a probabilidade de cada um.</p>
      <p class="note">Interpretação do § 5º do Art. 6º adotada: "${escapeHtml(snapshot.external_context.cup_redirect_policy)}" (texto ambíguo; ver documentação).</p>
      <p>Na corrida da Sul-Americana, os clubes são ordenados pela faixa entre os cenários. A coluna "vale em todos os cenários" é a probabilidade de terminar com a vaga seja quem for campeão dos outros torneios; ela nunca atribui peso a um cenário.</p>
      <h2>Dificuldade da tabela</h2>
      <p>Para cada jogo que falta, calculamos quantos pontos um time de força média faria contra aquele adversário, naquele mando, com o mesmo modelo dos jogos. A soma vira uma nota de 0 a 100: 50 é uma tabela média do campeonato, e quanto maior, menos pontos um time comum faria. Jogar fora é sempre mais difícil, por isso casa e fora também têm posição entre os 20. Os pontos esperados do clube usam a força dele e as probabilidades de cada jogo.</p>
      <h2>Validação</h2>
      ${metrics ? `<p>Backtesting temporal: o modelo de cada temporada foi treinado só com temporadas anteriores. Os hiperparâmetros foram escolhidos em ${metrics.validation_seasons[0]}–${metrics.validation_seasons[metrics.validation_seasons.length - 1]} e o teste foi feito em ${metrics.test_seasons[0]}–${metrics.test_seasons[metrics.test_seasons.length - 1]}. Valores menores são melhores.</p>
        <div class="table-scroll"><table><thead><tr><th class="left">Modelo</th><th>Log loss</th><th>Brier</th><th>RPS</th></tr></thead><tbody>${metricRows}</tbody></table></div>
        <p class="note">Empates previstos: ${pct(metrics.draw_rate.predicted)} · observados: ${pct(metrics.draw_rate.observed)}.</p>
        ${seasonSimulationText(metrics, snapshot, { finalTest, finalValidation, sameModelVersion, fixedRatings })}`
        : "<p class='note'>Relatório de backtesting indisponível.</p>"}
      ${historySection(reconstruction)}
      <h2>Dados</h2>
      <p>Cada temporada vem de uma única fonte, sem completar com outra. Jogo sem placar na fonte entra nas simulações como ainda não disputado.</p>
      <ul class="data-sources">${dataSources(snapshot.data).map(sourceItem).join("")}</ul>
      <p>O site mostra a tabela, os jogos e os resultados da temporada exibida e os números calculados a partir deles. Os arquivos de dados não são publicados aqui: quem quiser usá-los deve buscá-los nas fontes. Nenhuma fonte garante dados sem erro ou atraso. Se um placar estiver errado na fonte, ele aparece errado aqui até ser corrigido, sempre com evidência registrada.</p>
      <p class="note">Versão dos dados: <code class="data-version">${escapeHtml(snapshot.data.version)}</code>.</p>
      ${isPublishable(snapshot.data) ? "" : `<div class="warning">Atualização de pesquisa: estes dados são só para uso local e não podem ser publicados.</div>`}
      ${snapshot.data.warnings.length ? `<div class="warning">${snapshot.data.warnings.map(escapeHtml).join("<br>")}</div>` : ""}
      <h2>Escudos</h2>
      <p>Os escudos vêm do Wikimedia Commons, onde estão em domínio público por não atingirem originalidade (PD-textlogo; Mirassol e São Paulo também PD-shape). Domínio público de direito autoral não muda a marca: os escudos são marcas registradas dos clubes, aparecem só para identificar cada time e não indicam relação nem apoio dos clubes ao AInda dá?. Red Bull Bragantino, Corinthians e Vasco da Gama não têm escudo com licença livre: aparecem com o escudo oficial, sem alteração e só para identificar o clube, por decisão do projeto (ADR-0014). Se um clube preferir, o escudo sai.</p>
      <h2>Limitações</h2>
      <ul>
        <li>O modelo não conhece lesões, suspensões, troca de treinador nem rodízio por outras competições.</li>
        <li>Os gols simulados não geram cartões; os critérios de cartões usam apenas jogos já disputados.</li>
        <li>${fixedRatings ? "A força de cada clube fica fixa na data de referência durante toda a simulação: uma sequência de vitórias simuladas não deixa o time mais forte nas rodadas seguintes." : "As probabilidades dos jogos usam a força na data de referência; dentro das simulações, a força evolui."}</li>
        <li>Percentuais muito pequenos ou muito grandes ainda são incertos: "0%" significa que o desfecho não ocorreu em nenhuma simulação, não que seja impossível.</li>
      </ul>
      <h2>Elo e diferenças entre competições</h2>
      <div id="metodo-elo"></div>`;
    if (window.AIndaDaMetodo) window.AIndaDaMetodo.render(document.getElementById("metodo-elo"), "serie-a");
  }

  let lastSection = null;

  /* A privacidade não depende do snapshot: abre mesmo se as probabilidades não carregarem. */
  function renderPrivacy() {
    if (window.LiveRound) window.LiveRound.stop();
    document.querySelectorAll(".masthead nav a").forEach((link) => link.removeAttribute("aria-current"));
    window.AIndaDaPrivacidade.render(main);
    if (lastSection !== "privacidade") window.scrollTo(0, 0);
    lastSection = "privacidade";
  }

  function route() {
    const [, section = "", parameter = "", ...rest] = location.hash.replace(/^#/, "").split("/");
    if (section === "privacidade") { renderPrivacy(); return; }
    if (!state.snapshot) return;
    state.prediction = latestPrediction();
    const isHome = !section || section === "inicio";
    document.querySelectorAll(".masthead nav a").forEach((link) => {
      const active = (link.dataset.route === "home" && isHome) || link.dataset.route === section || (link.dataset.route === "jogos" && section === "partidas");
      if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
    if (section !== "ao-vivo" && window.LiveRound) window.LiveRound.stop();
    if (section === "classificacao") renderStandings(parameter);
    else if (section === "clubes") renderClub(decodeURIComponent(parameter));
    else if (section === "partidas" || section === "jogos") renderMatches(parameter);
    else if (section === "rodadas") {
      window.Rounds.render(main, [parameter, ...rest], { review: state.rounds, escapeHtml, pct, num, formatDate, formatShortDate, highlights: roundHighlights, favorite: favoriteClub() });
    }
    else if (section === "simular") window.Simulator.render(main, [parameter, ...rest], { snapshot: state.snapshot, escapeHtml, pct, crest, nameOf, formatShortDate });
    else if (section === "ao-vivo") window.LiveRound.render(main, { snapshot: state.snapshot, escapeHtml, pct, crest, favorite: favoriteClub() });
    else if (section === "metodologia") renderMethodology();
    else renderHome(parameter);
    revealActive(document.querySelector(".masthead nav"));
    main.querySelectorAll(".chip-strip").forEach(revealActive);
    revealActive(document.querySelector(".leagues"));
    const sameView = (isHome ? "inicio" : section) === lastSection && section !== "clubes";
    lastSection = isHome ? "inicio" : section;
    if (!sameView) window.scrollTo(0, 0);
  }

  async function loadCrests() {
    try {
      const response = await fetch("assets/crests/manifest.json", { headers: { Accept: "application/json" } });
      if (response.ok) return await response.json();
    } catch (error) { /* sem escudos: a interface usa só os nomes */ }
    return {};
  }

  async function start() {
    const section = location.hash.replace(/^#\/?/, "").split("/")[0];
    if (section === "privacidade") renderPrivacy(); else main.innerHTML = skeleton(section);
    document.getElementById("reference-bar").textContent = "Carregando as simulações…";
    state.snapshot = await fetchJson(`/seasons/${SEASON}/predictions`);
    if (!state.snapshot) {
      document.getElementById("reference-bar").textContent = "";
      if (location.hash.replace(/^#\/?/, "").split("/")[0] === "privacidade") return;
      main.innerHTML = stateBlock({
        icon: "offline",
        role: "alert",
        title: "Não deu para carregar as probabilidades",
        text: "A conexão falhou ou a atualização ainda não está no ar. Confira a internet e tente de novo.",
        action: `<button type="button" class="state-action btn-primary" id="retry">Tentar novamente</button>`,
      });
      document.getElementById("retry").addEventListener("click", start);
      return;
    }
    state.history = (await fetchJson(`/seasons/${SEASON}/probability-history`)) || [];
    const seasons = await fetchJson("/seasons");
    const season = Array.isArray(seasons) ? seasons.find((item) => item && item.season === SEASON) : null;
    state.historyMode = season && typeof season.history_mode === "string" ? season.history_mode : null;
    state.metrics = await fetchJson("/models/metrics");
    state.rounds = await fetchJson(`/seasons/${SEASON}/rounds`);
    state.insights = (await fetchJson(`/seasons/${SEASON}/insights`)) || [];
    try {
      state.currentRound = window.CurrentRound.prepare(state.snapshot, await fetchJson(`/seasons/${SEASON}/current-round`));
    } catch (error) {
      state.currentRound = null;
    }
    state.crests = await loadCrests();
    renderReferenceBar();
    route();
    loadLive();
  }

  window.addEventListener("hashchange", route);
  start();
})();
