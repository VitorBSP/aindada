/* Testes da lógica pura do simulador. Valores conferidos com a migração 0006 (sim_match_points, sim_pick_max,
   sim_scores), que substituiu a pontuação da 0003. Rodar: node --test tests/js/*.test.js */
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const logic = require(path.join(__dirname, "..", "..", "apps", "web", "assets", "simulator-logic.js"));

const { matchPoints, maxForPick, rankRows, newRows, addResult, encodeLink, decodeLink, scoreSampler, draw, tableScore, mergeStores } = logic;

/* ---- Placar exato: um caso por nível ---- */
test("placar exato: placar certo vale 10", () => assert.equal(matchPoints("placar", [2, 1], 2, 1), 10));
test("placar exato: vencedor e gols do vencedor valem 7", () => assert.equal(matchPoints("placar", [2, 0], 2, 1), 7));
test("placar exato: vencedor e diferença valem 6", () => assert.equal(matchPoints("placar", [3, 1], 2, 0), 6));
test("placar exato: vencedor e gols do perdedor valem 5", () => assert.equal(matchPoints("placar", [3, 1], 2, 1), 5));
test("placar exato: empate certo sem o placar vale 5", () => assert.equal(matchPoints("placar", [0, 0], 1, 1), 5));
test("placar exato: só o vencedor vale 3", () => assert.equal(matchPoints("placar", [4, 0], 2, 1), 3));
test("placar exato: placar invertido vale 2", () => assert.equal(matchPoints("placar", [0, 2], 2, 0), 2));
test("placar exato: resultado errado vale 0", () => assert.equal(matchPoints("placar", [1, 0], 0, 2), 0));
test("placar exato: empate apostado e jogo decidido vale 0", () => assert.equal(matchPoints("placar", [1, 1], 2, 1), 0));
test("placar exato: vitória apostada e empate real vale 0", () => assert.equal(matchPoints("placar", [2, 1], 1, 1), 0));

/* ---- Vencedor ---- */
test("vencedor: vitória certa vale 3", () => assert.equal(matchPoints("vencedor", "H", 2, 0), 3));
test("vencedor: vitória do visitante certa vale 3", () => assert.equal(matchPoints("vencedor", "A", 0, 1), 3));
test("vencedor: empate certo vale 5", () => assert.equal(matchPoints("vencedor", "D", 1, 1), 5));
test("vencedor: erro vale 0", () => assert.equal(matchPoints("vencedor", "H", 1, 1), 0));

/* ---- Máximo por palpite (sim_pick_max) ---- */
test("máximo: placar exato 10", () => assert.equal(maxForPick("placar", [1, 0]), 10));
test("máximo: vencedor empate 5", () => assert.equal(maxForPick("vencedor", "D"), 5));
test("máximo: vencedor vitória 3", () => assert.equal(maxForPick("vencedor", "H"), 3));

/* ---- Tabela e desempate (Art. 15) ---- */
function table(clubIds, results) {
  const rows = newRows(clubIds);
  results.forEach((result) => addResult(rows, result));
  return rankRows(rows, results);
}
const result = (home, away, homeGoals, awayGoals) => ({
  home, away, homeGoals, awayGoals, outcome: logic.outcomeOf(homeGoals, awayGoals),
});

test("rankRows: pontos decidem primeiro", () => {
  const ranked = table(["A", "B"], [result("A", "B", 0, 3)]);
  assert.deepEqual(ranked.map((row) => row.club_id), ["B", "A"]);
});

test("rankRows: vitórias vêm antes do saldo", () => {
  // A: 1 vitória e 1 derrota (3 pts, saldo -3); B: 3 empates (3 pts, saldo 0). A tem mais vitórias.
  const ranked = table(["A", "B", "C", "D"], [
    result("A", "C", 1, 0), result("D", "A", 4, 0), result("B", "C", 0, 0), result("B", "D", 1, 1), result("C", "B", 2, 2),
  ]);
  assert.equal(ranked.find((row) => row.club_id === "A").points, 3);
  assert.equal(ranked.find((row) => row.club_id === "B").points, 3);
  assert.ok(ranked.findIndex((row) => row.club_id === "A") < ranked.findIndex((row) => row.club_id === "B"));
});

