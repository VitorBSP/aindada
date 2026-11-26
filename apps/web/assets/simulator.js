/* Simulador do usuário (ADR-0015). Um modo por vez: o visitante escolhe Classificação, Vencedor ou Placar exato e
   segue o passo a passo até salvar (ou descarta o rascunho); só então começa outro. Cada simulação salva ganha um ID e
   a própria pontuação; dá para fazer quantas quiser.
   - Classificação: ordenar e revisar. Ordem impossível pela matemática não passa.
   - Vencedor e Placar exato: escolher como preencher (eu, eu e o modelo, ou o modelo), preencher rodada por rodada e
     revisar a tabela final. O modelo sorteia na hora um resultado concreto para cada jogo em branco, com as
     probabilidades que o Python publica no snapshot (`score_probabilities`): o navegador só sorteia, não refaz o modelo.
   Tudo fica no aparelho (localStorage). Com simulator-config.js preenchido, quem escolher "Participar" também salva no
   Supabase (simulator-cloud.js, até 10 simulações por pessoa a cada jogo novo), entra no ranking com um apelido e pode cadastrar um e-mail
   para avisos de pontuação. A pontuação, a tabela, o sorteio, os links e a mescla entre abas ficam em
   simulator-logic.js (testada com node:test) e repetem a do banco (migração 0006). A página "Agregado" mostra a posição
   média das simulações: as do aparelho e as do site. */
