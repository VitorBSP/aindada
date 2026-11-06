"use strict";

// Mundial de LoL (ADR-0013) no desenho dos sites de competição (D-043): Início com a chave do mata-mata e os possíveis
// adversários de cada time, Fase suíça, Força das ligas e Como calculamos.
(function () {
  const S = window.AIndaDaSite;
  const { escapeHtml, pct, team } = S;
  const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const QUARTERS = "Knockout stage / Quarterfinals";
  const SEMIS = "Knockout stage / Semifinals";
  const FINAL = "Knockout stage / Final";

  const played = (series) => series.score1 !== null && series.score2 !== null;
  const winner = (series) => (series.score1 > series.score2 ? series.team1 : series.team2);
  const loser = (series) => (series.score1 > series.score2 ? series.team2 : series.team1);

  // Chave só com as 4 quartas definidas (sorteio feito); antes disso, a página mostra a corrida da fase suíça.
  const drawn = (quarters) => quarters.length === 4 && quarters.every((series) => series.team1 && series.team2);

  // Fase já alcançada por resultado jogado: venceu a série da fase anterior do mata-mata.
  function reached(data, id, key) {
    const previous = { semifinal: QUARTERS, final: SEMIS, champion: FINAL }[key];
    return Boolean(previous && (data.bracket || []).some((series) => series.stage === previous && played(series) && winner(series) === id));
  }

  function knockout(data) {
    const of = (stage) => (data.bracket || []).filter((series) => series.stage === stage);
    return { quarters: of(QUARTERS), semis: of(SEMIS), final: of(FINAL)[0] };
  }

  // Eliminado só por resultado já jogado (fase suíça ou mata-mata), nunca por simulação.
  function outIn(data, id) {
    const byId = Object.fromEntries(data.teams.map((item) => [item.team_id, item]));
    if (byId[id].status === "eliminated") return "fase suíça";
    const lost = (data.bracket || []).find((series) => played(series) && loser(series) === id);
    if (!lost) return null;
    return { [QUARTERS]: "quartas", [SEMIS]: "semifinal", [FINAL]: "final" }[lost.stage];
  }

  function edition(data) {
    const swissDone = data.teams.every((item) => item.status !== "alive");
    return `<p class="edition"><span class="edition-name">Edição de ${escapeHtml(S.formatDate(data.reference_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }))}</span> · ${escapeHtml(data.competition_name)} · ${swissDone ? "mata-mata" : "fase suíça"}</p>
      <p class="edition-facts"><strong>${data.n_simulations.toLocaleString("pt-BR")}</strong> simulações até a final</p>`;
  }

  // Um lado de uma série: time definido (com placar ou probabilidade) ou, se ainda não definido, os candidatos.
  function side(id, series, index, candidates) {
    if (!id) {
      const list = candidates.filter((item) => item.value > 0).sort((a, b) => b.value - a.value);
      return `<div class="tie-side open"><span>a definir</span><span></span></div>${list.length ? `<ul class="candidates">${list.map((item) => `<li>${team(item.id, 16)}<strong>${item.certain ? "classificado" : pct(item.value)}</strong></li>`).join("")}</ul>` : ""}`;
    }
    let right = "";
    let cls = "";
    if (series && played(series)) {
      right = `<span class="score">${index === 0 ? series.score1 : series.score2}</span>`;
      cls = winner(series) === id ? " won" : " lost";
    } else if (series && series.p_team1 !== null) {
      right = `<span class="chance">${pct(index === 0 ? series.p_team1 : 1 - series.p_team1)}</span>`;
    }
    return `<div class="tie-side${cls}">${team(id, 20)}${right}</div>`;
  }

  function tieHead(series, label) {
    return `<div class="tie-head"><span>${series ? escapeHtml(S.shortDate(series.match_date)) : ""}${label ? ` · ${label}` : ""}</span><b>MD5</b></div>`;
  }

  // Quem chega a uma vaga: o vencedor da série jogada, senão os dois times com a probabilidade de passar daquela fase.
  function feeders(data, seriesList, stageKey) {
    const byId = Object.fromEntries(data.teams.map((item) => [item.team_id, item]));
    // O vencedor de uma quarta já jogada está garantido na semifinal, não além dela.
    const sure = stageKey === "semifinal";
    return seriesList.flatMap((series) => (played(series) ? [[winner(series), sure]] : [[series.team1, false], [series.team2, false]]))
      .filter(([id]) => Boolean(id))
      .map(([id, certain]) => ({ id, value: certain ? 1 : byId[id].stages[stageKey], certain }))
      .sort((a, b) => b.value - a.value);
  }

  function bracket(data) {
    const { quarters, semis, final } = knockout(data);
    if (!drawn(quarters)) return "";
    const halves = [quarters.slice(0, 2), quarters.slice(2, 4)];
    const quarterBox = (series) => `<div class="tie">${tieHead(series, "quartas")}${side(series.team1, series, 0)}${side(series.team2, series, 1)}</div>`;
    const semiBox = (series, half) => {
      const pending = (index) => {
        const source = half[index];
        if (series && (index === 0 ? series.team1 : series.team2)) return side(index === 0 ? series.team1 : series.team2, series, index);
        if (played(source)) return side(winner(source), series && series.team1 && series.team2 ? series : null, index);
        return side(null, null, index, feeders(data, [source], "semifinal"));
      };
      return `<div class="tie">${tieHead(series, "semifinal")}${pending(0)}${pending(1)}</div>`;
    };
    const finalSide = (index) => {
      const id = final && (index === 0 ? final.team1 : final.team2);
      if (id) return side(id, final, index);
      const semi = semis[index];
      if (semi && played(semi)) return side(winner(semi), null, index);
      return side(null, null, index, feeders(data, halves[index], "final"));
    };
    return `
      <div class="bracket" style="--rounds:3">
        <div class="bracket-round"><h3>Quartas de final</h3>${quarters.map(quarterBox).join("")}</div>
        <div class="bracket-round"><h3>Semifinais</h3>${semiBox(semis[0], halves[0])}${semiBox(semis[1], halves[1])}</div>
        <div class="bracket-round"><h3>Final</h3><div class="tie">${tieHead(final, "final")}${finalSide(0)}${finalSide(1)}</div></div>
      </div>
      <p class="note">Quartas 1 e 2 formam a semifinal 1; quartas 3 e 4, a semifinal 2. Todas em melhor de 5. Ao lado de cada time ainda sem série jogada: probabilidade de vencer o confronto; nas vagas a definir, probabilidade de cada candidato chegar ali.</p>`;
  }

  // Possíveis adversários de cada time vivo no mata-mata: na semi (o outro confronto do mesmo lado) e na final (o outro lado).
  function rivals(data) {
    const { quarters } = knockout(data);
    if (!drawn(quarters)) return "";
    const byId = Object.fromEntries(data.teams.map((item) => [item.team_id, item]));
    const halves = [quarters.slice(0, 2), quarters.slice(2, 4)];
    const alive = data.teams.filter((item) => item.status === "qualified" && !outIn(data, item.team_id));
    const cards = alive
      .map((item) => {
        const half = halves.findIndex((pair) => pair.some((series) => series.team1 === item.team_id || series.team2 === item.team_id));
        if (half < 0) return null;
        const mine = halves[half].findIndex((series) => series.team1 === item.team_id || series.team2 === item.team_id);
        const semiRivals = feeders(data, [halves[half][1 - mine]], "semifinal");
        const finalRivals = feeders(data, halves[1 - half], "final").sort((a, b) => b.value - a.value);
        const list = (items) => items.filter((rival) => rival.value > 0).map((rival) => `<span>${team(rival.id, 16)}<strong>${rival.certain ? "classificado" : pct(rival.value)}</strong></span>`).join("") || "<span>—</span>";
        const inSemi = halves[half][mine].score1 !== null && halves[half][mine].score2 !== null;
        const reach = inSemi ? "já está na semifinal" : `chega em ${pct(byId[item.team_id].stages.semifinal)}`;
        return { item, html: `<article class="rival-card">
          <h3>${team(item.team_id, 28)}</h3>
          <dl>
            <dt>Semifinal: ${reach}. Adversário possível</dt><dd>${list(semiRivals)}</dd>
            <dt>Final: ${reached(data, item.team_id, "final") ? "já está na final" : `chega em ${pct(byId[item.team_id].stages.final)}`}. Adversário possível</dt><dd>${list(finalRivals)}</dd>
            <dt>Título</dt><dd><strong>${pct(byId[item.team_id].stages.champion)}</strong></dd>
          </dl>
        </article>` };
      })
      .filter(Boolean)
      .sort((a, b) => b.item.stages.semifinal - a.item.stages.semifinal || b.item.stages.champion - a.item.stages.champion)
      .map((card) => card.html)
      .join("");
    return `<h2>Quem cada time pode enfrentar</h2>
      <p class="note">Percentual de cada adversário: probabilidade de ele chegar àquela fase do mesmo lado (semifinal) ou do outro lado da chave (final).</p>
      <div class="rivals">${cards}</div>`;
  }

  function home(data) {
    const favorites = [...data.teams].sort((a, b) => b.stages.champion - a.stages.champion).filter((item) => item.stages.champion > 0).slice(0, 8);
    const leader = favorites[0];
    const { quarters } = knockout(data);
    const latest = [...quarters].reverse().find(played);
    const latestLine = latest ? ` ${escapeHtml(S.nameOf(winner(latest)))} venceu ${escapeHtml(S.nameOf(loser(latest)))} por ${Math.max(latest.score1, latest.score2)} a ${Math.min(latest.score1, latest.score2)} e está na semifinal.` : "";
    const swiss = data.teams.filter((item) => item.status === "alive").sort((a, b) => b.stages.qualify - a.stages.qualify);
    return `
      <h1>Quem ainda dá para ser campeão do mundo?</h1>
      <p class="lede"><strong>${escapeHtml(leader.name)}</strong> é quem mais leva o Mundial: título em ${pct(leader.stages.champion)} das simulações.${latestLine}</p>
      ${drawn(quarters) ? `<h2>Chave do mata-mata</h2>${bracket(data)}` : swiss.length ? `<h2>Vaga nas quartas</h2>${S.raceRows(swiss.map((item) => ({ id: item.team_id, value: item.stages.qualify })), "lib")}` : ""}
      <div class="races">
        <section class="race"><h3>Título</h3><p class="note">% das simulações em que é campeão</p>${S.raceRows(favorites.map((item) => ({ id: item.team_id, value: item.stages.champion })), "")}</section>
      </div>
      ${rivals(data)}`;
  }

  function swissTable(data) {
    const rows = [...data.teams]
      .sort((a, b) => b.swiss_wins - a.swiss_wins || a.swiss_losses - b.swiss_losses || b.stages.champion - a.stages.champion)
      .map((item) => {
        const out = outIn(data, item.team_id);
        const cell = (key) => {
          if (out && item.stages[key] === 0) return `<span class="status-out">—</span>`;
          if (key === "champion" && reached(data, item.team_id, key)) return "campeão";
          if ((key === "qualify" && item.status === "qualified") || reached(data, item.team_id, key)) return "classificado";
          return pct(item.stages[key]);
        };
        const zone = item.status === "qualified" ? "zone-lib" : item.status === "eliminated" ? "zone-z4" : "";
        return `<tr class="${zone}">
          <td class="left club">${team(item.team_id, 20)}</td>
          <td class="left">${escapeHtml(item.league)}</td>
          <td><strong>${item.swiss_wins}–${item.swiss_losses}</strong></td>
          <td class="left">${out ? `<span class="status-out">eliminado ${{ "fase suíça": "na fase suíça", quartas: "nas quartas", semifinal: "na semifinal", final: "na final" }[out]}</span>` : item.status === "qualified" ? "no mata-mata" : "na disputa"}</td>
          <td>${cell("qualify")}</td><td>${cell("semifinal")}</td><td>${cell("final")}</td><td>${cell("champion")}</td>
        </tr>`;
      })
      .join("");
    return `
      <h1 class="race-heading">Fase suíça e mata-mata</h1>
      <p class="note">Na fase suíça, quem chega a 3 vitórias vai às quartas e quem chega a 3 derrotas sai. Percentuais: em quantas simulações o time chega a cada fase.</p>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Times do Mundial">
        <table class="standings">
          <thead><tr><th class="left">Time</th><th class="left">Liga</th><th>Suíça (V–D)</th><th class="left">Situação</th><th>Quartas</th><th>Semi</th><th>Final</th><th>Título</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function leagues(data) {
    const strongest = Math.max(...Object.values(data.league_strength));
    const weakest = Math.min(...Object.values(data.league_strength));
    const rows = Object.entries(data.league_strength)
      .map(([league, value]) => `<div class="race-row"><strong>${escapeHtml(league)}</strong><div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${(((value - weakest) / Math.max(strongest - weakest, 1)) * 100).toFixed(1)}%"></div></div><span class="value">${value > 0 ? "+" : ""}${Math.round(value)}</span></div>`)
      .join("");
    return `
      <h1 class="race-heading">Força das ligas</h1>
      <p class="lede lede-method">Pontos de Elo de cada liga, aprendidos só nos confrontos entre regiões em MSI e Mundial. 100 pontos de diferença dão cerca de 64% de probabilidade de vencer um mapa.</p>
      ${rows}`;
  }

  function regression(value) {
    if (value >= 1) return "Na virada do ano, o ajuste dos times recomeça do zero e a força da liga continua.";
    if (value <= 0) return "O ajuste dos times passa de um ano para o outro, assim como a força da liga.";
    return `Na virada do ano, o ajuste dos times perde ${Math.round(value * 100)}% e a força da liga continua.`;
  }

  function method(data) {
    const backtest = data.backtest;
    const facts = backtest
      ? `<div class="stat-row">
          <div class="stat"><span class="label">Log loss por mapa</span><span class="big">${decimal.format(backtest.test.map_log_loss)}</span><span class="sub">${backtest.test.maps} mapas deste Mundial; moeda ${decimal.format(backtest.test.coin_log_loss)}</span></div>
          <div class="stat"><span class="label">Log loss por série</span><span class="big">${decimal.format(backtest.test.series_log_loss)}</span><span class="sub">${backtest.test.series} séries deste Mundial; moeda ${decimal.format(backtest.test.coin_log_loss)}</span></div>
          <div class="stat"><span class="label">Validação, por mapa</span><span class="big">${decimal.format(backtest.validation.map_log_loss)}</span><span class="sub">${backtest.validation.maps} mapas do Mundial 2025 e do MSI 2026</span></div>
        </div>`
      : "";
    const sources = data.sources
      .map((source) => `<li><a href="${S.safeUrl(source.origin)}">${escapeHtml(source.attribution)}</a>, revisão ${escapeHtml(source.version.split("-r").pop())}.</li>`)
      .join("");
    return `
      <h1 class="race-heading">Como calculamos</h1>
      <p>Times de regiões diferentes quase nunca se enfrentam fora de MSI e Mundial. Por isso a força de cada time tem duas partes: a força da liga (LCK, LPL, LEC…) mais um ajuste do time dentro dela. Cada série muda os dois ajustes pela surpresa em mapas: mapas vencidos menos os que o modelo esperava. Quando as ligas são diferentes, a força das duas ligas também muda (K = ${number.format(data.params.k_league)}; ajuste do time: K = ${number.format(data.params.k_team)}). ${regression(data.params.team_regression)}</p>
      <p>A diferença de força dá a probabilidade de vencer um mapa; com mapas independentes, ela vira a probabilidade de vencer uma melhor de 1, de 3 ou de 5. Cada uma das ${data.n_simulations.toLocaleString("pt-BR")} simulações termina a fase suíça, sorteia as quartas com a regra do torneio (os dois times 3–0 em lados opostos, contra times 3–2) e joga o mata-mata até a final. Série já jogada entra com o resultado real.</p>
      <h2>Acerto</h2>
      ${facts}
      <p class="note">Menor é melhor. O teste é curto: poucos mapas do próprio Mundial 2026.</p>
      <h2>Limitações</h2>
      <ul class="summary-list">${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>
      <h2>Fontes</h2>
      <p>Texto sob CC BY-SA 4.0; os resultados vêm destas revisões:</p>
      <ul class="summary-list">${sources}</ul>
      <p class="note">Modelo ${escapeHtml(data.model_version)} · dados <code class="data-version">${escapeHtml(data.data_version)}</code> · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>`;
  }

  S.start({
    names: (data) => {
      document.getElementById("notice").textContent = data.notice;
      return Object.fromEntries(data.teams.map((item) => [item.team_id, item.name]));
    },
    edition,
    footer: (data) => {
      const latest = data.sources[data.sources.length - 1];
      return `Resultados: <a href="${S.safeUrl(latest.origin)}">colaboradores da Wikipédia em inglês</a> (CC BY-SA 4.0).`;
    },
    routes: [
      { id: "", label: "Início", render: home },
      { id: "times", label: "Times", render: swissTable },
      { id: "ligas", label: "Força das ligas", render: leagues },
      { id: "metodologia", label: "Como calculamos", render: method },
    ],
  });
})();