test("rankRows: saldo desempata pontos e vitórias iguais", () => {
  const ranked = table(["A", "B", "C", "D"], [result("A", "C", 3, 0), result("B", "D", 1, 0)]);
  assert.deepEqual(ranked.slice(0, 2).map((row) => row.club_id), ["A", "B"]);
});

test("rankRows: gols marcados desempatam saldo igual", () => {
  const ranked = table(["A", "B", "C", "D"], [result("A", "C", 3, 2), result("B", "D", 1, 0)]);
  assert.deepEqual(ranked.slice(0, 2).map((row) => row.club_id), ["A", "B"]);
});

test("rankRows: ciclo de vitórias entre três clubes fica empatado", () => {
  const results = [result("A", "B", 0, 1), result("B", "C", 0, 1), result("C", "A", 0, 1)];
  // A, B e C: 3 pts, 1 vitória, saldo 0 e 1 gol: triplo empate, sem confronto direto.
  const ranked = table(["A", "B", "C"], results);
  assert.ok(ranked.every((row) => row.tie === "cartões ou sorteio"));
});

test("rankRows: confronto direto só entre dois clubes ordena pelo jogo entre eles", () => {
  const rows = newRows(["A", "B"]);
  rows.A.points = rows.B.points = 10;
  rows.A.wins = rows.B.wins = 3;
  rows.A.goals_for = rows.B.goals_for = 8;
  rows.A.goals_against = rows.B.goals_against = 5;
  const ranked = rankRows(rows, [result("A", "B", 0, 1)]);
  assert.deepEqual(ranked.map((row) => row.club_id), ["B", "A"]);
  assert.equal(ranked[0].tie, null);
});

test("rankRows: confronto direto empatado sem diferença deixa marcado", () => {
  const rows = newRows(["A", "B"]);
  rows.A.points = rows.B.points = 4;
  const ranked = rankRows(rows, [result("A", "B", 1, 1), result("B", "A", 1, 1)]);
  assert.deepEqual(ranked.map((row) => row.tie), ["cartões ou sorteio", "cartões ou sorteio"]);
});

test("rankRows: saldo no confronto direto desempata pontos iguais entre os dois", () => {
  const rows = newRows(["A", "B"]);
  rows.A.points = rows.B.points = 4;
  const ranked = rankRows(rows, [result("A", "B", 3, 0), result("B", "A", 1, 0)]);
  assert.equal(ranked[0].club_id, "A");
});

test("rankRows: três clubes empatados não usam confronto direto", () => {
  const rows = newRows(["A", "B", "C"]);
  const ranked = rankRows(rows, [result("A", "B", 5, 0)]);
  assert.ok(ranked.every((row) => row.tie === "cartões ou sorteio"));
});

test("rankRows: posições vão de 1 a N", () => {
  const ranked = table(["A", "B", "C"], [result("A", "B", 1, 0)]);
  assert.deepEqual(ranked.map((row) => row.position), [1, 2, 3]);
});

/* ---- Links ---- */
const clubs = ["ata", "bot", "cru", "fla"];
const matchList = [
  { match_id: "m0", status: "scheduled" },
  { match_id: "m1", status: "scheduled" },
  { match_id: "m2", status: "finished" },
];
const matchIndex = new Map(matchList.map((match, index) => [match.match_id, index]));

test("link de Classificação: ida e volta", () => {
  const order = ["fla", "ata", "cru", "bot"];
  const code = encodeLink("classificacao", { order }, matchIndex, clubs);
  assert.deepEqual(decodeLink("classificacao", code, clubs, matchList).entry.order, order);
});

