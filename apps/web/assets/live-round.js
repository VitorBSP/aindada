/* Modo Ao vivo (#/ao-vivo). Aplica os placares parciais de `live_round_scores` (Supabase, migração 0007) sobre o
   snapshot publicado e recalcula, no navegador, a tabela e as chances de título, G4, Libertadores, Sul-Americana e
   rebaixamento. Não depende do publish-site.yml: o snapshot continua o oficial; este modo é uma leitura provisória.
   - Jogo encerrado no snapshot vale sempre (o placar oficial ganha do ao vivo).
   - Jogo ao vivo: placar atual + gols que faltam, Poisson com o xG do modelo proporcional ao tempo que resta.
   - Jogo que não começou: o placar sorteado da matriz que o Python publica (`score_probabilities`).
   - Sorteio, tabela e desempate vêm do simulador (window.Simulator.engine); vagas pelo Art. 6º–8º, igual a
     competition_rules/qualification.py, em cada cenário externo do snapshot (faixa, sem probabilidade arbitrária). */
(function (root) {
  "use strict";

  // serie_a_2026.toml: [libertadores], [sudamericana] e [relegation].
  const RULES = {
    leagueSlots: ["groups", "groups", "groups", "groups", "prelim"],
    cupChampionPhase: "groups",
    cupRunnerUpPhase: "prelim",
    continentalTitlePhase: "groups",
    cupRedirectPolicy: "equivalent_slot_only",
    sudamericanaCount: 6,
    relegationCount: 4,
  };
  const PHASE_RANK = { groups: 0, prelim: 1 };
  const TOP4 = 4;
  const LIVE_STATUSES = new Set(["live", "ht"]);
  const KNOWN_STATUSES = new Set(["scheduled", "live", "ht", "finished"]);
  const SIMULATIONS = 20000;
  const CHUNK = 2000;
  const SEED = 2026;
  const POLL_MS = 15000;
  // Minutos de um jogo com os acréscimos médios; depois disso sobra um resto mínimo de tempo.
  const MATCH_MINUTES = 95;
  const MIN_REMAINING_FRACTION = 0.01;
  const MAX_EXTRA_GOALS = 10;
  const HALF_TIME_MINUTE = 45;
  const FOREIGN_PREFIX = "foreign:";

  const engine = () => root.Simulator && root.Simulator.engine;

  /* ---------------------------------------------------------------- Vagas (qualification.py) */

  const sortedSlots = (slots) => [...slots].sort((left, right) => PHASE_RANK[left] - PHASE_RANK[right]);

  function leagueAllocation(order, slots, excluded) {
    const remaining = [...slots];
    const allocation = new Map();
    for (const clubId of order) {
      if (!remaining.length) break;
      if (excluded.has(clubId)) continue;
      allocation.set(clubId, remaining.shift());
    }
    return allocation;
  }

  function allocateSlots(order, outcome, rules = RULES) {
    const inLeague = new Set(order);
    const continental = new Map();
    for (const champion of [outcome.libertadores_champion, outcome.sudamericana_champion]) {
      if (champion && inLeague.has(champion)) continental.set(champion, rules.continentalTitlePhase);
    }
    const leagueSlots = [...rules.leagueSlots];
    const extraSlots = [];
    const cupHolders = new Map();
    const relegated = new Set(order.slice(order.length - rules.relegationCount));
    const champion = inLeague.has(outcome.cup_champion) ? outcome.cup_champion : null;
    const runnerUp = inLeague.has(outcome.cup_runner_up) ? outcome.cup_runner_up : null;
    let runnerUpPhase = rules.cupRunnerUpPhase;

    if (outcome.cup_champion) {
      const tentative = leagueAllocation(order, leagueSlots, new Set(continental.keys()));
      const broad = rules.cupRedirectPolicy === "any_other_qualification";
      const championLeaguePhase = champion ? tentative.get(champion) : undefined;
      if (champion && continental.has(champion)) {
        if (broad) { runnerUpPhase = rules.cupChampionPhase; extraSlots.push(rules.cupRunnerUpPhase); }
        else extraSlots.push(rules.cupChampionPhase);
      } else if (champion && championLeaguePhase !== undefined && PHASE_RANK[championLeaguePhase] <= PHASE_RANK[rules.cupChampionPhase]) {
        runnerUpPhase = rules.cupChampionPhase;
        extraSlots.push(rules.cupRunnerUpPhase);
      } else if (champion && relegated.has(champion)) {
        extraSlots.push(rules.cupChampionPhase);
      } else if (champion) {
        cupHolders.set(champion, rules.cupChampionPhase);
      }
    }

    if (runnerUp) {
      if (continental.has(runnerUp) || relegated.has(runnerUp)) {
        extraSlots.push(runnerUpPhase);
      } else {
        const tentative = leagueAllocation(order, leagueSlots, new Set([...continental.keys(), ...cupHolders.keys()]));
        const leaguePhase = tentative.get(runnerUp);
        if (leaguePhase === undefined || PHASE_RANK[runnerUpPhase] < PHASE_RANK[leaguePhase]) cupHolders.set(runnerUp, runnerUpPhase);
        else extraSlots.push(runnerUpPhase);
      }
    }

    const excluded = new Set([...continental.keys(), ...cupHolders.keys()]);
    const libertadores = new Map([...leagueAllocation(order, sortedSlots([...leagueSlots, ...extraSlots]), excluded), ...continental, ...cupHolders]);
    const sudamericana = [];
    for (const clubId of order) {
      if (sudamericana.length === rules.sudamericanaCount) break;
      if (!libertadores.has(clubId)) sudamericana.push(clubId);
    }
    return { libertadores, sudamericana, relegated: order.slice(order.length - rules.relegationCount) };
  }

  /* scenario_id = "libertadores|sul-americana|campeão da Copa|vice da Copa" (scenarios.py); "none" ou estrangeiro = fora. */
  function parseScenario(scenarioId) {
    const asClub = (reference) => (!reference || reference === "none" || reference.startsWith(FOREIGN_PREFIX) ? null : reference);
    const [libertadores, sudamericana, cupChampion, cupRunnerUp] = String(scenarioId).split("|");
    return {
      libertadores_champion: asClub(libertadores),
      sudamericana_champion: asClub(sudamericana),
      cup_champion: asClub(cupChampion),
      cup_runner_up: asClub(cupRunnerUp),
    };
  }

  /* ---------------------------------------------------------------- Distribuições de placar */

  function mulberry32(seed) {
    let value = seed >>> 0;
    return function random() {
      value = (value + 0x6d2b79f5) >>> 0;
      let mixed = value;
      mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
      mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
      return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
    };
  }

  function poissonPmf(rate, maximum) {
    const values = [Math.exp(-rate)];
    for (let goals = 1; goals <= maximum; goals += 1) values.push(values[goals - 1] * rate / goals);
    return values;
  }

  function expectedGoals(match) {
    if (Number.isFinite(match.xg_home) && Number.isFinite(match.xg_away)) return [match.xg_home, match.xg_away];
    const matrix = match.score_probabilities;
    if (!Array.isArray(matrix) || !matrix.length) return null;
    let home = 0, away = 0, total = 0;
    matrix.forEach((row, homeGoals) => row.forEach((probability, awayGoals) => {
      home += homeGoals * probability; away += awayGoals * probability; total += probability;
    }));
    return total > 0 ? [home / total, away / total] : null;
  }

  const remainingFraction = (minute) => Math.max(MIN_REMAINING_FRACTION, (MATCH_MINUTES - Math.min(minute, MATCH_MINUTES)) / MATCH_MINUTES);
  const liveMinute = (row) => (row.status === "ht" ? HALF_TIME_MINUTE : Number.isFinite(row.minute) ? row.minute : 0);

  /* Placar final a partir do parcial: gols que faltam com Poisson independente (xG × fração do tempo que resta). */
  function liveDistribution(match, row) {
    const rates = expectedGoals(match);
    if (!rates) return null;
    const fraction = remainingFraction(liveMinute(row));
    const homeExtra = poissonPmf(rates[0] * fraction, MAX_EXTRA_GOALS);
    const awayExtra = poissonPmf(rates[1] * fraction, MAX_EXTRA_GOALS);
    const cells = [];
    let total = 0;
    homeExtra.forEach((homeProbability, home) => awayExtra.forEach((awayProbability, away) => {
      const probability = homeProbability * awayProbability;
      if (probability > 0) { total += probability; cells.push([total, row.home_goals + home, row.away_goals + away]); }
    }));
    return total > 0 ? { cells, total } : null;
  }

  function preMatchDistribution(match) {
    const sampler = engine().scoreSampler(match);
    if (sampler) return sampler;
    const rates = expectedGoals(match);
    return rates ? liveDistribution(match, { status: "live", minute: 0, home_goals: 0, away_goals: 0 }) : null;
  }

  function outcomeChances(distribution) {
    const chances = { H: 0, D: 0, A: 0 };
    let previous = 0;
    distribution.cells.forEach(([cumulative, home, away]) => {
      chances[engine().outcomeOf(home, away)] += cumulative - previous;
      previous = cumulative;
    });
    return { H: chances.H / distribution.total, D: chances.D / distribution.total, A: chances.A / distribution.total };
  }

  /* ---------------------------------------------------------------- Estado da rodada */

  function validRow(row) {
    if (!row || typeof row.match_id !== "string" || !KNOWN_STATUSES.has(row.status)) return false;
    if (row.status === "scheduled") return true;
    return Number.isInteger(row.home_goals) && Number.isInteger(row.away_goals) && row.home_goals >= 0 && row.away_goals >= 0;
  }

  function currentRoundNumber(snapshot, rowsById) {
    const open = snapshot.matches.filter((match) => match.status !== "finished" && match.status !== "cancelled" && Number.isInteger(match.round));
    const counts = new Map();
    open.forEach((match) => {
      const row = rowsById.get(match.match_id);
      if (row && row.status !== "scheduled") counts.set(match.round, (counts.get(match.round) || 0) + 1);
    });
    if (counts.size) return [...counts.entries()].sort((left, right) => right[1] - left[1] || left[0] - right[0])[0][0];
    return open.length ? Math.min(...open.map((match) => match.round)) : null;
  }

  /* Junta snapshot e placares ao vivo. `round` é a rodada mostrada; `fixed` são os jogos com placar conhecido fora
     dela; `roundMatches` traz o estado de cada jogo da rodada; `future` são os outros jogos ainda por jogar. */
  function prepare(snapshot, liveRows) {
    const known = new Map(snapshot.matches.map((match) => [match.match_id, match]));
    const rowsById = new Map();
    let ignored = 0;
    (liveRows || []).forEach((row) => {
      if (!validRow(row) || !known.has(row.match_id) || (row.season !== undefined && Number(row.season) !== Number(snapshot.season))) { ignored += 1; return; }
      rowsById.set(row.match_id, row);
    });
    const round = currentRoundNumber(snapshot, rowsById);
    const fixed = [];
    const future = [];
    const roundMatches = [];
    snapshot.matches.forEach((match) => {
      if (match.status === "cancelled") return;
      if (match.round === round) {
        const row = rowsById.get(match.match_id);
        let state = "scheduled", homeGoals = null, awayGoals = null, minute = null, official = false;
        if (match.status === "finished") { state = "finished"; homeGoals = match.home_goals; awayGoals = match.away_goals; official = true; }
        else if (row && row.status !== "scheduled") { state = row.status; homeGoals = row.home_goals; awayGoals = row.away_goals; minute = Number.isInteger(row.minute) ? row.minute : null; }
        roundMatches.push({ match, state, homeGoals, awayGoals, minute, official, updatedAt: row ? row.updated_at : null });
      } else if (match.status === "finished") {
        fixed.push(match);
      } else {
        future.push(match);
      }
    });
    const live = roundMatches.filter((item) => LIVE_STATUSES.has(item.state)).length;
    const liveFinished = roundMatches.filter((item) => item.state === "finished" && !item.official).length;
    return { snapshot, round, fixed, future, roundMatches, live, liveFinished, ignored };
  }

  const resultOf = (homeId, awayId, homeGoals, awayGoals) => ({ home: homeId, away: awayId, outcome: engine().outcomeOf(homeGoals, awayGoals), homeGoals, awayGoals });

  function rankedTable(clubIds, matches) {
    const rows = engine().newRows(clubIds);
    const results = matches.map((item) => resultOf(item.home_id, item.away_id, item.home_goals, item.away_goals));
    results.forEach((result) => engine().addResult(rows, result));
    return engine().rankRows(rows, results);
  }

  /* Tabela antes da rodada e tabela "como está agora" (parciais contam como se o jogo acabasse assim). */
  function tables(model) {
    const clubIds = model.snapshot.teams.map((team) => team.club_id);
    const before = rankedTable(clubIds, model.fixed);
    const played = model.roundMatches.filter((item) => item.state !== "scheduled")
      .map((item) => ({ home_id: item.match.home_id, away_id: item.match.away_id, home_goals: item.homeGoals, away_goals: item.awayGoals }));
    const now = rankedTable(clubIds, [...model.fixed, ...played]);
    const beforePosition = new Map(before.map((row) => [row.club_id, row.position]));
    return now.map((row) => ({ ...row, before: beforePosition.get(row.club_id) }));
  }

  /* ---------------------------------------------------------------- Monte Carlo */

  /* Jogos a sortear. Com `baseline`, toda a rodada volta ao início (chances antes da rodada). */
  function plan(model, baseline) {
    const draws = [];
    const settled = [...model.fixed.map((match) => ({ home_id: match.home_id, away_id: match.away_id, home_goals: match.home_goals, away_goals: match.away_goals }))];
    model.roundMatches.forEach((item) => {
      if (!baseline && item.state === "finished") {
        settled.push({ home_id: item.match.home_id, away_id: item.match.away_id, home_goals: item.homeGoals, away_goals: item.awayGoals });
        return;
      }
      const isLive = !baseline && LIVE_STATUSES.has(item.state);
      const distribution = isLive ? liveDistribution(item.match, { status: item.state, minute: item.minute, home_goals: item.homeGoals, away_goals: item.awayGoals }) : preMatchDistribution(item.match);
      if (distribution) draws.push({ match: item.match, distribution });
    });
    model.future.forEach((match) => {
      const distribution = preMatchDistribution(match);
      if (distribution) draws.push({ match, distribution });
    });
    return { settled, draws };
  }

  async function simulate(model, options = {}) {
    const baseline = Boolean(options.baseline);
    const simulations = options.simulations || SIMULATIONS;
    const random = mulberry32(options.seed === undefined ? SEED : options.seed);
    const clubIds = model.snapshot.teams.map((team) => team.club_id);
    const size = clubIds.length;
    const index = new Map(clubIds.map((clubId, position) => [clubId, position]));
    const scenarios = (model.snapshot.scenarios && model.snapshot.scenarios.length ? model.snapshot.scenarios : [{ scenario_id: "none|none|none|none" }])
      .map((scenario) => ({ id: scenario.scenario_id, outcome: parseScenario(scenario.scenario_id) }));
    const { settled, draws } = plan(model, baseline);

    const basePoints = new Float64Array(size), baseWins = new Float64Array(size), baseBalance = new Float64Array(size), baseScored = new Float64Array(size);
    const duel = new Map();
    const duelKey = (left, right) => (left < right ? `${left}|${right}` : `${right}|${left}`);
    const applyDuel = (entry, home, away, homeGoals, awayGoals) => {
      const points = homeGoals > awayGoals ? [3, 0] : homeGoals < awayGoals ? [0, 3] : [1, 1];
      entry[home].points += points[0]; entry[away].points += points[1];
      entry[home].goals += homeGoals - awayGoals; entry[away].goals += awayGoals - homeGoals;
    };
    const emptyDuel = (first, second) => ({ [first]: { points: 0, goals: 0 }, [second]: { points: 0, goals: 0 } });
    const addTo = (points, wins, balance, scored, home, away, homeGoals, awayGoals) => {
      if (homeGoals > awayGoals) { points[home] += 3; wins[home] += 1; } else if (homeGoals < awayGoals) { points[away] += 3; wins[away] += 1; } else { points[home] += 1; points[away] += 1; }
      balance[home] += homeGoals - awayGoals; balance[away] += awayGoals - homeGoals; scored[home] += homeGoals; scored[away] += awayGoals;
    };
    settled.forEach((match) => {
      addTo(basePoints, baseWins, baseBalance, baseScored, index.get(match.home_id), index.get(match.away_id), match.home_goals, match.away_goals);
      const key = duelKey(match.home_id, match.away_id);
      if (!duel.has(key)) duel.set(key, emptyDuel(match.home_id, match.away_id));
      applyDuel(duel.get(key), match.home_id, match.away_id, match.home_goals, match.away_goals);
    });
    const drawsByPair = new Map();
    draws.forEach((item, position) => {
      const key = duelKey(item.match.home_id, item.match.away_id);
      drawsByPair.set(key, [...(drawsByPair.get(key) || []), position]);
    });

    const tally = clubIds.map(() => ({ title: 0, top4: 0, relegation: 0, positions: new Float64Array(size), libertadores: new Float64Array(scenarios.length), sudamericana: new Float64Array(scenarios.length) }));
    // `track` (Home do seu time, ADR-0016): para cada jogo acompanhado e cada resultado sorteado nele, conta em quantas
    // simulações o clube acompanhado terminou campeão, no G4 ou rebaixado. Só lê o sorteio; não muda o resultado.
    const trackedClub = options.track && index.has(options.track.clubId) ? index.get(options.track.clubId) : null;
    const trackedIds = new Set(trackedClub === null ? [] : options.track.matchIds || []);
    const emptyOutcome = () => ({ n: 0, title: 0, top4: 0, relegation: 0 });
    const tracked = draws.map((item, position) => ({ position, item })).filter(({ item }) => trackedIds.has(item.match.match_id))
      .map(({ position, item }) => ({ position, matchId: item.match.match_id, outcomes: { H: emptyOutcome(), D: emptyOutcome(), A: emptyOutcome() } }));
    const drawn = new Array(draws.length);
    const points = new Float64Array(size), wins = new Float64Array(size), balance = new Float64Array(size), scored = new Float64Array(size), luck = new Float64Array(size);
    const sample = engine().draw;

    for (let simulation = 0; simulation < simulations; simulation += 1) {
      points.set(basePoints); wins.set(baseWins); balance.set(baseBalance); scored.set(baseScored);
      draws.forEach((item, position) => {
        const [home, away] = sample(item.distribution, random);
        drawn[position] = [home, away];
        addTo(points, wins, balance, scored, index.get(item.match.home_id), index.get(item.match.away_id), home, away);
      });
      for (let club = 0; club < size; club += 1) luck[club] = random();
      const main = (left, right) => points[right] - points[left] || wins[right] - wins[left] || balance[right] - balance[left] || scored[right] - scored[left];
      const order = Array.from({ length: size }, (unused, club) => club).sort((left, right) => main(left, right) || luck[left] - luck[right]);
      for (let start = 0; start < size;) {
        let end = start + 1;
        while (end < size && main(order[start], order[end]) === 0) end += 1;
        if (end - start === 2) {
          const first = clubIds[order[start]], second = clubIds[order[start + 1]];
          const key = duelKey(first, second);
          const settledDuel = duel.get(key);
          const head = emptyDuel(first, second);
          if (settledDuel) [first, second].forEach((clubId) => { head[clubId].points += settledDuel[clubId].points; head[clubId].goals += settledDuel[clubId].goals; });
          (drawsByPair.get(key) || []).forEach((position) => {
            const match = draws[position].match;
            applyDuel(head, match.home_id, match.away_id, drawn[position][0], drawn[position][1]);
          });
          const edge = head[first].points - head[second].points || head[first].goals - head[second].goals;
          if (edge < 0) [order[start], order[start + 1]] = [order[start + 1], order[start]];
        }
        start = end;
      }
      if (tracked.length) {
        const rank = order.indexOf(trackedClub);
        tracked.forEach((entry) => {
          const [home, away] = drawn[entry.position];
          const bucket = entry.outcomes[engine().outcomeOf(home, away)];
          bucket.n += 1;
          if (rank === 0) bucket.title += 1;
          if (rank < TOP4) bucket.top4 += 1;
          if (rank >= size - RULES.relegationCount) bucket.relegation += 1;
        });
      }
      const finalOrder = order.map((club) => clubIds[club]);
      order.forEach((club, position) => {
        const entry = tally[club];
        entry.positions[position] += 1;
        if (position === 0) entry.title += 1;
        if (position < TOP4) entry.top4 += 1;
        if (position >= size - RULES.relegationCount) entry.relegation += 1;
      });
      scenarios.forEach((scenario, scenarioIndex) => {
        const slots = allocateSlots(finalOrder, scenario.outcome);
        slots.libertadores.forEach((phase, clubId) => { tally[index.get(clubId)].libertadores[scenarioIndex] += 1; });
        slots.sudamericana.forEach((clubId) => { tally[index.get(clubId)].sudamericana[scenarioIndex] += 1; });
      });
      if (simulation % CHUNK === CHUNK - 1 && options.yieldEvery !== false) await new Promise((resolve) => setTimeout(resolve));
    }

    const range = (values) => {
      const shares = Array.from(values, (value) => value / simulations);
      return { min: Math.min(...shares), max: Math.max(...shares) };
    };
    const result = new Map();
    clubIds.forEach((clubId, club) => {
      const entry = tally[club];
      result.set(clubId, {
        title: entry.title / simulations,
        top4: entry.top4 / simulations,
        relegation: entry.relegation / simulations,
        libertadores: range(entry.libertadores),
        sudamericana: range(entry.sudamericana),
      });
    });
    const track = tracked.map((entry) => ({
      match_id: entry.matchId,
      outcomes: Object.fromEntries(Object.entries(entry.outcomes).map(([outcome, bucket]) => [outcome, {
        n: bucket.n,
        title: bucket.n ? bucket.title / bucket.n : null,
        top4: bucket.n ? bucket.top4 / bucket.n : null,
        relegation: bucket.n ? bucket.relegation / bucket.n : null,
      }])),
    }));
    return { simulations, scenarios: scenarios.length, clubs: result, track };
  }

  /* ---------------------------------------------------------------- Página */

  const config = () => root.AINDA_DA_SIMULATOR || {};
  let active = null;

  async function fetchLiveRows(season) {
    const { supabaseUrl, supabaseAnonKey } = config();
    if (!supabaseUrl || !supabaseAnonKey) throw new Error("sem servidor");
    const url = `${supabaseUrl.replace(/\/$/, "")}/rest/v1/live_round_scores?season=eq.${encodeURIComponent(season)}&select=season,round,match_id,home_goals,away_goals,minute,status,updated_at`;
    const response = await fetch(url, { cache: "no-store", headers: { apikey: supabaseAnonKey, Authorization: `Bearer ${supabaseAnonKey}`, Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const rows = await response.json();
    if (!Array.isArray(rows)) throw new Error("resposta inesperada");
    return rows;
  }

  const brasiliaTime = (stamp, withSeconds = true) => new Date(stamp).toLocaleTimeString("pt-BR", {
    hour: "2-digit", minute: "2-digit", ...(withSeconds ? { second: "2-digit" } : {}), timeZone: "America/Sao_Paulo",
  });

  function render(main, context) {
    if (active) active.stop();
    const { snapshot, escapeHtml, pct, crest } = context;
    const teamOf = new Map(snapshot.teams.map((team) => [team.club_id, team]));
    const longName = (clubId) => escapeHtml((teamOf.get(clubId) || { name: clubId }).name);
    const shortName = (clubId) => escapeHtml((teamOf.get(clubId) || {}).short_name || (teamOf.get(clubId) || { name: clubId }).name);
    const clubName = (clubId) => `<span class="live-name-long">${longName(clubId)}</span><span class="live-name-short" aria-hidden="true">${shortName(clubId)}</span>`;
    const controller = { timer: null, stopped: false, signature: null, baseline: null, run: 0, rows: [], updatedAt: null, error: "" };
    active = controller;
    controller.stop = () => {
      controller.stopped = true;
      if (controller.timer) clearInterval(controller.timer);
      document.removeEventListener("visibilitychange", controller.onVisibility);
    };

    main.innerHTML = `
      <section class="live" aria-labelledby="live-title">
        <div class="live-head">
          <h1 id="live-title">Ao vivo</h1>
          <button type="button" class="live-refresh" id="live-refresh">Atualizar</button>
        </div>
        <p class="live-stamp" id="live-stamp" aria-live="polite">Buscando os placares…</p>
        <div id="live-body" aria-busy="true"></div>
        <p class="live-foot">Calculado no seu navegador com os placares de agora · ${SIMULATIONS.toLocaleString("pt-BR")} simulações · não é a edição oficial</p>
        <details class="live-method"><summary>Como é calculado</summary><p class="note">Provisório: o oficial continua sendo a edição publicada. Jogo em andamento termina no sorteio com o placar atual mais os gols que faltam (Poisson com o xG do modelo, proporcional ao tempo que resta, ${MATCH_MINUTES} minutos com acréscimos); jogo que não começou usa as probabilidades de placar da edição. ${SIMULATIONS.toLocaleString("pt-BR")} simulações com semente fixa; empate que os critérios do Art. 15 não desfazem (cartões, sorteio) é sorteado. Libertadores e Sul-Americana aparecem como faixa entre os cenários dos outros torneios ainda em aberto. As variações comparam com o mesmo cálculo antes da rodada.</p></details>
      </section>`;
    const body = main.querySelector("#live-body");
    const stamp = main.querySelector("#live-stamp");
    const favorite = context.favorite || "";
    controller.filter = "all";

    const kickoffText = (match) => {
      if (match.kickoff_utc) {
        const when = new Date(match.kickoff_utc);
        const day = when.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", weekday: "short", day: "2-digit", month: "2-digit" }).replace(".", "").replace(",", "");
        return `${day.charAt(0).toUpperCase()}${day.slice(1)} ${brasiliaTime(match.kickoff_utc, false)}`;
      }
      return match.match_date ? new Date(`${match.match_date}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : "";
    };

    function badge(item) {
      if (item.state === "finished") return `<span class="mc-badge is-final">${item.official ? "Encerrado" : "Fim · provisório"}</span>`;
      if (item.state === "ht") return `<span class="mc-badge is-live">Intervalo</span>`;
      if (item.state === "live") return `<span class="mc-badge is-live">Ao vivo${item.minute === null ? "" : ` · ${item.minute}'`}</span>`;
      return "";
    }

    // Match Card v2.1 (F1): placar no centro, probabilidade de agora em pílulas e, quando a conta termina, o efeito do jogo.
    function matchCard(item) {
      const { match } = item;
      const scored = item.state !== "scheduled";
      const center = scored
        ? `<div class="mc-result"><span class="mc-center">${item.homeGoals} × ${item.awayGoals}</span>${badge(item)}</div>`
        : `<span class="mc-center is-vs">VS</span>`;
      let odds = "";
      if (item.state !== "finished") {
        const isLive = LIVE_STATUSES.has(item.state);
        const distribution = isLive
          ? liveDistribution(match, { status: item.state, minute: item.minute, home_goals: item.homeGoals, away_goals: item.awayGoals })
          : preMatchDistribution(match);
        if (distribution) {
          const chances = outcomeChances(distribution);
          const top = Math.max(chances.H, chances.D, chances.A);
          const pill = (value, label) => `<span class="mc-odd${value === top ? " is-top" : ""}"><strong>${pct(value)}</strong><span>${label}</span></span>`;
          odds = `<p class="mc-caption">${isLive ? "Probabilidade de agora (placar e tempo que falta)" : "Probabilidade do modelo"}</p>
            <div class="mc-odds">${pill(chances.H, shortName(match.home_id))}${pill(chances.D, "Empate")}${pill(chances.A, shortName(match.away_id))}</div>`;
        }
      }
      const team = (clubId) => `<span class="mc-team">${crest(clubId, 38)}<span class="mc-team-name">${shortName(clubId)}</span></span>`;
      return `<li class="mc live-mc is-${item.state}">
        <div class="mc-top"><span>R${roundShown} · ${escapeHtml(kickoffText(match))}</span></div>
        <div class="mc-teams" aria-label="${longName(match.home_id)} ${scored ? `${item.homeGoals} a ${item.awayGoals}` : "contra"} ${longName(match.away_id)}">${team(match.home_id)}${center}${team(match.away_id)}</div>
        ${odds}
        <p class="live-effect" data-effect="${escapeHtml(match.match_id)}" hidden></p>
      </li>`;
    }
    let roundShown = "";

    function movement(row) {
      if (row.before === undefined || row.before === row.position) return `<span class="live-move same" aria-label="mesma posição">=</span>`;
      const up = row.before > row.position;
      const steps = Math.abs(row.before - row.position);
      return `<span class="live-move ${up ? "up" : "down"}" aria-label="${up ? "subiu" : "caiu"} ${steps}">${up ? "▲" : "▼"}${steps}</span>`;
    }

    const zoneClass = (position, total) => (position <= 5 ? "zone-lib" : position <= 11 ? "zone-sula" : position > total - RULES.relegationCount ? "zone-z4" : "");

    function tableHtml(rows) {
      return `<table class="live-table">
        <caption class="visually-hidden">Tabela com os placares de agora</caption>
        <thead><tr><th scope="col">#</th><th scope="col"><span class="visually-hidden">Variação desde antes da rodada</span>±</th><th scope="col" class="left">Clube</th><th scope="col">Pts</th><th scope="col">J</th><th scope="col">V</th><th scope="col">SG</th></tr></thead>
        <tbody>${rows.map((row) => `<tr class="${zoneClass(row.position, rows.length)}">
          <td class="pos">${row.position}</td><td>${movement(row)}</td>
          <td class="left club">${crest(row.club_id, 18)} ${clubName(row.club_id)}</td>
          <td><strong>${row.points}</strong></td><td>${row.played}</td><td>${row.wins}</td><td>${row.goals_for - row.goals_against}</td></tr>`).join("")}</tbody>
      </table>`;
    }

    function deltaHtml(now, before, inverse = false) {
      if (before === undefined) return "";
      const delta = now - before;
      if (Math.abs(delta) < 0.01) return "";
      const good = inverse ? delta < 0 : delta > 0;
      return `<span class="live-delta ${good ? "change-up" : "change-down"}">${delta > 0 ? "+" : "−"}${Math.round(Math.abs(delta) * 100)}</span>`;
    }

    function rangeText(range) {
      if (range.max - range.min < 0.005) return pct(range.max);
      return `${pct(range.min).replace("%", "")}–${pct(range.max)}`;
    }

    function chancesHtml(rows, result, baseline) {
      const cell = (clubId, key, kind, inverse = false) => {
        const value = result.clubs.get(clubId)[key];
        const before = baseline ? baseline.clubs.get(clubId)[key] : undefined;
        if (typeof value === "number") return `<td><span class="prob prob-${kind}" style="--p:${Math.min(1, value)}">${pct(value)}</span>${deltaHtml(value, before, inverse)}</td>`;
        const middle = (value.min + value.max) / 2;
        return `<td><span class="prob prob-${kind}" style="--p:${Math.min(1, middle)}">${rangeText(value)}</span>${before ? deltaHtml(middle, (before.min + before.max) / 2) : ""}</td>`;
      };
      return `<table class="live-table live-chances">
        <caption class="visually-hidden">Probabilidades com os placares de agora, em ${result.simulations.toLocaleString("pt-BR")} simulações</caption>
        <thead><tr><th scope="col" class="left">Clube</th><th scope="col">Título</th><th scope="col">G4</th><th scope="col"><abbr title="Libertadores">Liberta.</abbr></th><th scope="col"><abbr title="Sul-Americana">Sul-Am.</abbr></th><th scope="col"><abbr title="Rebaixamento">Queda</abbr></th></tr></thead>
        <tbody>${rows.map((row) => `<tr>
          <td class="left club">${crest(row.club_id, 18)} ${clubName(row.club_id)}</td>
          ${cell(row.club_id, "title", "title")}${cell(row.club_id, "top4", "lib")}${cell(row.club_id, "libertadores", "lib")}${cell(row.club_id, "sudamericana", "sula")}${cell(row.club_id, "relegation", "danger", true)}
        </tr>`).join("")}</tbody>
      </table>`;
    }

    /* ---- F2: o que está mudando agora (só dados: variação desde antes da rodada, sem adjetivo) */
    const METRICS = [
      { key: "title", filter: "title", label: "título", short: "Título" },
      { key: "top4", filter: "top4", label: "G4", short: "G4" },
      { key: "relegation", filter: "z4", label: "queda", short: "Queda" },
    ];
    const FILTERS = [["all", "Tudo"], ["title", "Título"], ["top4", "G4"], ["z4", "Z4"], ["mine", "Seu time"]];

    // O que o jogo do clube está fazendo, em palavras: vence/empata/perde (passado se acabou), ou ainda não jogou.
    function gameNote(model, clubId) {
      const item = model.roundMatches.find((entry) => entry.match.home_id === clubId || entry.match.away_id === clubId);
      if (!item || item.state === "scheduled") return "ainda não jogou na rodada";
      const home = item.match.home_id === clubId;
      const own = home ? item.homeGoals : item.awayGoals;
      const other = home ? item.awayGoals : item.homeGoals;
      const rival = longName(home ? item.match.away_id : item.match.home_id);
      const done = item.state === "finished";
      if (own > other) return `${done ? "venceu" : "vence"} o ${rival} por ${own} × ${other}`;
      if (own < other) return `${done ? "perdeu" : "perde"} para o ${rival} por ${own} × ${other}`;
      return `${done ? "empatou" : "empata"} com o ${rival} por ${own} × ${other}`;
    }

    function impactHtml(model, result, baseline) {
      const filter = controller.filter;
      if (filter === "mine" && !favorite) return `<p class="live-impact-empty">Escolha o seu time na página do clube (estrela ao lado do nome) para ver só ele aqui.</p>`;
      const moves = [];
      result.clubs.forEach((now, clubId) => {
        if (filter === "mine" && clubId !== favorite) return;
        const before = baseline.clubs.get(clubId);
        METRICS.forEach((metric) => {
          if (filter !== "all" && filter !== "mine" && metric.filter !== filter) return;
          const delta = now[metric.key] - before[metric.key];
          if (filter !== "mine" && Math.abs(delta) < 0.01) return;
          const settledValue = (value) => value < 0.005 || value > 0.995;
          if (settledValue(now[metric.key]) && settledValue(before[metric.key])) return;
          moves.push({ clubId, metric, now: now[metric.key], before: before[metric.key], delta });
        });
      });
      moves.sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta));
      const shown = moves.slice(0, filter === "all" ? 5 : 6);
      if (!shown.length) return `<p class="live-impact-empty">Nenhuma probabilidade mudou 1 ponto percentual ou mais desde o início da rodada${filter === "all" ? "" : " neste filtro"}.</p>`;
      return `<ul class="live-impact-list">${shown.map((move) => {
        const points = Math.round(Math.abs(move.delta) * 100);
        const arrow = Math.abs(move.delta) < 0.005 ? "=" : move.delta > 0 ? "▲" : "▼";
        const bad = move.metric.key === "relegation" ? move.delta > 0 : move.delta < 0;
        return `<li>${crest(move.clubId, 28)}
          <span class="live-impact-text"><strong>${longName(move.clubId)} · ${move.metric.label}</strong><span>${escapeHtml(gameNote(model, move.clubId))} · era ${pct(move.before)}</span></span>
          <span class="live-impact-value"><strong>${pct(move.now)}</strong><span class="${Math.abs(move.delta) < 0.005 ? "" : bad ? "change-down" : "change-up"}">${arrow} ${points} p.p.</span></span></li>`;
      }).join("")}</ul>`;
    }

    function chipsHtml() {
      return FILTERS.map(([key, label]) => `<button type="button" class="chip" data-live-filter="${key}" aria-pressed="${controller.filter === key}">${label}</button>`).join("");
    }

    // Por clube, a disputa mais aberta entre título, G4 e queda (a mais longe de 0% e de 100%).
    function effectLine(match, result) {
      const groups = new Map();
      [match.home_id, match.away_id].forEach((clubId) => {
        const values = result.clubs.get(clubId);
        const metric = METRICS.map((item) => ({ item, value: values[item.key] }))
          .filter((entry) => entry.value >= 0.01 && entry.value <= 0.99)
          .sort((left, right) => Math.min(right.value, 1 - right.value) - Math.min(left.value, 1 - left.value))[0];
        if (!metric) return;
        if (!groups.has(metric.item.short)) groups.set(metric.item.short, []);
        groups.get(metric.item.short).push(`${shortName(clubId)} ${pct(metric.value)}`);
      });
      return [...groups.entries()].map(([label, parts]) => `<span><b>${label}:</b> ${parts.join(" · ")}</span>`).join("");
    }

    // Tabela agora (compacta): só quem mudou de posição ou de probabilidade; a completa fica logo abaixo.
    function compactTable(rows, result, baseline) {
      const changed = rows.filter((row) => {
        const now = result.clubs.get(row.club_id);
        const before = baseline.clubs.get(row.club_id);
        return (row.before !== undefined && row.before !== row.position) || Math.abs(now.title - before.title) >= 0.01 || Math.abs(now.relegation - before.relegation) >= 0.01;
      });
      const list = changed.length ? changed : rows.slice(0, 4);
      const value = (clubId, key, inverse) => {
        const now = result.clubs.get(clubId)[key];
        return `<td>${pct(now)}${deltaHtml(now, baseline.clubs.get(clubId)[key], inverse)}</td>`;
      };
      return `<table class="live-table live-compact">
        <caption class="visually-hidden">Clubes que mudaram de posição ou de probabilidade com os placares de agora</caption>
        <thead><tr><th scope="col">#</th><th scope="col" class="left">Clube</th><th scope="col">Pts</th><th scope="col">Título</th><th scope="col">Z4</th></tr></thead>
        <tbody>${list.map((row) => `<tr><td class="pos"><span>${row.position}</span>${movement(row)}</td>
          <td class="left club">${crest(row.club_id, 18)} ${clubName(row.club_id)}</td><td><strong>${row.points}</strong></td>
          ${value(row.club_id, "title", false)}${value(row.club_id, "relegation", true)}</tr>`).join("")}</tbody>
      </table>`;
    }

    async function draw(model) {
      const run = ++controller.run;
      const rows = tables(model);
      const hasScores = model.live > 0 || model.liveFinished > 0;
      roundShown = model.round;
      main.querySelector("#live-title").textContent = `Ao vivo · R${model.round}`;
      const rolling = model.roundMatches.filter((item) => LIVE_STATUSES.has(item.state)).length;
      const ended = model.roundMatches.filter((item) => item.state === "finished").length;
      const waiting = model.roundMatches.filter((item) => item.state === "scheduled").length;
      const tally = [rolling ? `${rolling} rolando` : "", ended ? `${ended} ${ended === 1 ? "encerrado" : "encerrados"}` : "", waiting ? `${waiting} a jogar` : ""].filter(Boolean).join(" · ");
      const notices = [];
      if (model.ignored) notices.push(`<p class="note">${model.ignored === 1 ? "1 placar ignorado" : `${model.ignored} placares ignorados`}: jogo desconhecido, de outra temporada ou já encerrado de forma diferente.</p>`);
      body.innerHTML = `
        ${notices.join("")}
        <div class="live-chips" role="group" aria-label="Mostrar mudanças de">${chipsHtml()}</div>
        <section class="live-impact" aria-labelledby="live-impact-title">
          <p class="live-impact-head"><strong id="live-impact-title">O que está mudando agora</strong><span>desde o início da rodada</span></p>
          <div id="live-impact">${hasScores ? `<p class="live-impact-empty">Calculando…</p>` : `<p class="live-impact-empty">${model.liveFinished ? "" : "Sem jogos ao vivo no momento. "}Quando a bola rolar, as mudanças aparecem aqui sozinhas (a página confere a cada 15 segundos).</p>`}</div>
        </section>
        <h2 class="live-h">Jogos <span>${escapeHtml(tally)}</span></h2>
        <ul class="mc-list live-matches">${model.roundMatches.map(matchCard).join("")}</ul>
        ${hasScores ? `
          <section class="live-now" aria-labelledby="live-now-title">
            <h2 class="live-h" id="live-now-title">Tabela agora <span>se terminasse assim</span></h2>
            <div id="live-now"><p class="live-impact-empty">Calculando…</p></div>
            <details class="live-full"><summary>Tabela completa e todas as probabilidades</summary>
              <div class="legend"><span class="l-lib">Libertadores (1º–5º)</span><span class="l-sula">Sul-Americana (6º–11º)</span><span class="l-z4">Rebaixamento</span></div>
              ${tableHtml(rows)}
              <h3>Probabilidades agora</h3><p class="note" id="live-chances-note">Calculando…</p><div id="live-chances"></div>
            </details>
          </section>` : ""}`;
      body.setAttribute("aria-busy", hasScores ? "true" : "false");
      const bindChips = (result) => body.querySelectorAll("[data-live-filter]").forEach((button) => button.addEventListener("click", () => {
        controller.filter = button.dataset.liveFilter;
        body.querySelectorAll("[data-live-filter]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
        if (result) body.querySelector("#live-impact").innerHTML = impactHtml(model, result, controller.baseline);
      }));
      if (!hasScores) { bindChips(null); return; }
      if (!controller.baseline) controller.baseline = await simulate(model, { baseline: true });
      const result = await simulate(model);
      if (controller.stopped || run !== controller.run) return;
      bindChips(result);
      body.querySelector("#live-impact").innerHTML = impactHtml(model, result, controller.baseline);
      body.querySelector("#live-now").innerHTML = compactTable(rows, result, controller.baseline);
      body.querySelectorAll("[data-effect]").forEach((slot) => {
        const item = model.roundMatches.find((entry) => entry.match.match_id === slot.dataset.effect);
        const line = item ? effectLine(item.match, result) : "";
        if (line) { slot.innerHTML = line; slot.hidden = false; }
      });
      body.querySelector("#live-chances-note").textContent = `${result.simulations.toLocaleString("pt-BR")} simulações no seu navegador. O número pequeno é a variação em pontos percentuais desde antes da rodada. Vagas continentais: faixa entre ${result.scenarios} cenários dos outros torneios; as vagas pela tabela podem descer se o campeão da Copa do Brasil ou da Libertadores já estiver classificado.`;
      body.querySelector("#live-chances").innerHTML = chancesHtml(rows, result, controller.baseline);
      body.setAttribute("aria-busy", "false");
    }

    async function refresh(force) {
      if (controller.stopped) return;
      const button = main.querySelector("#live-refresh");
      if (button) button.disabled = true;
      try {
        const rows = await fetchLiveRows(snapshot.season);
        if (controller.stopped) return;
        controller.rows = rows;
        controller.updatedAt = Date.now();
        controller.error = "";
      } catch (error) {
        controller.error = error && error.message === "sem servidor"
          ? "Modo ao vivo sem servidor configurado: mostrando só a edição publicada."
          : "Não deu para buscar os placares agora. Tentando de novo em 15 segundos.";
      }
      if (controller.stopped) return;
      if (button) button.disabled = false;
      stamp.innerHTML = controller.updatedAt
        ? `<span class="live-badge">${brasiliaTime(controller.updatedAt)} · a cada 15 s</span>${controller.error ? ` <span class="sim-warning">${escapeHtml(controller.error)}</span>` : ""}`
        : `<span class="sim-warning">${escapeHtml(controller.error)}</span>`;
      const signature = JSON.stringify([...controller.rows].sort((left, right) => String(left.match_id).localeCompare(String(right.match_id)))
        .map((row) => [row.match_id, row.status, row.home_goals, row.away_goals, row.minute]));
      if (!force && signature === controller.signature) return;
      controller.signature = signature;
      const model = prepare(snapshot, controller.rows);
      if (model.round === null) {
        body.innerHTML = `<p class="live-empty" role="status"><strong>Temporada encerrada.</strong> Não há mais jogos para acompanhar ao vivo.</p>`;
        body.setAttribute("aria-busy", "false");
        return;
      }
      await draw(model);
    }

    controller.onVisibility = () => { if (!document.hidden) refresh(false); };
    main.querySelector("#live-refresh").addEventListener("click", () => refresh(false));
    document.addEventListener("visibilitychange", controller.onVisibility);
    controller.timer = setInterval(() => {
      if (!location.hash.startsWith("#/ao-vivo")) { controller.stop(); return; }
      if (!document.hidden) refresh(false);
    }, POLL_MS);
    refresh(true);
  }

  function stop() { if (active) active.stop(); }

  root.LiveRound = { render, stop, fetchLiveRows, prepare, tables, simulate, allocateSlots, parseScenario, liveDistribution, outcomeChances, RULES };
})(typeof window !== "undefined" ? window : globalThis);
