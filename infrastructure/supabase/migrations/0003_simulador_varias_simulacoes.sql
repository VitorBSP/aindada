-- Simulador do usuário, versão 2 (ADR-0015, pedido do dono em 2026-11-07).
--
-- 1. Várias simulações por pessoa, cada uma com o seu ID; até 3 por pessoa, modo e temporada entram no servidor
--    (e no ranking). As simulações de Vencedor e Placar exato guardam também os jogos sorteados pelo modelo
--    (que valem pontos) e a tabela final, quando todos os jogos têm resultado.
-- 2. Pontuação por jogo (Placar exato): placar exato 10; vencedor e gols do vencedor 7; vencedor e diferença de
--    gols 6; vencedor e gols do perdedor 5; só o vencedor (ou o empate) 4; placar invertido 2. Vencedor: 4 por
--    acerto, o mesmo valor de "só o vencedor".
-- 3. Classificação: 3 pontos por clube na posição exata e 1 a uma posição; 10 pelo campeão e 3 por rebaixado
--    acertado (máximo 82). Uma ordem impossível pela matemática (um clube acima de outro que ele não alcança mais)
--    é recusada.
-- 4. Classificação mais provável segundo os visitantes: a tabela de cada pessoa (a mais recente), com mínimo de 30.
-- 5. E-mail para avisos de pontuação, em tabela própria e privada (só o dono lê; o envio usa a chave de serviço).

-- ---------------------------------------------------------------- 1. ID por simulação

alter table public.sim_simulations drop constraint sim_simulations_pkey;
alter table public.sim_simulations add column id bigint generated always as identity;
alter table public.sim_simulations add constraint sim_simulations_pkey primary key (id);
alter table public.sim_simulations add column created_at timestamptz not null default now();
create index sim_simulations_owner_idx on public.sim_simulations (user_id, competition, season, mode);

alter table public.sim_standings add column points int;
alter table public.sim_standings add column max_points int;

-- ---------------------------------------------------------------- Validação e trava

create or replace function public.sim_valid_order(p_competition text, p_season int, p_order jsonb, p_feasible boolean)
returns boolean language sql stable set search_path = public as $$
  select coalesce(jsonb_typeof(p_order) = 'array'
    and jsonb_array_length(p_order) = (select count(*) from sim_standings where competition = p_competition and season = p_season)
    and not exists (
      select 1 from jsonb_array_elements(p_order) o(club)
      left join sim_standings st on st.competition = p_competition and st.season = p_season and st.club_id = o.club #>> '{}'
      where jsonb_typeof(o.club) <> 'string' or st.club_id is null)
    and (select count(distinct o) from jsonb_array_elements_text(p_order) o) = jsonb_array_length(p_order)
    and (not p_feasible or not exists (
      -- Um clube não pode ficar acima de outro se o máximo que ele ainda alcança é menor que o que o outro já tem.
      select 1
      from jsonb_array_elements_text(p_order) with ordinality as upper_club(club_id, pos)
      join jsonb_array_elements_text(p_order) with ordinality as lower_club(club_id, pos) on lower_club.pos > upper_club.pos
      join sim_standings up on up.competition = p_competition and up.season = p_season and up.club_id = upper_club.club_id
      join sim_standings low on low.competition = p_competition and low.season = p_season and low.club_id = lower_club.club_id
      where up.max_points is not null and low.points is not null and up.max_points < low.points)), false);
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
  lock_at timestamptz;
  ranked jsonb;
begin
  if tg_op = 'UPDATE' then
    if (new.id, new.user_id, new.competition, new.season, new.mode) is distinct from (old.id, old.user_id, old.competition, old.season, old.mode) then
      raise exception 'uma simulação não muda de dono, competição, temporada nem modo' using errcode = '42501';
    end if;
    if jsonb_typeof(old.payload -> 'picks') = 'object' then old_picks := old.payload -> 'picks'; end if;
  else
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

  -- Jogos sorteados pelo modelo: só IDs que estão entre os palpites guardados.
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

-- ---------------------------------------------------------------- 2 e 3. Pontuação