test("link de Classificação: clube repetido é recusado", () => {
  assert.equal(decodeLink("classificacao", "1" + "0012", clubs, matchList), null);
});

test("link de Vencedor: ida e volta", () => {
  const entry = { picks: { m0: "H", m1: "D" }, sampled: {} };
  const decoded = decodeLink("vencedor", encodeLink("vencedor", entry, matchIndex, clubs), clubs, matchList);
  assert.deepEqual(decoded.entry.picks, { m0: "H", m1: "D" });
});

test("link de Placar exato: ida e volta", () => {
  const entry = { picks: { m0: [2, 1] }, sampled: { m1: [0, 0] } };
  const decoded = decodeLink("placar", encodeLink("placar", entry, matchIndex, clubs), clubs, matchList);
  assert.deepEqual(decoded.entry.picks, { m0: [2, 1], m1: [0, 0] });
});

test("link: palpite de jogo já disputado é ignorado e contado", () => {
  const decoded = decodeLink("vencedor", "1m" + "02H" + "00A", clubs, matchList);
  assert.deepEqual([decoded.ignored, decoded.entry.picks], [1, { m0: "A" }]);
});

test("link: versão desconhecida é recusada", () => assert.equal(decodeLink("vencedor", "9m00H", clubs, matchList), null));
test("link: resultado inválido é recusado", () => assert.equal(decodeLink("vencedor", "1m00X", clubs, matchList), null));
test("link: jogo inexistente é recusado", () => assert.equal(decodeLink("vencedor", "1m0zH", clubs, matchList), null));

/* ---- Sorteio ---- */
const sequence = (values) => { let index = 0; return () => values[index++ % values.length]; };

test("scoreSampler: sem matriz devolve null", () => assert.equal(scoreSampler({}), null));
test("scoreSampler: matriz zerada devolve null", () => assert.equal(scoreSampler({ score_probabilities: [[0, 0], [0, 0]] }), null));

test("draw: a faixa sorteada acompanha a probabilidade da célula", () => {
  const sampler = scoreSampler({ score_probabilities: [[0.5, 0.25], [0.25, 0]] });
  assert.deepEqual([draw(sampler, () => 0.1), draw(sampler, () => 0.6), draw(sampler, () => 0.9)], [[0, 0], [0, 1], [1, 0]]);
});

test("draw: nunca sorteia célula de probabilidade zero", () => {
  const sampler = scoreSampler({ score_probabilities: [[0, 1], [0, 0]] });
  const random = sequence([0, 0.3, 0.99999]);
  for (let count = 0; count < 3; count += 1) assert.deepEqual(draw(sampler, random), [0, 1]);
});

test("draw: frequência sorteada converge para a matriz", () => {
  const sampler = scoreSampler({ score_probabilities: [[0.7, 0], [0, 0.3]] });
  let randomState = 12345;
  const random = () => { randomState = (randomState * 1664525 + 1013904223) % 4294967296; return randomState / 4294967296; };
  let hits = 0;
  for (let count = 0; count < 20000; count += 1) if (draw(sampler, random)[0] === 1) hits += 1;
  assert.ok(Math.abs(hits / 20000 - 0.3) < 0.02);
});

/* ---- Classificação ---- */
const clubIds = Array.from({ length: 20 }, (_, index) => `c${String(index + 1).padStart(2, "0")}`);
const fullReach = Object.fromEntries(clubIds.map((clubId) => [clubId, { best: 1, worst: 20 }]));

test("Classificação: ordem idêntica à tabela dá o máximo de 102", () => {
  const score = tableScore(clubIds, clubIds, fullReach);
  assert.deepEqual([score.points, score.maximum], [102, 102]);
});

test("Classificação: máximo é 20×3 + 10 + 4×3 + 4×5", () => {
  assert.equal(tableScore(clubIds, clubIds, fullReach).maximum, 60 + 10 + 12 + 20);
});

