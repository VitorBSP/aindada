(function () {
  "use strict";

  const SEASON = 2026;
  const state = { snapshot: null, history: [], metrics: null, rounds: null, currentRound: null, insights: [], crests: {}, apiMode: false, scenarioChoice: {}, historyMode: null };
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
  }

  function raceRows(teams, accessor, kind) {
    return teams.map((team) => {
      const value = accessor(team);
      return `<div class="race-row">
        ${clubLink(team.club_id)}
        <div class="bar-track" role="img" aria-label="${escapeHtml(team.name)}: ${pct(value)}">
          <div class="bar-fill ${kind}" style="width:${(value * 100).toFixed(1)}%"></div>
        </div>
        <span class="value">${pct(value)}</span>
      </div>`;
    }).join("");
  }

  function changesSinceLast(onlyKey = null) {
    if (state.history.length < 2) return "";
    const latest = state.history[state.history.length - 1];
    const previous = state.history[state.history.length - 2];
    const changes = [];
    const metrics = [["title", "título"], ["relegation", "rebaixamento"], ["top4", "G4"]].filter(([key]) => !onlyKey || key === onlyKey);
    for (const [clubId, values] of Object.entries(latest.teams)) {
      const before = previous.teams[clubId];
      if (!before) continue;
      for (const [key, label] of metrics) {
        const delta = values[key] - before[key];
        if (Math.abs(delta) >= 0.05) changes.push({ clubId, label, delta, now: values[key] });
      }
    }
    changes.sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta));
    if (!changes.length) return `<p class="note">Nenhuma chance andou mais de 5 pontos percentuais desde ${formatDate(previous.reference_date)}.</p>`;
    const comparedTo = !reconstructionInfo()
      ? `Comparado à atualização de ${formatDate(previous.reference_date)}.`
      : sameModel(previous, latest)
        ? `Comparado a ${formatDate(previous.reference_date)}, na curva recalculada com o mesmo modelo.`
        : `Comparado a ${formatDate(previous.reference_date)}, na curva recalculada. Atenção: parte desta curva foi calculada com outra versão do modelo, então as variações entre pontos podem vir da troca de modelo, e não dos jogos.`;
    return `<p class="note">${comparedTo} Só entram variações de 5 pontos percentuais ou mais.</p><ul class="changes">` + changes.slice(0, 8).map((change) => {
      const sign = change.delta > 0 ? "+" : "−";
      const css = (change.label === "rebaixamento") === (change.delta > 0) ? "change-down" : "change-up";
      return `<li>${clubLink(change.clubId)}: chance de ${change.label} <span class="${css}">${sign}${Math.round(Math.abs(change.delta) * 100)} p.p.</span> (agora ${pct(change.now)})</li>`;
    }).join("") + "</ul>";
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

  const MAX_HOME_SECONDARY = 2;

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

  const MOSAIC_DOTS = 1000;
  const MOSAIC_COLUMNS = 50;
  const MOSAIC_LABEL_MIN_DOTS = 40;

  const RACES = {
    titulo: { key: "title", label: "Título", noun: "título", slots: 1, color: "var(--title)" },
    g4: { key: "top4", label: "G4", noun: "G4", slots: 4, color: "var(--libertadores)" },
    rebaixamento: { key: "relegation", label: "Rebaixamento", noun: "rebaixamento", slots: 4, color: "var(--danger)" },
  };
  const RACE_MOVEMENT_THRESHOLD = 0.05;

  function allocateDots(shares, total) {
    const allocated = shares.map((item) => ({ ...item, dots: Math.floor(item.share * total), rest: item.share * total - Math.floor(item.share * total) }));
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
    const groups = allocateDots(contenders.map((team) => ({ team, share: team[race.key] / race.slots })), MOSAIC_DOTS);
    const perDot = state.snapshot.n_simulations * race.slots / MOSAIC_DOTS;
    const cell = 10, rows = MOSAIC_DOTS / MOSAIC_COLUMNS, top = 26, bottom = 30;
    const width = MOSAIC_COLUMNS * cell, height = top + rows * cell + bottom;
    let index = 0;
    let labelEnd = -Infinity;
    const labels = [];
    const size = 7.6;
    const dots = groups.map((group) => {
      const startColumn = Math.floor(index / rows);
      const circles = [];
      const href = `#${dotId(group.team.club_id)}`;
      for (let count = 0; count < group.dots; count += 1, index += 1) {
        const column = Math.floor(index / rows), row = index % rows;
        circles.push(`<use href="${href}" x="${column * cell + (cell - size) / 2}" y="${top + row * cell + (cell - size) / 2}" width="${size}" height="${size}"/>`);
      }
      const labelX = startColumn * cell + 1;
      if (group.dots >= MOSAIC_LABEL_MIN_DOTS && labelX > labelEnd + 6) {
        labels.push(`<text x="${labelX}" y="${top - 9}">${escapeHtml(group.team.short_name)}</text>`);
        labelEnd = labelX + group.team.short_name.length * 9;
      }
      return `<g>${circles.join("")}</g>`;
    }).join("");
    const unit = race.slots === 1 ? "simulações" : `vagas de ${race.noun}`;
    const lastX = width - cell / 2, lastY = top + rows * cell - cell / 2;
    const annotation = `<g class="annotation" aria-hidden="true">
      <path d="M${lastX},${lastY + 6} q2,12 -16,16" fill="none"/>
      <text x="${lastX - 20}" y="${height - 6}" text-anchor="end">cada ponto, ${perDot.toLocaleString("pt-BR")} ${unit}</text></g>`;
    const others = contenders.length - groups.length;
    const description = groups.map((group) => `${group.team.name}: ${group.dots} pontos`).join("; ");
    const legend = groups.map((group) => `<li>${dotSwatch(group.team.club_id)}
      <a class="club-cell" href="#/clubes/${encodeURIComponent(group.team.club_id)}"><span>${escapeHtml(group.team.name)}</span></a> <strong>${pct(group.team[race.key])}</strong></li>`).join("");
    const simulations = state.snapshot.n_simulations.toLocaleString("pt-BR");
    const explanation = race.slots === 1
      ? `Quem termina campeão em cada uma das ${simulations} simulações, agrupadas em ${MOSAIC_DOTS.toLocaleString("pt-BR")} pontos.`
      : `Em cada simulação, ${race.slots} clubes terminam no ${race.noun}: são ${(state.snapshot.n_simulations * race.slots).toLocaleString("pt-BR")} vagas no total, agrupadas em ${MOSAIC_DOTS.toLocaleString("pt-BR")} pontos. Ao lado do clube, a chance dele.`;
    return `<figure class="mosaic">
      <svg class="mosaic-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Mosaico de ${escapeHtml(race.noun)} em ${MOSAIC_DOTS.toLocaleString("pt-BR")} pontos, cada um igual a ${perDot.toLocaleString("pt-BR")} ${unit}. ${escapeHtml(description)}.">${dotDefs(groups.map((group) => group.team.club_id))}<g class="mosaic-labels">${labels.join("")}</g>${dots}${annotation}</svg>
      <figcaption>
        <ul class="mosaic-legend">${legend}</ul>
        <p class="note">${explanation}${others > 0 ? ` ${others} clube(s) com chance menor que um ponto não aparecem.` : ""}</p>
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

  const joinNames = (teams) => {
    const names = teams.map((team) => escapeHtml(team.name));
    return names.length > 1 ? `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}` : names.join("");
  };
  const NEAR_CERTAIN = 0.99;

  function raceStory(raceId) {
    const race = RACES[raceId];
    const teams = raceTeams(race);
    const simulations = state.snapshot.n_simulations.toLocaleString("pt-BR");
    const method = `Jogamos os ${state.snapshot.remaining_matches} jogos que faltam ${simulations} vezes, a partir da tabela real. Cada porcentagem diz em quantas dessas simulações aquilo aconteceu.`;
    if (raceId === "titulo") {
      const [leader, challenger] = teams.filter((team) => team.title >= 0.005);
      if (!leader) return { headline: "Quem ainda dá?", lede: method };
      const headline = challenger
        ? `${escapeHtml(leader.name)} na frente. ${escapeHtml(challenger.name)}: ainda dá${challenger.title < 0.05 ? ", por pouco" : ""}.`
        : `Só ${escapeHtml(leader.name)} ainda aparece com o título nas simulações.`;
      const detail = `O título fica com ${escapeHtml(leader.name)} em <strong>${pct(leader.title)}</strong> das simulações${challenger ? ` e com ${escapeHtml(challenger.name)} em <strong>${pct(challenger.title)}</strong>` : ""}.`;
      return { headline, lede: `${detail} <span class="lede-method">${method}</span>` };
    }
    const settled = teams.filter((team) => team[race.key] >= NEAR_CERTAIN);
    const open = teams.filter((team) => team[race.key] >= 0.01 && team[race.key] < NEAR_CERTAIN);
    const spots = race.slots - settled.length;
    const allSimulations = settled.every((team) => team[race.key] === 1) ? "todas as" : "praticamente todas as";
    const verb = raceId === "g4" ? (settled.length > 1 ? "terminam no G4" : "termina no G4") : (settled.length > 1 ? "caem" : "cai");
    const settledText = settled.length ? `${joinNames(settled)} ${verb} em ${allSimulations} simulações. ` : "";
    const rest = raceId === "g4" ? (spots > 1 ? `As ${spots} vagas restantes` : "A vaga restante") : (spots > 1 ? `As outras ${spots} quedas` : "A outra queda");
    const openText = open.length ? `${rest} ${spots > 1 ? "ficam" : "fica"} entre ${joinNames(open.slice(0, 6))}${open.length > 6 ? ` e mais ${open.length - 6}` : ""}.` : "";
    const headline = raceId === "g4"
      ? `G4: ${spots > 0 ? `${spots === 1 ? "uma vaga" : `${spots} vagas`} em aberto, ${open.length} ${open.length === 1 ? "clube" : "clubes"} na briga.` : "as quatro vagas já têm dono nas simulações."}`
      : `Quatro caem. ${spots > 0 ? `${open.length} ${open.length === 1 ? "clube ainda corre" : "clubes ainda correm"} risco por ${spots === 1 ? "uma vaga" : `${spots} vagas`}.` : "As simulações já apontam os quatro."}`;
    return { headline, lede: `${settledText}${openText} <span class="lede-method">${method}</span>` };
  }

  const ROUND_TAB = "rodada";

  function raceSwitch(selected, featured) {
    const round = state.currentRound;
    const roundLink = round ? `<a href="#/inicio/${ROUND_TAB}" ${selected === ROUND_TAB ? 'aria-current="page"' : ""}>${round.label}</a>` : "";
    const links = roundLink + Object.entries(RACES).map(([id, race]) => `<a href="#/inicio/${id}" ${id === selected ? 'aria-current="page"' : ""}>${race.label}</a>`).join("");
    const switchNav = `<nav class="segmented${round ? " has-round" : ""}" aria-label="${round ? "Escolha o que ver" : "Escolha a disputa"}">${links}</nav>`;
    if (selected === ROUND_TAB) return `<div class="race-switch">${switchNav}</div>`;
    const previous = state.history[state.history.length - 2];
    const latest = state.history[state.history.length - 1];
    const curve = !reconstructionInfo() ? "" : sameModel(previous, latest) ? ", na curva recalculada com o mesmo modelo" : ", na curva recalculada";
    const why = featured.reason === "movement" && previous
      ? `a disputa que mais mudou desde ${formatDate(previous.reference_date)}${curve}`
      : "a disputa mais aberta agora";
    const hint = selected === featured.id ? `Em destaque nesta edição: ${why}.` : `<a href="#/inicio/${featured.id}">Voltar ao destaque da edição</a> (${RACES[featured.id].noun}, ${why}).`;
    return `<div class="race-switch">${switchNav}<p class="note">${hint}</p></div>`;
  }

  function libertadoresRanges() {
    const fight = state.snapshot.teams.filter((team) => team.libertadores_total.max > 0.02 && team.libertadores_total.min < 0.98)
      .sort((left, right) => scenarioMid(right.libertadores_total) - scenarioMid(left.libertadores_total)).slice(0, 8);
    if (!fight.length) return "";
    return `<h2>E a Libertadores?</h2>
      <p class="note">Além do G4, há vagas que dependem de quem ganha Libertadores, Sul-Americana e Copa do Brasil. Por isso mostramos uma faixa: o menor e o maior valor entre os ${state.snapshot.scenarios.length} cenários possíveis. Não chutamos quem vence esses torneios.</p>
      <div>${fight.map((team) => {
        const range = team.libertadores_total;
        return `<div class="race-row">${clubLink(team.club_id)}
          <div class="bar-track" role="img" aria-label="${escapeHtml(team.name)}: ${scenarioValue(range)}">
            <div class="bar-fill lib" style="width:${(range.min * 100).toFixed(1)}%"></div>
            <div class="bar-range" style="left:${(range.min * 100).toFixed(1)}%;width:${((range.max - range.min) * 100).toFixed(1)}%"></div>
          </div><span class="value">${scenarioValue(range)}</span></div>`;
      }).join("")}</div>`;
  }

  function homeTab(requested, featured) {
    if (requested === ROUND_TAB && state.currentRound) return ROUND_TAB;
    if (RACES[requested]) return requested;
    if (!requested && window.CurrentRound.opensByDefault(state.currentRound, Date.now())) return ROUND_TAB;
    return featured.id;
  }

  function renderHome(requested) {
    const featured = featuredRace();
    const tab = homeTab(requested, featured);
    const raceId = tab === ROUND_TAB ? featured.id : tab;
    const race = RACES[raceId];
    const story = raceStory(raceId);
    const insights = currentInsights();
    const lead = insights.find((insight) => insight.placement === "home_lead");
    const secondary = insights.filter((insight) => insight.placement === "home_secondary").slice(0, MAX_HOME_SECONDARY);
    const leadBlock = lead
      ? `<span class="kicker">Destaques da rodada · dados até ${formatDate(state.snapshot.reference_date)}</span>
        <h1>${escapeHtml(lead.headline)}</h1>
        <p class="lede">${escapeHtml(lead.body)}</p>
        ${insightLinks(lead)}
        ${secondary.length ? `<div class="highlights">${secondary.map(insightArticle).join("")}</div>` : ""}`
      : "";
    if (tab === ROUND_TAB) {
      const renderer = window.CurrentRound.createRenderer({ escapeHtml, pct, crest, clubLink, nameOf, formatDate });
      main.innerHTML = `${leadBlock}${raceSwitch(ROUND_TAB, featured)}${renderer.render(state.currentRound, state.snapshot, Date.now(), overdueWarning(), Boolean(lead))}`;
      return;
    }
    const heading = lead ? `<h2 class="race-heading">${story.headline}</h2>` : `<h1>${story.headline}</h1>`;
    main.innerHTML = `
      ${leadBlock}
      ${raceSwitch(raceId, featured)}
      ${heading}
      <p class="lede">${story.lede}</p>
      ${overdueWarning()}
      ${raceMosaic(race)}
      ${raceId === "g4" ? libertadoresRanges() : ""}
      <h2>O que mudou em ${race.noun} desde a última atualização</h2>
      ${changesSinceLast(race.key)}`;
  }

  function scenarioStatus() {
    const total = state.snapshot.scenarios.length;
    const chosen = Object.keys(state.scenarioChoice).length;
    const remaining = matchingScenarios().length;
    if (!chosen) return `Sem escolha, Libertadores e Sul-Americana aparecem como faixa entre os ${total} cenários possíveis.`;
    if (remaining === 1) return "Cenário completo: as chances de vaga abaixo valem se esses resultados acontecerem.";
    return `Faixa entre os ${remaining} cenários que combinam com a sua escolha.`;
  }

  function scenarioPanel() {
    const choice = state.scenarioChoice;
    const select = ([key, label]) => {
      const others = Object.fromEntries(Object.entries(choice).filter(([other]) => other !== key));
      const options = [...new Set(matchingScenarios(others).map((scenario) => scenario[key]))].sort((left, right) => left.localeCompare(right, "pt-BR"));
      return `<label>${label}<select data-key="${key}">
        <option value="">Ainda em aberto</option>
        ${options.map((value) => `<option value="${escapeHtml(value)}" ${choice[key] === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}
      </select></label>`;
    };
    const clear = Object.keys(choice).length ? `<button type="button" class="link-button" id="scenario-clear">Limpar escolhas</button>` : "";
    return `<form class="scenario-panel" id="scenario-form" aria-labelledby="scenario-title">
      <p class="scenario-title" id="scenario-title">E se os outros torneios terminarem assim?</p>
      <fieldset>${SCENARIO_KEYS.map(select).join("")}</fieldset>
      <p class="note" id="scenario-status" aria-live="polite">${scenarioStatus()} ${clear}</p>
    </form>`;
  }

  function bindScenarioPanel(rerender) {
    const form = document.getElementById("scenario-form");
    if (!form) return;
    form.addEventListener("change", (event) => {
      const key = event.target.dataset.key;
      if (!key) return;
      if (event.target.value) state.scenarioChoice[key] = event.target.value;
      else delete state.scenarioChoice[key];
      rerender();
      const again = document.querySelector(`#scenario-form select[data-key="${key}"]`);
      if (again) again.focus();
    });
    const clear = document.getElementById("scenario-clear");
    if (clear) clear.addEventListener("click", () => { state.scenarioChoice = {}; rerender(); });
  }

  const elo = (team) => Math.round(team.ratings.elo);
  const rankOf = (team, accessor) => [...state.snapshot.teams].sort((left, right) => accessor(right) - accessor(left)).indexOf(team) + 1;

  const TABLE_VIEWS = {
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
      caption: "Ordenada pela corrida da Sul-Americana: a vaga depende de quem ganha Libertadores, Sul-Americana e Copa do Brasil, então a coluna Sul-Americana mostra a faixa entre os cenários (ou só os que combinam com a sua escolha), e Corrida mostra a posição do clube nessa disputa e, em cinza, a melhor e a pior conforme o cenário. Vale em todos os cenários = chance de terminar com a vaga seja quem for campeão desses torneios.",
    },
    rebaixamento: {
      label: "Rebaixamento",
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
    return [...FIXED_COLUMNS, ...extra];
  }

  function compareBy(column, direction) {
    return (left, right) => {
      const a = column.value(left), b = column.value(right);
      const base = typeof a === "string" ? a.localeCompare(b, "pt-BR") : a - b;
      return base * direction || left.current_position - right.current_position;
    };
  }

  const TABLE_GROUPS = [["Chances", ["titulo", "libertadores", "sul-americana", "rebaixamento"]], ["Clubes", ["forca", "dificuldade"]]];
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
    return `<div class="table-tabs">${TABLE_GROUPS.map(([group, ids]) => `<nav class="tabs" aria-label="${group}"><span class="tabs-label">${group}</span>${ids.map((id) =>
      `<a href="#/classificacao/${id}" ${id === selected ? 'aria-current="page"' : ""}>${TABLE_VIEWS[id].label}</a>`).join("")}</nav>`).join("")}</div>`;
  }

  function renderStandings(requested) {
    const snapshot = state.snapshot;
    const viewId = TABLE_VIEWS[requested] ? requested : "titulo";
    const view = TABLE_VIEWS[viewId];
    const columns = tableColumns(view);
    const chosen = state.tableSort && state.tableSort.view === viewId ? columns.find((column) => column.id === state.tableSort.id) : null;
    const order = view.order || ((team) => team.current_position);
    const teams = chosen
      ? [...snapshot.teams].sort(compareBy(chosen, state.tableSort.direction))
      : [...snapshot.teams].sort((left, right) => order(left) - order(right) || left.current_position - right.current_position);
    const fixedCount = FIXED_COLUMNS.length;
    const lastIsUpcoming = viewId === "dificuldade";
    const cellClass = (index) => `${index === fixedCount ? "view-start" : ""}${lastIsUpcoming && index === columns.length - 1 ? " left" : ""}`;
    const rows = teams.map((team) => {
      const zone = team.current_position <= 5 ? "zone-lib" : team.current_position <= 11 ? "zone-sula" : team.current_position > 16 ? "zone-z4" : "";
      const standing = standingOf(team);
      return `<tr class="${zone}">
        <td class="pos">${team.current_position}</td>
        <td class="left club">${clubLink(team.club_id)}</td>
        <td><strong>${standing.points}</strong></td><td>${standing.played}</td><td>${standing.wins}</td><td>${standing.goal_difference > 0 ? "+" : ""}${standing.goal_difference}</td>
        <td><strong>${num(team.expected_points)}</strong><div class="range" title="Faixa provável">${Math.round(team.points_interval_90[0])}–${Math.round(team.points_interval_90[1])}</div></td>
        <td>${num(team.expected_position)}</td>
        ${view.cells(team).map((cell, index) => `<td class="${cellClass(fixedCount + index)}">${cell}</td>`).join("")}
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
    main.innerHTML = `
      <span class="kicker">Tabela</span>
      <h1>Como está e como deve terminar</h1>
      <p class="lede">A tabela real em ${formatDate(snapshot.reference_date)} ao lado do que as simulações projetam para a última rodada. Escolha o que ver nas últimas colunas e clique no nome de uma coluna para ordenar.</p>
      ${tableTabs(viewId)}
      ${view.scenarios ? scenarioPanel() : ""}
      ${viewId === "dificuldade" ? difficultyNote() : ""}
      <div class="table-scroll"><table class="standings">
        <thead><tr>${head}</tr></thead>
        <tbody>${rows}</tbody></table></div>
      <div class="legend"><span class="l-lib">G5 (Libertadores via Brasileirão)</span><span class="l-sula">faixa típica da Sul-Americana</span><span class="l-z4">Z4</span></div>
      <p class="note">Pts proj. = média simulada de pontos no fim. Embaixo, a faixa provável, onde terminam 90% das simulações; nas temporadas passadas, a pontuação final ficou dentro dela menos vezes que isso (<a href="#/metodologia">Como calculamos</a>). Pos. média = posição final média nas simulações.${view.caption ? ` ${view.caption}` : ""}${chosen ? ` <button type="button" class="link-button" id="sort-reset">Voltar à ordem padrão</button>` : ""}</p>`;
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

  function lineChart(series, height = 240, annotated = null) {
    if (!state.history.length) return "<p class='note'>Sem histórico.</p>";
    const width = 640, left = 36, right = 128, top = 26, bottom = 28;
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
    const labels = ends.map(({ item, y: labelY }) => `<text class="series-end" x="${width - right + 8}" y="${(labelY + 4).toFixed(1)}" style="fill:${item.color}">${escapeHtml(item.label)} ${pct(item.values[item.values.length - 1])}</text>`).join("");
    const notes = annotated ? chartAnnotations(annotated.values).map((note) => {
      const px = x(note.index), py = y(annotated.values[note.index]);
      const above = note.above && annotated.values[note.index] < 0.85;
      const toLeft = px > left + (width - left - right) * 0.6;
      const tx = toLeft ? px - 14 : px + 14, ty = above ? py - 16 : py + 22;
      return `<g class="annotation"><circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3.5"/>
        <path d="M${px.toFixed(1)},${(py + (above ? -5 : 5)).toFixed(1)} Q${px.toFixed(1)},${ty.toFixed(1)} ${(tx + (toLeft ? 4 : -4)).toFixed(1)},${(ty - 4).toFixed(1)}" fill="none"/>
        <text x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" text-anchor="${toLeft ? "end" : "start"}">${escapeHtml(note.text)}</text></g>`;
    }).join("") : "";
    const description = series.map((item) => `${item.label} ${pct(item.values[item.values.length - 1])}`).join(", ");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolução das chances de ${formatDate(first)} a ${formatDate(last)}: ${escapeHtml(description)}${reconstructionInfo() ? " (curva recalculada com o modelo atual)" : ""}">${grid}${lines}${notes}${labels}
      <text x="${left}" y="${height - 6}">${formatDate(first)}</text><text x="${width - right}" y="${height - 6}" text-anchor="end">${formatDate(last)}</text></svg>
      ${annotated ? `<p class="note">Anotações marcam o pico e a maior virada em ${escapeHtml(annotated.label.toLowerCase())}; só aparecem variações acima de ${Math.round(MIN_ANNOTATED_JUMP * 100)} pontos percentuais e de ${NOISE_Z} vezes o erro da simulação.</p>` : ""}`;
  }

  function positionChart(probabilities) {
    const width = 640, height = 180, left = 8, bottom = 22, top = 8;
    const barWidth = (width - left * 2) / probabilities.length;
    const peak = Math.max(...probabilities, 0.01);
    const bars = probabilities.map((value, index) => {
      const barHeight = (value / peak) * (height - top - bottom);
      const color = index < 5 ? "var(--libertadores)" : index >= probabilities.length - 4 ? "var(--danger)" : "var(--ink-faint)";
      return `<rect x="${left + index * barWidth + 2}" y="${height - bottom - barHeight}" width="${barWidth - 4}" height="${barHeight}" fill="${color}"><title>${index + 1}º: ${pct(value)}</title></rect>
        <text x="${left + index * barWidth + barWidth / 2}" y="${height - 6}" text-anchor="middle">${index + 1}</text>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Distribuição da posição final">${bars}</svg>`;
  }

  function scoreOutlook(match) {
    if (!match.top_scores || !match.top_scores.length) {
      return match.most_likely_score ? ` · placar mais provável ${match.most_likely_score.replace("-", " × ")} (${pct(match.most_likely_score_probability)})` : "";
    }
    const scores = match.top_scores.map((score) => `<span class="score-chip">${score.home_goals} × ${score.away_goals} <strong>${pct(score.probability)}</strong></span>`).join("");
    const goals = match.p_three_plus_goals === null || match.p_three_plus_goals === undefined ? "" : `<span class="goals-chance">3 gols ou mais: <strong>${pct(match.p_three_plus_goals)}</strong></span>`;
    return `<span class="score-outlook"><span class="score-label">Placares mais prováveis</span>${scores}${goals}</span>`;
  }

  function matchRow(match) {
    const finished = match.status === "finished";
    const middle = finished
      ? `<div class="score">${match.home_goals} × ${match.away_goals}</div>`
      : `<div class="triple" role="img" aria-label="Mandante ${pct(match.p_home)}, empate ${pct(match.p_draw)}, visitante ${pct(match.p_away)}">
          <span class="t-home" style="width:${match.p_home * 100}%">${Math.round(match.p_home * 100)}</span>
          <span class="t-draw" style="width:${match.p_draw * 100}%">${Math.round(match.p_draw * 100)}</span>
          <span class="t-away" style="width:${match.p_away * 100}%">${Math.round(match.p_away * 100)}</span></div>`;
    const when = isPostponed(match) ? ` · <strong class="postponed">adiado, data a definir</strong>` : "";
    const meta = finished ? `Rodada ${match.round ?? "?"}` : `Rodada ${match.round ?? "?"}${when} · gols esperados ${num(match.xg_home)} × ${num(match.xg_away)}${scoreOutlook(match)}`;
    return `<div class="match"><div class="home">${clubLink(match.home_id, 22, true)}</div><div class="triple-cell">${middle}</div><div class="away">${clubLink(match.away_id, 22)}</div><div class="match-meta">${meta}</div></div>`;
  }

  function signedPercent(value) {
    const rounded = Math.round(value * 100);
    return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${Math.abs(rounded)}%`;
  }

  function renderClub(clubId) {
    const snapshot = state.snapshot;
    const byPosition = [...snapshot.teams].sort((left, right) => left.current_position - right.current_position);
    const team = teamById(clubId);
    if (!team) {
      const tiles = byPosition.map((item) => `<li><a class="club-tile" href="#/clubes/${encodeURIComponent(item.club_id)}">
        ${crest(item.club_id, 40)}<span class="club-tile-name">${escapeHtml(item.name)}</span>
        <span class="club-tile-meta">${item.current_position}º · ${item.current_points} pts</span></a></li>`).join("");
      main.innerHTML = `<span class="kicker">Clubes</span><h1>Escolha um clube</h1>
        <p class="lede">Chances, força estimada, próximos jogos e como tudo mudou ao longo do campeonato. Em ordem de classificação.</p>
        <ul class="club-grid">${tiles}</ul>`;
      return;
    }
    const picker = `<nav class="club-strip" aria-label="Trocar de clube">${byPosition.map((item) => `<a href="#/clubes/${encodeURIComponent(item.club_id)}" title="${escapeHtml(item.name)}" aria-label="${escapeHtml(item.name)}" ${item.club_id === clubId ? 'aria-current="page"' : ""}>${crest(item.club_id, 26)}</a>`).join("")}</nav>`;
    const remaining = snapshot.matches.filter((match) => match.status !== "finished" && (match.home_id === clubId || match.away_id === clubId));
    const upcoming = [...remaining.filter((match) => !isPostponed(match)).slice(0, 6), ...remaining.filter(isPostponed)];
    const scenarioRows = snapshot.scenarios.map((scenario) => ({ scenario, value: team.libertadores_total.by_scenario[scenario.scenario_id] }))
      .sort((left, right) => right.value - left.value);
    const describe = (scenario) => `Liberta: ${escapeHtml(scenario.libertadores_champion)} · Sul-Americana: ${escapeHtml(scenario.sudamericana_champion)} · Copa do Brasil: ${escapeHtml(scenario.cup_champion)} (vice ${escapeHtml(scenario.cup_runner_up)})`;
    const variesByScenario = team.libertadores_total.max - team.libertadores_total.min >= 0.01;
    const history = state.history.map((entry) => entry.teams[clubId] || { title: 0, top4: 0, relegation: 0 });
    main.innerHTML = `
      ${picker}
      <h1 class="club-heading">${crest(clubId, 48)}<span>${escapeHtml(team.name)}</span></h1>
      <p class="lede">${team.current_position}º lugar com ${team.current_points} pontos em ${team.played} jogos. Projeção: ${num(team.expected_points)} pontos (faixa provável de ${Math.round(team.points_interval_90[0])} a ${Math.round(team.points_interval_90[1])}).</p>
      <div class="stat-row">
        <div class="stat"><span class="label">Título</span><span class="big">${pct(team.title)}</span></div>
        <div class="stat"><span class="label">G4</span><span class="big">${pct(team.top4)}</span></div>
        <div class="stat"><span class="label">Libertadores</span><span class="big">${scenarioValue(team.libertadores_total)}</span><span class="sub">grupos ${scenarioValue(team.libertadores_groups)} · prévia ${scenarioValue(team.libertadores_prelim)}</span></div>
        <div class="stat"><span class="label">Sul-Americana</span><span class="big">${scenarioValue(team.sudamericana)}</span>${team.sudamericana_race ? `<span class="sub"><a href="#/classificacao/sul-americana">${team.sudamericana_race.rank}º na corrida</a></span>` : ""}</div>
        <div class="stat"><span class="label">Rebaixamento</span><span class="big">${pct(team.relegation)}</span></div>
      </div>
      <h2>Distribuição da posição final</h2>${positionChart(team.position_probabilities)}
      <h2>Evolução ao longo da temporada</h2>
      ${(() => {
        const series = [
          { key: "title", label: "Título", color: "var(--title)", values: history.map((item) => item.title) },
          { key: "top4", label: "G4", color: "var(--libertadores)", values: history.map((item) => item.top4) },
          { key: "relegation", label: "Rebaixamento", color: "var(--danger)", values: history.map((item) => item.relegation) },
        ];
        const focus = openMetric(history);
        return lineChart(series, 240, series.find((item) => item.key === focus));
      })()}
      ${reconstructionNote(reconstructionInfo())}
      <h2>Força estimada</h2>
      <div class="stat-row">
        <div class="stat"><span class="label">Elo</span><span class="big">${Math.round(team.ratings.elo)}</span><span class="sub">média da liga = 1500</span></div>
        <div class="stat"><span class="label">Ataque</span><span class="big">${signedPercent(team.ratings.attack)}</span><span class="sub">gols marcados vs. média</span></div>
        <div class="stat"><span class="label">Defesa</span><span class="big">${signedPercent(team.ratings.defense)}</span><span class="sub">positivo = sofre menos</span></div>
        <div class="stat"><span class="label">Gols projetados</span><span class="big">${Math.round(team.expected_goals_for)}–${Math.round(team.expected_goals_against)}</span><span class="sub">pró–contra no fim</span></div>
      </div>
      ${clubSchedule(team)}
      <h2>Próximos jogos</h2>${upcoming.length ? upcoming.map(matchRow).join("") : "<p class='note'>Sem jogos restantes.</p>"}
      <h2>Cenários externos</h2>
      ${variesByScenario ? `<p class="note">A chance de Libertadores depende dos torneios ainda em disputa.</p>
        <h3>Mais favorável: ${pct(scenarioRows[0].value)}</h3><p class="note">${describe(scenarioRows[0].scenario)}</p>
        <h3>Menos favorável: ${pct(scenarioRows[scenarioRows.length - 1].value)}</h3><p class="note">${describe(scenarioRows[scenarioRows.length - 1].scenario)}</p>`
        : `<p class="note">Os resultados de Libertadores, Sul-Americana e Copa do Brasil praticamente não alteram a chance de vaga deste clube (${scenarioValue(team.libertadores_total)}).</p>`}`;
  }

  function clubSchedule(team) {
    const schedule = team.schedule;
    if (!schedule) return "";
    const venueStat = (label, value, rank, points, games) => (value === null || value === undefined ? "" : `<div class="stat"><span class="label">${label}</span><span class="big">${Math.round(value)}</span><span class="sub">${rank === 1 ? "a mais difícil" : `${rank}ª mais difícil`} · ${num(points)} pts esperados em ${games} ${games === 1 ? "jogo" : "jogos"}</span></div>`);
    const gap = schedule.expected_points - schedule.average_team_points;
    return `<h2>Dificuldade do que falta</h2>
      <div class="stat-row">
        <div class="stat"><span class="label">Tabela</span><span class="big">${Math.round(schedule.difficulty)}</span><span class="sub">${schedule.difficulty_rank === 1 ? "a mais difícil das 20" : `${schedule.difficulty_rank}ª mais difícil das 20`}</span></div>
        ${venueStat("Em casa", schedule.difficulty_home, schedule.difficulty_home_rank, schedule.expected_points_home, schedule.home_matches)}
        ${venueStat("Fora", schedule.difficulty_away, schedule.difficulty_away_rank, schedule.expected_points_away, schedule.away_matches)}
      </div>
      <p>Nos ${schedule.remaining_matches} jogos que faltam, ${escapeHtml(team.name)} deve somar <strong>${num(schedule.expected_points)} pontos</strong>. Um time de força média faria ${num(schedule.average_team_points)} contra os mesmos adversários${Math.abs(gap) >= 0.5 ? `: a força do clube ${gap > 0 ? "soma" : "tira"} ${num(Math.abs(gap))} ${Math.abs(gap) >= 1.5 ? "pontos" : "ponto"}` : ""}.</p>
      <p class="upcoming-line">Próximos adversários ${upcomingCrests(team)}</p>
      ${difficultyNote()}`;
  }

  function renderMatches() {
    const snapshot = state.snapshot;
    const remaining = snapshot.matches.filter((match) => match.status !== "finished" && !isPostponed(match));
    const postponed = snapshot.matches.filter(isPostponed);
    const recent = snapshot.matches.filter((match) => match.status === "finished").slice(-10).reverse();
    const byDate = {};
    remaining.forEach((match) => { (byDate[match.match_date] = byDate[match.match_date] || []).push(match); });
    main.innerHTML = `
      <span class="kicker">Jogos</span>
      <h1>O que esperar de cada jogo</h1>
      <p class="lede">Chance de vitória do mandante, de empate e de vitória do visitante, com a força de cada clube em ${formatDate(snapshot.reference_date)}.</p>
      <div class="legend"><span class="l-home">mandante</span><span class="l-draw">empate</span><span class="l-away">visitante</span></div>
      ${overdueWarning()}
      ${Object.entries(byDate).map(([day, matches]) => `<section class="match-day"><h3>${formatShortDate(day)}</h3>${matches.map(matchRow).join("")}</section>`).join("")}
      ${postponed.length ? `<section class="match-day"><h3>Adiado, data a definir</h3>${postponed.map(matchRow).join("")}
        <p class="note">Nas simulações, ${postponed.length === 1 ? "este jogo conta" : "estes jogos contam"} como ainda a disputar.</p></section>` : ""}
      <h2>Últimos resultados</h2>${recent.map(matchRow).join("")}`;
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
      return `<h2>Histórico das chances</h2>
      <p>O gráfico de evolução de cada clube não guarda as previsões antigas. A cada atualização, refazemos a temporada inteira: para cada data de referência, o modelo atual roda as simulações usando só os resultados conhecidos até aquela data. Por isso a curva inteira muda quando o modelo muda ou quando um placar é corrigido na fonte, e um ponto antigo pode não bater com o que este site mostrou naquele dia. ${version} A aba Rodada a rodada é feita do mesmo jeito.</p>`;
    }
    if (state.rounds) {
      return `<h2>Histórico das chances</h2><p>A aba Rodada a rodada não guarda as previsões antigas. A cada atualização, o modelo atual refaz a véspera de cada rodada usando só os resultados conhecidos até ali.</p>`;
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
      <p>Situação em ${escapeHtml(snapshot.external_context.as_of)}: ${snapshot.external_context.notes.map(escapeHtml).join(" ")} Como esses torneios não têm vencedor definido, mostramos faixas entre os ${snapshot.scenarios.length} cenários possíveis. Não estimamos a chance de cada um.</p>
      <p class="note">Interpretação do § 5º do Art. 6º adotada: "${escapeHtml(snapshot.external_context.cup_redirect_policy)}" (texto ambíguo; ver documentação).</p>
      <p>Na corrida da Sul-Americana, os clubes são ordenados pela faixa entre os cenários. A coluna "vale em todos os cenários" é a chance de terminar com a vaga seja quem for campeão dos outros torneios; ela nunca atribui peso a um cenário.</p>
      <h2>Dificuldade da tabela</h2>
      <p>Para cada jogo que falta, calculamos quantos pontos um time de força média faria contra aquele adversário, naquele mando, com o mesmo modelo dos jogos. A soma vira uma nota de 0 a 100: 50 é uma tabela média do campeonato, e quanto maior, menos pontos um time comum faria. Jogar fora é sempre mais difícil, por isso casa e fora também têm posição entre os 20. Os pontos esperados do clube usam a força dele e as chances de cada jogo.</p>
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
      <p>Os escudos vêm do Wikimedia Commons, onde estão em domínio público por não atingirem originalidade (PD-textlogo; Mirassol e São Paulo também PD-shape). Domínio público de direito autoral não muda a marca: os escudos são marcas registradas dos clubes, aparecem só para identificar cada time e não indicam relação nem apoio dos clubes ao AInda dá?. Red Bull Bragantino, Corinthians e Vasco da Gama aparecem com a sigla e as cores do clube, porque não há escudo atual deles com licença livre.</p>
      <h2>Limitações</h2>
      <ul>
        <li>O modelo não conhece lesões, suspensões, troca de treinador nem rodízio por outras competições.</li>
        <li>Os gols simulados não geram cartões; os critérios de cartões usam apenas jogos já disputados.</li>
        <li>${fixedRatings ? "A força de cada clube fica fixa na data de referência durante toda a simulação: uma sequência de vitórias simuladas não deixa o time mais forte nas rodadas seguintes." : "As probabilidades dos jogos usam a força na data de referência; dentro das simulações, a força evolui."}</li>
        <li>Percentuais muito pequenos ou muito grandes ainda são incertos: "0%" significa que o desfecho não ocorreu em nenhuma simulação, não que seja impossível.</li>
      </ul>`;
  }

  let lastSection = null;

  function route() {
    if (!state.snapshot) return;
    const [, section = "", parameter = "", ...rest] = location.hash.replace(/^#/, "").split("/");
    const isHome = !section || section === "inicio";
    document.querySelectorAll(".masthead nav a").forEach((link) => {
      const active = (link.dataset.route === "home" && isHome) || link.dataset.route === section;
      if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
    if (section === "classificacao") renderStandings(parameter);
    else if (section === "clubes") renderClub(decodeURIComponent(parameter));
    else if (section === "partidas") renderMatches();
    else if (section === "rodadas") {
      window.Rounds.render(main, [parameter, ...rest], { review: state.rounds, escapeHtml, pct, num, formatDate, formatShortDate, highlights: roundHighlights });
    }
    else if (section === "metodologia") renderMethodology();
    else renderHome(parameter);
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
    state.snapshot = await fetchJson(`/seasons/${SEASON}/predictions`);
    if (!state.snapshot) {
      main.innerHTML = "<h1>Previsões indisponíveis</h1><p class='lede'>Nenhum snapshot encontrado. Rode <code>python -m brasileirao.cli simulate</code> e recarregue a página.</p>";
      document.getElementById("reference-bar").textContent = "";
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
  }

  window.addEventListener("hashchange", route);
  start();
})();