create or replace function public.sim_match_points(mode text, pick jsonb, home_goals int, away_goals int)
returns int language sql immutable set search_path = public as $$
  with p as (
    select case when public.sim_valid_pick(mode, pick) and mode = 'placar' then (pick ->> 0)::int end as ph,
           case when public.sim_valid_pick(mode, pick) and mode = 'placar' then (pick ->> 1)::int end as pa
  )
  select case
    when not public.sim_valid_pick(mode, pick) or home_goals is null or away_goals is null then 0
    when mode = 'vencedor' then
      case when pick #>> '{}' = (case when home_goals > away_goals then 'H' when home_goals < away_goals then 'A' else 'D' end)
           then 4 else 0 end
    when ph = home_goals and pa = away_goals then 10
    when sign(ph - pa) = sign(home_goals - away_goals) and home_goals <> away_goals
         and greatest(ph, pa) = greatest(home_goals, away_goals) then 7
    when sign(ph - pa) = sign(home_goals - away_goals) and ph - pa = home_goals - away_goals then 6
    when sign(ph - pa) = sign(home_goals - away_goals) and home_goals <> away_goals
         and least(ph, pa) = least(home_goals, away_goals) then 5
    when sign(ph - pa) = sign(home_goals - away_goals) then 4
    when ph <> pa and ph = away_goals and pa = home_goals then 2
    else 0
  end
  from p;
$$;

create or replace function public.sim_match_max(mode text) returns int
language sql immutable as $$ select case mode when 'placar' then 10 when 'vencedor' then 4 else 0 end; $$;

drop function if exists public.sim_ranking(text, int, text, int);
drop function if exists public.sim_my_scores(text, int);
drop view if exists public.sim_scores;

create view public.sim_scores with (security_invoker = false) as
  select s.id, s.user_id, s.competition, s.season, s.mode,
         sum(public.sim_match_points(s.mode, s.payload -> 'picks' -> m.match_id, m.home_goals, m.away_goals))::int as points,
         (count(*) * public.sim_match_max(s.mode))::int as max_points,
         count(*) filter (where public.sim_match_points(s.mode, s.payload -> 'picks' -> m.match_id, m.home_goals, m.away_goals)
                          = public.sim_match_max(s.mode))::int as exact_hits,
         count(*)::int as scored_picks
  from public.sim_simulations s
  join public.sim_matches m
    on m.competition = s.competition and m.season = s.season and m.status = 'finished'
   and s.payload -> 'picks' ? m.match_id
  where s.mode in ('vencedor', 'placar')
  group by s.id, s.user_id, s.competition, s.season, s.mode
  union all
  select s.id, s.user_id, s.competition, s.season, s.mode,
         (sum(case abs(st.position - o.ordinality::int) when 0 then 3 when 1 then 1 else 0 end)
          + max(case when o.ordinality = 1 and st.position = 1 then 10 else 0 end)
          + 3 * count(*) filter (where o.ordinality > jsonb_array_length(s.payload -> 'ranked_order') - 4
                                   and st.position > jsonb_array_length(s.payload -> 'ranked_order') - 4))::int,
         82,
         count(*) filter (where st.position = o.ordinality)::int,
         count(*)::int
  from public.sim_simulations s
  join public.sim_seasons se on se.competition = s.competition and se.season = s.season and se.final_at is not null
  cross join lateral jsonb_array_elements_text(s.payload -> 'ranked_order') with ordinality as o(club_id, ordinality)
  join public.sim_standings st on st.competition = s.competition and st.season = s.season and st.club_id = o.club_id
  where s.mode = 'classificacao' and jsonb_typeof(s.payload -> 'ranked_order') = 'array'
  group by s.id, s.user_id, s.competition, s.season, s.mode;

revoke all on public.sim_scores from anon, authenticated;

-- Ranking público: cada simulação de quem marcou "Aparecer no ranking", com apelido e o ID da simulação.
create function public.sim_ranking(p_competition text, p_season int, p_mode text, p_limit int default 100)
returns table (rank bigint, nickname text, simulation_id bigint, points int, max_points int, exact_hits int, scored_picks int)
language sql stable security definer set search_path = public as $$
  select rank() over (order by sc.points desc, sc.exact_hits desc), p.nickname::text, sc.id,
         sc.points, sc.max_points, sc.exact_hits, sc.scored_picks
  from sim_scores sc
  join sim_profiles p on p.user_id = sc.user_id and p.show_in_ranking and p.nickname is not null
  where sc.competition = p_competition and sc.season = p_season and sc.mode = p_mode
  order by sc.points desc, sc.exact_hits desc, sc.id
  limit least(greatest(p_limit, 1), 500);
$$;

-- Pontuação de cada simulação do próprio usuário, apareça ele no ranking ou não.
create function public.sim_my_scores(p_competition text, p_season int)
returns table (simulation_id bigint, mode text, points int, max_points int, exact_hits int, scored_picks int)
language sql stable security definer set search_path = public as $$
  select sc.id, sc.mode, sc.points, sc.max_points, sc.exact_hits, sc.scored_picks from sim_scores sc
  where sc.user_id = auth.uid() and sc.competition = p_competition and sc.season = p_season;
$$;

-- ---------------------------------------------------------------- Média e classificação dos visitantes

