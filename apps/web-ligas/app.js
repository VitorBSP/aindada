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
    return S.raceCard(title, `% das simulações em que termina ${range}.${zone.note ? ` ${escapeHtml(zone.note)}` : ""}`, S.raceRows(items, KIND[zone.kind]));
  }

  // Próximos jogos com data, em ordem cronológica (podem misturar rodadas).
  const upcoming = (data) => data.remaining.filter((match) => match.status === "scheduled" && match.match_date);
  const chronological = (a, b) => (a.kickoff_utc || a.match_date).localeCompare(b.kickoff_utc || b.match_date);
  const HOME_MATCHES = 4;

  function home(data) {
    const down = data.zones.find((zone) => zone.kind === "down");
    const info = `<p>Contamos cada posição do 1º ao ${data.teams.length}º em ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta da temporada. Sem playoff: os ${down.last - down.first + 1} últimos caem direto.</p>
      <p>"Campeão", "já garantiu", "caiu", "não dá mais" e "não cai mais" só aparecem quando a conta de pontos fecha.</p>`;
    const next = upcoming(data).sort(chronological).slice(0, HOME_MATCHES);
    return `
      ${S.screenHead("Quem ainda dá?", info)}
      ${next.length ? `<section class="comp-block" aria-labelledby="comp-next"><div class="block-head"><h2 id="comp-next">Próximos jogos</h2><a class="block-link" href="#/jogos">Ver todos ›</a></div>${S.matchesByDay(next)}</section>` : ""}
      <div class="races">${data.zones.map((zone) => race(data, zone)).join("")}</div>`;
  }

  const COLOR = { title: "title", up: "libertadores", down: "danger" };
  const WORDS = {
    title: { sure: "Campeão em quase todas as simulações", open: "Na briga pelo título", out: "Sem probabilidade relevante de título" },
    up: { sure: "Dentro em quase todas as simulações", open: "Na briga pela vaga", out: "Longe da vaga" },
    down: { sure: "Caem em quase todas as simulações", open: "Ainda correm risco de queda", out: "Longe da queda" },
  };

  const clubModels = (data) => data.teams.map((club) => ({
    id: club.club_id, name: club.name, position: club.position, points: club.points,
    meta: `${club.points} pts`, interval: club.points_interval_90,
  }));

  function races(data) {
    const byId = Object.fromEntries(data.teams.map((club) => [club.club_id, club]));
    return data.zones.map((zone) => {
      const range = zone.first === zone.last ? `em ${zone.first}º lugar` : `entre ${zone.first}º e ${zone.last}º`;
      return {
        id: zone.zone_id, label: zone.label, color: COLOR[zone.kind], words: WORDS[zone.kind],
        value: (model) => byId[model.id].zones[zone.zone_id],
        text: (model) => (byId[model.id].clinched[zone.zone_id] ? zoneLabel(byId[model.id], zone) : null),
        state: (model) => byId[model.id].clinched[zone.zone_id] || null,
        info: `<p>% das ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta em que o clube termina ${range}.</p>${zone.note ? `<p>${escapeHtml(zone.note)}</p>` : ""}<p>"Em quase todas as simulações" = 99% ou mais; só é certeza quando a conta de pontos fecha ("campeão", "já garantiu", "caiu").</p>`,
      };
    });
  }

  function table(data) {
    const info = `<p>Escolha a disputa: quem já está garantido, quem está na briga e quem está fora. "Tabela completa" traz pontos, jogos, saldo e a faixa de posição final de cada clube.</p><p>Toque num clube para ver a faixa de pontos, os próximos jogos e a evolução.</p>`;
    return `
      ${S.screenHead("Tabela", info + races(data).map((race) => `<p><strong>${escapeHtml(race.label)}.</strong> ${race.info.replace(/^<p>|<\/p>$/g, "")}</p>`).join(""))}
      ${S.disputeBoard("tabela", { clubs: clubModels(data), races: races(data), full: () => fullTable(data) })}`;
  }

  function fullTable(data) {
    const zones = data.zones.filter((zone) => zone.kind !== "title");
    const rowZone = (position) => {
      const zone = zones.find((item) => position >= item.first && position <= item.last);
      return zone ? ROW_ZONE[zone.kind] : "";
    };
    // Probabilidades logo depois de Pts: no celular o percentual aparece sem rolar a tabela de lado.
    const rows = data.teams.map((club) => {
      const goalDifference = club.goals_for - club.goals_against;
      const cells = data.zones.map((zone, index) => `<td${index === 0 ? ' class="view-start"' : ""}>${S.probCell(club.zones[zone.zone_id], KIND[zone.kind], club.clinched[zone.zone_id] ? zoneLabel(club, zone) : null)}</td>`).join("");
      return `<tr class="${rowZone(club.position)}">
        <td class="pos">${club.position}</td>
        <td class="left club">${S.teamCell(club.club_id)}</td>
        <td><strong>${club.points}</strong></td>
        ${cells}
        <td class="rest-start">${club.played}</td><td>${club.wins}</td><td>${club.draws}</td><td>${club.losses}</td>
        <td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td>
        <td>${number.format(club.expected_points)}<span class="range">${club.points_interval_90[0]}–${club.points_interval_90[1]}</span></td>
        <td class="left">${S.heat(club.position_probabilities, club.name)}</td>
      </tr>`;
    }).join("");
    return `<div class="table-scroll table-card" tabindex="0" role="region" aria-label="Tabela de ${escapeHtml(data.competition_name)}">
        <table class="standings">
          <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th>
            ${data.zones.map((zone, index) => `<th${index === 0 ? ' class="view-start"' : ""}>${escapeHtml(zone.label)}</th>`).join("")}
            <th class="rest-start">J</th><th>V</th><th>E</th><th>D</th><th>SG</th><th>Pts proj.</th><th class="left">Posição final (1º → ${data.teams.length}º)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function matches(data) {
    const scheduled = upcoming(data);
    const postponed = data.remaining.filter((match) => match.status !== "scheduled");
    const info = "<p>Horários de Brasília. Probabilidade de vitória do mandante, de empate e de vitória do visitante, com a força de cada clube na data da edição. Toque num jogo para ver os detalhes e num clube para ver a ficha dele.</p><p>Os jogos aparecem pelo dia em que caem, mesmo quando misturam rodadas. Adiados ou cancelados sem nova data entram na simulação.</p>";
    return `
      ${S.screenHead("Jogos", info)}
      ${S.dayAgenda("jogos", scheduled, { postponed })}`;
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
    shorts: (data) => Object.fromEntries(data.teams.map((club) => [club.club_id, club.short_name])),
    club: (data, id) => {
      const club = data.teams.find((item) => item.club_id === id);
      if (!club) return null;
      const LABEL = { title: "Título", down: "Queda" };
      const TONE = { title: "", up: "is-g4", down: "is-z4" };
      return {
        name: club.name,
        meta: `${club.position}º lugar · ${club.points} pts · ${club.played} J (${club.wins}V ${club.draws}E ${club.losses}D)`,
        stats: ["title", "up", "down"].map((kind) => data.zones.find((zone) => zone.kind === kind)).filter(Boolean)
          .map((zone) => ({ label: LABEL[zone.kind] || zone.label, text: zoneLabel(club, zone), tone: TONE[zone.kind] })),
        interval: club.points_interval_90,
        expectedPoints: club.expected_points,
        next: upcoming(data).filter((match) => match.home_id === id || match.away_id === id).sort(chronological).slice(0, 3),
      };
    },
    history: {
      clubs: (data) => data.teams.map((club) => ({ id: club.club_id, name: club.name })),
      metrics: (data, history) => history.zones.map((zone) => ({ id: zone.zone_id, label: zone.label, color: COLOR[zone.kind], get: (entry) => entry.zones[zone.zone_id] })),
    },
    edition,
    footer: (data) => `${data.sources.map((source) => `<a href="${S.safeUrl(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`).join("; ")}.`,
    routes: [
      { id: "", label: "Início", render: home },
      { id: "tabela", label: "Tabela", render: table },
      { id: "jogos", label: "Jogos", render: matches },
      { id: "metodologia", label: "Como calculamos", render: method, after: (data, main) => window.AIndaDaMetodo && window.AIndaDaMetodo.render(main.querySelector("#metodo-elo"), data.competition) },
    ],
  });
})();
