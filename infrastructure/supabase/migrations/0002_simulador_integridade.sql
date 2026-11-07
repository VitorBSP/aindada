-- Simulador do usuário: correções do parecer do Agente 06 (ADR-0015, 2026-11-07).
--
-- 1. Uma simulação não muda de dono, competição, temporada nem modo depois de criada; cada modo guarda só as
--    próprias chaves (Classificação: order e ranked_order; Vencedor e Placar: picks). Antes, trocar o modo de uma
--    linha herdava palpites forjados de jogos já encerrados.
-- 2. Pontuação e média validam o formato antes de converter para número: um palpite malformado não derruba mais
--    sim_ranking, sim_my_scores nem sim_community.
-- 3. Média dos visitantes: cada pessoa conta uma vez por jogo (vale o Placar, se houver, senão o Vencedor), com
--    mínimo de 20 pessoas, frações arredondadas a 5 pontos percentuais e contagem em faixas de 10.
-- 4. Jogo que já travou não destrava se o horário mudar depois (adiamento ou interrupção).

-- ---------------------------------------------------------------- 1. Chaves imutáveis e payload por modo

create or replace function public.sim_lock_picks() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  locked_ids text[];
  old_picks jsonb := '{}'::jsonb;
  new_picks jsonb;
  match_id text;
  lock_at timestamptz;
  ranked jsonb;
begin
  if tg_op = 'UPDATE' then
    if (new.user_id, new.competition, new.season, new.mode) is distinct from (old.user_id, old.competition, old.season, old.mode) then
      raise exception 'uma simulação não muda de dono, competição, temporada nem modo' using errcode = '42501';
    end if;
    if jsonb_typeof(old.payload -> 'picks') = 'object' then old_picks := old.payload -> 'picks'; end if;
  end if;
  new.updated_at := now();

  if new.mode = 'classificacao' then
    if jsonb_typeof(new.payload -> 'order') is distinct from 'array'
       or (select count(*) from sim_standings where competition = new.competition and season = new.season)
          <> jsonb_array_length(new.payload -> 'order')
       or exists (
         select 1 from jsonb_array_elements(new.payload -> 'order') o(club)
         left join sim_standings st on st.competition = new.competition and st.season = new.season and st.club_id = o.club #>> '{}'
         where jsonb_typeof(o.club) <> 'string' or st.club_id is null)
       or (select count(distinct o) from jsonb_array_elements_text(new.payload -> 'order') o) <> jsonb_array_length(new.payload -> 'order')
    then
      raise exception 'ordem inválida para %/%', new.competition, new.season using errcode = '22023';
    end if;
    -- A ordem continua editável para comparar; o ranking usa ranked_order, a última ordem salva antes da trava.
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
  new.payload := jsonb_build_object('picks', new_picks);
  return new;
end;
$$;

-- ---------------------------------------------------------------- 2. Formato validado antes de converter

create or replace function public.sim_valid_pick(mode text, pick jsonb) returns boolean
language sql immutable set search_path = public as $$
  select case
    when mode = 'vencedor' then jsonb_typeof(pick) = 'string' and pick #>> '{}' in ('H', 'D', 'A')
    when mode = 'placar' then jsonb_typeof(pick) = 'array' and jsonb_array_length(pick) = 2
      and jsonb_typeof(pick -> 0) = 'number' and jsonb_typeof(pick -> 1) = 'number'
      and pick ->> 0 ~ '^[0-9]{1,2}$' and pick ->> 1 ~ '^[0-9]{1,2}$'
    else false
  end;
$$;

-- Saída do palpite como resultado (H, D, A), ou null se o formato não vale.
create or replace function public.sim_pick_outcome(mode text, pick jsonb) returns text
language sql immutable set search_path = public as $$
  select case
    when not public.sim_valid_pick(mode, pick) then null
    when mode = 'vencedor' then pick #>> '{}'
    else case sign((pick ->> 0)::int - (pick ->> 1)::int) when 1 then 'H' when -1 then 'A' else 'D' end
  end;
$$;