test("Classificação: ordem invertida só pontua o que bate", () => {
  const reversed = [...clubIds].reverse();
  // Só o 10º e o 11º ficam a uma casa da certa (1 ponto cada); G4, campeão e rebaixados não batem.
  assert.equal(tableScore(reversed, clubIds, fullReach).points, 2);
});

test("Classificação: uma posição de diferença vale 1", () => {
  const swapped = [...clubIds];
  [swapped[8], swapped[9]] = [swapped[9], swapped[8]];
  assert.equal(tableScore(swapped, clubIds, fullReach).points, 102 - 2 * 3 + 2 * 1);
});

test("Classificação: trocar o 1º e o 2º perde o campeão (10) e as posições exatas, mas mantém o G4", () => {
  const order = [...clubIds];
  [order[0], order[1]] = [order[1], order[0]];
  assert.equal(tableScore(order, clubIds, fullReach).points, 102 - 10 - 2 * 3 + 2 * 1);
});

test("Classificação: teto cai quando o clube não alcança mais a posição", () => {
  const reach = { ...fullReach, c01: { best: 3, worst: 3 } };
  assert.ok(tableScore(clubIds, clubIds, reach).ceiling < 102);
});

/* ---- Mescla entre abas ---- */
const saved = (id, updatedAt, extra = {}) => ({ local_id: id, mode: "vencedor", updated_at: updatedAt, entry: {}, ...extra });

test("mescla: simulação salva em outra aba não se perde", () => {
  const merged = mergeStores({ version: 2, saved: [saved("AAAA", "2026-11-01")] }, { version: 2, saved: [saved("BBBB", "2026-11-02")] });
  assert.deepEqual(merged.saved.map((item) => item.local_id).sort(), ["AAAA", "BBBB"]);
});

test("mescla: duas abas sem o ID uma da outra ficam com as duas", () => {
  const tabOne = { version: 2, saved: [saved("AAAA", "1")] };
  const tabTwo = { version: 2, saved: [saved("BBBB", "2")] };
  const firstWrite = mergeStores(tabTwo, tabOne);
  const secondWrite = mergeStores(tabOne, firstWrite);
  assert.equal(secondWrite.saved.length, 2);
});

test("mescla: mesmo ID fica com o updated_at mais novo", () => {
  const merged = mergeStores(
    { saved: [saved("AAAA", "2026-11-01", { note: "velha" })] },
    { saved: [saved("AAAA", "2026-11-03", { note: "nova" })] },
  );
  assert.equal(merged.saved[0].note, "nova");
});

test("mescla: empate de updated_at fica com a aba que grava", () => {
  const merged = mergeStores({ saved: [saved("AAAA", "1", { note: "minha" })] }, { saved: [saved("AAAA", "1", { note: "outra" })] });
  assert.equal(merged.saved[0].note, "minha");
});

test("mescla: exclusão numa aba não ressuscita pela outra", () => {
  const merged = mergeStores({ saved: [], removed: ["AAAA"] }, { saved: [saved("AAAA", "1")] });
  assert.deepEqual(merged.saved, []);
});

test("mescla: exclusão feita na outra aba vale nesta", () => {
  const merged = mergeStores({ saved: [saved("AAAA", "1")] }, { saved: [], removed: ["AAAA"] });
  assert.deepEqual(merged.saved, []);
});

test("mescla: rascunho e sessão em andamento ficam os da aba que grava", () => {
  const merged = mergeStores({ saved: [], active: { mode: "placar" }, drafts: { a: 1 } }, { saved: [], active: { mode: "vencedor" } });
  assert.equal(merged.active.mode, "placar");
});

test("mescla: sem armazenamento anterior devolve as da própria aba", () => {
  assert.equal(mergeStores({ saved: [saved("AAAA", "1")] }, null).saved.length, 1);
});
