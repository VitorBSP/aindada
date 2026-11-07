-- Simulador do usuário, fase 2 (ADR-0015): simulações salvas, média dos usuários e ranking opcional.
--
-- Privacidade: o e-mail fica só em auth.users, que a API pública não expõe. O que é público é o apelido de quem
-- escolheu aparecer no ranking e números agregados (com mínimo de participantes). Todas as tabelas têm RLS.
-- Escrita de jogos e classificação: só a chave de serviço do CI (sem política para anon/authenticated).

create extension if not exists citext with schema extensions;

-- ---------------------------------------------------------------- Jogos e temporadas (escritos pelo CI)

create table public.sim_seasons (
  competition text not null,
  season int not null,
  -- Depois deste instante a ordem do modo Classificação deixa de valer para o ranking (continua editável).
  classificacao_locks_at timestamptz not null,
  -- Preenchido pelo CI quando a última rodada termina; só então a Classificação pontua.
  final_at timestamptz,
  primary key (competition, season)
);

create table public.sim_matches (
  competition text not null,
  season int not null,
  match_id text not null,
  round int,
  home_id text not null,
  away_id text not null,
  kickoff_utc timestamptz,
  status text not null check (status in ('scheduled', 'finished', 'postponed', 'cancelled')),
  home_goals int check (home_goals >= 0),
  away_goals int check (away_goals >= 0),
  updated_at timestamptz not null default now(),
  primary key (competition, season, match_id),
  -- Partida sem placar nunca vira 0 x 0 (AGENTS.md): placar só com status finished.
  check ((status = 'finished') = (home_goals is not null and away_goals is not null))
);

create table public.sim_standings (
  competition text not null,
  season int not null,
  club_id text not null,
  position int not null check (position between 1 and 40),
  primary key (competition, season, club_id)
);

alter table public.sim_seasons enable row level security;
alter table public.sim_matches enable row level security;
alter table public.sim_standings enable row level security;
create policy "leitura pública" on public.sim_seasons for select to anon, authenticated using (true);
create policy "leitura pública" on public.sim_matches for select to anon, authenticated using (true);
create policy "leitura pública" on public.sim_standings for select to anon, authenticated using (true);

-- ---------------------------------------------------------------- Perfis (apelido) e simulações

create table public.sim_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  -- Letras (com os acentos do português), números, _ . - e espaço; a mesma regra de NICKNAME em simulator.js.
  nickname citext unique check (nickname::text ~ '^[A-Za-zÀ-ÖØ-öø-ÿ0-9_. -]{3,20}$'),
  show_in_ranking boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (not show_in_ranking or nickname is not null)
);

create table public.sim_simulations (
  user_id uuid not null references auth.users (id) on delete cascade,
  competition text not null,
  season int not null,
  mode text not null check (mode in ('classificacao', 'vencedor', 'placar')),
  -- classificacao: {"order": [club_id, ...]}; vencedor: {"picks": {match_id: "H"|"D"|"A"}};
  -- placar: {"picks": {match_id: [gols_mandante, gols_visitante]}}.
  payload jsonb not null check (jsonb_typeof(payload) = 'object' and pg_column_size(payload) < 32000),
  assist boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (user_id, competition, season, mode),
  foreign key (competition, season) references public.sim_seasons (competition, season)
);

alter table public.sim_profiles enable row level security;
alter table public.sim_simulations enable row level security;

create policy "dono lê" on public.sim_profiles for select to authenticated using (user_id = auth.uid());
create policy "dono cria" on public.sim_profiles for insert to authenticated with check (user_id = auth.uid());
create policy "dono altera" on public.sim_profiles for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "dono apaga" on public.sim_profiles for delete to authenticated using (user_id = auth.uid());

create policy "dono lê" on public.sim_simulations for select to authenticated using (user_id = auth.uid());
create policy "dono cria" on public.sim_simulations for insert to authenticated with check (user_id = auth.uid());
create policy "dono altera" on public.sim_simulations for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "dono apaga" on public.sim_simulations for delete to authenticated using (user_id = auth.uid());

