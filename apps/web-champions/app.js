"use strict";

// Champions League (ADR-0012) no desenho dos sites de competição (D-043): Início, Chave provável, Fase de liga,
// Jogos e Como calculamos.
(function () {
  const S = window.AIndaDaSite;
  const { escapeHtml, pct, team } = S;
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const STAGES = [
    ["round_of_16", "Oitavas"],
    ["quarter_finals", "Quartas"],
    ["semi_finals", "Semi"],
    ["final", "Final"],
    ["winner", "Título"],
  ];
  const DONE = {
    top8: { in: "garantido", out: "não dá mais" },
    playoff: { in: "garantido", out: "eliminado" },
    out: { in: "eliminado", out: "não cai mais" },
  };
  // Art. 19: seção A = 1º/2º contra os vencedores do playoff 15º/16º × 17º/18º; B = 3º/4º × (13º/14º × 19º/20º);
  // C = 5º/6º × (11º/12º × 21º/22º); D = 7º/8º × (9º/10º × 23º/24º). Quartas: A × D e B × C em cada lado da chave.
  const SECTIONS = [
    { id: "A", seeds: [1, 2], playoff: [15, 16, 17, 18] },
    { id: "B", seeds: [3, 4], playoff: [13, 14, 19, 20] },
    { id: "C", seeds: [5, 6], playoff: [11, 12, 21, 22] },
    { id: "D", seeds: [7, 8], playoff: [9, 10, 23, 24] },
  ];

  // `playoff = out` vale tanto para quem já caiu quanto para quem já garantiu o top 8: o rótulo diz qual dos dois.
  function zoneLabel(club, zone) {
    if (zone === "playoff" && club.clinched.top8 === "in") return "já nas oitavas";
    if (zone === "playoff" && club.clinched.playoff === "out") return club.clinched.out === "in" ? "eliminado" : pct(club.zones.playoff);
    return club.clinched[zone] ? DONE[zone][club.clinched[zone]] : pct(club.zones[zone]);
  }
  const matchday = (data) => Math.max(...data.clubs.map((club) => club.played));
  const inPositions = (club, positions) => positions.reduce((sum, position) => sum + club.position_probabilities[position - 1], 0);

  function edition(data) {
    return `<p class="edition"><span class="edition-name">Edição de ${escapeHtml(S.formatDate(data.reference_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }))}</span> · ${escapeHtml(data.competition_name)} · fase de liga, ${matchday(data)} de 8 rodadas</p>
      <p class="edition-facts"><strong>${data.observed_matches}</strong> de ${data.observed_matches + data.remaining_matches} jogos disputados · <strong>${data.n_simulations.toLocaleString("pt-BR")}</strong> simulações até a final</p>`;
  }

  function home(data) {
    const open = (zone) => data.clubs.filter((club) => club.clinched[zone] !== "out");
    const byWinner = [...data.clubs].sort((a, b) => b.stages.winner - a.stages.winner).slice(0, 8);
    const byTop8 = open("top8").sort((a, b) => b.zones.top8 - a.zones.top8).slice(0, 8);
    const byOut = open("out").sort((a, b) => b.zones.out - a.zones.out).slice(0, 8);
    const leader = byWinner[0];
    return `
      <h1>Quem ainda dá para levantar a taça?</h1>
      <p class="lede"><strong>${escapeHtml(leader.name)}</strong> é quem mais ganha a Champions: título em ${pct(leader.stages.winner)} das simulações. Do 1º ao 8º vão direto às oitavas, do 9º ao 24º jogam o playoff e do 25º em diante saem.</p>
      <div class="races">
        <section class="race"><h3>Título</h3><p class="note">% das simulações em que é campeão</p>${S.raceRows(byWinner.map((club) => ({ id: club.club_id, value: club.stages.winner })), "")}</section>
        <section class="race"><h3>Direto às oitavas</h3><p class="note">% das simulações em que termina entre 1º e 8º</p>${S.raceRows(byTop8.map((club) => ({ id: club.club_id, value: club.zones.top8, label: zoneLabel(club, "top8") })), "lib")}</section>
        <section class="race"><h3>Eliminado na fase de liga</h3><p class="note">% das simulações em que termina entre 25º e 36º</p>${S.raceRows(byOut.map((club) => ({ id: club.club_id, value: club.zones.out, label: zoneLabel(club, "out") })), "danger")}</section>
      </div>
      <p class="more"><a href="#/chave">Chave provável do mata-mata</a> · <a href="#/fase-de-liga">Fase de liga</a> · <a href="#/jogos">Próxima rodada</a></p>`;
  }

  function candidates(data, positions, limit) {
    return data.clubs
      .map((club) => ({ club, value: inPositions(club, positions) }))
      .filter((item) => item.value >= 0.01)
      .sort((a, b) => b.value - a.value)
      .slice(0, limit);
  }

  function sectionCard(data, section) {
    const seeds = candidates(data, section.seeds, 4);
    const playoff = candidates(data, section.playoff, 4);
    const list = (items, extra) => `<ul class="candidates">${items.map((item) => `<li>${team(item.club.club_id, 16)}<strong>${pct(item.value)}${extra ? ` · quartas ${pct(item.club.stages.quarter_finals)}` : ""}</strong></li>`).join("") || "<li>—</li>"}</ul>`;
    return `<div class="section-card">
      <h3>Seção ${section.id}</h3>
      <p class="candidates-label">Cabeça: ${section.seeds[0]}º ou ${section.seeds[1]}º colocado</p>${list(seeds, true)}
      <p class="candidates-label">Adversário: vencedor do playoff ${section.playoff[0]}º/${section.playoff[1]}º × ${section.playoff[2]}º/${section.playoff[3]}º</p>${list(playoff, false)}
    </div>`;
  }

  function bracketBox(title, lines) {
    return `<div class="tie"><div class="tie-head"><span>${title}</span><b>ida e volta</b></div>${lines.map((line) => `<div class="tie-side open">${line}</div>`).join("")}</div>`;
  }

  function bracket(data) {
    const label = (section) => `${section.seeds[0]}º/${section.seeds[1]}º × playoff ${section.playoff[0]}º–${section.playoff[3]}º`;
    const [a, b, c, d] = SECTIONS;
    const finalists = [...data.clubs].sort((x, y) => y.stages.final - x.stages.final).slice(0, 6);
    const semis = [...data.clubs].sort((x, y) => y.stages.semi_finals - x.stages.semi_finals).slice(0, 8);
    return `
      <h1 class="race-heading">Chave provável do mata-mata</h1>
      <p class="lede lede-method">A fase de liga ainda não acabou, então a chave sai das posições finais. Cada lado da chave tem um cabeça de cada seção; o 1º e o 2º caem em lados opostos e só podem se cruzar na final.</p>
      <h2>O caminho de um lado da chave</h2>
      <div class="bracket" style="--rounds:4">
        <div class="bracket-round"><h3>Oitavas</h3>${[a, d, b, c].map((section) => bracketBox(`Seção ${section.id}`, [label(section)])).join("")}</div>
        <div class="bracket-round"><h3>Quartas</h3>${bracketBox("A × D", ["vencedor da seção A", "vencedor da seção D"])}${bracketBox("B × C", ["vencedor da seção B", "vencedor da seção C"])}</div>
        <div class="bracket-round"><h3>Semifinal</h3>${bracketBox("(A × D) × (B × C)", ["vencedores das quartas"])}</div>
        <div class="bracket-round"><h3>Final</h3><div class="tie"><div class="tie-head"><span>Jogo único</span><b>final</b></div><p class="candidates-label">Mais prováveis na final</p><ul class="candidates">${finalists.map((club) => `<li>${team(club.club_id, 16)}<strong>${pct(club.stages.final)}</strong></li>`).join("")}</ul></div></div>
      </div>
      <h2>Quem pode ocupar cada seção</h2>
      <p class="note">Percentual ao lado de cada clube: em quantas simulações ele termina nas posições daquela seção. Para os cabeças, também a chance de chegar às quartas.</p>
      <div class="sections-grid">${SECTIONS.map((section) => sectionCard(data, section)).join("")}</div>
      <h2>Mais prováveis nas semifinais</h2>
      ${S.raceRows(semis.map((club) => ({ id: club.club_id, value: club.stages.semi_finals })), "")}
      <h2>Fase a fase</h2>
      ${stagesTable(data)}`;
  }

  function stagesTable(data) {
    const rows = [...data.clubs]
      .sort((a, b) => b.stages.winner - a.stages.winner || b.stages.round_of_16 - a.stages.round_of_16)
      .map((club) => `<tr>
        <td class="left club">${team(club.club_id, 20)}</td>
        <td>${S.probCell(club.zones.top8, "lib", club.clinched.top8 ? zoneLabel(club, "top8") : null)}</td>
        <td>${S.probCell(club.zones.playoff, "sula", club.clinched.playoff || club.clinched.top8 ? zoneLabel(club, "playoff") : null)}</td>
        ${STAGES.map(([key]) => `<td class="stage${club.stages[key] >= 0.5 ? " strong" : ""}">${pct(club.stages[key])}</td>`).join("")}
      </tr>`)
      .join("");
    return `<div class="table-scroll" tabindex="0" role="region" aria-label="Chance de cada clube por fase">
      <table><thead><tr><th class="left">Clube</th><th>Top 8</th><th>Playoff</th>${STAGES.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>
    </div>
    <p class="note">Percentuais: em quantas simulações o clube chega a cada fase. As oitavas somam quem foi direto e quem passou no playoff.</p>`;
  }

  function leaguePhase(data) {
    const zone = (position) => (position <= 8 ? "zone-lib" : position <= 24 ? "zone-sula" : "zone-z4");
    const rows = data.clubs.map((club) => {
      const goalDifference = club.goals_for - club.goals_against;
      return `<tr class="${zone(club.position)}">
        <td class="pos">${club.position}</td>
        <td class="left club">${team(club.club_id, 20)} <span class="elo-country">${escapeHtml(club.country)}</span></td>
        <td><strong>${club.points}</strong></td><td>${club.played}</td><td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td><td>${club.goals_for}</td>
        <td class="view-start">${number.format(club.expected_points)}</td>
        <td>${S.probCell(club.zones.top8, "lib", club.clinched.top8 ? zoneLabel(club, "top8") : null)}</td>
        <td>${S.probCell(club.zones.playoff, "sula", club.clinched.playoff || club.clinched.top8 ? zoneLabel(club, "playoff") : null)}</td>
        <td>${S.probCell(club.zones.out, "danger", club.clinched.out ? zoneLabel(club, "out") : null)}</td>
        <td class="left">${S.heat(club.position_probabilities, club.name).replace('class="heat"', 'class="heat heat-wide"')}</td>
      </tr>`;
    }).join("");
    return `
      <h1 class="race-heading">Fase de liga</h1>
      <div class="legend"><span class="l-lib">direto às oitavas (1º ao 8º)</span><span class="l-sula">playoff (9º ao 24º)</span><span class="l-z4">eliminado (25º ao 36º)</span></div>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Tabela da fase de liga">
        <table class="standings">
          <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>SG</th><th>GP</th><th class="view-start">Pts proj.</th><th>Top 8</th><th>Playoff</th><th>Eliminado</th><th class="left">Posição final (1º → 36º)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <p class="note">Ordem atual por pontos, saldo e gols. Pts proj. = média simulada de pontos ao fim das 8 rodadas.</p>`;
  }

  function matches(data) {
    const scheduled = data.remaining.filter((match) => match.round !== null);
    if (!scheduled.length) return `<h1 class="race-heading">Jogos</h1><p>Não há jogos marcados.</p>`;
    const round = Math.min(...scheduled.map((match) => match.round));
    let lastDay = "";
    const rows = scheduled
      .filter((match) => match.round === round)
      .sort((a, b) => (a.kickoff_utc || a.match_date).localeCompare(b.kickoff_utc || b.match_date))
      .map((match) => {
        const day = match.match_date !== lastDay ? `<h3 class="round-day">${escapeHtml(S.formatDate(match.match_date, { weekday: "long", day: "numeric", month: "long" }))}</h3>` : "";
        lastDay = match.match_date;
        return day + S.matchRow(match);
      })
      .join("");
    return `
      <h1 class="race-heading">Rodada ${round} da fase de liga</h1>
      <p class="note">Horários de Brasília. Mandante à esquerda; chance de vitória do mandante, empate e vitória do visitante.</p>
      <div class="legend"><span class="l-home">mandante</span><span class="l-draw">empate</span><span class="l-away">visitante</span></div>
      ${rows}`;
  }

  function method(data) {
    const backtest = data.backtest;
    const seasons = backtest ? backtest.test_seasons.map((season) => `${season}/${String(season + 1).slice(2)}`).join(" e ") : "";
    const facts = backtest
      ? `<div class="stat-row">
          <div class="stat"><span class="label">Log loss por jogo</span><span class="big">${decimal.format(backtest.log_loss)}</span><span class="sub">${backtest.n_matches} jogos de ${seasons}; taxa base ${decimal.format(backtest.log_loss_base_rate)}</span></div>
          <div class="stat"><span class="label">Brier do top 8</span><span class="big">${decimal.format(backtest.top8_brier)}</span><span class="sub">com ${8 - backtest.late_matchday} rodadas por jogar; só a proporção ${decimal.format(backtest.top8_brier_base)}</span></div>
          <div class="stat"><span class="label">Brier das quartas</span><span class="big">${decimal.format(backtest.quarter_finals_brier)}</span><span class="sub">no mesmo ponto; só a proporção ${decimal.format(backtest.quarter_finals_brier_base)}</span></div>
          <div class="stat"><span class="label">Log loss do campeão</span><span class="big">${decimal.format(backtest.winner_log_loss)}</span><span class="sub">chute uniforme ${decimal.format(backtest.winner_log_loss_uniform)}; só duas temporadas</span></div>
        </div>`
      : "";
    return `
      <h1 class="race-heading">Como calculamos</h1>
      <p>Na Champions, os clubes vêm de ligas diferentes. Por isso usamos uma força única (Elo) para todos, calculada com as sete principais ligas da Europa e com a Champions, a Liga Europa e a Conference desde 2021/22: as copas europeias ligam as ligas entre si. Um modelo de gols treinado só com jogos europeus de temporadas anteriores transforma a diferença de força em placares. Cada uma das ${data.n_simulations.toLocaleString("pt-BR")} simulações termina a fase de liga com os critérios de desempate da UEFA e joga o mata-mata com o chaveamento do regulamento, até a final.</p>
      <h2>Acerto em temporadas passadas</h2>
      ${facts}
      <p class="note">Menor é melhor no log loss e no Brier.</p>
      <h2>Limitações</h2>
      <ul class="summary-list">${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
        <li>Clubes de ligas fora das sete principais têm força medida só pelos jogos europeus; os que nunca jogaram copas europeias desde 2021/22 começam de um valor fixo.</li>
        <li>A chave provável mostra as posições de cada seção; onde a UEFA sorteia (quem é o 1º ou o 2º de cada lado), a simulação sorteia com chances iguais.</li>
        <li>"Garantido", "não dá mais", "eliminado" e "não cai mais" só aparecem quando a conta de pontos fecha, nunca por simulação.</li>
      </ul>
      <h2>Regulamento e fontes</h2>
      <p>Regulamento: <a href="${S.safeUrl(data.regulation.url)}">${escapeHtml(data.regulation.title)}</a>.</p>
      <ul class="summary-list">${S.sources(data.sources)}</ul>
      <p class="note">Modelo ${escapeHtml(data.model_version)} · dados <code class="data-version">${escapeHtml(data.data_version)}</code> · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
      <div id="metodo-elo"></div>`;
  }

  S.start({
    names: (data) => Object.fromEntries(data.clubs.map((club) => [club.club_id, club.name])),
    edition,
    footer: (data) => {
      const credits = [...new Map(data.sources.map((source) => [source.attribution, source])).values()];
      return `Fontes: ${credits.map((source) => `<a href="${S.safeUrl(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`).join("; ")}.`;
    },
    routes: [
      { id: "", label: "Início", render: home },
      { id: "chave", label: "Chave provável", render: bracket },
      { id: "fase-de-liga", label: "Fase de liga", render: leaguePhase },
      { id: "jogos", label: "Jogos", render: matches },
      { id: "metodologia", label: "Como calculamos", render: method, after: (data, main) => window.AIndaDaMetodo && window.AIndaDaMetodo.render(main.querySelector("#metodo-elo"), data.competition) },
    ],
  });
})();
