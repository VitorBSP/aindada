/* Aba "Rodada a rodada": avaliação por rodada, por time e comparativo entre times.
   Lê a revisão gerada por `brasileirao.cli review-rounds` e os escudos de assets/crests/manifest.json.
   Polimento Kanban #43 (D-052): 4A (Corrida + Agito), 5B + Jornada (Por time), 6C expandida (Comparar). */
(function () {
  "use strict";

  const METRIC_LABELS = { title: "título", top4: "G4", relegation: "rebaixamento" };
  const METRIC_TITLES = { title: "Título", top4: "G4", relegation: "Rebaixamento" };
  const DISPUTE_CHIPS = { title: "Título", top4: "G4", relegation: "Z4" };
  const RACE_HEADINGS = { title: "Corrida pelo título", top4: "Corrida pelo G4", relegation: "Corrida contra o Z4" };
  const INFO_ICON = `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>`;
  const RANK_WORDS = ["maior mudança da temporada", "segunda maior mudança", "terceira maior mudança", "quarta maior mudança"];
  const COMPARE_METRICS = {
    title: { label: "Título", short: "Título", kind: "share" },
    top4: { label: "G4", short: "G4", kind: "share" },
    relegation: { label: "Rebaixamento", short: "Z4", kind: "share" },
    position: { label: "Posição", short: "Pos.", kind: "position" },
    points: { label: "Pontos", short: "Pts", kind: "count" },
    expected_points: { label: "Pts proj.", short: "Pts proj.", kind: "count" },
  };
  /* Até 4 séries comparadas: cores dos tokens validadas para daltonismo, cada série com traço e marcador próprios. */
  const SERIES = [
    { color: "var(--signal)", dash: "", marker: "circle", name: "linha contínua, círculo" },
    { color: "var(--libertadores)", dash: "7 4", marker: "square", name: "linha tracejada, quadrado" },
    { color: "var(--sudamericana)", dash: "2 4", marker: "triangle", name: "linha pontilhada, triângulo" },
    { color: "var(--series-4)", dash: "10 3 2 3", marker: "diamond", name: "traço e ponto, losango" },
  ];
  const MAX_COMPARE = 4;
  /* Página do time: cada série tem significado fixo; queda usa --danger como no resto do site. */
  const TEAM_SERIES = [
    { color: "var(--title)", dash: "", marker: "circle", name: "linha contínua, círculo" },
    { color: "var(--libertadores)", dash: "7 4", marker: "square", name: "linha tracejada, quadrado" },
    { color: "var(--danger)", dash: "2 4", marker: "triangle", name: "linha pontilhada, triângulo" },
  ];
  const POS_SERIES = [
    { color: "var(--signal)", dash: "", marker: "circle", name: "linha contínua, círculo" },
    { color: "var(--libertadores)", dash: "6 4", marker: "square", name: "linha tracejada, quadrado" },
  ];

  const ui = {
    metric: "title",
    overviewMode: "race",
    teamMetric: {},
    teamChartMode: "probs",
    compare: null,
    compareMetric: "title",
    compareRound: null,
    compareTableMode: "selected",
    focusClub: null,
  };
  const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
  const BADGE_LABEL = /^[A-Z]{2,4}$/;
  let crests = {};
  let crestsRequested = false;
  let helpers = null;
  let review = null;
  let main = null;
  let compareTimer = null;

  const h = () => helpers;
  const escapeHtml = (text) => h().escapeHtml(text);
  const pct = (value) => h().pct(value);
  const num = (value, digits) => h().num(value, digits);
  const formatDate = (iso) => h().formatDate(iso);
  const formatShortDate = (iso) => h().formatShortDate(iso);

  function stopPlayback() {
    if (compareTimer) {
      clearInterval(compareTimer);
      compareTimer = null;
    }
  }
  window.addEventListener("hashchange", stopPlayback);

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

  function deltaSpan(delta, metric, digits = 1) {
    const good = metric === "relegation" ? delta < 0 : delta > 0;
    const css = Math.abs(delta) < 0.0005 ? "" : good ? "change-up" : "change-down";
    return `<span class="${css}">${signedPp(delta, digits)}</span>`;
  }

  function positionText(values) {
    return values && values.played > 0 && values.position ? `${values.position}º` : "–";
  }

  function metricPicker(current, options, attribute, extraClass = "") {
    return `<div class="chip-strip rr-chips ${extraClass}" role="group" aria-label="Disputa">${Object.entries(options).map(([key, label]) =>
      `<button type="button" class="chip chip-sm" data-${attribute}="${key}" aria-pressed="${key === current}">${escapeHtml(typeof label === "string" ? label : label.label)}</button>`).join("")}</div>`;
  }

  function roundChips(selected, attribute) {
    return `<nav class="chip-strip rr-round-chips" aria-label="Rodadas">${review.rounds.map((view) => {
      const current = view.round_number === selected;
      const label = shortRoundLabel(view);
      return attribute
        ? `<button type="button" class="chip chip-sm" data-${attribute}="${view.round_number}" aria-pressed="${current}" aria-label="${roundLabel(view)}">${label}</button>`
        : `<a class="chip chip-sm" href="#/rodadas/${view.round_number}" ${current ? 'aria-current="page"' : ""} aria-label="${roundLabel(view)}">${label}</a>`;
    }).join("")}</nav>`;
  }

  function centerCurrentChip() {
    const chip = main.querySelector('.rr-round-chips [aria-current="page"], .rr-round-chips [aria-pressed="true"]');
    if (chip) chip.parentElement.scrollLeft = chip.offsetLeft - chip.parentElement.clientWidth / 2 + chip.offsetWidth / 2;
  }

  function tabs(active) {
    const items = [["rodada", "#/rodadas", "Visão geral"], ["time", "#/rodadas/time", "Por time"], ["comparar", "#/rodadas/comparar", "Comparar"]];
    return `<nav class="chip-row rr-tabs" aria-label="Visões da aba Rodada a rodada">${items.map(([key, href, label]) =>
      `<a class="chip chip-sm" href="${href}" ${key === active ? 'aria-current="page"' : ""}>${label}</a>`).join("")}</nav>`;
  }

  function header(active, lede) {
    return `<div class="screen-head rr-screen-head">
        <div class="rr-head-left">
          <h1 class="screen-title">Rodada a rodada</h1>
          <button type="button" class="icon-button" data-rounds-info aria-label="Como ler a aba Rodada a rodada">${INFO_ICON}</button>
        </div>
        ${tabs(active)}
      </div>
      <template id="rounds-info">${lede}</template>`;
  }

  function bindInfo() {
    const button = main.querySelector("[data-rounds-info]");
    const source = main.querySelector("#rounds-info");
    if (!button || !source) return;
    button.addEventListener("click", () => {
      const body = `<div class="sheet-info"><p>${source.innerHTML}</p></div>`;
      if (window.AIndaDaShell) window.AIndaDaShell.openSheet("Rodada a rodada", body);
    });
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

  /* ---------- gráfico de séries com rótulos diretos e barra de leitura viva ---------- */

  function markerShape(kind, x, y, color) {
    if (kind === "square") return `<rect x="${x - 3.5}" y="${y - 3.5}" width="7" height="7" fill="${color}" class="marker"/>`;
    if (kind === "triangle") return `<path d="M${x},${y - 4.5}L${x + 4.5},${y + 3.5}L${x - 4.5},${y + 3.5}Z" fill="${color}" class="marker"/>`;
    if (kind === "diamond") return `<path d="M${x},${y - 5}L${x + 5},${y}L${x},${y + 5}L${x - 5},${y}Z" fill="${color}" class="marker"/>`;
    if (kind === "cross") return `<path d="M${x - 1.6},${y - 5}h3.2v3.4h3.4v3.2h-3.4v3.4h-3.2v-3.4h-3.4v-3.2h3.4Z" fill="${color}" class="marker"/>`;
    return `<circle cx="${x}" cy="${y}" r="4" fill="${color}" class="marker"/>`;
  }

  function clubMatches(view, clubId) {
    return (view.matches || []).filter((match) => match.home_id === clubId || match.away_id === clubId).map((match) => {
      const played = match.home_goals !== null && match.home_goals !== undefined && match.away_goals !== null && match.away_goals !== undefined;
      const score = played ? `${match.home_goals} × ${match.away_goals}` : "a jogar";
      return `${clubShort(match.home_id)} ${score} ${clubShort(match.away_id)}`;
    });
  }

  /* Afasta rótulos de fim de linha sobrepostos sem empurrar rótulos isolados para fora do topo. */
  function spreadLabels(positions, gap, minimum, maximum) {
    const order = positions.map((value, index) => ({ value, index })).filter((item) => item.value !== null).sort((a, b) => a.value - b.value);
    if (!order.length) return [...positions];
    const ys = order.map((item) => Math.max(minimum, Math.min(maximum, item.value)));
    for (let i = 1; i < ys.length; i += 1) {
      if (ys[i] < ys[i - 1] + gap) ys[i] = ys[i - 1] + gap;
    }
    if (ys[ys.length - 1] > maximum) {
      ys[ys.length - 1] = maximum;
      for (let i = ys.length - 2; i >= 0; i -= 1) {
        if (ys[i] > ys[i + 1] - gap) ys[i] = ys[i + 1] - gap;
      }
    }
    const placed = [...positions];
    order.forEach((item, idx) => { placed[item.index] = Math.max(minimum, ys[idx]); });
    return placed;
  }

  const chartRegistry = [];

  function seriesChart({
    series,
    domain,
    invert = false,
    format,
    ariaLabel,
    guides = [],
    styles = SERIES,
    initialIndex = null,
    showEndValues = true,
    readout = true,
    onFocus = null,
  }) {
    const views = review.rounds;
    const narrow = main.clientWidth < 560;
    const width = narrow ? 380 : 620;
    const height = narrow ? 210 : 230;
    const left = 36;
    const right = showEndValues ? (narrow ? 76 : 96) : (narrow ? 56 : 74);
    const top = 14;
    const bottom = 24;
    const [low, high] = domain;
    const x = (index) => left + (views.length <= 1 ? 0 : (index / (views.length - 1)) * (width - left - right));
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
    const step = views.length > 24 ? 5 : views.length > 10 ? 2 : 1;
    const ticks = views.map((view, index) => {
      const isLast = index === views.length - 1;
      const show = isLast || (view.round_number % step === 0 && (views.length - 1 - index) >= 3);
      return show ? `<text x="${x(index)}" y="${height - 6}" text-anchor="middle">${shortRoundLabel(view)}</text>` : "";
    }).join("");

    const endPoints = series.map((item) => {
      const index = item.values.map((value) => value !== null && value !== undefined).lastIndexOf(true);
      return index < 0 ? null : { x: x(index), y: y(item.values[index]), value: item.values[index] };
    });
    const labelY = spreadLabels(endPoints.map((point) => point ? point.y : null), 15, top + 6, height - bottom - 2);
    const lines = series.map((item, seriesIndex) => {
      const style = styles[seriesIndex % styles.length];
      const points = item.values.map((value, index) => value === null || value === undefined ? null : [x(index), y(value)]);
      let path = "";
      points.forEach((point, index) => {
        if (!point) return;
        path += `${path && points[index - 1] ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`;
      });
      const end = endPoints[seriesIndex];
      const endDot = end ? markerShape(style.marker, end.x, end.y, style.color) : "";
      const endText = end
        ? `<text class="series-label" x="${end.x + 8}" y="${labelY[seriesIndex] + 4}" style="fill:${style.color}">${escapeHtml(item.label)}${showEndValues ? ` ${escapeHtml(format(end.value))}` : ""}</text>`
        : "";
      return `<path d="${path}" fill="none" stroke="${style.color}" stroke-width="2.2" stroke-dasharray="${style.dash}" stroke-linejoin="round" stroke-linecap="round"/>${endDot}${endText}`;
    }).join("");

    const activeIdx = initialIndex !== null && initialIndex >= 0 && initialIndex < views.length ? initialIndex : views.length - 1;
    const sameClub = series.every((item) => item.club && item.club === series[0].club);

    const buildReadout = (index) => {
      const view = views[index];
      const shared = sameClub && view.round_number !== 0 ? clubMatches(view, series[0].club) : [];
      const clubNow = sameClub && hasTable(view) && view.teams[series[0].club] ? view.teams[series[0].club] : null;
      const head = sameClub && clubNow
        ? `<strong>${shortRoundLabel(view)} · ${positionText(clubNow)} (${clubNow.points ?? "–"} pts)</strong>${shared.length ? `<span class="rr-readout-game">${shared.map(escapeHtml).join(" · ")}</span>` : ""}`
        : `<strong>${roundLabel(view)}</strong><span class="rr-readout-date">${formatShortDate(view.reference_date)}</span>`;
      const items = series.map((item, seriesIndex) => {
        const style = styles[seriesIndex % styles.length];
        const value = item.values[index] === null || item.values[index] === undefined ? "–" : format(item.values[index]);
        return `<span class="rr-readout-item"><i class="rr-dot" style="background:${style.color}"></i>${escapeHtml(item.label)} <strong>${escapeHtml(value)}</strong></span>`;
      }).join("");
      return `<div class="rr-readout-head">${head}</div><div class="rr-readout-items">${items}</div>`;
    };

    const chartId = chartRegistry.push({
      x: views.map((view, index) => x(index)),
      width,
      buildReadout,
      onFocus,
    }) - 1;

    const columnWidth = (width - left - right) / Math.max(views.length - 1, 1);
    const hover = views.map((view, index) => {
      const desc = series.map((item) => `${item.label}: ${item.values[index] === null || item.values[index] === undefined ? "–" : format(item.values[index])}`).join(" · ");
      return `<rect class="hit" data-index="${index}" x="${x(index) - columnWidth / 2}" y="${top}" width="${Math.max(columnWidth, 6)}" height="${height - top - bottom}"><title>${roundLabel(view)} (${formatDate(view.reference_date)}): ${escapeHtml(desc)}</title></rect>`;
    }).join("");

    const ruleX = x(activeIdx);
    return `<div class="series-wrap" data-chart="${chartId}">
      <svg class="chart series-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(ariaLabel)}">${grid}${ticks}${lines}<line class="tip-rule" x1="${ruleX}" x2="${ruleX}" y1="${top}" y2="${height - bottom}"/>${hover}</svg>
      ${readout ? `<div class="rr-readout" aria-live="polite">${buildReadout(activeIdx)}</div>` : ""}
    </div>`;
  }

  function focusChartIndex(wrap, index, notify = true) {
    if (!wrap) return;
    const data = chartRegistry[Number(wrap.dataset.chart)];
    if (!data) return;
    const clamped = Math.max(0, Math.min(data.x.length - 1, index));
    const rule = wrap.querySelector(".tip-rule");
    if (rule) {
      rule.setAttribute("x1", data.x[clamped]);
      rule.setAttribute("x2", data.x[clamped]);
    }
    const readout = wrap.querySelector(".rr-readout");
    if (readout) readout.innerHTML = data.buildReadout(clamped);
    if (notify && data.onFocus) data.onFocus(clamped);
  }

  function bindCharts() {
    main.querySelectorAll(".series-wrap[data-chart]").forEach((wrap) => {
      const data = chartRegistry[Number(wrap.dataset.chart)];
      if (!data) return;
      const svg = wrap.querySelector("svg");
      const pickIndex = (event) => {
        const box = svg.getBoundingClientRect();
        if (!box.width) return;
        const localX = ((event.clientX - box.left) / box.width) * data.width;
        let best = 0;
        for (let i = 1; i < data.x.length; i += 1) {
          if (Math.abs(data.x[i] - localX) < Math.abs(data.x[best] - localX)) best = i;
        }
        focusChartIndex(wrap, best, true);
      };
      svg.addEventListener("pointermove", pickIndex);
      svg.addEventListener("pointerdown", pickIndex);
    });
  }

  const shareFormat = (value) => pct(value);
  const positionFormat = (value) => `${Math.round(value)}º`;
  const countFormat = (value) => num(value, 0);

  /* ---------- 4A: Agito (1 cor suave + pico em --signal) e Visão geral ---------- */

  function movementChart(metric, selected) {
    const views = review.rounds;
    const narrow = main.clientWidth < 560;
    const width = narrow ? 380 : 620, height = 190, left = 10, right = 10, top = 26, bottom = 24;
    const values = views.map((view) => movementOf(view, metric));
    const peak = Math.max(...values, 0.01);
    let peakIndex = -1;
    values.forEach((val, idx) => {
      if (views[idx].summary && (peakIndex < 0 || val > values[peakIndex])) peakIndex = idx;
    });
    const slot = (width - left - right) / Math.max(views.length, 1);
    const barW = Math.max(slot - 2.5, 2);
    const scale = (value) => (value / peak) * (height - top - bottom);

    const bars = views.map((view, index) => {
      if (!view.summary) return "";
      const x = left + index * slot + (slot - barW) / 2;
      const barH = Math.max(scale(values[index]), 2);
      const isPeak = index === peakIndex;
      const isCurrent = view.round_number === selected;
      const cls = `agito-bar${isPeak ? " is-peak" : ""}${isCurrent ? " is-current" : ""}`;
      return `<a href="#/rodadas/${view.round_number}" data-agito-idx="${index}" aria-label="${roundLabel(view)}: ${num(values[index] * 100)} pontos percentuais redistribuídos">
        <rect class="${cls}" x="${x.toFixed(1)}" y="${(height - bottom - barH).toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" rx="2"></rect>
      </a>`;
    }).join("");

    let peakAnnotation = "";
    if (peakIndex >= 0) {
      const px = left + peakIndex * slot + slot / 2;
      const anchor = px > width * 0.7 ? "end" : px < width * 0.3 ? "start" : "middle";
      const labelX = anchor === "end" ? Math.min(width - 8, px + 6) : anchor === "start" ? Math.max(8, px - 6) : px;
      const peakView = views[peakIndex];
      peakAnnotation = `<text class="agito-peak-label" x="${labelX.toFixed(1)}" y="${top - 8}" text-anchor="${anchor}">${shortRoundLabel(peakView)} · maior mudança · ${num(values[peakIndex] * 100)} p.p.</text>`;
    }

    const step = views.length > 24 ? 5 : views.length > 10 ? 2 : 1;
    const ticks = views.map((view, index) => {
      const isLast = index === views.length - 1;
      const show = isLast || (view.round_number % step === 0 && (views.length - 1 - index) >= 3);
      return show ? `<text x="${(left + index * slot + slot / 2).toFixed(1)}" y="${height - 6}" text-anchor="middle">${shortRoundLabel(view)}</text>` : "";
    }).join("");

    const defaultIdx = peakIndex >= 0 ? peakIndex : views.length - 1;
    const readoutText = (idx) => {
      const view = views[idx];
      if (!view || !view.summary) return `<strong>${view ? roundLabel(view) : "Pré-temporada"}</strong><span class="rr-readout-date">Sem jogos ainda</span>`;
      const total = values[idx] * 100;
      const fromRes = (view.summary.results_movement[metric] / 2) * 100;
      const fromStr = (view.summary.strength_movement[metric] / 2) * 100;
      return `<div class="rr-readout-head"><strong>${roundLabel(view)}</strong><span class="rr-readout-date">${formatShortDate(view.reference_date)}</span></div>
        <div class="rr-readout-items"><span class="rr-readout-item"><strong>${num(total)} p.p.</strong> trocaram de clube (${num(fromRes)} resultados · ${num(fromStr)} força)</span></div>`;
    };

    return `<div class="agito-wrap" data-agito-metric="${metric}">
      <svg class="chart rr-bars" viewBox="0 0 ${width} ${height}" role="img" aria-label="Probabilidade de ${METRIC_LABELS[metric]} redistribuída em cada rodada">${bars}${peakAnnotation}${ticks}</svg>
      <div class="rr-readout" id="rr-agito-readout" aria-live="polite">${readoutText(defaultIdx)}</div>
    </div>`;
  }

  function topRaceClubs(metric, count = 4) {
    const latest = latestView();
    const clubs = Object.keys(latest.teams);
    return clubs.map((clubId) => {
      let peak = 0;
      for (const view of review.rounds) {
        const val = view.teams[clubId] ? (view.teams[clubId][metric] || 0) : 0;
        if (val > peak) peak = val;
      }
      return { clubId, peak, now: latest.teams[clubId][metric] || 0, ep: latest.teams[clubId].expected_points || 0 };
    }).sort((a, b) => b.peak - a.peak || b.now - a.now || b.ep - a.ep).slice(0, count).map((item) => item.clubId);
  }

  function topMatch(view, metric, previous) {
    return [...view.matches].map((match) => ({ match, impacts: relevantImpacts(match, metric, "impacts", 0.005, previous) }))
      .filter((entry) => entry.impacts.length)
      .sort((left, right) => right.impacts.reduce((sum, item) => sum + Math.abs(item.value), 0) - left.impacts.reduce((sum, item) => sum + Math.abs(item.value), 0))[0] || null;
  }

  function timelineNode(view, metric, label) {
    const index = review.rounds.indexOf(view);
    const previous = review.rounds[index - 1];
    let line = `<span class="rr-node-line">Sem jogos com efeito em ${METRIC_LABELS[metric]} acima do ruído da simulação.</span>`;
    if (view.summary && previous) {
      const top = topMatch(view, metric, previous);
      if (top) {
        const chips = top.impacts.slice(0, 2).map((item) => `<b>${escapeHtml(clubShort(item.club))} ${deltaSpan(item.value, metric, 0)}</b>`).join(" ");
        line = `<span class="rr-node-line">${matchLabel(top.match)} · ${METRIC_LABELS[metric]} ${chips}</span>`;
      } else if (view.summary.risers[metric][0]) {
        const riser = view.summary.risers[metric][0];
        line = `<span class="rr-node-line">Quem mais subiu: ${escapeHtml(clubName(riser.club_id))} ${deltaSpan(riser.delta, metric, 0)}</span>`;
      }
    } else if (!view.summary) {
      line = `<span class="rr-node-line">Antes do primeiro jogo, só com a força herdada da temporada anterior.</span>`;
    }
    return `<li><a class="rr-node" href="#/rodadas/${view.round_number}"><span class="rr-node-title">${roundLabel(view)}${label ? ` · <em>${label}</em>` : ""}</span>${line}<span class="rr-node-go" aria-hidden="true">›</span></a></li>`;
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
    return `<div class="table-card table-scroll"><table class="season-table">
      <thead><tr><th class="left">Rodada</th><th>Jogos</th><th>p.p. em jogo</th><th class="left">Rodada foi</th><th class="left">Líder da tabela</th><th class="left">Favorito ao título</th><th class="left">Mais subiu (${METRIC_LABELS[metric]})</th><th class="left">Mais caiu</th><th class="left">Jogo decisivo</th><th class="left">Maior surpresa</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="note">"Rodada foi": agitada se ficou entre as 25% que mais mexeram na probabilidade de ${METRIC_LABELS[metric]} na temporada; calma se ficou entre as 25% que menos mexeram.</p>`;
  }

  function seasonTimeline(metric) {
    const views = review.rounds;
    const latest = latestView();
    const ranked = views.filter((view) => view.summary).sort((left, right) => movementOf(right, metric) - movementOf(left, metric));
    const rankOf = new Map(ranked.map((view, rank) => [view, rank]));
    const labelOf = (view) => {
      const rank = rankOf.get(view);
      const parts = [];
      if (view === latest) parts.push(view.partial ? "em andamento" : "a mais recente");
      if (rank !== undefined && rank < RANK_WORDS.length) parts.push(RANK_WORDS[rank]);
      return parts.join(" · ");
    };
    const chosen = new Set([latest, ...ranked.filter((view) => view !== latest).slice(0, 3)]);
    const shown = views.filter((view) => chosen.has(view)).reverse();
    return `<ol class="rr-timeline-grid">${shown.map((view) => timelineNode(view, metric, labelOf(view))).join("")}</ol>
      <details class="rr-all"><summary>Ver todas as ${views.length} rodadas ›</summary>
        <ol class="rr-timeline">${[...views].reverse().map((view) => timelineNode(view, metric, labelOf(view))).join("")}</ol>
        <h3>Avaliação de todas as rodadas</h3>
        ${seasonEvaluation(metric)}
      </details>`;
  }

  function renderOverview() {
    stopPlayback();
    chartRegistry.length = 0;
    const metric = ui.metric;
    const mode = ui.overviewMode;
    const latest = latestView();
    const raceClubs = topRaceClubs(metric, 4);
    const chartTitle = mode === "race" ? `${RACE_HEADINGS[metric]} rodada a rodada` : `Quanto cada rodada mexeu no ${METRIC_LABELS[metric]}`;
    const chartSub = mode === "race"
      ? "4 clubes com maior pico na temporada · passe o mouse ou arraste o dedo"
      : "Barras de 1 cor · destaque na maior virada · toque numa barra para abrir a rodada";

    const chartBody = mode === "race"
      ? seriesChart({
          series: raceClubs.map((clubId) => ({
            label: clubShort(clubId),
            club: clubId,
            values: review.rounds.map((view) => view.teams[clubId] ? view.teams[clubId][metric] : null),
          })),
          domain: [0, 1],
          format: shareFormat,
          ariaLabel: `${RACE_HEADINGS[metric]} rodada a rodada entre ${raceClubs.map(clubName).join(", ")}`,
          guides: [{ value: 0, label: "0%" }, { value: 0.5, label: "50%" }, { value: 1, label: "100%" }],
        })
      : movementChart(metric, latest.round_number);

    main.innerHTML = `
      ${header("rodada", `Como o modelo atual vê o campeonato na véspera de cada rodada, desde a pré-temporada, e o que fez as probabilidades mudarem. ${review.rounds.length} visões com ${review.n_simulations.toLocaleString("pt-BR")} simulações cada; dados até ${formatDate(review.data_until)}.${review.model_version ? ` Tudo recalculado com a versão ${escapeHtml(review.model_version)} do modelo; não são as previsões publicadas na época.` : ""} Os rótulos das rodadas (maior mudança, segunda maior…) vêm da soma de pontos percentuais que trocaram de clube.`)}
      ${metricPicker(metric, DISPUTE_CHIPS, "metric")}
      <section class="rr-block" aria-labelledby="rr-season">
        <div class="rr-card">
          <div class="rr-card-head">
            <div>
              <h2 class="rr-h" id="rr-season">${chartTitle}</h2>
              <p class="rr-sub">${chartSub}</p>
            </div>
            <div class="rr-seg" role="group" aria-label="Tipo de gráfico">
              <button type="button" data-overview-mode="race" aria-pressed="${mode === "race"}">Corrida</button>
              <button type="button" data-overview-mode="agito" aria-pressed="${mode === "agito"}">Agito</button>
            </div>
          </div>
          ${chartBody}
        </div>
      </section>
      <section class="rr-block" aria-labelledby="rr-key-rounds">
        <div class="rr-section-head">
          <div>
            <h2 class="rr-h" id="rr-key-rounds">Rodadas decisivas (${METRIC_TITLES[metric]})</h2>
            <p class="rr-sub">Toque para ver placares, impacto por jogo e tabela daquela rodada</p>
          </div>
          <a class="block-link" href="#/rodadas/time">Ver por time ›</a>
        </div>
        ${seasonTimeline(metric)}
      </section>`;

    bindInfo();
    bindPicker("metric", (value) => { ui.metric = value; renderOverview(); });
    bindPicker("overview-mode", (value) => { ui.overviewMode = value; renderOverview(); });
    bindCharts();

    if (mode === "agito") {
      const readout = main.querySelector("#rr-agito-readout");
      main.querySelectorAll("[data-agito-idx]").forEach((anchor) => {
        const show = () => {
          const idx = Number(anchor.dataset.agitoIdx);
          const view = review.rounds[idx];
          if (!readout || !view || !view.summary) return;
          const total = movementOf(view, metric) * 100;
          const fromRes = (view.summary.results_movement[metric] / 2) * 100;
          const fromStr = (view.summary.strength_movement[metric] / 2) * 100;
          readout.innerHTML = `<div class="rr-readout-head"><strong>${roundLabel(view)}</strong><span class="rr-readout-date">${formatShortDate(view.reference_date)}</span></div>
            <div class="rr-readout-items"><span class="rr-readout-item"><strong>${num(total)} p.p.</strong> trocaram de clube (${num(fromRes)} resultados · ${num(fromStr)} força)</span></div>`;
        };
        anchor.addEventListener("pointerenter", show);
        anchor.addEventListener("focus", show);
      });
    }
  }

  /* ---------- detalhe de uma rodada (#/rodadas/N) ---------- */

  function roundHeadline(view, metric) {
    const summary = view.summary;
    const riser = summary.risers[metric][0];
    const faller = summary.fallers[metric][0];
    const decisive = view.matches.find((match) => match.match_id === summary.decisive_match_id);
    const surprise = view.matches.find((match) => match.match_id === summary.surprise_match_id);
    const items = [];
    if (riser) items.push(`Quem mais subiu em ${METRIC_LABELS[metric]}: ${teamLink(riser.club_id)} ${deltaSpan(riser.delta, metric)} p.p. (agora ${pct(view.teams[riser.club_id][metric])}).`);
    if (faller) items.push(`Quem mais caiu em ${METRIC_LABELS[metric]}: ${teamLink(faller.club_id)} ${deltaSpan(faller.delta, metric)} p.p. (agora ${pct(view.teams[faller.club_id][metric])}).`);
    if (decisive) items.push(`Jogo que mais mexeu nas probabilidades: <strong>${matchLabel(decisive)}</strong>.`);
    if (surprise) items.push(`Maior surpresa: <strong>${matchLabel(surprise)}</strong>. Esse resultado tinha ${pct(surprise.pre_match[surprise.outcome])} de probabilidade antes do jogo.`);
    const moved = movementOf(view, metric);
    items.push(`${num(moved * 100)} p.p. de probabilidade de ${METRIC_LABELS[metric]} trocaram de clube: ${num(summary.results_movement[metric] / 2 * 100)} p.p. pelos resultados (pontos na tabela) e ${num(summary.strength_movement[metric] / 2 * 100)} p.p. pela reavaliação da força dos times.`);
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
    return `<div class="table-card table-scroll"><table>
      <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>Pts proj.</th><th>${METRIC_TITLES[metric]}</th><th>Variação (p.p.)</th><th>Resultados</th><th>Força</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      ${hidden ? `<p class="note">${hidden === clubs.length ? "Nenhum clube" : `Os outros ${hidden} clubes não`} ${hidden === clubs.length ? "aparece" : "aparecem"} com ${METRIC_LABELS[metric]} nas simulações${view.summary ? ", nem antes nem depois desta rodada" : ""}. A tabela completa está em <a href="#/rodadas/comparar">Comparar</a>.</p>` : ""}`;
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
      ? `<span class="chip chip-sm">${crest(entry.club, 16)}${escapeHtml(clubShort(entry.club))} ${deltaSpan(entry.value, metric)}</span>`
      : `<span class="chip chip-sm">${crest(entry.club, 16)}${escapeHtml(clubShort(entry.club))} ${num(entry.value * 100)}</span>`).join("");
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
      <div class="match-actions"><button type="button" class="match-open" data-match-id="${match.match_id}">Ver o que aconteceu</button></div>
    </div>`;
  }

  function renderRound(parameter) {
    stopPlayback();
    const views = review.rounds;
    const requested = Number.parseInt(parameter, 10);
    const view = views.find((item) => item.round_number === requested) || latestView();
    const index = views.indexOf(view);
    const metric = ui.metric;
    const previous = views[index - 1], next = views[index + 1];
    const navigation = `${roundChips(view.round_number, "")}
      <p class="rr-step">${previous ? `<a href="#/rodadas/${previous.round_number}">← ${roundLabel(previous)}</a>` : "<span></span>"}<span>${formatDate(view.reference_date)}</span>${next ? `<a href="#/rodadas/${next.round_number}">${roundLabel(next)} →</a>` : "<span></span>"}</p>`;
    const body = view.summary
      ? `<h2>Resumo: ${roundLabel(view)} ${intensityLabel(view, metric, intensityScale(metric))}</h2>${roundHeadline(view, metric)}
        <h2>Como ficou cada clube</h2>
        <p class="note">Tabela real em ${formatDate(view.reference_date)} e variação desde ${formatDate(previous.reference_date)}. <strong>Resultados</strong>: efeito dos jogos, com a força dos times congelada. <strong>Força</strong>: efeito da reavaliação dos times depois desses jogos. As duas colunas somam a variação.</p>
        ${roundTable(view, metric)}
        <h2>Jogos do intervalo e quem eles afetaram</h2>
        <p class="note">Efeito = probabilidade de ${METRIC_LABELS[metric]} com o resultado real menos a probabilidade antes do jogo, medida em simulações recalculadas com os resultados até a véspera. Inclui jogos adiados de outras rodadas. Só aparecem efeitos acima de 2 erros-padrão do ruído da simulação.</p>
        ${[...view.matches].sort((left, right) => relevantImpacts(right, metric, "impacts", 0, previous).reduce((t, e) => t + Math.abs(e.value), 0) - relevantImpacts(left, metric, "impacts", 0, previous).reduce((t, e) => t + Math.abs(e.value), 0)).map((match) => matchCard(match, metric, previous, view)).join("")}`
      : `<h2>Pré-temporada</h2><p>Antes do primeiro jogo, só com a força herdada da temporada anterior (com regressão à média; promovidos recebem a média dos rebaixados).</p>
        ${roundTable(view, metric)}`;
    main.innerHTML = `
      <a class="back-link" href="#/rodadas">← Rodada a rodada</a>
      ${header("rodada", `Como o modelo atual vê o campeonato na véspera de cada rodada, desde a pré-temporada, e o que fez as probabilidades mudarem. ${views.length} visões com ${review.n_simulations.toLocaleString("pt-BR")} simulações cada; dados até ${formatDate(review.data_until)}.${review.model_version ? ` Tudo recalculado com a versão ${escapeHtml(review.model_version)} do modelo; não são as previsões publicadas na época.` : ""}`)}
      ${navigation}
      ${metricPicker(metric, DISPUTE_CHIPS, "metric")}
      ${helpers.highlights ? helpers.highlights(view) : ""}
      ${body}`;
    bindInfo();
    centerCurrentChip();
    bindPicker("metric", (value) => { ui.metric = value; renderRound(String(view.round_number)); });
  }

  /* ---------- 5B + Jornada: Por time (#/rodadas/time/{clube}) ---------- */

  function teamMatchesInRound(view, clubId) {
    return (view.matches || []).filter((match) => match.home_id === clubId || match.away_id === clubId);
  }

  function teamResult(match, clubId) {
    const home = match.home_id === clubId;
    const scored = home ? match.home_goals : match.away_goals;
    const conceded = home ? match.away_goals : match.home_goals;
    const letter = scored > conceded ? "V" : scored === conceded ? "E" : "D";
    const opponent = home ? match.away_id : match.home_id;
    return { letter, text: `${letter} ${scored}×${conceded} ${clubShort(opponent)}${home ? "" : " (fora)"}`, opponent };
  }

  function openMetric(clubId) {
    const now = latestView().teams[clubId];
    const metrics = Object.keys(METRIC_TITLES);
    const open = metrics.map((metric) => ({ metric, spread: now[metric] * (1 - now[metric]) })).sort((a, b) => b.spread - a.spread)[0];
    if (open.spread > 0.0001) return open.metric;
    return metrics.sort((a, b) => now[b] - now[a])[0];
  }

  function changeNoise(before, after) {
    const total = review.n_simulations;
    return 2 * Math.sqrt((before * (1 - before) + after * (1 - after)) / total);
  }

  function teamExtremes(clubId, metric) {
    const moments = review.rounds.map((view, index) => {
      if (!view.summary) return null;
      const previous = review.rounds[index - 1];
      const delta = view.changes[clubId][metric];
      if (Math.abs(delta) < Math.max(0.002, changeNoise(previous.teams[clubId][metric], view.teams[clubId][metric]))) return null;
      const own = teamMatchesInRound(view, clubId);
      return { view, index, delta, own };
    }).filter(Boolean);

    const goodFn = (m) => (metric === "relegation" ? m.delta < 0 : m.delta > 0);
    const badFn = (m) => (metric === "relegation" ? m.delta > 0 : m.delta < 0);
    const best = moments.filter(goodFn).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0] || null;
    const worst = moments.filter(badFn).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0] || null;

    const describeMatch = (moment) => {
      if (!moment.own.length) return "sem jogo (outros resultados)";
      return moment.own.map((match) => teamResult(match, clubId).text).join(" · ");
    };
    const renderCard = (kicker, moment, emptyText) => {
      if (!moment) return `<div class="rr-extreme is-empty"><span class="rr-extreme-kicker">${kicker}</span><span class="rr-extreme-empty">${emptyText}</span></div>`;
      return `<a class="rr-extreme" href="#/rodadas/${moment.view.round_number}">
        <span class="rr-extreme-kicker">${kicker}</span>
        <span class="rr-extreme-row"><span><strong>${shortRoundLabel(moment.view)}</strong> · ${escapeHtml(describeMatch(moment))}</span><strong class="rr-extreme-val">${deltaSpan(moment.delta, metric)} p.p.</strong></span>
      </a>`;
    };
    const bestLabel = metric === "relegation" ? "Maior alívio" : "Maior salto";
    const worstLabel = metric === "relegation" ? "Maior susto" : "Maior queda";
    return `<div class="rr-extremes">
      ${renderCard(bestLabel, best, `Sem variação positiva acima do ruído em ${METRIC_LABELS[metric]}.`)}
      ${renderCard(worstLabel, worst, `Sem variação negativa acima do ruído em ${METRIC_LABELS[metric]}.`)}
    </div>`;
  }

  function buildTeamJourney(clubId, metric) {
    const views = review.rounds;
    const latestIdx = views.length - 1;
    const first = views[0].teams[clubId];
    const now = views[latestIdx].teams[clubId];
    const metricLabel = DISPUTE_CHIPS[metric];

    const played = views.map((view, index) => ({ view, index, values: view.teams[clubId] }))
      .filter((item) => hasTable(item.view) && item.values && item.values.position);

    const byIndex = new Map();
    const put = (index, item) => {
      if (!byIndex.has(index)) byIndex.set(index, { ...item, index });
    };

    put(0, {
      label: "Pré-temporada",
      note: `Projeção inicial: ${num(first.expected_position, 1)}º · ${metricLabel} ${pct(first[metric])}`,
      kind: "",
    });

    if (played.length >= 2) {
      const bestPos = played.reduce((best, cur) => (cur.values.position < best.values.position ? cur : best), played[0]);
      const worstPos = played.reduce((worst, cur) => (cur.values.position > worst.values.position ? cur : worst), played[0]);
      if (bestPos.index > 0 && bestPos.index < latestIdx && bestPos.values.position < worstPos.values.position) {
        put(bestPos.index, {
          label: `${shortRoundLabel(bestPos.view)} · Melhor momento (${bestPos.values.position}º)`,
          note: `${bestPos.values.points} pts · ${metricLabel} ${pct(bestPos.values[metric])}`,
          kind: "good",
        });
      }
      if (worstPos.index > 0 && worstPos.index < latestIdx && worstPos.values.position > bestPos.values.position) {
        put(worstPos.index, {
          label: `${shortRoundLabel(worstPos.view)} · Pior momento (${worstPos.values.position}º)`,
          note: `${worstPos.values.points} pts · ${metricLabel} ${pct(worstPos.values[metric])}`,
          kind: "bad",
        });
      }
    }

    // Maior virada intermediária ainda não listada, para enriquecer a linha do tempo sem repetir extremos idênticos.
    const midTurns = views.map((view, index) => {
      if (!view.summary || index === 0 || index === latestIdx || byIndex.has(index)) return null;
      const previous = views[index - 1];
      const delta = view.changes[clubId][metric];
      if (Math.abs(delta) < Math.max(0.015, changeNoise(previous.teams[clubId][metric], view.teams[clubId][metric]))) return null;
      return { view, index, delta };
    }).filter(Boolean).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

    if (midTurns.length) {
      const turn = midTurns[0];
      const games = teamMatchesInRound(turn.view, clubId).map((m) => teamResult(m, clubId).text).join(" · ");
      const good = metric === "relegation" ? turn.delta < 0 : turn.delta > 0;
      put(turn.index, {
        label: `${shortRoundLabel(turn.view)} · Virada (${signedPp(turn.delta)} p.p.)`,
        note: `${games ? `${games} · ` : ""}${metricLabel} foi para ${pct(turn.view.teams[clubId][metric])}`,
        kind: good ? "good" : "bad",
      });
    }

    if (latestIdx > 0) {
      put(latestIdx, {
        label: `${shortRoundLabel(views[latestIdx])} · Agora (${positionText(now)})`,
        note: `${now.points ?? "–"} pts · ${metricLabel} ${pct(now[metric])}`,
        kind: "now",
      });
    }

    return [...byIndex.values()].sort((a, b) => a.index - b.index);
  }

  function teamTable(clubId, metric) {
    const rows = [...review.rounds].reverse().map((view) => {
      const index = review.rounds.indexOf(view);
      const values = view.teams[clubId];
      const previous = review.rounds[index - 1];
      const own = teamMatchesInRound(view, clubId).map((match) => {
        const result = teamResult(match, clubId);
        const impact = match.impacts[clubId] ? match.impacts[clubId][metric] : 0;
        const shown = previous && Math.abs(impact) >= Math.max(0.005, noiseFloor(match, metric, "impacts", previous, clubId));
        return `<span class="result result-${result.letter}">${escapeHtml(result.text)}</span>${shown ? ` ${deltaSpan(impact, metric)}` : ""}`;
      }).join("<br>");
      return `<tr>
        <td class="left"><a href="#/rodadas/${view.round_number}">${shortRoundLabel(view)}</a></td>
        <td>${positionText(values)}</td>
        <td>${values.played > 0 ? values.points : "–"}</td>
        <td>${num(values.expected_points)}</td>
        <td>${pct(values.title)}</td>
        <td>${pct(values.top4)}</td>
        <td>${pct(values.relegation)}</td>
        <td>${view.summary ? deltaSpan(view.changes[clubId][metric], metric) : "–"}</td>
        <td class="left">${own || '<span class="note">–</span>'}</td>
      </tr>`;
    }).join("");
    return `<div class="table-card table-scroll"><table>
      <thead><tr><th class="left">Rod.</th><th>Pos.</th><th>Pts</th><th>Pts proj.</th><th>Título</th><th>G4</th><th>Z4</th><th>Var. ${DISPUTE_CHIPS[metric]}</th><th class="left">Jogo</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  }

  function openClubSheet(title, selectedSet, onPick) {
    if (!window.AIndaDaShell) return;
    const latest = latestView();
    const clubs = Object.keys(latest.teams).sort((a, b) => clubName(a).localeCompare(clubName(b), "pt-BR"));
    const body = `<div class="rr-club-sheet">${clubs.map((cid) => {
      const vals = latest.teams[cid];
      const isSelected = selectedSet.has(cid);
      return `<button type="button" class="rr-club-opt${isSelected ? " is-selected" : ""}" data-sheet-club="${escapeHtml(cid)}" aria-pressed="${isSelected}">
        ${crest(cid, 24)}
        <span class="rr-club-opt-name">${escapeHtml(clubName(cid))}</span>
        <span class="rr-club-opt-meta">${hasTable(latest) ? `${positionText(vals)} · ${vals.points ?? "–"}` : num(vals.expected_points, 0)}</span>
      </button>`;
    }).join("")}</div>`;
    window.AIndaDaShell.openSheet(title, body, (dialog) => {
      dialog.querySelectorAll("[data-sheet-club]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const cid = btn.dataset.sheetClub;
          dialog.close();
          onPick(cid);
        });
      });
    });
  }

  function defaultTeamId() {
    const latest = latestView();
    if (helpers.favorite && latest.teams[helpers.favorite]) return helpers.favorite;
    if (ui.focusClub && latest.teams[ui.focusClub]) return ui.focusClub;
    return Object.keys(latest.teams).sort((a, b) => (latest.teams[a].position || 99) - (latest.teams[b].position || 99) || latest.teams[b].expected_points - latest.teams[a].expected_points)[0];
  }

  function renderTeam(requestedClub) {
    stopPlayback();
    chartRegistry.length = 0;
    const latest = latestView();
    const clubId = requestedClub && latest.teams[requestedClub] ? requestedClub : defaultTeamId();
    ui.focusClub = clubId;

    const metric = ui.teamMetric[clubId] || openMetric(clubId);
    const chartMode = ui.teamChartMode;
    const first = review.rounds[0].teams[clubId];
    const now = latest.teams[clubId];
    const views = review.rounds;
    const positions = views.filter((v) => hasTable(v) && v.teams[clubId] && v.teams[clubId].position).map((v) => v.teams[clubId].position);
    const bestWorst = positions.length ? `${Math.min(...positions)}º / ${Math.max(...positions)}º` : "–";
    const openLabel = metric === "relegation" ? "Queda (Z4)" : METRIC_TITLES[metric];
    const openClass = metric === "relegation" ? "is-danger" : "is-lib";
    const journey = buildTeamJourney(clubId, metric);

    const chartHtml = chartMode === "probs"
      ? seriesChart({
          series: [
            { label: "Título", club: clubId, values: views.map((view) => view.teams[clubId].title) },
            { label: "G4", club: clubId, values: views.map((view) => view.teams[clubId].top4) },
            { label: "Z4", club: clubId, values: views.map((view) => view.teams[clubId].relegation) },
          ],
          domain: [0, 1],
          format: shareFormat,
          styles: TEAM_SERIES,
          ariaLabel: `Probabilidades de título, G4 e rebaixamento de ${clubName(clubId)} por rodada`,
          guides: [{ value: 0, label: "0%" }, { value: 0.5, label: "50%" }, { value: 1, label: "100%" }],
        })
      : seriesChart({
          series: [
            { label: "Real", club: clubId, values: views.map((view) => hasTable(view) ? view.teams[clubId].position : null) },
            { label: "Proj.", club: clubId, values: views.map((view) => view.teams[clubId].expected_position) },
          ],
          domain: [1, 20],
          invert: true,
          format: positionFormat,
          styles: POS_SERIES,
          ariaLabel: `Posição real e posição final projetada de ${clubName(clubId)} por rodada`,
          guides: [{ value: 1, label: "1º" }, { value: 4, label: "G4" }, { value: 17, label: "Z4" }, { value: 20, label: "20º" }],
        });

    main.innerHTML = `
      ${header("time", `Como as probabilidades de ${escapeHtml(clubName(clubId))} evoluíram desde a pré-temporada e quais rodadas mudaram sua campanha.`)}
      <div class="rr-team-bar">
        <button type="button" class="rr-team-btn" id="rr-pick-team" aria-label="Trocar time (atual: ${escapeHtml(clubName(clubId))})">
          ${crest(clubId, 30)}<span>${escapeHtml(clubName(clubId))}</span><span class="rr-caret" aria-hidden="true">▾</span>
        </button>
        <a class="btn-secondary btn-sm" href="#/rodadas/comparar/${encodeURIComponent(clubId)}">Comparar ${escapeHtml(clubShort(clubId))} ›</a>
      </div>

      <div class="rr-stat-4">
        <div class="rr-stat-pill"><span>Posição atual</span><strong>${positionText(now)}</strong><small>${now.points ?? "–"} pts em ${now.played ?? "–"} jogos</small></div>
        <div class="rr-stat-pill"><span>Pts projetados</span><strong>${num(now.expected_points)}</strong><small>proj. ${num(now.expected_position, 1)}º</small></div>
        <div class="rr-stat-pill ${openClass}"><span>${openLabel}</span><strong>${pct(now[metric])}</strong><small>${deltaSpan(now[metric] - first[metric], metric)} p.p. desde pré</small></div>
        <div class="rr-stat-pill"><span>Melhor / pior</span><strong>${bestWorst}</strong><small>na tabela</small></div>
      </div>

      <div class="rr-team-grid">
        <div class="rr-stack">
          <section class="rr-card" id="rr-team-chart-card">
            <div class="rr-card-head">
              <div>
                <h2 class="rr-h">${chartMode === "probs" ? `Probabilidades · ${escapeHtml(clubName(clubId))}` : "Posição real vs. projeção"}</h2>
                <p class="rr-sub">Passe o mouse ou arraste o dedo para inspecionar</p>
              </div>
              <div class="rr-seg" role="group" aria-label="Métrica do gráfico">
                <button type="button" data-team-chart="probs" aria-pressed="${chartMode === "probs"}">Probabilidades</button>
                <button type="button" data-team-chart="pos" aria-pressed="${chartMode === "pos"}">Posição</button>
              </div>
            </div>
            ${chartHtml}
          </section>

          <details class="rr-card rr-details-card">
            <summary>Tabela completa rodada a rodada (${views.length} visões)</summary>
            <div class="rr-details-body">${teamTable(clubId, metric)}</div>
          </details>
        </div>

        <div class="rr-stack">
          <section class="rr-card">
            <div class="rr-card-head rr-card-head-tight">
              <div>
                <h2 class="rr-h">Momentos decisivos</h2>
                <p class="rr-sub">Extremos em ${METRIC_LABELS[metric]}</p>
              </div>
              <div class="rr-seg rr-seg-sm" role="group" aria-label="Disputa dos momentos">
                ${Object.entries(DISPUTE_CHIPS).map(([key, label]) =>
                  `<button type="button" data-team-metric="${key}" aria-pressed="${key === metric}">${label}</button>`).join("")}
              </div>
            </div>
            ${teamExtremes(clubId, metric)}
          </section>

          <section class="rr-card">
            <div class="rr-card-head rr-card-head-tight">
              <div>
                <h2 class="rr-h">Jornada na temporada</h2>
                <p class="rr-sub">Linha do tempo cronológica · toque para focar no gráfico</p>
              </div>
            </div>
            <ol class="rr-vtimeline">
              ${journey.map((item) => `
                <li class="${item.kind ? `is-${item.kind}` : ""}">
                  <button type="button" class="rr-vtl-btn" data-jump-idx="${item.index}">
                    <span class="rr-vtl-label">${escapeHtml(item.label)}</span>
                    <span class="rr-vtl-note">${escapeHtml(item.note)}</span>
                  </button>
                </li>`).join("")}
            </ol>
          </section>
        </div>
      </div>`;

    bindInfo();
    bindCharts();
    bindPicker("team-chart", (value) => { ui.teamChartMode = value; renderTeam(clubId); });
    bindPicker("team-metric", (value) => { ui.teamMetric[clubId] = value; renderTeam(clubId); });

    const pickBtn = document.getElementById("rr-pick-team");
    if (pickBtn) {
      pickBtn.addEventListener("click", () => {
        openClubSheet("Escolher time", new Set([clubId]), (chosen) => {
          location.hash = `#/rodadas/time/${encodeURIComponent(chosen)}`;
        });
      });
    }

    main.querySelectorAll("[data-jump-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.jumpIdx);
        const wrap = main.querySelector("#rr-team-chart-card .series-wrap");
        focusChartIndex(wrap, idx, false);
        main.querySelectorAll(".rr-vtl-btn").forEach((b) => b.classList.toggle("is-active", b === btn));
        if (window.innerWidth < 900 && wrap) wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });
  }

  /* ---------- 6C expandida: Comparar (#/rodadas/comparar/{a,b,c,d}) ---------- */

  function defaultComparison(seedClub = null) {
    const latest = latestView();
    const byStanding = Object.entries(latest.teams)
      .sort((left, right) => right[1].expected_points - left[1].expected_points)
      .map(([club]) => club);
    if (seedClub && latest.teams[seedClub]) {
      const seedEp = latest.teams[seedClub].expected_points;
      const nearby = byStanding.filter((c) => c !== seedClub)
        .sort((a, b) => Math.abs(latest.teams[a].expected_points - seedEp) - Math.abs(latest.teams[b].expected_points - seedEp));
      return [seedClub, ...nearby.slice(0, MAX_COMPARE - 1)];
    }
    const base = helpers.favorite && latest.teams[helpers.favorite] ? [helpers.favorite] : [];
    for (const c of byStanding) {
      if (base.length >= MAX_COMPARE) break;
      if (!base.includes(c)) base.push(c);
    }
    return base;
  }

  function compareValue(view, clubId, metric) {
    const values = view.teams[clubId];
    if (!values) return null;
    if ((metric === "position" || metric === "points") && !hasTable(view)) return null;
    return values[metric];
  }

  function compareSnapshotRowsHtml(roundIndex, selected, metric, tableMode) {
    const views = review.rounds;
    const view = views[roundIndex];
    const prevView = roundIndex > 0 ? views[roundIndex - 1] : null;
    const showTable = hasTable(view);
    const prevHasTable = prevView && hasTable(prevView);
    const info = COMPARE_METRICS[metric];
    const format = info.kind === "share" ? shareFormat : info.kind === "position" ? positionFormat : countFormat;

    const allClubs = Object.keys(view.teams).sort((left, right) => showTable
      ? view.teams[left].position - view.teams[right].position
      : view.teams[right].expected_points - view.teams[left].expected_points);
    const shown = tableMode === "selected" ? allClubs.filter((c) => selected.includes(c)) : allClubs;

    return shown.map((club) => {
      const values = view.teams[club];
      const idx = selected.indexOf(club);
      const val = compareValue(view, club, metric);
      let mv = "";
      if (showTable && prevHasTable && prevView.teams[club] && prevView.teams[club].position && values.position) {
        const diff = prevView.teams[club].position - values.position;
        if (diff > 0) mv = `<span class="rr-mv is-up">▲${diff}</span>`;
        else if (diff < 0) mv = `<span class="rr-mv is-dn">▼${Math.abs(diff)}</span>`;
      }
      const accentStyle = idx >= 0 ? ` style="box-shadow:inset 4px 0 0 ${SERIES[idx].color}"` : "";
      const valStyle = idx >= 0 ? ` style="color:${SERIES[idx].color}"` : "";
      return `<tr class="${idx >= 0 ? "is-compared" : ""}">
        <td class="num rr-snap-pos"${accentStyle}>${positionText(values)}${mv}</td>
        <td class="left club">${teamLink(club)}</td>
        <td class="num">${showTable ? values.points ?? "–" : "–"}</td>
        <td class="num"><strong${valStyle}>${val === null || val === undefined ? "–" : format(val)}</strong></td>
      </tr>`;
    }).join("");
  }

  function compareDataTable(selected, metric) {
    const info = COMPARE_METRICS[metric];
    const format = info.kind === "share" ? shareFormat : info.kind === "position" ? positionFormat : countFormat;
    const rows = [...review.rounds].reverse().map((view) => `<tr><td class="left"><a href="#/rodadas/${view.round_number}">${shortRoundLabel(view)}</a></td>${selected.map((club) => {
      const value = compareValue(view, club, metric);
      return `<td class="num">${value === null || value === undefined ? "–" : format(value)}</td>`;
    }).join("")}</tr>`).join("");
    return `<details class="rr-card rr-details-card"><summary>Ver histórico completo em tabela (${review.rounds.length} rodadas)</summary>
      <div class="rr-details-body"><div class="table-card table-scroll"><table>
      <thead><tr><th class="left">Rodada</th>${selected.map((club) => `<th class="num">${escapeHtml(clubShort(club))}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody></table></div></div></details>`;
  }

  function renderCompare(parameter) {
    stopPlayback();
    chartRegistry.length = 0;
    const latest = latestView();
    const views = review.rounds;
    const requested = (parameter || "").split(",").map(decodeURIComponent).filter((club) => latest.teams[club]);
    if (requested.length === 1) {
      ui.compare = defaultComparison(requested[0]);
    } else if (requested.length >= 2) {
      ui.compare = [...new Set(requested)].slice(0, MAX_COMPARE);
    }
    if (!ui.compare || !ui.compare.length) ui.compare = defaultComparison();
    const selected = ui.compare;
    const metric = ui.compareMetric;
    const tableMode = ui.compareTableMode;

    if (ui.compareRound === null || !views.some((view) => view.round_number === ui.compareRound)) {
      ui.compareRound = latest.round_number;
    }
    let roundIdx = Math.max(0, views.findIndex((view) => view.round_number === ui.compareRound));
    const roundView = views[roundIdx];

    const info = COMPARE_METRICS[metric];
    const format = info.kind === "share" ? shareFormat : info.kind === "position" ? positionFormat : countFormat;
    const maxValue = Math.max(1, ...views.flatMap((view) => selected.map((club) => compareValue(view, club, metric) || 0)));
    const chartOptions = info.kind === "share"
      ? { domain: [0, 1], guides: [{ value: 0, label: "0%" }, { value: 0.5, label: "50%" }, { value: 1, label: "100%" }] }
      : info.kind === "position"
        ? { domain: [1, 20], invert: true, guides: [{ value: 1, label: "1º" }, { value: 4, label: "G4" }, { value: 17, label: "Z4" }, { value: 20, label: "20º" }] }
        : { domain: [0, Math.ceil(maxValue / 10) * 10], guides: [] };

    const clubChipsHtml = `<div class="rr-cmp-chips" role="group" aria-label="Times selecionados (até ${MAX_COMPARE})">
      ${selected.map((club, i) => `
        <span class="rr-cmp-chip">
          <span class="rr-ring" style="border-color:${SERIES[i].color}">${crest(club, 20)}</span>
          <span class="rr-cmp-chip-name">${escapeHtml(clubShort(club))}</span>
          ${selected.length > 1 ? `<button type="button" class="rr-cmp-x" data-remove-club="${escapeHtml(club)}" aria-label="Remover ${escapeHtml(clubName(club))}">×</button>` : ""}
        </span>`).join("")}
      ${selected.length < MAX_COMPARE ? `<button type="button" class="chip chip-sm" id="rr-add-club">+ time (${selected.length}/${MAX_COMPARE})</button>` : ""}
    </div>`;

    const syncRound = (nextIdx, updateChart = true) => {
      roundIdx = Math.max(0, Math.min(views.length - 1, nextIdx));
      const rv = views[roundIdx];
      ui.compareRound = rv.round_number;
      const titleEl = document.getElementById("rr-snap-title");
      const dateEl = document.getElementById("rr-snap-date");
      const tbodyEl = document.getElementById("rr-snap-tbody");
      const sliderEl = document.getElementById("rr-cmp-slider");
      const labelEl = document.getElementById("rr-cmp-rlabel");
      if (titleEl) titleEl.textContent = rv.round_number === 0 ? "Foto da pré-temporada" : `Foto da Rodada ${rv.round_number}`;
      if (dateEl) dateEl.textContent = formatDate(rv.reference_date);
      if (tbodyEl) tbodyEl.innerHTML = compareSnapshotRowsHtml(roundIdx, selected, metric, ui.compareTableMode);
      if (sliderEl && Number(sliderEl.value) !== roundIdx) sliderEl.value = String(roundIdx);
      if (labelEl) labelEl.textContent = shortRoundLabel(rv);
      if (updateChart) {
        const wrap = main.querySelector("#rr-cmp-chart-card .series-wrap");
        focusChartIndex(wrap, roundIdx, false);
      }
    };

    main.innerHTML = `
      ${header("comparar", `Compare até ${MAX_COMPARE} clubes lado a lado ao longo de toda a temporada. Passe o mouse no gráfico, arraste a barra ou aperte Evoluir para ver a tabela rodada a rodada.`)}
      ${clubChipsHtml}
      ${metricPicker(metric, COMPARE_METRICS, "compare-metric", "metric-picker-wide")}

      <div class="rr-cmp-grid">
        <section class="rr-card" id="rr-cmp-chart-card">
          <div class="rr-card-head">
            <div>
              <h2 class="rr-h">Evolução comparada (${escapeHtml(info.short)})</h2>
              <p class="rr-sub">Passe o mouse ou dê play para acompanhar a foto da rodada</p>
            </div>
          </div>
          ${seriesChart({
            series: selected.map((club) => ({ label: clubShort(club), club, values: views.map((view) => compareValue(view, club, metric)) })),
            format,
            ariaLabel: `${info.label} por rodada: ${selected.map(clubName).join(", ")}`,
            initialIndex: roundIdx,
            readout: false,
            onFocus: (idx) => { stopPlayback(); updatePlayButton(); syncRound(idx, false); },
            ...chartOptions,
          })}
          <div class="rr-playback">
            <button type="button" class="rr-play-btn" id="rr-cmp-play" ${views.length < 2 ? "disabled" : ""}>▶ Evoluir</button>
            <input type="range" class="rr-slider" id="rr-cmp-slider" min="0" max="${Math.max(0, views.length - 1)}" value="${roundIdx}" aria-label="Rodada na foto comparada" ${views.length < 2 ? "disabled" : ""}>
            <strong class="rr-rlabel" id="rr-cmp-rlabel">${shortRoundLabel(roundView)}</strong>
          </div>
        </section>

        <section class="rr-card rr-snap-card">
          <div class="rr-snap-head">
            <div>
              <strong class="rr-snap-title" id="rr-snap-title">${roundView.round_number === 0 ? "Foto da pré-temporada" : `Foto da Rodada ${roundView.round_number}`}</strong>
              <span class="rr-snap-date" id="rr-snap-date">${formatDate(roundView.reference_date)}</span>
            </div>
            <div class="rr-seg rr-seg-sm" role="group" aria-label="Escopo da tabela">
              <button type="button" data-cmp-tmode="selected" aria-pressed="${tableMode === "selected"}">Comparados (${selected.length})</button>
              <button type="button" data-cmp-tmode="all" aria-pressed="${tableMode === "all"}">Tabela</button>
            </div>
          </div>
          <div class="rr-snap-scroll">
            <table class="rr-snap-table">
              <thead><tr><th class="num">#</th><th class="left">Clube</th><th class="num">Pts</th><th class="num">${escapeHtml(info.short)}</th></tr></thead>
              <tbody id="rr-snap-tbody">${compareSnapshotRowsHtml(roundIdx, selected, metric, tableMode)}</tbody>
            </table>
          </div>
        </section>
      </div>
      ${compareDataTable(selected, metric)}`;

    const updatePlayButton = () => {
      const btn = document.getElementById("rr-cmp-play");
      if (btn) btn.textContent = compareTimer ? "❚❚ Pausar" : "▶ Evoluir";
    };

    const updateHash = () => {
      history.replaceState(null, "", `#/rodadas/comparar/${ui.compare.map(encodeURIComponent).join(",")}`);
    };

    main.querySelectorAll("[data-remove-club]").forEach((btn) => btn.addEventListener("click", () => {
      if (ui.compare.length <= 1) return;
      ui.compare = ui.compare.filter((c) => c !== btn.dataset.removeClub);
      updateHash();
      renderCompare("");
    }));

    const addBtn = document.getElementById("rr-add-club");
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        openClubSheet("Adicionar time ao comparativo", new Set(ui.compare), (chosen) => {
          if (ui.compare.includes(chosen)) {
            if (ui.compare.length > 1) ui.compare = ui.compare.filter((c) => c !== chosen);
          } else if (ui.compare.length < MAX_COMPARE) {
            ui.compare = [...ui.compare, chosen];
          }
          updateHash();
          renderCompare("");
        });
      });
    }

    const slider = document.getElementById("rr-cmp-slider");
    if (slider) {
      slider.addEventListener("input", () => {
        stopPlayback();
        updatePlayButton();
        syncRound(Number(slider.value), true);
      });
    }

    const playBtn = document.getElementById("rr-cmp-play");
    if (playBtn) {
      playBtn.addEventListener("click", () => {
        if (compareTimer) {
          stopPlayback();
          updatePlayButton();
          return;
        }
        if (roundIdx >= views.length - 1) syncRound(0, true);
        compareTimer = setInterval(() => {
          if (!document.getElementById("rr-cmp-play") || roundIdx >= views.length - 1) {
            stopPlayback();
            updatePlayButton();
            return;
          }
          syncRound(roundIdx + 1, true);
        }, 420);
        updatePlayButton();
      });
    }

    main.querySelectorAll("[data-cmp-tmode]").forEach((btn) => btn.addEventListener("click", () => {
      ui.compareTableMode = btn.dataset.cmpTmode;
      main.querySelectorAll("[data-cmp-tmode]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      syncRound(roundIdx, false);
    }));

    bindPicker("compare-metric", (value) => { ui.compareMetric = value; renderCompare(""); });
    bindInfo();
    bindCharts();
  }

  function bindPicker(attribute, onChange) {
    main.querySelectorAll(`[data-${attribute}]`).forEach((button) => button.addEventListener("click", () => {
      onChange(button.getAttribute(`data-${attribute}`));
    }));
  }

  function render(target, segments, context) {
    stopPlayback();
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
      else if (first === "") renderOverview();
      else renderRound(first);
    };
    draw();
    loadCrests(() => { if (location.hash.startsWith("#/rodadas")) draw(); });
  }

  window.Rounds = { render };
})();