(function () {
  "use strict";

  const logic = window.SimulatorLogic;
  const {
    LIBERTADORES_GROUPS, LIBERTADORES_SLOTS, SUDAMERICANA_SLOTS, RELEGATED, POINTS,
    outcomeOf, scoreSampler, draw, newRows, addResult, goalDifference, compareMain, rankRows, matchPoints, maxForPick, encodeLink,
    decodeLink,
  } = logic;

  const MODES = {
    classificacao: {
      label: "Classificação", effort: "1 minuto",
      what: "Ordene os 20 clubes do 1º ao 20º.",
      scoring: "3 pontos por clube na posição exata, 1 a uma posição da certa, 10 pelo campeão, 3 por clube do G4 acertado e 5 por rebaixado acertado (máximo 102). No ranking, a pontuação é multiplicada pela fração de jogos que ainda faltavam quando você salvou: quanto mais cedo, mais vale.",
    },
    vencedor: {
      label: "Vencedor", effort: "5 minutos",
      what: "Escolha mandante, empate ou visitante em cada jogo que falta.",
      scoring: "3 pontos por vitória certa e 5 por empate certo.",
    },
    placar: {
      label: "Placar exato", effort: "10 minutos",
      what: "Dê o placar de cada jogo que falta.",
      scoring: "Placar exato 10; vencedor e gols do vencedor 7; vencedor e diferença de gols 6; vencedor e gols do perdedor 5; empate certo (sem o placar) 5; só o vencedor 3; placar invertido 2.",
    },
  };
  // Versão 5 (ADR-0015): até 10 simulações por pessoa desde o último jogo que travou; cada jogo trava 30 minutos antes
  // do início (mesmas regras de sim_lock_margin e sim_event_start, migração 0005).
  const EVENT_LIMIT = 10;
  const LOCK_MARGIN_MINUTES = 30;
  const MAX_GOALS_INPUT = 20;
  const MINUS = "−";
  // Mesma regra do banco (sim_profiles.nickname): letras com acento do português, números e _ . - espaço.
  const NICKNAME = /^[A-Za-zÀ-ÖØ-öø-ÿ0-9_. -]{3,20}$/;
  const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  const view = { store: null, season: null, link: null, linkNote: "", refresh: null, previewMode: "", previewMatchId: "", previewScore: [1, 0], previewPick: "H" };
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

  /* Antes de gravar, relê o armazenamento e mescla as simulações salvas pelo local_id: outra aba pode ter salvo
     enquanto esta estava aberta. Rascunho e sessão em andamento são desta aba e ficam como estão. */
  function writeStore() {
    try {
      const raw = window.localStorage.getItem(storageKey(view.season));
      const other = raw ? JSON.parse(raw) : null;
      if (other && other.version === 2) {
        const merged = logic.mergeStores(view.store, other);
        view.store.saved = merged.saved;
        view.store.removed = merged.removed;
      }
      window.localStorage.setItem(storageKey(view.season), JSON.stringify(view.store));
    } catch (error) { /* só nesta aba */ }
  }

  /* Outra aba gravou: traz as simulações dela para esta e atualiza a lista, se for a tela que a mostra. */
  if (typeof window.addEventListener === "function") window.addEventListener("storage", (event) => {
    if (!view.store || event.key !== storageKey(view.season) || !event.newValue) return;
    try {
      const other = JSON.parse(event.newValue);
      if (!other || other.version !== 2) return;
      const merged = logic.mergeStores(view.store, other);
      view.store.saved = merged.saved;
      view.store.removed = merged.removed;
      if (view.refresh) view.refresh();
    } catch (error) { /* gravação ilegível: mantém a desta aba */ }
  });

  const newLocalId = () => Math.random().toString(36).slice(2, 6).toUpperCase();

  /* ---------------------------------------------------------------- Sorteio e tabela */

  function zoneOf(position, total) {
    if (position === 1) return { key: "title", label: "Campeão" };
    if (position <= LIBERTADORES_GROUPS) return { key: "libertadores", label: "Libertadores" };
    if (position <= LIBERTADORES_SLOTS) return { key: "libertadores", label: "Pré-Libertadores" };
    if (position <= LIBERTADORES_SLOTS + SUDAMERICANA_SLOTS) return { key: "sudamericana", label: "Sul-Americana" };
    if (position > total - RELEGATED) return { key: "relegation", label: "Rebaixado" };
    return { key: "", label: "" };
  }

  /* ---------------------------------------------------------------- Pontuação (simulator-logic.js) */

  const perMatchText = (mode) => (mode === "placar" ? `${POINTS.exact} por jogo` : `${POINTS.winner} por vitória, ${POINTS.draw} por empate`);

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
    // Jogo cancelado não soma pontos a ninguém (mesma regra do supabase_sync, que envia o máximo ao banco).
    const remainingByClub = Object.fromEntries(clubIds.map((clubId) => [clubId, 0]));
    remaining.filter((match) => match.status !== "cancelled").forEach((match) => { remainingByClub[match.home_id] += 1; remainingByClub[match.away_id] += 1; });
    const maxPoints = Object.fromEntries(clubIds.map((clubId) => [clubId, currentPoints[clubId] + 3 * remainingByClub[clubId]]));
    // Faixa de posições que cada clube ainda alcança (empates contam a favor).
    const reach = Object.fromEntries(clubIds.map((clubId) => [clubId, {
      best: 1 + clubIds.filter((other) => other !== clubId && currentPoints[other] > maxPoints[clubId]).length,
      worst: clubIds.length - clubIds.filter((other) => other !== clubId && maxPoints[other] < currentPoints[clubId]).length,
    }]));
    const rounds = (() => {
      const byRound = new Map();
      [...remaining].sort((left, right) => (left.round || 99) - (right.round || 99) || left.match_date.localeCompare(right.match_date))
        .forEach((match) => { const key = match.round || 0; if (!byRound.has(key)) byRound.set(key, []); byRound.get(key).push(match); });
      return [...byRound.entries()].map(([round, matches]) => ({ round, matches }));
    })();

    const [first = "", second = "", third = ""] = segments;
    const clubCell = (clubId, size = 18) => `<span class="club-cell">${crest(clubId, size)}<span>${escapeHtml(nameOf(clubId))}</span></span>`;
    const shortName = (clubId) => escapeHtml((teamById[clubId] || {}).short_name || nameOf(clubId));
    const clock = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const currentSegments = () => location.hash.replace(/^#\/?/, "").split("/").slice(1).filter(Boolean);
    const onSimulator = () => location.hash.replace(/^#\/?/, "").startsWith("simular");
    const rerender = () => { if (onSimulator()) render(main, currentSegments(), context); };
    view.refresh = () => { const [screen = ""] = currentSegments(); if (screen === "" || screen === "minhas") rerender(); };
    const go = (hash) => { if (location.hash === hash) rerender(); else location.hash = hash; };
    const formatDay = (iso) => new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
    const clone = (value) => JSON.parse(JSON.stringify(value));

    function emptyEntry(mode) {
      if (mode === "classificacao") return { order: [...snapshot.teams].sort((left, right) => left.expected_position - right.expected_position).map((team) => team.club_id) };
      return { picks: {}, sampled: {}, model: false };
    }

    /* Tira do rascunho o que não vale mais (clube que não existe, jogo já disputado). */
    function sanitize(mode, entry) {
      if (!entry) return emptyEntry(mode);
      if (mode === "classificacao") {
        const valid = Array.isArray(entry.order) && entry.order.length === clubIds.length && clubIds.every((clubId) => entry.order.includes(clubId));
        return valid ? { order: [...entry.order] } : emptyEntry(mode);
      }
      const keep = (picks) => Object.fromEntries(Object.entries(picks || {}).filter(([matchId]) => remainingIds.has(matchId)));
      return { picks: keep(entry.picks), sampled: canSample ? keep(entry.sampled) : {}, model: Boolean(entry.model) && canSample };
    }

    /* ---------------- Sessão em andamento: um modo por vez, até salvar ou descartar */

    const stepsOf = (mode) => (mode === "classificacao" ? ["Campeão", "G4", "Rebaixados", "Ajustar", "Revisar"] : ["Como jogar", "Jogos", "Revisar"]);

    function startSession(mode, savedItem, entry) {
      store.active = {
        mode,
        savedId: savedItem ? savedItem.local_id : null,
        // Editar uma simulação salva começa pelo ajuste (Classificação) ou pelos cartões (Vencedor e Placar exato).
        step: savedItem ? (mode === "classificacao" ? 4 : 2) : 1,
        cursor: 0,
        entry: entry || (savedItem ? clone(savedItem.entry) : emptyEntry(mode)),
        started_at: new Date().toISOString(),
      };
      writeStore();
    }

    function endSession() { store.active = null; writeStore(); }

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

    /* Evento = cada vez que um jogo trava. Simulação salva antes do último evento fica fechada. */
    function eventStart() {
      const now = Date.now();
      const passed = snapshot.matches.map((match) => lockTime(match).getTime()).filter((time) => !Number.isNaN(time) && time <= now);
      return passed.length ? new Date(Math.max(...passed)) : null;
    }

    function isClosed(item) {
      const start = eventStart();
      return Boolean(start && item.created_at && new Date(item.created_at) < start);
    }

    function eventCount() {
      const start = eventStart();
      return store.saved.filter((item) => item.server_id && !item.detached && (!start || new Date(item.created_at) >= start)).length;
    }

    /* Envia uma simulação ao servidor; devolve um texto sobre o que aconteceu. Depois do envio, a cópia local passa a
       ser o que o servidor guardou (palpites de jogos travados saem), para a pontuação da tela bater com a do ranking. */
    async function pushToServer(item) {
      if (!cloud || !cloudState.user) return "";
      if (item.detached) return " Ela foi enviada por outra participação, da qual você saiu: fica só neste aparelho.";
      if (item.server_id && isClosed(item)) return " Ela está fechada: um jogo começou depois que foi salva.";
      if (!item.server_id && eventCount() >= EVENT_LIMIT) return ` Você já enviou ${EVENT_LIMIT} simulações desde o último jogo: esta ficou só neste aparelho. Depois do próximo jogo, dá para enviar outras ${EVENT_LIMIT}.`;
      try {
        const stored = await cloud.saveSimulation(season, item.mode, item.entry, item.server_id, finalOrderOf(item.mode, item.entry));
        if (!stored) return "";
        const note = droppedNote(item, stored.payload);
        item.server_id = stored.id;
        if (stored.created_at) item.created_at = stored.created_at;
        writeStore();
        return ` Enviada ao servidor como #${stored.id}.${note}`;
      } catch (error) {
        return ` Não foi ao servidor (${error.message}); continua salva neste aparelho.`;
      }
    }

    function droppedNote(item, payload) {
      if (item.mode === "classificacao") return "";
      const sent = Object.keys({ ...item.entry.sampled, ...item.entry.picks });
      const kept = new Set(Object.keys(payload.picks || {}));
      const dropped = sent.filter((matchId) => !kept.has(matchId)).length;
      if (!dropped) return "";
      return dropped === 1 ? " 1 palpite é de jogo que já fechou: fica na sua simulação, mas não conta para o ranking." : ` ${dropped} palpites são de jogos que já fecharam: ficam na sua simulação, mas não contam para o ranking.`;
    }

    /* Mesma trava do servidor: 30 minutos antes do pontapé (supabase_sync.match_lock_utc menos sim_lock_margin) ou,
       sem horário, 00:00 de Brasília do dia. */
    const POSTPONED_AFTER_DAYS = 7;
    const NEVER = new Date(8.64e15);
    /* Adiado, data a definir (mesma regra do supabase_sync.is_postponed): o palpite fica aberto até a data nova. */
    function isPostponedMatch(match) {
      if (match.status === "finished" || match.status === "cancelled") return false;
      if (match.status === "postponed") return true;
      return (new Date(`${snapshot.reference_date}T12:00:00`) - new Date(`${match.match_date}T12:00:00`)) / 86400000 > POSTPONED_AFTER_DAYS;
    }

    function lockTime(match) {
      if (isPostponedMatch(match)) return NEVER;
      if (!match.kickoff_utc) return new Date(`${match.match_date}T00:00:00-03:00`);
      return new Date(new Date(match.kickoff_utc).getTime() - LOCK_MARGIN_MINUTES * 60000);
    }

    function lockLabel(match) {
      if (!cloud || !cloudState.user) return "";
      if (isPostponedMatch(match)) return `<span class="sim-lock">adiado, aberto até a data nova</span>`;
      const lock = lockTime(match);
      if (Number.isNaN(lock.getTime())) return "";
      if (lock <= new Date()) return `<span class="sim-lock is-locked">fechado</span>`;
      return `<span class="sim-lock">aberto até ${lock.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>`;
    }

    function crowdForMatch(match) {
      const data = cloudState.community && cloudState.community.matches ? cloudState.community.matches[match.match_id] : null;
      if (!data) return "";
      return `<span class="sim-crowd" title="Pelo menos ${data.users_at_least} visitantes com palpite neste jogo; arredondado de 5 em 5 pontos">visitantes: ${pct(data.H)} · ${pct(data.D)} · ${pct(data.A)}</span>`;
    }

    /* ---------------- Pontuação */

    function effectivePicks(entry) { return { ...(entry.sampled || {}), ...(entry.picks || {}) }; }

    function pickScore(mode, entry) {
      let points = 0;
      let scored = 0;
      let open = 0;
      let outOf = 0;
      let openMax = 0;
      Object.entries(effectivePicks(entry)).forEach(([matchId, pick]) => {
        const match = matchById.get(matchId);
        if (!match) return;
        if (isFinished(match)) { scored += 1; points += matchPoints(mode, pick, match.home_goals, match.away_goals); outOf += maxForPick(mode, pick); }
        else { open += 1; openMax += maxForPick(mode, pick); }
      });
      return { points, outOf, scored, ceiling: points + openMax, total: outOf + openMax };
    }

    /* Classificação comparada com a tabela de hoje (como se o campeonato acabasse agora) e o teto que ainda dá. */
    function tableScore(order) { return logic.tableScore(order, standingsOrder, reach); }

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

    /* ---------------- Probabilidade de tudo junto (versão 5): campeão, G4 e rebaixados da simulação, juntos.
       Sorteia o resto do campeonato a partir das probabilidades de cada jogo publicadas pelo modelo (o navegador não refaz
       o modelo, só sorteia delas, como na versão 1). A força fica a da data de referência e empate sem critério é
       sorteado; por isso o número pode diferir um pouco do oficial. */

    const JOINT_DRAWS = 20000;
    const JOINT_CHUNK = 2000;
    const jointCache = new Map();
    const playable = remaining.filter((match) => match.status !== "cancelled" && samplers.get(match.match_id));
    const clubIndex = new Map(clubIds.map((clubId, index) => [clubId, index]));
    const baseRows = (() => {
      const rows = newRows(clubIds);
      finished.forEach((match) => addResult(rows, { home: match.home_id, away: match.away_id, outcome: outcomeOf(match.home_goals, match.away_goals), homeGoals: match.home_goals, awayGoals: match.away_goals }));
      return clubIds.map((clubId) => rows[clubId]);
    })();
    const OUTCOME_PROBABILITY = { H: (match) => match.p_home, D: (match) => match.p_draw, A: (match) => match.p_away };

    function targetOf(order) {
      return { champion: order[0], top4: order.slice(0, LIBERTADORES_GROUPS), relegated: order.slice(order.length - RELEGATED) };
    }

    /* Um campeonato sorteado. Com `lean`, puxa os resultados a favor do que se quer ver (só para achar um caminho). */
    function drawSeason(lean) {
      const size = clubIds.length;
      const points = new Float64Array(size), wins = new Float64Array(size), balance = new Float64Array(size), scored = new Float64Array(size);
      baseRows.forEach((row, index) => { points[index] = row.points; wins[index] = row.wins; balance[index] = row.goals_for - row.goals_against; scored[index] = row.goals_for; });
      const outcomes = new Array(playable.length);
      playable.forEach((match, position) => {
        let home, away;
        if (lean) {
          const edge = (lean[match.home_id] || 0) - (lean[match.away_id] || 0);
          const weights = [match.p_home * Math.exp(edge), match.p_draw, match.p_away * Math.exp(-edge)];
          const target = Math.random() * (weights[0] + weights[1] + weights[2]);
          const wanted = target < weights[0] ? "H" : target < weights[0] + weights[1] ? "D" : "A";
          for (let attempt = 0; attempt < 30; attempt += 1) {
            [home, away] = draw(samplers.get(match.match_id));
            if (outcomeOf(home, away) === wanted) break;
          }
          if (outcomeOf(home, away) !== wanted) [home, away] = wanted === "H" ? [1, 0] : wanted === "A" ? [0, 1] : [1, 1];
        } else {
          [home, away] = draw(samplers.get(match.match_id));
        }
        const h = clubIndex.get(match.home_id), a = clubIndex.get(match.away_id);
        const outcome = outcomeOf(home, away);
        outcomes[position] = outcome;
        if (outcome === "H") { points[h] += 3; wins[h] += 1; } else if (outcome === "A") { points[a] += 3; wins[a] += 1; } else { points[h] += 1; points[a] += 1; }
        balance[h] += home - away; balance[a] += away - home; scored[h] += home; scored[a] += away;
      });
      const luck = clubIds.map(() => Math.random());
      const order = clubIds.map((clubId, index) => index).sort((left, right) => points[right] - points[left] || wins[right] - wins[left]
        || balance[right] - balance[left] || scored[right] - scored[left] || luck[left] - luck[right]).map((index) => clubIds[index]);
      return { order, outcomes };
    }

    function likelihood(outcomes) {
      return outcomes.reduce((sum, outcome, position) => sum + Math.log(Math.max(1e-9, OUTCOME_PROBABILITY[outcome](playable[position]))), 0);
    }

    async function jointChance(target) {
      const key = `${target.champion}|${[...target.top4].sort()}|${[...target.relegated].sort()}`;
      if (jointCache.has(key)) return jointCache.get(key);
      const top4 = new Set(target.top4), down = new Set(target.relegated);
      const matchesTarget = (order) => order[0] === target.champion
        && order.slice(0, LIBERTADORES_GROUPS).every((clubId) => top4.has(clubId))
        && order.slice(order.length - RELEGATED).every((clubId) => down.has(clubId));
      const tally = { champion: 0, top4: 0, relegated: 0, all: 0 };
      let best = null;
      for (let index = 0; index < JOINT_DRAWS; index += 1) {
        const season = drawSeason(null);
        const champion = season.order[0] === target.champion;
        const inTop4 = season.order.slice(0, LIBERTADORES_GROUPS).every((clubId) => top4.has(clubId));
        const inDown = season.order.slice(season.order.length - RELEGATED).every((clubId) => down.has(clubId));
        tally.champion += champion; tally.top4 += inTop4; tally.relegated += inDown;
        if (champion && inTop4 && inDown) {
          tally.all += 1;
          const score = likelihood(season.outcomes);
          if (!best || score > best.score) best = { score, outcomes: season.outcomes };
        }
        if (index % JOINT_CHUNK === JOINT_CHUNK - 1) await new Promise((resolve) => setTimeout(resolve));
      }
      let leaned = false;
      if (!best) {
        // Nenhum sorteio comum chegou lá: procura um caminho puxando os resultados a favor da escolha.
        const lean = {};
        clubIds.forEach((clubId) => { lean[clubId] = clubId === target.champion ? 3 : top4.has(clubId) ? 1.5 : down.has(clubId) ? -2 : 0; });
        for (let index = 0; index < JOINT_DRAWS && !best; index += 1) {
          const season = drawSeason(lean);
          if (matchesTarget(season.order)) best = { score: likelihood(season.outcomes), outcomes: season.outcomes };
          if (index % JOINT_CHUNK === JOINT_CHUNK - 1) await new Promise((resolve) => setTimeout(resolve));
        }
        leaned = Boolean(best);
      }
      const result = {
        draws: JOINT_DRAWS,
        champion: tally.champion / JOINT_DRAWS, top4: tally.top4 / JOINT_DRAWS, relegated: tally.relegated / JOINT_DRAWS, all: tally.all / JOINT_DRAWS,
        path: best ? best.outcomes : null, leaned,
      };
      jointCache.set(key, result);
      return result;
    }

    function chanceText(value, draws) {
      if (value === 0) return `menos de 1 em ${draws.toLocaleString("pt-BR")}`;
      if (value < 0.01) return `${pct(value)} (cerca de 1 em ${Math.round(1 / value).toLocaleString("pt-BR")})`;
      return pct(value);
    }

    function pathTable(outcomes) {
      const byRound = playable.map((match, position) => ({ match, outcome: outcomes[position] }))
        .sort((left, right) => (left.match.round || 99) - (right.match.round || 99) || left.match.match_date.localeCompare(right.match.match_date));
      const rows = byRound.map(({ match, outcome }) => {
        const result = outcome === "D" ? "empate" : `vitória do ${shortName(outcome === "H" ? match.home_id : match.away_id)}`;
        return `<tr><td class="num">${match.round || "–"}</td><td>${shortName(match.home_id)} × ${shortName(match.away_id)}</td><td>${result}</td></tr>`;
      }).join("");
      return `<div class="table-wrap"><table class="sim-table sim-path"><thead><tr><th class="num">Rod.</th><th>Jogo</th><th>Resultado</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }

    const jointSlot = (id) => `<section class="sim-joint" id="${id}" aria-live="polite"><p class="sim-joint-label">Probabilidade de tudo junto</p><p class="note">Calculando ${JOINT_DRAWS.toLocaleString("pt-BR")} campeonatos sorteados…</p></section>`;

    function fillJoint(id, order, withPath) {
      if (!canSample || !order || order.length !== clubIds.length) {
        const slot = document.getElementById(id);
        if (slot) slot.remove();
        return;
      }
      const target = targetOf(order);
      jointChance(target).then((result) => {
        const slot = document.getElementById(id);
        if (!slot) return;
        const names = (list) => list.map((clubId) => shortName(clubId)).join(", ");
        const path = withPath && result.path ? `<details class="sim-path-details"><summary>Um caminho possível: vitórias, empates e derrotas que levam a essa tabela</summary>
            <p class="note">${result.leaned ? "Nenhum sorteio comum chegou a essa combinação; este caminho foi achado puxando os resultados a favor dela." : "O caminho mais provável entre os sorteios que chegaram a essa combinação."} É só um exemplo: outros resultados também levam ao mesmo campeão, G4 e rebaixados.</p>
            ${pathTable(result.path)}</details>` : "";
        const big = result.all > 0
          ? `<p class="sim-joint-big"><strong>${pct(result.all)}</strong><span>1 em cada ${Math.round(1 / result.all).toLocaleString("pt-BR")} simulações</span></p>`
          : `<p class="sim-joint-big"><strong>&lt; ${pct(1 / result.draws)}</strong><span>nenhuma em ${result.draws.toLocaleString("pt-BR")} simulações</span></p>`;
        slot.innerHTML = `<p class="sim-joint-label">Probabilidade de tudo junto</p>
          ${big}
          <p class="note">Campeão, G4 e rebaixados como na sua simulação, contados juntos em ${result.draws.toLocaleString("pt-BR")} campeonatos sorteados com as probabilidades de cada jogo publicadas pelo modelo. Os jogos dependem uns dos outros, por isso não é a multiplicação das probabilidades de cada um. A força dos clubes fica fixa e empate sem critério é sorteado: o número pode diferir um pouco do oficial.</p>
          <ul class="sim-joint-parts">
            <li><span>Campeão: ${shortName(target.champion)}</span><strong>${chanceText(result.champion, result.draws)}</strong></li>
            <li><span>G4: ${names(target.top4)} (em qualquer ordem)</span><strong>${chanceText(result.top4, result.draws)}</strong></li>
            <li><span>Rebaixados: ${names(target.relegated)}</span><strong>${chanceText(result.relegated, result.draws)}</strong></li>
          </ul>
          ${path}`;
      });
    }


    function finalOrderOf(mode, entry) {
      if (mode === "classificacao") return entry.order;
      if (!isComplete(entry)) return null;
      return finalTable(mode, entry).map((row) => row.club_id);
    }

    function counts(entry) {
      const own = remaining.filter((match) => entry.picks[match.match_id] !== undefined).length;
      const sampled = remaining.filter((match) => entry.picks[match.match_id] === undefined && entry.sampled[match.match_id] !== undefined).length;
      return { own, sampled, blank: remaining.length - own - sampled };
    }

    /* ---------------- Moldura (v2.1 + Kanban #43) */

    const INFO_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>`;

    function tabs(active) {
      const items = [["", "Início"]];
      if (cloud) items.push(["ranking", "Ranking"]);
      items.push(["agregado", "Agregado"]);
      return `<nav class="chip-row sim-chips" aria-label="Simulador">${items.map(([key, label]) =>
        `<a class="chip" href="#/simular${key ? `/${key}` : ""}" ${key === active ? 'aria-current="page"' : ""}>${label}</a>`).join("")}</nav>`;
    }

    function storageNote() {
      if (!cloud) return "Suas simulações ficam salvas só neste aparelho.";
      return "Suas simulações ficam salvas neste aparelho; se você participar, também no nosso servidor, ligadas a uma conta sem nome.";
    }

    function infoSheetHtml() {
      const rules = Object.values(MODES).map((item) => `<p><strong>${item.label}:</strong> ${item.scoring}</p>`).join("");
      const cloudInfo = cloud
        ? `<p><strong>Ranking e privacidade:</strong> até ${EVENT_LIMIT} simulações por pessoa a cada jogo novo; só contam palpites enviados antes da trava (${LOCK_MARGIN_MINUTES} min antes do início). Os sorteados pelo modelo contam como os seus. Ao participar, as simulações vão para o Supabase (EUA) ligadas a uma conta sem nome que você apaga quando quiser. <a href="#/privacidade">Política de privacidade completa</a>.</p>`
        : `<p>${storageNote()}</p>`;
      return `<div class="sheet-info">${rules}${cloudInfo}<p>As vagas seguem o regulamento de 2026; vagas extras que vêm das copas não entram na conta.</p></div>`;
    }

    function accountPill() {
      if (!cloud) return "";
      if (!cloudState.checked) return `<button type="button" class="sim-account-pill" id="sim-account-trigger" aria-busy="true"><span class="sim-account-dot is-guest"></span>Conta…</button>`;
      const user = cloudState.user;
      if (!user) return `<button type="button" class="sim-account-pill" id="sim-account-trigger"><span class="sim-account-dot is-guest"></span>Entrar no ranking</button>`;
      const profile = cloudState.profile || {};
      const label = profile.nickname ? `@${escapeHtml(profile.nickname)}` : "Participando";
      const suffix = profile.show_in_ranking ? " · no ranking ▾" : " ▾";
      return `<button type="button" class="sim-account-pill" id="sim-account-trigger"><span class="sim-account-dot"></span>${label}${suffix}</button>`;
    }

    function shell(active, title, lede, body, options = {}) {
      if (options.focus) {
        main.innerHTML = `
          <div class="screen-head sim-screen-head">
            <div class="sim-head-left"><h1 class="screen-title">${title}</h1><button type="button" class="icon-button sim-info-btn" id="sim-info-trigger" aria-label="Regras e privacidade do simulador">${INFO_ICON}</button></div>
          </div>
          ${lede ? `<p class="sim-sub-lede">${lede}</p>` : ""}
          ${body}`;
      } else {
        main.innerHTML = `
          <div class="screen-head sim-screen-head">
            <div class="sim-head-left"><h1 class="screen-title">${title}</h1><button type="button" class="icon-button sim-info-btn" id="sim-info-trigger" aria-label="Regras e privacidade do simulador">${INFO_ICON}</button></div>
            ${accountPill()}
          </div>
          ${tabs(active)}
          ${body}
          <p class="note sim-footnote">${storageNote()} <a href="#/privacidade">Privacidade</a>.</p>`;
      }
      const infoBtn = document.getElementById("sim-info-trigger");
      if (infoBtn) infoBtn.addEventListener("click", () => {
        if (window.AIndaDaShell) window.AIndaDaShell.openSheet("Como funciona o Simulador", infoSheetHtml());
      });
      if (!options.focus) {
        const accountBtn = document.getElementById("sim-account-trigger");
        if (accountBtn) accountBtn.addEventListener("click", openAccountSheet);
      }
    }

    /* ---------------- Painel da conta (folha modal v2.1) */

    const captchaSlot = () => (cloud && cloud.captchaEnabled ? '<div class="sim-captcha" id="sim-captcha"></div>' : "");
    const captchaHost = (root = document) => root.querySelector("#sim-captcha");

    function accountBodyHtml() {
      if (!cloud) return "";
      const status = `<p class="note" id="sim-cloud-status" aria-live="polite">${escapeHtml(cloudState.status)}</p>`;
      if (!cloudState.checked) return `<div class="sim-account-sheet">${status}</div>`;
      const user = cloudState.user;
      if (!user) {
        const login = cloudState.open === "login" ? `<form class="sim-form" id="sim-login-form">
            <label>E-mail ligado à sua participação <input type="email" required autocomplete="email" id="sim-login-email"></label>
            <button type="submit" class="btn-secondary btn-sm">Enviar link de entrada</button></form>` : "";
        return `<div class="sim-account-sheet">
          <p><strong>Entre no ranking e compare com os outros visitantes.</strong> Participe para enviar suas simulações ao servidor (até ${EVENT_LIMIT} a cada jogo novo) e aparecer no ranking com um apelido. Não precisa de cadastro.</p>
          <p class="sim-account-cta-row"><button type="button" class="btn-primary btn-sm" id="sim-join">Participar</button> <button type="button" class="btn-secondary btn-sm" id="sim-login-open">Já participo em outro aparelho</button></p>
          <p class="note sim-consent">Ao participar, suas simulações vão para o Supabase (EUA), ligadas a uma conta sem nome que você apaga quando quiser. Veja a <a href="#/privacidade">política de privacidade</a>.</p>${captchaSlot()}${login}${status}</div>`;
      }
      const profile = cloudState.profile || {};
      const contact = cloudState.contact;
      const who = profile.nickname ? `como <strong>${escapeHtml(profile.nickname)}</strong>${profile.show_in_ranking ? " · no ranking" : " · fora do ranking"}` : "sem apelido · fora do ranking";
      const notices = contact && contact.notify ? "avisos por e-mail ligados" : "sem avisos por e-mail";
      const forms = {
        profile: `<form class="sim-form" id="sim-profile-form">
          <label>Apelido <input type="text" id="sim-nickname" maxlength="20" minlength="3" value="${escapeHtml(profile.nickname || "")}" autocomplete="nickname"></label>
          <label class="sim-check"><input type="checkbox" id="sim-in-ranking" ${profile.show_in_ranking ? "checked" : ""}> Aparecer no ranking com este apelido</label>
          <p class="note">De 3 a 20 letras, números, espaço, ponto, hífen ou _. Não use e-mail nem nome completo. Apelidos ofensivos ou que imitam o site são recusados.</p>
          <button type="submit" class="btn-primary btn-sm">Salvar apelido</button></form>`,
        contact: `<form class="sim-form" id="sim-contact-form">
          <label>E-mail para avisos <input type="email" required autocomplete="email" id="sim-contact-email" value="${escapeHtml(contact ? contact.email : "")}"></label>
          <label class="sim-check"><input type="checkbox" id="sim-contact-notify" ${!contact || contact.notify ? "checked" : ""}> Quero receber minha pontuação por e-mail</label>
          <p class="note">Usamos só para avisar da sua pontuação. Ninguém mais vê o e-mail, e ele sai do servidor quando você apagar a participação.</p>
          <button type="submit" class="btn-primary btn-sm">Salvar e-mail</button>${contact ? ` <button type="button" class="link-button" id="sim-contact-delete">Remover e-mail</button>` : ""}</form>`,
        email: `<form class="sim-form" id="sim-email-form">
          <label>E-mail para entrar em outro aparelho <input type="email" required autocomplete="email" id="sim-email"></label>
          <p class="note">Enviamos um link de confirmação. Depois, use o mesmo e-mail para entrar em outro aparelho.</p>
          <button type="submit" class="btn-primary btn-sm">Enviar link</button></form>`,
      };
      const loginAction = user.hasEmail ? `<span class="note">Login por e-mail ligado</span>` : `<button type="button" class="btn-secondary btn-sm" id="sim-email-open">Usar em outro aparelho</button>`;
      return `<div class="sim-account-sheet">
        <p>Participando ${who} · ${notices}.</p>
        <div class="sim-account-actions">
          <button type="button" class="btn-secondary btn-sm" id="sim-profile-open">Apelido e ranking</button>
          <button type="button" class="btn-secondary btn-sm" id="sim-contact-open">Avisos por e-mail</button>
          ${loginAction}
        </div>
        ${forms[cloudState.open] || ""}
        <p class="sim-account-danger"><button type="button" class="link-button" id="sim-signout">Sair</button> · <button type="button" class="link-button" id="sim-delete">Apagar minha participação</button></p>
        ${status}</div>`;
    }

    function openAccountSheet() {
      if (!cloud || !window.AIndaDaShell) return;
      window.AIndaDaShell.openSheet("Conta do Simulador", accountBodyHtml(), (dialog) => {
        bindAccount(dialog);
      });
    }

    function bindAccount(root) {
      if (!cloud || !root) return;
      const on = (id, event, handler) => { const element = root.querySelector(`#${id}`); if (element) element.addEventListener(event, handler); };
      const refreshSheetAndPage = () => {
        rerender();
        const dialog = document.getElementById("app-sheet");
        if (dialog && dialog.open) openAccountSheet();
      };
      const toggle = (panel) => () => { cloudState.open = cloudState.open === panel ? "" : panel; openAccountSheet(); };
      ["login", "profile", "contact", "email"].forEach((panel) => on(`sim-${panel}-open`, "click", toggle(panel)));
      on("sim-join", "click", async () => {
        setStatus("Entrando…");
        try {
          cloudState.user = await cloud.join(captchaHost(root));
          [cloudState.profile, cloudState.contact] = await Promise.all([cloud.profile(), cloud.contact()]);
          const notes = [];
          for (const item of store.saved) if (!item.server_id) notes.push(await pushToServer(item));
          await refreshScores();
          cloudState.open = "profile";
          cloudState.status = `Participando.${notes.join("")} Escolha um apelido para aparecer no ranking.`;
        } catch (error) {
          cloudState.status = `Não deu para participar agora (${error.message}).`;
        }
        refreshSheetAndPage();
      });
      on("sim-login-form", "submit", async (event) => {
        event.preventDefault();
        try {
          await cloud.signInWithEmail(root.querySelector("#sim-login-email").value.trim(), captchaHost(root));
          setStatus("Enviamos um link para esse e-mail. Abra-o neste aparelho para entrar.");
        } catch (error) { setStatus(`Não deu para enviar o link (${error.message}).`); }
      });
      on("sim-email-form", "submit", async (event) => {
        event.preventDefault();
        try {
          await cloud.linkEmail(root.querySelector("#sim-email").value.trim());
          setStatus("Enviamos um link de confirmação. Depois de confirmar, use o mesmo e-mail para entrar em outro aparelho.");
        } catch (error) { setStatus(`Não deu para ligar o e-mail (${error.message}).`); }
      });
      on("sim-contact-form", "submit", async (event) => {
        event.preventDefault();
        const email = root.querySelector("#sim-contact-email").value.trim();
        if (!EMAIL.test(email)) { setStatus("Confira o e-mail."); return; }
        try {
          await cloud.saveContact(email, root.querySelector("#sim-contact-notify").checked);
          cloudState.contact = await cloud.contact();
          cloudState.open = "";
          cloudState.status = "E-mail salvo para os avisos de pontuação.";
          refreshSheetAndPage();
        } catch (error) { setStatus(`Não deu para salvar o e-mail (${error.message}).`); }
      });
      on("sim-contact-delete", "click", async () => {
        try {
          await cloud.deleteContact();
          cloudState.contact = null; cloudState.open = ""; cloudState.status = "E-mail removido.";
          refreshSheetAndPage();
        } catch (error) { setStatus(`Não deu para remover (${error.message}).`); }
      });
      on("sim-profile-form", "submit", async (event) => {
        event.preventDefault();
        const nickname = root.querySelector("#sim-nickname").value.trim();
        const inRanking = root.querySelector("#sim-in-ranking").checked;
        if (nickname.includes("@")) { setStatus("O apelido não pode ter @: não use seu e-mail."); return; }
        if (nickname && !NICKNAME.test(nickname)) { setStatus("Apelido com 3 a 20 letras, números, espaço, ponto, hífen ou _."); return; }
        if (inRanking && !nickname) { setStatus("Para aparecer no ranking, escolha um apelido."); return; }
        try {
          await cloud.saveProfile(nickname, inRanking);
          cloudState.profile = await cloud.profile();
          cloudState.open = "";
          cloudState.status = "Apelido salvo.";
          refreshSheetAndPage();
        } catch (error) { setStatus(`Não deu para salvar (${error.message}).`); }
      });
      const leave = (message) => {
        cloudState.user = null; cloudState.profile = null; cloudState.contact = null; cloudState.scores = {};
        cloudState.open = ""; cloudState.status = message;
        store.saved.forEach((item) => { if (item.server_id) item.detached = true; });
        writeStore();
        refreshSheetAndPage();
      };
      on("sim-signout", "click", async () => {
        const warning = cloudState.user && !cloudState.user.hasEmail
          ? "Sua participação não tem login por e-mail: ao sair, você não consegue voltar a ela, e as simulações enviadas continuam no servidor. Para tirá-las de lá, use \"Apagar minha participação\". Sair mesmo assim?"
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

    /* ---------------- Início (Kanban #43 · 2C: prévia viva + lista compacta de simulações) */

    function simulationLabel(item) { return item.server_id ? `#${item.server_id}` : `#${item.local_id}`; }

    /* Jogos que ainda faltavam num instante (mesma conta do banco, migração 0006): não cancelados e com a trava depois. */
    function remainingAt(moment) {
      const when = moment ? new Date(moment) : new Date();
      return snapshot.matches.filter((match) => match.status !== "cancelled" && lockTime(match) > when).length;
    }

    /* Deflator da Classificação: pontos × (jogos que faltavam ÷ jogos da temporada). O banco guarda pontos × jogos que
       faltavam (inteiro, mesma ordem no ranking); a página divide pelo total para mostrar. */
    const seasonMatches = snapshot.matches.filter((match) => match.status !== "cancelled").length;
    const deflated = (product) => (product / seasonMatches).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const weighted = (points, remaining) => deflated(points * remaining);

    function scoreSummary(item) {
      if (item.mode === "classificacao") {
        const score = tableScore(item.entry.order);
        const left = remainingAt(item.updated_at);
        return `<strong>${score.points}</strong> pontos com a tabela de hoje (até <strong>${score.ceiling}</strong> de ${score.maximum}) × ${left}/${seasonMatches} ${left === 1 ? "jogo que faltava" : "jogos que faltavam"} = <strong>${weighted(score.points, left)}</strong> no ranking`;
      }
      const score = pickScore(item.mode, item.entry);
      const server = item.server_id && cloudState.scores[item.server_id];
      const counted = server ? ` · no ranking: ${server.points} de ${server.max_points}` : "";
      if (!score.scored) return `Nenhum jogo terminou ainda · até <strong>${score.ceiling}</strong> pontos possíveis${counted}`;
      return `<strong>${score.points}</strong> de ${score.outOf} pontos em ${score.scored} ${score.scored === 1 ? "jogo" : "jogos"} · ainda dá para chegar a <strong>${score.ceiling}</strong>${counted}`;
    }

    function compactScore(item) {
      if (item.mode === "classificacao") {
        const score = tableScore(item.entry.order);
        const left = remainingAt(item.updated_at);
        return { big: `${score.points} pts`, sub: `até ${score.ceiling} · ${weighted(score.points, left)} no ranking` };
      }
      const score = pickScore(item.mode, item.entry);
      if (!score.scored) return { big: "—", sub: `aguardando · até ${score.ceiling} pts` };
      return { big: `${score.points} pts`, sub: `de ${score.outOf} em ${score.scored} ${score.scored === 1 ? "jogo" : "jogos"}` };
    }

    function nextOpenMatch() {
      const now = new Date();
      return deck.find((match) => lockTime(match) > now) || deck[0] || null;
    }

    function ensurePreviewDefaults(match) {
      if (!view.previewMode) view.previewMode = match ? "placar" : "classificacao";
      if (!match && view.previewMode !== "classificacao") view.previewMode = "classificacao";
      if (match && view.previewMatchId !== match.match_id) {
        view.previewMatchId = match.match_id;
        const top = match.top_scores && match.top_scores[0];
        view.previewScore = top ? [top.home_goals, top.away_goals] : [1, 0];
        const probs = [["H", match.p_home || 0], ["D", match.p_draw || 0], ["A", match.p_away || 0]];
        view.previewPick = probs.sort((a, b) => b[1] - a[1])[0][0];
      }
    }

    function previewStageHtml(mode, match) {
      if (mode === "classificacao" || !match) {
        const lockedChamp = clubIds.filter((id) => lockLabelOf("champion", id));
        const lockedG4 = clubIds.filter((id) => lockLabelOf("top4", id)).slice(0, LIBERTADORES_GROUPS);
        const lockedZ4 = clubIds.filter((id) => lockLabelOf("relegated", id)).slice(0, RELEGATED);
        const topModel = [...snapshot.teams].sort((a, b) => a.expected_position - b.expected_position);
        const champShown = lockedChamp[0] || topModel[0].club_id;
        const g4Shown = lockedG4.length ? lockedG4 : topModel.slice(0, LIBERTADORES_GROUPS).map((t) => t.club_id);
        const z4Open = Math.max(0, RELEGATED - lockedZ4.length);
        return `<div class="sim-live-stage">
          <div class="sim-live-top"><span>Sem jogo a jogo · ~1 min</span><span class="mc-badge">Direto na tabela</span></div>
          <div class="sim-class-rows">
            <div class="sim-class-row"><span>Campeão</span><span class="sim-class-val">${crest(champShown, 22)}<strong>${escapeHtml(nameOf(champShown))}</strong>${lockedChamp.length ? `<small>(travado)</small>` : ""}</span></div>
            <div class="sim-class-row"><span class="is-g4">G4</span><span class="sim-class-val">${g4Shown.map((id) => crest(id, 22)).join("")}</span></div>
            <div class="sim-class-row"><span class="is-z4">Z4</span><span class="sim-class-val">${lockedZ4.map((id) => crest(id, 22)).join("")}${z4Open ? `<small class="is-open">+${z4Open} ${z4Open === 1 ? "vaga aberta" : "vagas abertas"}</small>` : ""}</span></div>
          </div>
        </div>`;
      }
      const when = `${formatShortDate(match.match_date)}${kickoffClock(match) ? ` · ${kickoffClock(match)}` : ""}${match.round ? ` · R${match.round}` : ""}`;
      if (mode === "vencedor") {
        const opt = (key, label, probability) => `<button type="button" class="sim-pick-btn${view.previewPick === key ? " is-on" : ""}" data-prev-pick="${key}" aria-pressed="${view.previewPick === key}"><span>${label}</span><small>${pct(probability)}</small></button>`;
        return `<div class="sim-live-stage">
          <div class="sim-live-top"><span>Próximo jogo · ${escapeHtml(when)}</span><span class="mc-badge">1 toque · já entra salvo</span></div>
          <div class="sim-live-teams"><span class="sim-live-team">${crest(match.home_id, 34)}<span>${escapeHtml(nameOf(match.home_id))}</span></span><span class="sim-live-vs">VS</span><span class="sim-live-team">${crest(match.away_id, 34)}<span>${escapeHtml(nameOf(match.away_id))}</span></span></div>
          <div class="sim-pick-1x2">${opt("H", shortName(match.home_id), match.p_home)}${opt("D", "Empate", match.p_draw)}${opt("A", shortName(match.away_id), match.p_away)}</div>
        </div>`;
      }
      const [sh, sa] = view.previewScore;
      return `<div class="sim-live-stage">
        <div class="sim-live-top"><span>Próximo jogo · ${escapeHtml(when)}</span><span class="mc-badge">Já vale como 1º palpite</span></div>
        <div class="sim-mini-score">
          <div class="sim-mini-side">${crest(match.home_id, 34)}<span class="sim-mini-name">${escapeHtml(nameOf(match.home_id))}</span>
            <div class="sim-mini-ctrl"><button type="button" data-prev-goal="0" data-delta="-1" aria-label="Menos um gol de ${escapeHtml(nameOf(match.home_id))}">−</button><strong>${sh}</strong><button type="button" data-prev-goal="0" data-delta="1" aria-label="Mais um gol de ${escapeHtml(nameOf(match.home_id))}">+</button></div>
          </div>
          <span class="sim-mini-x" aria-hidden="true">×</span>
          <div class="sim-mini-side">${crest(match.away_id, 34)}<span class="sim-mini-name">${escapeHtml(nameOf(match.away_id))}</span>
            <div class="sim-mini-ctrl"><button type="button" data-prev-goal="1" data-delta="-1" aria-label="Menos um gol de ${escapeHtml(nameOf(match.away_id))}">−</button><strong>${sa}</strong><button type="button" data-prev-goal="1" data-delta="1" aria-label="Mais um gol de ${escapeHtml(nameOf(match.away_id))}">+</button></div>
          </div>
        </div>
        <p class="sim-live-probs">Modelo: ${shortName(match.home_id)} ${pct(match.p_home)} · Emp ${pct(match.p_draw)} · ${shortName(match.away_id)} ${pct(match.p_away)}</p>
      </div>`;
    }

    function renderHome(notice) {
      const active = store.active;
      const previewMatch = nextOpenMatch();
      ensurePreviewDefaults(previewMatch);
      const pm = view.previewMode;
      const [sh, sa] = view.previewScore;
      const ctaText = pm === "classificacao" || !previewMatch
        ? "Montar minha classificação ›"
        : pm === "placar"
          ? `Começar com ${shortName(previewMatch.home_id)} ${sh}×${sa} ${shortName(previewMatch.away_id)} ›`
          : `Começar com ${view.previewPick === "D" ? "Empate" : shortName(view.previewPick === "H" ? previewMatch.home_id : previewMatch.away_id)} ›`;

      const draftBlock = active ? (() => {
        const steps = stepsOf(active.mode);
        const editing = active.savedId ? store.saved.find((item) => item.local_id === active.savedId) : null;
        return `<div class="sim-draft-note" role="region" aria-label="Simulação em andamento">
          <span>Rascunho de <strong>${MODES[active.mode].label}</strong>${editing ? ` (${escapeHtml(simulationLabel(editing))})` : ""} · Passo ${Math.min(active.step, steps.length)}/${steps.length}</span>
          <span class="sim-draft-actions"><a class="block-link" href="#/simular/fazer">Continuar ›</a><button type="button" class="link-button" id="sim-discard">Descartar</button></span>
          ${store.pendingLink ? `<p class="note sim-draft-link">Link de ${MODES[store.pendingLink.mode].label} aguardando. <button type="button" class="link-button" id="sim-open-link">Abrir link</button></p>` : ""}
        </div>`;
      })() : "";

      const saved = [...store.saved].sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at)));
      const savedHtml = saved.length
        ? saved.map((item) => {
            const sc = compactScore(item);
            const originMeta = item.server_id && !item.detached ? "No ranking" : "Só neste aparelho";
            const closedTag = isClosed(item) ? " · fechada" : "";
            return `<a class="sim-saved-row" href="#/simular/ver/${encodeURIComponent(item.local_id)}">
              <span class="sim-saved-left">
                <span class="sim-saved-top"><span class="sim-mode-chip is-${item.mode}">${MODES[item.mode].label}</span><span class="sim-saved-id">${escapeHtml(simulationLabel(item))}</span><span class="sim-saved-origin">${originMeta}${closedTag}</span></span>
                <span class="sim-saved-sub">${sc.sub} · ${escapeHtml(formatDay(item.updated_at))}</span>
              </span>
              <span class="sim-saved-right"><strong>${sc.big}</strong><span class="mc-go" aria-hidden="true">›</span></span>
            </a>`;
          }).join("")
        : `<p class="sim-saved-empty">Nenhuma simulação salva ainda. Comece um palpite e salve para acompanhar sua pontuação aqui.</p>`;

      const roundsLeft = rounds.length;
      const heroSub = remaining.length
        ? `${remaining.length} ${remaining.length === 1 ? "jogo restante" : "jogos restantes"}${roundsLeft ? ` em ${roundsLeft} ${roundsLeft === 1 ? "rodada" : "rodadas"}` : ""} · o modelo pode completar o que você pular`
        : "Todos os jogos desta edição já terminaram.";

      shell("", "Simulador", "", `
        ${notice ? `<p class="sim-banner" role="status">${notice}</p>` : ""}
        <div class="sim-home-grid">
          <section class="card sim-hero-card" aria-labelledby="sim-hero-title">
            <div>
              <h2 class="sim-hero-title" id="sim-hero-title">Simule a reta final</h2>
              <p class="sim-hero-sub">${heroSub}</p>
            </div>
            <div class="sim-mode-seg" role="tablist" aria-label="Modo de simulação">
              <button type="button" data-prev-mode="placar" role="tab" aria-selected="${pm === "placar"}" ${!previewMatch ? "disabled" : ""}>Placar exato</button>
              <button type="button" data-prev-mode="vencedor" role="tab" aria-selected="${pm === "vencedor"}" ${!previewMatch ? "disabled" : ""}>Vencedor</button>
              <button type="button" data-prev-mode="classificacao" role="tab" aria-selected="${pm === "classificacao"}">Classificação</button>
            </div>
            ${previewStageHtml(pm, previewMatch)}
            <button type="button" class="btn-primary sim-hero-cta" id="sim-start-preview">${ctaText}</button>
            ${draftBlock}
          </section>

          <section class="sim-list-card" id="sim-minhas" aria-labelledby="sim-minhas-title">
            <div class="sim-list-head">
              <div>
                <h2 id="sim-minhas-title">Minhas simulações</h2>
                <p class="sim-list-sub">${saved.length ? `${saved.length} ${saved.length === 1 ? "salva" : "salvas"} neste aparelho` : "Acompanhe sua pontuação aqui"}</p>
              </div>
              ${cloud ? `<a class="block-link" href="#/simular/ranking">Ranking ›</a>` : ""}
            </div>
            <div class="sim-saved-list">${savedHtml}</div>
          </section>
        </div>`);

      main.querySelectorAll("[data-prev-mode]").forEach((btn) => btn.addEventListener("click", () => {
        view.previewMode = btn.dataset.prevMode;
        renderHome();
      }));
      main.querySelectorAll("[data-prev-pick]").forEach((btn) => btn.addEventListener("click", () => {
        view.previewPick = btn.dataset.prevPick;
        renderHome();
      }));
      main.querySelectorAll("[data-prev-goal]").forEach((btn) => btn.addEventListener("click", () => {
        const side = Number(btn.dataset.prevGoal);
        const delta = Number(btn.dataset.delta);
        view.previewScore[side] = Math.max(0, Math.min(MAX_GOALS_INPUT, view.previewScore[side] + delta));
        renderHome();
      }));
      const startBtn = document.getElementById("sim-start-preview");
      if (startBtn) startBtn.addEventListener("click", () => {
        if (store.active && !window.confirm(`Você já tem um rascunho de ${MODES[store.active.mode].label}. Descartar esse rascunho e começar uma nova simulação de ${MODES[pm].label}?`)) return;
        if (pm === "classificacao" || !previewMatch) {
          startSession("classificacao", null, null);
          go("#/simular/fazer");
          return;
        }
        const entry = emptyEntry(pm);
        if (lockTime(previewMatch) > new Date()) {
          entry.picks[previewMatch.match_id] = pm === "placar" ? [...view.previewScore] : view.previewPick;
        }
        startSession(pm, null, entry);
        store.active.step = 2;
        const firstIdx = deck.findIndex((m) => m.match_id === previewMatch.match_id);
        store.active.cursor = firstIdx >= 0 && firstIdx + 1 < deck.length ? firstIdx + 1 : 0;
        writeStore();
        go("#/simular/fazer");
      });
      const openLink = document.getElementById("sim-open-link");
      if (openLink) openLink.addEventListener("click", () => {
        if (!window.confirm("Descartar o rascunho em andamento e abrir a simulação do link?")) return;
        const link = store.pendingLink;
        store.pendingLink = null;
        endSession();
        go(`#/simular/${link.mode}/l/${link.code}`);
      });
      const discard = document.getElementById("sim-discard");
      if (discard) discard.addEventListener("click", () => {
        if (!window.confirm(`Descartar o rascunho de ${MODES[active.mode].label}? O que você preencheu nele se perde.`)) return;
        endSession();
        renderHome("Rascunho descartado.");
      });
    }

    /* ---------------- Passo a passo */

    function stepper(mode, step) {
      const steps = stepsOf(mode);
      return `<ol class="sim-stepper" aria-label="Passos">${steps.map((label, index) => {
        const number = index + 1;
        const state = number < step ? "is-done" : number === step ? "is-current" : "";
        return `<li class="${state}" ${number === step ? 'aria-current="step"' : ""}><span class="sim-step-number">${number < step ? "✓" : number}</span><span>${label}</span></li>`;
      }).join("")}</ol>`;
    }

    function sessionHeader(active) {
      const editing = active.savedId ? store.saved.find((item) => item.local_id === active.savedId) : null;
      return `<div class="sim-session">
        <p class="sim-session-title"><strong>${MODES[active.mode].label}</strong>${editing ? ` · editando ${escapeHtml(simulationLabel(editing))}` : " · simulação nova"}</p>
        <p class="sim-session-actions"><a href="#/simular" class="link-button">Sair (o rascunho fica guardado)</a> · <button type="button" class="link-button" id="sim-session-discard">Descartar</button></p>
      </div>
      ${stepper(active.mode, active.step)}`;
    }

    function navBar(previousLabel, nextLabel, blocked) {
      return `<div class="sim-savebar">
        ${blocked ? `<p class="sim-warning">${blocked}</p>` : ""}
        ${previousLabel ? `<button type="button" class="sim-button is-secondary" id="sim-back">${previousLabel}</button>` : ""}
        <button type="button" class="sim-button" id="sim-next" ${blocked ? "disabled" : ""}>${nextLabel}</button>
        <span class="note" id="sim-save-status" aria-live="polite"></span>
      </div>`;
    }

    function bindSession(active, back, next) {
      document.getElementById("sim-session-discard").addEventListener("click", () => {
        if (!window.confirm("Descartar esta simulação? O que você preencheu nela se perde.")) return;
        endSession();
        go("#/simular");
      });
      const backButton = document.getElementById("sim-back");
      if (backButton && back) backButton.addEventListener("click", back);
      const nextButton = document.getElementById("sim-next");
      if (nextButton && next) nextButton.addEventListener("click", next);
    }

    function moveStep(active, step) { active.step = step; writeStore(); rerender(); window.scrollTo(0, 0); }

    async function saveActive() {
      if (view.saving) return;
      view.saving = true;
      main.querySelectorAll(".sim-savebar button").forEach((button) => { button.disabled = true; });
      const active = store.active;
      const now = new Date().toISOString();
      let item = active.savedId ? store.saved.find((saved) => saved.local_id === active.savedId) : null;
      if (item) { item.entry = clone(active.entry); item.updated_at = now; }
      else {
        item = { local_id: newLocalId(), server_id: null, mode: active.mode, created_at: now, updated_at: now, entry: clone(active.entry) };
        store.saved.push(item);
      }
      writeStore();
      const status = document.getElementById("sim-save-status");
      if (status) status.textContent = "Salvando…";
      const note = await pushToServer(item);
      if (cloud && cloudState.user) await refreshScores();
      store.done = { local_id: item.local_id, note, cheer: pickOne(savedCheers) };
      view.saving = false;
      endSession();
      go(`#/simular/ver/${encodeURIComponent(item.local_id)}`);
    }

    function renderSession() {
      const active = store.active;
      if (!active) { renderHome(); return; }
      active.entry = sanitize(active.mode, active.entry);
      if (active.mode === "classificacao") {
        if (active.step <= 3) renderTablePick(active);
        else if (active.step === 4) renderTableAdjust(active);
        else renderTableReview(active);
      } else if (active.step === 1) renderFillChoice(active);
      else if (active.step === 2) renderDeck(active);
      else renderReview(active);
    }

    /* ---------------- Mensagens */

    const pickOne = (options) => options[Math.floor(Math.random() * options.length)];
    const outcomeName = (match, outcome) => (outcome === "H" ? nameOf(match.home_id) : outcome === "A" ? nameOf(match.away_id) : "o empate");
    const outcomeProbability = (match, outcome) => (outcome === "H" ? match.p_home : outcome === "A" ? match.p_away : match.p_draw);

    function hintFor(match) {
      const options = [["H", match.p_home], ["D", match.p_draw], ["A", match.p_away]];
      const [favorite, top] = options.filter(([key]) => key !== "D").sort((left, right) => right[1] - left[1])[0];
      const team = escapeHtml(outcomeName(match, favorite));
      if (top >= 0.65) return `<strong>Favoritaço.</strong> O modelo dá ${pct(top)} para ${team}.`;
      if (top >= 0.5) return `<strong>${team} é favorito</strong> (${pct(top)}), mas zebra acontece.`;
      if (match.p_draw >= 0.3) return `<strong>Cheiro de empate:</strong> ${pct(match.p_draw)} de probabilidade de ficar tudo igual.`;
      return `<strong>Jogo parelho:</strong> ninguém passa de ${pct(top)} no modelo.`;
    }

    function cheerFor(match, outcome) {
      const probability = outcomeProbability(match, outcome);
      if (probability < 0.2) return pickOne([`Corajoso! O modelo dá só ${pct(probability)} para isso.`, "Zebra anotada. Se der, você vai lembrar.", "Isso é que é acreditar."]);
      if (probability >= 0.5) return pickOne(["Seguindo a lógica.", "Anotado. O modelo concorda.", "Faz sentido."]);
      return pickOne(["Anotado.", "Fechado.", "Bora para o próximo."]);
    }

    function progressCheer(filled, total) {
      const left = total - filled;
      if (!left) return "Tudo preenchido! Vamos revisar a tabela?";
      if (left <= 5) return `Faltam só ${left}!`;
      if (filled === Math.ceil(total / 2)) return "Metade do caminho!";
      return "";
    }

    function championCheer(clubId) {
      const probability = teamById[clubId].title;
      const name = escapeHtml(nameOf(clubId));
      if (probability >= 0.5) return `Aposta segura: o modelo também vê ${name} na frente (${pct(probability)}).`;
      if (probability >= 0.1) return `Boa briga: o modelo dá ${pct(probability)} de título para ${name}.`;
      return `Coragem! O modelo dá só ${pct(probability)} de título para ${name}.`;
    }

    const savedCheers = ["Simulação salva! Agora é torcer.", "Pronto! Que comecem os jogos.", "Salva. Daqui para a frente, é com os times."];

    /* ---------------- Classificação: campeão, G4, rebaixados, ajustar, revisar */

    /* Travas da Classificação (decisão do dono, 2026-11-07): entra travado quem a matemática já pôs na faixa e quem
       ficou nela em todas as simulações do modelo (100%), mesmo sem certeza matemática; a etiqueta diz qual dos dois. */
    const everySimulation = `em todas as ${snapshot.n_simulations.toLocaleString("pt-BR")} simulações`;
    const ZONE_LOCKS = {
      champion: { math: (clubId) => reach[clubId].worst === 1, model: (clubId) => teamById[clubId].title >= 1,
        mathLabel: "campeão pela matemática", modelLabel: `campeão ${everySimulation}`, inZone: (index) => index === 0, zoneName: "campeão" },
      top4: { math: (clubId) => reach[clubId].worst <= LIBERTADORES_GROUPS, model: (clubId) => teamById[clubId].top4 >= 1,
        mathLabel: "garantido no G4 pela matemática", modelLabel: `no G4 ${everySimulation}`, inZone: (index) => index < LIBERTADORES_GROUPS, zoneName: "no G4" },
      relegated: { math: (clubId) => reach[clubId].best > clubIds.length - RELEGATED, model: (clubId) => teamById[clubId].relegation >= 1,
        mathLabel: "rebaixado pela matemática", modelLabel: `rebaixado ${everySimulation}`, inZone: (index) => index >= clubIds.length - RELEGATED, zoneName: "no rebaixamento" },
    };
    const lockLabelOf = (zone, clubId) => (ZONE_LOCKS[zone].math(clubId) ? ZONE_LOCKS[zone].mathLabel : ZONE_LOCKS[zone].model(clubId) ? ZONE_LOCKS[zone].modelLabel : "");

    /* Clubes travados fora da faixa deles na ordem montada (o ajuste fino não pode tirá-los de lá). */
    function zoneProblems(order) {
      const problems = new Map();
      order.forEach((clubId, index) => {
        Object.entries(ZONE_LOCKS).forEach(([zone, lock]) => {
          const label = lockLabelOf(zone, clubId);
          if (label && !lock.inZone(index) && !(zone === "top4" && index === 0)) problems.set(clubId, `Travado ${lock.zoneName}: ${label}.`);
        });
      });
      return problems;
    }

    const TABLE_STEPS = {
      1: { key: "champion", count: 1, title: "Quem leva o título?", lede: "Escolha o campeão. Quem já não alcança o 1º lugar fica de fora.", allowed: (clubId) => reach[clubId].best === 1,
        forced: (clubId) => Boolean(lockLabelOf("champion", clubId)), forcedLabel: (clubId) => lockLabelOf("champion", clubId) },
      2: { key: "top4", count: LIBERTADORES_GROUPS - 1, title: "Quem completa o G4?", lede: `Escolha mais ${LIBERTADORES_GROUPS - 1} clubes para a fase de grupos da Libertadores. Quem já está garantido no G4 entra travado.`, allowed: (clubId) => reach[clubId].best <= LIBERTADORES_GROUPS,
        forced: (clubId) => Boolean(lockLabelOf("top4", clubId)), forcedLabel: (clubId) => lockLabelOf("top4", clubId) },
      3: { key: "relegated", count: RELEGATED, title: "Quem cai?", lede: `Escolha os ${RELEGATED} rebaixados. Quem já não pode cair fica de fora, e quem já caiu entra travado.`, allowed: (clubId) => reach[clubId].worst > clubIds.length - RELEGATED,
        forced: (clubId) => Boolean(lockLabelOf("relegated", clubId)), forcedLabel: (clubId) => lockLabelOf("relegated", clubId) },
    };

    function tablePicks(active) {
      if (!active.table) active.table = { champion: [], top4: [], relegated: [] };
      return active.table;
    }

    function orderFromPicks(picks) {
      const byModel = [...clubIds].sort((left, right) => teamById[left].expected_position - teamById[right].expected_position);
      const chosen = new Set([...picks.champion, ...picks.top4, ...picks.relegated]);
      const sortModel = (list) => [...list].sort((left, right) => teamById[left].expected_position - teamById[right].expected_position);
      return [...picks.champion, ...sortModel(picks.top4), ...byModel.filter((clubId) => !chosen.has(clubId)), ...sortModel(picks.relegated)];
    }

    function clubCard(clubId, selected, disabled, detail, lockedLabel) {
      const team = teamById[clubId];
      if (lockedLabel) {
        return `<div class="sim-club-card is-selected is-locked" aria-label="${escapeHtml(nameOf(clubId))}: ${escapeHtml(lockedLabel)}">
        <span class="sim-club-crest">${crest(clubId, 40)}</span>
        <span class="sim-club-name">${escapeHtml(nameOf(clubId))}</span>
        <span class="sim-club-meta">${currentPoints[clubId]} pts · ${team.current_position}º hoje</span>
        <span class="sim-club-chance">${escapeHtml(lockedLabel)}</span>
      </div>`;
      }
      return `<button type="button" class="sim-club-card ${selected ? "is-selected" : ""}" data-club="${escapeHtml(clubId)}" aria-pressed="${selected}" ${disabled ? "disabled" : ""}>
        <span class="sim-club-crest">${crest(clubId, 40)}</span>
        <span class="sim-club-name">${escapeHtml(nameOf(clubId))}</span>
        <span class="sim-club-meta">${currentPoints[clubId]} pts · ${team.current_position}º hoje</span>
        <span class="sim-club-chance">${disabled ? "já não alcança" : detail}</span>
      </button>`;
    }

    function renderTablePick(active) {
      const config = TABLE_STEPS[active.step];
      const picks = tablePicks(active);
      const taken = new Set(Object.entries(picks).filter(([key]) => key !== config.key).flatMap(([, list]) => list));
      const current = picks[config.key];
      // Quem a matemática já pôs nesta faixa entra primeiro e não sai.
      const forced = clubIds.filter((clubId) => !taken.has(clubId) && config.forced(clubId));
      forced.forEach((clubId) => { if (!current.includes(clubId)) current.unshift(clubId); });
      if (current.length > config.count) current.splice(0, current.length, ...forced, ...current.filter((clubId) => !forced.includes(clubId)).slice(0, Math.max(0, config.count - forced.length)));
      const metric = config.key === "champion" ? "title" : config.key === "top4" ? "top4" : "relegation";
      const label = config.key === "champion" ? "de título" : config.key === "top4" ? "de G4" : "de queda";
      const clubs = [...clubIds].filter((clubId) => !taken.has(clubId))
        .sort((left, right) => (teamById[right][metric] - teamById[left][metric]) || (teamById[left].expected_position - teamById[right].expected_position));
      const cards = clubs.map((clubId) => clubCard(clubId, current.includes(clubId), !config.allowed(clubId), `${pct(teamById[clubId][metric])} ${label} no modelo`, forced.includes(clubId) ? config.forcedLabel(clubId) : "")).join("");
      const done = current.length === config.count;
      const cheer = config.key === "champion" && current.length ? championCheer(current[0])
        : done ? pickOne(["Escolhas feitas.", "Fechado!", "Pronto, próximo passo."]) : `${current.length} de ${config.count} escolhidos.`;
      shell("", config.title, config.lede, `${sessionHeader(active)}
        <p class="sim-cheer" aria-live="polite">${cheer}</p>
        <div class="sim-club-grid">${cards}</div>
        ${navBar(active.step > 1 ? "Voltar" : "", active.step === 3 ? "Montar a tabela" : "Próximo", done ? "" : `Escolha ${config.count === 1 ? "1 clube" : `${config.count} clubes`} para seguir.`)}`, { focus: true });
      bindSession(active,
        active.step > 1 ? () => moveStep(active, active.step - 1) : null,
        () => {
          if (active.step === 3) active.entry.order = orderFromPicks(picks);
          moveStep(active, active.step + 1);
        });
      main.querySelectorAll(".sim-club-card[data-club]").forEach((button) => button.addEventListener("click", () => {
        const clubId = button.dataset.club;
        const list = picks[config.key];
        if (list.includes(clubId)) list.splice(list.indexOf(clubId), 1);
        else if (config.count === 1) list.splice(0, list.length, clubId);
        else if (list.length < config.count) list.push(clubId);
        writeStore();
        const scroll = window.scrollY;
        renderTablePick(active);
        window.scrollTo(0, scroll);
      }));
    }

    function renderTableAdjust(active, focusClub, focusDirection) {
      const entry = active.entry;
      const order = entry.order;
      const problems = impossiblePairs(order);
      const locks = zoneProblems(order);
      const total = order.length;
      const blocked = problems.size ? `${problems.size === 1 ? "Uma posição é impossível" : `${problems.size} posições são impossíveis`} pela matemática. Corrija antes de seguir.`
        : locks.size ? `${locks.size === 1 ? "Um clube travado saiu" : `${locks.size} clubes travados saíram`} da faixa dele. Corrija antes de seguir.` : "";
      const rows = order.map((clubId, index) => {
        const position = index + 1;
        const zone = zoneOf(position, total);
        const problem = problems.get(clubId);
        const range = reach[clubId];
        const lockProblem = locks.get(clubId);
        return `<li class="sim-quick-row ${zone.key ? `zone-${zone.key}` : ""} ${problem || lockProblem ? "is-impossible" : ""}" draggable="true" data-club="${escapeHtml(clubId)}">
          <span class="sim-pos">${position}º</span>
          ${clubCell(clubId, 22)}
          <span class="sim-zone">${zone.label}</span>
          <span class="sim-model" title="Probabilidade do modelo de terminar exatamente nesta posição; entre parênteses, as posições que o clube ainda alcança">modelo ${pct(teamById[clubId].position_probabilities[index])} <span class="sim-reach">(${range.best}º–${range.worst}º)</span></span>
          <span class="sim-move">
            <button type="button" data-move="-1" aria-label="Subir ${escapeHtml(nameOf(clubId))}" ${index === 0 ? "disabled" : ""}>▲</button>
            <button type="button" data-move="1" aria-label="Descer ${escapeHtml(nameOf(clubId))}" ${index === total - 1 ? "disabled" : ""}>▼</button>
          </span>
          ${problem ? `<span class="sim-warning">Impossível: chega a no máximo ${maxPoints[clubId]} pontos e ${escapeHtml(nameOf(problem))} já tem ${currentPoints[problem]}.</span>` : ""}
          ${!problem && lockProblem ? `<span class="sim-warning">${escapeHtml(lockProblem)}</span>` : ""}
        </li>`;
      }).join("");
      shell("", "Ajuste a tabela", "Seu campeão, G4 e rebaixados já estão no lugar; o meio veio na ordem do modelo. Arraste as linhas ou use as setas para deixar do seu jeito.", `${sessionHeader(active)}
        <ol class="sim-quick" aria-label="Sua tabela final">${rows}</ol>
        <p class="note">"modelo" é a probabilidade de o clube terminar exatamente naquela posição; entre parênteses, as posições que ele ainda alcança.</p>
        ${navBar(active.savedId ? "" : "Refazer as escolhas", "Revisar", blocked)}`, { focus: true });
      bindSession(active, active.savedId ? null : () => moveStep(active, 3), () => moveStep(active, 5));
      const again = (club, direction) => renderTableAdjust(active, club, direction);
      const move = (clubId, target) => {
        const next = entry.order.filter((item) => item !== clubId);
        next.splice(Math.max(0, Math.min(next.length, target)), 0, clubId);
        entry.order = next;
        writeStore();
      };
      main.querySelectorAll(".sim-quick-row button[data-move]").forEach((button) => button.addEventListener("click", () => {
        const clubId = button.closest(".sim-quick-row").dataset.club;
        move(clubId, entry.order.indexOf(clubId) + Number(button.dataset.move));
        again(clubId, button.dataset.move);
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
          again();
        });
      });
      if (focusClub) {
        const button = main.querySelector(`.sim-quick-row[data-club="${CSS.escape(focusClub)}"] button[data-move="${focusDirection}"]`)
          || main.querySelector(`.sim-quick-row[data-club="${CSS.escape(focusClub)}"] button:not([disabled])`);
        if (button) button.focus();
      }
    }

    function highlightCards(items) {
      return `<div class="sim-highlights">${items.map((item) => `<div class="sim-highlight"><span class="sim-highlight-label">${item.label}</span><span class="sim-highlight-value">${item.value}</span>${item.note ? `<span class="sim-highlight-note">${item.note}</span>` : ""}</div>`).join("")}</div>`;
    }

    function renderTableReview(active) {
      const order = active.entry.order;
      const total = order.length;
      const score = tableScore(order);
      const problems = impossiblePairs(order);
      const rows = order.map((clubId, index) => {
        const zone = zoneOf(index + 1, total);
        return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${index + 1}</td><td>${clubCell(clubId)}</td><td>${zone.label}</td><td class="num">${pct(teamById[clubId].position_probabilities[index])}</td></tr>`;
      }).join("");
      const relegated = order.slice(total - RELEGATED);
      shell("", "Revise e salve", "Confira a sua tabela antes de salvar.", `${sessionHeader(active)}
        ${highlightCards([
          { label: "Seu campeão", value: clubCell(order[0], 24), note: `modelo: ${pct(teamById[order[0]].title)}` },
          { label: "Seu G4", value: order.slice(0, LIBERTADORES_GROUPS).map((clubId) => crest(clubId, 24)).join(""), note: order.slice(1, LIBERTADORES_GROUPS).map((clubId) => escapeHtml(teamById[clubId].short_name || nameOf(clubId))).join(" · ") },
          { label: "Seus rebaixados", value: relegated.map((clubId) => crest(clubId, 24)).join(""), note: relegated.map((clubId) => escapeHtml(teamById[clubId].short_name || nameOf(clubId))).join(" · ") },
          { label: "Pontuação", value: `${score.points}`, note: `com a tabela de hoje · até ${score.ceiling} de ${score.maximum} · no ranking, × ${remainingAt()}/${seasonMatches} jogos que faltam = ${weighted(score.points, remainingAt())}` },
        ])}
        ${jointSlot("sim-joint")}
        <div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Clube</th><th>Vaga</th><th class="num">Modelo</th></tr></thead><tbody>${rows}</tbody></table></div>
        ${navBar("Voltar e ajustar", active.savedId ? "Salvar alterações" : "Salvar simulação", problems.size ? "Há posições impossíveis: volte e ajuste." : zoneProblems(order).size ? "Há clube travado fora da faixa dele: volte e ajuste." : "")}`, { focus: true });
      bindSession(active, () => moveStep(active, 4), () => saveActive());
      fillJoint("sim-joint", order, true);
    }

    /* ---------------- Vencedor e Placar exato: como preencher, jogos (um cartão por vez), revisar */

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

    const FILL_CHOICES = [
      { key: "manual", icon: '<svg viewBox="0 0 24 24" width="28" height="28"><path d="M4 20l4-1 10-10-3-3L5 16l-1 4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M13 8l3 3" stroke="currentColor" stroke-width="1.8"/></svg>', title: "Eu escolho tudo", text: "Você decide cada jogo. O que ficar em branco fica fora da tabela final." },
      { key: "assist", icon: '<svg viewBox="0 0 24 24" width="28" height="28"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></svg>', title: "Eu escolho, o modelo completa", text: "Você decide os jogos que quiser; o modelo sorteia na hora um resultado para cada um que ficar em branco." },
      { key: "model", icon: '<svg viewBox="0 0 24 24" width="28" height="28"><rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="9" r="1.5" fill="currentColor"/><circle cx="15" cy="15" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>', title: "O modelo sorteia, eu reviso", text: "O modelo sorteia agora todos os jogos, com as probabilidades dele. Você passa os cartões e troca o que quiser." },
    ];

    function renderFillChoice(active) {
      const mode = active.mode;
      const cards = FILL_CHOICES.map((choice) => `<button type="button" class="sim-choice-card" data-fill="${choice.key}" ${!canSample && choice.key !== "manual" ? "disabled" : ""}>
          <span class="sim-choice-icon" aria-hidden="true">${choice.icon}</span><strong>${choice.title}</strong><span>${choice.text}</span></button>`).join("");
      shell("", "Como você quer jogar?", `${MODES[mode].what} ${MODES[mode].scoring}`, `${sessionHeader(active)}
        <div class="sim-choice-grid">${cards}</div>
        <p class="note">São ${remaining.length} jogos, um cartão por vez. Os resultados sorteados pelo modelo aparecem tracejados e valem pontos como os seus.</p>`, { focus: true });
      bindSession(active, null, null);
      main.querySelectorAll("[data-fill]").forEach((button) => button.addEventListener("click", () => {
        const choice = button.dataset.fill;
        active.entry.model = choice !== "manual";
        if (choice === "model") { active.entry.picks = {}; fillWithModel(mode, active.entry, true); }
        else if (choice === "assist") active.entry.sampled = {};
        else active.entry.sampled = {};
        active.cursor = 0;
        moveStep(active, 2);
      }));
    }

    const deck = rounds.flatMap((item) => item.matches);

    /* Placar com setas na vertical (REDESIGN_SPEC v2.1 §3.6): ↑ em cima, escudo, número e ↓ embaixo, 52 × 44 px. */
    function scoreStepper(side, value, label, clubId) {
      const arrow = (path) => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
      return `<div class="sim-vstep" role="group" aria-label="${escapeHtml(label)}">
        <button type="button" class="sim-vstep-btn" data-goal="${side}" data-delta="1" aria-label="Mais um gol de ${escapeHtml(nameOf(clubId))}">${arrow("M6 14l6-6 6 6")}</button>
        ${crest(clubId, 44)}
        <output class="sim-vstep-num">${value === null ? "–" : value}</output>
        <button type="button" class="sim-vstep-btn" data-goal="${side}" data-delta="-1" aria-label="Menos um gol de ${escapeHtml(nameOf(clubId))}">${arrow("M6 10l6 6 6-6")}</button>
        <span class="sim-vstep-name">${escapeHtml(nameOf(clubId))}</span></div>`;
    }

    const kickoffClock = (match) => (match.kickoff_utc ? new Date(match.kickoff_utc).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" }) : "");

    // As 3 pílulas 1X2 com a sigla dos clubes, como no Match Card; a maior ganha a borda de destaque.
    function modelPills(match) {
      const values = [match.p_home, match.p_draw, match.p_away];
      if (!values.every((value) => typeof value === "number")) return "";
      const top = Math.max(...values);
      const pill = (value, label) => `<span class="sim-odd${value === top ? " is-top" : ""}"><strong>${pct(value)}</strong>${escapeHtml(label)}</span>`;
      return `<p class="sim-mini-label">Probabilidade do modelo</p><div class="sim-odds">${pill(match.p_home, shortName(match.home_id))}${pill(match.p_draw, "Empate")}${pill(match.p_away, shortName(match.away_id))}</div>`;
    }

    // Seção 2 da D0: todos os jogos, agrupados por dia, com o palpite de cada um. No Vencedor, os 3 botões ficam na
    // própria linha (D2); no Placar, tocar na linha leva o card até o jogo.
    function dayList(mode, entry, cursor) {
      const picks = effectivePicks(entry);
      const groups = new Map();
      const roundOfCard = (deck[cursor] || {}).round;
      deck.forEach((match, index) => {
        if (match.round !== roundOfCard) return;
        const day = match.match_date || "";
        if (!groups.has(day)) groups.set(day, []);
        groups.get(day).push({ match, index });
      });
      const dayTitle = (day) => (day ? new Date(`${day}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" }).replace(".", "") : "Sem data");
      return [...groups.entries()].map(([day, items]) => `<p class="sim-day-title">${escapeHtml(dayTitle(day))}<span>${items.length} ${items.length === 1 ? "jogo" : "jogos"}</span></p>
        <div class="sim-day-list">${items.map(({ match, index }) => {
          const origin = originOf(entry, match.match_id);
          const pick = picks[match.match_id];
          const locked = lockTime(match) <= new Date();
          const teams = `${shortName(match.home_id)} × ${shortName(match.away_id)}`;
          const when = `${kickoffClock(match) || "–"}`;
          if (mode === "vencedor") {
            const option = (key, label, probability) => `<button type="button" class="sim-row-pick${pick === key ? (origin === "model" ? " is-model" : " is-chosen") : ""}" data-row-pick="${key}" data-match="${escapeHtml(match.match_id)}" aria-pressed="${pick === key}" ${locked ? "disabled" : ""}>${label}<small>${pct(probability)}</small></button>`;
            return `<div class="sim-day-row is-picks${index === cursor ? " is-current" : ""}">
              <p class="sim-day-meta">${kickoffClock(match) ? `<span>${escapeHtml(kickoffClock(match))}</span>` : ""}<span>${escapeHtml(nameOf(match.home_id))} × ${escapeHtml(nameOf(match.away_id))}</span></p>
              <div class="sim-row-picks" role="group" aria-label="${escapeHtml(`Palpite: ${nameOf(match.home_id)} × ${nameOf(match.away_id)}`)}">${option("H", shortName(match.home_id), match.p_home)}${option("D", "Empate", match.p_draw)}${option("A", shortName(match.away_id), match.p_away)}</div></div>`;
          }
          const value = pick === undefined ? `<span class="sim-day-pick is-empty">—</span>`
            : `<span class="sim-day-pick">${pick[0]} × ${pick[1]}<small>${index === cursor ? "neste card" : origin === "model" ? "do modelo" : "seu"}</small></span>`;
          return `<button type="button" class="sim-day-row${index === cursor ? " is-current" : ""}" data-jump="${index}" ${index === cursor ? 'aria-current="true"' : ""}>
            <span class="sim-day-time">${escapeHtml(when)}</span><span class="sim-day-teams">${teams}</span>${value}</button>`;
        }).join("")}</div>`).join("");
    }

    function renderDeck(active, cheer) {
      const mode = active.mode;
      const entry = active.entry;
      if (!deck.length) { moveStep(active, 3); return; }
      active.cursor = Math.max(0, Math.min(deck.length - 1, active.cursor || 0));
      const match = deck[active.cursor];
      const own = entry.picks[match.match_id];
      const sampled = own === undefined ? entry.sampled[match.match_id] : undefined;
      const value = own !== undefined ? own : sampled;
      const tally = counts(entry);
      const filled = tally.own + tally.sampled;
      const locked = lockTime(match) <= new Date();
      const off = locked ? "disabled" : "";
      const state = sampled !== undefined ? `<span class="sim-tag is-model">sorteado pelo modelo: confirme ou troque</span>` : own !== undefined ? `<span class="sim-tag is-own">seu palpite</span>` : "";
      let controls;
      if (mode === "vencedor") {
        const option = (key, text, probability) => `<button type="button" class="sim-outcome ${value === key ? (sampled !== undefined ? "is-model" : "is-chosen") : ""}" data-pick="${key}" aria-pressed="${value === key}" ${off}><span class="sim-outcome-label">${text}</span><span class="sim-outcome-prob">${pct(probability)}</span></button>`;
        controls = `<div class="sim-card-teams"><span class="sim-card-team">${crest(match.home_id, 44)}<span>${escapeHtml(nameOf(match.home_id))}</span></span><span class="sim-card-vs">×</span><span class="sim-card-team">${crest(match.away_id, 44)}<span>${escapeHtml(nameOf(match.away_id))}</span></span></div>
          <div class="sim-outcomes">${option("H", `Vitória do ${shortName(match.home_id)}`, match.p_home)}${option("D", "Empate", match.p_draw)}${option("A", `Vitória do ${shortName(match.away_id)}`, match.p_away)}</div>`;
      } else {
        const goals = active.draftScore && active.draftScore.match_id === match.match_id ? active.draftScore.value : value !== undefined ? value : [null, null];
        const quick = locked ? "" : (match.top_scores || []).map((score) => `<button type="button" class="sim-quick-score" data-score="${score.home_goals}-${score.away_goals}">${score.home_goals} × ${score.away_goals} <span>${pct(score.probability)}</span></button>`).join("");
        const probability = goals[0] !== null && goals[1] !== null && match.score_probabilities && match.score_probabilities[goals[0]] ? match.score_probabilities[goals[0]][goals[1]] || 0 : null;
        controls = `<div class="sim-score-pick${locked ? " is-locked" : ""}">${scoreStepper(0, goals[0], `Gols de ${nameOf(match.home_id)}`, match.home_id)}<span class="sim-score-x" aria-hidden="true">×</span>${scoreStepper(1, goals[1], `Gols de ${nameOf(match.away_id)}`, match.away_id)}</div>
          ${probability === null ? `<p class="sim-mini-label">Use as setas ou um dos placares mais prováveis.</p>` : ""}
          ${quick ? `<p class="sim-mini-label">Placares mais prováveis (toque para escolher)</p><div class="sim-quick-scores">${quick}</div>` : ""}`;
      }
      const message = cheer || progressCheer(filled, deck.length);
      const lockText = locked ? "fechado" : isPostponedMatch(match) ? "adiado, data a definir" : `trava às ${lockTime(match).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" })}`;
      const scoreLine = mode === "placar" && match.top_scores && match.top_scores.length
        ? `<p class="sim-mini-label">Mais provável: ${match.top_scores[0].home_goals} × ${match.top_scores[0].away_goals} (${pct(match.top_scores[0].probability)})${(() => {
            const goals = active.draftScore && active.draftScore.match_id === match.match_id ? active.draftScore.value : value;
            if (!goals || goals[0] === null || goals[1] === null || !match.score_probabilities || !match.score_probabilities[goals[0]]) return "";
            return ` · o seu, ${goals[0]} × ${goals[1]}: ${pct(match.score_probabilities[goals[0]][goals[1]] || 0)}`;
          })()}</p>` : "";
      const primary = mode === "placar"
        ? (locked ? "" : `<button type="button" class="sim-button" id="sim-confirm-score">${active.cursor === deck.length - 1 ? "Revisar →" : "Próximo jogo →"}</button>`)
        : `<button type="button" class="sim-button" id="sim-forward">${active.cursor === deck.length - 1 ? "Revisar →" : "Próximo jogo →"}</button>`;
      shell("", MODES[mode].label, "", `${sessionHeader(active)}
        <div class="sim-deck-progress"><div class="sim-progress" role="img" aria-label="${tally.own} seus, ${tally.sampled} sorteados, ${tally.blank} em branco"><span class="is-own" style="width:${tally.own / deck.length * 100}%"></span><span class="is-model" style="width:${tally.sampled / deck.length * 100}%"></span></div>
          <span class="sim-deck-count">${filled} de ${deck.length}</span></div>
        <p class="sim-mini-label">${tally.own} seus · ${tally.sampled} do modelo · a probabilidade de tudo junto aparece na revisão, com todos os jogos preenchidos</p>
        <div class="sim-deck-grid">
          <div class="sim-deck-main">
            <p class="sim-section-title"><b>1</b>Seu palpite neste jogo</p>
            <article class="sim-card" aria-labelledby="sim-card-title">
              <p class="sim-card-meta"><span>Jogo ${active.cursor + 1} de ${deck.length} · ${match.round ? `R${match.round}` : "sem rodada"} · ${escapeHtml(formatShortDate(match.match_date))}${kickoffClock(match) ? ` ${kickoffClock(match)}` : ""}</span><span>${lockText}</span></p>
              <h2 class="visually-hidden" id="sim-card-title">${escapeHtml(nameOf(match.home_id))} × ${escapeHtml(nameOf(match.away_id))}</h2>
              ${locked ? `<p class="sim-card-lock">Este jogo fechou ${LOCK_MARGIN_MINUTES} minutos antes do início: não dá mais para mudar o palpite${cloud && cloudState.user ? ", e ele não conta para o ranking" : ""}.</p>` : ""}
              ${crowdForMatch(match)}
              ${controls}
              ${mode === "placar" ? modelPills(match) : ""}
              ${scoreLine}
              <div class="sim-card-state">${state}</div>
              <div class="sim-card-actions">
                ${canSample && !locked ? `<button type="button" class="sim-button is-secondary" id="sim-roll">Sortear</button>` : ""}
                ${primary}
              </div>
              <p class="sim-card-links"><button type="button" class="link-button" id="sim-prev" ${active.cursor === 0 ? "disabled" : ""}>← Anterior</button>${locked ? "" : ` · <button type="button" class="link-button" id="sim-skip">${value === undefined ? "Pular" : "Deixar em branco"}</button>`}</p>
            </article>
            <p class="sim-cheer" aria-live="polite">${message}</p>
          </div>
          <div class="sim-deck-side">
            <p class="sim-section-title"><b>2</b>${match.round ? `Jogos da rodada ${match.round}` : "Jogos sem rodada"} · ${mode === "vencedor" ? "toque no resultado de cada jogo" : "toque para palpitar"}</p>
            ${originLegend()}
            ${dayList(mode, entry, active.cursor)}
            ${canSample ? `<p class="sim-map-actions"><button type="button" class="sim-button is-secondary" id="sim-fill-rest">Sortear o resto${tally.blank ? ` (${tally.blank})` : ""}</button> <button type="button" class="link-button" id="sim-clear-model">Tirar os sorteados</button></p>` : ""}
          </div>
        </div>
        ${navBar("Mudar o jeito de jogar", "Revisar →", "")}`, { focus: true });
      bindSession(active, () => moveStep(active, 1), () => { if (entry.model) fillWithModel(mode, entry, false); moveStep(active, 3); });
      const goTo = (index, nextCheer) => { active.cursor = index; active.draftScore = null; writeStore(); renderDeck(active, nextCheer); const card = main.querySelector(".sim-card"); if (card) card.scrollIntoView({ block: "nearest" }); };
      const advance = (nextCheer) => {
        if (active.cursor < deck.length - 1) setTimeout(() => goTo(active.cursor + 1, nextCheer), 220);
        else { writeStore(); renderDeck(active, nextCheer || "Último jogo! Revise a tabela quando quiser."); }
      };
      document.getElementById("sim-prev").addEventListener("click", () => goTo(active.cursor - 1));
      const forward = document.getElementById("sim-forward");
      if (forward) forward.addEventListener("click", () => {
        if (active.cursor === deck.length - 1) { if (entry.model) fillWithModel(mode, entry, false); moveStep(active, 3); }
        else goTo(active.cursor + 1);
      });
      const skip = document.getElementById("sim-skip");
      if (skip) skip.addEventListener("click", () => {
        delete entry.picks[match.match_id];
        delete entry.sampled[match.match_id];
        goTo(Math.min(deck.length - 1, active.cursor + 1), "Pulado. Dá para voltar depois pela lista de jogos.");
      });
      const roll = document.getElementById("sim-roll");
      if (roll) roll.addEventListener("click", () => {
        delete entry.picks[match.match_id];
        entry.sampled[match.match_id] = sampleMatch(mode, match);
        active.draftScore = null;
        writeStore();
        const drawn = entry.sampled[match.match_id];
        renderDeck(active, mode === "vencedor" ? `O modelo sorteou: ${escapeHtml(drawn === "D" ? "empate" : `vitória do ${outcomeName(match, drawn)}`)}.` : `O modelo sorteou ${drawn[0]} × ${drawn[1]}.`);
      });
      main.querySelectorAll("[data-jump]").forEach((button) => button.addEventListener("click", () => goTo(Number(button.dataset.jump))));
      const fillRest = document.getElementById("sim-fill-rest");
      if (fillRest) fillRest.addEventListener("click", () => { entry.model = true; fillWithModel(mode, entry, false); writeStore(); renderDeck(active, "O modelo sorteou os jogos em branco. Eles aparecem tracejados."); });
      const clearModel = document.getElementById("sim-clear-model");
      if (clearModel) clearModel.addEventListener("click", () => { entry.model = false; entry.sampled = {}; writeStore(); renderDeck(active, "Sorteados removidos. Ficaram só os seus palpites."); });
      main.querySelectorAll("[data-row-pick]").forEach((button) => button.addEventListener("click", () => {
        const target = matchById.get(button.dataset.match);
        if (!target) return;
        entry.picks[target.match_id] = button.dataset.rowPick;
        delete entry.sampled[target.match_id];
        writeStore();
        renderDeck(active, cheerFor(target, button.dataset.rowPick));
        const again = main.querySelector(`[data-row-pick="${button.dataset.rowPick}"][data-match="${CSS.escape(target.match_id)}"]`);
        if (again) again.focus();
      }));
      main.querySelectorAll("[data-pick]").forEach((button) => button.addEventListener("click", () => {
        entry.picks[match.match_id] = button.dataset.pick;
        delete entry.sampled[match.match_id];
        main.querySelectorAll(".sim-outcome").forEach((item) => item.classList.toggle("is-chosen", item === button));
        advance(cheerFor(match, button.dataset.pick));
      }));
      if (locked) main.querySelectorAll("[data-goal]").forEach((button) => { button.disabled = true; });
      main.querySelectorAll("[data-goal]").forEach((button) => button.addEventListener("click", () => {
        const current = active.draftScore && active.draftScore.match_id === match.match_id ? [...active.draftScore.value] : value !== undefined ? [...value] : [null, null];
        const side = Number(button.dataset.goal);
        current[side] = Math.max(0, Math.min(MAX_GOALS_INPUT, (current[side] === null ? 0 : current[side]) + Number(button.dataset.delta)));
        if (current[1 - side] === null) current[1 - side] = 0;
        active.draftScore = { match_id: match.match_id, value: current };
        renderDeck(active, " ");
        const again = main.querySelector(`[data-goal="${side}"][data-delta="${button.dataset.delta}"]`);
        if (again) again.focus();
      }));
      main.querySelectorAll("[data-score]").forEach((button) => button.addEventListener("click", () => {
        const [home, away] = button.dataset.score.split("-").map(Number);
        entry.picks[match.match_id] = [home, away];
        delete entry.sampled[match.match_id];
        active.draftScore = null;
        advance(cheerFor(match, outcomeOf(home, away)));
      }));
      const confirm = document.getElementById("sim-confirm-score");
      if (confirm) confirm.addEventListener("click", () => {
        const goals = active.draftScore && active.draftScore.match_id === match.match_id ? active.draftScore.value : value;
        const filledScore = goals && goals[0] !== null && goals[1] !== null;
        const last = active.cursor === deck.length - 1;
        if (!filledScore && !last) { goTo(active.cursor + 1); return; }
        if (filledScore) {
          entry.picks[match.match_id] = [goals[0], goals[1]];
          delete entry.sampled[match.match_id];
        }
        active.draftScore = null;
        if (last) { writeStore(); if (entry.model) fillWithModel(mode, entry, false); moveStep(active, 3); return; }
        advance(cheerFor(match, outcomeOf(goals[0], goals[1])));
      });
    }

    function finalTableHtml(mode, entry) {
      const table = finalTable(mode, entry);
      const body = table.map((row) => {
        const zone = zoneOf(row.position, table.length);
        const sign = goalDifference(row) > 0 ? "+" : goalDifference(row) < 0 ? MINUS : "";
        return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${row.position}</td><td>${clubCell(row.club_id)}${row.tie ? ` <span class="sim-tie" title="Empate em todos os critérios que dá para calcular; o regulamento decide por cartões e, depois, sorteio">empate: ${row.tie}</span>` : ""}</td>
          <td class="num">${row.points}</td><td class="num">${row.played}</td><td class="num">${row.wins}</td><td class="num">${sign}${Math.abs(goalDifference(row))}</td></tr>`;
      }).join("");
      return `<div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Clube</th><th class="num">Pts</th><th class="num">J</th><th class="num">V</th><th class="num">SG</th></tr></thead><tbody>${body}</tbody></table></div>`;
    }

    function picksHighlights(mode, entry) {
      const table = finalTable(mode, entry);
      const ownPicks = Object.entries(entry.picks || {}).map(([matchId, pick]) => {
        const match = matchById.get(matchId);
        if (!match || isFinished(match)) return null;
        const outcome = mode === "vencedor" ? pick : outcomeOf(pick[0], pick[1]);
        return { match, outcome, probability: outcomeProbability(match, outcome) };
      }).filter(Boolean);
      const boldest = ownPicks.sort((left, right) => left.probability - right.probability)[0];
      const bold = ownPicks.filter((item) => item.probability < 0.25).length;
      const relegated = table.slice(table.length - RELEGATED).map((row) => row.club_id);
      return highlightCards([
        { label: "Seu campeão", value: clubCell(table[0].club_id, 24), note: `${table[0].points} pontos · modelo: ${pct(teamById[table[0].club_id].title)}` },
        { label: "Seus rebaixados", value: relegated.map((clubId) => crest(clubId, 24)).join(""), note: relegated.map((clubId) => escapeHtml(teamById[clubId].short_name || nameOf(clubId))).join(" · ") },
        { label: "Sua maior zebra", value: boldest ? escapeHtml(`${teamById[boldest.match.home_id].short_name} × ${teamById[boldest.match.away_id].short_name}`) : "–", note: boldest ? `${escapeHtml(boldest.outcome === "D" ? "empate" : `vitória do ${outcomeName(boldest.match, boldest.outcome)}`)} · ${pct(boldest.probability)} no modelo` : "nenhum palpite seu ainda" },
        { label: "Palpites ousados", value: `${bold}`, note: "seus, com menos de 25% no modelo" },
      ]);
    }

    /* Como cada jogo foi decidido, em palavras que o visitante entende (versão 6, D-049). */
    function originLegend() {
      return `<p class="sim-legend" aria-label="Legenda">
        <span><i class="sim-key is-own"></i>Seu palpite: você escolheu</span>
        <span><i class="sim-key is-model"></i>Sorteado pelo modelo: ele escolheu com as probabilidades dele; você pode trocar</span>
        <span><i class="sim-key is-blank"></i>Em branco: fica fora da conta</span></p>`;
    }

    const originOf = (entry, matchId) => (entry.picks[matchId] !== undefined ? "own" : entry.sampled[matchId] !== undefined ? "model" : "blank");
    const ORIGIN_TEXT = { own: "seu palpite", model: "sorteado pelo modelo", blank: "em branco, fora da conta" };

    function pickText(mode, match, pick) {
      if (pick === undefined) return "–";
      if (mode === "vencedor") return pick === "D" ? "empate" : `vitória do ${escapeHtml(shortName(pick === "H" ? match.home_id : match.away_id))}`;
      return `${pick[0]} × ${pick[1]}`;
    }

    /* Lista jogo a jogo, na ordem da rodada, com a origem de cada palpite (aparece na revisão). */
    function decisionsTable(mode, entry) {
      const ordered = [...remaining].sort((left, right) => (left.round || 99) - (right.round || 99) || left.match_date.localeCompare(right.match_date));
      const rows = ordered.map((match) => {
        const origin = originOf(entry, match.match_id);
        const pick = effectivePicks(entry)[match.match_id];
        return `<tr class="sim-origin-${origin}"><td class="num">${match.round || "–"}</td><td>${shortName(match.home_id)} × ${shortName(match.away_id)}</td><td>${pickText(mode, match, pick)}</td><td><span class="sim-origin-tag is-${origin}">${ORIGIN_TEXT[origin]}</span></td></tr>`;
      }).join("");
      return `<details class="sim-decisions" open><summary>Jogo a jogo: quem decidiu cada palpite (${ordered.length})</summary>
        <div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">Rod.</th><th>Jogo</th><th>Palpite</th><th>Quem decidiu</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
    }

    /* O que a simulação tem de mais ousado (D-049): quantas vezes seguiu o favorito do modelo e os palpites contra ele,
       do mais arriscado ao menos arriscado. Aparece na revisão e na simulação salva. */
    function decidedPicks(mode, entry) {
      return Object.entries(effectivePicks(entry)).map(([matchId, pick]) => {
        const match = matchById.get(matchId);
        if (!match || isFinished(match)) return null;
        const outcome = mode === "vencedor" ? pick : outcomeOf(pick[0], pick[1]);
        const favorite = ["H", "D", "A"].reduce((best, key) => (outcomeProbability(match, key) > outcomeProbability(match, best) ? key : best), "H");
        return { match, outcome, probability: outcomeProbability(match, outcome), followsFavorite: favorite === outcome, origin: originOf(entry, matchId), score: mode === "placar" ? pick : null };
      }).filter(Boolean);
    }

    function insightsBlock(mode, entry) {
      if (mode === "classificacao") return "";
      const picks = decidedPicks(mode, entry);
      if (!picks.length) return "";
      const followed = picks.filter((item) => item.followsFavorite).length;
      const risky = picks.filter((item) => !item.followsFavorite).sort((left, right) => left.probability - right.probability).slice(0, 5);
      const pickWord = (item) => (item.score ? `${item.score[0]} × ${item.score[1]}` : item.outcome === "D" ? "empate" : `vitória do ${shortName(item.outcome === "H" ? item.match.home_id : item.match.away_id)}`);
      const rows = risky.map((item) => `<li><span>${shortName(item.match.home_id)} × ${shortName(item.match.away_id)}</span><strong>${pickWord(item)}</strong><em>${pct(item.probability)} no modelo · ${ORIGIN_TEXT[item.origin]}</em></li>`).join("");
      return `<section class="sim-insights" aria-labelledby="sim-insights-title">
        <h2 id="sim-insights-title">O que a sua simulação tem de mais ousado</h2>
        <p class="note">Você seguiu o favorito do modelo em <strong>${followed}</strong> de ${picks.length} jogos. ${risky.length ? `Os palpites contra o favorito, do mais arriscado ao menos arriscado:` : "Nenhum palpite foi contra o favorito."}</p>
        ${risky.length ? `<ol class="sim-zebras">${rows}</ol>` : ""}
      </section>`;
    }

    function reviewSummary(mode, entry, tally) {
      const parts = [`<strong>${tally.own}</strong> seus`, `<strong>${tally.sampled}</strong> sorteados pelo modelo`, `<strong>${tally.blank}</strong> em branco`];
      const note = tally.blank
        ? `Os jogos em branco ficam fora da tabela e da pontuação. Os sorteados pelo modelo contam como os seus.`
        : `Tudo decidido. Toque em Salvar simulação: ela ganha um número, a pontuação e aparece em Minhas simulações. Os sorteados pelo modelo contam como os seus.`;
      return `<div class="sim-review-summary" role="status"><p>${parts.join(" · ")}</p><p class="note">${note}</p></div>`;
    }

    function renderReview(active) {
      const mode = active.mode;
      const entry = active.entry;
      const tally = counts(entry);
      const score = pickScore(mode, entry);
      const complete = isComplete(entry);
      const blocked = tally.own + tally.sampled ? "" : "Nenhum jogo preenchido. Volte aos cartões ou deixe o modelo sortear.";
      const warning = tally.blank ? `<p class="sim-banner">${tally.blank} ${tally.blank === 1 ? "jogo está em branco e fica" : "jogos estão em branco e ficam"} fora da tabela final e da pontuação. <button type="button" class="link-button" id="sim-fill-blank">Deixar o modelo sortear ${tally.blank === 1 ? "esse jogo" : "esses jogos"}</button></p>` : "";
      const asTable = complete ? (() => {
        const tableEval = tableScore(finalTable(mode, entry).map((row) => row.club_id));
        return ` Como Classificação, esta tabela faria ${tableEval.points} pontos hoje (até ${tableEval.ceiling} de ${tableEval.maximum}).`;
      })() : "";
      const goalsNote = mode === "vencedor" ? `<p class="note">No modo Vencedor não há placar, então o saldo de gols da tabela é só o dos jogos já disputados.</p>` : "";
      shell("", "Revise e salve", `Vale até ${score.total} pontos (${perMatchText(mode)}).${asTable}`, `${sessionHeader(active)}
        <p class="sim-section-title"><b>3</b>Revisão</p>
        ${warning}${complete ? jointSlot("sim-joint") : ""}
        <section class="sim-review-card"><h2>Como termina a sua tabela</h2>${goalsNote}${finalTableHtml(mode, entry)}</section>
        ${insightsBlock(mode, entry)}${picksHighlights(mode, entry)}${reviewSummary(mode, entry, tally)}
        ${decisionsTable(mode, entry).replace("<details class=\"sim-decisions\" open>", "<details class=\"sim-decisions\">")}
        ${navBar("Voltar aos jogos", active.savedId ? "Salvar alterações" : "Salvar simulação", blocked)}`, { focus: true });
      bindSession(active, () => moveStep(active, 2), () => saveActive());
      if (complete) fillJoint("sim-joint", finalOrderOf(mode, entry), false);
      const fillBlank = document.getElementById("sim-fill-blank");
      if (fillBlank) fillBlank.addEventListener("click", () => { entry.model = true; fillWithModel(mode, entry, false); writeStore(); rerender(); });
    }

    /* ---------------- Simulação salva */

    function renderSaved(localId) {
      const item = store.saved.find((saved) => saved.local_id === localId);
      if (!item) { renderHome("Essa simulação não está neste aparelho."); return; }
      const done = store.done && store.done.local_id === localId ? store.done : null;
      if (done) { store.done = null; writeStore(); }
      const mode = item.mode;
      const table = mode === "classificacao"
        ? `<div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Clube</th><th>Vaga</th></tr></thead><tbody>${item.entry.order.map((clubId, index) => {
          const zone = zoneOf(index + 1, item.entry.order.length);
          return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${index + 1}</td><td>${clubCell(clubId)}</td><td>${zone.label}</td></tr>`;
        }).join("")}</tbody></table></div>`
        : finalTableHtml(mode, item.entry);
      const busy = store.active && (store.active.savedId !== localId);
      const savedOrder = finalOrderOf(mode, item.entry);
      shell("", `${MODES[mode].label} ${escapeHtml(simulationLabel(item))}`, "", `
        <p class="sim-back"><a href="#/simular/minhas">← Minhas simulações</a></p>
        ${done ? `<div class="sim-celebrate" role="status"><p class="sim-celebrate-title">${escapeHtml(done.cheer || savedCheers[0])}</p>
          <p><strong>Pronto: a simulação ${escapeHtml(simulationLabel(item))} foi salva.</strong> Ela está em "Minhas simulações", com a pontuação dela.${escapeHtml(done.note)}</p>
          <p class="sim-celebrate-next"><a class="sim-button" href="#/simular">Fazer outra simulação</a> <a class="sim-button is-secondary" href="#/simular/minhas">Ver minhas simulações</a></p></div>` : ""}
        <div class="sim-scorebox"><p>${scoreSummary(item)}</p><p class="note">Salva em ${escapeHtml(formatDay(item.updated_at))}${item.server_id ? " · no servidor" : " · só neste aparelho"}.</p></div>
        ${insightsBlock(mode, item.entry)}
        <p class="sim-toolbar">${isClosed(item) ? `<span class="sim-locked">Fechada: um jogo começou depois que ela foi salva. Ela fica como está; para mudar algo, faça outra.</span>`
          : busy ? `<span class="sim-locked">Há outra simulação em andamento: termine ou descarte antes de editar esta.</span>` : `<button type="button" class="sim-button" id="sim-edit">Editar</button>`}
          <a class="sim-button is-secondary" href="#/simular">Fazer outra simulação</a>
          <a class="sim-button is-secondary" href="#/simular/minhas">Minhas simulações</a>
          <button type="button" class="link-button" id="sim-share">Copiar link</button>
          <button type="button" class="link-button" id="sim-remove">Excluir</button>
          <span class="note" id="sim-save-status" aria-live="polite"></span></p>
        ${savedOrder ? jointSlot("sim-joint") : ""}
        <h2>${mode === "classificacao" ? "Sua ordem" : "Sua tabela final"}</h2>${table}`);
      if (savedOrder) fillJoint("sim-joint", savedOrder, mode === "classificacao");
      const edit = document.getElementById("sim-edit");
      if (edit) edit.addEventListener("click", () => {
        if (!store.active || store.active.savedId !== localId) startSession(mode, item, null);
        go("#/simular/fazer");
      });
      document.getElementById("sim-share").addEventListener("click", async () => {
        const url = `${location.href.split("#")[0]}#/simular/${mode}/l/${encodeLink(mode, item.entry, matchIndex, sortedClubs)}`;
        const status = document.getElementById("sim-save-status");
        try { await navigator.clipboard.writeText(url); status.textContent = "Link copiado."; }
        catch (error) {
          status.innerHTML = `Copie o link: <input class="sim-share-url" readonly value="${escapeHtml(url)}" aria-label="Link da simulação">`;
          const input = status.querySelector("input"); input.focus(); input.select();
        }
      });
      document.getElementById("sim-remove").addEventListener("click", async () => {
        if (!window.confirm(`Excluir a simulação ${simulationLabel(item)}?${item.server_id ? " Ela sai também do servidor e do ranking." : ""}`)) return;
        if (item.server_id && cloud && cloudState.user) {
          try { await cloud.deleteSimulation(item.server_id); } catch (error) { document.getElementById("sim-save-status").textContent = `Não deu para excluir no servidor (${error.message}).`; return; }
        }
        store.saved = store.saved.filter((saved) => saved !== item);
        store.removed = [...(store.removed || []), item.local_id];
        if (store.active && store.active.savedId === localId) store.active = null;
        writeStore();
        go("#/simular");
      });
    }

    /* ---------------- Ranking (Kanban #43 · 3B) */

    async function renderRanking(requested) {
      const rankMode = MODES[requested] ? requested : "placar";
      const subTabs = `<nav class="chip-row sim-subchips" aria-label="Ranking por modo">${Object.entries(MODES).map(([key, item]) =>
        `<a class="chip chip-sm" href="#/simular/ranking/${key}" ${key === rankMode ? 'aria-current="page"' : ""}>${item.label}</a>`).join("")}</nav>`;
      shell("ranking", "Simulador", "",
        `${subTabs}<div id="sim-ranking" aria-live="polite"><div class="skeleton-page"><span class="skeleton sk-row"></span><span class="skeleton sk-row"></span><span class="skeleton sk-row"></span></div></div>`);
      const target = document.getElementById("sim-ranking");
      try {
        const rows = await cloud.ranking(season, rankMode);
        if (!document.body.contains(target)) return;
        if (!rows.length) {
          target.innerHTML = `<div class="state"><p class="state-title">Ninguém pontuou ainda em ${MODES[rankMode].label}</p><p class="state-text">Os pontos entram assim que os jogos com palpite terminam${rankMode === "classificacao" ? " e, na Classificação, no fim da temporada" : ""}.</p><a class="btn-primary btn-sm state-action" href="#/simular">Fazer simulação</a></div>`;
          return;
        }
        const mine = new Set(store.saved.map((item) => item.server_id).filter(Boolean));
        const exactLabel = rankMode === "placar" ? "Exatos" : rankMode === "vencedor" ? "Acertos" : "Exatas";
        const formatPts = (row) => (rankMode === "classificacao" ? `${deflated(row.points)} / ${deflated(row.max_points)}` : `${row.points} / ${row.max_points}`);
        const podium = rows.length >= 3 ? `<div class="sim-highlights-3" aria-label="Pódio">${rows.slice(0, 3).map((row, idx) => `
          <article class="sim-podium-card${idx === 0 ? " is-first" : ""}">
            <span class="sim-podium-kicker">${row.rank}º lugar</span>
            <strong class="sim-podium-name">${escapeHtml(row.nickname)} <small>#${row.simulation_id}</small></strong>
            <span class="sim-podium-pts"><strong>${rankMode === "classificacao" ? deflated(row.points) : row.points}</strong> <small>/ ${rankMode === "classificacao" ? deflated(row.max_points) : row.max_points} pts · ${row.exact_hits} ${exactLabel.toLowerCase()}</small></span>
          </article>`).join("")}</div>` : "";
        const bestMine = rows.find((row) => mine.has(row.simulation_id));
        const myStrip = bestMine
          ? `<div class="sim-my-rank"><span>Sua melhor posição: <strong>#${bestMine.rank}</strong> · ${escapeHtml(bestMine.nickname)} (#${bestMine.simulation_id})</span><strong>${formatPts(bestMine)} pts</strong></div>`
          : !cloudState.user
            ? `<div class="sim-my-rank"><span>Entre no ranking com um apelido para aparecer aqui.</span><button type="button" class="btn-primary btn-sm" id="sim-rank-join">Participar</button></div>`
            : "";
        target.innerHTML = `${podium}${myStrip}
          <div class="table-card table-scroll"><table class="sim-table sim-vtable"><thead><tr><th class="num">#</th><th>Apelido</th><th class="num">Pontos</th><th class="num">${exactLabel}</th><th class="num">${rankMode === "classificacao" ? "Faltavam" : "Jogos"}</th></tr></thead>
          <tbody>${rows.map((row) => `<tr${mine.has(row.simulation_id) ? ' class="selected-team"' : ""}><td class="num sim-rank-pos${row.rank <= 3 ? " is-top" : ""}">${row.rank}º</td><td><strong>${escapeHtml(row.nickname)}</strong> <span class="sim-row-id">#${row.simulation_id}</span></td><td class="num"><strong>${rankMode === "classificacao" ? deflated(row.points) : row.points}</strong> <span class="sim-row-id">/ ${rankMode === "classificacao" ? deflated(row.max_points) : row.max_points}</span></td><td class="num">${row.exact_hits}</td><td class="num">${row.scored_picks}</td></tr>`).join("")}</tbody></table></div>`;
        const joinBtn = document.getElementById("sim-rank-join");
        if (joinBtn) joinBtn.addEventListener("click", openAccountSheet);
      } catch (error) {
        if (document.body.contains(target)) target.innerHTML = `<div class="state" role="alert"><p class="state-title">Ranking indisponível agora</p><p class="state-text">${escapeHtml(error.message)}</p></div>`;
      }
    }

    /* ---------------- Agregado (Kanban #43 · 3B): posição média + onde a torcida discorda do modelo */

    function aggregate(tables) {
      const totals = Object.fromEntries(clubIds.map((clubId) => [clubId, { sum: 0, champion: 0, relegated: 0 }]));
      tables.forEach((order) => order.forEach((clubId, index) => {
        if (!totals[clubId]) return;
        totals[clubId].sum += index + 1;
        if (index === 0) totals[clubId].champion += 1;
        if (index >= order.length - RELEGATED) totals[clubId].relegated += 1;
      }));
      return clubIds.map((clubId) => ({
        club_id: clubId,
        average_position: totals[clubId].sum / tables.length,
        champion: totals[clubId].champion / tables.length,
        relegated: totals[clubId].relegated / tables.length,
      })).sort((left, right) => left.average_position - right.average_position || left.club_id.localeCompare(right.club_id));
    }

    function divergenceCards(rows, official) {
      const diffs = rows.map((club, index) => ({
        club_id: club.club_id,
        crowd: index + 1,
        model: official[club.club_id] || index + 1,
        diff: (official[club.club_id] || index + 1) - (index + 1),
      })).filter((item) => item.diff !== 0);
      if (!diffs.length) return "";
      const optimistic = [...diffs].filter((d) => d.diff > 0).sort((a, b) => b.diff - a.diff);
      const pessimistic = [...diffs].filter((d) => d.diff < 0).sort((a, b) => a.diff - b.diff);
      const chosen = [...optimistic.slice(0, 2), ...pessimistic.slice(0, 1)];
      if (chosen.length < 3) {
        for (const extra of [...optimistic.slice(2), ...pessimistic.slice(1)]) {
          if (chosen.length >= 3) break;
          chosen.push(extra);
        }
      }
      return `<div class="sim-highlights-3" aria-label="Onde a torcida mais discorda do modelo">${chosen.map((item) => {
        const up = item.diff > 0;
        const sign = up ? `+${item.diff}` : `${MINUS}${Math.abs(item.diff)}`;
        return `<article class="sim-podium-card">
          <span class="sim-podium-kicker ${up ? "is-up" : "is-dn"}">${up ? "Torcida mais otimista" : "Torcida mais pessimista"}</span>
          <strong class="sim-podium-club">${clubCell(item.club_id, 22)}</strong>
          <span class="sim-podium-sub">${item.crowd}º na torcida vs. ${item.model}º modelo (${sign})</span>
        </article>`;
      }).join("")}</div>`;
    }

    function aggregateTable(rows, note, showDivergence) {
      const official = Object.fromEntries([...snapshot.teams].sort((left, right) => left.expected_position - right.expected_position).map((team, index) => [team.club_id, index + 1]));
      const cards = showDivergence ? divergenceCards(rows, official) : "";
      return `<p class="sim-agg-note">${note}</p>${cards}
        <div class="table-card table-scroll"><table class="sim-table sim-vtable"><thead><tr><th class="num">#</th><th>Clube</th><th class="num" title="Posição média">Pos. média</th><th class="num">Título</th><th class="num" title="Rebaixado">Z4</th><th class="num" title="Diferença entre a torcida e o modelo oficial">vs. Modelo</th></tr></thead>
        <tbody>${rows.map((club, index) => {
          const rank = index + 1;
          const zone = zoneOf(rank, rows.length);
          const modelRank = official[club.club_id] || rank;
          const diff = modelRank - rank;
          const deltaBadge = diff > 0
            ? `<span class="sim-delta-pill is-up" title="Modelo: ${modelRank}º">+${diff}</span>`
            : diff < 0
              ? `<span class="sim-delta-pill is-dn" title="Modelo: ${modelRank}º">${MINUS}${Math.abs(diff)}</span>`
              : `<span class="sim-delta-pill is-eq" title="Igual ao modelo">=</span>`;
          return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${rank}º</td><td>${clubCell(club.club_id)}</td>
            <td class="num">${Number(club.average_position).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td><td class="num">${pct(club.champion)}</td><td class="num">${pct(club.relegated)}</td><td class="num">${deltaBadge}</td></tr>`;
        }).join("")}</tbody></table></div>`;
    }

    async function renderAggregate(scope) {
      const scopeName = scope === "minhas" ? "minhas" : "todas";
      const subTabs = `<nav class="chip-row sim-subchips" aria-label="Escopo do agregado">${cloud ? `<a class="chip chip-sm" href="#/simular/agregado" ${scopeName === "todas" ? 'aria-current="page"' : ""}>Visitantes</a>` : ""}<a class="chip chip-sm" href="#/simular/agregado/minhas" ${scopeName === "minhas" || !cloud ? 'aria-current="page"' : ""}>As minhas</a></nav>`;
      shell("agregado", "Simulador", "",
        `${subTabs}<div id="sim-aggregate" aria-live="polite"><div class="skeleton-page"><span class="skeleton sk-row"></span><span class="skeleton sk-row"></span><span class="skeleton sk-row"></span></div></div>`);
      const target = document.getElementById("sim-aggregate");
      if (scopeName === "minhas" || !cloud) {
        const tables = store.saved.map((item) => finalOrderOf(item.mode, item.entry)).filter((order) => Array.isArray(order) && order.length === clubIds.length);
        target.innerHTML = tables.length
          ? aggregateTable(aggregate(tables), `Média das suas ${tables.length} ${tables.length === 1 ? "simulação completa" : "simulações completas"} neste aparelho.`, false)
          : `<div class="state"><p class="state-title">Sem simulação completa ainda</p><p class="state-text">Salve uma Classificação, ou um Vencedor / Placar exato com todos os jogos preenchidos (o modelo pode completar).</p><a class="btn-primary btn-sm state-action" href="#/simular">Criar simulação</a></div>`;
        return;
      }
      try {
        const data = await cloud.consensus(season);
        if (!document.body.contains(target)) return;
        if (!data.clubs || !data.clubs.length) {
          target.innerHTML = `<div class="state"><p class="state-title">Consenso ainda em formação</p><p class="state-text">A média dos visitantes aparece com pelo menos ${data.min_users} participantes, para proteger a escolha individual. Enquanto isso, veja a média das suas simulações.</p><a class="btn-secondary btn-sm state-action" href="#/simular/agregado/minhas">Ver as minhas ›</a></div>`;
          return;
        }
        const approx = data.approximate ? " · aproximado" : "";
        target.innerHTML = aggregateTable(data.clubs, `Consenso de pelo menos ${data.users_at_least} participantes${approx} · cada pessoa pesa igual.`, true);
      } catch (error) {
        if (document.body.contains(target)) target.innerHTML = `<div class="state" role="alert"><p class="state-title">Consenso indisponível agora</p><p class="state-text">${escapeHtml(error.message)}</p></div>`;
      }
    }

    /* ---------------- Rotas: #/simular, /fazer, /ver/{id}, /{modo}[/l/{código}], /ranking/{modo}, /agregado[/minhas] */

    function openMode(mode, code) {
      let entry = null;
      let notice = "";
      if (code) {
        const decoded = decodeLink(mode, code, sortedClubs, matchList);
        if (decoded) entry = sanitize(mode, decoded.entry);
        else notice = "Não deu para abrir a simulação do link: ele está incompleto ou é de outra temporada.";
      }
      if (store.active && (store.active.mode !== mode || entry)) {
        if (entry) { store.pendingLink = { mode, code }; writeStore(); }
        renderHome(`${notice ? `${notice} ` : ""}Você tem uma simulação de ${MODES[store.active.mode].label} em andamento. Termine ou descarte antes de começar ${entry ? "a do link (ela fica guardada aqui até lá)" : `uma de ${MODES[mode].label}`}.`);
        history.replaceState(null, "", "#/simular");
        return;
      }
      if (!store.active) startSession(mode, null, entry);
      history.replaceState(null, "", "#/simular/fazer");
      renderSession();
    }

    if (first === "fazer") renderSession();
    else if (first === "ver") renderSaved(decodeURIComponent(second));
    else if (first === "minhas") {
      renderHome();
      const section = document.getElementById("sim-minhas");
      if (section) section.scrollIntoView({ block: "start" });
    }
    else if (first === "ranking" && cloud) renderRanking(second);
    else if (first === "agregado" || first === "visitantes") renderAggregate(second);
    else if (MODES[first]) {
      if (second === "s") go(`#/simular/ver/${third}`);
      else openMode(first, second === "l" ? third : second);
    } else renderHome();
    initCloud();
  }

  /* Motor reaproveitado pelo modo Ao vivo (live-round.js): sorteio do placar, tabela e desempate do Art. 15. */
  window.Simulator = { render, engine: { scoreSampler, draw, outcomeOf, newRows, addResult, rankRows, zoneOf, compareMain, matchPoints } };
})();
