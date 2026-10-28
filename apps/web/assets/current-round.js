/* Aba da rodada da home (ADR-0009, Decisão 3; textos e layout da D-037, versão enxuta).
   Só apresenta o que vem em current-round.json e predictions.json: não calcula chance nem decide qual
   rodada mostrar. O relógio do aparelho só escolhe a aba padrão e troca "a jogar" por "aguardando placar". */
(function () {
  "use strict";

  const TIME_ZONE = "America/Sao_Paulo";
  const HOUR_MS = 3600000;
  const OVERDUE_HOURS = 4;
  const NOISE_FLOOR = 0.01;
  const MOVEMENT_MIN = 0.02;
  const MOVEMENTS_SHOWN = 6;
  const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
  const STATES = { in_progress: "Rodada atual", finished: "Última rodada" };
  const METRICS = [
    { key: "title", noun: "título", head: "Título" },
    { key: "top4", noun: "G4", head: "G4" },
    { key: "relegation", noun: "rebaixamento", head: "Queda" },
  ];
  const FEMININE_CLUBS = new Set(["chapecoense"]);
  const MINUS = "−";

  const isNumber = (value) => typeof value === "number" && Number.isFinite(value);
  const isProbability = (value) => isNumber(value) && value >= 0 && value <= 1;
  const parseStamp = (value) => {
    if (typeof value !== "string") return null;
    const stamp = Date.parse(value);
    return Number.isNaN(stamp) ? null : stamp;
  };
  const hasScore = (match) => match.status === "finished" && Number.isInteger(match.home_goals) && Number.isInteger(match.away_goals);
  const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

  const dayParts = new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
  const clockParts = new Intl.DateTimeFormat("pt-BR", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

  function brasiliaDay(stamp) {
    const parts = Object.fromEntries(dayParts.formatToParts(new Date(stamp)).map((part) => [part.type, part.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  const brasiliaClock = (stamp) => clockParts.format(new Date(stamp));

  function addDays(isoDay, days) {
    const date = new Date(`${isoDay}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString().slice(0, 10);
  }

  const longDay = (isoDay) => new Date(`${isoDay}T12:00:00Z`).toLocaleDateString("pt-BR", { timeZone: "UTC", weekday: "long", day: "numeric", month: "long" });
  const shortWeekdayDay = (stamp) => new Date(stamp).toLocaleDateString("pt-BR", { timeZone: TIME_ZONE, weekday: "long", day: "numeric", month: "long" }).replace("-feira", "");

  function validBaseline(baseline) {
    if (!baseline || typeof baseline !== "object") return null;
    if (!baseline.teams || typeof baseline.teams !== "object") return null;
    if (!isNumber(baseline.n_simulations) || baseline.n_simulations <= 0 || typeof baseline.model_version !== "string") return null;
    return baseline;
  }

  /* Junta current-round.json ao snapshot. null quando não há rodada ou o arquivo não confere:
     nesse caso a aba não aparece e a home fica como antes (D-037, item 3). */
  function prepare(snapshot, payload) {
    if (!snapshot || !payload || typeof payload !== "object") return null;
    const round = payload.round;
    if (!round || typeof round !== "object" || !STATES[round.state]) return null;
    if (!Number.isInteger(round.round_number) || round.round_number < 1 || !Array.isArray(round.match_ids)) return null;
    if (payload.model_version !== snapshot.model.model_version || payload.data_version !== snapshot.data.version) return null;
    const byId = new Map(snapshot.matches.map((match) => [match.match_id, match]));
    const listedIds = new Set(round.match_ids);
    const rescheduledIds = new Set((Array.isArray(round.rescheduled_match_ids) ? round.rescheduled_match_ids : []).filter((matchId) => !listedIds.has(matchId)));
    const listed = round.match_ids.map((matchId) => byId.get(matchId)).filter(Boolean);
    const rescheduled = [...rescheduledIds].map((matchId) => byId.get(matchId)).filter(Boolean);
    if (!listed.length && !rescheduled.length) return null;
    return {
      number: round.round_number,
      inProgress: round.state === "in_progress",
      label: STATES[round.state],
      endsOn: typeof round.ends_on === "string" && ISO_DAY.test(round.ends_on) ? round.ends_on : null,
      updatedAt: parseStamp(payload.updated_at) ?? parseStamp(snapshot.generated_at),
      listed,
      rescheduled,
      rescheduledIds,
      baseline: validBaseline(round.baseline),
    };
  }

  /* Regra da aba padrão da D-037: rodada em andamento, ou encerrada até 23:59 (Brasília) do dia
     seguinte ao do último jogo encerrado. */
  function opensByDefault(info, now) {
    if (!info) return false;
    if (info.inProgress) return true;
    const finishedDays = info.listed.filter(hasScore).map((match) => match.match_date).filter((day) => ISO_DAY.test(day)).sort();
    const lastDay = finishedDays.length ? finishedDays[finishedDays.length - 1] : info.endsOn;
    return Boolean(lastDay) && brasiliaDay(now) <= addDays(lastDay, 1);
  }

  function matchState(match, info, now) {
    if (hasScore(match)) return { kind: "finished", text: "encerrado" };
    if (info.rescheduledIds.has(match.match_id) || match.status === "postponed" || match.status === "cancelled") return { kind: "postponed", text: "adiado" };
    const kickoff = parseStamp(match.kickoff_utc);
    if (kickoff !== null && now >= kickoff) return { kind: "waiting", text: "aguardando placar", overdue: now - kickoff >= OVERDUE_HOURS * HOUR_MS };
    return { kind: "upcoming", text: "a jogar" };
  }

  function createRenderer(helpers) {
    const { escapeHtml, pct, crest, clubLink, nameOf, formatDate } = helpers;
    const clubName = (clubId) => escapeHtml(nameOf(clubId));
    const ofClub = (clubId) => `${FEMININE_CLUBS.has(clubId) ? "da" : "do"} ${clubName(clubId)}`;

    function kickoffText(match) {
      const kickoff = parseStamp(match.kickoff_utc);
      return kickoff === null ? "a definir" : brasiliaClock(kickoff);
    }

    function postponedMeta(match, info) {
      if (match.status === "postponed" || match.status === "cancelled" || !info.rescheduledIds.has(match.match_id)) return "Data a definir.";
      if (!ISO_DAY.test(match.match_date)) return "Data a definir.";
      const kickoff = parseStamp(match.kickoff_utc);
      return `Remarcado para ${escapeHtml(longDay(match.match_date))}${kickoff === null ? "" : `, às ${brasiliaClock(kickoff)}`}.`;
    }

    function matchRow(match, info, now) {
      const status = matchState(match, info, now);
      const meta = [];
      if (Number.isInteger(match.round) && match.round !== info.number) meta.push(`Jogo atrasado da rodada ${match.round}.`);
      let center = "×";
      let spoken = `<span class="visually-hidden">contra</span>`;
      if (status.kind === "finished") {
        center = `${match.home_goals} × ${match.away_goals}`;
        spoken = `<span class="visually-hidden">Placar final: ${clubName(match.home_id)} ${match.home_goals}, ${clubName(match.away_id)} ${match.away_goals}.</span>`;
        if (info.rescheduledIds.has(match.match_id) && ISO_DAY.test(match.match_date)) meta.push(`Remarcado e disputado em ${escapeHtml(longDay(match.match_date))}.`);
      } else if (status.kind === "postponed") {
        center = "adiado";
        spoken = "";
        meta.push(postponedMeta(match, info));
      } else if (status.kind === "waiting") {
        meta.push(status.overdue
          ? "O placar ainda não chegou da fonte de dados. Até chegar, as chances tratam este jogo como não disputado."
          : `Começou às ${kickoffText(match)}. O placar entra aqui depois do fim do jogo, com atraso.`);
      }
      const statusClass = status.kind === "postponed" || status.overdue ? " rm-status-alert" : "";
      return `<li class="round-match is-${status.kind}">
        <span class="rm-time">${kickoffText(match)}</span><span class="rm-status${statusClass}">${status.text}</span>
        <span class="rm-home">${clubLink(match.home_id, 20)}</span>
        <span class="rm-center" aria-hidden="true">${center}</span>${spoken}
        <span class="rm-away">${clubLink(match.away_id, 20, true)}</span>
        ${meta.length ? `<p class="rm-meta">${meta.join(" ")}</p>` : ""}
      </li>`;
    }

    function byKickoff(left, right) {
      const a = parseStamp(left.kickoff_utc), b = parseStamp(right.kickoff_utc);
      if (a === null && b === null) return 0;
      if (a === null) return 1;
      if (b === null) return -1;
      return a - b;
    }

    function matchesBlock(info, now) {
      const days = new Map();
      info.listed.forEach((match) => {
        const day = ISO_DAY.test(match.match_date) ? match.match_date : "";
        if (!days.has(day)) days.set(day, []);
        days.get(day).push(match);
      });
      const sections = [...days.keys()].sort().map((day) => {
        const heading = day ? escapeHtml(capitalize(longDay(day))) : "Data a definir";
        const anchor = `dia-${day || "sem-data"}`;
        const rows = days.get(day).slice().sort(byKickoff).map((match) => matchRow(match, info, now)).join("");
        return `<section class="round-day" aria-labelledby="${anchor}"><h3 id="${anchor}">${heading}</h3><ol class="round-matches">${rows}</ol></section>`;
      });
      if (info.rescheduled.length) {
        const rows = info.rescheduled.slice().sort((left, right) => String(left.match_date).localeCompare(String(right.match_date)) || byKickoff(left, right))
          .map((match) => matchRow(match, info, now)).join("");
        sections.push(`<section class="round-day" aria-labelledby="dia-fora-da-rodada"><h3 id="dia-fora-da-rodada">Fora das datas da rodada</h3><ol class="round-matches">${rows}</ol></section>`);
      }
      return `<h2>Jogos</h2><p class="note">Horários de Brasília.</p>${sections.join("")}`;
    }

    function noise(before, now, baseline, nNow) {
      return 2 * Math.sqrt(before * (1 - before) / baseline.n_simulations + now * (1 - now) / nNow);
    }

    /* Variações por clube e disputa. Os números vêm prontos do export; aqui só se subtrai e se aplica o
       limiar de ruído da D-037, sem alterar valor nenhum. */
    function comparison(info, snapshot) {
      const baseline = info.baseline;
      if (!baseline) return null;
      const comparable = baseline.model_version === snapshot.model.model_version;
      const rows = [...snapshot.teams].sort((left, right) => left.current_position - right.current_position).map((team) => {
        const before = baseline.teams[team.club_id] || {};
        const cells = METRICS.map((metric) => {
          const now = team[metric.key];
          const start = isProbability(before[metric.key]) ? before[metric.key] : null;
          const delta = start === null || !isNumber(now) ? null : now - start;
          const shown = comparable && delta !== null && Math.abs(delta) >= Math.max(NOISE_FLOOR, noise(start, now, baseline, snapshot.n_simulations));
          return { metric, now, start, delta, shown };
        });
        return { team, cells };
      });
      const movements = rows.flatMap((row) => row.cells.filter((cell) => cell.shown).map((cell) => ({ clubId: row.team.club_id, ...cell })))
        .sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta));
      return { comparable, rows, movements };
    }

    const signed = (delta) => `${delta > 0 ? "+" : MINUS}${Math.round(Math.abs(delta) * 100)}`;
    const changeClass = (metric, delta) => ((metric.key === "relegation") === (delta > 0) ? "change-down" : "change-up");

    function biggestChange(compared, inProgress) {
      if (!compared || !compared.comparable) return "";
      const top = compared.movements[0];
      if (!top) return inProgress ? "Até agora, nenhuma chance mudou além do ruído das simulações." : "Nenhuma chance mudou além do ruído das simulações nesta rodada.";
      const fact = `${ofClub(top.clubId)}: chance de ${top.metric.noun} de ${pct(top.start)} para ${pct(top.now)}.`;
      return inProgress ? `Até agora, a maior mudança é ${fact}` : `A maior mudança foi ${fact}`;
    }

    function headline(info, compared, anyFinished) {
      const own = info.listed.filter((match) => match.round === info.number);
      const postponed = own.filter((match) => matchState(match, info, 0).kind === "postponed").length
        + info.rescheduled.filter((match) => !hasScore(match)).length;
      const counted = own.filter((match) => matchState(match, info, 0).kind !== "postponed");
      const finished = counted.filter(hasScore).length;
      if (!info.inProgress) {
        const title = postponed ? `Rodada ${info.number} encerrada, com ${postponed} ${postponed === 1 ? "jogo adiado" : "jogos adiados"}` : `Rodada ${info.number} encerrada`;
        return { title, lede: biggestChange(compared, false) };
      }
      if (!finished) {
        const lede = info.baseline
          ? "As chances abaixo são as do início da rodada. Cada placar entra depois do apito final, com atraso."
          : "Cada placar entra depois do apito final, com atraso.";
        return { title: `Rodada ${info.number}: nenhum jogo encerrado ainda`, lede: anyFinished ? biggestChange(compared, true) || lede : lede };
      }
      return { title: `Rodada ${info.number}: ${finished} de ${counted.length} jogos encerrados`, lede: biggestChange(compared, true) };
    }

    function updateBlock(info) {
      const stamp = info.updatedAt;
      const when = stamp === null ? "" : `<p class="note round-updated"><strong>Atualizado às ${brasiliaClock(stamp)} de ${escapeHtml(shortWeekdayDay(stamp))} (horário de Brasília).</strong></p>`;
      const detail = info.inProgress
        ? "O site não acompanha os jogos ao vivo. Cada placar entra aqui depois do apito final, em geral de 30 minutos a 1 hora depois, quando a fonte de dados registra o resultado e as simulações são refeitas. Recarregue a página para ver a atualização mais recente."
        : "Esta rodada não muda mais, a não ser que a fonte corrija um placar.";
      return `${when}<p class="note">${detail}</p>`;
    }

    function comparisonNote(info, compared, snapshot, anyFinished) {
      const baseline = info.baseline;
      if (!compared.comparable) {
        return `O modelo mudou durante a rodada (versão ${escapeHtml(baseline.model_version)} para ${escapeHtml(snapshot.model.model_version)}). Comparar as duas daria diferenças que não vêm dos jogos, então mostramos só as chances de agora.`;
      }
      if (!anyFinished) return "Nenhum jogo da rodada terminou ainda, então as chances não mudaram.";
      if (baseline.reconstructed === false) {
        const day = typeof baseline.reference_date === "string" && ISO_DAY.test(baseline.reference_date) ? formatDate(baseline.reference_date) : "";
        return `Início da rodada = chances publicadas${day ? ` em ${escapeHtml(day)}` : ""}, antes do primeiro jogo, com o mesmo modelo de agora.`;
      }
      return `Início da rodada = chances com os resultados conhecidos antes do primeiro jogo, recalculadas com o mesmo modelo de agora (versão ${escapeHtml(snapshot.model.model_version)}). Não é necessariamente o que o site mostrava naquela hora. A diferença vem dos jogos encerrados desde então.`;
    }

    function movementList(compared) {
      const items = compared.movements.filter((item) => Math.abs(item.delta) >= MOVEMENT_MIN).slice(0, MOVEMENTS_SHOWN);
      if (!items.length) return "";
      return `<ul class="changes">${items.map((item, index) => {
        const unit = index === 0 ? "pontos percentuais" : `<abbr title="pontos percentuais">p.p.</abbr>`;
        return `<li>${clubLink(item.clubId, 20)}: ${item.metric.noun} de ${pct(item.start)} para ${pct(item.now)} (<span class="${changeClass(item.metric, item.delta)}">${signed(item.delta)} ${unit}</span>)</li>`;
      }).join("")}</ul>`;
    }

    function tableCell(cell, withVariation) {
      if (!isNumber(cell.now)) return "<td>–</td>";
      if (withVariation && cell.start === 0 && cell.now === 0) return "<td>–</td>";
      let variation = "";
      if (withVariation && cell.start !== null) {
        variation = cell.shown
          ? `<span class="range"><span class="visually-hidden">variação: </span><span class="${changeClass(cell.metric, cell.delta)}">${signed(cell.delta)}</span></span>`
          : `<span class="range"><span aria-hidden="true">=</span><span class="visually-hidden">sem variação além do ruído</span></span>`;
      }
      return `<td>${pct(cell.now)}${variation}</td>`;
    }

    function changesBlock(info, compared, snapshot, anyFinished) {
      if (!compared) return "";
      const withVariation = compared.comparable && anyFinished;
      const rows = compared.rows.map((row) => {
        const team = row.team;
        const link = `<a class="club-cell" href="#/clubes/${encodeURIComponent(team.club_id)}" title="${escapeHtml(team.name)}">${crest(team.club_id, 20)}<span>${escapeHtml(team.short_name || team.name)}</span></a>`;
        return `<tr><th scope="row" class="left club">${link}</th>${row.cells.map((cell) => tableCell(cell, withVariation)).join("")}</tr>`;
      }).join("");
      const legend = withVariation
        ? `<p class="note">Embaixo de cada chance, a variação desde o início da rodada, em pontos percentuais. "=" quando a diferença fica dentro do ruído das simulações.</p>`
        : "";
      return `<h2>O que mudou desde o início da rodada</h2>
        <p class="note">${comparisonNote(info, compared, snapshot, anyFinished)}</p>
        ${withVariation ? movementList(compared) : ""}
        <div class="table-scroll"><table class="round-changes">
          <caption>Chances no início da rodada e agora</caption>
          <thead><tr><th scope="col" class="left">Clube</th>${METRICS.map((metric) => `<th scope="col">${metric.head}</th>`).join("")}</tr></thead>
          <tbody>${rows}</tbody></table></div>
        ${legend}`;
    }

    function render(info, snapshot, now, overdueWarning, belowLead = false) {
      const anyFinished = info.listed.some(hasScore) || info.rescheduled.some(hasScore);
      const compared = comparison(info, snapshot);
      const { title, lede } = headline(info, compared, anyFinished);
      const analysis = info.inProgress ? "" : `<p class="note"><a href="#/rodadas/${info.number}">Análise completa da rodada ${info.number} em Rodada a rodada</a> (recalculada com os resultados até a véspera de cada rodada; os números podem diferir um pouco dos daqui).</p>`;
      return `${belowLead ? `<h2 class="race-heading">${title}</h2>` : `<h1>${title}</h1>`}
        ${lede ? `<p class="lede">${lede}</p>` : ""}
        <div class="round-update">${updateBlock(info)}${overdueWarning}</div>
        ${matchesBlock(info, now)}
        ${changesBlock(info, compared, snapshot, anyFinished)}
        ${analysis}`;
    }

    return { render };
  }

  window.CurrentRound = { prepare, opensByDefault, createRenderer, brasiliaDay };
})();
