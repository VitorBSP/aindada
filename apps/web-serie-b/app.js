"use strict";

(function () {
  const main = document.getElementById("main");

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

  // Certeza só quando a aritmética decide (clinched); simulação nunca vira certeza (CONTENT_GUIDELINES).
  function pct(value, decided, done = { yes: "100%", no: "não dá mais" }) {
    if (decided === 1) return done.yes;
    if (decided === 0) return done.no;
    if (value < 0.001) return "<0,1%";
    if (value > 0.999) return ">99,9%";
    if (value < 0.01 || value > 0.99) return number.format(Math.round(value * 1000) / 10) + "%";
    return Math.round(value * 100) + "%";
  }

  const PROMOTION_DONE = { yes: "subiu", no: "não dá mais" };
  const RELEGATION_DONE = { yes: "caiu", no: "não cai mais" };

  function formatDate(iso) {
    const [year, month, day] = iso.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" });
  }

  function badge(team) {
    return `<span class="badge" aria-hidden="true">${escapeHtml(team.short_name)}</span>`;
  }

  function decidedPromotion(team) {
    if (team.clinched.promoted_direct) return 1;
    if (team.clinched.out_of_top6) return 0;
    return null;
  }

  // Fora do top 2 ainda pode subir pelo playoff: "não dá mais" só quando nem o 6º lugar é possível.
  function directDone(team) {
    return { yes: "subiu", no: team.clinched.out_of_top6 ? "não dá mais" : "só pelo playoff" };
  }

  function decidedDirect(team) {
    if (team.clinched.promoted_direct) return 1;
    if (team.clinched.out_of_top2) return 0;
    return null;
  }

  function decidedRelegation(team) {
    if (team.clinched.relegated) return 1;
    if (team.clinched.safe) return 0;
    return null;
  }

  function zoneList(teams, valueOf, decidedOf, doneOf) {
    return `<ol>${teams
      .map((team) => {
        const decided = decidedOf(team);
        const value = `<span class="value${decided === null ? "" : " done"}">${pct(valueOf(team), decided, doneOf(team))}</span>`;
        return `<li>${badge(team)}<span class="name">${escapeHtml(team.name)}</span>${value}</li>`;
      })
      .join("")}</ol>`;
  }

  function hero(data) {
    const byPromotion = [...data.teams].sort((a, b) => b.promotion - a.promotion);
    const byDirect = [...data.teams].sort((a, b) => b.promotion_direct - a.promotion_direct).slice(0, 4);
    const byPlayoff = [...data.teams].sort((a, b) => b.playoff - a.playoff).slice(0, 6);
    const byDrop = [...data.teams].sort((a, b) => b.relegation - a.relegation).slice(0, 6);
    const roundsLeft = Math.max(...data.teams.map((team) => team.remaining));
    const leader = byPromotion[0];
    const relegated = data.teams.filter((team) => team.clinched.relegated);
    const dropLine = relegated.length
      ? ` ${relegated.map((team) => escapeHtml(team.name)).join(", ").replace(/, ([^,]*)$/, " e $1")} já ${relegated.length > 1 ? "caíram" : "caiu"}.`
      : "";
    return `
      <section aria-labelledby="titulo">
        <p class="kicker">Série B ${data.season} · ${roundsLeft === 1 ? "falta 1 rodada" : `faltam ${roundsLeft} rodadas`}</p>
        <h1 id="titulo">Quatro sobem, quatro caem. Quem ainda dá?</h1>
        <p class="lede">Dois sobem direto. Do 3º ao 6º, playoff em ida e volta vale mais duas vagas na Série A de ${data.season + 1}. ${escapeHtml(leader.name)} ${decidedPromotion(leader) === 1 ? "já subiu." : `é quem está mais perto: sobe em ${pct(leader.promotion)} das simulações.`}${dropLine}</p>
        <p class="meta">Resultados até ${formatDate(data.reference_date)} · ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta e dos playoffs</p>
        <div class="zones">
          <div class="zone up"><h3>Sobe direto</h3><p class="zone-sub">% das simulações em que termina em 1º ou 2º</p>${zoneList(byDirect, (team) => team.promotion_direct, decidedDirect, directDone)}</div>
          <div class="zone mid"><h3>Vai ao playoff</h3><p class="zone-sub">% das simulações em que termina entre 3º e 6º</p>${zoneList(byPlayoff, (team) => team.playoff, (team) => (team.clinched.out_of_top6 ? 0 : null), () => PROMOTION_DONE)}</div>
          <div class="zone down"><h3>Cai</h3><p class="zone-sub">% das simulações em que termina entre 17º e 20º</p>${zoneList(byDrop, (team) => team.relegation, decidedRelegation, () => RELEGATION_DONE)}</div>
        </div>
      </section>`;
  }

  function ladder(data) {
    const contenders = data.teams.filter((team) => !team.clinched.out_of_top6).sort((a, b) => b.promotion - a.promotion);
    const rows = contenders
      .map((team) => {
        const lost = Math.max(team.playoff - team.promotion_playoff, 0);
        const width = (value) => `${(value * 100).toFixed(2)}%`;
        const label = `${team.name}: ${pct(team.promotion_direct, decidedDirect(team), directDone(team))} direto, ${pct(team.promotion_playoff)} pelo playoff`;
        return `<li>
          ${badge(team)}<span class="club">${escapeHtml(team.name)}</span>
          <span class="stack" role="img" aria-label="${escapeHtml(label)}">
            <span class="direct" style="width:${width(team.promotion_direct)}"></span>
            <span class="via-playoff" style="width:${width(team.promotion_playoff)}"></span>
            <span class="lost-playoff" style="width:${width(lost)}"></span>
          </span>
          <span class="total">${pct(team.promotion, decidedPromotion(team), PROMOTION_DONE)}</span>
        </li>`;
      })
      .join("");
    const out = data.teams.length - contenders.length;
    return `
      <section id="corrida" aria-labelledby="corrida-titulo">
        <h2 id="corrida-titulo">A escada do acesso</h2>
        <p class="section-note">Chance total de subir, dividida pelo caminho. O trecho claro é a chance de chegar ao playoff e perder.${out ? ` ${out} clubes não alcançam mais o 6º lugar e ficam de fora.` : ""}</p>
        <ul class="legend">
          <li><i style="background:var(--up)"></i>sobe direto</li>
          <li><i style="background:var(--up-mid)"></i>sobe pelo playoff</li>
          <li><i style="background:var(--up-soft)"></i>vai ao playoff e cai fora</li>
        </ul>
        <ol class="ladder">${rows}</ol>
      </section>`;
  }

  function playoff(data, byId) {
    const ties = data.likely_playoffs
      .map((pairing) => {
        const better = byId[pairing.better_club_id];
        const worse = byId[pairing.worse_club_id];
        const betterShare = (pairing.better_advances * 100).toFixed(1);
        return `<article class="tie">
          <h3>Grupo ${escapeHtml(pairing.group)} · ${pairing.better_position}º x ${pairing.worse_position}º</h3>
          <div class="side">${badge(better)}<span class="name">${escapeHtml(better.name)}</span><span class="pct">${pct(pairing.better_advances)}</span></div>
          <p class="vs">decide em casa</p>
          <div class="side">${badge(worse)}<span class="name">${escapeHtml(worse.name)}</span><span class="pct">${pct(1 - pairing.better_advances)}</span></div>
          <div class="split" aria-hidden="true"><span style="width:${betterShare}%"></span><span style="width:${(100 - betterShare).toFixed(1)}%"></span></div>
          <p>Confronto mais provável do grupo, em ${pct(pairing.probability)} das simulações. Percentuais: chance de cada um passar se esse for o duelo.</p>
        </article>`;
      })
      .join("");
    return `
      <section id="playoff" aria-labelledby="playoff-titulo">
        <h2 id="playoff-titulo">O playoff mais provável</h2>
        <p class="section-note">Ida na casa do pior colocado, volta na casa do melhor. Passa quem somar mais pontos nos dois jogos; empatou, vale o saldo de gols e, persistindo, a melhor posição na classificação final. Não tem pênaltis.</p>
        <div class="playoff-grid">${ties}</div>
      </section>`;
  }

  function relegation(data) {
    const atRisk = data.teams.filter((team) => !team.clinched.safe).sort((a, b) => b.relegation - a.relegation);
    const safeCount = data.teams.length - atRisk.length;
    const items = atRisk
      .map((team) => {
        const decided = decidedRelegation(team);
        const gone = decided === 1;
        return `<li class="${gone ? "gone" : ""}">${badge(team)}<span class="name">${escapeHtml(team.name)}</span>
          <span class="pct">${pct(team.relegation, decided, RELEGATION_DONE)}</span>
          <span class="meter" aria-hidden="true"><span style="width:${(team.relegation * 100).toFixed(1)}%"></span></span></li>`;
      })
      .join("");
    return `
      <section id="queda" aria-labelledby="queda-titulo">
        <h2 id="queda-titulo">Quem ainda pode cair</h2>
        <p class="section-note">Só clubes que a matemática ainda não livrou. ${safeCount} já não caem mais.</p>
        <ul class="drop">${items}</ul>
      </section>`;
  }

  function table(data) {
    const direct = data.rules.direct_promotion;
    const playoffLast = Math.max(...data.rules.playoff_groups.map((group) => group[1]));
    const safeLast = data.teams.length - data.rules.relegation;
    const rows = data.teams
      .map((team) => {
        const cut = team.position === direct ? "cut-direct" : team.position === playoffLast ? "cut-playoff" : team.position === safeLast ? "cut-safe" : "";
        const heat = team.position_probabilities
          .map((value, index) => `<i style="opacity:${value === 0 ? 0.06 : (0.12 + 0.88 * Math.min(1, value * 1.6)).toFixed(2)}" title="${index + 1}º: ${pct(value)}"></i>`)
          .join("");
        return `<tr class="${cut}">
          <td>${team.position}</td>
          <td class="left"><span class="club-cell">${badge(team)}${escapeHtml(team.name)}</span></td>
          <td class="pts">${team.points}</td><td>${team.played}</td><td>${team.wins}</td><td>${team.draws}</td><td>${team.losses}</td>
          <td>${team.goals_for - team.goals_against > 0 ? "+" : ""}${team.goals_for - team.goals_against}</td>
          <td>${number.format(team.expected_points)}</td>
          <td>${pct(team.promotion, decidedPromotion(team), PROMOTION_DONE)}</td>
          <td>${pct(team.relegation, decidedRelegation(team), RELEGATION_DONE)}</td>
          <td class="left"><span class="heat" role="img" aria-label="Distribuição da posição final de ${escapeHtml(team.name)}">${heat}</span></td>
        </tr>`;
      })
      .join("");
    return `
      <section id="tabela" aria-labelledby="tabela-titulo">
        <h2 id="tabela-titulo">Tabela e posição final provável</h2>
        <p class="section-note">Linhas de corte depois do ${direct}º (acesso direto), do ${playoffLast}º (playoff) e do ${safeLast}º (rebaixamento). A faixa à direita mostra a chance de cada posição final, do 1º ao 20º: quanto mais escura, mais provável.</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Tabela da Série B">
          <table>
            <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>V</th><th>E</th><th>D</th><th>SG</th><th>Pts esp.</th><th>Sobe</th><th>Cai</th><th class="left">Posição final (1º → 20º)</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
  }

  function matches(data, byId) {
    const items = [...data.remaining]
      .sort((a, b) => byId[a.home_id].position - byId[b.home_id].position)
      .map((match) => {
        const home = byId[match.home_id];
        const away = byId[match.away_id];
        const widths = [match.p_home, match.p_draw, match.p_away].map((value) => (value * 100).toFixed(1));
        return `<li>
          <div class="teams"><span>${escapeHtml(home.name)}</span><span>${escapeHtml(away.name)}</span></div>
          <div class="bar" role="img" aria-label="${escapeHtml(home.name)} ${pct(match.p_home)}, empate ${pct(match.p_draw)}, ${escapeHtml(away.name)} ${pct(match.p_away)}">
            <span class="h" style="width:${widths[0]}%"></span><span class="d" style="width:${widths[1]}%"></span><span class="a" style="width:${widths[2]}%"></span>
          </div>
          <div class="nums"><span>${pct(match.p_home)}</span><span>empate ${pct(match.p_draw)}</span><span>${pct(match.p_away)}</span></div>
        </li>`;
      })
      .join("");
    return `
      <section id="jogos" aria-labelledby="jogos-titulo">
        <h2 id="jogos-titulo">Os ${data.remaining.length} jogos que faltam</h2>
        <p class="section-note">Mandante à esquerda. A fonte não traz as datas, então os jogos aparecem pela posição do mandante na tabela.</p>
        <ul class="matches">${items}</ul>
      </section>`;
  }

  function method(data) {
    const backtest = data.backtest;
    const facts = backtest
      ? `<div class="facts">
          <div class="fact"><strong>${decimal.format(backtest.log_loss)}</strong><span>log loss do modelo em ${backtest.n_matches.toLocaleString("pt-BR")} jogos de ${backtest.test_seasons[0]} a ${backtest.test_seasons[backtest.test_seasons.length - 1]} (taxa base: ${decimal.format(backtest.log_loss_base_rate)}; menor é melhor)</span></div>
          <div class="fact"><strong>${decimal.format(backtest.late_top4_brier)}</strong><span>Brier de "4 primeiros" com ${38 - backtest.late_round} rodadas por jogar (chute fixo: ${decimal.format(backtest.climatology_brier)})</span></div>
          <div class="fact"><strong>${decimal.format(backtest.late_relegation_brier)}</strong><span>Brier do rebaixamento no mesmo ponto da temporada</span></div>
          <div class="fact"><strong>${Math.round(backtest.late_points_interval_90_coverage * 100)}%</strong><span>dos pontos finais caíram no intervalo de 90% previsto</span></div>
        </div>`
      : "";
    const sources = data.sources
      .map((source) => `<li><a href="${escapeHtml(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>, versão ${escapeHtml(source.version)}.</li>`)
      .join("");
    return `
      <section id="metodo" class="prose" aria-labelledby="metodo-titulo">
        <h2 id="metodo-titulo">Como calculamos</h2>
        <p>É o mesmo modelo da Série A do AInda dá?, com parâmetros calibrados nos jogos da própria Série B: força de cada clube (Elo, ataque e defesa) reconstruída jogo a jogo desde 2018, um modelo de gols treinado só com temporadas anteriores e ${data.n_simulations.toLocaleString("pt-BR")} simulações do que falta. Cada simulação termina a tabela com os critérios do regulamento e depois disputa os dois playoffs, ida e volta.</p>
        ${facts}
        <p>Limitações que você precisa saber:</p>
        <ul>${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
          <li>Quem não jogou a Série B no ano anterior (os rebaixados da Série A e os que subiram da Série C) começa a temporada com a força média dos clubes que deixaram a divisão. A força se ajusta jogo a jogo depois disso.</li>
          <li>"Subiu", "caiu" e "não dá mais" só aparecem quando a conta de pontos fecha, nunca por simulação.</li>
        </ul>
        <p>Regulamento: <a href="${escapeHtml(data.regulation.url)}">${escapeHtml(data.regulation.title)}</a>. Fontes:</p>
        <ul>${sources}</ul>
        <p class="meta">Modelo ${escapeHtml(data.model_version)} · dados ${escapeHtml(data.data_version)} · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
        <div id="metodo-elo"></div>
      </section>`;
  }

  function render(data) {
    const byId = Object.fromEntries(data.teams.map((team) => [team.club_id, team]));
    main.innerHTML = [hero(data), ladder(data), playoff(data, byId), relegation(data), table(data), matches(data, byId), method(data)].join("");
    if (window.AIndaDaMetodo) window.AIndaDaMetodo.render(document.getElementById("metodo-elo"), "serie-b");
    const credits = document.getElementById("credits");
    credits.innerHTML = `Fontes: ${data.sources
      .map((source) => `<a href="${escapeHtml(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`)
      .join("; ")}. Licenças: <a href="https://creativecommons.org/licenses/by-sa/4.0/deed.pt-br">CC BY-SA 4.0</a> e <a href="https://creativecommons.org/publicdomain/zero/1.0/deed.pt-br">CC0 1.0</a>.`;
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
