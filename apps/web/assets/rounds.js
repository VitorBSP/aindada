/* Aba "Rodada a rodada": avaliação por rodada, por time e comparativo entre times.
   Lê a revisão gerada por `brasileirao.cli review-rounds` e os escudos de assets/crests/manifest.json. */
(function () {
  "use strict";

  const METRIC_LABELS = { title: "título", top4: "G4", relegation: "rebaixamento" };
  const METRIC_TITLES = { title: "Título", top4: "G4", relegation: "Rebaixamento" };
  const COMPARE_METRICS = {
    title: { label: "Título", kind: "share" },
    top4: { label: "G4", kind: "share" },
    relegation: { label: "Rebaixamento", kind: "share" },
    position: { label: "Posição na tabela", kind: "position" },
    points: { label: "Pontos", kind: "count" },
    expected_points: { label: "Pontos projetados", kind: "count" },
  };
  /* Até 3 séries por gráfico: cores dos tokens validadas para daltonismo, e cada série também tem traço e marcador próprios. */
  const SERIES = [
    { color: "var(--title)", dash: "", marker: "circle", name: "linha contínua, círculo" },
    { color: "var(--libertadores)", dash: "7 4", marker: "square", name: "linha tracejada, quadrado" },
    { color: "var(--sudamericana)", dash: "2 4", marker: "triangle", name: "linha pontilhada, triângulo" },
  ];
  const MAX_COMPARE = SERIES.length;
  /* Página do time: cada série tem significado fixo; queda usa --danger como no resto do site.
     Tinta, azul e vermelho também passam no validador de paleta (daltonismo) nos dois temas. */
  const TEAM_SERIES = [SERIES[0], SERIES[1], { color: "var(--danger)", dash: "2 4", marker: "triangle", name: "linha pontilhada, triângulo" }];

  const ui = { metric: "title", teamMetric: {}, compare: null, compareMetric: "title", compareRound: null };
  const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
  const BADGE_LABEL = /^[A-Z]{2,4}$/;
  let crests = {};
  let crestsRequested = false;
  let helpers = null;
  let review = null;
  let main = null;

  const h = () => helpers;
  const escapeHtml = (text) => h().escapeHtml(text);
  const pct = (value) => h().pct(value);
  const num = (value, digits) => h().num(value, digits);
  const formatDate = (iso) => h().formatDate(iso);
  const formatShortDate = (iso) => h().formatShortDate(iso);

  async function loadCrests(rerender) {
    if (crestsRequested) return;
    crestsRequested = true;
    try {
      const response = await fetch("assets/crests/manifest.json", { headers: { Accept: "application/json" } });
      if (response.ok) {
        crests = await response.json();
        rerender();
      }
    } catch (error) { /* sem escudos: a interface usa só os nomes */ }
  }

  function crest(clubId, size = 20) {
    const entry = crests[clubId];
    if (entry && entry.file) {
      return `<img class="crest" src="assets/crests/${encodeURIComponent(entry.file)}" alt="" width="${size}" height="${size}" loading="lazy" decoding="async">`;
    }
    const badge = entry && entry.badge;
    if (badge && typeof badge.label === "string" && BADGE_LABEL.test(badge.label) && HEX_COLOR.test(badge.bg) && HEX_COLOR.test(badge.fg)) {
      const text = size < 32 ? badge.label.charAt(0) : badge.label;
      const fontSize = Math.round(size * (size < 32 ? 0.6 : 0.32));
      return `<span class="crest crest-badge" aria-hidden="true" style="width:${size}px;height:${size}px;font-size:${fontSize}px;--badge-bg:${badge.bg};--badge-fg:${badge.fg}">${escapeHtml(text)}</span>`;
    }
    return size > 24 ? "" : `<span class="crest-spacer" style="width:${size}px" aria-hidden="true"></span>`;
  }

  const clubName = (clubId) => (review.clubs[clubId] || { name: clubId }).name;
  const clubShort = (clubId) => (review.clubs[clubId] || { short_name: clubId }).short_name;
  const clubLabel = (clubId, size = 20) => `<span class="club-cell">${crest(clubId, size)}<span>${escapeHtml(clubName(clubId))}</span></span>`;
  const teamLink = (clubId) => `<a class="club-cell" href="#/rodadas/time/${encodeURIComponent(clubId)}">${crest(clubId)}<span>${escapeHtml(clubName(clubId))}</span></a>`;
  const roundLabel = (view) => view.round_number === 0 ? "Pré-temporada" : `Rodada ${view.round_number}${view.partial ? " (parcial)" : ""}`;
  const shortRoundLabel = (view) => view.round_number === 0 ? "Pré" : `R${view.round_number}`;
  const matchLabel = (match) => `${escapeHtml(clubName(match.home_id))} ${match.home_goals} × ${match.away_goals} ${escapeHtml(clubName(match.away_id))}`;
  const hasTable = (view) => view.teams && Object.values(view.teams).some((values) => (values.played || 0) > 0);
  const latestView = () => review.rounds[review.rounds.length - 1];

  function signedPp(delta, digits = 1) {
    const value = delta * 100;
    if (Math.abs(value) < 0.05) return "0";
    return (value > 0 ? "+" : "−") + num(Math.abs(value), digits);
  }

  function deltaSpan(delta, metric) {
    const good = metric === "relegation" ? delta < 0 : delta > 0;
    const css = Math.abs(delta) < 0.0005 ? "" : good ? "change-up" : "change-down";
    return `<span class="${css}">${signedPp(delta)}</span>`;
  }

  function positionText(values) {
    return values && values.played > 0 && values.position ? `${values.position}º` : "–";
  }

  function metricPicker(current, options, attribute, extraClass = "") {
    return `<div class="metric-picker ${extraClass}" role="group" aria-label="Métrica">${Object.entries(options).map(([key, label]) =>
      `<button type="button" data-${attribute}="${key}" aria-pressed="${key === current}">${escapeHtml(typeof label === "string" ? label : label.label)}</button>`).join("")}</div>`;
  }

  function tabs(active) {
    const items = [["rodada", "#/rodadas", "Por rodada"], ["time", "#/rodadas/time", "Por time"], ["comparar", "#/rodadas/comparar", "Comparar times"]];
    return `<nav class="rounds-tabs" aria-label="Visões da aba Rodada a rodada">${items.map(([key, href, label]) =>
      `<a href="${href}" ${key === active ? 'aria-current="page"' : ""}>${label}</a>`).join("")}</nav>`;
  }

  function header(active, lede) {
    return `<span class="kicker">Rodada a rodada</span>
      <h1>${active === "time" ? "Cada time, rodada a rodada" : active === "comparar" ? "Times lado a lado" : "O que mudou em cada rodada"}</h1>
      <p class="lede">${lede}</p>
      ${tabs(active)}`;
  }

  /* ---------- intensidade de uma rodada em relação à temporada ---------- */

  function movementOf(view, metric) {
    return view.summary ? view.summary.total_movement[metric] / 2 : 0;
  }

  function intensityScale(metric) {
    const values = review.rounds.filter((view) => view.summary).map((view) => movementOf(view, metric)).sort((a, b) => a - b);
    const quantile = (q) => values[Math.min(values.length - 1, Math.floor(q * values.length))] || 0;
    return { low: quantile(0.25), high: quantile(0.75) };
  }

  function intensityLabel(view, metric, scale) {
    if (!view.summary) return "";
    const value = movementOf(view, metric);
    if (value >= scale.high) return '<span class="intensity intensity-high">agitada</span>';
    if (value <= scale.low) return '<span class="intensity intensity-low">calma</span>';
    return '<span class="intensity">normal</span>';
  }

  /* ---------- por rodada ---------- */

  function movementChart(metric, selected) {
    const views = review.rounds;
    const width = 640, height = 170, left = 8, right = 8, top = 10, bottom = 24;
    const values = views.map((view) => movementOf(view, metric));
    const strength = views.map((view) => view.summary ? view.summary.strength_movement[metric] / 2 : 0);
    const peak = Math.max(...values, 0.01);
    const slot = (width - left - right) / views.length;
    const scale = (value) => (value / peak) * (height - top - bottom);
    const bars = views.map((view, index) => {
      if (!view.summary) return "";
      const x = left + index * slot + 1;
      const total = scale(values[index]);
      const fromStrength = Math.min(scale(strength[index]), total);
      const current = view.round_number === selected ? " current" : "";
      return `<a href="#/rodadas/${view.round_number}" aria-label="${roundLabel(view)}: ${num(values[index] * 100)} pontos percentuais redistribuídos">
        <rect class="move-bar${current}" x="${x}" y="${height - bottom - total}" width="${Math.max(slot - 2, 1)}" height="${total - fromStrength}"><title>${roundLabel(view)}: ${num(values[index] * 100)} p.p. (${num((values[index] - strength[index]) * 100)} dos resultados, ${num(strength[index] * 100)} da força)</title></rect>
        <rect class="move-bar strength${current}" x="${x}" y="${height - bottom - fromStrength}" width="${Math.max(slot - 2, 1)}" height="${fromStrength}"></rect></a>`;
    }).join("");
    const ticks = views.filter((view) => view.round_number % 5 === 0).map((view) => {
      const index = views.indexOf(view);
      return `<text x="${left + index * slot + slot / 2}" y="${height - 6}" text-anchor="middle">${view.round_number}</text>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Chance de ${METRIC_LABELS[metric]} redistribuída em cada rodada">${bars}${ticks}</svg>
      <div class="note"><span class="swatch swatch-results"></span> resultados &nbsp; <span class="swatch swatch-strength"></span> reavaliação de força · altura = pontos percentuais (p.p.) de chance de ${METRIC_LABELS[metric]} que trocaram de clube na rodada</div>`;
  }

  function roundHeadline(view, metric) {
    const summary = view.summary;
    const riser = summary.risers[metric][0];
    const faller = summary.fallers[metric][0];
    const decisive = view.matches.find((match) => match.match_id === summary.decisive_match_id);
    const surprise = view.matches.find((match) => match.match_id === summary.surprise_match_id);
    const items = [];
    if (riser) items.push(`Quem mais subiu em ${METRIC_LABELS[metric]}: ${teamLink(riser.club_id)} ${deltaSpan(riser.delta, metric)} p.p. (agora ${pct(view.teams[riser.club_id][metric])}).`);
    if (faller) items.push(`Quem mais caiu em ${METRIC_LABELS[metric]}: ${teamLink(faller.club_id)} ${deltaSpan(faller.delta, metric)} p.p. (agora ${pct(view.teams[faller.club_id][metric])}).`);
    if (decisive) items.push(`Jogo que mais mexeu nas chances: <strong>${matchLabel(decisive)}</strong>.`);
    if (surprise) items.push(`Maior surpresa: <strong>${matchLabel(surprise)}</strong>. Esse resultado tinha ${pct(surprise.pre_match[surprise.outcome])} de chance antes do jogo.`);
    const moved = movementOf(view, metric);
    items.push(`${num(moved * 100)} p.p. de chance de ${METRIC_LABELS[metric]} trocaram de clube: ${num(summary.results_movement[metric] / 2 * 100)} p.p. pelos resultados (pontos na tabela) e ${num(summary.strength_movement[metric] / 2 * 100)} p.p. pela reavaliação da força dos times.`);
    items.push(`<span class="note">Parte do efeito dos resultados que não dá para pôr na conta de um jogo só: ${num(summary.residual_movement[metric] / 2 * 100)} p.p. O ruído esperado da simulação é de ~${num(summary.expected_noise_movement[metric] / 2 * 100)} p.p.; o resto vem da combinação de resultados na mesma rodada.</span>`);
    return `<ul class="summary-list">${items.map((item) => `<li>${item}</li>`).join("")}</ul>`;
  }

  function roundTable(view, metric) {
    const showTable = hasTable(view);
    const clubs = Object.keys(view.teams).sort((left, right) => showTable
      ? view.teams[left].position - view.teams[right].position
      : view.teams[right][metric] - view.teams[left][metric]);
    const moved = (club) => view.summary && [view.changes, view.results_effect, view.strength_effect]
      .some((values) => Math.abs(values[club][metric]) >= 0.0005);
    const shown = clubs.filter((club) => view.teams[club][metric] >= 0.0005 || moved(club));
    const hidden = clubs.length - shown.length;
    const rows = shown.map((club) => {
      const values = view.teams[club];
      const change = view.changes[club] ? view.changes[club][metric] : 0;
      return `<tr>
        <td class="pos">${positionText(values)}</td>
        <td class="left club">${teamLink(club)}</td>
        <td>${showTable ? values.points ?? "–" : "–"}</td>
        <td>${num(values.expected_points)}</td>
        <td>${pct(values[metric])}</td>
        <td>${!view.summary ? "–" : Math.abs(change) >= 0.0005 ? `<strong>${deltaSpan(change, metric)}</strong>` : deltaSpan(change, metric)}</td>
        <td>${view.summary ? deltaSpan(view.results_effect[club][metric], metric) : "–"}</td>
        <td>${view.summary ? deltaSpan(view.strength_effect[club][metric], metric) : "–"}</td>
      </tr>`;
    }).join("");
    return `<div class="table-scroll"><table>
      <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>Pts proj.</th><th>${METRIC_TITLES[metric]}</th><th>Variação (p.p.)</th><th>Resultados</th><th>Força</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      ${hidden ? `<p class="note">${hidden === clubs.length ? "Nenhum clube" : `Os outros ${hidden} clubes não`} ${hidden === clubs.length ? "aparece" : "aparecem"} com ${METRIC_LABELS[metric]} nas simulações${view.summary ? ", nem antes nem depois desta rodada" : ""}. A tabela completa está em <a href="#/rodadas/comparar">Comparar times</a>.</p>` : ""}`;
  }

  function noiseFloor(match, metric, key, previousView, club) {
    const total = review.n_simulations;
    const probability = previousView.teams[club][metric];
    const variance = probability * (1 - probability);
    if (key === "impacts") {
      const count = Math.max(match.pre_match[match.outcome] * total, 1);
      return 2 * Math.sqrt(variance * Math.max(1 / count - 1 / total, 0));
    }
    const rarest = Math.max(Math.min(...Object.values(match.pre_match)) * total, 1);
    return 2 * Math.sqrt((2 * variance) / rarest);
  }

  function relevantImpacts(match, metric, key, threshold, previousView) {
    return Object.entries(match[key]).map(([club, values]) => ({ club, value: values[metric] }))
      .filter((entry) => Math.abs(entry.value) >= Math.max(threshold, noiseFloor(match, metric, key, previousView, entry.club)))
      .sort((left, right) => Math.abs(right.value) - Math.abs(left.value));
  }

  function impactChips(match, metric, key, threshold, previousView) {
    const entries = relevantImpacts(match, metric, key, threshold, previousView).slice(0, 6);
    return entries.map((entry) => key === "impacts"
      ? `<span class="chip">${crest(entry.club, 16)}${escapeHtml(clubShort(entry.club))} ${deltaSpan(entry.value, metric)}</span>`
      : `<span class="chip">${crest(entry.club, 16)}${escapeHtml(clubShort(entry.club))} ${num(entry.value * 100)}</span>`).join("");
  }

  function matchCard(match, metric, previousView, view) {
    const pre = match.pre_match;
    const effect = impactChips(match, metric, "impacts", 0.005, previousView);
    const stakes = impactChips(match, metric, "stakes", 0.01, previousView);
    const offRound = match.round !== view.round_number ? ` · jogo da rodada ${match.round}` : "";
    return `<div class="match">
      <div class="home">${teamLink(match.home_id)}</div>
      <div class="triple-cell"><div class="score">${match.home_goals} × ${match.away_goals}</div></div>
      <div class="away">${teamLink(match.away_id)}</div>
      <div class="match-meta">${formatShortDate(match.match_date)}${offRound} · antes do jogo: mandante ${pct(pre.home)}, empate ${pct(pre.draw)}, visitante ${pct(pre.away)}</div>
      <div class="impact-row">${effect ? `<span class="impact-label">Efeito em ${METRIC_LABELS[metric]} (p.p.):</span> ${effect}` : `<span class="note">Sem efeito em ${METRIC_LABELS[metric]} que se distinga do ruído da simulação.</span>`}</div>
      ${stakes ? `<div class="impact-row"><span class="impact-label">Estava em jogo (melhor menos pior resultado, p.p.):</span> ${stakes}</div>` : ""}
    </div>`;
  }

  function seasonEvaluation(metric) {
    const scale = intensityScale(metric);
    const rows = review.rounds.map((view) => {
      const favourite = Object.entries(view.teams).sort((left, right) => right[1].title - left[1].title)[0];
      const leader = hasTable(view) ? Object.entries(view.teams).find(([, values]) => values.position === 1) : null;
      const summary = view.summary;
      const decisive = summary && view.matches.find((match) => match.match_id === summary.decisive_match_id);
      const surprise = summary && view.matches.find((match) => match.match_id === summary.surprise_match_id);
      const riser = summary && summary.risers[metric][0];
      const faller = summary && summary.fallers[metric][0];
      return `<tr>
        <td class="left"><a href="#/rodadas/${view.round_number}">${roundLabel(view)}</a><div class="range">${formatDate(view.reference_date)}</div></td>
        <td>${view.matches.length || "–"}</td>
        <td>${summary ? num(movementOf(view, metric) * 100) : "–"}</td>
        <td class="left">${intensityLabel(view, metric, scale)}</td>
        <td class="left">${leader ? clubLabel(leader[0]) : "–"}</td>
        <td class="left">${clubLabel(favourite[0])} <span class="range">${pct(favourite[1].title)}</span></td>
        <td class="left">${riser ? `${clubLabel(riser.club_id)} ${deltaSpan(riser.delta, metric)}` : "–"}</td>
        <td class="left">${faller ? `${clubLabel(faller.club_id)} ${deltaSpan(faller.delta, metric)}` : "–"}</td>
        <td class="left">${decisive ? matchLabel(decisive) : "–"}</td>
        <td class="left">${surprise ? `${matchLabel(surprise)} <span class="range">${pct(surprise.pre_match[surprise.outcome])}</span>` : "–"}</td>
      </tr>`;
    }).join("");
    return `<div class="table-scroll"><table class="season-table">
      <thead><tr><th class="left">Rodada</th><th>Jogos</th><th>p.p. em jogo</th><th class="left">Rodada foi</th><th class="left">Líder da tabela</th><th class="left">Favorito ao título</th><th class="left">Mais subiu (${METRIC_LABELS[metric]})</th><th class="left">Mais caiu</th><th class="left">Jogo decisivo</th><th class="left">Maior surpresa</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="note">"Rodada foi": agitada se ficou entre as 25% que mais mexeram na chance de ${METRIC_LABELS[metric]} na temporada; calma se ficou entre as 25% que menos mexeram.</p>`;
  }

  function renderRound(parameter) {
    const views = review.rounds;
    const requested = Number.parseInt(parameter, 10);
    const view = views.find((item) => item.round_number === requested) || latestView();
    const index = views.indexOf(view);
    const metric = ui.metric;
    const previous = views[index - 1], next = views[index + 1];
    const navigation = `<div class="round-nav">
      ${previous ? `<a class="button" href="#/rodadas/${previous.round_number}">← ${roundLabel(previous)}</a>` : "<span></span>"}
      <label>Rodada <select id="round-select">${views.map((item) => `<option value="${item.round_number}" ${item === view ? "selected" : ""}>${roundLabel(item)} · ${formatDate(item.reference_date)}</option>`).join("")}</select></label>
      ${next ? `<a class="button" href="#/rodadas/${next.round_number}">${roundLabel(next)} →</a>` : "<span></span>"}
    </div>`;
    const body = view.summary
      ? `<h2>Resumo: ${roundLabel(view)} ${intensityLabel(view, metric, intensityScale(metric))}</h2>${roundHeadline(view, metric)}
        <h2>Como ficou cada clube</h2>
        <p class="note">Tabela real em ${formatDate(view.reference_date)} e variação desde ${formatDate(previous.reference_date)}. <strong>Resultados</strong>: efeito dos jogos, com a força dos times congelada. <strong>Força</strong>: efeito da reavaliação dos times depois desses jogos. As duas colunas somam a variação.</p>
        ${roundTable(view, metric)}
        <h2>Jogos do intervalo e quem eles afetaram</h2>
        <p class="note">Efeito = chance de ${METRIC_LABELS[metric]} com o resultado real menos a chance antes do jogo, medida nas simulações feitas antes da bola rolar. Inclui jogos adiados de outras rodadas. Só aparecem efeitos acima de 2 erros-padrão do ruído da simulação.</p>
        ${[...view.matches].sort((left, right) => relevantImpacts(right, metric, "impacts", 0, previous).reduce((t, e) => t + Math.abs(e.value), 0) - relevantImpacts(left, metric, "impacts", 0, previous).reduce((t, e) => t + Math.abs(e.value), 0)).map((match) => matchCard(match, metric, previous, view)).join("")}`
      : `<h2>Pré-temporada</h2><p>Antes do primeiro jogo, só com a força herdada da temporada anterior (com regressão à média; promovidos recebem a média dos rebaixados).</p>
        ${roundTable(view, metric)}`;
    main.innerHTML = `
      ${header("rodada", `Como o modelo via o campeonato na véspera de cada rodada, desde a pré-temporada, e o que fez as chances mudarem. ${views.length} visões com ${review.n_simulations.toLocaleString("pt-BR")} simulações cada; dados até ${formatDate(review.data_until)}.`)}
      ${helpers.highlights ? helpers.highlights(view) : ""}
      ${metricPicker(metric, METRIC_TITLES, "metric")}
      <h2>Onde o campeonato mudou</h2>
      ${movementChart(metric, view.round_number)}
      ${navigation}
      ${body}
      <h2>Avaliação de todas as rodadas</h2>
      ${seasonEvaluation(metric)}`;
    document.getElementById("round-select").addEventListener("change", (event) => { location.hash = `#/rodadas/${event.target.value}`; });
    bindPicker("metric", (value) => { ui.metric = value; renderRound(String(view.round_number)); });
  }

  /* ---------- gráfico de séries (por time e comparativo) ---------- */

  function markerShape(kind, x, y, color) {
    if (kind === "square") return `<rect x="${x - 3.5}" y="${y - 3.5}" width="7" height="7" fill="${color}" class="marker"/>`;
    if (kind === "triangle") return `<path d="M${x},${y - 4.5}L${x + 4.5},${y + 3.5}L${x - 4.5},${y + 3.5}Z" fill="${color}" class="marker"/>`;
    return `<circle cx="${x}" cy="${y}" r="4" fill="${color}" class="marker"/>`;
  }

  function seriesChart({ series, domain, invert = false, format, ariaLabel, guides = [], styles = SERIES }) {
    const views = review.rounds;
    const width = 640, height = 240, left = 40, right = 124, top = 12, bottom = 26;
    const [low, high] = domain;
    const x = (index) => left + (views.length === 1 ? 0 : (index / (views.length - 1)) * (width - left - right));
    const y = (value) => {
      const share = (value - low) / ((high - low) || 1);
      return top + (invert ? share : 1 - share) * (height - top - bottom);
    };
    const gridValues = guides.length ? guides : [low, low + (high - low) / 2, high];
    const grid = gridValues.map((guide) => {
      const value = typeof guide === "object" ? guide.value : guide;
      const label = typeof guide === "object" ? guide.label : format(value);
      return `<line class="axis" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"/><text x="${left - 6}" y="${y(value) + 4}" text-anchor="end">${escapeHtml(label)}</text>`;
    }).join("");
    const ticks = views.map((view, index) => view.round_number % 5 === 0
      ? `<text x="${x(index)}" y="${height - 8}" text-anchor="middle">${view.round_number}</text>` : "").join("");
    const endPoints = series.map((item) => {
      const index = item.values.map((value) => value !== null && value !== undefined).lastIndexOf(true);
      return index < 0 ? null : { x: x(index), y: y(item.values[index]) };
    });
    const labelY = spreadLabels(endPoints.map((point) => point ? point.y : null), 15, top + 4, height - bottom);
    const lines = series.map((item, seriesIndex) => {
      const style = styles[seriesIndex % styles.length];
      const points = item.values.map((value, index) => value === null || value === undefined ? null : [x(index), y(value)]);
      let path = "";
      points.forEach((point, index) => {
        if (!point) return;
        path += `${path && points[index - 1] ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`;
      });
      const markers = points.map((point, index) => point && (index % 5 === 0 || index === points.length - 1)
        ? markerShape(style.marker, point[0], point[1], style.color) : "").join("");
      const end = endPoints[seriesIndex];
      const labelText = end ? `<text class="series-label" x="${end.x + 8}" y="${labelY[seriesIndex] + 4}">${escapeHtml(item.label)}</text>` : "";
      return `<path d="${path}" fill="none" stroke="${style.color}" stroke-width="2" stroke-dasharray="${style.dash}" stroke-linejoin="round"/>${markers}${labelText}`;
    }).join("");
    const columnWidth = (width - left - right) / Math.max(views.length - 1, 1);
    const hover = views.map((view, index) => {
      const lines = series.map((item) => `${item.label}: ${item.values[index] === null || item.values[index] === undefined ? "–" : format(item.values[index])}`).join(" · ");
      return `<rect class="hit" x="${x(index) - columnWidth / 2}" y="${top}" width="${columnWidth}" height="${height - top - bottom}"><title>${roundLabel(view)} (${formatDate(view.reference_date)}): ${escapeHtml(lines)}</title></rect>`;
    }).join("");
    const legend = series.map((item, seriesIndex) => {
      const style = styles[seriesIndex % styles.length];
      return `<span class="legend-item"><svg width="30" height="12" aria-hidden="true"><line x1="0" x2="30" y1="6" y2="6" stroke="${style.color}" stroke-width="2" stroke-dasharray="${style.dash}"/>${markerShape(style.marker, 15, 6, style.color)}</svg>${escapeHtml(item.label)}</span>`;
    }).join("");
    return `<svg class="chart series-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(ariaLabel)}">${grid}${ticks}${lines}${hover}</svg>
      <div class="series-legend">${legend}<span class="note">eixo: rodada · passe o mouse para ver os valores</span></div>`;
  }

  /* Afasta rótulos de fim de linha que ficariam sobrepostos, mantendo a ordem vertical. */
  function spreadLabels(positions, gap, minimum, maximum) {
    const order = positions.map((value, index) => ({ value, index })).filter((item) => item.value !== null).sort((a, b) => a.value - b.value);
    const placed = [...positions];
    order.forEach((item, rank) => {
      const previous = rank ? placed[order[rank - 1].index] : minimum - gap;
      placed[item.index] = Math.max(item.value, previous + gap);
    });
    const overflow = order.length ? placed[order[order.length - 1].index] - maximum : 0;
    if (overflow > 0) order.forEach((item) => { placed[item.index] -= overflow; });
    return placed;
  }

  const shareFormat = (value) => pct(value);
  const positionFormat = (value) => `${Math.round(value)}º`;
  const countFormat = (value) => num(value, 0);

  /* ---------- por time ---------- */

  function teamMatchesInRound(view, clubId) {
    return view.matches.filter((match) => match.home_id === clubId || match.away_id === clubId);
  }

  function teamResult(match, clubId) {
    const home = match.home_id === clubId;
    const scored = home ? match.home_goals : match.away_goals;
    const conceded = home ? match.away_goals : match.home_goals;
    const letter = scored > conceded ? "V" : scored === conceded ? "E" : "D";
    const opponent = home ? match.away_id : match.home_id;
    return { letter, text: `${letter} ${scored}×${conceded} ${clubShort(opponent)}${home ? "" : " (fora)"}`, opponent };
  }

  /* Métrica em que a pergunta "ainda dá?" está mais aberta para o clube: maior p·(1 − p) hoje;
     se tudo estiver decidido, a de maior probabilidade. */
  function openMetric(clubId) {
    const now = latestView().teams[clubId];
    const metrics = Object.keys(METRIC_TITLES);
    const open = metrics.map((metric) => ({ metric, spread: now[metric] * (1 - now[metric]) })).sort((a, b) => b.spread - a.spread)[0];
    if (open.spread > 0.0001) return open.metric;
    return metrics.sort((a, b) => now[b] - now[a])[0];
  }

  /* Duas estimativas independentes da mesma chance: 2 erros-padrão da diferença. */
  function changeNoise(before, after) {
    const total = review.n_simulations;
    return 2 * Math.sqrt((before * (1 - before) + after * (1 - after)) / total);
  }

  function keyMoments(clubId, metric) {
    const moments = review.rounds.map((view, index) => {
      if (!view.summary) return null;
      const previous = review.rounds[index - 1];
      const delta = view.changes[clubId][metric];
      if (Math.abs(delta) < Math.max(0.001, changeNoise(previous.teams[clubId][metric], view.teams[clubId][metric]))) return null;
      const own = teamMatchesInRound(view, clubId);
      const biggest = view.matches.map((match) => ({ match, value: match.impacts[clubId] ? match.impacts[clubId][metric] : 0 }))
        .filter((entry) => Math.abs(entry.value) >= Math.max(0.005, noiseFloor(entry.match, metric, "impacts", previous, clubId)))
        .sort((left, right) => Math.abs(right.value) - Math.abs(left.value))[0];
      return { view, delta, own, biggest, strength: view.strength_effect[clubId][metric] };
    }).filter(Boolean);
    const ordered = [...moments].sort((left, right) => right.delta - left.delta);
    const describe = (moment) => {
      const ownText = moment.own.length ? moment.own.map((match) => teamResult(match, clubId).text).join(", ") : "não jogou";
      const cause = moment.biggest
        ? ` Jogo que mais pesou: ${matchLabel(moment.biggest.match)} (${deltaSpan(moment.biggest.value, metric)} p.p.).`
        : "";
      return `<li><a href="#/rodadas/${moment.view.round_number}">${roundLabel(moment.view)}</a>: ${deltaSpan(moment.delta, metric)} p.p. (${ownText}).${cause} Reavaliação de força: ${deltaSpan(moment.strength, metric)} p.p.</li>`;
    };
    const gains = ordered.filter((moment) => moment.delta > 0).slice(0, 3);
    const losses = ordered.filter((moment) => moment.delta < 0).reverse().slice(0, 3);
    const none = (kind) => `<p class='note'>Nenhuma ${kind} em ${METRIC_LABELS[metric]} maior que o ruído da simulação.</p>`;
    return `<div class="grid">
      <section><h3>${metric === "relegation" ? "Quando o risco de queda mais subiu" : `Quando a chance de ${METRIC_LABELS[metric]} mais subiu`}</h3>${gains.length ? `<ul class="summary-list">${gains.map(describe).join("")}</ul>` : none("alta")}</section>
      <section><h3>${metric === "relegation" ? "Quando o risco de queda mais caiu" : `Quando a chance de ${METRIC_LABELS[metric]} mais caiu`}</h3>${losses.length ? `<ul class="summary-list">${losses.map(describe).join("")}</ul>` : none("queda")}</section>
    </div>
    <p class="note">Só entram variações acima de 2 erros-padrão da simulação.</p>`;
  }

  function teamTable(clubId, metric) {
    const rows = review.rounds.map((view, index) => {
      const values = view.teams[clubId];
      const previous = review.rounds[index - 1];
      const own = teamMatchesInRound(view, clubId).map((match) => {
        const result = teamResult(match, clubId);
        const impact = match.impacts[clubId] ? match.impacts[clubId][metric] : 0;
        const shown = previous && Math.abs(impact) >= Math.max(0.005, noiseFloor(match, metric, "impacts", previous, clubId));
        return `<span class="result result-${result.letter}">${escapeHtml(result.text)}</span>${shown ? ` ${deltaSpan(impact, metric)}` : ""}`;
      }).join("<br>");
      return `<tr>
        <td class="left"><a href="#/rodadas/${view.round_number}">${roundLabel(view)}</a></td>
        <td>${positionText(values)}</td>
        <td>${values.played > 0 ? values.points : "–"}</td>
        <td>${values.played ?? "–"}</td>
        <td>${num(values.expected_points)}</td>
        <td>${pct(values.title)}</td>
        <td>${pct(values.top4)}</td>
        <td>${pct(values.relegation)}</td>
        <td>${view.summary ? deltaSpan(view.changes[clubId][metric], metric) : "–"}</td>
        <td class="left">${own || '<span class="note">–</span>'}</td>
      </tr>`;
    }).join("");
    return `<div class="table-scroll"><table>
      <thead><tr><th class="left">Rodada</th><th>Pos.</th><th>Pts</th><th>J</th><th>Pts proj.</th><th>Título</th><th>G4</th><th>Rebaix.</th><th>Variação ${METRIC_LABELS[metric]} (p.p.)</th><th class="left">Jogos no intervalo (efeito em ${METRIC_LABELS[metric]})</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  }

  function renderTeam(clubId) {
    const latest = latestView();
    const clubs = Object.keys(latest.teams).sort((left, right) => clubName(left).localeCompare(clubName(right), "pt-BR"));
    const picker = `<div class="club-picker">${clubs.map((club) =>
      `<a class="club-cell" href="#/rodadas/time/${encodeURIComponent(club)}" ${club === clubId ? 'aria-current="true"' : ""}>${crest(club, 18)}<span>${escapeHtml(clubName(club))}</span></a>`).join("")}</div>`;
    if (!latest.teams[clubId]) {
      main.innerHTML = `${header("time", "Escolha um time para ver como as chances dele evoluíram em cada rodada e o que as fez mudar.")}${picker}`;
      return;
    }
    const metric = ui.teamMetric[clubId] || openMetric(clubId);
    const first = review.rounds[0].teams[clubId];
    const now = latest.teams[clubId];
    const views = review.rounds;
    const stat = (label, key) => `<div class="stat"><span class="label">${label}</span><span class="big">${pct(now[key])}</span><span class="sub">${deltaSpan(now[key] - first[key], key)} p.p. desde a pré-temporada</span></div>`;
    main.innerHTML = `
      ${header("time", `Como as chances de ${escapeHtml(clubName(clubId))} evoluíram desde a pré-temporada e quais jogos fizeram a diferença.`)}
      ${picker}
      <h2 class="team-heading">${crest(clubId, 48)}<span>${escapeHtml(clubName(clubId))}</span></h2>
      <div class="stat-row">
        <div class="stat"><span class="label">Na tabela</span><span class="big">${positionText(now)}</span><span class="sub">${now.points ?? "–"} pontos em ${now.played ?? "–"} jogos</span></div>
        <div class="stat"><span class="label">Pontos projetados</span><span class="big">${num(now.expected_points)}</span><span class="sub">${num(first.expected_points)} na pré-temporada</span></div>
        ${stat("Título", "title")}${stat("G4", "top4")}${stat("Rebaixamento", "relegation")}
      </div>
      <h2>Chances ao longo das rodadas</h2>
      ${seriesChart({
        series: [
          { label: "Título", values: views.map((view) => view.teams[clubId].title) },
          { label: "G4", values: views.map((view) => view.teams[clubId].top4) },
          { label: "Rebaixamento", values: views.map((view) => view.teams[clubId].relegation) },
        ],
        domain: [0, 1], format: shareFormat, styles: TEAM_SERIES, ariaLabel: `Chances de título, G4 e rebaixamento de ${clubName(clubId)} por rodada`,
        guides: [{ value: 0, label: "0%" }, { value: 0.5, label: "50%" }, { value: 1, label: "100%" }],
      })}
      <h2>Posição na tabela e projeção</h2>
      ${seriesChart({
        series: [
          { label: "Na tabela", values: views.map((view) => hasTable(view) ? view.teams[clubId].position : null) },
          { label: "Projeção final", values: views.map((view) => view.teams[clubId].expected_position) },
        ],
        domain: [1, 20], invert: true, format: positionFormat, ariaLabel: `Posição real e posição final projetada de ${clubName(clubId)} por rodada`,
        guides: [{ value: 1, label: "1º" }, { value: 4, label: "G4" }, { value: 16, label: "Z4" }, { value: 20, label: "20º" }],
      })}
      <h2>Momentos que mudaram a temporada</h2>
      ${metricPicker(metric, METRIC_TITLES, "team-metric")}
      ${keyMoments(clubId, metric)}
      <h2>Rodada a rodada</h2>
      ${teamTable(clubId, metric)}
      <p class="note"><a href="#/rodadas/comparar/${encodeURIComponent(clubId)}">Comparar ${escapeHtml(clubName(clubId))} com outros times →</a></p>`;
    bindPicker("team-metric", (value) => { ui.teamMetric[clubId] = value; renderTeam(clubId); });
  }

  /* ---------- comparativo ---------- */

  function defaultComparison() {
    const latest = latestView();
    return Object.entries(latest.teams).sort((left, right) => right[1].expected_points - left[1].expected_points).slice(0, MAX_COMPARE).map(([club]) => club);
  }

  function compareValue(view, clubId, metric) {
    const values = view.teams[clubId];
    if (!values) return null;
    if ((metric === "position" || metric === "points") && !hasTable(view)) return null;
    return values[metric];
  }

  function compareSnapshotTable(view, selected) {
    const showTable = hasTable(view);
    const clubs = Object.keys(view.teams).sort((left, right) => showTable
      ? view.teams[left].position - view.teams[right].position
      : view.teams[right].expected_points - view.teams[left].expected_points);
    const rows = clubs.map((club) => {
      const values = view.teams[club];
      const seriesIndex = selected.indexOf(club);
      const mark = seriesIndex >= 0
        ? `<svg width="12" height="12" aria-label="${escapeHtml(SERIES[seriesIndex].name)}">${markerShape(SERIES[seriesIndex].marker, 6, 6, SERIES[seriesIndex].color)}</svg>` : "";
      return `<tr class="${seriesIndex >= 0 ? "selected-team" : ""}">
        <td class="pos">${positionText(values)}</td>
        <td class="left club">${mark} ${teamLink(club)}</td>
        <td>${showTable ? values.points : "–"}</td>
        <td>${values.played ?? "–"}</td>
        <td>${showTable ? (values.goal_difference > 0 ? "+" : "") + values.goal_difference : "–"}</td>
        <td>${num(values.expected_points)}</td>
        <td>${pct(values.title)}</td>
        <td>${pct(values.top4)}</td>
        <td>${pct(values.relegation)}</td>
      </tr>`;
    }).join("");
    return `<div class="table-scroll"><table>
      <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>SG</th><th>Pts proj.</th><th>Título</th><th>G4</th><th>Rebaix.</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  }

  function compareDataTable(selected, metric) {
    const format = COMPARE_METRICS[metric].kind === "share" ? shareFormat : COMPARE_METRICS[metric].kind === "position" ? positionFormat : countFormat;
    const rows = review.rounds.map((view) => `<tr><td class="left">${roundLabel(view)}</td>${selected.map((club) => {
      const value = compareValue(view, club, metric);
      return `<td>${value === null || value === undefined ? "–" : format(value)}</td>`;
    }).join("")}</tr>`).join("");
    return `<details class="data-table"><summary>Ver os valores em tabela</summary><div class="table-scroll"><table>
      <thead><tr><th class="left">Rodada</th>${selected.map((club) => `<th>${escapeHtml(clubShort(club))}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody></table></div></details>`;
  }

  function renderCompare(parameter) {
    const latest = latestView();
    const requested = (parameter || "").split(",").map(decodeURIComponent).filter((club) => latest.teams[club]);
    if (requested.length) ui.compare = requested.slice(0, MAX_COMPARE);
    if (!ui.compare || !ui.compare.length) ui.compare = defaultComparison();
    const selected = ui.compare;
    const metric = ui.compareMetric;
    const views = review.rounds;
    if (ui.compareRound === null || !views.some((view) => view.round_number === ui.compareRound)) ui.compareRound = latest.round_number;
    const roundView = views.find((view) => view.round_number === ui.compareRound);
    const info = COMPARE_METRICS[metric];
    const format = info.kind === "share" ? shareFormat : info.kind === "position" ? positionFormat : countFormat;
    const maxValue = Math.max(1, ...views.flatMap((view) => selected.map((club) => compareValue(view, club, metric) || 0)));
    const chartOptions = info.kind === "share"
      ? { domain: [0, 1], guides: [{ value: 0, label: "0%" }, { value: 0.5, label: "50%" }, { value: 1, label: "100%" }] }
      : info.kind === "position"
        ? { domain: [1, 20], invert: true, guides: [{ value: 1, label: "1º" }, { value: 4, label: "G4" }, { value: 16, label: "Z4" }, { value: 20, label: "20º" }] }
        : { domain: [0, Math.ceil(maxValue / 10) * 10], guides: [] };
    const clubs = Object.keys(latest.teams).sort((left, right) => clubName(left).localeCompare(clubName(right), "pt-BR"));
    const chooser = `<div class="compare-picker" role="group" aria-label="Times no comparativo (até ${MAX_COMPARE})">${clubs.map((club) => {
      const index = selected.indexOf(club);
      const marker = index >= 0 ? `<svg width="12" height="12" aria-hidden="true">${markerShape(SERIES[index].marker, 6, 6, SERIES[index].color)}</svg>` : "";
      return `<button type="button" data-club="${escapeHtml(club)}" aria-pressed="${index >= 0}">${marker}${crest(club, 18)}<span>${escapeHtml(clubName(club))}</span></button>`;
    }).join("")}</div>`;
    main.innerHTML = `
      ${header("comparar", `Escolha até ${MAX_COMPARE} times para comparar rodada a rodada e veja como todos estavam em qualquer rodada.`)}
      <h2>Times</h2>
      ${chooser}
      <p class="note">${selected.length} de ${MAX_COMPARE} selecionados. Para trocar, desmarque um time e marque outro.</p>
      <h2>${escapeHtml(info.label)} rodada a rodada</h2>
      ${metricPicker(metric, COMPARE_METRICS, "compare-metric", "metric-picker-wide")}
      ${seriesChart({ series: selected.map((club) => ({ label: clubShort(club), values: views.map((view) => compareValue(view, club, metric)) })), format, ariaLabel: `${info.label} por rodada: ${selected.map(clubName).join(", ")}`, ...chartOptions })}
      ${compareDataTable(selected, metric)}
      <h2>Como cada time estava na rodada</h2>
      <div class="round-nav">
        ${views[views.indexOf(roundView) - 1] ? `<button type="button" class="button" data-compare-step="-1">← anterior</button>` : "<span></span>"}
        <label>Rodada <select id="compare-round">${views.map((view) => `<option value="${view.round_number}" ${view === roundView ? "selected" : ""}>${roundLabel(view)} · ${formatDate(view.reference_date)}</option>`).join("")}</select></label>
        ${views[views.indexOf(roundView) + 1] ? `<button type="button" class="button" data-compare-step="1">próxima →</button>` : "<span></span>"}
      </div>
      <p class="note">${roundView.round_number === 0 ? "Antes do primeiro jogo: sem tabela, ordenado pelos pontos projetados." : `Tabela real em ${formatDate(roundView.reference_date)} e as chances que o modelo dava naquele dia.`} Os times escolhidos aparecem destacados, com o mesmo marcador do gráfico.</p>
      ${compareSnapshotTable(roundView, selected)}`;
    main.querySelectorAll("[data-club]").forEach((button) => button.addEventListener("click", () => {
      const club = button.dataset.club;
      const index = ui.compare.indexOf(club);
      if (index >= 0) {
        if (ui.compare.length > 1) ui.compare = ui.compare.filter((item) => item !== club);
      } else if (ui.compare.length < MAX_COMPARE) {
        ui.compare = [...ui.compare, club];
      } else {
        return;
      }
      history.replaceState(null, "", `#/rodadas/comparar/${ui.compare.map(encodeURIComponent).join(",")}`);
      renderCompare("");
    }));
    bindPicker("compare-metric", (value) => { ui.compareMetric = value; renderCompare(""); });
    document.getElementById("compare-round").addEventListener("change", (event) => { ui.compareRound = Number(event.target.value); renderCompare(""); });
    main.querySelectorAll("[data-compare-step]").forEach((button) => button.addEventListener("click", () => {
      const target = views[views.indexOf(roundView) + Number(button.dataset.compareStep)];
      if (target) { ui.compareRound = target.round_number; renderCompare(""); }
    }));
  }

  function bindPicker(attribute, onChange) {
    main.querySelectorAll(`[data-${attribute}]`).forEach((button) => button.addEventListener("click", () => {
      onChange(button.getAttribute(`data-${attribute}`));
    }));
  }

  function render(target, segments, context) {
    main = target;
    helpers = context;
    review = context.review;
    if (!review) {
      main.innerHTML = `<span class="kicker">Rodada a rodada</span><h1>Ainda sem revisão por rodada</h1><p class="lede">Rode <code>python -m brasileirao.cli review-rounds</code> e recarregue a página.</p>`;
      return;
    }
    const [first = "", second = ""] = segments;
    const draw = () => {
      if (first === "time") renderTeam(decodeURIComponent(second));
      else if (first === "comparar") renderCompare(second);
      else renderRound(first);
    };
    draw();
    loadCrests(() => { if (location.hash.startsWith("#/rodadas")) draw(); });
  }

  window.Rounds = { render };
})();
