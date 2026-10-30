"use strict";

// Como o Elo é calculado e o que muda em cada competição (D-040). Compartilhado pelos sites de todas as
// competições; os números vêm de methods.json, gerado das configurações versionadas (python -m brasileirao.methods).
(function () {
  const script = document.currentScript;
  const base = script ? new URL(".", script.src) : new URL("assets/", location.href);
  const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
  const percent = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  const ELO_TEXT = `
    <h3 class="elo-title">Como o Elo é calculado</h3>
    <p>Cada clube tem um número de força, o Elo. Antes de cada jogo, a diferença entre os dois (somando ao mandante a vantagem de jogar em casa, <em>H</em>) vira um resultado esperado entre 0 e 1:</p>
    <p class="formula">esperado do mandante = 1 / (1 + 10<sup>−(Elo mandante + H − Elo visitante) / 400</sup>)</p>
    <p>Depois do jogo, o mandante ganha ou perde pontos de Elo conforme o resultado ficou acima ou abaixo do esperado, e o visitante recebe o oposto:</p>
    <p class="formula">variação = K × M × (resultado − esperado)</p>
    <p>O resultado vale 1 na vitória, 0,5 no empate e 0 na derrota. <em>K</em> controla a velocidade da mudança. <em>M</em> pesa o placar: 1 para vitória por um gol, 1,5 por dois e (11 + diferença) / 8 a partir de três. Entre uma temporada e outra, cada clube volta uma parte (<em>regressão</em>) do caminho até a média, porque elencos mudam. A diferença de Elo, junto com outros indicadores, entra num modelo de gols que dá a chance de cada placar, e cada simulação sorteia os jogos que faltam.</p>`;

  // Exemplos com jogos reais (data/elo-examples.json de cada site, gerado junto com a previsão; fora do git).
  // Um confronto direto por competição e, para cada lado, de onde vem o Elo antes do jogo.
  const examplesCache = {};
  const whole = (value) => Math.round(value).toLocaleString("pt-BR");
  const fixed = (value, digits) => value.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const signed = (value, digits = 1) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${fixed(Math.abs(value), digits)}`;
  const shortDate = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { day: "numeric", month: "short", year: "numeric" });
  const dayMonth = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const plural = (count, one, many) => `${count.toLocaleString("pt-BR")} ${count === 1 ? one : many}`;
  const RESULT_WORDS = { 1: "vitória do mandante = 1", 0.5: "empate = 0,5", 0: "derrota do mandante = 0" };
  const VENUE = { home: "em casa", away: "fora", neutral: "campo neutro" };

  function loadExamples(competition) {
    if (!examplesCache[competition.id]) {
      examplesCache[competition.id] = fetch(new URL(`${competition.path}data/elo-examples.json`, new URL("..", base)), { cache: "no-cache" })
        .then((response) => (response.ok ? response.json() : null))
        .then((data) => (data && data.competitions ? data.competitions.find((item) => item.id === competition.id) || null : null))
        .catch(() => null);
    }
    return examplesCache[competition.id];
  }

  function newcomerText(rule) {
    if (rule.rule === "leavers_mean") {
      const names = rule.leavers.map((club) => escapeHtml(club.name));
      const value = rule.offset ? `${whole(rule.base)} ${signed(rule.offset, 0)} de ajuste = <strong>${whole(rule.elo)}</strong>` : `<strong>${whole(rule.elo)}</strong>`;
      return `chegou de outra divisão e entrou com a média do Elo dos ${names.length} clubes que tinham saído (${names.join(", ")}): ${value}`;
    }
    if (rule.rule === "country_mean") return `estreou e entrou com a média do Elo dos clubes do país dele: <strong>${whole(rule.elo)}</strong>`;
    if (rule.rule === "unknown_country") return `estreou sem histórico do país e entrou com o Elo inicial ${whole(rule.base)}${rule.offset ? ` ${signed(rule.offset, 0)} de ajuste` : ""} = <strong>${whole(rule.elo)}</strong>`;
    return `entrou na base de dados com o Elo inicial: <strong>${whole(rule.elo)}</strong>`;
  }

  const seasonLabel = (ledger, season) => (ledger.seasons.find((item) => item.season === season) || { label: String(season) }).label;

  function previousText(example, ledger) {
    const season = ledger.current.season - 1;
    const row = ledger.seasons.find((item) => item.season === season);
    if (!row) return "";
    const stats = example.previous_season && example.previous_season.season === season ? example.previous_season : null;
    const place = stats && stats.position ? `${stats.position}º de ${stats.n_clubs}${stats.points !== null ? `, ${stats.points} pontos` : ""}; ` : "";
    return `<p><strong>Em ${escapeHtml(row.label)}:</strong> ${place}${plural(row.matches, "jogo", "jogos")}, saldo de ${signed(row.net)}. O Elo foi de ${whole(row.entry_elo)} para <strong>${whole(row.end_elo)}</strong>.</p>`;
  }

  function entryText(example, ledger) {
    const entry = ledger.current.entry;
    const label = escapeHtml(ledger.current.label);
    if (entry.newcomer && entry.newcomer_rule) return `<p><strong>Começo de ${label}:</strong> ${escapeHtml(example.name)} ${newcomerText(entry.newcomer_rule)}.</p>`;
    const target = entry.recentered_to ?? entry.reference_mean;
    const meanLabel = entry.reference_mean_kind === "country" ? "a média dos clubes do país" : "a média da liga";
    return `<p><strong>Começo de ${label}:</strong> o Elo volta ${fixed(entry.regression * 100, 0)}% do caminho até ${meanLabel}, porque elencos mudam.</p>
      <p class="formula">${whole(target)} + (${whole(entry.before)} − ${whole(entry.reference_mean)}) × ${fixed(1 - entry.regression, 2)} = <strong>${whole(entry.after)}</strong></p>`;
  }

  function matchesTable(ledger) {
    const rows = ledger.current.matches_until.map((item) => {
      const home = item.venue !== "away";
      const score = home ? `${item.home_goals} × ${item.away_goals}` : `${item.away_goals} × ${item.home_goals}`;
      const date = `${dayMonth(item.date)}${item.date_is_approximate ? "*" : ""}`;
      return `<tr><td class="left">${date}</td><td class="left">${escapeHtml(item.opponent_name)} <span class="elo-venue">${VENUE[item.venue] || ""}${item.competition ? ` · ${escapeHtml(item.competition)}` : ""}</span></td><td>${score}</td><td class="${item.delta >= 0 ? "elo-up" : "elo-down"}">${signed(item.delta)}</td><td>${whole(item.elo_after)}</td></tr>`;
    }).join("");
    const approximate = ledger.current.matches_until.some((item) => item.date_is_approximate);
    return `<details class="elo-details"><summary>Ver os ${plural(ledger.current.matches_until.length, "jogo", "jogos")}</summary>
      <div class="table-scroll"><table class="elo-table"><thead><tr><th class="left">Data</th><th class="left">Adversário</th><th>Placar</th><th>Variação</th><th>Elo</th></tr></thead><tbody>${rows}</tbody></table></div>
      ${approximate ? `<p class="note">* Data aproximada: a fonte não traz datas desta temporada.</p>` : ""}</details>`;
  }

  function weightsTable(example, ledger) {
    const weights = ledger.weights;
    const keep = fixed(1 - weights.regression, 2);
    const rows = weights.seasons.map((item) => `<tr><td class="left">${escapeHtml(seasonLabel(ledger, item.season))}${item.season === ledger.current.season ? " (até o jogo)" : ""}</td><td>${signed(item.net)}</td><td>${fixed(item.weight, 2)}</td><td>${signed(item.contribution)}</td></tr>`);
    if (weights.older && weights.older.n_seasons) {
      rows.push(`<tr><td class="left">${escapeHtml(seasonLabel(ledger, weights.older.first_season))} a ${escapeHtml(seasonLabel(ledger, weights.older.last_season))}</td><td>${signed(weights.older.net)}</td><td>menor</td><td>${signed(weights.older.contribution)}</td></tr>`);
    }
    const start = weights.starting_point;
    if (start && Math.abs(start.contribution) >= 0.05) {
      rows.push(`<tr><td class="left">Ponto de partida: entrou em ${escapeHtml(seasonLabel(ledger, start.season))} com ${whole(start.entry_elo)}</td><td>${signed(start.entry_elo - weights.anchor)}</td><td>${fixed(start.weight, 2)}</td><td>${signed(start.contribution)}</td></tr>`);
    }
    const gap = weights.exact - weights.approx_total;
    const closing = Math.abs(gap) < 0.5
      ? `${whole(weights.anchor)} + soma = <strong>${whole(weights.approx_total)}</strong>, o Elo do clube antes do jogo.`
      : `${whole(weights.anchor)} + soma = ${whole(weights.approx_total)}; o Elo real era ${whole(weights.exact)}. A diferença (${signed(gap)}) vem da média de cada país, que também se move de um ano para o outro.`;
    return `<details class="elo-details"><summary>Quanto cada temporada pesa nesse número</summary>
      <p>A cada virada de temporada, a distância até a média encolhe para ${keep} do que era. Por isso um ano bom ou ruim pesa inteiro na hora, ${keep} no ano seguinte, ${fixed((1 - weights.regression) ** 2, 2)} no outro, e vai sumindo.</p>
      <div class="table-scroll"><table class="elo-table"><thead><tr><th class="left">Temporada</th><th>Saldo</th><th>Peso</th><th>Conta hoje</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>
      <p>${closing}</p></details>`;
  }

  function sideCard(example) {
    const ledger = example.ledger;
    const current = ledger.current;
    return `<article class="elo-example">
      <h5>${escapeHtml(example.name)}${example.country ? ` <span class="elo-country">${escapeHtml(example.country)}</span>` : ""} chegou com <strong>${whole(current.elo_before_match)}</strong></h5>
      ${previousText(example, ledger)}
      ${entryText(example, ledger)}
      <p><strong>${escapeHtml(current.label)} até o jogo:</strong> ${plural(current.matches_until.length, "jogo", "jogos")}, saldo de ${signed(current.net_until)}: ${whole(current.entry.after)} → <strong>${whole(current.elo_before_match)}</strong>.</p>
      ${current.matches_until.length ? matchesTable(ledger) : ""}
      ${weightsTable(example, ledger)}
    </article>`;
  }

  function matchSteps(match) {
    const home = match.home, away = match.away;
    const goalDiff = Math.abs(match.home_goals - match.away_goals);
    const multiplier = goalDiff <= 1 ? "1 (empate ou um gol de diferença)" : goalDiff === 2 ? "1,5 (dois gols de diferença)" : `(11 + ${goalDiff}) / 8 = ${fixed(match.goal_difference_multiplier, 3)}`;
    const venue = match.neutral ? "em campo neutro, sem mando" : `mando H = ${whole(match.home_advantage)}`;
    return `<h5 class="elo-match-title">A conta do jogo</h5>
      <ol class="elo-steps">
        <li>Esperado do mandante, com ${venue}: 1 / (1 + 10<sup>−(${whole(home.elo_before)} + ${whole(match.neutral ? 0 : match.home_advantage)} − ${whole(away.elo_before)}) / 400</sup>) = <strong>${fixed(match.expected_home, 2)}</strong></li>
        <li>Resultado: ${RESULT_WORDS[match.result_home] || fixed(match.result_home, 1)}</li>
        <li>Peso do placar: M = ${multiplier}</li>
        <li>Variação do mandante: ${fixed(match.k_factor, 0)} × ${fixed(match.goal_difference_multiplier, 2)} × (${fixed(match.result_home, 1)} − ${fixed(match.expected_home, 2)}) = <strong>${signed(match.delta_home)}</strong>; o visitante recebe o oposto.</li>
      </ol>
      <p>Depois do jogo: ${escapeHtml(home.name)} ${whole(home.elo_before)} → <strong>${whole(home.elo_after)}</strong> · ${escapeHtml(away.name)} ${whole(away.elo_before)} → <strong>${whole(away.elo_after)}</strong>.</p>`;
  }

  function examplesHtml(data) {
    if (!data || !data.match || !data.examples || data.examples.length !== 2) return "";
    const match = data.match;
    const when = match.date_is_approximate
      ? `${escapeHtml(match.season_label)}, data aproximada (a fonte não traz datas desta temporada)`
      : `${shortDate(match.date)}${match.round ? `, rodada ${match.round}` : ""}`;
    const earlier = match.season !== data.season ? ` É o confronto mais recente entre os dois, da temporada ${escapeHtml(match.season_label)}.` : "";
    return `<h4 class="elo-examples-title">Na prática: ${escapeHtml(match.home.name)} ${match.home_goals} × ${match.away_goals} ${escapeHtml(match.away.name)}</h4>
      <p class="note">${when}.${earlier} Primeiro, de onde vem o Elo de cada um antes do jogo; depois, como o jogo mexeu nos dois.</p>
      <div class="elo-examples-grid">${data.examples.map(sideCard).join("")}</div>
      ${matchSteps(match)}
      <p class="note">Contas do próprio modelo com os dados até ${shortDate(data.reference_date)}. Os valores aparecem arredondados; o cálculo usa todas as casas decimais.</p>`;
  }

  function fillExamples(container, competition) {
    const slot = container.querySelector(`#metodo-exemplos-${competition.id}`);
    if (!slot || slot.dataset.loaded) return;
    slot.dataset.loaded = "true";
    loadExamples(competition).then((data) => { slot.innerHTML = examplesHtml(data); });
  }

  function panel(competition, current) {
    const elo = competition.elo;
    const validation = competition.validation;
    const gain = (1 - validation.log_loss / validation.base_rate) * 100;
    const link = competition.id === current ? "" : ` <a href="${escapeHtml(base.href.replace(/assets\/$/, "") + competition.path)}">Ver a página</a>`;
    return `
      <dl class="method-facts">
        <div><dt>K</dt><dd>${decimal.format(elo.k_factor)}</dd></div>
        <div><dt>Mando (H)</dt><dd>${decimal.format(elo.home_advantage)} pontos</dd></div>
        <div><dt>Regressão entre temporadas</dt><dd>${percent.format(elo.season_regression * 100)}%</dd></div>
        <div><dt>Acerto no teste</dt><dd>log loss ${decimal.format(validation.log_loss)} contra ${decimal.format(validation.base_rate)} da taxa base (${percent.format(gain)}% melhor), ${validation.n_matches.toLocaleString("pt-BR")} jogos de ${escapeHtml(validation.seasons)}</dd></div>
      </dl>
      <ul class="method-list">
        <li><strong>Clube novo:</strong> ${escapeHtml(elo.newcomer)}.</li>
        ${competition.extras.map((item) => `<li>${escapeHtml(item)}.</li>`).join("")}
        <li><strong>Dados:</strong> ${escapeHtml(competition.data)}</li>
        <li><strong>Regras:</strong> ${escapeHtml(competition.rules)}${link}</li>
      </ul>
      <div class="elo-examples" id="metodo-exemplos-${competition.id}"></div>`;
  }

  function render(container, current) {
    fetch(new URL("methods.json", base), { cache: "no-cache" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => {
        const competitions = data.competitions;
        const tabs = competitions
          .map((competition) => `<button type="button" role="tab" id="metodo-tab-${competition.id}" aria-controls="metodo-painel-${competition.id}" aria-selected="${competition.id === current}" tabindex="${competition.id === current ? 0 : -1}">${escapeHtml(competition.name)}</button>`)
          .join("");
        const panels = competitions
          .map((competition) => `<div role="tabpanel" id="metodo-painel-${competition.id}" aria-labelledby="metodo-tab-${competition.id}"${competition.id === current ? "" : " hidden"}>${panel(competition, current)}</div>`)
          .join("");
        container.innerHTML = `${ELO_TEXT}
          <h3 class="elo-title">O que muda em cada competição</h3>
          <div class="method-tabs" role="tablist" aria-label="Competições">${tabs}</div>${panels}`;
        const buttons = [...container.querySelectorAll('[role="tab"]')];
        const byId = Object.fromEntries(competitions.map((competition) => [competition.id, competition]));
        const select = (button) => {
          buttons.forEach((other) => {
            const selected = other === button;
            other.setAttribute("aria-selected", String(selected));
            other.tabIndex = selected ? 0 : -1;
            container.querySelector(`#${other.getAttribute("aria-controls")}`).hidden = !selected;
          });
          fillExamples(container, byId[button.id.replace("metodo-tab-", "")]);
          button.focus();
        };
        if (byId[current]) fillExamples(container, byId[current]);
        buttons.forEach((button, index) => {
          button.addEventListener("click", () => select(button));
          button.addEventListener("keydown", (event) => {
            const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (step) select(buttons[(index + step + buttons.length) % buttons.length]);
          });
        });
      })
      .catch(() => {
        container.innerHTML = ELO_TEXT;
      });
  }

  window.AIndaDaMetodo = { render };
})();
