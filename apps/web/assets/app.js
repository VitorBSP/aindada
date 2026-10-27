(function () {
  "use strict";

  const SEASON = 2026;
  const state = { snapshot: null, history: [], metrics: null, rounds: null, insights: [], apiMode: false, scenarioChoice: {} };
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
  const nameOf = (clubId) => (teamById(clubId) || { name: clubId }).name;
  const clubLink = (clubId) => `<a href="#/clubes/${encodeURIComponent(clubId)}">${escapeHtml(nameOf(clubId))}</a>`;

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

  function renderReferenceBar() {
    const snapshot = state.snapshot;
    const bar = document.getElementById("reference-bar");
    bar.innerHTML = `
      <span>Dados até <strong>${formatDate(snapshot.reference_date)}</strong></span>
      <span><strong>${snapshot.observed_matches}</strong> de ${snapshot.observed_matches + snapshot.remaining_matches} jogos disputados</span>
      <span><strong>${snapshot.n_simulations.toLocaleString("pt-BR")}</strong> simulações do resto do campeonato</span>
      <span class="pill">Modelo experimental</span>`;
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

  function changesSinceLast() {
    if (state.history.length < 2) return "";
    const latest = state.history[state.history.length - 1];
    const previous = state.history[state.history.length - 2];
    const changes = [];
    for (const [clubId, values] of Object.entries(latest.teams)) {
      const before = previous.teams[clubId];
      if (!before) continue;
      for (const [key, label] of [["title", "título"], ["relegation", "rebaixamento"], ["top4", "G4"]]) {
        const delta = values[key] - before[key];
        if (Math.abs(delta) >= 0.05) changes.push({ clubId, label, delta, now: values[key] });
      }
    }
    changes.sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta));
    if (!changes.length) return `<p class="note">Nenhuma chance andou mais de 5 pontos percentuais desde ${formatDate(previous.reference_date)}.</p>`;
    return `<p class="note">Comparado à atualização de ${formatDate(previous.reference_date)}. Só entram variações de 5 pontos percentuais ou mais.</p><ul class="changes">` + changes.slice(0, 8).map((change) => {
      const sign = change.delta > 0 ? "+" : "−";
      const css = (change.label === "rebaixamento") === (change.delta > 0) ? "change-down" : "change-up";
      return `<li>${clubLink(change.clubId)}: chance de ${change.label} <span class="${css}">${sign}${Math.round(Math.abs(change.delta) * 100)} p.p.</span> (agora ${pct(change.now)})</li>`;
    }).join("") + "</ul>";
  }

  function overdueWarning() {
    const generated = state.snapshot.generated_at.slice(0, 10);
    const overdue = state.snapshot.matches.filter((match) => match.status !== "finished" && match.match_date < generated);
    if (!overdue.length) return "";
    const list = overdue.map((match) => `${escapeHtml(nameOf(match.home_id))} x ${escapeHtml(nameOf(match.away_id))} (${formatShortDate(match.match_date)})`).join("; ");
    const count = overdue.length === 1 ? "1 jogo com data passada ainda está" : `${overdue.length} jogos com data passada ainda estão`;
    return `<details class="warning"><summary><strong>${count} sem placar na fonte de dados.</strong> Podem ter sido adiados ou ainda não registrados; entram na simulação como não disputados.</summary><p>${list}.</p></details>`;
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

  function renderHome() {
    const teams = state.snapshot.teams;
    const contenders = teams.filter((team) => team.title >= 0.005).sort((left, right) => right.title - left.title);
    const libertadoresFight = teams.filter((team) => team.libertadores_total.max > 0.02 && team.libertadores_total.min < 0.98)
      .sort((left, right) => scenarioMid(right.libertadores_total) - scenarioMid(left.libertadores_total)).slice(0, 8);
    const relegation = teams.filter((team) => team.relegation >= 0.01).sort((left, right) => right.relegation - left.relegation);
    const leader = contenders[0];
    const challenger = contenders[1];
    let headline = "Quem ainda dá?";
    if (leader && challenger) {
      headline = `${escapeHtml(leader.name)} na frente. ${escapeHtml(challenger.name)}: ainda dá${challenger.title < 0.05 ? ", por pouco" : ""}.`;
    } else if (leader) {
      headline = `Só ${escapeHtml(leader.name)} ainda aparece com o título nas simulações.`;
    }
    const simulations = state.snapshot.n_simulations.toLocaleString("pt-BR");
    const titleLede = `Jogamos os ${state.snapshot.remaining_matches} jogos que faltam ${simulations} vezes, a partir da tabela real.
      ${leader ? `O título fica com ${escapeHtml(leader.name)} em <strong>${pct(leader.title)}</strong> das simulações${challenger ? ` e com ${escapeHtml(challenger.name)} em <strong>${pct(challenger.title)}</strong>` : ""}.` : ""}
      Cada porcentagem diz em quantas dessas simulações aquilo aconteceu.`;
    const insights = currentInsights();
    const lead = insights.find((insight) => insight.placement === "home_lead");
    const secondary = insights.filter((insight) => insight.placement === "home_secondary").slice(0, MAX_HOME_SECONDARY);
    const opening = lead
      ? `<span class="kicker">Destaques da rodada · dados até ${formatDate(state.snapshot.reference_date)}</span>
        <h1>${escapeHtml(lead.headline)}</h1>
        <p class="lede">${escapeHtml(lead.body)}</p>
        ${insightLinks(lead)}
        ${secondary.length ? `<div class="highlights">${secondary.map(insightArticle).join("")}</div>` : ""}
        ${overdueWarning()}
        <h2>${headline}</h2>
        <p>${titleLede}</p>`
      : `<span class="kicker">Briga pelo título</span>
        <h1>${headline}</h1>
        <p class="lede">${titleLede}</p>
        ${overdueWarning()}`;
    main.innerHTML = `
      ${opening}
      <div class="grid">
        <section class="card" aria-labelledby="h-title"><h3 id="h-title">Chance de título</h3>${raceRows(contenders, (team) => team.title, "")}</section>
        <section class="card" aria-labelledby="h-z4"><h3 id="h-z4">Risco de queda</h3>${raceRows(relegation, (team) => team.relegation, "danger")}</section>
      </div>
      <h2>Briga pela Libertadores</h2>
      <p class="note">A vaga ainda depende de quem ganha Libertadores, Sul-Americana e Copa do Brasil. Por isso mostramos uma faixa: o menor e o maior valor entre os ${state.snapshot.scenarios.length} cenários possíveis. Não chutamos quem vence esses torneios.</p>
      <div>${libertadoresFight.map((team) => {
        const range = team.libertadores_total;
        return `<div class="race-row">${clubLink(team.club_id)}
          <div class="bar-track" role="img" aria-label="${escapeHtml(team.name)}: ${scenarioValue(range)}">
            <div class="bar-fill lib" style="width:${(range.min * 100).toFixed(1)}%"></div>
            <div class="bar-range" style="left:${(range.min * 100).toFixed(1)}%;width:${((range.max - range.min) * 100).toFixed(1)}%"></div>
          </div><span class="value">${scenarioValue(range)}</span></div>`;
      }).join("")}</div>
      <h2>O que mudou desde a última atualização</h2>
      ${changesSinceLast()}`;
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

  function renderStandings() {
    const snapshot = state.snapshot;
    const teamsByPosition = [...snapshot.teams].sort((left, right) => left.current_position - right.current_position);
    const rows = teamsByPosition.map((team) => {
      const zone = team.current_position <= 5 ? "zone-lib" : team.current_position <= 11 ? "zone-sula" : team.current_position > 16 ? "zone-z4" : "";
      const standing = snapshot.standings.find((entry) => entry.club_id === team.club_id);
      return `<tr class="${zone}">
        <td class="pos">${team.current_position}</td>
        <td class="left club">${clubLink(team.club_id)}</td>
        <td>${standing.points}</td><td>${standing.played}</td><td>${standing.wins}</td><td>${standing.goal_difference > 0 ? "+" : ""}${standing.goal_difference}</td>
        <td><strong>${num(team.expected_points)}</strong><div class="range">${Math.round(team.points_interval_90[0])}–${Math.round(team.points_interval_90[1])}</div></td>
        <td>${num(team.expected_position)}</td>
        <td>${probCell(team.title, "title")}</td>
        <td>${probCell(team.top4, "lib")}</td>
        <td>${scenarioValue(team.libertadores_groups)}</td>
        <td>${scenarioValue(team.libertadores_total)}</td>
        <td>${scenarioValue(team.sudamericana)}</td>
        <td>${probCell(team.relegation, "danger")}</td>
      </tr>`;
    }).join("");
    main.innerHTML = `
      <span class="kicker">Tabela</span>
      <h1>Como está e como deve terminar</h1>
      <p class="lede">A tabela real em ${formatDate(snapshot.reference_date)} ao lado do que as simulações projetam para a última rodada.</p>
      <div class="legend"><span class="l-lib">G5 (Libertadores via Brasileirão)</span><span class="l-sula">faixa típica da Sul-Americana</span><span class="l-z4">Z4</span></div>
      ${scenarioPanel()}
      <div class="table-scroll"><table>
        <caption class="note" style="caption-side:bottom;text-align:left;padding:8px">Pts proj. = média simulada (intervalo de 90%). Libertadores e Sul-Americana dependem de torneios externos: sem cenário escolhido, mostramos a faixa entre todos os cenários.</caption>
        <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>V</th><th>SG</th><th>Pts proj.</th><th>Pos. média</th><th>Título</th><th>G4</th><th>Liberta. grupos</th><th>Liberta. total</th><th>Sul-Americana</th><th>Rebaix.</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
    bindScenarioPanel(renderStandings);
  }

  function lineChart(series, height = 220) {
    if (!state.history.length) return "<p class='note'>Sem histórico.</p>";
    const width = 640, left = 36, right = 12, top = 12, bottom = 28;
    const points = state.history.length;
    const x = (index) => left + (points === 1 ? 0 : (index / (points - 1)) * (width - left - right));
    const y = (value) => top + (1 - value) * (height - top - bottom);
    const grid = [0, 0.25, 0.5, 0.75, 1].map((value) => `<line class="axis" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"/><text x="4" y="${y(value) + 4}">${Math.round(value * 100)}%</text>`).join("");
    const first = state.history[0].reference_date, last = state.history[points - 1].reference_date;
    const lines = series.map((item) => {
      const path = item.values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join("");
      return `<path d="${path}" fill="none" stroke="${item.color}" stroke-width="2.5"/>`;
    }).join("");
    const legend = series.map((item) => `<span style="color:${item.color};font-weight:700">■</span> ${escapeHtml(item.label)}`).join(" &nbsp; ");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolução das probabilidades">${grid}${lines}
      <text x="${left}" y="${height - 6}">${formatDate(first)}</text><text x="${width - right}" y="${height - 6}" text-anchor="end">${formatDate(last)}</text></svg>
      <div class="note">${legend}</div>`;
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

  function matchRow(match) {
    const finished = match.status === "finished";
    const middle = finished
      ? `<div class="score">${match.home_goals} × ${match.away_goals}</div>`
      : `<div class="triple" role="img" aria-label="Mandante ${pct(match.p_home)}, empate ${pct(match.p_draw)}, visitante ${pct(match.p_away)}">
          <span class="t-home" style="width:${match.p_home * 100}%">${Math.round(match.p_home * 100)}</span>
          <span class="t-draw" style="width:${match.p_draw * 100}%">${Math.round(match.p_draw * 100)}</span>
          <span class="t-away" style="width:${match.p_away * 100}%">${Math.round(match.p_away * 100)}</span></div>`;
    const meta = finished ? `Rodada ${match.round ?? "?"}` : `Rodada ${match.round ?? "?"} · gols esperados ${num(match.xg_home)} × ${num(match.xg_away)} · placar mais provável ${match.most_likely_score.replace("-", " × ")} (${pct(match.most_likely_score_probability)})`;
    return `<div class="match"><div class="home">${clubLink(match.home_id)}</div><div class="triple-cell">${middle}</div><div class="away">${clubLink(match.away_id)}</div><div class="match-meta">${meta}</div></div>`;
  }

  function renderClub(clubId) {
    const snapshot = state.snapshot;
    const picker = `<div class="club-picker">${[...snapshot.teams].sort((left, right) => left.name.localeCompare(right.name, "pt-BR"))
      .map((team) => `<a href="#/clubes/${team.club_id}" ${team.club_id === clubId ? 'aria-current="true"' : ""}>${escapeHtml(team.name)}</a>`).join("")}</div>`;
    const team = teamById(clubId);
    if (!team) {
      main.innerHTML = `<h1>Clubes</h1><p class="lede">Escolha um clube para ver as probabilidades detalhadas.</p>${picker}`;
      return;
    }
    const upcoming = snapshot.matches.filter((match) => match.status !== "finished" && (match.home_id === clubId || match.away_id === clubId)).slice(0, 6);
    const scenarioRows = snapshot.scenarios.map((scenario) => ({ scenario, value: team.libertadores_total.by_scenario[scenario.scenario_id] }))
      .sort((left, right) => right.value - left.value);
    const describe = (scenario) => `Liberta: ${escapeHtml(scenario.libertadores_champion)} · Sul-Americana: ${escapeHtml(scenario.sudamericana_champion)} · Copa do Brasil: ${escapeHtml(scenario.cup_champion)} (vice ${escapeHtml(scenario.cup_runner_up)})`;
    const variesByScenario = team.libertadores_total.max - team.libertadores_total.min >= 0.01;
    const history = state.history.map((entry) => entry.teams[clubId] || { title: 0, top4: 0, relegation: 0 });
    main.innerHTML = `
      ${picker}
      <h1>${escapeHtml(team.name)}</h1>
      <p class="lede">${team.current_position}º lugar com ${team.current_points} pontos em ${team.played} jogos. Projeção: ${num(team.expected_points)} pontos (90% entre ${Math.round(team.points_interval_90[0])} e ${Math.round(team.points_interval_90[1])}).</p>
      <div class="stat-row">
        <div class="stat"><span class="label">Título</span><span class="big">${pct(team.title)}</span></div>
        <div class="stat"><span class="label">G4</span><span class="big">${pct(team.top4)}</span></div>
        <div class="stat"><span class="label">Libertadores</span><span class="big">${scenarioValue(team.libertadores_total)}</span><span class="sub">grupos ${scenarioValue(team.libertadores_groups)} · prévia ${scenarioValue(team.libertadores_prelim)}</span></div>
        <div class="stat"><span class="label">Sul-Americana</span><span class="big">${scenarioValue(team.sudamericana)}</span></div>
        <div class="stat"><span class="label">Rebaixamento</span><span class="big">${pct(team.relegation)}</span></div>
      </div>
      <h2>Distribuição da posição final</h2>${positionChart(team.position_probabilities)}
      <h2>Evolução ao longo da temporada</h2>
      ${lineChart([
        { label: "Título", color: "var(--title)", values: history.map((item) => item.title) },
        { label: "G4", color: "var(--libertadores)", values: history.map((item) => item.top4) },
        { label: "Rebaixamento", color: "var(--danger)", values: history.map((item) => item.relegation) },
      ])}
      <h2>Força estimada</h2>
      <div class="stat-row">
        <div class="stat"><span class="label">Elo</span><span class="big">${Math.round(team.ratings.elo)}</span><span class="sub">média da liga = 1500</span></div>
        <div class="stat"><span class="label">Ataque</span><span class="big">${team.ratings.attack >= 0 ? "+" : ""}${num(team.ratings.attack * 100, 0)}%</span><span class="sub">gols marcados vs. média</span></div>
        <div class="stat"><span class="label">Defesa</span><span class="big">${team.ratings.defense >= 0 ? "+" : ""}${num(team.ratings.defense * 100, 0)}%</span><span class="sub">positivo = sofre menos</span></div>
        <div class="stat"><span class="label">Gols projetados</span><span class="big">${Math.round(team.expected_goals_for)}–${Math.round(team.expected_goals_against)}</span><span class="sub">pró–contra no fim</span></div>
      </div>
      <h2>Próximos jogos</h2>${upcoming.length ? upcoming.map(matchRow).join("") : "<p class='note'>Sem jogos restantes.</p>"}
      <h2>Cenários externos</h2>
      ${variesByScenario ? `<p class="note">A chance de Libertadores depende dos torneios ainda em disputa.</p>
        <h3>Mais favorável: ${pct(scenarioRows[0].value)}</h3><p class="note">${describe(scenarioRows[0].scenario)}</p>
        <h3>Menos favorável: ${pct(scenarioRows[scenarioRows.length - 1].value)}</h3><p class="note">${describe(scenarioRows[scenarioRows.length - 1].scenario)}</p>`
        : `<p class="note">Os resultados de Libertadores, Sul-Americana e Copa do Brasil praticamente não alteram a chance de vaga deste clube (${scenarioValue(team.libertadores_total)}).</p>`}`;
  }

  function renderMatches() {
    const snapshot = state.snapshot;
    const remaining = snapshot.matches.filter((match) => match.status !== "finished");
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
      <h2>Últimos resultados</h2>${recent.map(matchRow).join("")}`;
  }

  function renderMethodology() {
    const snapshot = state.snapshot;
    const metrics = state.metrics;
    const labels = { base_rate: "Taxa-base (frequências históricas)", intercept_only: "Poisson sem variáveis", elo_only: "Elo", attack_defense_only: "Ataque/defesa", elo_attack_defense: "Elo + ataque/defesa (escolhido)", full: "Elo + ataque/defesa + forma", elo_attack_defense_sem_dixon_coles: "Escolhido sem Dixon-Coles" };
    const metricRows = metrics ? Object.entries(metrics.test_metrics).map(([name, values]) => `<tr><td class="left">${labels[name] || escapeHtml(name)}</td><td>${num(values.log_loss, 4)}</td><td>${num(values.brier, 4)}</td><td>${num(values.rps, 4)}</td></tr>`).join("") : "";
    const simulation = metrics && metrics.season_simulation ? metrics.season_simulation.overall : null;
    main.innerHTML = `
      <span class="kicker">Como calculamos</span>
      <h1>De onde saem as porcentagens</h1>
      <p class="lede">O modelo, as regras do regulamento, os testes com temporadas passadas, de onde vêm os dados e o que o modelo não sabe.</p>
      <h2>Modelo</h2>
      <p>Cada clube tem um <strong>rating Elo</strong> (força geral, com vantagem de mando e peso pelo saldo de gols) e <strong>ratings de ataque e defesa</strong> atualizados jogo a jogo, ajustados pela força do adversário. Duas regressões de Poisson convertem esses ratings em gols esperados do mandante e do visitante.</p>
      <p>A simulação de Monte Carlo parte da tabela real, preserva os jogos já disputados e sorteia placares para os ${snapshot.remaining_matches} restantes. Dentro de cada simulação, os ratings são atualizados após cada rodada simulada. Jogos da mesma data usam os ratings da véspera. Cada temporada simulada é independente. A classificação aplica os critérios do Art. 15 do regulamento: pontos, vitórias, saldo, gols pró, confronto direto (só entre dois clubes), cartões e sorteio.</p>
      <p class="note">Versão ${escapeHtml(snapshot.model.model_version)} · variáveis: ${escapeHtml(snapshot.model.feature_set)} · treino: ${snapshot.model.training_seasons[0]}–${snapshot.model.training_seasons[snapshot.model.training_seasons.length - 1]} · semente ${snapshot.seed} · ratings dinâmicos na simulação: ${snapshot.dynamic_ratings ? "sim" : "não"}.</p>
      <h2>Vagas continentais</h2>
      <p>Pelo <a href="${escapeHtml(snapshot.regulation.url)}">${escapeHtml(snapshot.regulation.title)}</a> (${escapeHtml(snapshot.regulation.date)}): do 1º ao 4º vão à fase de grupos da Libertadores 2027 e o 5º à fase preliminar. O campeão da Copa do Brasil vai à fase de grupos e o vice à preliminar. Os campeões da Libertadores e da Sul-Americana 2026 também se classificam, e as vagas liberadas descem para o melhor colocado ainda não classificado. A Sul-Americana fica com os seis melhores restantes. Os quatro últimos são rebaixados.</p>
      <p>Situação em ${escapeHtml(snapshot.external_context.as_of)}: ${snapshot.external_context.notes.map(escapeHtml).join(" ")} Como esses torneios não têm vencedor definido, mostramos faixas entre os ${snapshot.scenarios.length} cenários possíveis. Não estimamos a chance de cada um.</p>
      <p class="note">Interpretação do § 5º do Art. 6º adotada: "${escapeHtml(snapshot.external_context.cup_redirect_policy)}" (texto ambíguo; ver documentação).</p>
      <h2>Validação</h2>
      ${metrics ? `<p>Backtesting temporal: o modelo de cada temporada foi treinado só com temporadas anteriores. Os hiperparâmetros foram escolhidos em ${metrics.validation_seasons[0]}–${metrics.validation_seasons[metrics.validation_seasons.length - 1]} e o teste foi feito em ${metrics.test_seasons[0]}–${metrics.test_seasons[metrics.test_seasons.length - 1]}. Valores menores são melhores.</p>
        <div class="table-scroll"><table><thead><tr><th class="left">Modelo</th><th>Log loss</th><th>Brier</th><th>RPS</th></tr></thead><tbody>${metricRows}</tbody></table></div>
        <p class="note">Empates previstos: ${pct(metrics.draw_rate.predicted)} · observados: ${pct(metrics.draw_rate.observed)}.</p>
        ${simulation ? `<p>Na simulação de temporadas passadas (snapshots nas rodadas ${metrics.season_simulation.rounds.join(", ")}), o intervalo de 90% para os pontos finais acertou ${pct(simulation.dynamic.points_interval_90_coverage)} das vezes com ratings dinâmicos e ${pct(simulation.fixed.points_interval_90_coverage)} com ratings fixos. Erro médio da pontuação final projetada: ${num(simulation.dynamic.points_mae)} pontos.</p>` : ""}`
        : "<p class='note'>Relatório de backtesting indisponível.</p>"}
      <h2>Dados</h2>
      <p>Fonte: ${escapeHtml(snapshot.data.source)}, versão <code>${escapeHtml(snapshot.data.version.slice(0, 12))}</code>, coletada em ${escapeHtml(snapshot.data.retrieved_at.slice(0, 10))}. Status de licença: <strong>${escapeHtml(snapshot.data.license_status)}</strong>. Uso restrito a pesquisa local até a licença ser verificada.</p>
      ${snapshot.data.warnings.length ? `<div class="warning">${snapshot.data.warnings.map(escapeHtml).join("<br>")}</div>` : ""}
      <h2>Limitações</h2>
      <ul>
        <li>O modelo não conhece lesões, suspensões, troca de treinador nem rodízio por outras competições.</li>
        <li>Os gols simulados não geram cartões; os critérios de cartões usam apenas jogos já disputados.</li>
        <li>As probabilidades dos jogos usam a força na data de referência; dentro das simulações, a força evolui.</li>
        <li>Percentuais muito pequenos ou muito grandes ainda são incertos: "0%" significa que o desfecho não ocorreu em nenhuma simulação, não que seja impossível.</li>
      </ul>`;
  }

  function route() {
    if (!state.snapshot) return;
    const [, section = "", parameter = "", ...rest] = location.hash.replace(/^#/, "").split("/");
    document.querySelectorAll("nav a").forEach((link) => {
      const active = (link.dataset.route === "home" && !section) || link.dataset.route === section;
      if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
    if (section === "classificacao") renderStandings();
    else if (section === "clubes") renderClub(decodeURIComponent(parameter));
    else if (section === "partidas") renderMatches();
    else if (section === "rodadas") {
      window.Rounds.render(main, [parameter, ...rest], { review: state.rounds, escapeHtml, pct, num, formatDate, formatShortDate, highlights: roundHighlights });
    }
    else if (section === "metodologia") renderMethodology();
    else renderHome();
    window.scrollTo(0, 0);
  }

  async function start() {
    state.snapshot = await fetchJson(`/seasons/${SEASON}/predictions`);
    if (!state.snapshot) {
      main.innerHTML = "<h1>Previsões indisponíveis</h1><p class='lede'>Nenhum snapshot encontrado. Rode <code>python -m brasileirao.cli simulate</code> e recarregue a página.</p>";
      document.getElementById("reference-bar").textContent = "";
      return;
    }
    state.history = (await fetchJson(`/seasons/${SEASON}/probability-history`)) || [];
    state.metrics = await fetchJson("/models/metrics");
    state.rounds = await fetchJson(`/seasons/${SEASON}/rounds`);
    state.insights = (await fetchJson(`/seasons/${SEASON}/insights`)) || [];
    renderReferenceBar();
    route();
  }

  window.addEventListener("hashchange", route);
  start();
})();
