"use strict";

(function () {
  const main = document.getElementById("main");
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const DONE = {
    title: { in: "campeão", out: "não dá mais" },
    up: { in: "já garantiu", out: "não dá mais" },
    down: { in: "caiu", out: "não cai mais" },
  };
  const TIEBREAK_LABELS = {
    points: "pontos",
    wins: "vitórias",
    goal_difference: "saldo de gols",
    goals_for: "gols marcados",
    h2h_points: "pontos no confronto direto",
    h2h_goal_difference: "saldo no confronto direto",
    h2h_away_goals: "gols como visitante no confronto direto",
    draw_lot: "sorteio (no lugar de fair play ou jogo extra)",
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  // Certeza só quando a aritmética decide (clinched); simulação nunca vira certeza (CONTENT_GUIDELINES).
  function pct(value, state, kind) {
    if (state && kind) return DONE[kind][state];
    if (value < 0.001) return "<0,1%";
    if (value > 0.999) return ">99,9%";
    if (value < 0.01 || value > 0.99) return number.format(Math.round(value * 1000) / 10) + "%";
    return Math.round(value * 100) + "%";
  }

  function formatDate(iso) {
    const [year, month, day] = iso.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" });
  }

  function kickoff(match) {
    if (match.kickoff_utc) {
      return new Date(match.kickoff_utc).toLocaleString("pt-BR", {
        timeZone: "America/Sao_Paulo", weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      }) + " (Brasília)";
    }
    const [year, month, day] = match.match_date.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("pt-BR", { weekday: "short", day: "numeric", month: "short" }) + ", horário a definir";
  }

  function badge(team) {
    return `<span class="badge" aria-hidden="true">${escapeHtml(team.short_name)}</span>`;
  }

  function zoneCard(data, zone) {
    const candidates = data.teams
      .filter((team) => team.clinched[zone.zone_id] !== "out" && team.zones[zone.zone_id] > 0)
      .sort((a, b) => b.zones[zone.zone_id] - a.zones[zone.zone_id])
      .slice(0, zone.kind === "title" ? 4 : 6);
    const items = candidates
      .map((team) => {
        const state = team.clinched[zone.zone_id];
        return `<li>${badge(team)}<span class="name">${escapeHtml(team.name)}</span><span class="value${state ? " done" : ""}">${pct(team.zones[zone.zone_id], state, zone.kind)}</span></li>`;
      })
      .join("");
    const range = zone.first === zone.last ? `${zone.first}º lugar` : `entre ${zone.first}º e ${zone.last}º`;
    return `<div class="zone ${zone.kind}"><h3>${escapeHtml(zone.label)}</h3><p class="zone-sub">% das simulações em que termina ${range}</p><ol>${items}</ol></div>`;
  }

  function hero(data) {
    const title = data.zones.find((zone) => zone.kind === "title");
    const leader = [...data.teams].sort((a, b) => b.zones[title.zone_id] - a.zones[title.zone_id])[0];
    const played = Math.max(...data.teams.map((team) => team.played));
    const totalRounds = 2 * (data.teams.length - 1);
    const leaderLine = leader.clinched[title.zone_id] === "in"
      ? `${escapeHtml(leader.name)} já é campeão.`
      : `${escapeHtml(leader.name)} é o favorito: fica com o título em ${pct(leader.zones[title.zone_id])} das simulações.`;
    return `
      <section aria-labelledby="titulo">
        <p class="kicker">${escapeHtml(data.competition_name)} · ${played} de ${totalRounds} rodadas disputadas</p>
        <h1 id="titulo">Título, vaga e queda: quem ainda dá?</h1>
        <p class="lede">${leaderLine} Contamos cada posição do 1º ao ${data.teams.length}º em ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta da temporada.</p>
        <p class="meta">Resultados até ${formatDate(data.reference_date)}</p>
        <div class="zones" id="disputas">${data.zones.map((zone) => zoneCard(data, zone)).join("")}</div>
      </section>`;
  }

  function table(data) {
    const cuts = new Map();
    data.zones.forEach((zone) => {
      if (zone.kind === "down") cuts.set(zone.first - 1, "cut-safe");
      else if (zone.last < data.teams.length) cuts.set(zone.last, zone.kind === "title" ? "" : "cut-direct");
    });
    const rows = data.teams
      .map((team) => {
        const heat = team.position_probabilities
          .map((value, index) => `<i style="opacity:${value === 0 ? 0.06 : (0.12 + 0.88 * Math.min(1, value * 1.6)).toFixed(2)}" title="${index + 1}º: ${pct(value)}"></i>`)
          .join("");
        const zoneCells = data.zones
          .map((zone) => `<td class="zone-cell">${pct(team.zones[zone.zone_id], team.clinched[zone.zone_id], zone.kind)}</td>`)
          .join("");
        const goalDifference = team.goals_for - team.goals_against;
        return `<tr class="${cuts.get(team.position) || ""}">
          <td>${team.position}</td>
          <td class="left"><span class="club-cell">${badge(team)}${escapeHtml(team.name)}</span></td>
          <td class="pts">${team.points}</td><td>${team.played}</td><td>${team.wins}</td><td>${team.draws}</td><td>${team.losses}</td>
          <td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td><td>${number.format(team.expected_points)}</td>
          ${zoneCells}
          <td class="left"><span class="heat" role="img" aria-label="Distribuição da posição final de ${escapeHtml(team.name)}">${heat}</span></td>
        </tr>`;
      })
      .join("");
    return `
      <section id="tabela" aria-labelledby="tabela-titulo">
        <h2 id="tabela-titulo">Tabela e posição final provável</h2>
        <p class="section-note">Percentuais: em quantas das simulações o clube termina em cada faixa. A faixa à direita mostra a chance de cada posição final, do 1º ao ${data.teams.length}º: quanto mais escura, mais provável.</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Tabela de ${escapeHtml(data.competition_name)}">
          <table>
            <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>V</th><th>E</th><th>D</th><th>SG</th><th>Pts esp.</th>
              ${data.zones.map((zone) => `<th>${escapeHtml(zone.label)}</th>`).join("")}<th class="left">Posição final (1º → ${data.teams.length}º)</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
  }

  function nextRound(data, byId) {
    const scheduled = data.remaining.filter((match) => match.status === "scheduled" && match.round !== null);
    if (!scheduled.length) return "";
    const round = Math.min(...scheduled.map((match) => match.round));
    const items = scheduled
      .filter((match) => match.round === round)
      .sort((a, b) => (a.kickoff_utc || a.match_date).localeCompare(b.kickoff_utc || b.match_date))
      .map((match) => {
        const home = byId[match.home_id];
        const away = byId[match.away_id];
        const widths = [match.p_home, match.p_draw, match.p_away].map((value) => (value * 100).toFixed(1));
        return `<li>
          <div class="when">${escapeHtml(kickoff(match))}</div>
          <div class="teams"><span>${escapeHtml(home.name)}</span><span>${escapeHtml(away.name)}</span></div>
          <div class="bar" role="img" aria-label="${escapeHtml(home.name)} ${pct(match.p_home)}, empate ${pct(match.p_draw)}, ${escapeHtml(away.name)} ${pct(match.p_away)}">
            <span class="h" style="width:${widths[0]}%"></span><span class="d" style="width:${widths[1]}%"></span><span class="a" style="width:${widths[2]}%"></span>
          </div>
          <div class="nums"><span>${pct(match.p_home)}</span><span>empate ${pct(match.p_draw)}</span><span>${pct(match.p_away)}</span></div>
        </li>`;
      })
      .join("");
    const pending = data.remaining.filter((match) => match.status !== "scheduled").length;
    return `
      <section id="jogos" aria-labelledby="jogos-titulo">
        <h2 id="jogos-titulo">Próxima rodada</h2>
        <div class="round-head"><h3>Rodada ${round}</h3><span class="meta">mandante à esquerda; chance de vitória, empate e derrota</span></div>
        <ul class="matches">${items}</ul>
        ${pending ? `<p class="section-note">${pending} jogo(s) adiado(s) ou cancelado(s) sem nova data: entram na simulação, mas não aparecem aqui.</p>` : ""}
      </section>`;
  }

  function method(data) {
    const backtest = data.backtest;
    const seasons = backtest ? backtest.test_seasons.map((season) => `${season}/${String(season + 1).slice(2)}`) : [];
    const facts = backtest
      ? `<div class="facts">
          <div class="fact"><strong>${decimal.format(backtest.log_loss)}</strong><span>log loss do modelo em ${backtest.n_matches.toLocaleString("pt-BR")} jogos de ${seasons[0]} a ${seasons[seasons.length - 1]} (taxa base: ${decimal.format(backtest.log_loss_base_rate)}; menor é melhor)</span></div>
          <div class="fact"><strong>${decimal.format(backtest.late_title_brier)}</strong><span>Brier do título com ${2 * (data.teams.length - 1) - backtest.late_round} rodadas por jogar</span></div>
          <div class="fact"><strong>${decimal.format(backtest.late_top4_brier)}</strong><span>Brier do top 4 no mesmo ponto da temporada (chute fixo: 0,160)</span></div>
          <div class="fact"><strong>${Math.round(backtest.late_points_interval_90_coverage * 100)}%</strong><span>dos pontos finais caíram no intervalo de 90% previsto</span></div>
        </div>`
      : "";
    const notes = data.zones.filter((zone) => zone.note).map((zone) => `<li>${escapeHtml(zone.note)}</li>`).join("");
    const sources = data.sources
      .map((source) => `<li><a href="${escapeHtml(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>, versão ${escapeHtml(source.version)}.</li>`)
      .join("");
    return `
      <section id="metodo" class="prose" aria-labelledby="metodo-titulo">
        <h2 id="metodo-titulo">Como calculamos</h2>
        <p>É o modelo do AInda dá? para o Brasileirão, com parâmetros calibrados nos jogos desta liga: força de cada clube (Elo, ataque e defesa) reconstruída jogo a jogo, um modelo de gols treinado só com temporadas anteriores e ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta. Cada simulação fecha a tabela com os critérios de desempate do regulamento: ${data.tiebreak_order.map((key) => TIEBREAK_LABELS[key] || key).join(", ")}.</p>
        ${facts}
        <p>Limitações que você precisa saber:</p>
        <ul>${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}${notes}
          <li>"Campeão", "já garantiu", "caiu", "não dá mais" e "não cai mais" só aparecem quando a conta de pontos fecha, nunca por simulação.</li>
        </ul>
        <p>Regulamento: <a href="${escapeHtml(data.regulation.url)}">${escapeHtml(data.regulation.title)}</a>.${data.regulation.note ? ` ${escapeHtml(data.regulation.note)}` : ""} Fontes:</p>
        <ul>${sources}</ul>
        <p class="meta">Modelo ${escapeHtml(data.model_version)} · dados ${escapeHtml(data.data_version)} · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
        <div id="metodo-elo"></div>
      </section>`;
  }

  function render(data) {
    const byId = Object.fromEntries(data.teams.map((team) => [team.club_id, team]));
    document.title = `AInda dá? ${data.competition_name}`;
    document.getElementById("league-tag").textContent = data.competition_name.replace(/\s+\d{4}\/\d{2}$/, "");
    document.querySelectorAll("#leagues a[data-league]").forEach((link) => {
      if (link.dataset.league === data.competition) link.setAttribute("aria-current", "page");
    });
    main.innerHTML = [hero(data), table(data), nextRound(data, byId), method(data)].join("");
    if (window.AIndaDaMetodo) window.AIndaDaMetodo.render(document.getElementById("metodo-elo"), data.competition);
    document.getElementById("credits").innerHTML = `Fontes: ${data.sources
      .map((source) => `<a href="${escapeHtml(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`)
      .join("; ")}.`;
  }

  fetch("data/forecast.json", { cache: "no-cache" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch(() => {
      main.innerHTML = '<p class="loading">Não foi possível carregar as simulações agora. Tente de novo em alguns minutos.</p>';
    });
})();
