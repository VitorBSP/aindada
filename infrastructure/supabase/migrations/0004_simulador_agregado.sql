-- Simulador do usuário: agregado de todas as simulações e ressalvas C e F do Agente 06 (ADR-0015, 2026-11-07).
--
-- 1. sim_consensus usa todas as simulações completas de cada pessoa (Classificação e tabelas finais de Vencedor e
--    Placar exato), não só a mais recente. Cada pessoa pesa igual: primeiro a média das simulações dela, depois a
--    média entre pessoas. Continua com mínimo de 30 pessoas.
-- 2. sim_community conta só os palpites das pessoas: os jogos sorteados pelo modelo ficam de fora (ressalva F).
-- 3. O limite de 3 simulações por modo trava por pessoa, competição, temporada e modo antes de contar, para que
--    envios simultâneos não passem do limite (ressalva C).

create or replace function public.sim_lock_picks() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  locked_ids text[];
  old_picks jsonb := '{}'::jsonb;
  new_picks jsonb;
  sampled jsonb;
  final_order jsonb;
  match_id text;
  lock_at timestamptz;
  ranked jsonb;
begin
  if tg_op = 'UPDATE' then
    if (new.id, new.user_id, new.competition, new.season, new.mode) is distinct from (old.id, old.user_id, old.competition, old.season, old.mode) then
      raise exception 'uma simulação não muda de dono, competição, temporada nem modo' using errcode = '42501';
    end if;
    if jsonb_typeof(old.payload -> 'picks') = 'object' then old_picks := old.payload -> 'picks'; end if;
  else
    perform pg_advisory_xact_lock(hashtextextended(new.user_id::text || '|' || new.competition || '|' || new.season || '|' || new.mode, 0));
    if (select count(*) from sim_simulations
        where user_id = new.user_id and competition = new.competition and season = new.season and mode = new.mode) >= 3 then
      raise exception 'limite de 3 simulações por modo nesta temporada' using errcode = 'P0001';
    end if;
  end if;
  new.updated_at := now();

  if new.mode = 'classificacao' then
    if not public.sim_valid_order(new.competition, new.season, new.payload -> 'order', true) then
      raise exception 'ordem inválida ou impossível para %/%', new.competition, new.season using errcode = '22023';
    end if;
    select classificacao_locks_at into lock_at from sim_seasons where competition = new.competition and season = new.season;
    if lock_at is null or now() < lock_at then
      ranked := new.payload -> 'order';
    elsif tg_op = 'UPDATE' and jsonb_typeof(old.payload -> 'ranked_order') = 'array' then
      ranked := old.payload -> 'ranked_order';
    end if;
    new.payload := jsonb_build_object('order', new.payload -> 'order')
      || case when ranked is null then '{}'::jsonb else jsonb_build_object('ranked_order', ranked) end;
    return new;
  end if;

  select coalesce(array_agg(m.match_id), '{}') into locked_ids
  from sim_matches m
  where m.competition = new.competition and m.season = new.season
    and (m.status <> 'scheduled' or (m.kickoff_utc is not null and m.kickoff_utc <= now()));

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

create or replace function public.sim_community(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select 30 as min_users),
  votes as (
    -- Uma voz por pessoa e jogo: o palpite dela (não o sorteado pelo modelo) na simulação mais recente que tem
    -- esse jogo, com o Placar exato à frente.
    select distinct on (s.user_id, m.key) m.key as match_id, public.sim_pick_outcome(s.mode, m.value) as outcome
    from sim_simulations s cross join lateral jsonb_each(
      case when jsonb_typeof(s.payload -> 'picks') = 'object' then s.payload -> 'picks' else '{}'::jsonb end) m
    where s.competition = p_competition and s.season = p_season and s.mode in ('vencedor', 'placar')
      and public.sim_valid_pick(s.mode, m.value)
      and not (case when jsonb_typeof(s.payload -> 'sampled') = 'array' then s.payload -> 'sampled' else '[]'::jsonb end) ? m.key
    order by s.user_id, m.key, (s.mode = 'placar') desc, s.updated_at desc
  ),
  per_match as (
    select match_id, count(*) as users,
           count(*) filter (where outcome = 'H') as home,
           count(*) filter (where outcome = 'D') as draw,
           count(*) filter (where outcome = 'A') as away
    from votes group by match_id
  )
  select jsonb_build_object(
    'min_users', (select min_users from params),
    'rounding', 0.05,
    'matches', (select coalesce(jsonb_object_agg(match_id, jsonb_build_object(
        'users_at_least', (users / 10) * 10,
        'H', round(home::numeric / users * 20) / 20,
        'D', round(draw::numeric / users * 20) / 20,
        'A', round(away::numeric / users * 20) / 20)), '{}'::jsonb)
      from per_match, params where users >= min_users)
  );
$$;

create or replace function public.sim_consensus(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select 30 as min_users),
  tables as (
    select s.user_id,
           case when s.mode = 'classificacao' then s.payload -> 'order' else s.payload -> 'final_order' end as final_table
    from sim_simulations s
    where s.competition = p_competition and s.season = p_season
      and jsonb_typeof(case when s.mode = 'classificacao' then s.payload -> 'order' else s.payload -> 'final_order' end) = 'array'
  ),
  per_person as (
    select t.user_id, o.club_id, avg(o.ordinality) as average_position,
           avg(case when o.ordinality = 1 then 1 else 0 end) as champion,
           avg(case when o.ordinality > jsonb_array_length(t.final_table) - 4 then 1 else 0 end) as relegated
    from tables t cross join lateral jsonb_array_elements_text(t.final_table) with ordinality as o(club_id, ordinality)
    group by t.user_id, o.club_id
  ),
  positions as (
    select club_id, avg(average_position) as average_position, avg(champion) as champion, avg(relegated) as relegated
    from per_person group by club_id
  ),
  total as (select count(distinct user_id) as users, (select count(*) from tables) as simulations from tables)
  select jsonb_build_object(
    'min_users', (select min_users from params),
    'users_at_least', (select (users / 10) * 10 from total),
    'simulations_at_least', (select (simulations / 10) * 10 from total),
    'clubs', case when (select users from total) >= (select min_users from params) then (
      select coalesce(jsonb_agg(jsonb_build_object(
          'club_id', club_id, 'average_position', round(average_position, 1),
          'champion', round(champion * 20) / 20, 'relegated', round(relegated * 20) / 20)
        order by average_position, club_id), '[]'::jsonb)
      from positions) else '[]'::jsonb end
  );
$$;

revoke all on function public.sim_lock_picks() from public, anon, authenticated;
revoke all on function public.sim_community(text, int) from public;
revoke all on function public.sim_consensus(text, int) from public;
grant execute on function public.sim_community(text, int) to anon, authenticated;
grant execute on function public.sim_consensus(text, int) to anon, authenticated;