create or replace function public.sim_community(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select 30 as min_users),
  votes as (
    -- Uma voz por pessoa e jogo: a simulação mais recente dela que tem esse jogo, com o Placar exato à frente.
    select distinct on (s.user_id, m.key) m.key as match_id, public.sim_pick_outcome(s.mode, m.value) as outcome
    from sim_simulations s cross join lateral jsonb_each(
      case when jsonb_typeof(s.payload -> 'picks') = 'object' then s.payload -> 'picks' else '{}'::jsonb end) m
    where s.competition = p_competition and s.season = p_season and s.mode in ('vencedor', 'placar')
      and public.sim_valid_pick(s.mode, m.value)
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

-- Tabela final mais provável segundo os visitantes: a tabela mais recente de cada pessoa (Classificação ou a
-- tabela final de uma simulação de Vencedor ou Placar exato), ordenada pela posição média.
create or replace function public.sim_consensus(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select 30 as min_users),
  tables as (
    select distinct on (s.user_id) s.user_id,
           case when s.mode = 'classificacao' then s.payload -> 'order' else s.payload -> 'final_order' end as final_table
    from sim_simulations s
    where s.competition = p_competition and s.season = p_season
      and jsonb_typeof(case when s.mode = 'classificacao' then s.payload -> 'order' else s.payload -> 'final_order' end) = 'array'
    order by s.user_id, s.updated_at desc
  ),
  positions as (
    select o.club_id, avg(o.ordinality) as average_position,
           avg(case when o.ordinality = 1 then 1 else 0 end) as champion,
           avg(case when o.ordinality > jsonb_array_length(t.final_table) - 4 then 1 else 0 end) as relegated
    from tables t cross join lateral jsonb_array_elements_text(t.final_table) with ordinality as o(club_id, ordinality)
    group by o.club_id
  ),
  total as (select count(*) as users from tables)
  select jsonb_build_object(
    'min_users', (select min_users from params),
    'users_at_least', (select (users / 10) * 10 from total),
    'clubs', case when (select users from total) >= (select min_users from params) then (
      select coalesce(jsonb_agg(jsonb_build_object(
          'club_id', club_id, 'average_position', round(average_position, 1),
          'champion', round(champion * 20) / 20, 'relegated', round(relegated * 20) / 20)
        order by average_position, club_id), '[]'::jsonb)
      from positions) else '[]'::jsonb end
  );
$$;

-- ---------------------------------------------------------------- 5. E-mail para avisos de pontuação

create table public.sim_contacts (
  user_id uuid primary key references auth.users (id) on delete cascade,
  email text not null check (length(email) <= 254 and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  notify boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.sim_contacts enable row level security;
create policy "dono lê" on public.sim_contacts for select to authenticated using (user_id = auth.uid());
create policy "dono cria" on public.sim_contacts for insert to authenticated with check (user_id = auth.uid());
create policy "dono altera" on public.sim_contacts for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "dono apaga" on public.sim_contacts for delete to authenticated using (user_id = auth.uid());
revoke all on public.sim_contacts from anon;
grant select, insert, update, delete on public.sim_contacts to authenticated;
create trigger sim_touch_contact before update on public.sim_contacts
  for each row execute function public.sim_touch_profile();

-- Lista para o envio dos avisos: só a chave de serviço chama.
create function public.sim_notification_list(p_competition text, p_season int)
returns table (email text, nickname text, simulation_id bigint, mode text, points int, max_points int)
language sql stable security definer set search_path = public as $$
  select c.email, p.nickname::text, sc.id, sc.mode, sc.points, sc.max_points
  from sim_contacts c
  left join sim_profiles p on p.user_id = c.user_id
  left join sim_scores sc on sc.user_id = c.user_id and sc.competition = p_competition and sc.season = p_season
  where c.notify
  order by c.email, sc.mode, sc.id;
$$;

-- ---------------------------------------------------------------- Permissões das funções

revoke all on function public.sim_valid_order(text, int, jsonb, boolean) from public, anon, authenticated;
revoke all on function public.sim_match_max(text) from public, anon;
revoke all on function public.sim_ranking(text, int, text, int) from public;
revoke all on function public.sim_my_scores(text, int) from public, anon;
revoke all on function public.sim_consensus(text, int) from public;
revoke all on function public.sim_notification_list(text, int) from public, anon, authenticated;
grant execute on function public.sim_ranking(text, int, text, int) to anon, authenticated;
grant execute on function public.sim_my_scores(text, int) to authenticated;
grant execute on function public.sim_community(text, int) to anon, authenticated;
grant execute on function public.sim_consensus(text, int) to anon, authenticated;
grant execute on function public.sim_notification_list(text, int) to service_role;