-- Permissões explícitas: não dependem de o projeto expor tabelas novas por padrão. As linhas visíveis seguem o RLS.
grant select on public.sim_seasons, public.sim_matches, public.sim_standings to anon, authenticated;
grant select, insert, update, delete on public.sim_profiles, public.sim_simulations to authenticated;
grant select, insert, update, delete on public.sim_seasons, public.sim_matches, public.sim_standings to service_role;
-- O Supabase concede tudo a anon por padrão; perfis e simulações são só de quem tem conta.
revoke all on public.sim_profiles, public.sim_simulations from anon;

-- ---------------------------------------------------------------- Trava dos palpites

-- Valida e trava. Palpites malformados ou de jogos que não existem são descartados; a ordem da Classificação
-- precisa ter cada clube da temporada uma vez e, para o ranking, vale a última salva antes de
-- classificacao_locks_at. Palpite de jogo que já começou (ou terminou) não muda: o valor anterior é mantido, e um
-- palpite novo para esse jogo é descartado. Silencioso de propósito: o navegador pode estar com o relógio errado,
-- e o servidor é quem decide.
create or replace function public.sim_lock_picks() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  locked_ids text[];
  old_picks jsonb := case when tg_op = 'UPDATE' then coalesce(old.payload -> 'picks', '{}'::jsonb) else '{}'::jsonb end;
  new_picks jsonb;
  match_id text;
  lock_at timestamptz;
