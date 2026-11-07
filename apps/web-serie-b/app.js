"use strict";

// Série B (ADR-0010) no desenho dos sites de competição (D-043): Início, Tabela, Jogos e Como calculamos.
(function () {
  const S = window.AIndaDaSite;
  const { escapeHtml, pct, team } = S;
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

  // Rótulos de certeza: só quando a aritmética decide (clinched), nunca por simulação.
  function promotionLabel(club) {
    if (club.clinched.promoted_direct) return "subiu";
    if (club.clinched.out_of_top6) return "não dá mais";
    return pct(club.promotion);
  }
  function directLabel(club) {
    if (club.clinched.promoted_direct) return "subiu";
    if (club.clinched.out_of_top6) return "não dá mais";
    if (club.clinched.out_of_top2) return "só pelo playoff";
    return pct(club.promotion_direct);
  }
  function relegationLabel(club) {
    if (club.clinched.relegated) return "caiu";
    if (club.clinched.safe) return "não cai mais";
    return pct(club.relegation);
  }

  const roundsLeft = (data) => Math.max(...data.teams.map((club) => club.remaining));

  function edition(data) {
    const left = roundsLeft(data);
    return `<p class="edition"><span class="edition-name">Edição de ${escapeHtml(S.formatDate(data.reference_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }))}</span> · Série B ${data.season} · ${left === 1 ? "falta 1 rodada" : `faltam ${left} rodadas`}</p>
      <p class="edition-facts"><strong>${data.observed_matches}</strong> jogos disputados · <strong>${data.n_simulations.toLocaleString("pt-BR")}</strong> simulações do que falta e dos playoffs</p>`;
  }

  function playoffBracket(data, byId) {
    const groups = data.rules.playoff_groups;
    const likely = Object.fromEntries(data.likely_playoffs.map((pairing) => [`${pairing.better_position}-${pairing.worse_position}`, pairing]));
    const candidates = (position) => [...data.teams]
      .map((club) => ({ id: club.club_id, value: club.position_probabilities[position - 1] }))
      .filter((item) => item.value > 0.005)
      .sort((a, b) => b.value - a.value)
      .slice(0, 3);
    const side = (position) => `<p class="candidates-label">${position}º colocado</p><ul class="candidates">${candidates(position)
      .map((item) => `<li>${team(item.id, 16)}<strong>${pct(item.value)}</strong></li>`).join("") || "<li>—</li>"}</ul>`;
    const ties = groups.map(([better, worse]) => {
      const pairing = likely[`${better}-${worse}`];
      const tip = pairing
        ? `Duelo mais provável: ${escapeHtml(byId[pairing.better_club_id].name)} × ${escapeHtml(byId[pairing.worse_club_id].name)}, em ${pct(pairing.probability)} das simulações; nele, ${escapeHtml(byId[pairing.better_club_id].name)} passa em ${pct(pairing.better_advances)}.`
        : "";
      return `<div class="tie"><div class="tie-head"><span>${better}º × ${worse}º · ida e volta</span><b>vale vaga</b></div>${side(better)}${side(worse)}${tip ? `<p class="candidates-label">${tip}</p>` : ""}</div>`;
    }).join("");
    return `<div class="sections-grid">${ties}</div>`;
  }

  function home(data) {
    const byId = Object.fromEntries(data.teams.map((club) => [club.club_id, club]));
    const open = (key, out) => data.teams.filter((club) => !out(club)).sort((a, b) => b[key] - a[key]);
    const direct = open("promotion_direct", (club) => club.clinched.out_of_top6).slice(0, 6);
    const total = open("promotion", (club) => club.clinched.out_of_top6).slice(0, 8);
    const drop = data.teams.filter((club) => !club.clinched.safe).sort((a, b) => b.relegation - a.relegation).slice(0, 8);
    const leader = [...data.teams].sort((a, b) => b.promotion - a.promotion)[0];
    const relegated = data.teams.filter((club) => club.clinched.relegated);
    const dropLine = relegated.length ? ` ${relegated.map((club) => escapeHtml(club.name)).join(", ").replace(/, ([^,]*)$/, " e $1")} já ${relegated.length > 1 ? "caíram" : "caiu"}.` : "";
    return `
      <h1>Quatro sobem, quatro caem. Quem ainda dá?</h1>
      <p class="lede">Dois sobem direto; do 3º ao 6º, playoff em ida e volta vale mais duas vagas na Série A de ${data.season + 1}. <strong>${escapeHtml(leader.name)}</strong> ${leader.clinched.promoted_direct ? "já subiu." : `é quem está mais perto: sobe em ${pct(leader.promotion)} das simulações.`}${dropLine}</p>
      <div class="races">
        <section class="race"><h3>Sobe direto</h3><p class="note">% das simulações em que termina em 1º ou 2º</p>${S.raceRows(direct.map((club) => ({ id: club.club_id, value: club.promotion_direct, label: directLabel(club) })), "lib")}</section>
        <section class="race"><h3>Sobe (direto ou pelo playoff)</h3><p class="note">% das simulações em que termina com o acesso</p>${S.raceRows(total.map((club) => ({ id: club.club_id, value: club.promotion, label: promotionLabel(club) })), "lib")}</section>
        <section class="race"><h3>Cai</h3><p class="note">% das simulações em que termina entre 17º e 20º</p>${S.raceRows(drop.map((club) => ({ id: club.club_id, value: club.relegation, label: relegationLabel(club) })), "danger")}</section>
      </div>
      <h2>Chave do playoff</h2>
      <p class="note">Quem pode ocupar cada lugar do playoff e quanto disso acontece nas simulações. Ida na casa do pior colocado, volta na casa do melhor; empatou em pontos e saldo, passa o melhor colocado. Não tem pênaltis.</p>
      ${playoffBracket(data, byId)}
      <p class="more"><a href="#/tabela">Tabela completa</a> · <a href="#/jogos">Jogos que faltam</a></p>`;
  }

  function table(data) {
    const direct = data.rules.direct_promotion;
    const playoffLast = Math.max(...data.rules.playoff_groups.map((group) => group[1]));
    const safeLast = data.teams.length - data.rules.relegation;
    const zone = (position) => (position <= direct ? "zone-lib" : position <= playoffLast ? "zone-sula" : position > safeLast ? "zone-z4" : "");
    const rows = data.teams.map((club) => {
      const goalDifference = club.goals_for - club.goals_against;
      return `<tr class="${zone(club.position)}">
        <td class="pos">${club.position}</td>
        <td class="left club">${team(club.club_id, 20)}</td>
        <td><strong>${club.points}</strong></td><td>${club.played}</td><td>${club.wins}</td><td>${club.draws}</td><td>${club.losses}</td>
        <td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td>
        <td class="view-start">${number.format(club.expected_points)}<span class="range">${club.points_interval_90[0]}–${club.points_interval_90[1]}</span></td>
        <td>${S.probCell(club.promotion_direct, "lib", directLabel(club))}</td>
        <td>${S.probCell(club.playoff, "sula", club.clinched.out_of_top6 ? "não dá mais" : null)}</td>
        <td>${S.probCell(club.promotion, "lib", promotionLabel(club))}</td>
        <td>${S.probCell(club.relegation, "danger", relegationLabel(club))}</td>
        <td class="left">${S.heat(club.position_probabilities, club.name)}</td>
      </tr>`;
    }).join("");
    return `
      <h1 class="race-heading">Tabela</h1>
      <div class="legend"><span class="l-lib">acesso direto (1º e 2º)</span><span class="l-sula">playoff (3º ao 6º)</span><span class="l-z4">rebaixamento (17º ao 20º)</span></div>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Tabela da Série B">
        <table class="standings">
          <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>V</th><th>E</th><th>D</th><th>SG</th><th class="view-start">Pts proj.</th><th>Sobe direto</th><th>Playoff</th><th>Sobe</th><th>Cai</th><th class="left">Posição final (1º → 20º)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <p class="note">Pts proj. = média simulada de pontos no fim; embaixo, a faixa onde terminam 90% das simulações. "Sobe" soma o acesso direto e o pelo playoff. A faixa à direita mostra a probabilidade de cada posição final: quanto mais escura, mais provável.</p>`;
  }

  function matches(data) {
    const byId = Object.fromEntries(data.teams.map((club) => [club.club_id, club]));
    const rows = [...data.remaining].sort((a, b) => byId[a.home_id].position - byId[b.home_id].position).map(S.matchRow).join("");
    return `
      <h1 class="race-heading">Os ${data.remaining.length} jogos que faltam</h1>
      <p class="note">Mandante à esquerda; probabilidade de vitória do mandante, empate e vitória do visitante. A fonte não traz as datas, então os jogos aparecem pela posição do mandante na tabela.</p>
      <div class="legend"><span class="l-home">mandante</span><span class="l-draw">empate</span><span class="l-away">visitante</span></div>
      ${rows}`;
  }

  function method(data) {
    const backtest = data.backtest;
    const facts = backtest
      ? `<div class="stat-row">
          <div class="stat"><span class="label">Log loss por jogo</span><span class="big">${decimal.format(backtest.log_loss)}</span><span class="sub">${backtest.n_matches.toLocaleString("pt-BR")} jogos de ${backtest.test_seasons[0]} a ${backtest.test_seasons[backtest.test_seasons.length - 1]}; taxa base ${decimal.format(backtest.log_loss_base_rate)}</span></div>
          <div class="stat"><span class="label">Brier de "4 primeiros"</span><span class="big">${decimal.format(backtest.late_top4_brier)}</span><span class="sub">com ${38 - backtest.late_round} rodadas por jogar; chute fixo ${decimal.format(backtest.climatology_brier)}</span></div>
          <div class="stat"><span class="label">Brier do rebaixamento</span><span class="big">${decimal.format(backtest.late_relegation_brier)}</span><span class="sub">no mesmo ponto da temporada</span></div>
          <div class="stat"><span class="label">Pontos na faixa de 90%</span><span class="big">${Math.round(backtest.late_points_interval_90_coverage * 100)}%</span><span class="sub">dos pontos finais</span></div>
        </div>`
      : "";
    return `
      <h1 class="race-heading">Como calculamos</h1>
      <p>É o mesmo modelo da Série A do AInda dá?, com parâmetros calibrados nos jogos da própria Série B: força de cada clube (Elo, ataque e defesa) reconstruída jogo a jogo desde 2018, um modelo de gols treinado só com temporadas anteriores e ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta. Cada simulação termina a tabela com os critérios do regulamento e depois disputa os dois playoffs, ida e volta.</p>
      <h2>Acerto em temporadas passadas</h2>
      ${facts}
      <p class="note">Menor é melhor no log loss e no Brier.</p>
      <h2>Limitações</h2>
      <ul class="summary-list">${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
        <li>Quem não jogou a Série B no ano anterior começa a temporada com a força média dos clubes que deixaram a divisão; a força se ajusta jogo a jogo depois disso.</li>
        <li>"Subiu", "caiu" e "não dá mais" só aparecem quando a conta de pontos fecha, nunca por simulação.</li>
      </ul>
      <h2>Regulamento e fontes</h2>
      <p>Regulamento: <a href="${S.safeUrl(data.regulation.url)}">${escapeHtml(data.regulation.title)}</a>.</p>
      <ul class="summary-list">${S.sources(data.sources)}</ul>
      <p class="note">Modelo ${escapeHtml(data.model_version)} · dados <code class="data-version">${escapeHtml(data.data_version)}</code> · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
      <div id="metodo-elo"></div>`;
  }

  S.start({
    names: (data) => Object.fromEntries(data.teams.map((club) => [club.club_id, club.name])),
    edition,
    footer: (data) => `Fontes: ${data.sources.map((source) => `<a href="${S.safeUrl(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`).join("; ")}. Licenças: <a href="https://creativecommons.org/licenses/by-sa/4.0/deed.pt-br">CC BY-SA 4.0</a> e <a href="https://creativecommons.org/publicdomain/zero/1.0/deed.pt-br">CC0 1.0</a>.`,
    routes: [
      { id: "", label: "Início", render: home },
      { id: "tabela", label: "Tabela", render: table },
      { id: "jogos", label: "Jogos", render: matches },
      { id: "metodologia", label: "Como calculamos", render: method, after: (data, main) => window.AIndaDaMetodo && window.AIndaDaMetodo.render(main.querySelector("#metodo-elo"), "serie-b") },
    ],
  });
})();
