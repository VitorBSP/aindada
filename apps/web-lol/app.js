"use strict";

(function () {
  const main = document.getElementById("main");
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const STAGES = [
    ["qualify", "Quartas"],
    ["semifinal", "Semi"],
    ["final", "Final"],
    ["champion", "Título"],
  ];
  const STATUS = { qualified: "classificado", eliminated: "eliminado" };
  const ROUND = { "Swiss stage": "fase suíça", "Knockout stage / Quarterfinals": "quartas de final", "Knockout stage / Semifinals": "semifinal", "Knockout stage / Final": "final" };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  // Certeza só quando a campanha decide (status); simulação nunca vira certeza (CONTENT_GUIDELINES).
  function pct(value) {
    if (value === 0) return "0%";
    if (value < 0.001) return "<0,1%";
    if (value > 0.999) return ">99,9%";
    if (value < 0.01 || value > 0.99) return number.format(Math.round(value * 1000) / 10) + "%";
    return Math.round(value * 100) + "%";
  }

  function stageCell(team, key) {
    if (team.status === "eliminated") return "—";
    if (key === "qualify" && team.status === "qualified") return STATUS.qualified;
    return pct(team.stages[key]);
  }

  function formatDate(iso) {
    const [year, month, day] = iso.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" });
  }

  function shortDate(iso) {
    const [year, month, day] = iso.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("pt-BR", { weekday: "short", day: "numeric", month: "short" });
  }

  function stageName(stage) {
    const key = Object.keys(ROUND).find((prefix) => stage.startsWith(prefix));
    const round = stage.match(/Round (\d)/);
    return key === "Swiss stage" && round ? `${ROUND[key]}, rodada ${round[1]}` : ROUND[key] || stage;
  }

  function badge(team) {
    return `<span class="badge" aria-hidden="true">${escapeHtml(team.short_name)}</span>`;
  }

  function teamLabel(team) {
    return `${escapeHtml(team.name)}<span class="country">${escapeHtml(team.league)}</span>`;
  }

  function hero(data) {
    const favorites = [...data.teams].sort((a, b) => b.stages.champion - a.stages.champion);
    const leader = favorites[0];
    const alive = data.teams.filter((team) => team.status === "alive").sort((a, b) => b.stages.qualify - a.stages.qualify);
    const card = (title, sub, teams, value) => `<div class="zone up"><h3>${title}</h3><p class="zone-sub">${sub}</p><ol>${teams
      .map((team) => `<li>${badge(team)}<span class="name">${escapeHtml(team.name)}</span><span class="value">${value(team)}</span></li>`)
      .join("")}</ol></div>`;
    const swissCard = alive.length
      ? card("Vaga nas quartas", "% das simulações em que chega a 3 vitórias na fase suíça", alive.slice(0, 6), (team) => pct(team.stages.qualify))
      : "";
    return `
      <section aria-labelledby="titulo">
        <p class="kicker">${escapeHtml(data.competition_name)}</p>
        <h1 id="titulo">Quem ainda dá para ser campeão do mundo?</h1>
        <p class="lede">${escapeHtml(leader.name)} é quem mais leva o Mundial: título em ${pct(leader.stages.champion)} das simulações. Jogamos o que falta da fase suíça e cada série do mata-mata, em ${data.n_simulations.toLocaleString("pt-BR")} simulações.</p>
        <p class="meta">Resultados até ${formatDate(data.reference_date)}</p>
        <div class="zones">
          ${card("Título", "% das simulações em que é campeão", favorites.slice(0, 6), (team) => pct(team.stages.champion))}
          ${card("Final", "% das simulações em que chega à final", [...data.teams].sort((a, b) => b.stages.final - a.stages.final).slice(0, 6), (team) => pct(team.stages.final))}
          ${swissCard}
        </div>
      </section>`;
  }

  function path(data) {
    const rows = data.teams
      .map((team) => `<tr>
        <td class="left"><span class="club-cell">${badge(team)}${teamLabel(team)}</span></td>
        <td>${team.swiss_wins}–${team.swiss_losses}</td>
        ${STAGES.map(([key]) => `<td class="stage${team.stages[key] >= 0.5 && team.status !== "eliminated" ? " strong" : ""}">${stageCell(team, key)}</td>`).join("")}
      </tr>`)
      .join("");
    return `
      <section id="caminho" class="path" aria-labelledby="caminho-titulo">
        <h2 id="caminho-titulo">O caminho até a final</h2>
        <p class="section-note">Na fase suíça, quem chega a 3 vitórias vai às quartas e quem chega a 3 derrotas sai. Do mata-mata em diante, todas as séries são em melhor de 5. Percentuais: em quantas simulações o time chega a cada fase.</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Chance de cada time por fase">
          <table>
            <thead><tr><th class="left">Time</th><th>Suíça (V–D)</th>${STAGES.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
  }

  function upcoming(data, byId) {
    if (!data.upcoming.length) return "";
    const items = data.upcoming
      .map((series) => {
        const first = byId[series.team1];
        const second = byId[series.team2];
        const widths = [series.p_team1, 1 - series.p_team1].map((value) => (value * 100).toFixed(1));
        return `<li>
          <div class="when">${escapeHtml(shortDate(series.match_date))} · ${escapeHtml(stageName(series.stage))} · melhor de ${series.best_of}</div>
          <div class="teams"><span>${escapeHtml(first.name)}</span><span>${escapeHtml(second.name)}</span></div>
          <div class="bar" role="img" aria-label="${escapeHtml(first.name)} ${pct(series.p_team1)}, ${escapeHtml(second.name)} ${pct(1 - series.p_team1)}">
            <span class="h" style="width:${widths[0]}%"></span><span class="a" style="width:${widths[1]}%"></span>
          </div>
          <div class="nums"><span>${pct(series.p_team1)}</span><span>${pct(1 - series.p_team1)}</span></div>
        </li>`;
      })
      .join("");
    return `
      <section id="jogos" aria-labelledby="jogos-titulo">
        <h2 id="jogos-titulo">Próximas séries</h2>
        <div class="round-head"><h3>Confrontos já definidos</h3><span class="meta">chance de vencer a série</span></div>
        <ul class="matches">${items}</ul>
      </section>`;
  }

  function leagues(data) {
    const rows = Object.entries(data.league_strength)
      .map(([league, value]) => `<tr><td class="left">${escapeHtml(league)}</td><td>${value > 0 ? "+" : ""}${Math.round(value)}</td></tr>`)
      .join("");
    return `
      <section id="ligas" aria-labelledby="ligas-titulo">
        <h2 id="ligas-titulo">Força das ligas</h2>
        <p class="section-note">Pontos de Elo de cada liga, aprendidos só nos confrontos entre regiões em MSI e Mundial. 100 pontos de diferença dão cerca de 64% de chance de vencer um mapa.</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="Força de cada liga">
          <table><thead><tr><th class="left">Liga</th><th>Elo da liga</th></tr></thead><tbody>${rows}</tbody></table>
        </div>
      </section>`;
  }

  function regression(value) {
    if (value >= 1) return "Na virada do ano, o ajuste dos times recomeça do zero e a força da liga continua.";
    if (value <= 0) return "O ajuste dos times passa de um ano para o outro, assim como a força da liga.";
    return `Na virada do ano, o ajuste dos times perde ${Math.round(value * 100)}% e a força da liga continua.`;
  }

  function method(data) {
    const backtest = data.backtest;
    const facts = backtest
      ? `<div class="facts">
          <div class="fact"><strong>${decimal.format(backtest.test.map_log_loss)}</strong><span>log loss por mapa em ${backtest.test.maps} mapas já jogados deste Mundial (moeda: ${decimal.format(backtest.test.coin_log_loss)}; menor é melhor)</span></div>
          <div class="fact"><strong>${decimal.format(backtest.test.series_log_loss)}</strong><span>log loss por série em ${backtest.test.series} séries deste Mundial (moeda: ${decimal.format(backtest.test.coin_log_loss)})</span></div>
          <div class="fact"><strong>${decimal.format(backtest.validation.map_log_loss)}</strong><span>log loss por mapa na validação, ${backtest.validation.maps} mapas do Mundial 2025 e do MSI 2026, onde os parâmetros foram escolhidos</span></div>
        </div>`
      : "";
    const sources = data.sources
      .map((source) => `<li><a href="${escapeHtml(source.origin)}">${escapeHtml(source.attribution)}</a>, revisão ${escapeHtml(source.version.split("-r").pop())}.</li>`)
      .join("");
    return `
      <section id="metodo" class="prose" aria-labelledby="metodo-titulo">
        <h2 id="metodo-titulo">Como calculamos</h2>
        <p>Times de regiões diferentes quase nunca se enfrentam fora de MSI e Mundial. Por isso a força de cada time tem duas partes: a força da liga (LCK, LPL, LEC…) mais um ajuste do time dentro dela. Cada série muda os dois ajustes pela surpresa em mapas: mapas vencidos menos os que o modelo esperava. Quando as ligas são diferentes, a força das duas ligas também muda (K = ${number.format(data.params.k_league)}; ajuste do time: K = ${number.format(data.params.k_team)}). ${regression(data.params.team_regression)}</p>
        <p>A diferença de força dá a chance de vencer um mapa; com mapas independentes, ela vira a chance de vencer uma melhor de 1, de 3 ou de 5. Cada uma das ${data.n_simulations.toLocaleString("pt-BR")} simulações termina a fase suíça, sorteia as quartas com a regra do torneio (os dois times 3–0 em lados opostos, contra times 3–2) e joga o mata-mata até a final.</p>
        ${facts}
        <p>Limitações que você precisa saber:</p>
        <ul>${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>
        <p>Fontes (texto sob CC BY-SA 4.0; os resultados vêm destas revisões):</p>
        <ul>${sources}</ul>
        <p class="meta">Modelo ${escapeHtml(data.model_version)} · dados ${escapeHtml(data.data_version)} · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
      </section>`;
  }

  function render(data) {
    const byId = Object.fromEntries(data.teams.map((team) => [team.team_id, team]));
    main.innerHTML = [hero(data), path(data), upcoming(data, byId), leagues(data), method(data)].join("");
    document.getElementById("notice").textContent = data.notice;
    const latest = data.sources[data.sources.length - 1];
    document.getElementById("credits").innerHTML = `Resultados: <a href="${escapeHtml(latest.origin)}">colaboradores da Wikipédia em inglês</a> (CC BY-SA 4.0).`;
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