begin
  new.updated_at := now();
  if new.mode = 'classificacao' then
    if jsonb_typeof(new.payload -> 'order') <> 'array'
       or (select count(*) from sim_standings where competition = new.competition and season = new.season)
          <> jsonb_array_length(new.payload -> 'order')
       or exists (
         select 1 from jsonb_array_elements_text(new.payload -> 'order') o(club_id)
         left join sim_standings st on st.competition = new.competition and st.season = new.season and st.club_id = o.club_id
         where st.club_id is null)
       or (select count(distinct o) from jsonb_array_elements_text(new.payload -> 'order') o) <> jsonb_array_length(new.payload -> 'order')
    then
      raise exception 'ordem inválida para %/%', new.competition, new.season using errcode = '22023';
    end if;
    -- A ordem continua editável para comparar; o ranking usa ranked_order, a última ordem salva antes da trava.
    select classificacao_locks_at into lock_at from sim_seasons where competition = new.competition and season = new.season;
    if lock_at is null or now() < lock_at then
      new.payload := jsonb_set(new.payload, '{ranked_order}', new.payload -> 'order');
    elsif tg_op = 'UPDATE' and old.payload ? 'ranked_order' then
      new.payload := jsonb_set(new.payload, '{ranked_order}', old.payload -> 'ranked_order');
    else
      new.payload := new.payload - 'ranked_order';
    end if;
    return new;
  end if;

  select coalesce(array_agg(m.match_id), '{}') into locked_ids
  from sim_matches m
  where m.competition = new.competition and m.season = new.season
    and (m.status = 'finished' or (m.kickoff_utc is not null and m.kickoff_utc <= now()));

  select coalesce(jsonb_object_agg(e.key, e.value), '{}'::jsonb) into new_picks
  from jsonb_each(case when jsonb_typeof(new.payload -> 'picks') = 'object' then new.payload -> 'picks' else '{}'::jsonb end) e
  join sim_matches m on m.competition = new.competition and m.season = new.season and m.match_id = e.key
  where (new.mode = 'vencedor' and jsonb_typeof(e.value) = 'string' and e.value #>> '{}' in ('H', 'D', 'A'))
     or (new.mode = 'placar' and jsonb_typeof(e.value) = 'array' and jsonb_array_length(e.value) = 2
         and e.value ->> 0 ~ '^[0-9]{1,2}$' and e.value ->> 1 ~ '^[0-9]{1,2}$');
  foreach match_id in array locked_ids loop
    if old_picks ? match_id then
      new_picks := jsonb_set(new_picks, array[match_id], old_picks -> match_id);
    else
      new_picks := new_picks - match_id;
    end if;
  end loop;
  new.payload := jsonb_set(new.payload, '{picks}', new_picks);
  return new;
end;
$$;

create trigger sim_lock_picks before insert or update on public.sim_simulations
  for each row execute function public.sim_lock_picks();

create or replace function public.sim_touch_profile() returns trigger
language plpgsql as $$ begin new.updated_at := now(); return new; end; $$;
create trigger sim_touch_profile before update on public.sim_profiles
  for each row execute function public.sim_touch_profile();

-- ---------------------------------------------------------------- Pontuação (bolão clássico)

-- Placar exato: 5 pelo placar, 3 pelo vencedor (ou empate) com o saldo certo, 2 só pelo vencedor (ou empate).
-- Vencedor: 1 por acerto. Classificação (só com a temporada encerrada): 3 pela posição exata, 1 por errar uma.
create or replace function public.sim_match_points(mode text, pick jsonb, home_goals int, away_goals int)
returns int language sql immutable as $$
  select case
    when mode = 'vencedor' then
      case when pick #>> '{}' = (case when home_goals > away_goals then 'H' when home_goals < away_goals then 'A' else 'D' end)
           then 1 else 0 end
    when mode = 'placar' and jsonb_typeof(pick) = 'array' then
      case
        when (pick ->> 0)::int = home_goals and (pick ->> 1)::int = away_goals then 5
        when sign((pick ->> 0)::int - (pick ->> 1)::int) = sign(home_goals - away_goals)
             and (pick ->> 0)::int - (pick ->> 1)::int = home_goals - away_goals then 3
        when sign((pick ->> 0)::int - (pick ->> 1)::int) = sign(home_goals - away_goals) then 2
        else 0
      end
    else 0
  end;
$$;

create or replace view public.sim_scores with (security_invoker = false) as
  select s.user_id, s.competition, s.season, s.mode,
         sum(public.sim_match_points(s.mode, s.payload -> 'picks' -> m.match_id, m.home_goals, m.away_goals))::int as points,
         count(*) filter (where public.sim_match_points(s.mode, s.payload -> 'picks' -> m.match_id, m.home_goals, m.away_goals)
                          = case s.mode when 'placar' then 5 else 1 end)::int as exact_hits,
         count(*)::int as scored_picks
  from public.sim_simulations s
  join public.sim_matches m
    on m.competition = s.competition and m.season = s.season and m.status = 'finished'
   and s.payload -> 'picks' ? m.match_id
  where s.mode in ('vencedor', 'placar')
  group by s.user_id, s.competition, s.season, s.mode
  union all
  select s.user_id, s.competition, s.season, s.mode,
         sum(case abs(st.position - (o.ordinality)::int) when 0 then 3 when 1 then 1 else 0 end)::int,
         count(*) filter (where st.position = o.ordinality)::int,
         count(*)::int
  from public.sim_simulations s
  join public.sim_seasons se on se.competition = s.competition and se.season = s.season and se.final_at is not null
  cross join lateral jsonb_array_elements_text(s.payload -> 'ranked_order') with ordinality as o(club_id, ordinality)
  join public.sim_standings st on st.competition = s.competition and st.season = s.season and st.club_id = o.club_id
  where s.mode = 'classificacao' and jsonb_typeof(s.payload -> 'ranked_order') = 'array'
  group by s.user_id, s.competition, s.season, s.mode;

-- A visão junta dados de todos os usuários: ninguém lê direto, só pelas funções abaixo.
revoke all on public.sim_scores from anon, authenticated;

-- Ranking público: só quem marcou show_in_ranking, identificado pelo apelido.
create or replace function public.sim_ranking(p_competition text, p_season int, p_mode text, p_limit int default 100)
returns table (rank bigint, nickname text, points int, exact_hits int, scored_picks int)
language sql stable security definer set search_path = public as $$
  select rank() over (order by sc.points desc, sc.exact_hits desc), p.nickname::text, sc.points, sc.exact_hits, sc.scored_picks
  from sim_scores sc
  join sim_profiles p on p.user_id = sc.user_id and p.show_in_ranking and p.nickname is not null
  where sc.competition = p_competition and sc.season = p_season and sc.mode = p_mode
  order by sc.points desc, sc.exact_hits desc, p.nickname
  limit least(greatest(p_limit, 1), 500);
$$;

-- Pontuação do próprio usuário, apareça ele no ranking ou não.
create or replace function public.sim_my_scores(p_competition text, p_season int)
returns table (mode text, points int, exact_hits int, scored_picks int)
language sql stable security definer set search_path = public as $$
  select sc.mode, sc.points, sc.exact_hits, sc.scored_picks from sim_scores sc
  where sc.user_id = auth.uid() and sc.competition = p_competition and sc.season = p_season;
$$;

-- ---------------------------------------------------------------- Média dos usuários

-- Só sai número com pelo menos min_users participantes, para não expor a escolha de uma pessoa.
create or replace function public.sim_community(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select 10 as min_users),
  outcome_counts as (
    select m.key as match_id, s.mode,
           case when s.mode = 'vencedor' then m.value #>> '{}'
                else case sign((m.value ->> 0)::int - (m.value ->> 1)::int) when 1 then 'H' when -1 then 'A' else 'D' end end as outcome,
           count(*) as users
    from sim_simulations s cross join lateral jsonb_each(s.payload -> 'picks') m
    where s.competition = p_competition and s.season = p_season and s.mode in ('vencedor', 'placar')
    group by 1, 2, 3
  ),
  per_match as (
    select match_id, sum(users) as users,
           jsonb_object_agg(outcome, users) as counts
    from outcome_counts group by match_id
  ),
  positions as (
    select o.club_id, avg(o.ordinality) as average_position,
           avg(case when o.ordinality = 1 then 1 else 0 end) as champion,
           avg(case when o.ordinality > jsonb_array_length(s.payload -> 'order') - 4 then 1 else 0 end) as relegated,
           count(*) as users
    from sim_simulations s
    cross join lateral jsonb_array_elements_text(s.payload -> 'order') with ordinality as o(club_id, ordinality)
    where s.competition = p_competition and s.season = p_season and s.mode = 'classificacao'
    group by o.club_id
  )
  select jsonb_build_object(
    'min_users', (select min_users from params),
    'simulations', (select coalesce(jsonb_object_agg(mode, total), '{}'::jsonb) from (
       select mode, count(*) as total from sim_simulations where competition = p_competition and season = p_season group by mode) t),
    'matches', (select coalesce(jsonb_object_agg(match_id, jsonb_build_object(
        'users', users,
        'H', coalesce((counts ->> 'H')::numeric, 0) / users,
        'D', coalesce((counts ->> 'D')::numeric, 0) / users,
        'A', coalesce((counts ->> 'A')::numeric, 0) / users)), '{}'::jsonb)
      from per_match, params where users >= min_users),
    'clubs', (select coalesce(jsonb_object_agg(club_id, jsonb_build_object(
        'users', users, 'average_position', round(average_position, 2),
        'champion', round(champion, 4), 'relegated', round(relegated, 4))), '{}'::jsonb)
      from positions, params where users >= min_users)
  );
$$;

revoke all on function public.sim_ranking(text, int, text, int) from public;
revoke all on function public.sim_my_scores(text, int) from public, anon;
revoke all on function public.sim_community(text, int) from public;
grant execute on function public.sim_ranking(text, int, text, int) to anon, authenticated;
grant execute on function public.sim_my_scores(text, int) to authenticated;
grant execute on function public.sim_community(text, int) to anon, authenticated;
revoke all on function public.sim_lock_picks() from public, anon, authenticated;

-- ---------------------------------------------------------------- Direito de apagar (LGPD, art. 18)

-- Apaga a conta de quem chama, com perfil e simulações (on delete cascade). Sem volta.
create or replace function public.sim_delete_me() returns void
language sql security definer set search_path = public, auth as $$
  delete from auth.users where id = auth.uid();
$$;
revoke all on function public.sim_delete_me() from public, anon;
grant execute on function public.sim_delete_me() to authenticated;