create or replace function public.sim_match_points(mode text, pick jsonb, home_goals int, away_goals int)
returns int language sql immutable set search_path = public as $$
  select case
    when not public.sim_valid_pick(mode, pick) or home_goals is null or away_goals is null then 0
    when mode = 'vencedor' then
      case when pick #>> '{}' = (case when home_goals > away_goals then 'H' when home_goals < away_goals then 'A' else 'D' end)
           then 1 else 0 end
    when (pick ->> 0)::int = home_goals and (pick ->> 1)::int = away_goals then 5
    when sign((pick ->> 0)::int - (pick ->> 1)::int) = sign(home_goals - away_goals)
         and (pick ->> 0)::int - (pick ->> 1)::int = home_goals - away_goals then 3
    when sign((pick ->> 0)::int - (pick ->> 1)::int) = sign(home_goals - away_goals) then 2
    else 0
  end;
$$;

-- ---------------------------------------------------------------- 3. Média dos visitantes

create or replace function public.sim_community(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select 20 as min_users),
  votes as (
    -- Uma voz por pessoa e jogo: o Placar exato, se houver, senão o Vencedor.
    select distinct on (s.user_id, m.key) m.key as match_id, public.sim_pick_outcome(s.mode, m.value) as outcome
    from sim_simulations s cross join lateral jsonb_each(
      case when jsonb_typeof(s.payload -> 'picks') = 'object' then s.payload -> 'picks' else '{}'::jsonb end) m
    where s.competition = p_competition and s.season = p_season and s.mode in ('vencedor', 'placar')
      and public.sim_valid_pick(s.mode, m.value)
    order by s.user_id, m.key, (s.mode = 'placar') desc
  ),
  per_match as (
    select match_id, count(*) as users,
           count(*) filter (where outcome = 'H') as home,
           count(*) filter (where outcome = 'D') as draw,
           count(*) filter (where outcome = 'A') as away
    from votes group by match_id
  ),
  positions as (
    select o.club_id, avg(o.ordinality) as average_position,
           avg(case when o.ordinality = 1 then 1 else 0 end) as champion,
           avg(case when o.ordinality > jsonb_array_length(s.payload -> 'order') - 4 then 1 else 0 end) as relegated,
           count(*) as users
    from sim_simulations s
    cross join lateral jsonb_array_elements_text(s.payload -> 'order') with ordinality as o(club_id, ordinality)
    where s.competition = p_competition and s.season = p_season and s.mode = 'classificacao'
      and jsonb_typeof(s.payload -> 'order') = 'array'
    group by o.club_id
  )
  select jsonb_build_object(
    'min_users', (select min_users from params),
    'rounding', 0.05,
    'matches', (select coalesce(jsonb_object_agg(match_id, jsonb_build_object(
        'users_at_least', (users / 10) * 10,
        'H', round(home::numeric / users * 20) / 20,
        'D', round(draw::numeric / users * 20) / 20,
        'A', round(away::numeric / users * 20) / 20)), '{}'::jsonb)
      from per_match, params where users >= min_users),
    'clubs', (select coalesce(jsonb_object_agg(club_id, jsonb_build_object(
        'users_at_least', (users / 10) * 10, 'average_position', round(average_position * 2) / 2,
        'champion', round(champion * 20) / 20, 'relegated', round(relegated * 20) / 20)), '{}'::jsonb)
      from positions, params where users >= min_users)
  );
$$;

revoke all on function public.sim_valid_pick(text, jsonb) from public, anon;
revoke all on function public.sim_pick_outcome(text, jsonb) from public, anon;
revoke all on function public.sim_match_points(text, jsonb, int, int) from public, anon;
revoke all on function public.sim_lock_picks() from public, anon, authenticated;
revoke all on function public.sim_community(text, int) from public;
grant execute on function public.sim_community(text, int) to anon, authenticated;

-- ---------------------------------------------------------------- 4. Trava que não volta atrás

create or replace function public.sim_keep_match_lock() returns trigger
language plpgsql set search_path = public as $$
begin
  new.updated_at := now();
  if old.kickoff_utc is not null and old.kickoff_utc <= now()
     and (new.kickoff_utc is null or new.kickoff_utc > old.kickoff_utc) then
    new.kickoff_utc := old.kickoff_utc;
  end if;
  return new;
end;
$$;
revoke all on function public.sim_keep_match_lock() from public, anon, authenticated;

drop trigger if exists sim_keep_match_lock on public.sim_matches;
create trigger sim_keep_match_lock before update on public.sim_matches
  for each row execute function public.sim_keep_match_lock();
