"use strict";

// Champions League (ADR-0012) no desenho dos sites de competição (D-043): Início, Chave provável, Fase de liga,
// Jogos e Como calculamos. Com a fase de liga encerrada (data.phase = "knockout"), Início e Chave mostram os
// confrontos reais do mata-mata, com placares de ida e volta e a probabilidade de cada clube passar.
(function () {
  const S = window.AIndaDaSite;
  const { escapeHtml, pct, team } = S;
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
  // Art. 19: seção A = 1º/2º contra os vencedores do playoff 15º/16º × 17º/18º; B = 3º/4º × (13º/14º × 19º/20º);
  // C = 5º/6º × (11º/12º × 21º/22º); D = 7º/8º × (9º/10º × 23º/24º). Quartas: A × D e B × C em cada lado da chave.
  const SECTIONS = [
    { id: "A", seeds: [1, 2], playoff: [15, 16, 17, 18] },
    { id: "B", seeds: [3, 4], playoff: [13, 14, 19, 20] },
    { id: "C", seeds: [5, 6], playoff: [11, 12, 21, 22] },
    { id: "D", seeds: [7, 8], playoff: [9, 10, 23, 24] },
  ];

  // `playoff = out` vale tanto para quem já caiu quanto para quem já garantiu o top 8: o rótulo diz qual dos dois.
  function zoneLabel(club, zone) {
    if (zone === "playoff" && club.clinched.top8 === "in") return "já nas oitavas";
    if (zone === "playoff" && club.clinched.playoff === "out") return club.clinched.out === "in" ? "eliminado" : pct(club.zones.playoff);
    return club.clinched[zone] ? DONE[zone][club.clinched[zone]] : pct(club.zones[zone]);
  }
  const matchday = (data) => Math.max(...data.clubs.map((club) => club.played));
  const isKnockout = (data) => data.phase === "knockout";
  const STAGE_NAMES = { PLAYOFFS: "Playoff", LAST_16: "Oitavas", QUARTER_FINALS: "Quartas", SEMI_FINALS: "Semifinal", FINAL: "Final" };
  const STAGE_ORDER = Object.keys(STAGE_NAMES);
  const NEXT = { PLAYOFFS: "round_of_16", LAST_16: "quarter_finals", QUARTER_FINALS: "semi_finals", SEMI_FINALS: "final", FINAL: "winner" };
  const dayMonth = (iso) => S.formatDate(iso, { day: "2-digit", month: "2-digit" });

  // Jogos do mata-mata por disputar, no formato dos jogos da fase de liga (cards, popup e "Próximo jogo" do Seu time).
  const knockoutMatches = (data) => (data.knockout || []).flatMap((tie) => tie.legs
    .filter((leg) => leg.status === "scheduled")
    .map((leg) => ({ ...leg, round: null, stage: tie.stage })));
  const inPositions = (club, positions) => positions.reduce((sum, position) => sum + club.position_probabilities[position - 1], 0);

  function edition(data) {
    const day = escapeHtml(S.formatDate(data.reference_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }));
    if (isKnockout(data)) {
      const ties = data.knockout || [];
      const decided = ties.filter((tie) => tie.winner_id).length;
      return `<p class="edition"><span class="edition-name">Edição de ${day}</span> · ${escapeHtml(data.competition_name)} · mata-mata, ${escapeHtml(STAGE_NAMES[data.current_stage] || "")}</p>
        <p class="edition-facts"><strong>${decided}</strong> de ${ties.length} confrontos já decididos · <strong>${data.n_simulations.toLocaleString("pt-BR")}</strong> simulações até a final</p>`;
    }
    return `<p class="edition"><span class="edition-name">Edição de ${day}</span> · ${escapeHtml(data.competition_name)} · fase de liga, ${matchday(data)} de 8 rodadas</p>
      <p class="edition-facts"><strong>${data.observed_matches}</strong> de ${data.observed_matches + data.remaining_matches} jogos disputados · <strong>${data.n_simulations.toLocaleString("pt-BR")}</strong> simulações até a final</p>`;
  }

  // Próximos jogos com data, em ordem cronológica: os que faltam da fase de liga e os do mata-mata.
  const upcoming = (data) => [...data.remaining, ...knockoutMatches(data)].filter((match) => match.match_date);

  /* ---------------- Mata-mata real */

  // Gols de cada lado num jogo encerrado, com a prorrogação somada (o placar que vale no confronto).
  const legGoals = (leg) => (leg.extra_time ? leg.extra_time : [leg.home_goals, leg.away_goals]);

  function tieState(tie) {
    const last = tie.legs[tie.legs.length - 1];
    const pending = tie.legs.find((leg) => leg.status === "scheduled");
    if (tie.winner_id) {
      const how = last && last.penalties
        ? ` nos pênaltis (${escapeHtml(S.shortOf(last.home_id))} ${last.penalties[0]} × ${last.penalties[1]} ${escapeHtml(S.shortOf(last.away_id))})`
        : last && last.extra_time ? " na prorrogação" : "";
      return `${escapeHtml(S.nameOf(tie.winner_id))} passou${how}`;
    }
    if (pending) return `${tie.stage === "FINAL" ? "Jogo único" : pending.leg === 1 ? "Ida" : "Volta"} em ${escapeHtml(dayMonth(pending.match_date))}`;
    return tie.stage === "FINAL" ? "Jogo único" : "Volta ainda sem data";
  }

  function legLine(tie) {
    return tie.legs.map((leg) => {
      const label = tie.stage === "FINAL" ? "Final" : leg.leg === 1 ? "Ida" : "Volta";
      if (leg.status !== "finished") return `<span>${label}: ${escapeHtml(S.shortOf(leg.home_id))} × ${escapeHtml(S.shortOf(leg.away_id))}, ${escapeHtml(dayMonth(leg.match_date))}</span>`;
      const [home, away] = legGoals(leg);
      return `<span>${label}: ${escapeHtml(S.shortOf(leg.home_id))} <b>${home} × ${away}</b> ${escapeHtml(S.shortOf(leg.away_id))}${leg.extra_time ? " (prorr.)" : ""}</span>`;
    }).join("");
  }

  function tieCard(tie) {
    const label = tie.stage === "FINAL" ? "título" : "passa";
    const sides = tie.club_ids.map((id, index) => {
      const decided = Boolean(tie.winner_id);
      const won = decided && tie.winner_id === id;
      const value = tie.advance[id];
      const end = decided ? (won ? "passou" : "fora") : pct(value);
      const aggregate = tie.aggregate ? `<span class="ko-agg" aria-label="${tie.legs.length > 1 ? "agregado" : "placar"}">${tie.aggregate[index]}</span>` : `<span class="ko-agg"></span>`;
      return `<div class="ko-side${won ? " is-won" : decided ? " is-lost" : ""}">${team(id, 22)}${aggregate}<strong class="ko-adv${!decided && value >= 0.5 ? " is-top" : ""}" aria-label="${escapeHtml(S.nameOf(id))} ${label}: ${escapeHtml(end)}">${escapeHtml(end)}</strong></div>`;
    }).join("");
    return `<article class="ko-tie">
      <div class="ko-head"><span>${escapeHtml(STAGE_NAMES[tie.stage])}</span><span>${tieState(tie)}</span></div>
      ${sides}
      <p class="ko-legs">${legLine(tie)}</p>
    </article>`;
  }

  const tiesOf = (data, stage) => (data.knockout || []).filter((tie) => tie.stage === stage);

  function knockoutHome(data) {
    const stage = data.current_stage;
    const current = tiesOf(data, stage);
    const facts = knockoutFacts(data);
    const alive = data.clubs.filter((club) => !facts.out.has(club.club_id));
    const byWinner = [...alive].sort((a, b) => b.stages.winner - a.stages.winner).slice(0, 8);
    const info = `<p>A fase de liga acabou: agora são os confrontos reais do mata-mata. Ida e volta decidem pelo agregado, sem gol fora; empate leva à prorrogação e aos pênaltis. A final é em jogo único.</p>
      <p>"Passa" diz em quantas das ${data.n_simulations.toLocaleString("pt-BR")} simulações o clube vence o confronto. Placar real entra como aconteceu; só o que falta é simulado.</p>`;
    const next = upcoming(data).sort(chronological).slice(0, HOME_MATCHES);
    const stageBlock = current.length
      ? `<section class="comp-block" aria-labelledby="ko-now"><div class="block-head"><h2 id="ko-now">${escapeHtml(STAGE_NAMES[stage])}</h2><a class="block-link" href="#/chave">Chave ›</a></div><div class="ko-grid">${current.map(tieCard).join("")}</div></section>`
      : `<section class="comp-block" aria-labelledby="ko-now"><div class="block-head"><h2 id="ko-now">${escapeHtml(STAGE_NAMES[stage] || "Mata-mata")}</h2><a class="block-link" href="#/chave">Chave ›</a></div><p class="note">Os confrontos desta fase aparecem aqui quando a fonte trouxer os clubes. Até lá, a chave usa o regulamento e sorteia onde a UEFA sorteia.</p></section>`;
    const nextBlock = next.length
      ? `<section class="comp-block" aria-labelledby="comp-next"><div class="block-head"><h2 id="comp-next">Próximos jogos</h2><a class="block-link" href="#/jogos">Ver todos ›</a></div>${S.matchesByDay(next)}</section>`
      : "";
    const racesBlock = `<div class="races">
        ${S.raceCard("Título", "% das simulações em que é campeão.", S.raceRows(byWinner.map((club) => ({ id: club.club_id, value: club.stages.winner })), ""))}
      </div>`;
    return `
      ${S.screenHead("Para quem ainda dá?", info)}
      ${stageBlock}
      ${next.length ? `<div class="comp-home-grid">${nextBlock}${racesBlock}</div>` : racesBlock}
      <nav class="chip-row comp-links" aria-label="Mais"><a class="chip" href="#/chave">Chave do mata-mata ›</a><a class="chip" href="#/fase-de-liga">Fase de liga ›</a></nav>`;
  }

  function knockoutBracket(data) {
    const info = `<p>Confrontos reais de cada fase, com o placar de cada jogo e o agregado. Nos que faltam decidir, a porcentagem diz em quantas simulações o clube passa.</p>
      <p>Fases sem confronto definido mostram os clubes com mais simulações chegando lá. Onde a fonte ainda não mostra o cruzamento, a simulação sorteia entre as chaves do regulamento que batem com o que já aconteceu.</p>`;
    const facts = knockoutFacts(data);
    const blocks = STAGE_ORDER.map((stage) => {
      const ties = tiesOf(data, stage);
      if (ties.length) return `<section class="comp-block" aria-labelledby="ko-${stage}"><h2 id="ko-${stage}" class="ko-stage">${escapeHtml(STAGE_NAMES[stage])}</h2><div class="ko-grid">${ties.map(tieCard).join("")}</div></section>`;
      const key = { PLAYOFFS: "round_of_16", LAST_16: "round_of_16", QUARTER_FINALS: "quarter_finals", SEMI_FINALS: "semi_finals", FINAL: "final" }[stage];
      if (stage === "PLAYOFFS") return "";
      const sure = data.clubs.filter((club) => facts.reached[key].has(club.club_id));
      const likely = data.clubs.filter((club) => !facts.reached[key].has(club.club_id) && !facts.out.has(club.club_id) && club.stages[key] > 0)
        .sort((a, b) => b.stages[key] - a.stages[key]).slice(0, 8);
      if (!likely.length && !sure.length) return "";
      const rows = [...sure.map((club) => ({ id: club.club_id, value: 1, label: "garantido" })), ...likely.map((club) => ({ id: club.club_id, value: club.stages[key] }))];
      return `<section class="comp-block" aria-labelledby="ko-${stage}"><h2 id="ko-${stage}" class="ko-stage">${escapeHtml(STAGE_NAMES[stage])} <span>quem chega</span></h2>${S.raceRows(rows, "")}</section>`;
    }).join("");
    return `
      ${S.screenHead("Chave do mata-mata", info)}
      ${blocks}
      <h2 class="comp-section-h">Fase a fase</h2>
      ${stagesTable({ ...data, clubs: data.clubs.filter((club) => club.zones.out < 1) })}`;
  }
  const chronological = (a, b) => (a.kickoff_utc || a.match_date).localeCompare(b.kickoff_utc || b.match_date);
  const HOME_MATCHES = 4;

  function home(data) {
    if (isKnockout(data)) return knockoutHome(data);
    const open = (zone) => data.clubs.filter((club) => club.clinched[zone] !== "out");
    const byWinner = [...data.clubs].sort((a, b) => b.stages.winner - a.stages.winner).slice(0, 8);
    const byTop8 = open("top8").sort((a, b) => b.zones.top8 - a.zones.top8).slice(0, 8);
    const byOut = open("out").sort((a, b) => b.zones.out - a.zones.out).slice(0, 8);
    const info = `<p>Do 1º ao 8º vão direto às oitavas, do 9º ao 24º jogam o playoff e do 25º em diante saem.</p>
      <p>Cada porcentagem diz em quantas das ${data.n_simulations.toLocaleString("pt-BR")} simulações (fase de liga e mata-mata até a final) aquilo aconteceu. "Garantido", "não dá mais" e "eliminado" só aparecem quando a conta de pontos fecha.</p>`;
    const next = upcoming(data).sort(chronological).slice(0, HOME_MATCHES);
    const nextBlock = next.length
      ? `<section class="comp-block" aria-labelledby="comp-next"><div class="block-head"><h2 id="comp-next">Próximos jogos</h2><a class="block-link" href="#/jogos">Ver todos ›</a></div>${S.matchesByDay(next)}</section>`
      : "";
    const racesBlock = `<div class="races">
        ${S.raceCard("Título", "% das simulações em que é campeão.", S.raceRows(byWinner.map((club) => ({ id: club.club_id, value: club.stages.winner })), ""))}
        ${S.raceCard("Direto às oitavas", "% das simulações em que termina entre 1º e 8º.", S.raceRows(byTop8.map((club) => ({ id: club.club_id, value: club.zones.top8, label: zoneLabel(club, "top8") })), "lib"))}
        ${S.raceCard("Eliminado na fase de liga", "% das simulações em que termina entre 25º e 36º.", S.raceRows(byOut.map((club) => ({ id: club.club_id, value: club.zones.out, label: zoneLabel(club, "out") })), "danger"))}
      </div>`;
    return `
      ${S.screenHead("Para quem ainda dá?", info)}
      ${next.length ? `<div class="comp-home-grid">${nextBlock}${racesBlock}</div>` : racesBlock}
      <nav class="chip-row comp-links" aria-label="Mais"><a class="chip" href="#/chave">Chave provável ›</a><a class="chip" href="#/fase-de-liga">Fase de liga ›</a></nav>`;
  }

  function candidates(data, positions, limit) {
    return data.clubs
      .map((club) => ({ club, value: inPositions(club, positions) }))
      .filter((item) => item.value >= 0.01)
      .sort((a, b) => b.value - a.value)
      .slice(0, limit);
  }

  function sectionCard(data, section) {
    const seeds = candidates(data, section.seeds, 4);
    const playoff = candidates(data, section.playoff, 4);
    const list = (items, extra) => `<ul class="candidates">${items.map((item) => `<li>${team(item.club.club_id, 16)}<strong>${pct(item.value)}${extra ? ` · quartas ${pct(item.club.stages.quarter_finals)}` : ""}</strong></li>`).join("") || "<li>—</li>"}</ul>`;
    return `<div class="section-card">
      <h3>Seção ${section.id}</h3>
      <p class="candidates-label">Cabeça: ${section.seeds[0]}º ou ${section.seeds[1]}º colocado</p>${list(seeds, true)}
      <p class="candidates-label">Adversário: vencedor do playoff ${section.playoff[0]}º/${section.playoff[1]}º × ${section.playoff[2]}º/${section.playoff[3]}º</p>${list(playoff, false)}
    </div>`;
  }

  function bracketBox(title, lines) {
    return `<div class="tie"><div class="tie-head"><span>${title}</span><b>ida e volta</b></div>${lines.map((line) => `<div class="tie-side open">${line}</div>`).join("")}</div>`;
  }

  function bracket(data) {
    if (isKnockout(data)) return knockoutBracket(data);
    const label = (section) => `${section.seeds[0]}º/${section.seeds[1]}º × playoff ${section.playoff[0]}º–${section.playoff[3]}º`;
    const [a, b, c, d] = SECTIONS;
    const finalists = [...data.clubs].sort((x, y) => y.stages.final - x.stages.final).slice(0, 6);
    const semis = [...data.clubs].sort((x, y) => y.stages.semi_finals - x.stages.semi_finals).slice(0, 8);
    const info = `<p>A fase de liga ainda não acabou, então a chave sai das posições finais. Cada lado da chave tem um cabeça de cada seção; o 1º e o 2º caem em lados opostos e só podem se cruzar na final.</p>
      <p>Nas seções, o percentual ao lado de cada clube diz em quantas simulações ele termina nas posições daquela seção; para os cabeças, também a probabilidade de chegar às quartas.</p>
      <p>Na tabela fase a fase, o percentual diz em quantas simulações o clube chega a cada fase. As oitavas somam quem foi direto e quem passou no playoff.</p>`;
    return `
      ${S.screenHead("Chave provável", info)}
      <h2 class="comp-section-h">O caminho de um lado da chave</h2>
      <div class="bracket" style="--rounds:4">
        <div class="bracket-round"><h3>Oitavas</h3>${[a, d, b, c].map((section) => bracketBox(`Seção ${section.id}`, [label(section)])).join("")}</div>
        <div class="bracket-round"><h3>Quartas</h3>${bracketBox("A × D", ["vencedor da seção A", "vencedor da seção D"])}${bracketBox("B × C", ["vencedor da seção B", "vencedor da seção C"])}</div>
        <div class="bracket-round"><h3>Semifinal</h3>${bracketBox("(A × D) × (B × C)", ["vencedores das quartas"])}</div>
        <div class="bracket-round"><h3>Final</h3><div class="tie"><div class="tie-head"><span>Jogo único</span><b>final</b></div><p class="candidates-label">Mais prováveis na final</p><ul class="candidates">${finalists.map((club) => `<li>${team(club.club_id, 16)}<strong>${pct(club.stages.final)}</strong></li>`).join("")}</ul></div></div>
      </div>
      <h2 class="comp-section-h">Quem pode ocupar cada seção</h2>
      <div class="sections-grid">${SECTIONS.map((section) => sectionCard(data, section)).join("")}</div>
      <div class="comp-block">${S.raceCard("Mais prováveis nas semifinais", "% das simulações em que o clube chega às semifinais.", S.raceRows(semis.map((club) => ({ id: club.club_id, value: club.stages.semi_finals })), ""))}</div>
      <h2 class="comp-section-h">Fase a fase</h2>
      ${stagesTable(data)}`;
  }

  // Fatos do mata-mata (nunca da simulação): quem já chegou a cada fase e quem já caiu. Top 8 vai direto às oitavas;
  // vencedor de confronto decidido chega à fase seguinte; perdedor e quem ficou de 25º a 36º estão fora.
  function knockoutFacts(data) {
    const reached = Object.fromEntries(STAGES.map(([key]) => [key, new Set()]));
    const out = new Set(data.clubs.filter((club) => club.zones.out === 1).map((club) => club.club_id));
    data.clubs.filter((club) => club.zones.top8 === 1).forEach((club) => reached.round_of_16.add(club.club_id));
    (data.knockout || []).filter((tie) => tie.winner_id).forEach((tie) => {
      reached[NEXT[tie.stage]].add(tie.winner_id);
      tie.club_ids.filter((id) => id !== tie.winner_id).forEach((id) => out.add(id));
    });
    // Quem chegou a uma fase também chegou às anteriores.
    STAGES.map(([key]) => key).reduceRight((later, key) => { later.forEach((id) => reached[key].add(id)); return reached[key]; }, new Set());
    return { reached, out };
  }

  function stageText(data, facts, club, key) {
    if (!facts) return pct(club.stages[key]);
    if (facts.reached[key].has(club.club_id)) return key === "winner" ? "campeão" : "garantido";
    if (facts.out.has(club.club_id)) return "—";
    return pct(club.stages[key]);
  }

  function stagesTable(data) {
    const knockout = isKnockout(data);
    const facts = knockout ? knockoutFacts(data) : null;
    const rows = [...data.clubs]
      .sort((a, b) => b.stages.winner - a.stages.winner || b.stages.final - a.stages.final || b.stages.semi_finals - a.stages.semi_finals
        || b.stages.quarter_finals - a.stages.quarter_finals || b.stages.round_of_16 - a.stages.round_of_16)
      .map((club) => `<tr>
        <td class="left club">${S.teamCell(club.club_id, 20)}</td>
        <td>${knockout ? (club.zones.top8 === 1 ? "sim" : "—") : S.probCell(club.zones.top8, "lib", club.clinched.top8 ? zoneLabel(club, "top8") : null)}</td>
        <td>${knockout ? (club.zones.playoff === 1 ? "sim" : "—") : S.probCell(club.zones.playoff, "sula", club.clinched.playoff || club.clinched.top8 ? zoneLabel(club, "playoff") : null)}</td>
        ${STAGES.map(([key]) => `<td class="stage${club.stages[key] >= 0.5 ? " strong" : ""}">${stageText(data, facts, club, key)}</td>`).join("")}
      </tr>`)
      .join("");
    return `<div class="table-scroll table-card" tabindex="0" role="region" aria-label="Probabilidade de cada clube por fase">
      <table><thead><tr><th class="left">Clube</th><th>Top 8</th><th>Playoff</th>${STAGES.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>
    </div>`;
  }

  const clubModels = (data) => data.clubs.map((club) => ({
    id: club.club_id, name: club.name, position: club.position, points: club.points,
    meta: `${club.points} pts · ${club.played} J`, interval: null,
  }));

  function races(data) {
    const byId = Object.fromEntries(data.clubs.map((club) => [club.club_id, club]));
    const zone = (id, label, color, words, text, info) => ({
      id, label, color, words, info,
      value: (model) => byId[model.id].zones[id],
      text: (model) => { const label_ = byId[model.id].clinched[id] || (id === "playoff" && byId[model.id].clinched.top8) ? zoneLabel(byId[model.id], id) : null; return label_; },
      state: (model) => { const club = byId[model.id]; return id === "playoff" ? (club.clinched.playoff === "in" ? "in" : club.clinched.playoff === "out" || club.clinched.top8 === "in" ? "out" : null) : club.clinched[id] || null; },
    });
    const winner = {
      id: "winner", label: "Título", color: "title",
      words: { sure: "Campeão", open: "Na briga pelo título", out: "Sem probabilidade relevante de título" },
      value: (model) => byId[model.id].stages.winner,
      info: `<p>% das ${data.n_simulations.toLocaleString("pt-BR")} simulações (fase de liga e mata-mata até a final) em que o clube é campeão.</p>`,
    };
    return [
      winner,
      zone("top8", "Top 8", "libertadores", { sure: "Direto às oitavas em quase todas", open: "Na briga pelo top 8", out: "Longe do top 8" }, null, "<p>% das simulações em que termina entre 1º e 8º e vai direto às oitavas. \"Garantido\" só quando a conta de pontos fecha.</p>"),
      zone("playoff", "Playoff", "sudamericana", { sure: "No playoff em quase todas", open: "Na briga pelo playoff", out: "Fora do playoff" }, null, "<p>% das simulações em que termina entre 9º e 24º e joga o playoff.</p>"),
      zone("out", "Eliminado", "danger", { sure: "Eliminados em quase todas", open: "Ainda correm risco", out: "Longe da eliminação" }, null, "<p>% das simulações em que termina entre 25º e 36º e está fora.</p>"),
    ];
  }

  function leaguePhase(data) {
    const info = `<p>Escolha a disputa: quem já está garantido, quem está na briga e quem está fora. "Tabela completa" traz a ordem atual por pontos, saldo e gols, com a probabilidade de cada faixa. Faixa lateral: azul = direto às oitavas (1º ao 8º), âmbar = playoff (9º ao 24º), vermelho = eliminado (25º ao 36º).</p><p>Toque num clube para ver a ficha dele.</p>`;
    return `
      ${S.screenHead("Fase de liga", info + races(data).map((race) => `<p><strong>${escapeHtml(race.label)}.</strong> ${race.info.replace(/^<p>|<\/p>$/g, "")}</p>`).join(""))}
      ${S.disputeBoard("fase", { clubs: clubModels(data), races: races(data), full: () => leagueTable(data) })}`;
  }

  function leagueTable(data) {
    const zone = (position) => (position <= 8 ? "zone-lib" : position <= 24 ? "zone-sula" : "zone-z4");
    // Probabilidades logo depois de Pts: no celular o percentual aparece sem rolar a tabela de lado.
    const rows = data.clubs.map((club) => {
      const goalDifference = club.goals_for - club.goals_against;
      return `<tr class="${zone(club.position)}">
        <td class="pos">${club.position}</td>
        <td class="left club">${S.teamCell(club.club_id, 20, `<span class="elo-country">${escapeHtml(club.country)}</span>`)}</td>
        <td><strong>${club.points}</strong></td>
        <td class="view-start">${S.probCell(club.zones.top8, "lib", club.clinched.top8 ? zoneLabel(club, "top8") : null)}</td>
        <td>${S.probCell(club.zones.playoff, "sula", club.clinched.playoff || club.clinched.top8 ? zoneLabel(club, "playoff") : null)}</td>
        <td>${S.probCell(club.zones.out, "danger", club.clinched.out ? zoneLabel(club, "out") : null)}</td>
        <td class="rest-start">${club.played}</td><td>${goalDifference > 0 ? "+" : ""}${goalDifference}</td><td>${club.goals_for}</td>
        <td>${number.format(club.expected_points)}</td>
        <td class="left">${S.heat(club.position_probabilities, club.name).replace('class="heat"', 'class="heat heat-wide"')}</td>
      </tr>`;
    }).join("");
    return `<div class="table-scroll table-card" tabindex="0" role="region" aria-label="Tabela da fase de liga">
        <table class="standings">
          <thead><tr><th>#</th><th class="left">Clube</th><th>Pts</th><th class="view-start">Top 8</th><th>Playoff</th><th>Eliminado</th><th class="rest-start">J</th><th>SG</th><th>GP</th><th>Pts proj.</th><th class="left">Posição final (1º → 36º)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function matches(data) {
    const scheduled = upcoming(data).filter((match) => match.round !== null || match.stage);
    const info = "<p>Horários de Brasília. Probabilidade de vitória do mandante, de empate e de vitória do visitante, com a força de cada clube na data da edição. Toque num jogo para ver os detalhes e num clube para ver a ficha dele.</p>";
    return `
      ${S.screenHead("Jogos", info)}
      ${S.dayAgenda("jogos", scheduled)}`;
  }

  function method(data) {
    const backtest = data.backtest;
    const seasons = backtest ? backtest.test_seasons.map((season) => `${season}/${String(season + 1).slice(2)}`).join(" e ") : "";
    const facts = backtest
      ? `<div class="stat-row">
          <div class="stat"><span class="label">Log loss por jogo</span><span class="big">${decimal.format(backtest.log_loss)}</span><span class="sub">${backtest.n_matches} jogos de ${seasons}; taxa base ${decimal.format(backtest.log_loss_base_rate)}</span></div>
          <div class="stat"><span class="label">Brier do top 8</span><span class="big">${decimal.format(backtest.top8_brier)}</span><span class="sub">com ${8 - backtest.late_matchday} rodadas por jogar; só a proporção ${decimal.format(backtest.top8_brier_base)}</span></div>
          <div class="stat"><span class="label">Brier das quartas</span><span class="big">${decimal.format(backtest.quarter_finals_brier)}</span><span class="sub">no mesmo ponto; só a proporção ${decimal.format(backtest.quarter_finals_brier_base)}</span></div>
          <div class="stat"><span class="label">Log loss do campeão</span><span class="big">${decimal.format(backtest.winner_log_loss)}</span><span class="sub">chute uniforme ${decimal.format(backtest.winner_log_loss_uniform)}; só duas temporadas</span></div>
        </div>`
      : "";
    return `
      <h1 class="race-heading">Como calculamos</h1>
      <p>Na Champions, os clubes vêm de ligas diferentes. Por isso usamos uma força única (Elo) para todos, calculada com as sete principais ligas da Europa e com a Champions, a Liga Europa e a Conference desde 2021/22: as copas europeias ligam as ligas entre si. Um modelo de gols treinado só com jogos europeus de temporadas anteriores transforma a diferença de força em placares. Cada uma das ${data.n_simulations.toLocaleString("pt-BR")} simulações termina a fase de liga com os critérios de desempate da UEFA e joga o mata-mata com o chaveamento do regulamento, até a final.</p>
      <h2>Acerto em temporadas passadas</h2>
      ${facts}
      <p class="note">Menor é melhor no log loss e no Brier.</p>
      <h2>Limitações</h2>
      <ul class="summary-list">${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
        <li>Clubes de ligas fora das sete principais têm força medida só pelos jogos europeus; os que nunca jogaram copas europeias desde 2021/22 começam de um valor fixo.</li>
        <li>A chave provável mostra as posições de cada seção; onde a UEFA sorteia (quem é o 1º ou o 2º de cada lado), a simulação sorteia com probabilidades iguais.</li>
        <li>"Garantido", "não dá mais", "eliminado" e "não cai mais" só aparecem quando a conta de pontos fecha, nunca por simulação.</li>
      </ul>
      <h2>Regulamento e fontes</h2>
      <p>Regulamento: <a href="${S.safeUrl(data.regulation.url)}">${escapeHtml(data.regulation.title)}</a>.</p>
      <ul class="summary-list">${S.sources(data.sources)}</ul>
      <p class="note">Modelo ${escapeHtml(data.model_version)} · dados <code class="data-version">${escapeHtml(data.data_version)}</code> · semente ${data.seed} · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}</p>
      <div id="metodo-elo"></div>`;
  }

  S.start({
    names: (data) => Object.fromEntries(data.clubs.map((club) => [club.club_id, club.name])),
    shorts: (data) => Object.fromEntries(data.clubs.map((club) => [club.club_id, club.short_name])),
    club: (data, id) => {
      const club = data.clubs.find((item) => item.club_id === id);
      if (!club) return null;
      const meta = `${club.position}º na fase de liga · ${club.points} pts · ${club.played} J`;
      const next = upcoming(data).filter((match) => match.home_id === id || match.away_id === id).sort(chronological).slice(0, 3);
      if (isKnockout(data)) {
        const tie = (data.knockout || []).find((item) => item.stage === data.current_stage && item.club_ids.includes(id));
        const now = tie ? (tie.winner_id ? (tie.winner_id === id ? "passou" : "fora") : pct(tie.advance[id])) : knockoutFacts(data).out.has(id) ? "fora" : "na disputa";
        return {
          name: club.name, meta, next,
          stats: [
            { label: tie ? `Passa (${STAGE_NAMES[tie.stage]})` : "Mata-mata", text: now, tone: "is-g4" },
            { label: "Final", text: pct(club.stages.final) },
            { label: "Título", text: pct(club.stages.winner) },
          ],
        };
      }
      return {
        name: club.name, meta, next,
        stats: [
          { label: "Top 8", text: zoneLabel(club, "top8"), tone: "is-g4" },
          { label: "Playoff", text: zoneLabel(club, "playoff") },
          { label: "Título", text: pct(club.stages.winner) },
        ],
      };
    },
    history: {
      clubs: (data) => data.clubs.map((club) => ({ id: club.club_id, name: club.name })),
      metrics: () => [
        { id: "winner", label: "Título", color: "title", get: (entry) => (entry.stages ? entry.stages.winner : 0) },
        { id: "top8", label: "Top 8", color: "libertadores", get: (entry) => entry.zones.top8 },
        { id: "playoff", label: "Playoff", color: "sudamericana", get: (entry) => entry.zones.playoff },
        { id: "out", label: "Eliminado", color: "danger", get: (entry) => entry.zones.out },
      ],
    },
    edition,
    footer: (data) => {
      const credits = [...new Map(data.sources.map((source) => [source.attribution, source])).values()];
      return `${credits.map((source) => `<a href="${S.safeUrl(source.origin)}">${escapeHtml(source.attribution || source.source_name)}</a>`).join("; ")}.`;
    },
    routes: [
      { id: "", label: "Início", render: home },
      { id: "chave", label: "Chave", render: bracket },
      { id: "fase-de-liga", label: "Fase de liga", render: leaguePhase },
      { id: "jogos", label: "Jogos", render: matches },
      { id: "metodologia", label: "Como calculamos", render: method, after: (data, main) => window.AIndaDaMetodo && window.AIndaDaMetodo.render(main.querySelector("#metodo-elo"), data.competition) },
    ],
  });
})();
