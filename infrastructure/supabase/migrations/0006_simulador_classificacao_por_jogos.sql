-- Simulador do usuário: ranking da Classificação já nesta temporada e pontuação nova (ADR-0015, versão 5, pedidos do
-- dono em 2026-11-07).
--
-- 1. Sai a trava da temporada (classificacao_locks_at) para a Classificação: toda ordem salva conta para o ranking.
-- 2. Classificação: 3 por posição exata, 1 a uma posição, 10 pelo campeão, 3 por clube do G4 acertado (em qualquer
--    ordem) e 5 por rebaixado acertado: máximo 102. Deflator: a pontuação é multiplicada pelos jogos que ainda faltavam
--    quando a simulação foi salva pela última vez (jogos não cancelados com a trava depois de updated_at; a simulação
--    fecha no jogo seguinte, 0005, então o número não muda). O banco guarda pontos × jogos que faltavam (inteiro); a
--    página divide pelo total de jogos da temporada para mostrar o valor deflacionado (mesma ordem no ranking). Usa a
--    tabela de hoje e é provisória até o fim da temporada, como na página. scored_picks traz os jogos que faltavam.
-- 3. Vencedor: 3 por vitória certa e 5 por empate certo. Placar exato: exato 10; vencedor e gols do vencedor 7;
--    vencedor e diferença 6; vencedor e gols do perdedor 5; empate certo (sem o placar) 5; só o vencedor 3; invertido 2.
--    O máximo de cada palpite passa a depender dele (sim_pick_max): Vencedor 3 ou 5 (empate), Placar exato 10.
-- As colunas de sim_scores não mudam (create or replace view), então sim_ranking, sim_my_scores e
-- sim_notification_list continuam valendo.

create or replace function public.sim_match_points(mode text, pick jsonb, home_goals int, away_goals int)
returns int language sql immutable set search_path = public as $$
  with p as (
    select case when public.sim_valid_pick(mode, pick) and mode = 'placar' then (pick ->> 0)::int end as ph,
           case when public.sim_valid_pick(mode, pick) and mode = 'placar' then (pick ->> 1)::int end as pa
  )
  select case
    when not public.sim_valid_pick(mode, pick) or home_goals is null or away_goals is null then 0
    when mode = 'vencedor' then
      case when pick #>> '{}' <> (case when home_goals > away_goals then 'H' when home_goals < away_goals then 'A' else 'D' end) then 0
           when home_goals = away_goals then 5 else 3 end
    when ph = home_goals and pa = away_goals then 10
    when sign(ph - pa) = sign(home_goals - away_goals) and home_goals <> away_goals
         and greatest(ph, pa) = greatest(home_goals, away_goals) then 7
    when sign(ph - pa) = sign(home_goals - away_goals) and home_goals <> away_goals and ph - pa = home_goals - away_goals then 6
    when sign(ph - pa) = sign(home_goals - away_goals) and home_goals <> away_goals
         and least(ph, pa) = least(home_goals, away_goals) then 5
    when ph = pa and home_goals = away_goals then 5
    when sign(ph - pa) = sign(home_goals - away_goals) then 3
    when ph <> pa and ph = away_goals and pa = home_goals then 2
    else 0
  end
  from p;
$$;

-- Máximo de um palpite: o que ele vale se o resultado sair como apostado.
create or replace function public.sim_pick_max(mode text, pick jsonb) returns int
language sql immutable set search_path = public as $$
  select case when not public.sim_valid_pick(mode, pick) then 0
              when mode = 'placar' then 10
              when pick #>> '{}' = 'D' then 5 else 3 end;
$$;

create or replace function public.sim_lock_picks() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  locked_ids text[];
  old_picks jsonb := '{}'::jsonb;
  new_picks jsonb;
  sampled jsonb;
  final_order jsonb;
  match_id text;
  event_start timestamptz := public.sim_event_start(new.competition, new.season);
