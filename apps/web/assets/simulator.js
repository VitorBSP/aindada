/* Simulador do usuário (ADR-0015). O visitante escolhe um modo, monta a simulação e salva; pode fazer quantas quiser,
   cada uma com o seu ID, e depois ir para outro modo.
   - Classificação: ordena a tabela final. Ordem impossível pela matemática não pode ser salva.
   - Vencedor: vitória do mandante, empate ou vitória do visitante em cada jogo.
   - Placar exato: o placar de cada jogo.
   Em Vencedor e Placar exato, a chave "Modelo sorteia" sorteia na hora um resultado concreto para cada jogo em branco,
   com as probabilidades que o Python publica no snapshot (`score_probabilities`): o navegador só sorteia, não refaz o
   modelo. Tudo fica no aparelho (localStorage). Com simulator-config.js preenchido, quem escolher "Participar" também
   salva no Supabase (simulator-cloud.js, até 3 simulações por modo), entra no ranking com um apelido e pode cadastrar
   um e-mail para avisos de pontuação. A pontuação aqui repete a do banco (migração 0003). */
(function () {
  "use strict";

  const MODES = {
    classificacao: {
      label: "Classificação", effort: "1 minuto",
      what: "Ordene os 20 clubes do 1º ao 20º.",
      scoring: "3 pontos por clube na posição exata, 1 a uma posição da certa, 10 pelo campeão e 3 por rebaixado acertado (máximo 82).",
    },
    vencedor: {
      label: "Vencedor", effort: "5 minutos",
      what: "Escolha mandante, empate ou visitante em cada jogo que falta.",
      scoring: "4 pontos por resultado certo.",
    },
    placar: {
      label: "Placar exato", effort: "10 minutos",
      what: "Dê o placar de cada jogo que falta.",
      scoring: "Placar exato 10; vencedor e gols do vencedor 7; vencedor e diferença de gols 6; vencedor e gols do perdedor 5; só o vencedor 4; placar invertido 2.",
    },
  };
  const OUTCOME_LABEL = { H: "mandante", D: "empate", A: "visitante" };
  // serie_a_2026.toml: Art. 6º (5 vagas de Libertadores pela liga), 7º (6 de Sul-Americana) e 8º (4 rebaixados).
  const LIBERTADORES_GROUPS = 4;
  const LIBERTADORES_SLOTS = 5;
  const SUDAMERICANA_SLOTS = 6;
  const RELEGATED = 4;
  const POINTS = { exact: 10, winnerGoals: 7, difference: 6, loserGoals: 5, winner: 4, inverted: 2 };
  const TABLE_POINTS = { exact: 3, near: 1, champion: 10, relegated: 3 };
  const SERVER_LIMIT = 3;
  const MAX_GOALS_INPUT = 20;
  const CODE_VERSION = "1";
  const MINUS = "−";
  // Mesma regra do banco (sim_profiles.nickname): letras com acento do português, números e _ . - espaço.
  const NICKNAME = /^[A-Za-zÀ-ÖØ-öø-ÿ0-9_. -]{3,20}$/;
  const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  const view = { store: null, season: null, link: null, linkNote: "" };
  const cloudState = { checked: false, user: null, profile: null, contact: null, community: null, scores: {}, status: "", open: "" };
  const cloudApi = () => (window.SimulatorCloud && window.SimulatorCloud.enabled ? window.SimulatorCloud : null);

  /* ---------------------------------------------------------------- Armazenamento local */

  const storageKey = (season) => `ainda-da:simulador:serie-a:${season}:v2`;

  function readStore(season) {
    try {
      const raw = window.localStorage.getItem(storageKey(season));
      const store = raw ? JSON.parse(raw) : null;
      if (store && store.version === 2) return store;
    } catch (error) { /* armazenamento indisponível: começa vazio */ }
    return { version: 2, drafts: {}, saved: [] };
  }

  function writeStore() {
    try { window.localStorage.setItem(storageKey(view.season), JSON.stringify(view.store)); } catch (error) { /* só nesta aba */ }
  }

  const newLocalId = () => Math.random().toString(36).slice(2, 6).toUpperCase();

  /* ---------------------------------------------------------------- Sorteio e tabela */

  function scoreSampler(match) {
    const matrix = match.score_probabilities;
    if (!Array.isArray(matrix) || !matrix.length) return null;
    const cells = [];
    let total = 0;
    matrix.forEach((row, home) => row.forEach((probability, away) => {
      if (probability > 0) { total += probability; cells.push([total, home, away]); }
    }));
    return total > 0 ? { cells, total } : null;
  }

  function draw(distribution) {
    const target = Math.random() * distribution.total;
    const cells = distribution.cells;
    let low = 0;
    let high = cells.length - 1;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (cells[middle][0] < target) low = middle + 1; else high = middle;
    }
    return [cells[low][1], cells[low][2]];
  }

  const outcomeOf = (home, away) => (home > away ? "H" : home < away ? "A" : "D");

  function newRows(clubIds) {
    const rows = {};
    clubIds.forEach((clubId) => { rows[clubId] = { club_id: clubId, played: 0, points: 0, wins: 0, draws: 0, losses: 0, goals_for: 0, goals_against: 0 }; });
    return rows;
  }

  function addResult(rows, result) {
    const home = rows[result.home];
    const away = rows[result.away];
    home.played += 1; away.played += 1;
    if (result.outcome === "H") { home.points += 3; home.wins += 1; away.losses += 1; }
    else if (result.outcome === "A") { away.points += 3; away.wins += 1; home.losses += 1; }
    else { home.points += 1; away.points += 1; home.draws += 1; away.draws += 1; }
    if (result.homeGoals !== null) {
      home.goals_for += result.homeGoals; home.goals_against += result.awayGoals;
      away.goals_for += result.awayGoals; away.goals_against += result.homeGoals;
    }
  }

  const goalDifference = (row) => row.goals_for - row.goals_against;
  const compareMain = (left, right) => right.points - left.points || right.wins - left.wins
    || goalDifference(right) - goalDifference(left) || right.goals_for - left.goals_for;

  /* Art. 15: pontos, vitórias, saldo, gols marcados e confronto direto só entre dois clubes (pontos e depois saldo
     nos jogos entre eles). Cartões e sorteio não dá para saber: o empate fica marcado. */
  function rankRows(rows, results) {
    const sorted = Object.values(rows).sort((left, right) => compareMain(left, right) || left.club_id.localeCompare(right.club_id));
    const ranked = [];
    for (let start = 0; start < sorted.length;) {
      let end = start + 1;
      while (end < sorted.length && compareMain(sorted[start], sorted[end]) === 0) end += 1;
      const group = sorted.slice(start, end);
      if (group.length === 2) {
        const [first, second] = group;
        const duel = { [first.club_id]: { points: 0, goals: 0 }, [second.club_id]: { points: 0, goals: 0 } };
        results.forEach((result) => {
          if (!duel[result.home] || !duel[result.away]) return;
          const points = { H: [3, 0], D: [1, 1], A: [0, 3] }[result.outcome];
          duel[result.home].points += points[0]; duel[result.away].points += points[1];
          if (result.homeGoals !== null) {
            duel[result.home].goals += result.homeGoals - result.awayGoals;
            duel[result.away].goals += result.awayGoals - result.homeGoals;
          }
        });
        const edge = duel[first.club_id].points - duel[second.club_id].points || duel[first.club_id].goals - duel[second.club_id].goals;
        if (edge !== 0) ranked.push(...(edge > 0 ? [first, second] : [second, first]).map((row) => ({ ...row, tie: null })));
        else ranked.push(...group.map((row) => ({ ...row, tie: "cartões ou sorteio" })));
      } else {
        ranked.push(...group.map((row) => ({ ...row, tie: group.length > 2 ? "cartões ou sorteio" : null })));
      }
      start = end;
    }
    return ranked.map((row, index) => ({ ...row, position: index + 1 }));
  }

  function zoneOf(position, total) {
    if (position === 1) return { key: "title", label: "Campeão" };
    if (position <= LIBERTADORES_GROUPS) return { key: "libertadores", label: "Libertadores" };
    if (position <= LIBERTADORES_SLOTS) return { key: "libertadores", label: "Pré-Libertadores" };
    if (position <= LIBERTADORES_SLOTS + SUDAMERICANA_SLOTS) return { key: "sudamericana", label: "Sul-Americana" };
    if (position > total - RELEGATED) return { key: "relegation", label: "Rebaixado" };
    return { key: "", label: "" };
  }

  /* ---------------------------------------------------------------- Pontuação (igual a sim_match_points) */

  function matchPoints(mode, pick, homeGoals, awayGoals) {
    if (mode === "vencedor") return pick === outcomeOf(homeGoals, awayGoals) ? POINTS.winner : 0;
    const [home, away] = pick;
    const sameWinner = Math.sign(home - away) === Math.sign(homeGoals - awayGoals);
    const decided = homeGoals !== awayGoals;
    if (home === homeGoals && away === awayGoals) return POINTS.exact;
    if (sameWinner && decided && Math.max(home, away) === Math.max(homeGoals, awayGoals)) return POINTS.winnerGoals;
    if (sameWinner && home - away === homeGoals - awayGoals) return POINTS.difference;
    if (sameWinner && decided && Math.min(home, away) === Math.min(homeGoals, awayGoals)) return POINTS.loserGoals;
    if (sameWinner) return POINTS.winner;
    if (home !== away && home === awayGoals && away === homeGoals) return POINTS.inverted;
    return 0;
  }

  const maxPerMatch = (mode) => (mode === "placar" ? POINTS.exact : POINTS.winner);

  /* ---------------------------------------------------------------- Links */

  function encodeLink(mode, entry, matchIndex, clubs) {
    if (mode === "classificacao") return CODE_VERSION + entry.order.map((clubId) => clubs.indexOf(clubId).toString(36)).join("");
    const picks = { ...(entry.sampled || {}), ...(entry.picks || {}) };
    return CODE_VERSION + "m" + Object.entries(picks).filter(([matchId]) => matchIndex.has(matchId))
      .map(([matchId, pick]) => matchIndex.get(matchId).toString(36).padStart(2, "0")
        + (mode === "vencedor" ? pick : pick[0].toString(36) + pick[1].toString(36))).join("");
  }

  function decodeLink(mode, code, clubs, matchList) {
    if (!code || code[0] !== CODE_VERSION) return null;
    const body = code.slice(1);
    if (mode === "classificacao") {
      const order = [...body].map((char) => clubs[parseInt(char, 36)]);
      const valid = order.length === clubs.length && new Set(order).size === clubs.length && order.every(Boolean);
      return valid ? { entry: { order }, ignored: 0 } : null;
    }
    const step = mode === "vencedor" ? 3 : 4;
    const picks = {};
    let ignored = 0;
    for (let start = 1; start + step <= body.length; start += step) {
      const match = matchList[parseInt(body.slice(start, start + 2), 36)];
      if (!match) return null;
      if (match.status === "finished") { ignored += 1; continue; }
      if (mode === "vencedor") {
        if (!OUTCOME_LABEL[body[start + 2]]) return null;
        picks[match.match_id] = body[start + 2];
      } else {
        const home = parseInt(body[start + 2], 36);
        const away = parseInt(body[start + 3], 36);
        if (Number.isNaN(home) || Number.isNaN(away)) return null;
        picks[match.match_id] = [home, away];
      }
    }
    return { entry: { picks, sampled: {}, model: false }, ignored };
  }

  /* ---------------------------------------------------------------- Página */

  function render(main, segments, context) {
    const { snapshot, escapeHtml, pct, crest, nameOf, formatShortDate } = context;
    const cloud = cloudApi();
    const season = snapshot.season;
    if (view.season !== season) { view.season = season; view.store = readStore(season); }
    const store = view.store;

    const matchList = [...snapshot.matches].sort((left, right) => left.match_id.localeCompare(right.match_id));
    const matchIndex = new Map(matchList.map((match, index) => [match.match_id, index]));
    const matchById = new Map(snapshot.matches.map((match) => [match.match_id, match]));
    const isFinished = (match) => match.status === "finished" && Number.isInteger(match.home_goals) && Number.isInteger(match.away_goals);
    const finished = snapshot.matches.filter(isFinished);
    const remaining = snapshot.matches.filter((match) => match.status !== "finished");
    const remainingIds = new Set(remaining.map((match) => match.match_id));
    const teamById = Object.fromEntries(snapshot.teams.map((team) => [team.club_id, team]));
    const clubIds = snapshot.teams.map((team) => team.club_id);
    const sortedClubs = [...clubIds].sort();
    const samplers = new Map(remaining.map((match) => [match.match_id, scoreSampler(match)]));
    const canSample = remaining.every((match) => samplers.get(match.match_id));
    const standingsOrder = [...snapshot.standings].sort((left, right) => left.position - right.position).map((row) => row.club_id);
    const currentPoints = Object.fromEntries(snapshot.standings.map((row) => [row.club_id, row.points]));
    const remainingByClub = Object.fromEntries(clubIds.map((clubId) => [clubId, 0]));
    remaining.forEach((match) => { remainingByClub[match.home_id] += 1; remainingByClub[match.away_id] += 1; });
    const maxPoints = Object.fromEntries(clubIds.map((clubId) => [clubId, currentPoints[clubId] + 3 * remainingByClub[clubId]]));
    // Faixa de posições que cada clube ainda alcança (empates contam a favor).
    const reach = Object.fromEntries(clubIds.map((clubId) => [clubId, {
      best: 1 + clubIds.filter((other) => other !== clubId && currentPoints[other] > maxPoints[clubId]).length,
      worst: clubIds.length - clubIds.filter((other) => other !== clubId && maxPoints[other] < currentPoints[clubId]).length,
    }]));

    const [first = "", second = "", third = ""] = segments;
    const clubCell = (clubId, size = 18) => `<span class="club-cell">${crest(clubId, size)}<span>${escapeHtml(nameOf(clubId))}</span></span>`;
    const shortName = (clubId) => escapeHtml((teamById[clubId] || {}).short_name || nameOf(clubId));
    const clock = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const currentSegments = () => location.hash.replace(/^#\/?/, "").split("/").slice(1).filter(Boolean);
    const onSimulator = () => location.hash.replace(/^#\/?/, "").startsWith("simular");
    const rerender = () => { if (onSimulator()) render(main, currentSegments(), context); };
    const formatDay = (iso) => new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });

    function emptyEntry(mode) {
      if (mode === "classificacao") return { order: [...snapshot.teams].sort((left, right) => left.expected_position - right.expected_position).map((team) => team.club_id) };
      return { picks: {}, sampled: {}, model: false };
    }

    /* Tira de um rascunho ou de uma simulação o que não vale mais (clube que não existe, jogo já disputado). */
    function sanitize(mode, entry) {
      if (!entry) return emptyEntry(mode);
      if (mode === "classificacao") {
        const valid = Array.isArray(entry.order) && entry.order.length === clubIds.length && clubIds.every((clubId) => entry.order.includes(clubId));
        return valid ? { order: [...entry.order] } : emptyEntry(mode);
      }
      const keep = (picks) => Object.fromEntries(Object.entries(picks || {}).filter(([matchId]) => remainingIds.has(matchId)));
      return { picks: keep(entry.picks), sampled: canSample ? keep(entry.sampled) : {}, model: Boolean(entry.model) && canSample };
    }

    /* ---------------- Contas e servidor */

    const setStatus = (text) => {
      cloudState.status = text;
      const target = document.getElementById("sim-cloud-status");
      if (target) target.textContent = text;
    };

    function entryFromServer(row) {
      if (row.mode === "classificacao") return { order: row.payload.order };
      const picks = row.payload.picks || {};
      const sampledIds = new Set(row.payload.sampled || []);
      return {
        picks: Object.fromEntries(Object.entries(picks).filter(([matchId]) => !sampledIds.has(matchId))),
        sampled: Object.fromEntries(Object.entries(picks).filter(([matchId]) => sampledIds.has(matchId))),
        model: Boolean(row.assist),
      };
    }

    async function refreshScores() {
      try {
        const rows = await cloud.myScores(season);
        cloudState.scores = Object.fromEntries(rows.map((row) => [row.simulation_id, row]));
      } catch (error) { cloudState.scores = {}; }
    }

    async function initCloud() {
      if (!cloud || cloudState.checked) return;
      cloudState.checked = true;
      try {
        cloudState.user = await cloud.currentUser();
        if (cloudState.user) {
          [cloudState.profile, cloudState.contact] = await Promise.all([cloud.profile(), cloud.contact()]);
          const rows = await cloud.loadSimulations(season);
          rows.forEach((row) => {
            if (store.saved.some((item) => item.server_id === row.id)) return;
            // Simulações completas guardam todos os jogos de quando foram salvas; os encerrados continuam pontuando.
            store.saved.push({ local_id: `S${row.id}`, server_id: row.id, mode: row.mode, created_at: row.created_at, updated_at: row.updated_at, entry: entryFromServer(row) });
          });
          writeStore();
          await refreshScores();
        }
      } catch (error) {
        cloudState.status = `Servidor indisponível agora (${error.message}). As simulações continuam salvas neste aparelho.`;
      }
      try { cloudState.community = await cloud.community(season); } catch (error) { cloudState.community = null; }
      rerender();
    }

    function serverCount(mode) { return store.saved.filter((item) => item.mode === mode && item.server_id).length; }

    /* Envia uma simulação ao servidor; devolve um texto sobre o que aconteceu. */
    async function pushToServer(item) {
      if (!cloud || !cloudState.user) return "";
      if (!item.server_id && serverCount(item.mode) >= SERVER_LIMIT) return ` No servidor cabem ${SERVER_LIMIT} por modo: esta ficou só neste aparelho e fora do ranking.`;
      try {
        const stored = await cloud.saveSimulation(season, item.mode, item.entry, item.server_id, finalOrderOf(item.mode, item.entry));
        if (!stored) return "";
        item.server_id = stored.id;
        writeStore();
        return ` Enviada ao servidor como #${stored.id}.${droppedNote(item, stored.payload)}`;
      } catch (error) {
        return ` Não foi ao servidor (${error.message}); continua salva neste aparelho.`;
      }
    }

    function droppedNote(item, payload) {
      if (item.mode === "classificacao") return payload.ranked_order ? "" : " Esta ordem não conta para o ranking: a trava da temporada já passou.";
      const sent = Object.keys({ ...item.entry.sampled, ...item.entry.picks });
      const kept = new Set(Object.keys(payload.picks || {}));
      const dropped = sent.filter((matchId) => !kept.has(matchId)).length;
      if (!dropped) return "";
      return dropped === 1 ? " 1 palpite é de jogo já travado e não conta para o ranking." : ` ${dropped} palpites são de jogos já travados e não contam para o ranking.`;
    }

    /* Mesma trava do servidor (supabase_sync.match_lock_utc): o pontapé ou, sem ele, 00:00 de Brasília do dia. */
    function lockTime(match) {
      return match.kickoff_utc ? new Date(match.kickoff_utc) : new Date(`${match.match_date}T00:00:00-03:00`);
    }

    function lockLabel(match) {
      if (!cloud || !cloudState.user) return "";
      const lock = lockTime(match);
      if (Number.isNaN(lock.getTime())) return "";
      if (lock <= new Date()) return `<span class="sim-lock is-locked">não conta mais para o ranking</span>`;
      return `<span class="sim-lock">vale para o ranking até ${lock.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>`;
    }

    function crowdForMatch(match) {
      const data = cloudState.community && cloudState.community.matches ? cloudState.community.matches[match.match_id] : null;
      if (!data) return "";
      return `<span class="sim-crowd" title="Pelo menos ${data.users_at_least} visitantes com palpite neste jogo; arredondado de 5 em 5 pontos">visitantes: ${pct(data.H)} · ${pct(data.D)} · ${pct(data.A)}</span>`;
    }

    /* ---------------- Pontuação das simulações */

    function pickScore(mode, entry) {
      const picks = { ...(entry.sampled || {}), ...(entry.picks || {}) };
      let points = 0;
      let scored = 0;
      let open = 0;
      Object.entries(picks).forEach(([matchId, pick]) => {
        const match = matchById.get(matchId);
        if (!match) return;
        if (isFinished(match)) { scored += 1; points += matchPoints(mode, pick, match.home_goals, match.away_goals); }
        else open += 1;
      });
      const per = maxPerMatch(mode);
      return { points, outOf: scored * per, scored, ceiling: points + open * per, total: (scored + open) * per };
    }

    /* Classificação comparada com a tabela de hoje (como se o campeonato acabasse agora) e o teto que ainda dá. */
    function tableScore(order) {
      const total = order.length;
      let points = 0;
      let ceiling = 0;
      order.forEach((clubId, index) => {
        const predicted = index + 1;
        const actual = standingsOrder.indexOf(clubId) + 1;
        points += predicted === actual ? TABLE_POINTS.exact : Math.abs(predicted - actual) === 1 ? TABLE_POINTS.near : 0;
        const range = reach[clubId];
        if (predicted >= range.best && predicted <= range.worst) ceiling += TABLE_POINTS.exact;
        else if (predicted + 1 >= range.best && predicted - 1 <= range.worst) ceiling += TABLE_POINTS.near;
      });
      if (order[0] === standingsOrder[0]) points += TABLE_POINTS.champion;
      if (reach[order[0]].best === 1) ceiling += TABLE_POINTS.champion;
      order.slice(total - RELEGATED).forEach((clubId) => {
        if (standingsOrder.indexOf(clubId) >= total - RELEGATED) points += TABLE_POINTS.relegated;
        if (reach[clubId].worst > total - RELEGATED) ceiling += TABLE_POINTS.relegated;
      });
      const maximum = total * TABLE_POINTS.exact + TABLE_POINTS.champion + RELEGATED * TABLE_POINTS.relegated;
      return { points, ceiling, maximum };
    }

    function impossiblePairs(order) {
      const problems = new Map();
      order.forEach((upper, upperIndex) => {
        order.slice(upperIndex + 1).forEach((lower) => {
          if (maxPoints[upper] < currentPoints[lower] && !problems.has(upper)) problems.set(upper, lower);
        });
      });
      return problems;
    }

    /* ---------------- Tabela final de Vencedor e Placar exato */

    function effectivePicks(entry) { return { ...(entry.sampled || {}), ...(entry.picks || {}) }; }

    function resultsFor(mode, entry) {
      const results = finished.map((match) => ({ home: match.home_id, away: match.away_id, outcome: outcomeOf(match.home_goals, match.away_goals), homeGoals: match.home_goals, awayGoals: match.away_goals }));
      const picks = effectivePicks(entry);
      remaining.forEach((match) => {
        const pick = picks[match.match_id];
        if (pick === undefined) return;
        if (mode === "vencedor") results.push({ home: match.home_id, away: match.away_id, outcome: pick, homeGoals: null, awayGoals: null });
        else results.push({ home: match.home_id, away: match.away_id, outcome: outcomeOf(pick[0], pick[1]), homeGoals: pick[0], awayGoals: pick[1] });
      });
      return results;
    }

    function finalTable(mode, entry) {
      const results = resultsFor(mode, entry);
      const rows = newRows(clubIds);
      results.forEach((result) => addResult(rows, result));
      return rankRows(rows, results);
    }

    function isComplete(entry) { const picks = effectivePicks(entry); return remaining.every((match) => picks[match.match_id] !== undefined); }

    function finalOrderOf(mode, entry) {
      if (mode === "classificacao" || !isComplete(entry)) return null;
      return finalTable(mode, entry).map((row) => row.club_id);
    }

    /* ---------------- Moldura */

    function tabs(active) {
      const items = [["", "Início"], ...Object.entries(MODES).map(([key, item]) => [key, item.label])];
      if (cloud) items.push(["ranking", "Ranking"], ["visitantes", "Visitantes"]);
      return `<nav class="tabs sim-tabs" aria-label="Simulador">${items.map(([key, label]) =>
        `<a href="#/simular${key ? `/${key}` : ""}" ${key === active ? 'aria-current="page"' : ""}>${label}</a>`).join("")}</nav>`;
    }

    function storageNote() {
      if (!cloud) return "Suas simulações ficam salvas só neste aparelho, sem conta e sem envio para servidor.";
      return "Suas simulações ficam salvas neste aparelho. Ao abrir o simulador, o navegador baixa a biblioteca do Supabase pelo jsDelivr e consulta a média dos visitantes no servidor do AInda dá? (Supabase, nos Estados Unidos). Se você participar, as simulações também vão para lá, ligadas a uma conta sem nome. O e-mail é opcional e nunca aparece para ninguém; no ranking só aparece o apelido.";
    }

    function shell(active, title, lede, body) {
      main.innerHTML = `
        <span class="kicker">Simulador</span>
        <h1>${title}</h1>
        <p class="lede">${lede}</p>
        ${tabs(active)}
        ${accountPanel()}
        ${body}
        <p class="note sim-footnote">${storageNote()} Vagas pela liga em 2026: 1º a 4º na fase de grupos da Libertadores, 5º na fase preliminar, 6º a 11º na Sul-Americana, 17º a 20º rebaixados (regulamento, Art. 6º a 8º). Títulos da Copa do Brasil, da Libertadores e da Sul-Americana podem empurrar essas vagas para baixo; isso o simulador não calcula.</p>`;
      bindAccount();
    }

    /* ---------------- Painel da conta */

    function accountPanel() {
      if (!cloud) return "";
      const status = `<p class="note" id="sim-cloud-status" aria-live="polite">${escapeHtml(cloudState.status)}</p>`;
      if (!cloudState.checked) return `<div class="sim-account">${status}</div>`;
      const user = cloudState.user;
      if (!user) {
        const login = cloudState.open === "login" ? `<form class="sim-form" id="sim-login-form">
            <label>E-mail ligado à sua participação <input type="email" required autocomplete="email" id="sim-login-email"></label>
            <button type="submit">Enviar link de entrada</button></form>` : "";
        return `<div class="sim-account"><p><strong>Entre no ranking e compare com os outros visitantes.</strong> Participe para enviar suas simulações ao servidor (até ${SERVER_LIMIT} por modo), ver o que os outros visitantes acham e aparecer no ranking com um apelido. Não precisa de cadastro.</p>
          <p><button type="button" class="sim-button" id="sim-join">Participar</button> <button type="button" class="link-button" id="sim-login-open">Já participo em outro aparelho</button></p>${login}${status}</div>`;
      }
      const profile = cloudState.profile || {};
      const contact = cloudState.contact;
      const who = profile.nickname ? `como <strong>${escapeHtml(profile.nickname)}</strong>${profile.show_in_ranking ? " · no ranking" : " · fora do ranking"}` : "sem apelido · fora do ranking";
      const notices = contact && contact.notify ? "avisos por e-mail ligados" : "sem avisos por e-mail";
      const forms = {
        profile: `<form class="sim-form" id="sim-profile-form">
          <label>Apelido <input type="text" id="sim-nickname" maxlength="20" minlength="3" value="${escapeHtml(profile.nickname || "")}" autocomplete="nickname"></label>
          <label class="sim-check"><input type="checkbox" id="sim-in-ranking" ${profile.show_in_ranking ? "checked" : ""}> Aparecer no ranking com este apelido</label>
          <p class="note">De 3 a 20 letras, números, espaço, ponto, hífen ou _. Não use seu e-mail nem seu nome completo: o apelido é a única coisa que os outros veem.</p>
          <button type="submit">Salvar</button></form>`,
        contact: `<form class="sim-form" id="sim-contact-form">
          <label>E-mail para avisos <input type="email" required autocomplete="email" id="sim-contact-email" value="${escapeHtml(contact ? contact.email : "")}"></label>
          <label class="sim-check"><input type="checkbox" id="sim-contact-notify" ${!contact || contact.notify ? "checked" : ""}> Quero receber minha pontuação por e-mail</label>
          <p class="note">Usamos só para avisar da sua pontuação. Ninguém mais vê o e-mail, e ele sai do servidor quando você apagar a participação.</p>
          <button type="submit">Salvar e-mail</button>${contact ? ` <button type="button" class="link-button" id="sim-contact-delete">Remover e-mail</button>` : ""}</form>`,
        email: `<form class="sim-form" id="sim-email-form">
          <label>E-mail para entrar em outro aparelho <input type="email" required autocomplete="email" id="sim-email"></label>
          <p class="note">Enviamos um link de confirmação. Depois, use o mesmo e-mail para entrar em outro aparelho.</p>
          <button type="submit">Enviar link de confirmação</button></form>`,
      };
      const loginAction = user.hasEmail ? "login por e-mail ligado" : `<button type="button" class="link-button" id="sim-email-open">Usar em outro aparelho</button>`;
      return `<div class="sim-account"><p>Participando ${who} · ${notices}.</p>
        <p class="sim-account-actions"><button type="button" class="link-button" id="sim-profile-open">Apelido e ranking</button> · <button type="button" class="link-button" id="sim-contact-open">Avisos por e-mail</button> · ${loginAction} · <button type="button" class="link-button" id="sim-signout">Sair</button> · <button type="button" class="link-button" id="sim-delete">Apagar minha participação</button></p>
        ${forms[cloudState.open] || ""}${status}</div>`;
    }

    function bindAccount() {
      if (!cloud) return;
      const on = (id, event, handler) => { const element = document.getElementById(id); if (element) element.addEventListener(event, handler); };
      const toggle = (panel) => () => { cloudState.open = cloudState.open === panel ? "" : panel; rerender(); };
      ["login", "profile", "contact", "email"].forEach((panel) => on(`sim-${panel}-open`, "click", toggle(panel)));
      on("sim-join", "click", async () => {
        setStatus("Entrando…");
        try {
          cloudState.user = await cloud.join();
          [cloudState.profile, cloudState.contact] = await Promise.all([cloud.profile(), cloud.contact()]);
          const notes = [];
          for (const item of store.saved) if (!item.server_id) notes.push(await pushToServer(item));
          await refreshScores();
          cloudState.open = "profile";
          cloudState.status = `Participando.${notes.join("")} Escolha um apelido para aparecer no ranking.`;
        } catch (error) {
          cloudState.status = `Não deu para participar agora (${error.message}).`;
        }
        rerender();
      });
      on("sim-login-form", "submit", async (event) => {
        event.preventDefault();
        try {
          await cloud.signInWithEmail(document.getElementById("sim-login-email").value.trim());
          setStatus("Enviamos um link para esse e-mail. Abra-o neste aparelho para entrar.");
        } catch (error) { setStatus(`Não deu para enviar o link (${error.message}).`); }
      });
      on("sim-email-form", "submit", async (event) => {
        event.preventDefault();
        try {
          await cloud.linkEmail(document.getElementById("sim-email").value.trim());
          setStatus("Enviamos um link de confirmação. Depois de confirmar, use o mesmo e-mail para entrar em outro aparelho.");
        } catch (error) { setStatus(`Não deu para ligar o e-mail (${error.message}).`); }
      });
      on("sim-contact-form", "submit", async (event) => {
        event.preventDefault();
        const email = document.getElementById("sim-contact-email").value.trim();
        if (!EMAIL.test(email)) { setStatus("Confira o e-mail."); return; }
        try {
          await cloud.saveContact(email, document.getElementById("sim-contact-notify").checked);
          cloudState.contact = await cloud.contact();
          cloudState.open = "";
          cloudState.status = "E-mail salvo para os avisos de pontuação.";
          rerender();
        } catch (error) { setStatus(`Não deu para salvar o e-mail (${error.message}).`); }
      });
      on("sim-contact-delete", "click", async () => {
        try {
          await cloud.deleteContact();
          cloudState.contact = null; cloudState.open = ""; cloudState.status = "E-mail removido.";
          rerender();
        } catch (error) { setStatus(`Não deu para remover (${error.message}).`); }
      });
      on("sim-profile-form", "submit", async (event) => {
        event.preventDefault();
        const nickname = document.getElementById("sim-nickname").value.trim();
        const inRanking = document.getElementById("sim-in-ranking").checked;
        if (nickname.includes("@")) { setStatus("O apelido não pode ter @: não use seu e-mail."); return; }
        if (nickname && !NICKNAME.test(nickname)) { setStatus("Apelido com 3 a 20 letras, números, espaço, ponto, hífen ou _."); return; }
        if (inRanking && !nickname) { setStatus("Para aparecer no ranking, escolha um apelido."); return; }
        try {
          await cloud.saveProfile(nickname, inRanking);
          cloudState.profile = await cloud.profile();
          cloudState.open = "";
          cloudState.status = "Apelido salvo.";
          rerender();
        } catch (error) { setStatus(`Não deu para salvar (${error.message}).`); }
      });
      const leave = (message) => {
        cloudState.user = null; cloudState.profile = null; cloudState.contact = null; cloudState.scores = {};
        cloudState.open = ""; cloudState.status = message;
        store.saved.forEach((item) => { item.server_id = null; });
        writeStore();
        rerender();
      };
      on("sim-signout", "click", async () => {
        const warning = cloudState.user && !cloudState.user.hasEmail
          ? "Sua participação não tem login por e-mail: ao sair, você não consegue voltar a ela. Sair mesmo assim?"
          : "Sair da participação neste aparelho? As simulações continuam salvas aqui.";
        if (!window.confirm(warning)) return;
        try { await cloud.signOut(); } catch (error) { /* sai localmente mesmo assim */ }
        leave("Você saiu.");
      });
      on("sim-delete", "click", async () => {
        if (!window.confirm("Apagar sua participação? Saem do servidor o apelido, os e-mails e as simulações salvas lá, sem volta. As simulações continuam neste aparelho.")) return;
        try { await cloud.deleteAccount(); leave("Participação apagada do servidor."); }
        catch (error) { setStatus(`Não deu para apagar agora (${error.message}).`); }
      });
    }

    /* ---------------- Início: escolher o modo e ver as simulações */

    function simulationLabel(item) { return item.server_id ? `#${item.server_id}` : `#${item.local_id}`; }

    function scoreSummary(item) {
      if (item.mode === "classificacao") {
        const score = tableScore(item.entry.order);
        return `<strong>${score.points}</strong> pontos com a tabela de hoje · até <strong>${score.ceiling}</strong> de ${score.maximum} possíveis`;
      }
      const score = pickScore(item.mode, item.entry);
      const server = item.server_id && cloudState.scores[item.server_id];
      const counted = server ? ` · no ranking: ${server.points} de ${server.max_points}` : "";
      if (!score.scored) return `Nenhum jogo terminou ainda · até <strong>${score.ceiling}</strong> pontos possíveis${counted}`;
      return `<strong>${score.points}</strong> de ${score.outOf} pontos em ${score.scored} ${score.scored === 1 ? "jogo" : "jogos"} · ainda dá para chegar a <strong>${score.ceiling}</strong>${counted}`;
    }

    function renderHome() {
      const cards = Object.entries(MODES).map(([key, item]) => {
        const count = store.saved.filter((saved) => saved.mode === key).length;
        return `<article class="sim-mode-card">
          <h2>${item.label}</h2>
          <p class="sim-mode-what">${item.what}</p>
          <p class="note">${item.scoring}</p>
          <p class="sim-mode-meta">${item.effort}${count ? ` · ${count} ${count === 1 ? "simulação salva" : "simulações salvas"}` : ""}</p>
          <a class="sim-button" href="#/simular/${key}">${store.drafts[key] ? "Continuar" : "Começar"}</a>
        </article>`;
      }).join("");
      const saved = [...store.saved].sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at)));
      const list = saved.length ? `<div class="table-wrap"><table class="sim-table sim-saved">
          <thead><tr><th>Simulação</th><th>Modo</th><th>Salva em</th><th>Pontuação</th><th><span class="visually-hidden">Ações</span></th></tr></thead>
          <tbody>${saved.map((item) => `<tr>
            <td><a href="#/simular/${item.mode}/s/${encodeURIComponent(item.local_id)}">${escapeHtml(simulationLabel(item))}</a>${item.server_id ? ` <span class="sim-tag">no servidor</span>` : ""}</td>
            <td>${MODES[item.mode].label}</td>
            <td>${escapeHtml(formatDay(item.updated_at))}</td>
            <td>${scoreSummary(item)}</td>
            <td><button type="button" class="link-button" data-delete="${escapeHtml(item.local_id)}">Excluir</button></td></tr>`).join("")}</tbody></table></div>`
        : `<p class="note">Você ainda não salvou nenhuma simulação. Escolha um modo acima.</p>`;
      shell("", "E se o campeonato terminar do seu jeito?", "Escolha um modo, monte a sua simulação e salve. Dá para fazer quantas quiser, em qualquer modo: cada uma ganha um ID e a própria pontuação.",
        `<div class="sim-mode-grid">${cards}</div>
         <h2>Minhas simulações</h2>
         <p class="note">A pontuação conta os jogos que já terminaram. Na Classificação, ela compara com a tabela de hoje e mostra o máximo que ainda dá para fazer.</p>
         ${list}`);
      main.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", async () => {
        const item = store.saved.find((saved) => saved.local_id === button.dataset.delete);
        if (!item || !window.confirm(`Excluir a simulação ${simulationLabel(item)}?${item.server_id ? " Ela sai também do servidor e do ranking." : ""}`)) return;
        if (item.server_id && cloud && cloudState.user) {
          try { await cloud.deleteSimulation(item.server_id); } catch (error) { setStatus(`Não deu para excluir no servidor (${error.message}).`); return; }
        }
        store.saved = store.saved.filter((saved) => saved !== item);
        writeStore();
        cloudState.status = `Simulação ${simulationLabel(item)} excluída.`;
        renderHome();
      }));
    }

    /* ---------------- Editor */

    function openEditor(mode, savedId, code) {
      if (code) {
        const decoded = decodeLink(mode, code, sortedClubs, matchList);
        if (decoded) {
          view.link = { mode, entry: sanitize(mode, decoded.entry) };
          view.linkNote = decoded.ignored ? ` ${decoded.ignored} ${decoded.ignored === 1 ? "palpite era de um jogo que já aconteceu e ficou" : "palpites eram de jogos que já aconteceram e ficaram"} de fora.` : "";
        } else {
          view.link = null;
          view.linkNote = "Não deu para abrir a simulação do link: ele está incompleto ou é de outra temporada.";
        }
        history.replaceState(null, "", `#/simular/${mode}`);
      }
      const savedItem = savedId ? store.saved.find((item) => item.local_id === savedId && item.mode === mode) : null;
      const fromLink = !savedItem && Boolean(view.link && view.link.mode === mode);
      let entry;
      if (savedItem) {
        // Uma simulação salva mantém os jogos que já terminaram (eles pontuam); o editor mostra só os que faltam.
        entry = savedItem.entry;
      } else if (fromLink) {
        entry = view.link.entry;
      } else {
        store.drafts[mode] = sanitize(mode, store.drafts[mode]);
        entry = store.drafts[mode];
      }
      const persist = () => { if (!fromLink) writeStore(); };
      if (mode === "classificacao") renderTable(entry, savedItem, fromLink, persist);
      else renderPicks(mode, entry, savedItem, fromLink, persist);
    }

    function editorHeader(mode, savedItem, fromLink) {
      const where = savedItem ? `Editando a simulação <strong>${escapeHtml(simulationLabel(savedItem))}</strong>. <a href="#/simular/${mode}">Começar outra</a> · <a href="#/simular">Voltar ao início</a>`
        : fromLink ? `Simulação aberta por link.${escapeHtml(view.linkNote)} <button type="button" class="link-button" id="sim-link-keep">Usar como meu rascunho</button> · <button type="button" class="link-button" id="sim-link-drop">Voltar ao meu rascunho</button>`
          : "Rascunho novo: ao salvar, ele vira uma simulação com ID próprio, e o rascunho volta ao começo.";
      const error = !fromLink && view.linkNote && !view.link ? `<p class="sim-banner" role="status">${escapeHtml(view.linkNote)}</p>` : "";
      return `${error}<p class="sim-where">${where}</p>`;
    }

    function bindEditorHeader(mode) {
      const keep = document.getElementById("sim-link-keep");
      if (keep) keep.addEventListener("click", () => { store.drafts[mode] = view.link.entry; view.link = null; view.linkNote = ""; writeStore(); rerender(); });
      const drop = document.getElementById("sim-link-drop");
      if (drop) drop.addEventListener("click", () => { view.link = null; view.linkNote = ""; rerender(); });
      if (!view.link) view.linkNote = "";
    }

    function saveBar(savedItem, blocked) {
      const reason = blocked ? `<p class="sim-warning">${blocked}</p>` : "";
      const buttons = savedItem
        ? `<button type="button" class="sim-button" id="sim-save" ${blocked ? "disabled" : ""}>Salvar alterações em ${escapeHtml(simulationLabel(savedItem))}</button> <button type="button" class="link-button" id="sim-save-new" ${blocked ? "disabled" : ""}>Salvar como nova</button>`
        : `<button type="button" class="sim-button" id="sim-save" ${blocked ? "disabled" : ""}>Salvar simulação</button>`;
      return `<div class="sim-savebar">${reason}${buttons} <button type="button" class="link-button" id="sim-share">Copiar link</button><span class="note" id="sim-save-status" aria-live="polite"></span></div>`;
    }

    function bindSaveBar(mode, entry, savedItem) {
      const status = (text) => { const target = document.getElementById("sim-save-status"); if (target) target.textContent = text; };
      const save = async (asNew) => {
        const now = new Date().toISOString();
        const copy = JSON.parse(JSON.stringify(entry));
        let item = savedItem && !asNew ? savedItem : null;
        if (item) { item.entry = copy; item.updated_at = now; }
        else {
          item = { local_id: newLocalId(), server_id: null, mode, created_at: now, updated_at: now, entry: copy };
          store.saved.push(item);
          if (view.link && view.link.mode === mode) view.link = null;
          else if (!savedItem) store.drafts[mode] = emptyEntry(mode);
        }
        writeStore();
        status("Salvando…");
        const note = await pushToServer(item);
        if (cloud && cloudState.user) await refreshScores();
        cloudState.status = `Simulação ${simulationLabel(item)} salva às ${clock()}.${note}`;
        const target = `#/simular/${mode}/s/${encodeURIComponent(item.local_id)}`;
        if (location.hash === target) rerender(); else location.hash = target;
      };
      const saveButton = document.getElementById("sim-save");
      if (saveButton) saveButton.addEventListener("click", () => save(false));
      const saveNew = document.getElementById("sim-save-new");
      if (saveNew) saveNew.addEventListener("click", () => save(true));
      document.getElementById("sim-share").addEventListener("click", async () => {
        const url = `${location.href.split("#")[0]}#/simular/${mode}/l/${encodeLink(mode, entry, matchIndex, sortedClubs)}`;
        try { await navigator.clipboard.writeText(url); status("Link copiado."); }
        catch (error) {
          const target = document.getElementById("sim-save-status");
          target.innerHTML = `Copie o link: <input class="sim-share-url" readonly value="${escapeHtml(url)}" aria-label="Link da simulação">`;
          const input = target.querySelector("input"); input.focus(); input.select();
        }
      });
    }

    /* ---------------- Classificação */

    function renderTable(entry, savedItem, fromLink, persist, focusClub, focusDirection) {
      const order = entry.order;
      const problems = impossiblePairs(order);
      const total = order.length;
      const score = tableScore(order);
      const rows = order.map((clubId, index) => {
        const position = index + 1;
        const zone = zoneOf(position, total);
        const problem = problems.get(clubId);
        const range = reach[clubId];
        return `<li class="sim-quick-row ${zone.key ? `zone-${zone.key}` : ""} ${problem ? "is-impossible" : ""}" draggable="true" data-club="${escapeHtml(clubId)}">
          <span class="sim-pos">${position}º</span>
          ${clubCell(clubId, 22)}
          <span class="sim-zone">${zone.label}</span>
          <span class="sim-model" title="Probabilidade do modelo de terminar exatamente nesta posição; entre parênteses, as posições que o clube ainda alcança">modelo ${pct(teamById[clubId].position_probabilities[index])} <span class="sim-reach">(${range.best}º–${range.worst}º)</span></span>
          <span class="sim-move">
            <button type="button" data-move="-1" aria-label="Subir ${escapeHtml(nameOf(clubId))}" ${index === 0 ? "disabled" : ""}>▲</button>
            <button type="button" data-move="1" aria-label="Descer ${escapeHtml(nameOf(clubId))}" ${index === total - 1 ? "disabled" : ""}>▼</button>
          </span>
          ${problem ? `<span class="sim-warning">Impossível: chega a no máximo ${maxPoints[clubId]} pontos e ${escapeHtml(nameOf(problem))} já tem ${currentPoints[problem]}.</span>` : ""}
        </li>`;
      }).join("");
      const blocked = problems.size ? `Não dá para salvar: ${problems.size === 1 ? "uma posição é impossível" : `${problems.size} posições são impossíveis`} pela matemática. Veja os avisos na lista.` : "";
      const relegated = order.slice(total - RELEGATED);
      shell("classificacao", "Classificação", `${MODES.classificacao.what} ${MODES.classificacao.scoring}`, `
        ${editorHeader("classificacao", savedItem, fromLink)}
        <div class="sim-scorebox">
          <p><strong>${score.points}</strong> pontos se o campeonato acabasse hoje · até <strong>${score.ceiling}</strong> de ${score.maximum} possíveis no fim</p>
          <p class="note">Seu campeão: ${clubCell(order[0])} (modelo: ${pct(teamById[order[0]].title)}) · Seus rebaixados: ${relegated.map((clubId) => `${clubCell(clubId)} ${pct(teamById[clubId].relegation)}`).join(" · ")}</p>
        </div>
        <p class="sim-toolbar"><button type="button" class="link-button" id="sim-reset-model">Começar da ordem do modelo</button> · <button type="button" class="link-button" id="sim-reset-table">Começar da tabela atual</button></p>
        <ol class="sim-quick" aria-label="Sua tabela final">${rows}</ol>
        <p class="note">"modelo" é a probabilidade, nas simulações do modelo, de o clube terminar exatamente naquela posição; entre parênteses, as posições que ele ainda alcança pela matemática. Arraste as linhas ou use as setas.</p>
        ${saveBar(savedItem, blocked)}`);
      bindEditorHeader("classificacao");
      bindSaveBar("classificacao", entry, savedItem);
      const rerenderTable = (club, direction) => renderTable(entry, savedItem, fromLink, persist, club, direction);
      const move = (clubId, target) => {
        const next = entry.order.filter((item) => item !== clubId);
        next.splice(Math.max(0, Math.min(next.length, target)), 0, clubId);
        entry.order = next;
        persist();
      };
      main.querySelectorAll(".sim-quick-row button[data-move]").forEach((button) => button.addEventListener("click", () => {
        const clubId = button.closest(".sim-quick-row").dataset.club;
        move(clubId, entry.order.indexOf(clubId) + Number(button.dataset.move));
        rerenderTable(clubId, button.dataset.move);
      }));
      let dragged = null;
      main.querySelectorAll(".sim-quick-row").forEach((row) => {
        row.addEventListener("dragstart", (event) => { dragged = row.dataset.club; event.dataTransfer.effectAllowed = "move"; row.classList.add("dragging"); });
        row.addEventListener("dragend", () => row.classList.remove("dragging"));
        row.addEventListener("dragover", (event) => { event.preventDefault(); row.classList.add("drop-target"); });
        row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
        row.addEventListener("drop", (event) => {
          event.preventDefault();
          if (!dragged || dragged === row.dataset.club) return;
          move(dragged, entry.order.indexOf(row.dataset.club));
          rerenderTable();
        });
      });
      document.getElementById("sim-reset-model").addEventListener("click", () => { entry.order = emptyEntry("classificacao").order; persist(); rerenderTable(); });
      document.getElementById("sim-reset-table").addEventListener("click", () => { entry.order = [...standingsOrder]; persist(); rerenderTable(); });
      if (focusClub) {
        const button = main.querySelector(`.sim-quick-row[data-club="${CSS.escape(focusClub)}"] button[data-move="${focusDirection}"]`)
          || main.querySelector(`.sim-quick-row[data-club="${CSS.escape(focusClub)}"] button:not([disabled])`);
        if (button) button.focus();
      }
    }

    /* ---------------- Vencedor e Placar exato */

    function sampleMatch(mode, match) {
      if (mode === "vencedor") {
        const target = Math.random();
        return target < match.p_home ? "H" : target < match.p_home + match.p_draw ? "D" : "A";
      }
      return draw(samplers.get(match.match_id));
    }

    function fillWithModel(mode, entry, redraw) {
      if (redraw) entry.sampled = {};
      remaining.forEach((match) => {
        if (entry.picks[match.match_id] === undefined && entry.sampled[match.match_id] === undefined) entry.sampled[match.match_id] = sampleMatch(mode, match);
      });
    }

    function matchControl(mode, match, entry) {
      const own = entry.picks[match.match_id];
      const sampled = own === undefined ? entry.sampled[match.match_id] : undefined;
      const value = own !== undefined ? own : sampled;
      const label = `${nameOf(match.home_id)} x ${nameOf(match.away_id)}`;
      const tag = sampled !== undefined ? `<span class="sim-tag is-model">sorteado pelo modelo</span>` : own !== undefined ? "" : `<span class="sim-tag">em branco</span>`;
      if (mode === "vencedor") {
        const option = (key, text, probability) => `<button type="button" class="sim-choice ${value === key ? (sampled !== undefined ? "is-model" : "chosen") : ""}" data-match="${escapeHtml(match.match_id)}" data-pick="${key}" aria-pressed="${value === key}">
          <span>${text}</span><span class="sim-prob">${pct(probability)}</span></button>`;
        return `<div class="sim-choices" role="group" aria-label="${escapeHtml(label)}">
          ${option("H", shortName(match.home_id), match.p_home)}${option("D", "Empate", match.p_draw)}${option("A", shortName(match.away_id), match.p_away)}</div>${tag}`;
      }
      const goals = (side) => (value !== undefined ? value[side] : "");
      const probability = value !== undefined && match.score_probabilities && match.score_probabilities[value[0]] ? match.score_probabilities[value[0]][value[1]] || 0 : null;
      return `<span class="sim-score ${sampled !== undefined ? "is-model" : ""}">
        <input type="number" inputmode="numeric" min="0" max="${MAX_GOALS_INPUT}" value="${goals(0)}" data-match="${escapeHtml(match.match_id)}" data-side="0" aria-label="Gols de ${escapeHtml(nameOf(match.home_id))} contra ${escapeHtml(nameOf(match.away_id))}">
        <span aria-hidden="true">x</span>
        <input type="number" inputmode="numeric" min="0" max="${MAX_GOALS_INPUT}" value="${goals(1)}" data-match="${escapeHtml(match.match_id)}" data-side="1" aria-label="Gols de ${escapeHtml(nameOf(match.away_id))} contra ${escapeHtml(nameOf(match.home_id))}">
        </span>${tag}<span class="sim-prob">${probability !== null ? `modelo: ${pct(probability)} para este placar` : `mais provável: ${escapeHtml(match.most_likely_score || "–")}`}</span>`;
    }

    function resultPanel(mode, entry) {
      const table = finalTable(mode, entry);
      const picks = effectivePicks(entry);
      const missing = remaining.filter((match) => picks[match.match_id] === undefined).length;
      const body = table.map((row) => {
        const zone = zoneOf(row.position, table.length);
        const sign = goalDifference(row) > 0 ? "+" : goalDifference(row) < 0 ? MINUS : "";
        return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${row.position}</td><td>${clubCell(row.club_id)}${row.tie ? ` <span class="sim-tie" title="Empate em todos os critérios que dá para calcular; o regulamento decide por cartões e, depois, sorteio">empate: ${row.tie}</span>` : ""}</td>
          <td class="num">${row.points}</td><td class="num">${row.played}</td><td class="num">${row.wins}</td><td class="num">${sign}${Math.abs(goalDifference(row))}</td></tr>`;
      }).join("");
      const missingNote = missing ? `${missing} ${missing === 1 ? "jogo em branco não entra" : "jogos em branco não entram"} na tabela. Ligue "Modelo sorteia" para completar.` : "Todos os jogos têm resultado.";
      const goalsNote = mode === "vencedor" ? " No modo Vencedor não há placar, então o saldo de gols é só o dos jogos já disputados." : "";
      const asTable = missing ? "" : (() => {
        const score = tableScore(table.map((row) => row.club_id));
        return `<div class="sim-scorebox"><p><strong>Esta tabela como Classificação:</strong> ${score.points} pontos se o campeonato acabasse hoje · até ${score.ceiling} de ${score.maximum} possíveis.</p></div>`;
      })();
      return `<h2>Sua tabela final</h2><p class="note">${missingNote}${goalsNote}</p>
        <div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Clube</th><th class="num">Pts</th><th class="num">J</th><th class="num">V</th><th class="num">SG</th></tr></thead><tbody>${body}</tbody></table></div>${asTable}`;
    }

    function renderPicks(mode, entry, savedItem, fromLink, persist) {
      const picks = effectivePicks(entry);
      const pending = remaining.length;
      const own = remaining.filter((match) => entry.picks[match.match_id] !== undefined).length;
      const sampledCount = remaining.filter((match) => entry.picks[match.match_id] === undefined && entry.sampled[match.match_id] !== undefined).length;
      const blank = pending - own - sampledCount;
      const byRound = new Map();
      [...remaining].sort((left, right) => (left.round || 99) - (right.round || 99) || left.match_date.localeCompare(right.match_date))
        .forEach((match) => { const key = match.round || 0; if (!byRound.has(key)) byRound.set(key, []); byRound.get(key).push(match); });
      const rounds = [...byRound.entries()].map(([round, matches], index) => {
        const filled = matches.filter((match) => picks[match.match_id] !== undefined).length;
        return `<details class="sim-round" ${index < 2 ? "open" : ""}><summary><span>${round ? `Rodada ${round}` : "Sem rodada"}</span><span class="note">${filled} de ${matches.length} preenchidos</span></summary>
          ${matches.map((match) => `<div class="sim-match" data-row="${escapeHtml(match.match_id)}">
            <span class="sim-date">${escapeHtml(formatShortDate(match.match_date))}${match.match_date < snapshot.reference_date ? " · adiado" : ""} ${lockLabel(match)}</span>
            <span class="sim-home">${clubCell(match.home_id)}</span>
            <span class="sim-pick">${matchControl(mode, match, entry)}${crowdForMatch(match)}${entry.picks[match.match_id] !== undefined ? `<button type="button" class="link-button sim-clear-one" data-clear="${escapeHtml(match.match_id)}">apagar</button>` : ""}</span>
            <span class="sim-away">${clubCell(match.away_id)}</span></div>`).join("")}
        </details>`;
      }).join("");
      const modelSwitch = canSample ? `<div class="sim-model-switch" role="group" aria-label="O que fazer com os jogos em branco">
          <span class="sim-model-switch-label">Jogos em branco</span>
          <span class="sim-segments"><button type="button" class="sim-segment" data-model="off" aria-pressed="${!entry.model}">Deixar em branco</button><button type="button" class="sim-segment" data-model="on" aria-pressed="${entry.model}">Modelo sorteia</button></span>
          ${entry.model ? `<button type="button" class="link-button" id="sim-redraw">Sortear de novo</button>` : ""}
          <p class="note">${entry.model ? "O modelo sorteou agora um resultado para cada jogo que você não preencheu, com as probabilidades dele. Os sorteados aparecem tracejados e valem pontos como os seus; troque qualquer um clicando nele." : "Os jogos que você não preencher ficam fora da tabela final. Escolha \"Modelo sorteia\" para completar cada um com um resultado sorteado na hora."}</p>
        </div>` : `<p class="note">O sorteio do modelo precisa de um snapshot mais novo, com a matriz de placares.</p>`;
      const progress = `<div class="sim-progress" role="img" aria-label="${own} seus, ${sampledCount} sorteados, ${blank} em branco"><span class="is-own" style="width:${own / pending * 100}%"></span><span class="is-model" style="width:${sampledCount / pending * 100}%"></span></div>
        <p class="note">${own} seus · ${sampledCount} sorteados pelo modelo · ${blank} em branco, de ${pending} jogos que faltam.</p>`;
      const score = pickScore(mode, entry);
      const scoreLine = savedItem ? `<div class="sim-scorebox"><p>${scoreSummary(savedItem)}</p></div>`
        : `<div class="sim-scorebox"><p>Esta simulação vale até <strong>${score.total}</strong> pontos (${maxPerMatch(mode)} por jogo preenchido).</p></div>`;
      const blocked = Object.keys(picks).length ? "" : "Preencha pelo menos um jogo, ou escolha \"Modelo sorteia\", para salvar.";
      shell(mode, MODES[mode].label, `${MODES[mode].what} ${MODES[mode].scoring}`, `
        ${editorHeader(mode, savedItem, fromLink)}
        ${modelSwitch}${progress}${scoreLine}
        <p class="sim-toolbar"><button type="button" class="link-button" id="sim-clear">Apagar meus palpites</button></p>
        <div class="sim-layout"><div class="sim-picks">${rounds || "<p>Não há jogos por disputar.</p>"}</div>
          <div class="sim-result" id="sim-result" aria-live="polite">${resultPanel(mode, entry)}</div></div>
        ${saveBar(savedItem, blocked)}`);
      bindEditorHeader(mode);
      bindSaveBar(mode, entry, savedItem);
      const again = (focusSelector) => {
        const scroll = window.scrollY;
        const openRounds = [...main.querySelectorAll(".sim-round")].map((details) => details.open);
        renderPicks(mode, entry, savedItem, fromLink, persist);
        main.querySelectorAll(".sim-round").forEach((details, index) => { if (openRounds[index] !== undefined) details.open = openRounds[index]; });
        window.scrollTo(0, scroll);
        if (focusSelector) { const element = main.querySelector(focusSelector); if (element) element.focus({ preventScroll: true }); }
      };
      main.querySelectorAll("[data-model]").forEach((button) => button.addEventListener("click", () => {
        entry.model = button.dataset.model === "on";
        if (entry.model) fillWithModel(mode, entry, false); else entry.sampled = {};
        persist(); again(`[data-model="${button.dataset.model}"]`);
      }));
      const redraw = document.getElementById("sim-redraw");
      if (redraw) redraw.addEventListener("click", () => { fillWithModel(mode, entry, true); persist(); again("#sim-redraw"); });
      document.getElementById("sim-clear").addEventListener("click", () => {
        if (Object.keys(entry.picks).length && !window.confirm("Apagar os seus palpites? Os sorteados pelo modelo ficam.")) return;
        entry.picks = {};
        if (entry.model) fillWithModel(mode, entry, false);
        persist(); again();
      });
      main.querySelectorAll("[data-clear]").forEach((button) => button.addEventListener("click", () => {
        const matchId = button.dataset.clear;
        delete entry.picks[matchId];
        if (entry.model) entry.sampled[matchId] = sampleMatch(mode, remaining.find((item) => item.match_id === matchId));
        persist(); again();
      }));
      main.querySelectorAll(".sim-choice[data-pick]").forEach((button) => button.addEventListener("click", () => {
        entry.picks[button.dataset.match] = button.dataset.pick;
        delete entry.sampled[button.dataset.match];
        persist(); again(`.sim-choice[data-match="${CSS.escape(button.dataset.match)}"][data-pick="${button.dataset.pick}"]`);
      }));
      main.querySelectorAll(".sim-score input").forEach((input) => input.addEventListener("change", () => {
        const matchId = input.dataset.match;
        const fields = main.querySelectorAll(`.sim-score input[data-match="${CSS.escape(matchId)}"]`);
        const values = Array.from(fields, (field) => (field.value === "" ? null : Math.max(0, Math.min(MAX_GOALS_INPUT, Math.round(Number(field.value))))));
        if (!values.every((value) => value !== null && !Number.isNaN(value))) return;
        entry.picks[matchId] = values;
        delete entry.sampled[matchId];
        persist();
        const nextRow = main.querySelector(`.sim-match[data-row="${CSS.escape(matchId)}"]`)?.nextElementSibling;
        const nextId = nextRow && nextRow.dataset ? nextRow.dataset.row : null;
        again(nextId ? `.sim-score input[data-match="${CSS.escape(nextId)}"][data-side="0"]` : null);
      }));
    }

    /* ---------------- Ranking e visitantes */

    async function renderRanking(requested) {
      const rankMode = MODES[requested] ? requested : "placar";
      const subTabs = `<nav class="tabs sim-subtabs" aria-label="Ranking por modo">${Object.entries(MODES).map(([key, item]) =>
        `<a href="#/simular/ranking/${key}" ${key === rankMode ? 'aria-current="page"' : ""}>${item.label}</a>`).join("")}</nav>`;
      shell("ranking", "Ranking", `Cada simulação enviada ao servidor por quem escolheu aparecer no ranking (até ${SERVER_LIMIT} por pessoa e modo), com o apelido e o ID da simulação.`,
        `${subTabs}<p class="note">${MODES[rankMode].scoring} Só contam palpites salvos no servidor antes do horário de cada jogo; os sorteados pelo modelo contam como os outros.</p>
         <div id="sim-ranking" aria-live="polite"><p class="note">Carregando o ranking…</p></div>`);
      const target = document.getElementById("sim-ranking");
      try {
        if (rankMode === "classificacao") {
          const info = await cloud.seasonInfo(season);
          if (info && new Date(info.classificacao_locks_at) <= new Date() && document.body.contains(target)) {
            target.insertAdjacentHTML("beforebegin", `<p class="sim-banner">Nesta temporada não há ranking da Classificação: a trava foi em ${formatDay(info.classificacao_locks_at)}, antes de o simulador existir. Ele começa na próxima temporada. A pontuação de cada Classificação continua em "Minhas simulações".</p>`);
          }
        }
        const rows = await cloud.ranking(season, rankMode);
        const mine = new Set(store.saved.map((item) => item.server_id).filter(Boolean));
        const exactLabel = rankMode === "placar" ? "Placares exatos" : rankMode === "vencedor" ? "Acertos" : "Posições exatas";
        const body = rows.length ? `<div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Apelido · simulação</th><th class="num">Pontos</th><th class="num">${exactLabel}</th><th class="num">${rankMode === "classificacao" ? "Clubes" : "Jogos"}</th></tr></thead>
          <tbody>${rows.map((row) => `<tr${mine.has(row.simulation_id) ? ' class="selected-team"' : ""}><td class="num">${row.rank}</td><td>${escapeHtml(row.nickname)} · #${row.simulation_id}</td><td class="num">${row.points} de ${row.max_points}</td><td class="num">${row.exact_hits}</td><td class="num">${row.scored_picks}</td></tr>`).join("")}</tbody></table></div>`
          : `<p>Ninguém pontuou ainda neste modo. Os pontos aparecem depois que os jogos com palpite terminam${rankMode === "classificacao" ? " e, na Classificação, no fim da temporada" : ""}.</p>`;
        if (document.body.contains(target)) target.innerHTML = body;
      } catch (error) {
        if (document.body.contains(target)) target.innerHTML = `<p class="note">Ranking indisponível agora (${escapeHtml(error.message)}).</p>`;
      }
    }

    async function renderVisitors() {
      shell("visitantes", "Classificação dos visitantes", "A tabela final mais provável segundo as simulações feitas no site: a mais recente de cada pessoa que participa (uma Classificação, ou a tabela final de um Vencedor ou Placar exato completo), ordenada pela posição média.",
        `<div id="sim-visitors" aria-live="polite"><p class="note">Carregando…</p></div>`);
      const target = document.getElementById("sim-visitors");
      try {
        const data = await cloud.consensus(season);
        if (!document.body.contains(target)) return;
        if (!data.clubs || !data.clubs.length) {
          target.innerHTML = `<p>Ainda são poucas pessoas: a tabela aparece com pelo menos ${data.min_users} participantes, para não expor a escolha de ninguém. Participe e salve uma simulação para entrar na conta.</p>`;
          return;
        }
        const official = Object.fromEntries([...snapshot.teams].sort((left, right) => left.expected_position - right.expected_position).map((team, index) => [team.club_id, index + 1]));
        target.innerHTML = `<p class="note">Com as tabelas de pelo menos ${data.users_at_least} pessoas. Na última coluna, a posição do clube na ordem do modelo oficial.</p>
          <div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Clube</th><th class="num">Posição média</th><th class="num">Campeão</th><th class="num">Rebaixado</th><th class="num">Modelo</th></tr></thead>
          <tbody>${data.clubs.map((club, index) => { const zone = zoneOf(index + 1, data.clubs.length); return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${index + 1}</td><td>${clubCell(club.club_id)}</td>
            <td class="num">${Number(club.average_position).toLocaleString("pt-BR", { minimumFractionDigits: 1 })}</td><td class="num">${pct(club.champion)}</td><td class="num">${pct(club.relegated)}</td><td class="num">${official[club.club_id] || "–"}º</td></tr>`; }).join("")}</tbody></table></div>`;
      } catch (error) {
        if (document.body.contains(target)) target.innerHTML = `<p class="note">Indisponível agora (${escapeHtml(error.message)}).</p>`;
      }
    }

    /* ---------------- Rotas: #/simular, /{modo}, /{modo}/s/{id}, /{modo}/l/{código}, /ranking/{modo}, /visitantes */

    if (first === "ranking" && cloud) renderRanking(second);
    else if (first === "visitantes" && cloud) renderVisitors();
    else if (MODES[first]) {
      if (second === "s") openEditor(first, decodeURIComponent(third), null);
      else if (second === "l") openEditor(first, null, third);
      else if (second) openEditor(first, null, second);
      else openEditor(first, null, null);
    } else renderHome();
    initCloud();
  }

  window.Simulator = { render };
})();
