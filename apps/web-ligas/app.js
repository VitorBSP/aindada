"use strict";

// Premier League e LaLiga (ADR-0011) no desenho dos sites de competição (D-043). O mesmo app serve as duas ligas;
// cada uma é publicada em /<código>/ com o próprio data/forecast.json.
(function () {
  const S = window.AIndaDaSite;
  const { escapeHtml, pct, team } = S;
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const DONE = {
    title: { in: "campeão", out: "não dá mais" },
    up: { in: "já garantiu", out: "não dá mais" },
    down: { in: "caiu", out: "não cai mais" },
  };
  const KIND = { title: "title", up: "lib", down: "danger" };
  const ROW_ZONE = { up: "zone-lib", down: "zone-z4" };
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

  // Certeza só quando a aritmética decide (clinched); simulação nunca vira certeza.
  const zoneLabel = (club, zone) => {
    const state = club.clinched[zone.zone_id];
    return state ? DONE[zone.kind][state] : pct(club.zones[zone.zone_id]);
  };
  const leagueName = (data) => data.competition_name.replace(/\s+\d{4}\/\d{2}$/, "");
  const totalRounds = (data) => 2 * (data.teams.length - 1);

  function edition(data) {
    const played = Math.max(...data.teams.map((club) => club.played));
    return `<p class="edition"><span class="edition-name">Edição de ${escapeHtml(S.formatDate(data.reference_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }))}</span> · ${escapeHtml(data.competition_name)} · ${played} de ${totalRounds(data)} rodadas</p>
      <p class="edition-facts"><strong>${data.observed_matches}</strong> de ${data.observed_matches + data.remaining_matches} jogos disputados · <strong>${data.n_simulations.toLocaleString("pt-BR")}</strong> simulações do que falta</p>`;
  }

  function race(data, zone) {
    const items = data.teams
      .filter((club) => club.clinched[zone.zone_id] !== "out" && club.zones[zone.zone_id] > 0)
      .sort((a, b) => b.zones[zone.zone_id] - a.zones[zone.zone_id])
      .slice(0, zone.kind === "title" ? 5 : 8)
      .map((club) => ({ id: club.club_id, value: club.zones[zone.zone_id], label: zoneLabel(club, zone) }));
    const range = zone.first === zone.last ? `em ${zone.first}º lugar` : `entre ${zone.first}º e ${zone.last}º`;
    const title = zone.kind === "up" ? `${zone.label}: Liga dos Campeões` : zone.label;
    return `<section class="race"><h3>${escapeHtml(title)}</h3><p class="note">% das simulações em que termina ${range}</p>${S.raceRows(items, KIND[zone.kind])}</section>`;
  }

  function home(data) {
    const title = data.zones.find((zone) => zone.kind === "title");
    const leader = [...data.teams].sort((a, b) => b.zones[title.zone_id] - a.zones[title.zone_id])[0];
    const leaderLine = leader.clinched[title.zone_id] === "in"
      ? `<strong>${escapeHtml(leader.name)}</strong> já é campeão.`
      : `<strong>${escapeHtml(leader.name)}</strong> é o favorito: fica com o título em ${pct(leader.zones[title.zone_id])} das simulações.`;
    const notes = data.zones.filter((zone) => zone.note).map((zone) => `<p class="note">${escapeHtml(zone.note)}</p>`).join("");
    const next = nextRound(data);
    return `
      <h1>Título, vaga e queda: quem ainda dá?</h1>
      <p class="lede">${leaderLine} Contamos cada posição do 1º ao ${data.teams.length}º em ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta da temporada. Sem playoff: os ${data.zones.find((zone) => zone.kind === "down").last - data.zones.find((zone) => zone.kind === "down").first + 1} últimos caem direto.</p>
      <div class="races">${data.zones.map((zone) => race(data, zone)).join("")}</div>
      ${notes}
      ${next ? `<h2>Próxima rodada: rodada ${next.round}</h2><p class="note">Horários de Brasília. Mandante à esquerda.</p>${next.matches.slice(0, 4).map(S.matchRow).join("")}<p class="more"><a href="#/jogos">Todos os ${next.matches.length} jogos da rodada</a> · <a href="#/tabela">Tabela completa</a></p>` : ""}`;
  }

  function table(data) {
    const zones = data.zones.filter((zone) => zone.kind !== "title");
    const rowZone = (position) => {
      const zone = zones.find((item) => position >= item.first && position <= item.last);
      return zone ? ROW_ZONE[zone.kind] : "";
    };
    const rows = data.teams.map((club) => {
      const goalDifference = club.goals_for - club.goals_against;
      const cells = data.zones.map((zone) => `<td>${S.probCell(club.zones[zone.zone_id], KIND[zone.kind], club.clinched[zone.zone_id] ? zoneLabel(club, zone) : null)}</td>`).join("");
      return `<tr class="${rowZone(club.position)}">
        <td class="pos">${club.position}</td>
        <td class="left club">${team(club.club_id, 20)}</td>
        <td><strong>${club.points}</strong></td><td>${club.played}</td><td>${club.wins}</td><td>${club.draws}</td><td>${club.losses}</td>
        <td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td>
        <td class="view-start">${number.format(club.expected_points)}<span class="range">${club.points_interval_90[0]}–${club.points_interval_90[1]}</span></td>
        ${cells}
        <td class="left">${S.heat(club.position_probabilities, club.name)}</td>
      </tr>`;
    }).join("");
    const legend = zones.map((zone) => `<span class="${zone.kind === "up" ? "l-lib" : "l-z4"}">${escapeHtml(zone.label)} (${zone.first}º ao ${zone.last}º)</span>`).join("");
    return `
      <h1 class="race-heading">Tabela</h1>
      <div class="legend">${legend}</div>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Tabela de ${escapeHtml(data.competition_name)}">
        <table class="standings">
          <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>V</th><th>E</th><th>D</th><th>SG</th><th class="view-start">Pts proj.</th>
            ${data.zones.map((zone) => `<th>${escapeHtml(zone.label)}</th>`).join("")}<th class="left">Posição final (1º → ${data.teams.length}º)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <p class="note">Pts proj. = média simulada de pontos no fim; embaixo, a faixa onde terminam 90% das simulações. Percentuais: em quantas simulações o clube termina em cada faixa. A faixa à direita mostra a chance de cada posição final: quanto mais escura, mais provável.</p>`;
  }

  function nextRound(data) {
    const scheduled = data.remaining.filter((match) => match.status === "scheduled" && match.round !== null);
    if (!scheduled.length) return null;
    const round = Math.min(...scheduled.map((match) => match.round));
    const matches = scheduled
      .filter((match) => match.round === round)
      .sort((a, b) => (a.kickoff_utc || a.match_date).localeCompare(b.kickoff_utc || b.match_date));
    return { round, matches };
  }

  function matches(data) {
    const next = nextRound(data);
    if (!next) return `<h1 class="race-heading">Jogos</h1><p>Não há jogos marcados.</p>`;
    let lastDay = "";
    const rows = next.matches.map((match) => {
      const day = match.match_date !== lastDay ? `<h3 class="round-day">${escapeHtml(S.formatDate(match.match_date, { weekday: "long", day: "numeric", month: "long" }))}</h3>` : "";
      lastDay = match.match_date;
      return day + S.matchRow(match);
    }).join("");
    const pending = data.remaining.filter((match) => match.status !== "scheduled").length;
    return `
      <h1 class="race-heading">Rodada ${next.round}</h1>
      <p class="note">Horários de Brasília. Mandante à esquerda; chance de vitória do mandante, empate e vitória do visitante.</p>
      <div class="legend"><span class="l-home">mandante</span><span class="l-draw">empate</span><span class="l-away">visitante</span></div>
      ${rows}
      ${pending ? `<p class="note">${pending} jogo(s) adiado(s) ou cancelado(s) sem nova data: entram na simulação, mas não aparecem aqui.</p>` : ""}`;
  }

  function method(data) {
    const backtest = data.backtest;
    const seasons = backtest ? backtest.test_seasons.map((season) => `${season}/${String(season + 1).slice(2)}`) : [];
    const facts = backtest
      ? `<div class="stat-row">
          <div class="stat"><span class="label">Log loss por jogo</span><span class="big">${decimal.format(backtest.log_loss)}</span><span class="sub">${backtest.n_matches.toLocaleString("pt-BR")} jogos de ${seasons[0]} a ${seasons[seasons.length - 1]}; taxa base ${decimal.format(backtest.log_loss_base_rate)}</span></div>
          <div class="stat"><span class="label">Brier do título</span><span class="big">${decimal.format(backtest.late_title_brier)}</span><span class="sub">com ${totalRounds(data) - backtest.late_round} rodadas por jogar</span></div>
          <div class="stat"><span class="label">Brier do top 4</span><span class="big">${decimal.format(backtest.late_top4_brier)}</span><span class="sub">no mesmo ponto; chute fixo 0,160</span></div>
          <div class="stat"><span class="label">Pontos na faixa de 90%</span><span class="big">${Math.round(backtest.late_points_interval_90_coverage * 100)}%</span><span class="sub">dos pontos finais</span></div>
        </div>`
      : "";
    return `
      <h1 class="race-heading">Como calculamos</h1>
      <p>É o modelo do AInda dá? para o Brasileirão, com parâmetros calibrados nos jogos desta liga: força de cada clube (Elo, ataque e defesa) reconstruída jogo a jogo, um modelo de gols treinado só com temporadas anteriores e ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta. Cada simulação fecha a tabela com os critérios de desempate do regulamento: ${data.tiebreak_order.map((key) => escapeHtml(TIEBREAK_LABELS[key] || key)).join(", ")}.</p>
      <h2>Acerto em temporadas passadas</h2>
      ${facts}
      <p class="note">Menor é melhor no log loss e no Brier.</p>
      <h2>Limitações</h2>
      <ul class="summary-list">${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}${data.zones.filter((zone) => zone.note).map((zone) => `<li>${escapeHtml(zone.note)}</li>`).join("")}
        <li>"Campeão", "já garantiu", "caiu", "não dá mais" e "não cai mais" só aparecem quando a conta de pontos fecha, nunca por simulação.</li>
      </ul>
      <h2>Regulamento e fontes</h2>
      <p>Regulamento: <a href="${S.safeUrl(data.regulation.url)}">${escapeHtml(data.regulation.title)}</a>.${data.regulation.note ? ` ${escapeHtml(data.regulation.note)}` : ""}</p>
      <ul class="summary-list">${S.sources(data.sources)}</ul>
      <p class="note">Modelo ${escapeHtml(data.model_version)} · dados <code class="data-version">${escapeHtml(data.data_version)}</code> · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
      <div id="metodo-elo"></div>`;
  }

  S.start({
    names: (data) => {
      document.title = `AInda dá? ${data.competition_name}`;
      document.getElementById("league-tag").textContent = leagueName(data);
      document.querySelectorAll("#leagues a[data-league]").forEach((link) => {
        if (link.dataset.league === data.competition) link.setAttribute("aria-current", "page");
      });
      return Object.fromEntries(data.teams.map((club) => [club.club_id, club.name]));
    },
    edition,
    footer: (data) => `Fontes: ${data.sources.map((source) => `<a href="${S.safeUrl(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`).join("; ")}.`,
    routes: [
      { id: "", label: "Início", render: home },
      { id: "tabela", label: "Tabela", render: table },
      { id: "jogos", label: "Jogos", render: matches },
      { id: "metodologia", label: "Como calculamos", render: method, after: (data, main) => window.AIndaDaMetodo && window.AIndaDaMetodo.render(main.querySelector("#metodo-elo"), data.competition) },
    ],
  });
})();
