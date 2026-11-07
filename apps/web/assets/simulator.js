/* Simulador do usuário (ADR-0015, fase 1): o visitante monta o próprio fim de campeonato.
   Modos: Classificação (ordena a tabela final), Vencedor (vitória, empate ou derrota em cada jogo) e Placar exato
   (placar de cada jogo). Com "Completar com o modelo", os jogos sem palpite são sorteados com a matriz de placares
   que o modelo publica no snapshot (`score_probabilities`): o navegador só sorteia, não refaz o modelo.
   Fica no aparelho (localStorage) e pode ser compartilhado por link. Com simulator-config.js preenchido (fase 2),
   quem escolher "Participar" também salva no Supabase (simulator-cloud.js), vê a média dos visitantes e pode entrar
   no ranking com um apelido. */
(function () {
  "use strict";

  const MODES = {
    classificacao: { label: "Classificação", hint: "Ordene a tabela final como você acha que ela vai terminar." },
    vencedor: { label: "Vencedor", hint: "Escolha vitória do mandante, empate ou vitória do visitante em cada jogo." },
    placar: { label: "Placar exato", hint: "Dê o placar de cada jogo. A tabela sai com os critérios de desempate do regulamento." },
  };
  const OUTCOMES = { H: "home", D: "draw", A: "away" };
  // serie_a_2026.toml: Art. 6º (5 vagas de Libertadores pela liga), 7º (6 de Sul-Americana) e 8º (4 rebaixados).
  const LIBERTADORES_GROUPS = 4;
  const LIBERTADORES_SLOTS = 5;
  const SUDAMERICANA_SLOTS = 6;
  const RELEGATED = 4;
  const ASSIST_SIMULATIONS = 5000;
  const ASSIST_SEED = 2026;
  const MAX_GOALS_INPUT = 20;
  const CODE_VERSION = "1";
  const MINUS = "−";
  const RANKING_MODES = {
    placar: { label: "Placar exato", exact: "Placares exatos", rules: "5 pontos pelo placar exato, 3 pelo vencedor (ou empate) com o saldo de gols certo e 2 só pelo vencedor (ou empate)." },
    vencedor: { label: "Vencedor", exact: "Acertos", rules: "1 ponto por resultado certo: vitória do mandante, empate ou vitória do visitante." },
    classificacao: { label: "Classificação", exact: "Posições exatas", rules: "No fim da temporada: 3 pontos por clube na posição exata e 1 por clube a uma posição da certa. Vale a última ordem salva antes da trava da temporada, que fica no início do campeonato." },
  };
  // Mesma regra do banco (sim_profiles.nickname): letras com acento do português, números e _ . - espaço.
  const NICKNAME = /^[A-Za-zÀ-ÖØ-öø-ÿ0-9_. -]{3,20}$/;
  const cloudState = { checked: false, user: null, profile: null, community: null, status: "", open: "" };
  const cloudTimers = {};
  const cloudApi = () => (window.SimulatorCloud && window.SimulatorCloud.enabled ? window.SimulatorCloud : null);

  // fromLink: o modo aberto por link (ou false); ownEntry guarda a simulação do próprio usuário nesse modo.
  const view = { mode: "classificacao", fromLink: false, ownEntry: null, linkNote: "", data: null, baseline: null };

  function storageKey(season) { return `ainda-da:simulador:serie-a:${season}`; }

  function readSaved(season) {
    try {
      const raw = window.localStorage.getItem(storageKey(season));
      const saved = raw ? JSON.parse(raw) : null;
      return saved && saved.version === 1 ? saved : null;
    } catch (error) { return null; }
  }

  function writeSaved(season, data) {
    try {
      window.localStorage.setItem(storageKey(season), JSON.stringify({ version: 1, saved_at: new Date().toISOString(), ...data }));
      return true;
    } catch (error) { return false; }
  }

  function emptyData(snapshot) {
    const order = [...snapshot.teams].sort((left, right) => left.expected_position - right.expected_position).map((team) => team.club_id);
    return { classificacao: { order }, vencedor: { picks: {}, assist: true }, placar: { picks: {}, assist: true } };
  }

  function mulberry32(seed) {
    let value = seed >>> 0;
    return function () {
      value = (value + 0x6d2b79f5) >>> 0;
      let mixed = value;
      mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
      mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
      return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
    };
  }

  const outcomeOf = (home, away) => (home > away ? "H" : home < away ? "A" : "D");

  /* Distribuições acumuladas da matriz de placares: uma para o jogo todo e uma por resultado (H, D, A). */
  function scoreSampler(match) {
    const matrix = match.score_probabilities;
    if (!Array.isArray(matrix) || !matrix.length) return null;
    const build = (accept) => {
      const cells = [];
      let total = 0;
      matrix.forEach((row, home) => row.forEach((probability, away) => {
        if (probability > 0 && accept(home, away)) { total += probability; cells.push([total, home, away]); }
      }));
      return total > 0 ? { cells, total } : null;
    };
    return {
      all: build(() => true),
      H: build((home, away) => home > away),
      D: build((home, away) => home === away),
      A: build((home, away) => home < away),
    };
  }

  function draw(distribution, random) {
    const target = random() * distribution.total;
    const cells = distribution.cells;
    let low = 0;
    let high = cells.length - 1;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (cells[middle][0] < target) low = middle + 1; else high = middle;
    }
    return cells[low];
  }

  function newRows(clubIds) {
    const rows = {};
    clubIds.forEach((clubId) => { rows[clubId] = { club_id: clubId, played: 0, points: 0, wins: 0, draws: 0, losses: 0, goals_for: 0, goals_against: 0 }; });
    return rows;
  }

  function addResult(rows, homeId, awayId, outcome, homeGoals, awayGoals) {
    const home = rows[homeId];
    const away = rows[awayId];
    home.played += 1; away.played += 1;
    if (outcome === "H") { home.points += 3; home.wins += 1; away.losses += 1; }
    else if (outcome === "A") { away.points += 3; away.wins += 1; home.losses += 1; }
    else { home.points += 1; away.points += 1; home.draws += 1; away.draws += 1; }
    if (homeGoals !== null) {
      home.goals_for += homeGoals; home.goals_against += awayGoals;
      away.goals_for += awayGoals; away.goals_against += homeGoals;
    }
  }

  const goalDifference = (row) => row.goals_for - row.goals_against;
  const compareMain = (left, right) => right.points - left.points || right.wins - left.wins
    || goalDifference(right) - goalDifference(left) || right.goals_for - left.goals_for;

  /* Art. 15: pontos, vitórias, saldo, gols marcados e confronto direto só entre dois clubes
     (pontos e depois saldo nos jogos entre eles). Cartões e sorteio não dá para saber: o empate fica marcado. */
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
        if (edge !== 0) {
          ranked.push(...(edge > 0 ? [first, second] : [second, first]).map((row) => ({ ...row, tie: null })));
        } else {
          ranked.push(...group.map((row) => ({ ...row, tie: "cartões ou sorteio" })));
        }
      } else if (group.length > 2) {
        ranked.push(...group.map((row) => ({ ...row, tie: "cartões ou sorteio" })));
      } else {
        ranked.push({ ...group[0], tie: null });
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

  function encodeLink(mode, data, matchIndex) {
    if (mode === "classificacao") {
      const clubs = [...data.classificacao.order].sort();
      return CODE_VERSION + data.classificacao.order.map((clubId) => clubs.indexOf(clubId).toString(36)).join("");
    }
    const entry = data[mode];
    const picks = Object.entries(entry.picks).filter(([matchId]) => matchIndex.has(matchId))
      .map(([matchId, pick]) => matchIndex.get(matchId).toString(36).padStart(2, "0")
        + (mode === "vencedor" ? pick : pick[0].toString(36) + pick[1].toString(36)));
    return CODE_VERSION + (entry.assist ? "a" : "m") + picks.join("");
  }

  function decodeLink(mode, code, snapshot, matchList) {
    if (!code || code[0] !== CODE_VERSION) return null;
    const body = code.slice(1);
    if (mode === "classificacao") {
      const clubs = snapshot.teams.map((team) => team.club_id).sort();
      const order = [...body].map((char) => clubs[parseInt(char, 36)]);
      const valid = order.length === clubs.length && new Set(order).size === clubs.length && order.every(Boolean);
      return valid ? { order, ignored: 0 } : null;
    }
    const assist = body[0] === "a";
    const step = mode === "vencedor" ? 3 : 4;
    const picks = {};
    let ignored = 0;
    for (let start = 1; start + step <= body.length; start += step) {
      const match = matchList[parseInt(body.slice(start, start + 2), 36)];
      if (!match) return null;
      if (match.status === "finished") { ignored += 1; continue; }
      if (mode === "vencedor") {
        if (!OUTCOMES[body[start + 2]]) return null;
        picks[match.match_id] = body[start + 2];
      } else {
        const home = parseInt(body[start + 2], 36);
        const away = parseInt(body[start + 3], 36);
        if (Number.isNaN(home) || Number.isNaN(away)) return null;
        picks[match.match_id] = [home, away];
      }
    }
    return { picks, assist, ignored };
  }

  function render(main, segments, context) {
    const { snapshot, escapeHtml, pct, crest, nameOf, formatShortDate } = context;
    const season = snapshot.season;
    const matchList = [...snapshot.matches].sort((left, right) => left.match_id.localeCompare(right.match_id));
    const matchIndex = new Map(matchList.map((match, index) => [match.match_id, index]));
    const finished = snapshot.matches.filter((match) => match.status === "finished" && Number.isInteger(match.home_goals) && Number.isInteger(match.away_goals));
    const remaining = snapshot.matches.filter((match) => match.status !== "finished");
    const remainingIds = new Set(remaining.map((match) => match.match_id));
    const teamById = Object.fromEntries(snapshot.teams.map((team) => [team.club_id, team]));
    const clubIds = snapshot.teams.map((team) => team.club_id);
    const samplers = new Map(remaining.map((match) => [match.match_id, scoreSampler(match)]));
    const canAssist = remaining.every((match) => samplers.get(match.match_id));
    const remainingByClub = Object.fromEntries(clubIds.map((clubId) => [clubId, 0]));
    remaining.forEach((match) => { remainingByClub[match.home_id] += 1; remainingByClub[match.away_id] += 1; });
    const currentPoints = Object.fromEntries(snapshot.standings.map((row) => [row.club_id, row.points]));
    const maxPoints = Object.fromEntries(clubIds.map((clubId) => [clubId, currentPoints[clubId] + 3 * remainingByClub[clubId]]));

    const cloud = cloudApi();
    const [modeSegment = "", code = ""] = segments;
    const isRanking = Boolean(cloud) && modeSegment === "ranking";
    const mode = MODES[modeSegment] ? modeSegment : view.mode;
    view.mode = mode;
    if (!view.data || view.data.season !== season) {
      const saved = readSaved(season);
      view.data = { season, ...emptyData(snapshot), ...(saved ? { classificacao: saved.classificacao, vencedor: saved.vencedor, placar: saved.placar } : {}) };
      const validOrder = Array.isArray(view.data.classificacao.order) && view.data.classificacao.order.length === clubIds.length && clubIds.every((clubId) => view.data.classificacao.order.includes(clubId));
      if (!validOrder) view.data.classificacao = emptyData(snapshot).classificacao;
      ["vencedor", "placar"].forEach((key) => {
        view.data[key].picks = Object.fromEntries(Object.entries(view.data[key].picks || {}).filter(([matchId]) => remainingIds.has(matchId)));
      });
      view.fromLink = false;
    }
    if (code && !isRanking) {
      const decoded = decodeLink(mode, code, snapshot, matchList);
      if (decoded) {
        if (view.fromLink && view.fromLink !== mode) view.data[view.fromLink] = view.ownEntry;
        if (view.fromLink !== mode) view.ownEntry = view.data[mode];
        if (mode === "classificacao") view.data.classificacao = { order: decoded.order };
        else view.data[mode] = { picks: decoded.picks, assist: decoded.assist && canAssist };
        view.fromLink = mode;
        view.linkNote = decoded.ignored ? ` ${decoded.ignored} ${decoded.ignored === 1 ? "palpite era de um jogo que já aconteceu e ficou" : "palpites eram de jogos que já aconteceram e ficaram"} de fora.` : "";
      } else {
        main.dataset.simLinkError = "1";
      }
      history.replaceState(null, "", `#/simular/${mode}`);
    }

    const save = () => {
      const own = { classificacao: view.data.classificacao, vencedor: view.data.vencedor, placar: view.data.placar };
      if (view.fromLink) own[view.fromLink] = view.ownEntry;
      writeSaved(season, own);
      if (cloud && cloudState.user && view.fromLink !== mode) scheduleCloudSave(mode);
    };

    /* ---------- Servidor (fase 2) ---------- */

    const clock = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const onSimulator = () => location.hash.replace(/^#\/?/, "").startsWith("simular");
    const rerender = () => { if (onSimulator()) render(main, isRanking ? ["ranking", segments[1] || ""] : [mode], context); };

    function setStatus(text) {
      cloudState.status = text;
      const target = document.getElementById("sim-cloud-status");
      if (target) target.textContent = text;
    }

    function scheduleCloudSave(modeKey) {
      window.clearTimeout(cloudTimers[modeKey]);
      cloudTimers[modeKey] = window.setTimeout(async () => {
        try {
          const stored = await cloud.saveSimulation(season, modeKey, view.data[modeKey]);
          setStatus(`Salvo no servidor às ${clock()}.${rankingNote(modeKey, stored)}`);
        } catch (error) {
          setStatus(`Não deu para salvar no servidor (${error.message}); continua salvo neste aparelho.`);
        }
      }, 800);
    }

    /* Lê o que o servidor de fato guardou: palpites de jogos travados não contam para o ranking. */
    function rankingNote(modeKey, stored) {
      if (!stored) return "";
      if (modeKey === "classificacao") return stored.ranked_order ? "" : " Esta ordem não conta para o ranking: a trava da temporada já passou.";
      const sent = Object.keys(view.data[modeKey].picks || {});
      const kept = new Set(Object.keys(stored.picks || {}));
      const dropped = sent.filter((matchId) => !kept.has(matchId)).length;
      if (!dropped) return "";
      return dropped === 1 ? " 1 palpite é de jogo já travado e não conta para o ranking." : ` ${dropped} palpites são de jogos já travados e não contam para o ranking.`;
    }

    /* Mesma trava do servidor (supabase_sync.match_lock_utc): o pontapé ou, sem ele, 00:00 de Brasília do dia. */
    function lockTime(match) {
      if (match.kickoff_utc) return new Date(match.kickoff_utc);
      return new Date(`${match.match_date}T00:00:00-03:00`);
    }

    function lockLabel(match) {
      if (!cloud || !cloudState.user) return "";
      const lock = lockTime(match);
      if (Number.isNaN(lock.getTime())) return "";
      if (lock <= new Date()) return " · não conta mais para o ranking";
      const when = lock.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
      return ` · vale para o ranking até ${when}`;
    }

    function acceptStored(stored) {
      Object.entries(stored).forEach(([key, entry]) => {
        if (key === "classificacao") {
          const valid = Array.isArray(entry.order) && entry.order.length === clubIds.length && clubIds.every((clubId) => entry.order.includes(clubId));
          if (!valid) return;
        } else {
          entry.picks = Object.fromEntries(Object.entries(entry.picks || {}).filter(([matchId]) => remainingIds.has(matchId)));
          entry.assist = Boolean(entry.assist) && canAssist;
        }
        if (view.fromLink === key) view.ownEntry = entry; else view.data[key] = entry;
      });
    }

    async function initCloud() {
      if (!cloud || cloudState.checked) return;
      cloudState.checked = true;
      try {
        cloudState.user = await cloud.currentUser();
        if (cloudState.user) {
          cloudState.profile = await cloud.profile();
          acceptStored(await cloud.loadSimulations(season));
          const own = { classificacao: view.data.classificacao, vencedor: view.data.vencedor, placar: view.data.placar };
          if (view.fromLink) own[view.fromLink] = view.ownEntry;
          writeSaved(season, own);
        }
      } catch (error) {
        cloudState.status = `Servidor indisponível agora (${error.message}). A simulação continua salva neste aparelho.`;
      }
      try { cloudState.community = await cloud.community(season); } catch (error) { cloudState.community = null; }
      rerender();
    }

    async function uploadAll() {
      for (const key of Object.keys(MODES)) {
        const entry = view.fromLink === key ? view.ownEntry : view.data[key];
        if (entry) await cloud.saveSimulation(season, key, entry);
      }
    }

    function accountPanel() {
      if (!cloud) return "";
      const status = `<span class="note" id="sim-cloud-status" aria-live="polite">${escapeHtml(cloudState.status)}</span>`;
      if (!cloudState.checked) return `<div class="sim-account">${status}</div>`;
      const user = cloudState.user;
      if (!user) {
        const login = cloudState.open === "login" ? `<form class="sim-form" id="sim-login-form">
            <label>E-mail ligado à sua participação <input type="email" required autocomplete="email" id="sim-login-email"></label>
            <button type="submit">Enviar link de entrada</button></form>` : "";
        return `<div class="sim-account"><p><strong>Compare com os outros visitantes.</strong> Participe para salvar sua simulação no servidor, ver o que os outros visitantes acham e, se quiser, entrar no ranking com um apelido. Não precisa de cadastro.</p>
          <p><button type="button" class="sim-button" id="sim-join">Participar</button> <button type="button" class="link-button" id="sim-login-open">Já participo em outro aparelho</button></p>${login}${status}</div>`;
      }
      const profile = cloudState.profile || {};
      const who = profile.nickname ? `como <strong>${escapeHtml(profile.nickname)}</strong>${profile.show_in_ranking ? " · no ranking" : " · fora do ranking"}` : "sem apelido · fora do ranking";
      const profileForm = cloudState.open === "profile" ? `<form class="sim-form" id="sim-profile-form">
          <label>Apelido <input type="text" id="sim-nickname" maxlength="20" minlength="3" value="${escapeHtml(profile.nickname || "")}" autocomplete="nickname"></label>
          <label class="sim-check"><input type="checkbox" id="sim-in-ranking" ${profile.show_in_ranking ? "checked" : ""}> Aparecer no ranking com este apelido</label>
          <p class="note">De 3 a 20 letras, números, espaço, ponto, hífen ou _. Não use seu e-mail nem seu nome completo: o apelido é a única coisa que os outros veem.</p>
          <button type="submit">Salvar</button></form>` : "";
      const emailForm = cloudState.open === "email" ? `<form class="sim-form" id="sim-email-form">
          <label>Seu e-mail <input type="email" required autocomplete="email" id="sim-email"></label>
          <p class="note">Serve só para você entrar em outro aparelho. Não aparece para ninguém, nem no ranking.</p>
          <button type="submit">Enviar link de confirmação</button></form>` : "";
      const emailAction = user.hasEmail ? "e-mail ligado" : `<button type="button" class="link-button" id="sim-email-open">Usar em outro aparelho</button>`;
      return `<div class="sim-account"><p>Participando ${who}. <button type="button" class="link-button" id="sim-profile-open">Apelido e ranking</button> · ${emailAction} · <button type="button" class="link-button" id="sim-signout">Sair</button> · <button type="button" class="link-button" id="sim-delete">Apagar minha participação</button></p>${profileForm}${emailForm}${status}</div>`;
    }

    function bindAccount() {
      if (!cloud) return;
      const on = (id, event, handler) => { const element = document.getElementById(id); if (element) element.addEventListener(event, handler); };
      const toggle = (panel) => () => { cloudState.open = cloudState.open === panel ? "" : panel; rerender(); };
      on("sim-login-open", "click", toggle("login"));
      on("sim-profile-open", "click", toggle("profile"));
      on("sim-email-open", "click", toggle("email"));
      on("sim-join", "click", async () => {
        setStatus("Entrando…");
        try {
          cloudState.user = await cloud.join();
          cloudState.profile = await cloud.profile();
          await uploadAll();
          cloudState.open = "profile";
          cloudState.status = `Participando. Simulação salva no servidor às ${clock()}.`;
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
      on("sim-delete", "click", async () => {
        if (!window.confirm("Apagar sua participação? Saem do servidor o apelido, o e-mail ligado e as simulações salvas lá, sem volta. A simulação continua neste aparelho.")) return;
        try {
          await cloud.deleteAccount();
          cloudState.user = null; cloudState.profile = null; cloudState.open = ""; cloudState.status = "Participação apagada do servidor.";
          rerender();
        } catch (error) { setStatus(`Não deu para apagar agora (${error.message}).`); }
      });
      on("sim-signout", "click", async () => {
        const warning = cloudState.user && !cloudState.user.hasEmail
          ? "Sua participação não tem e-mail ligado: ao sair, você não consegue voltar a ela. Sair mesmo assim?"
          : "Sair da participação neste aparelho? A simulação continua salva aqui.";
        if (!window.confirm(warning)) return;
        try { await cloud.signOut(); } catch (error) { /* sai localmente mesmo assim */ }
        cloudState.user = null; cloudState.profile = null; cloudState.open = ""; cloudState.status = "Você saiu.";
        rerender();
      });
    }

    function crowdForMatch(match) {
      const data = cloudState.community && cloudState.community.matches ? cloudState.community.matches[match.match_id] : null;
      if (!data) return "";
      return `<span class="sim-crowd" title="Pelo menos ${data.users_at_least} visitantes com palpite neste jogo; números arredondados de 5 em 5 pontos">visitantes: ${pct(data.H)} · ${pct(data.D)} · ${pct(data.A)}</span>`;
    }

    function crowdForClub(clubId) {
      const data = cloudState.community && cloudState.community.clubs ? cloudState.community.clubs[clubId] : null;
      if (!data) return "";
      return ` <span class="sim-crowd" title="Posição média nas tabelas de pelo menos ${data.users_at_least} visitantes, arredondada a meia posição">· visitantes ${Number(data.average_position).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}º</span>`;
    }

    const signed = (value) => {
      const points = Math.round(value * 100);
      if (points === 0) return "0";
      return (points > 0 ? "+" : MINUS) + Math.abs(points);
    };
    const clubCell = (clubId, size = 18) => `<span class="club-cell">${crest(clubId, size)}<span>${escapeHtml(nameOf(clubId))}</span></span>`;
    const shortName = (clubId) => escapeHtml((teamById[clubId] || {}).short_name || nameOf(clubId));

    function tabs() {
      const ranking = cloud ? `<a href="#/simular/ranking" ${isRanking ? 'aria-current="page"' : ""}>Ranking</a>` : "";
      return `<nav class="tabs sim-tabs" aria-label="Modo do simulador">${Object.entries(MODES).map(([key, item]) =>
        `<a href="#/simular/${key}" ${key === mode && !isRanking ? 'aria-current="page"' : ""}>${item.label}</a>`).join("")}${ranking}</nav>`;
    }

    function linkBanner() {
      if (main.dataset.simLinkError) {
        delete main.dataset.simLinkError;
        return `<p class="sim-banner" role="status">Não deu para abrir a simulação do link: ele está incompleto ou é de outra temporada. Abrimos a sua.</p>`;
      }
      if (view.fromLink !== mode) return "";
      return `<p class="sim-banner" role="status">Você está vendo uma simulação aberta por link.${escapeHtml(view.linkNote)} Ela não substitui a sua até você salvar.
        <button type="button" class="link-button" id="sim-keep">Salvar como minha</button> · <button type="button" class="link-button" id="sim-discard">Voltar à minha</button></p>`;
    }

    function storageNote() {
      if (!cloud) return "Sua simulação fica salva só neste aparelho, sem conta e sem envio para servidor.";
      return "Sua simulação fica salva neste aparelho. Ao abrir o simulador, o navegador baixa a biblioteca do Supabase pelo jsDelivr e consulta a média dos visitantes no servidor do AInda dá? (Supabase, nos Estados Unidos). Se você participar, a simulação também vai para lá, ligada a uma conta sem nome; o e-mail é opcional e nunca aparece para ninguém. No ranking e na média dos visitantes só entram o apelido e números somados e arredondados.";
    }

    function shell(controls, body, lede) {
      main.innerHTML = `
        <span class="kicker">Simulador</span>
        <h1>E se o campeonato terminar do seu jeito?</h1>
        <p class="lede">${lede || `${MODES[mode].hint} O modelo fica ao lado, para comparar.`}</p>
        ${tabs()}
        ${isRanking ? "" : linkBanner()}
        ${controls === null ? "" : `<div class="sim-toolbar">${controls}<button type="button" class="link-button" id="sim-share">Copiar link desta simulação</button><span class="note" id="sim-share-status" aria-live="polite"></span></div>`}
        ${accountPanel()}
        ${body}
        <p class="note sim-footnote">${storageNote()} Vagas pela liga em 2026: 1º a 4º na fase de grupos da Libertadores, 5º na fase preliminar, 6º a 11º na Sul-Americana, 17º a 20º rebaixados (regulamento, Art. 6º a 8º). Títulos da Copa do Brasil, da Libertadores e da Sul-Americana podem empurrar essas vagas para baixo; isso o simulador não calcula.</p>`;
      bindCommon();
      bindAccount();
    }

    function bindCommon() {
      const share = document.getElementById("sim-share");
      if (share) share.addEventListener("click", async () => {
        const url = `${location.href.split("#")[0]}#/simular/${mode}/${encodeLink(mode, view.data, matchIndex)}`;
        const status = document.getElementById("sim-share-status");
        try {
          await navigator.clipboard.writeText(url);
          status.textContent = "Link copiado.";
        } catch (error) {
          status.innerHTML = `Copie o link: <input class="sim-share-url" readonly value="${escapeHtml(url)}" aria-label="Link da simulação">`;
          const input = status.querySelector("input");
          input.focus(); input.select();
        }
      });
      const keep = document.getElementById("sim-keep");
      if (keep) keep.addEventListener("click", () => { view.fromLink = false; view.ownEntry = null; save(); render(main, [mode], context); });
      const discard = document.getElementById("sim-discard");
      if (discard) discard.addEventListener("click", () => { view.data[mode] = view.ownEntry; view.fromLink = false; view.ownEntry = null; render(main, [mode], context); });
    }

    /* ---------- Classificação ---------- */

    function impossiblePairs(order) {
      const problems = new Map();
      order.forEach((upper, upperIndex) => {
        order.slice(upperIndex + 1).forEach((lower) => {
          if (maxPoints[upper] < currentPoints[lower] && !problems.has(upper)) problems.set(upper, lower);
        });
      });
      return problems;
    }

    function renderQuick(focusClub, focusDirection) {
      const order = view.data.classificacao.order;
      const problems = impossiblePairs(order);
      const total = order.length;
      const rows = order.map((clubId, index) => {
        const position = index + 1;
        const zone = zoneOf(position, total);
        const team = teamById[clubId];
        const chance = team.position_probabilities[index];
        const problem = problems.get(clubId);
        return `<li class="sim-quick-row ${zone.key ? `zone-${zone.key}` : ""}" draggable="true" data-club="${escapeHtml(clubId)}">
          <span class="sim-pos">${position}º</span>
          ${clubCell(clubId, 22)}
          <span class="sim-zone">${zone.label}</span>
          <span class="sim-model" title="Probabilidade do modelo de terminar exatamente nesta posição">modelo ${pct(chance)}${crowdForClub(clubId)}</span>
          <span class="sim-move">
            <button type="button" data-move="-1" aria-label="Subir ${escapeHtml(nameOf(clubId))}" ${index === 0 ? "disabled" : ""}>▲</button>
            <button type="button" data-move="1" aria-label="Descer ${escapeHtml(nameOf(clubId))}" ${index === total - 1 ? "disabled" : ""}>▼</button>
          </span>
          ${problem ? `<span class="sim-warning">Impossível: chega a no máximo ${maxPoints[clubId]} pontos e ${escapeHtml(nameOf(problem))} já tem ${currentPoints[problem]}.</span>` : ""}
        </li>`;
      }).join("");
      const champion = order[0];
      const relegated = order.slice(total - RELEGATED);
      const summary = `<div class="sim-summary">
        <p><strong>Seu campeão:</strong> ${clubCell(champion)} <span class="note">(modelo: ${pct(teamById[champion].title)} de probabilidade)</span></p>
        <p><strong>Seus rebaixados:</strong> ${relegated.map((clubId) => `${clubCell(clubId)} <span class="note">${pct(teamById[clubId].relegation)}</span>`).join(" · ")}</p>
        ${problems.size ? `<p class="sim-warning">${problems.size === 1 ? "Uma posição é impossível" : `${problems.size} posições são impossíveis`} pela matemática: veja os avisos na lista.</p>` : ""}
      </div>`;
      const controls = `<button type="button" class="link-button" id="sim-reset-model">Começar da ordem do modelo</button> · <button type="button" class="link-button" id="sim-reset-table">Começar da tabela atual</button> · `;
      shell(controls, `${summary}<ol class="sim-quick" aria-label="Sua tabela final">${rows}</ol>
        <p class="note">"modelo" é a probabilidade, nas simulações do modelo, de o clube terminar exatamente naquela posição. Arraste as linhas ou use as setas.</p>`);
      bindQuick();
      if (focusClub) {
        const button = main.querySelector(`.sim-quick-row[data-club="${CSS.escape(focusClub)}"] button[data-move="${focusDirection}"]`)
          || main.querySelector(`.sim-quick-row[data-club="${CSS.escape(focusClub)}"] button:not([disabled])`);
        if (button) button.focus();
      }
    }

    function moveClub(clubId, target) {
      const order = view.data.classificacao.order.filter((item) => item !== clubId);
      order.splice(Math.max(0, Math.min(order.length, target)), 0, clubId);
      view.data.classificacao.order = order;
      save();
    }

    function bindQuick() {
      main.querySelectorAll(".sim-quick-row button[data-move]").forEach((button) => button.addEventListener("click", () => {
        const clubId = button.closest(".sim-quick-row").dataset.club;
        const direction = Number(button.dataset.move);
        moveClub(clubId, view.data.classificacao.order.indexOf(clubId) + direction);
        renderQuick(clubId, button.dataset.move);
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
          moveClub(dragged, view.data.classificacao.order.indexOf(row.dataset.club));
          renderQuick();
        });
      });
      document.getElementById("sim-reset-model").addEventListener("click", () => { view.data.classificacao = emptyData(snapshot).classificacao; save(); renderQuick(); });
      document.getElementById("sim-reset-table").addEventListener("click", () => {
        view.data.classificacao = { order: [...snapshot.standings].sort((left, right) => left.position - right.position).map((row) => row.club_id) };
        save(); renderQuick();
      });
    }

    /* ---------- Vencedor e Placar exato ---------- */

    function pickResult(match) {
      const pick = view.data[mode].picks[match.match_id];
      if (pick === undefined) return null;
      if (mode === "vencedor") return { outcome: pick, homeGoals: null, awayGoals: null };
      return { outcome: outcomeOf(pick[0], pick[1]), homeGoals: pick[0], awayGoals: pick[1] };
    }

    function playedResults() {
      return finished.map((match) => ({ home: match.home_id, away: match.away_id, outcome: outcomeOf(match.home_goals, match.away_goals), homeGoals: match.home_goals, awayGoals: match.away_goals }));
    }

    function deterministicTable() {
      const results = playedResults();
      remaining.forEach((match) => {
        const pick = pickResult(match);
        if (pick) results.push({ home: match.home_id, away: match.away_id, ...pick });
      });
      const rows = newRows(clubIds);
      results.forEach((result) => addResult(rows, result.home, result.away, result.outcome, result.homeGoals, result.awayGoals));
      return rankRows(rows, results);
    }

    /* Monte Carlo do "Completar com o modelo": jogos com palpite ficam fixos (no Vencedor, só o vencedor fica fixo e o
       placar é sorteado dentro dele); os outros são sorteados da matriz do modelo. Depois de gols marcados,
       o desempate é sorteado, como os cartões e o sorteio do regulamento, que não dá para prever. */
    function assistedSimulation(withPicks) {
      const random = mulberry32(ASSIST_SEED);
      const base = newRows(clubIds);
      playedResults().forEach((result) => addResult(base, result.home, result.away, result.outcome, result.homeGoals, result.awayGoals));
      const plan = remaining.map((match) => {
        const pick = withPicks ? pickResult(match) : null;
        const sampler = samplers.get(match.match_id);
        if (pick && pick.homeGoals !== null) return { match, fixed: pick };
        return { match, distribution: pick ? sampler[pick.outcome] || sampler.all : sampler.all };
      });
      const index = Object.fromEntries(clubIds.map((clubId, position) => [clubId, position]));
      const count = clubIds.length;
      const positions = clubIds.map(() => new Float64Array(count));
      const points = new Float64Array(count);
      const stats = new Int32Array(count * 4);
      for (let simulation = 0; simulation < ASSIST_SIMULATIONS; simulation += 1) {
        clubIds.forEach((clubId, position) => {
          const row = base[clubId];
          stats[position * 4] = row.points; stats[position * 4 + 1] = row.wins;
          stats[position * 4 + 2] = row.goals_for - row.goals_against; stats[position * 4 + 3] = row.goals_for;
        });
        for (const step of plan) {
          let homeGoals;
          let awayGoals;
          if (step.fixed) { homeGoals = step.fixed.homeGoals; awayGoals = step.fixed.awayGoals; }
          else { const cell = draw(step.distribution, random); homeGoals = cell[1]; awayGoals = cell[2]; }
          const home = index[step.match.home_id] * 4;
          const away = index[step.match.away_id] * 4;
          if (homeGoals > awayGoals) { stats[home] += 3; stats[home + 1] += 1; }
          else if (homeGoals < awayGoals) { stats[away] += 3; stats[away + 1] += 1; }
          else { stats[home] += 1; stats[away] += 1; }
          stats[home + 2] += homeGoals - awayGoals; stats[away + 2] += awayGoals - homeGoals;
          stats[home + 3] += homeGoals; stats[away + 3] += awayGoals;
        }
        const lot = clubIds.map(() => random());
        const order = clubIds.map((_, position) => position).sort((left, right) =>
          stats[right * 4] - stats[left * 4] || stats[right * 4 + 1] - stats[left * 4 + 1]
          || stats[right * 4 + 2] - stats[left * 4 + 2] || stats[right * 4 + 3] - stats[left * 4 + 3] || lot[left] - lot[right]);
        order.forEach((club, rank) => { positions[club][rank] += 1; points[club] += stats[club * 4]; });
      }
      return clubIds.map((clubId, position) => {
        const distribution = Array.from(positions[position], (value) => value / ASSIST_SIMULATIONS);
        const expected = distribution.reduce((sum, probability, rank) => sum + probability * (rank + 1), 0);
        return {
          club_id: clubId,
          expected_position: expected,
          expected_points: points[position] / ASSIST_SIMULATIONS,
          title: distribution[0],
          top4: distribution.slice(0, LIBERTADORES_GROUPS).reduce((sum, value) => sum + value, 0),
          relegation: distribution.slice(count - RELEGATED).reduce((sum, value) => sum + value, 0),
        };
      }).sort((left, right) => left.expected_position - right.expected_position);
    }

    function baselineGap() {
      if (!view.baseline || view.baseline.generated_at !== snapshot.generated_at) {
        const rows = assistedSimulation(false);
        const gap = Math.max(...rows.flatMap((row) => ["title", "top4", "relegation"].map((key) => Math.abs(row[key] - teamById[row.club_id][key]))));
        view.baseline = { generated_at: snapshot.generated_at, gap };
      }
      return view.baseline.gap;
    }

    function pickedCount() { return Object.keys(view.data[mode].picks).length; }

    function resultPanel() {
      const entry = view.data[mode];
      const missing = remaining.length - pickedCount();
      if (entry.assist && canAssist) {
        const rows = assistedSimulation(true);
        const gap = baselineGap();
        const body = rows.map((row, index) => {
          const zone = zoneOf(index + 1, rows.length);
          const official = teamById[row.club_id];
          const cell = (key) => `<td class="num">${pct(row[key])}<span class="sim-delta" title="diferença para o modelo oficial, em pontos percentuais">${signed(row[key] - official[key])}</span></td>`;
          return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${index + 1}</td><td>${clubCell(row.club_id)}</td>
            <td class="num">${row.expected_points.toFixed(1).replace(".", ",")}</td>${cell("title")}${cell("top4")}${cell("relegation")}</tr>`;
        }).join("");
        return `<h2>Sua simulação, com o modelo completando</h2>
          <p class="note">${pickedCount()} ${pickedCount() === 1 ? "jogo com palpite seu" : "jogos com palpite seu"}; ${missing === 1 ? "o outro foi sorteado" : `os outros ${missing} foram sorteados`} ${ASSIST_SIMULATIONS.toLocaleString("pt-BR")} vezes com as probabilidades do modelo. Ao lado de cada número, a diferença para o modelo oficial, em pontos percentuais.</p>
          <div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Clube</th><th class="num">Pts</th><th class="num">Título</th><th class="num">G4</th><th class="num">Queda</th></tr></thead><tbody>${body}</tbody></table></div>
          <p class="note">Cálculo simplificado, feito no seu navegador: a força dos clubes fica a da data de referência (no modelo oficial ela muda a cada jogo simulado) e, depois de gols marcados, o desempate é sorteado. Sem nenhum palpite, este cálculo fica a até ${(Math.round(gap * 1000) / 10).toLocaleString("pt-BR")} p.p. do oficial, somando a simplificação e o acaso do sorteio. Diferenças desse tamanho podem não vir dos seus palpites.</p>`;
      }
      const table = deterministicTable();
      const body = table.map((row) => {
        const zone = zoneOf(row.position, table.length);
        return `<tr class="${zone.key ? `zone-${zone.key}` : ""}"><td class="num">${row.position}</td><td>${clubCell(row.club_id)}${row.tie ? ` <span class="sim-tie" title="Empate em todos os critérios que dá para calcular; o regulamento decide por cartões e, depois, sorteio">empate: ${row.tie}</span>` : ""}</td>
          <td class="num">${row.points}</td><td class="num">${row.played}</td><td class="num">${row.wins}</td><td class="num">${goalDifference(row) > 0 ? "+" : goalDifference(row) < 0 ? MINUS : ""}${Math.abs(goalDifference(row))}</td></tr>`;
      }).join("");
      const missingNote = missing ? `Faltam palpites em ${missing} ${missing === 1 ? "jogo, que não entra" : "jogos, que não entram"} na tabela. Marque "Completar com o modelo" para o modelo simular esses jogos.` : "Todos os jogos têm palpite.";
      const goalsNote = mode === "vencedor" ? " No modo Vencedor não há placar, então o saldo de gols é só o dos jogos já disputados." : "";
      return `<h2>Sua tabela final</h2>
        <p class="note">${missingNote}${goalsNote}</p>
        <div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Clube</th><th class="num">Pts</th><th class="num">J</th><th class="num">V</th><th class="num">SG</th></tr></thead><tbody>${body}</tbody></table></div>`;
    }

    function matchControl(match) {
      const pick = view.data[mode].picks[match.match_id];
      const label = `${nameOf(match.home_id)} x ${nameOf(match.away_id)}`;
      if (mode === "vencedor") {
        const option = (key, text, probability) => `<label class="sim-choice ${pick === key ? "chosen" : ""}">
          <input type="radio" name="pick-${escapeHtml(match.match_id)}" value="${key}" ${pick === key ? "checked" : ""} data-match="${escapeHtml(match.match_id)}">
          <span>${text}</span><span class="sim-prob">${pct(probability)}</span></label>`;
        return `<fieldset class="sim-choices"><legend class="visually-hidden">${escapeHtml(label)}</legend>
          ${option("H", shortName(match.home_id), match.p_home)}${option("D", "Empate", match.p_draw)}${option("A", shortName(match.away_id), match.p_away)}
          ${pick ? `<button type="button" class="link-button sim-clear-one" data-match="${escapeHtml(match.match_id)}" aria-label="Apagar palpite de ${escapeHtml(label)}">apagar</button>` : ""}</fieldset>`;
      }
      const value = (side) => (pick ? pick[side] : "");
      const probability = pick ? (match.score_probabilities && match.score_probabilities[pick[0]] ? match.score_probabilities[pick[0]][pick[1]] : 0) : null;
      return `<span class="sim-score">
        <input type="number" inputmode="numeric" min="0" max="${MAX_GOALS_INPUT}" value="${value(0)}" data-match="${escapeHtml(match.match_id)}" data-side="0" aria-label="Gols de ${escapeHtml(nameOf(match.home_id))} contra ${escapeHtml(nameOf(match.away_id))}">
        <span aria-hidden="true">x</span>
        <input type="number" inputmode="numeric" min="0" max="${MAX_GOALS_INPUT}" value="${value(1)}" data-match="${escapeHtml(match.match_id)}" data-side="1" aria-label="Gols de ${escapeHtml(nameOf(match.away_id))} contra ${escapeHtml(nameOf(match.home_id))}">
        </span><span class="sim-prob" data-prob="${escapeHtml(match.match_id)}">${probability !== null ? `placar: ${pct(probability)}` : `modelo: ${escapeHtml(match.most_likely_score || "–")} é o mais provável`}</span>`;
    }

    function renderPicks() {
      const byRound = new Map();
      [...remaining].sort((left, right) => (left.round || 99) - (right.round || 99) || left.match_date.localeCompare(right.match_date))
        .forEach((match) => {
          const key = match.round || 0;
          if (!byRound.has(key)) byRound.set(key, []);
          byRound.get(key).push(match);
        });
      const rounds = [...byRound.entries()].map(([round, matches]) => `<section class="sim-round"><h3>${round ? `Rodada ${round}` : "Sem rodada"}</h3>
        ${matches.map((match) => `<div class="sim-match">
          <span class="sim-date">${escapeHtml(formatShortDate(match.match_date))}${match.match_date < snapshot.reference_date ? " · adiado" : ""}${lockLabel(match)}</span>
          <span class="sim-home">${clubCell(match.home_id)}</span>
          <span class="sim-pick">${matchControl(match)}${crowdForMatch(match)}</span>
          <span class="sim-away">${clubCell(match.away_id)}</span></div>`).join("")}</section>`).join("");
      const entry = view.data[mode];
      const assistToggle = canAssist
        ? `<label class="sim-assist"><input type="checkbox" id="sim-assist" ${entry.assist ? "checked" : ""}> Completar com o modelo <span class="note">(o modelo simula os jogos em que você não mexer)</span></label> · `
        : `<span class="note">"Completar com o modelo" precisa de um snapshot mais novo, com a matriz de placares. </span>`;
      const controls = `${assistToggle}<button type="button" class="link-button" id="sim-clear">Apagar palpites</button> · `;
      shell(controls, `<div class="sim-layout"><div class="sim-picks">${rounds || "<p>Não há jogos por disputar.</p>"}</div>
        <div class="sim-result" id="sim-result" aria-live="polite"></div></div>`);
      updateResult();
      bindPicks();
    }

    let pending = null;
    function updateResult() {
      const target = document.getElementById("sim-result");
      if (!target) return;
      if (pending) window.clearTimeout(pending);
      target.classList.add("sim-busy");
      pending = window.setTimeout(() => { target.innerHTML = resultPanel(); target.classList.remove("sim-busy"); pending = null; }, 30);
    }

    function bindPicks() {
      const entry = view.data[mode];
      const assist = document.getElementById("sim-assist");
      if (assist) assist.addEventListener("change", () => { entry.assist = assist.checked; save(); updateResult(); });
      document.getElementById("sim-clear").addEventListener("click", () => {
        if (pickedCount() && !window.confirm("Apagar todos os palpites deste modo?")) return;
        entry.picks = {}; save(); renderPicks();
      });
      main.querySelectorAll(".sim-choices input[type=radio]").forEach((input) => input.addEventListener("change", () => {
        entry.picks[input.dataset.match] = input.value;
        save();
        input.closest(".sim-choices").querySelectorAll(".sim-choice").forEach((choice) => choice.classList.toggle("chosen", choice.contains(input)));
        updateResult();
      }));
      main.querySelectorAll(".sim-clear-one").forEach((button) => button.addEventListener("click", () => {
        delete entry.picks[button.dataset.match]; save(); renderPicks();
      }));
      main.querySelectorAll(".sim-score input").forEach((input) => input.addEventListener("input", () => {
        const matchId = input.dataset.match;
        const inputs = main.querySelectorAll(`.sim-score input[data-match="${CSS.escape(matchId)}"]`);
        const values = Array.from(inputs, (field) => (field.value === "" ? null : Math.max(0, Math.min(MAX_GOALS_INPUT, Math.round(Number(field.value))))));
        const label = main.querySelector(`[data-prob="${CSS.escape(matchId)}"]`);
        const match = remaining.find((item) => item.match_id === matchId);
        if (values.every((value) => value !== null && !Number.isNaN(value))) {
          entry.picks[matchId] = values;
          const matrix = match.score_probabilities;
          const probability = matrix && matrix[values[0]] ? matrix[values[0]][values[1]] || 0 : 0;
          label.textContent = `placar: ${pct(probability)}`;
        } else {
          delete entry.picks[matchId];
          label.textContent = `modelo: ${match.most_likely_score || "–"} é o mais provável`;
        }
        save();
        updateResult();
      }));
    }

    /* ---------- Ranking ---------- */

    async function renderRanking(requested) {
      const rankMode = RANKING_MODES[requested] ? requested : "placar";
      const subTabs = `<nav class="tabs sim-subtabs" aria-label="Ranking por modo">${Object.entries(RANKING_MODES).map(([key, item]) =>
        `<a href="#/simular/ranking/${key}" ${key === rankMode ? 'aria-current="page"' : ""}>${item.label}</a>`).join("")}</nav>`;
      shell(null, `${subTabs}<p class="note">${RANKING_MODES[rankMode].rules} Só contam palpites salvos no servidor antes do início de cada jogo; jogos completados pelo modelo não contam. Aparece aqui só quem escolheu um apelido e marcou "Aparecer no ranking".</p>
        <div id="sim-ranking" aria-live="polite"><p class="note">Carregando o ranking…</p></div>`,
        "Quem mais acerta os jogos e a tabela entre os visitantes que participam. Cada modo tem o seu ranking.");
      const target = document.getElementById("sim-ranking");
      if (rankMode === "classificacao") {
        try {
          const info = await cloud.seasonInfo(season);
          if (info && new Date(info.classificacao_locks_at) <= new Date() && document.body.contains(target)) {
            const when = new Date(info.classificacao_locks_at).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
            target.insertAdjacentHTML("beforebegin", `<p class="sim-banner">Nesta temporada não há ranking da Classificação: a trava foi em ${when}, antes de o simulador existir. Ele começa na próxima temporada.</p>`);
          }
        } catch (error) { /* sem a trava, a página segue sem o aviso */ }
      }
      try {
        const [rows, mine] = await Promise.all([cloud.ranking(season, rankMode), cloudState.user ? cloud.myScores(season) : Promise.resolve([])]);
        const own = (mine || []).find((row) => row.mode === rankMode);
        const ownLine = cloudState.user
          ? `<p><strong>Você:</strong> ${own ? `${own.points} ${own.points === 1 ? "ponto" : "pontos"} em ${own.scored_picks} ${own.scored_picks === 1 ? "palpite contado" : "palpites contados"}` : "ainda sem pontos neste modo"}${cloudState.profile && cloudState.profile.show_in_ranking ? "" : " (fora do ranking público)"}.</p>`
          : "";
        const body = rows.length ? `<div class="table-wrap"><table class="sim-table"><thead><tr><th class="num">#</th><th>Apelido</th><th class="num">Pontos</th><th class="num">${RANKING_MODES[rankMode].exact}</th><th class="num">Palpites contados</th></tr></thead>
          <tbody>${rows.map((row) => `<tr${cloudState.profile && row.nickname === cloudState.profile.nickname ? ' class="selected-team"' : ""}><td class="num">${row.rank}</td><td>${escapeHtml(row.nickname)}</td><td class="num">${row.points}</td><td class="num">${row.exact_hits}</td><td class="num">${row.scored_picks}</td></tr>`).join("")}</tbody></table></div>`
          : `<p>Ninguém pontuou ainda neste modo. Os pontos aparecem depois que os jogos com palpite terminam${rankMode === "classificacao" ? " e, na Classificação, no fim da temporada" : ""}.</p>`;
        if (document.body.contains(target)) target.innerHTML = ownLine + body;
      } catch (error) {
        if (document.body.contains(target)) target.innerHTML = `<p class="note">Ranking indisponível agora (${escapeHtml(error.message)}).</p>`;
      }
    }

    if (isRanking) renderRanking(segments[1]);
    else if (mode === "classificacao") renderQuick();
    else renderPicks();
    initCloud();
  }

  window.Simulator = { render };
})();
