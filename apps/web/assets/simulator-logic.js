/* Lógica pura do simulador (ADR-0015): pontuação, tabela com o Art. 15, sorteio, links e mescla do armazenamento.
   Sem DOM, sem rede e sem estado: carrega como script (window.SimulatorLogic) e como módulo (require), para o
   `node --test` conferir os números contra a migração 0006 (sim_match_points, sim_pick_max, sim_scores). */
(function (root, factory) {
  "use strict";
  const logic = factory();
  if (typeof module === "object" && module.exports) module.exports = logic;
  else root.SimulatorLogic = logic;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // serie_a_2026.toml: Art. 6º (5 vagas de Libertadores pela liga), 7º (6 de Sul-Americana) e 8º (4 rebaixados).
  const LIBERTADORES_GROUPS = 4;
  const LIBERTADORES_SLOTS = 5;
  const SUDAMERICANA_SLOTS = 6;
  const RELEGATED = 4;
  // Pontuação (igual a sim_match_points e sim_pick_max, migração 0006).
  const POINTS = { exact: 10, winnerGoals: 7, difference: 6, loserGoals: 5, draw: 5, winner: 3, inverted: 2 };
  const TABLE_POINTS = { exact: 3, near: 1, champion: 10, top4: 3, relegated: 5 };
  const CODE_VERSION = "1";
  const OUTCOMES = ["H", "D", "A"];

  const outcomeOf = (home, away) => (home > away ? "H" : home < away ? "A" : "D");

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

  function draw(distribution, random = Math.random) {
    const target = random() * distribution.total;
    const cells = distribution.cells;
    let low = 0;
    let high = cells.length - 1;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (cells[middle][0] < target) low = middle + 1; else high = middle;
    }
    return [cells[low][1], cells[low][2]];
  }

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

  /* Pontuação de um palpite contra o placar real (igual a sim_match_points). */
  function matchPoints(mode, pick, homeGoals, awayGoals) {
    if (mode === "vencedor") {
      if (pick !== outcomeOf(homeGoals, awayGoals)) return 0;
      return homeGoals === awayGoals ? POINTS.draw : POINTS.winner;
    }
    const [home, away] = pick;
    const sameWinner = Math.sign(home - away) === Math.sign(homeGoals - awayGoals);
    const decided = homeGoals !== awayGoals;
    if (home === homeGoals && away === awayGoals) return POINTS.exact;
    if (sameWinner && decided && Math.max(home, away) === Math.max(homeGoals, awayGoals)) return POINTS.winnerGoals;
    if (sameWinner && decided && home - away === homeGoals - awayGoals) return POINTS.difference;
    if (sameWinner && decided && Math.min(home, away) === Math.min(homeGoals, awayGoals)) return POINTS.loserGoals;
    if (home === away && homeGoals === awayGoals) return POINTS.draw;
    if (sameWinner) return POINTS.winner;
    if (home !== away && home === awayGoals && away === homeGoals) return POINTS.inverted;
    return 0;
  }

  /* O que um palpite vale se o resultado sair como apostado (sim_pick_max). */
  const maxForPick = (mode, pick) => (mode === "placar" ? POINTS.exact : pick === "D" ? POINTS.draw : POINTS.winner);

  /* Classificação comparada com a tabela de hoje e o teto que ainda dá. `reach[clube]` = { best, worst }. */
  function tableScore(order, standingsOrder, reach) {
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
    order.slice(0, LIBERTADORES_GROUPS).forEach((clubId) => {
      if (standingsOrder.indexOf(clubId) < LIBERTADORES_GROUPS) points += TABLE_POINTS.top4;
      if (reach[clubId].best <= LIBERTADORES_GROUPS) ceiling += TABLE_POINTS.top4;
    });
    order.slice(total - RELEGATED).forEach((clubId) => {
      if (standingsOrder.indexOf(clubId) >= total - RELEGATED) points += TABLE_POINTS.relegated;
      if (reach[clubId].worst > total - RELEGATED) ceiling += TABLE_POINTS.relegated;
    });
    const maximum = total * TABLE_POINTS.exact + TABLE_POINTS.champion + LIBERTADORES_GROUPS * TABLE_POINTS.top4 + RELEGATED * TABLE_POINTS.relegated;
    return { points, ceiling, maximum };
  }

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
        if (!OUTCOMES.includes(body[start + 2])) return null;
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

  /* Mescla as simulações salvas de duas abas pelo local_id, sem perder nenhuma. `removed` guarda os IDs excluídos
     (lápides) para uma exclusão feita numa aba não ressuscitar pela outra. Em conflito, vale a de updated_at maior;
     empate fica com a `mine` (a aba que está gravando). */
  function mergeStores(mine, other) {
    const removed = [...new Set([...(mine.removed || []), ...((other && other.removed) || [])])];
    const gone = new Set(removed);
    const byId = new Map();
    ((other && other.saved) || []).forEach((item) => { if (!gone.has(item.local_id)) byId.set(item.local_id, item); });
    (mine.saved || []).forEach((item) => {
      if (gone.has(item.local_id)) return;
      const rival = byId.get(item.local_id);
      if (!rival || String(item.updated_at || "") >= String(rival.updated_at || "")) byId.set(item.local_id, item);
    });
    return { ...mine, saved: [...byId.values()], removed };
  }

  return {
    LIBERTADORES_GROUPS, LIBERTADORES_SLOTS, SUDAMERICANA_SLOTS, RELEGATED, POINTS, TABLE_POINTS, CODE_VERSION,
    outcomeOf, scoreSampler, draw, newRows, addResult, goalDifference, rankRows, matchPoints, maxForPick, tableScore,
    encodeLink, decodeLink, mergeStores,
  };
});
