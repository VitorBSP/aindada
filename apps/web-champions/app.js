"use strict";

(function () {
  const main = document.getElementById("main");
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

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  // Certeza só quando a aritmética decide (clinched); simulação nunca vira certeza (CONTENT_GUIDELINES).
  function pct(value, state, zone) {
    if (state && zone) return DONE[zone][state];
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

  // "out" no playoff vale para quem já garantiu o top 8 e para quem já caiu: o texto diz qual dos dois.
  function playoffLabel(club) {
    if (club.clinched.playoff === "out") return club.clinched.top8 === "in" ? "já nas oitavas" : "eliminado";
    return pct(club.zones.playoff, club.clinched.playoff, "playoff");
  }

  function badge(club) {
    return `<span class="badge" aria-hidden="true">${escapeHtml(club.short_name)}</span>`;
  }

  function clubLabel(club) {
    return `${escapeHtml(club.name)}<span class="country">${escapeHtml(club.country)}</span>`;
  }

  function hero(data) {
    const favorites = [...data.clubs].sort((a, b) => b.stages.winner - a.stages.winner);
    const leader = favorites[0];
    const matchday = Math.max(...data.clubs.map((club) => club.played));
    const card = (title, sub, clubs, value) => `<div class="zone up"><h3>${title}</h3><p class="zone-sub">${sub}</p><ol>${clubs
      .map((club) => `<li>${badge(club)}<span class="name">${escapeHtml(club.name)}</span><span class="value">${value(club)}</span></li>`)
      .join("")}</ol></div>`;
    const byTop8 = [...data.clubs].filter((club) => club.clinched.top8 !== "out").sort((a, b) => b.zones.top8 - a.zones.top8).slice(0, 6);
    const byOut = [...data.clubs].filter((club) => club.clinched.out !== "out").sort((a, b) => b.zones.out - a.zones.out).slice(0, 6);
    return `
      <section aria-labelledby="titulo">
        <p class="kicker">${escapeHtml(data.competition_name)} · fase de liga, ${matchday} de 8 rodadas</p>
        <h1 id="titulo">Quem ainda dá para levantar a taça?</h1>
        <p class="lede">${escapeHtml(leader.name)} é quem mais ganha a Champions: título em ${pct(leader.stages.winner)} das simulações. Contamos a fase de liga, o playoff e cada mata-mata até a final, em ${data.n_simulations.toLocaleString("pt-BR")} simulações.</p>
        <p class="meta">Resultados até ${formatDate(data.reference_date)}</p>
        <div class="zones">
          ${card("Título", "% das simulações em que é campeão", favorites.slice(0, 6), (club) => pct(club.stages.winner))}
          ${card("Direto às oitavas", "% das simulações em que termina entre 1º e 8º", byTop8, (club) => pct(club.zones.top8, club.clinched.top8, "top8"))}
          ${card("Eliminado na fase de liga", "% das simulações em que termina entre 25º e 36º", byOut, (club) => pct(club.zones.out, club.clinched.out, "out"))}
        </div>
      </section>`;
  }

  function path(data) {
    const rows = [...data.clubs]
      .sort((a, b) => b.stages.winner - a.stages.winner || b.stages.round_of_16 - a.stages.round_of_16)
      .map((club) => `<tr>
        <td class="left"><span class="club-cell">${badge(club)}${clubLabel(club)}</span></td>
        <td>${pct(club.zones.top8, club.clinched.top8, "top8")}</td>
        <td>${playoffLabel(club)}</td>
        ${STAGES.map(([key]) => `<td class="stage${club.stages[key] >= 0.5 ? " strong" : ""}">${pct(club.stages[key])}</td>`).join("")}
      </tr>`)
      .join("");
    return `
      <section id="caminho" class="path" aria-labelledby="caminho-titulo">
        <h2 id="caminho-titulo">O caminho até a final</h2>
        <p class="section-note">Do 1º ao 8º vão direto às oitavas; do 9º ao 24º jogam o playoff de ida e volta; do 25º em diante saem. Percentuais: em quantas simulações o clube chega a cada fase. As oitavas somam quem foi direto e quem passou no playoff.</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Chance de cada clube por fase">
          <table>
            <thead><tr><th class="left">Clube</th><th>Top 8</th><th>Playoff</th>${STAGES.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
  }

  function table(data) {
    const rows = data.clubs
      .map((club) => {
        const heat = club.position_probabilities
          .map((value, index) => `<i style="opacity:${value === 0 ? 0.06 : (0.12 + 0.88 * Math.min(1, value * 2.5)).toFixed(2)}" title="${index + 1}º: ${pct(value)}"></i>`)
          .join("");
        const goalDifference = club.goals_for - club.goals_against;
        const cut = club.position === 8 ? "cut-direct" : club.position === 24 ? "cut-safe" : "";
        return `<tr class="${cut}">
          <td>${club.position}</td>
          <td class="left"><span class="club-cell">${badge(club)}${clubLabel(club)}</span></td>
          <td class="pts">${club.points}</td><td>${club.played}</td><td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td><td>${club.goals_for}</td>
          <td>${number.format(club.expected_points)}</td>
          <td class="left"><span class="heat heat-36" role="img" aria-label="Distribuição da posição final de ${escapeHtml(club.name)}">${heat}</span></td>
        </tr>`;
      })
      .join("");
    return `
      <section id="tabela" aria-labelledby="tabela-titulo">
        <h2 id="tabela-titulo">Fase de liga</h2>
        <p class="section-note">Ordem atual por pontos, saldo e gols. Linhas de corte depois do 8º (oitavas) e do 24º (playoff). A faixa à direita mostra a chance de cada posição final, do 1º ao 36º.</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Tabela da fase de liga">
          <table>
            <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th>J</th><th>SG</th><th>GP</th><th>Pts esp.</th><th class="left">Posição final (1º → 36º)</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
  }

  function nextRound(data, byId) {
    if (!data.remaining.length) return "";
    const round = Math.min(...data.remaining.filter((match) => match.round !== null).map((match) => match.round));
    const items = data.remaining
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
    return `
      <section id="jogos" aria-labelledby="jogos-titulo">
        <h2 id="jogos-titulo">Próxima rodada</h2>
        <div class="round-head"><h3>Rodada ${round} da fase de liga</h3><span class="meta">mandante à esquerda; chance de vitória, empate e derrota</span></div>
        <ul class="matches">${items}</ul>
      </section>`;
  }

  function method(data) {
    const backtest = data.backtest;
    const seasons = backtest ? backtest.test_seasons.map((season) => `${season}/${String(season + 1).slice(2)}`).join(" e ") : "";
    const facts = backtest
      ? `<div class="facts">
          <div class="fact"><strong>${decimal.format(backtest.log_loss)}</strong><span>log loss do modelo em ${backtest.n_matches} jogos da Champions de ${seasons} (taxa base: ${decimal.format(backtest.log_loss_base_rate)}; menor é melhor)</span></div>
          <div class="fact"><strong>${decimal.format(backtest.top8_brier)}</strong><span>Brier do top 8 com ${8 - backtest.late_matchday} rodadas por jogar (só a proporção: ${decimal.format(backtest.top8_brier_base)})</span></div>
          <div class="fact"><strong>${decimal.format(backtest.quarter_finals_brier)}</strong><span>Brier de quem chega às quartas, no mesmo ponto (só a proporção: ${decimal.format(backtest.quarter_finals_brier_base)})</span></div>
          <div class="fact"><strong>${decimal.format(backtest.winner_log_loss)}</strong><span>log loss do campeão (chute uniforme: ${decimal.format(backtest.winner_log_loss_uniform)}); só duas temporadas, número muito instável</span></div>
        </div>`
      : "";
    const sources = data.sources
      .map((source) => `<li><a href="${escapeHtml(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>, versão ${escapeHtml(source.version)}.</li>`)
      .join("");
    return `
      <section id="metodo" class="prose" aria-labelledby="metodo-titulo">
        <h2 id="metodo-titulo">Como calculamos</h2>
        <p>Na Champions, os clubes vêm de ligas diferentes. Por isso usamos uma força única (Elo) para todos, calculada com as sete principais ligas da Europa e com a Champions, a Liga Europa e a Conference desde 2021/22: as copas europeias ligam as ligas entre si. Um modelo de gols treinado só com jogos europeus de temporadas anteriores transforma a diferença de força em placares. Cada uma das ${data.n_simulations.toLocaleString("pt-BR")} simulações termina a fase de liga com os critérios de desempate da UEFA e joga o mata-mata com o chaveamento do regulamento, até a final.</p>
        ${facts}
        <p>Limitações que você precisa saber:</p>
        <ul>${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
          <li>Clubes de ligas fora das sete principais têm força medida só pelos jogos europeus; os que nunca jogaram copas europeias desde 2021/22 começam de um valor fixo.</li>
          <li>"Garantido", "não dá mais", "eliminado" e "não cai mais" só aparecem quando a conta de pontos fecha, nunca por simulação.</li>
        </ul>
        <p>Regulamento: <a href="${escapeHtml(data.regulation.url)}">${escapeHtml(data.regulation.title)}</a>. Fontes:</p>
        <ul>${sources}</ul>
        <p class="meta">Modelo ${escapeHtml(data.model_version)} · dados ${escapeHtml(data.data_version)} · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
        <div id="metodo-elo"></div>
      </section>`;
  }

  function render(data) {
    const byId = Object.fromEntries(data.clubs.map((club) => [club.club_id, club]));
    document.getElementById("league-tag").textContent = "Champions League";
    document.querySelectorAll("#leagues a[data-league]").forEach((link) => {
      if (link.dataset.league === data.competition) link.setAttribute("aria-current", "page");
    });
    main.innerHTML = [hero(data), path(data), table(data), nextRound(data, byId), method(data)].join("");
    if (window.AIndaDaMetodo) window.AIndaDaMetodo.render(document.getElementById("metodo-elo"), data.competition);
    const credits = [...new Map(data.sources.map((source) => [source.attribution, source])).values()];
    document.getElementById("credits").innerHTML = `Fontes: ${credits
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
