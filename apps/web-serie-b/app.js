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
    const phase = left === 0 ? "fase regular encerrada · playoffs" : left === 1 ? "falta 1 rodada" : `faltam ${left} rodadas`;
    const simScope = left === 0 ? "simulações dos playoffs" : "simulações do que falta e dos playoffs";
    return `<p class="edition"><span class="edition-name">Edição de ${escapeHtml(S.formatDate(data.reference_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }))}</span> · Série B ${data.season} · ${phase}</p>
      <p class="edition-facts"><strong>${data.observed_matches}</strong> jogos disputados · <strong>${data.n_simulations.toLocaleString("pt-BR")}</strong> ${simScope}</p>`;
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
    const info = `<p>Dois sobem direto; do 3º ao 6º, playoff em ida e volta vale mais duas vagas na Série A de ${data.season + 1}. Os quatro últimos caem.</p>
      <p>Cada porcentagem diz em quantas das ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta (e dos playoffs) aquilo aconteceu. "Subiu", "caiu" e "não dá mais" só aparecem quando a conta de pontos fecha.</p>`;
    const playoffInfo = "Quem pode ocupar cada lugar do playoff e quanto disso acontece nas simulações. Ida na casa do pior colocado, volta na casa do melhor; empatou em pontos e saldo, passa o melhor colocado. Não tem pênaltis.";
    return `
      ${S.screenHead("Quem sobe, quem cai", info)}
      ${S.yourTeam(data)}
      <div class="races">
        ${S.raceCard("Sobe direto", "% das simulações em que termina em 1º ou 2º.", S.raceRows(direct.map((club) => ({ id: club.club_id, value: club.promotion_direct, label: directLabel(club) })), "lib"))}
        ${S.raceCard("Sobe (direto ou pelo playoff)", "% das simulações em que termina com o acesso, direto ou pelo playoff.", S.raceRows(total.map((club) => ({ id: club.club_id, value: club.promotion, label: promotionLabel(club) })), "lib"))}
        ${S.raceCard("Cai", "% das simulações em que termina entre 17º e 20º.", S.raceRows(drop.map((club) => ({ id: club.club_id, value: club.relegation, label: relegationLabel(club) })), "danger"))}
      </div>
      ${S.raceCard("Chave do playoff", playoffInfo, playoffBracket(data, byId))}
      <nav class="chip-row comp-links" aria-label="Mais"><a class="chip" href="#/tabela">Tabela completa ›</a>${data.remaining.length ? '<a class="chip" href="#/jogos">Jogos que faltam ›</a>' : ""}</nav>`;
  }

  const WORDS = {
    sobe: { sure: "Sobem em quase todas as simulações", open: "Na briga pelo acesso", out: "Longe do acesso" },
    playoff: { sure: "No playoff em quase todas", open: "Na briga pelo playoff", out: "Fora do playoff" },
    cai: { sure: "Caem em quase todas as simulações", open: "Ainda correm risco de queda", out: "Longe da queda" },
  };

  function races(data) {
    const byId = Object.fromEntries(data.teams.map((club) => [club.club_id, club]));
    const race = (id, label, color, words, key, text, state, info) => ({
      id, label, color, words, info,
      value: (model) => byId[model.id][key], text: (model) => text(byId[model.id]), state: (model) => state(byId[model.id]),
    });
    const text = (fn, clinchedAny) => (club) => (clinchedAny(club) ? fn(club) : null);
    return [
      race("direto", "Sobe direto", "libertadores", WORDS.sobe, "promotion_direct", text(directLabel, (club) => club.clinched.promoted_direct || club.clinched.out_of_top6 || club.clinched.out_of_top2),
        (club) => (club.clinched.promoted_direct ? "in" : club.clinched.out_of_top6 || club.clinched.out_of_top2 ? "out" : null), "<p>% das simulações em que termina em 1º ou 2º e sobe direto.</p>"),
      race("sobe", "Sobe", "libertadores", WORDS.sobe, "promotion", text(promotionLabel, (club) => club.clinched.promoted_direct || club.clinched.out_of_top6),
        (club) => (club.clinched.promoted_direct ? "in" : club.clinched.out_of_top6 ? "out" : null), "<p>% das simulações em que termina com o acesso, direto ou pelo playoff.</p>"),
      race("playoff", "Playoff", "sudamericana", WORDS.playoff, "playoff", text(() => "não dá mais", (club) => club.clinched.out_of_top6),
        (club) => (club.clinched.out_of_top6 ? "out" : null), "<p>% das simulações em que termina entre 3º e 6º e disputa o playoff.</p>"),
      race("cai", "Cai", "danger", WORDS.cai, "relegation", text(relegationLabel, (club) => club.clinched.relegated || club.clinched.safe),
        (club) => (club.clinched.relegated ? "in" : club.clinched.safe ? "out" : null), "<p>% das simulações em que termina entre 17º e 20º.</p>"),
    ];
  }

  function table(data) {
    const info = `<p>Escolha a disputa: quem já está garantido, quem está na briga e quem está fora. "Tabela completa" traz pontos, jogos, saldo e a faixa de posição final.</p><p>Faixa lateral da tabela: azul = acesso direto (1º e 2º), âmbar = playoff (3º ao 6º), vermelho = rebaixamento (17º ao 20º). "Sobe" soma o acesso direto e o pelo playoff.</p><p>Toque num clube para ver a ficha dele.</p>`;
    const clubs = data.teams.map((club) => ({ id: club.club_id, name: club.name, position: club.position, points: club.points, meta: `${club.points} pts`, interval: club.points_interval_90 }));
    return `
      ${S.screenHead("Tabela", info + races(data).map((race) => `<p><strong>${escapeHtml(race.label)}.</strong> ${race.info.replace(/^<p>|<\/p>$/g, "")}</p>`).join(""))}
      ${S.disputeBoard("tabela", { clubs, races: races(data), full: () => fullTable(data) })}`;
  }

  function fullTable(data) {
    const direct = data.rules.direct_promotion;
    const playoffLast = Math.max(...data.rules.playoff_groups.map((group) => group[1]));
    const safeLast = data.teams.length - data.rules.relegation;
    const zone = (position) => (position <= direct ? "zone-lib" : position <= playoffLast ? "zone-sula" : position > safeLast ? "zone-z4" : "");
    // Probabilidades logo depois de Pts: no celular o percentual aparece sem rolar a tabela de lado.
    const rows = data.teams.map((club) => {
      const goalDifference = club.goals_for - club.goals_against;
      return `<tr class="${zone(club.position)}">
        <td class="pos">${club.position}</td>
        <td class="left club">${S.teamCell(club.club_id)}</td>
        <td><strong>${club.points}</strong></td>
        <td class="view-start">${S.probCell(club.promotion_direct, "lib", directLabel(club))}</td>
        <td>${S.probCell(club.playoff, "sula", club.clinched.out_of_top6 ? "não dá mais" : null)}</td>
        <td>${S.probCell(club.promotion, "lib", promotionLabel(club))}</td>
        <td>${S.probCell(club.relegation, "danger", relegationLabel(club))}</td>
        <td class="rest-start">${club.played}</td><td>${club.wins}</td><td>${club.draws}</td><td>${club.losses}</td>
        <td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td>
        <td>${number.format(club.expected_points)}<span class="range">${club.points_interval_90[0]}–${club.points_interval_90[1]}</span></td>
        <td class="left">${S.heat(club.position_probabilities, club.name)}</td>
      </tr>`;
    }).join("");
    return `<div class="table-scroll table-card" tabindex="0" role="region" aria-label="Tabela da Série B">
        <table class="standings">
          <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th class="view-start">Sobe direto</th><th>Playoff</th><th>Sobe</th><th>Cai</th><th class="rest-start">J</th><th>V</th><th>E</th><th>D</th><th>SG</th><th>Pts proj.</th><th class="left">Posição final (1º → 20º)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function matches(data) {
    const info = "<p>Probabilidade de vitória do mandante, de empate e de vitória do visitante, com a força de cada clube na data da edição. Toque num jogo para ver os detalhes.</p><p>A fonte da Série B não traz as datas dos jogos que faltam; por isso eles aparecem em ordem da tabela (pela posição do mandante).</p>";
    if (!data.remaining.length) {
      return `
        ${S.screenHead("Jogos", info)}
        <div class="state">
          <p class="state-title">Fase regular encerrada</p>
          <p class="state-text">Todos os ${data.observed_matches} jogos dos pontos corridos já foram disputados. Veja os confrontos e probabilidades do playoff no Início.</p>
          <a class="state-action btn-secondary" href="#/">Ver chave do playoff</a>
        </div>`;
    }
    const byId = Object.fromEntries(data.teams.map((club) => [club.club_id, club]));
    const list = [...data.remaining].sort((a, b) => byId[a.home_id].position - byId[b.home_id].position);
    return `
      ${S.screenHead(`Jogos que faltam · ${data.remaining.length}`, info)}
      <p class="comp-notice">Sem datas na fonte: jogos na ordem da tabela.</p>
      ${S.matchList(list)}`;
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
    shorts: (data) => Object.fromEntries(data.teams.map((club) => [club.club_id, club.short_name])),
    favorite: {
      code: () => "serie-b",
      clubs: (data) => data.teams.map((club) => ({ id: club.club_id, name: club.name, meta: `${club.position}º lugar · ${club.points} pts` })),
      stats: (data, id) => {
        const club = data.teams.find((item) => item.club_id === id);
        return [
          { label: "Acesso", text: promotionLabel(club), tone: "is-g4" },
          { label: "Playoff", text: club.clinched.out_of_top6 ? "não dá mais" : pct(club.playoff) },
          { label: "Queda", text: relegationLabel(club), tone: "is-z4" },
        ];
      },
    },
    club: (data, id) => {
      const club = data.teams.find((item) => item.club_id === id);
      if (!club) return null;
      return {
        name: club.name,
        meta: `${club.position}º lugar · ${club.points} pts · ${club.played} J (${club.wins}V ${club.draws}E ${club.losses}D)`,
        stats: [
          { label: "Acesso", text: promotionLabel(club), tone: "is-g4" },
          { label: "Playoff", text: club.clinched.out_of_top6 ? "não dá mais" : pct(club.playoff) },
          { label: "Queda", text: relegationLabel(club), tone: "is-z4" },
        ],
        interval: club.points_interval_90,
        expectedPoints: club.expected_points,
        next: [],
      };
    },
    edition,
    footer: (data) => `${data.sources.map((source) => `<a href="${S.safeUrl(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`).join("; ")}. Licenças: <a href="https://creativecommons.org/licenses/by-sa/4.0/deed.pt-br">CC BY-SA 4.0</a> e <a href="https://creativecommons.org/publicdomain/zero/1.0/deed.pt-br">CC0 1.0</a>.`,
    routes: [
      { id: "", label: "Início", render: home },
      { id: "tabela", label: "Tabela", render: table },
      { id: "jogos", label: "Jogos", render: matches },
      { id: "metodologia", label: "Como calculamos", render: method, after: (data, main) => window.AIndaDaMetodo && window.AIndaDaMetodo.render(main.querySelector("#metodo-elo"), "serie-b") },
    ],
  });
})();