begin
  if tg_op = 'UPDATE' then
    if (new.id, new.user_id, new.competition, new.season, new.mode, new.created_at)
       is distinct from (old.id, old.user_id, old.competition, old.season, old.mode, old.created_at) then
      raise exception 'uma simulação não muda de dono, competição, temporada, modo nem data de criação' using errcode = '42501';
    end if;
    if old.created_at < event_start then
      raise exception 'simulação fechada: um jogo começou depois que ela foi salva' using errcode = 'P0001';
    end if;
    if jsonb_typeof(old.payload -> 'picks') = 'object' then old_picks := old.payload -> 'picks'; end if;
  else
    new.created_at := now();
    perform pg_advisory_xact_lock(hashtextextended(new.user_id::text || '|' || new.competition || '|' || new.season, 0));
    if (select count(*) from sim_simulations
        where user_id = new.user_id and competition = new.competition and season = new.season
          and created_at >= event_start) >= 10 then
      raise exception 'limite de 10 simulações por pessoa até o próximo jogo' using errcode = 'P0001';
    end if;
  end if;
  new.updated_at := now();

  if new.mode = 'classificacao' then
    if not public.sim_valid_order(new.competition, new.season, new.payload -> 'order', true) then
      raise exception 'ordem inválida ou impossível para %/%', new.competition, new.season using errcode = '22023';
    end if;
    -- Sem trava da temporada: toda ordem vale para o ranking, pesada pelos jogos que faltavam (sim_scores).
    new.payload := jsonb_build_object('order', new.payload -> 'order', 'ranked_order', new.payload -> 'order');
    return new;
  end if;

  select coalesce(array_agg(m.match_id), '{}') into locked_ids
  from sim_matches m
  where m.competition = new.competition and m.season = new.season
    and (m.status in ('finished', 'cancelled') or (m.kickoff_utc is not null and m.kickoff_utc - public.sim_lock_margin() <= now()));

  select coalesce(jsonb_object_agg(e.key, e.value), '{}'::jsonb) into new_picks
  from jsonb_each(case when jsonb_typeof(new.payload -> 'picks') = 'object' then new.payload -> 'picks' else '{}'::jsonb end) e
  join sim_matches m on m.competition = new.competition and m.season = new.season and m.match_id = e.key
  where public.sim_valid_pick(new.mode, e.value);
  foreach match_id in array locked_ids loop
    if old_picks ? match_id and public.sim_valid_pick(new.mode, old_picks -> match_id) then
      new_picks := jsonb_set(new_picks, array[match_id], old_picks -> match_id);
    else
      new_picks := new_picks - match_id;
    end if;
  end loop;

  select coalesce(jsonb_agg(s.value order by s.value), '[]'::jsonb) into sampled
  from jsonb_array_elements_text(case when jsonb_typeof(new.payload -> 'sampled') = 'array' then new.payload -> 'sampled' else '[]'::jsonb end) s
  where new_picks ? s.value;
  final_order := case when public.sim_valid_order(new.competition, new.season, new.payload -> 'final_order', false)
                      then new.payload -> 'final_order' end;

  new.payload := jsonb_build_object('picks', new_picks, 'sampled', sampled)
    || case when final_order is null then '{}'::jsonb else jsonb_build_object('final_order', final_order) end;
  return new;
end;
$$;

create or replace view public.sim_scores with (security_invoker = false) as
  select s.id, s.user_id, s.competition, s.season, s.mode,
         sum(public.sim_match_points(s.mode, s.payload -> 'picks' -> m.match_id, m.home_goals, m.away_goals))::int as points,
         sum(public.sim_pick_max(s.mode, s.payload -> 'picks' -> m.match_id))::int as max_points,
         count(*) filter (where public.sim_match_points(s.mode, s.payload -> 'picks' -> m.match_id, m.home_goals, m.away_goals)
                          = public.sim_pick_max(s.mode, s.payload -> 'picks' -> m.match_id))::int as exact_hits,
         count(*)::int as scored_picks
  from public.sim_simulations s
  join public.sim_matches m
    on m.competition = s.competition and m.season = s.season and m.status = 'finished'
   and s.payload -> 'picks' ? m.match_id
  where s.mode in ('vencedor', 'placar')
  group by s.id, s.user_id, s.competition, s.season, s.mode
  union all
  select s.id, s.user_id, s.competition, s.season, s.mode,
         ((sum(case abs(st.position - o.ordinality::int) when 0 then 3 when 1 then 1 else 0 end)
           + max(case when o.ordinality = 1 and st.position = 1 then 10 else 0 end)
           + 3 * count(*) filter (where o.ordinality <= 4 and st.position <= 4)
           + 5 * count(*) filter (where o.ordinality > jsonb_array_length(s.payload -> 'order') - 4
                                    and st.position > jsonb_array_length(s.payload -> 'order') - 4)) * max(w.remaining))::int,
         (102 * max(w.remaining))::int,
         count(*) filter (where st.position = o.ordinality)::int,
         max(w.remaining)::int
  from public.sim_simulations s
  cross join lateral (
    select count(*) filter (where m.status <> 'cancelled'
                              and (m.kickoff_utc is null or m.kickoff_utc - public.sim_lock_margin() > s.updated_at)) as remaining
    from public.sim_matches m where m.competition = s.competition and m.season = s.season
  ) w
  cross join lateral jsonb_array_elements_text(s.payload -> 'order') with ordinality as o(club_id, ordinality)
  join public.sim_standings st on st.competition = s.competition and st.season = s.season and st.club_id = o.club_id
  where s.mode = 'classificacao' and jsonb_typeof(s.payload -> 'order') = 'array'
  group by s.id, s.user_id, s.competition, s.season, s.mode;

revoke all on public.sim_scores from anon, authenticated;
revoke all on function public.sim_lock_picks() from public, anon, authenticated;
revoke all on function public.sim_pick_max(text, jsonb) from public, anon, authenticated;
