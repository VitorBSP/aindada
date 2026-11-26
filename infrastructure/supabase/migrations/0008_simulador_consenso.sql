-- Simulador do usuário: consenso e média dos visitantes sem deduzir a escolha de uma pessoa (ADR-0015, "Endurecimento
-- do consenso"; achados A e 6 do Agente 06 em docs/project/status.md). Não altera tabelas de dados nem a trava.
--
-- A. Com contas anônimas baratas, alguém com 29 contas próprias (mínimo 30) via a escolha da 30ª pessoa: uma fração
--    de 1/30 arredonda para 0,05 e aparece, e a posição média com uma casa decimal revela o 30º participante. A
--    mitigação tem três camadas:
--    1. mínimo de pessoas sobe de 30 para 50 (sim_privacy_min_users), o que encarece o ataque de 29 para 49 contas;
--    2. ruído determinístico: cada número publicado leva um deslocamento fixo de até ±3 "pessoas" (sim_privacy_noise_people)
--       escalado pelo intervalo do valor e dividido pelo número de pessoas, derivado de um sal secreto (sim_private) e do
--       nome do número. Fixo = repetir a consulta não permite tirar a média do ruído; secreto = quem controla as contas
--       não sabe onde fica a fronteira do arredondamento, então não consegue calibrar as contas para que 1 voto vire o
--       número. Com mais pessoas o erro cai (3/n);
--    3. precisão menor: frações em passos de 0,05 (como antes) e posição média em passos de 0,5 (antes, 0,1).
--    Risco que sobra (ver docs/architecture/simulator-supabase.md): comparar o número antes e depois de uma pessoa
--    entrar, com ≥ 50 contas já prontas, ainda mostra que "algo mudou"; e quem cria centenas de contas pode refinar a
--    estimativa. A defesa de fundo é limitar a criação de contas (CAPTCHA, e-mail confirmado).
-- 6. sim_consensus só usa a tabela final de Vencedor e Placar exato se ela bater com os palpites guardados e com a
--    matemática do campeonato (sim_final_order_ok): todos os jogos que faltam têm palpite válido; pontos finais =
--    pontos de hoje (sim_standings.points) + resultado dos palpites; nenhum clube passa de max_points; a ordem não tem
--    um clube com menos pontos acima de outro com mais. Empate em pontos aceita qualquer ordem (os critérios de
--    desempate não existem no banco).

-- ---------------------------------------------------------------- Permissões de tabela mínimas

-- O Supabase concede tudo nas tabelas novas a anon e authenticated, e só a RLS segura escrita nas tabelas do CI (sem
-- política, a escrita some em silêncio). Aqui o privilégio também sai: defesa em profundidade, e TRUNCATE, que a RLS
-- não cobre, deixa de ser possível. O CI continua escrevendo com service_role (concedido na 0001).
revoke insert, update, delete, truncate, references, trigger on public.sim_seasons, public.sim_matches, public.sim_standings
  from anon, authenticated;
revoke truncate, references, trigger on public.sim_profiles, public.sim_simulations, public.sim_contacts from anon, authenticated;

-- ---------------------------------------------------------------- Segredo do ruído

create table if not exists public.sim_private (
  name text primary key,
  value text not null
);
alter table public.sim_private enable row level security;
-- Sem política e sem permissão: só o dono do banco e as funções security definer leem. Nem a chave de serviço do CI.
revoke all on public.sim_private from public, anon, authenticated, service_role;
insert into public.sim_private (name, value) values ('noise_salt', gen_random_uuid()::text)
  on conflict (name) do nothing;

create or replace function public.sim_privacy_min_users() returns int
language sql immutable as $$ select 50 $$;

-- Amplitude do ruído, em pessoas: um número de n pessoas se desloca até noise_people * (intervalo do valor) / n.
create or replace function public.sim_privacy_noise_people() returns numeric
language sql immutable as $$ select 3::numeric $$;

-- Número em [-1, 1) fixo para cada (sal, nome). Nunca devolvido tal qual: só dentro das funções abaixo.
create or replace function public.sim_noise(p_scope text) returns numeric
language sql stable security definer set search_path = public as $$
  select (('x' || substr(md5((select value from sim_private where name = 'noise_salt') || '|' || p_scope), 1, 8))::bit(32)::bigint)::numeric
         / 2147483648 - 1;
$$;

revoke all on function public.sim_privacy_min_users() from public, anon, authenticated;
revoke all on function public.sim_privacy_noise_people() from public, anon, authenticated;
revoke all on function public.sim_noise(text) from public, anon, authenticated;

-- ---------------------------------------------------------------- 6. A tabela final bate com os palpites?

create or replace function public.sim_final_order_ok(p_competition text, p_season int, p_mode text, p_payload jsonb)
returns boolean language sql stable set search_path = public as $$
  with remaining as (
    select m.match_id, m.home_id, m.away_id, m.status,
           public.sim_pick_outcome(p_mode, case when jsonb_typeof(p_payload -> 'picks') = 'object'
                                                then p_payload -> 'picks' -> m.match_id end) as outcome
    from sim_matches m
    where m.competition = p_competition and m.season = p_season and m.status <> 'finished'
  ),
  gained as (
    select home_id as club_id, case outcome when 'H' then 3 when 'D' then 1 else 0 end as gained_points
    from remaining where outcome is not null
    union all
    select away_id, case outcome when 'A' then 3 when 'D' then 1 else 0 end
    from remaining where outcome is not null
  ),
  totals as (
    select st.club_id, st.points, st.max_points,
           st.points + coalesce((select sum(g.gained_points) from gained g where g.club_id = st.club_id), 0) as final_points
    from sim_standings st
    where st.competition = p_competition and st.season = p_season
  ),
  ordered as (
    select o.club_id, o.pos
    from jsonb_array_elements_text(case when jsonb_typeof(p_payload -> 'final_order') = 'array'
                                        then p_payload -> 'final_order' else '[]'::jsonb end) with ordinality as o(club_id, pos)
  )
  select coalesce(
    public.sim_valid_order(p_competition, p_season, p_payload -> 'final_order', false)
    and not exists (select 1 from remaining where outcome is null and status <> 'cancelled')
    and not exists (select 1 from totals where points is null)
    and not exists (select 1 from totals where max_points is not null and final_points > max_points)
    and not exists (
      select 1 from ordered upper_club
      join ordered lower_club on lower_club.pos = upper_club.pos + 1
      join totals upper_total on upper_total.club_id = upper_club.club_id
      join totals lower_total on lower_total.club_id = lower_club.club_id
      where upper_total.final_points < lower_total.final_points),
    false);
$$;
revoke all on function public.sim_final_order_ok(text, int, text, jsonb) from public, anon, authenticated;

-- ---------------------------------------------------------------- A. Média dos visitantes (jogos)

create or replace function public.sim_community(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select public.sim_privacy_min_users() as min_users, public.sim_privacy_noise_people() as noise_people),
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
    'noise_people', (select noise_people from params),
    'matches', (select coalesce(jsonb_object_agg(match_id, jsonb_build_object(
        'users_at_least', (users / 10) * 10,
        'H', least(1, greatest(0, round((home + noise_people * public.sim_noise('community|' || p_competition || '|' || p_season || '|' || match_id || '|H')) / users * 20) / 20)),
        'D', least(1, greatest(0, round((draw + noise_people * public.sim_noise('community|' || p_competition || '|' || p_season || '|' || match_id || '|D')) / users * 20) / 20)),
        'A', least(1, greatest(0, round((away + noise_people * public.sim_noise('community|' || p_competition || '|' || p_season || '|' || match_id || '|A')) / users * 20) / 20)))), '{}'::jsonb)
      from per_match, params where users >= min_users)
  );
$$;

-- ---------------------------------------------------------------- A e 6. Consenso (tabelas finais)

create or replace function public.sim_consensus(p_competition text, p_season int)
returns jsonb language sql stable security definer set search_path = public as $$
  with params as (select public.sim_privacy_min_users() as min_users, public.sim_privacy_noise_people() as noise_people),
  candidates as (
    select s.user_id, s.mode, s.payload,
           case when s.mode = 'classificacao' then s.payload -> 'order' else s.payload -> 'final_order' end as final_table
    from sim_simulations s
    where s.competition = p_competition and s.season = p_season
  ),
  tables as (
    select user_id, final_table from candidates
    where (mode = 'classificacao' and public.sim_valid_order(p_competition, p_season, final_table, false))
       or (mode in ('vencedor', 'placar') and public.sim_final_order_ok(p_competition, p_season, mode, payload))
  ),
  per_person as (
    select t.user_id, o.club_id, avg(o.ordinality) as average_position,
           avg(case when o.ordinality = 1 then 1 else 0 end) as champion,
           avg(case when o.ordinality > jsonb_array_length(t.final_table) - 4 then 1 else 0 end) as relegated
    from tables t cross join lateral jsonb_array_elements_text(t.final_table) with ordinality as o(club_id, ordinality)
    group by t.user_id, o.club_id
  ),
  total as (
    select count(distinct user_id) as users, count(*) as simulations,
           (select count(*) from sim_standings where competition = p_competition and season = p_season) as clubs
    from tables
  ),
  positions as (
    select club_id, avg(average_position) as average_position, avg(champion) as champion, avg(relegated) as relegated
    from per_person group by club_id
  ),
  noisy as (
    -- Ruído = noise_people * intervalo do valor / pessoas, com o sinal e o tamanho fixos por (sal, nome).
    select p.club_id,
           p.average_position + params.noise_people * (total.clubs - 1) / total.users
             * public.sim_noise('consensus|' || p_competition || '|' || p_season || '|' || p.club_id || '|position') as average_position,
           p.champion + params.noise_people / total.users
             * public.sim_noise('consensus|' || p_competition || '|' || p_season || '|' || p.club_id || '|champion') as champion,
           p.relegated + params.noise_people / total.users
             * public.sim_noise('consensus|' || p_competition || '|' || p_season || '|' || p.club_id || '|relegated') as relegated
    from positions p, params, total
  )
  select jsonb_build_object(
    'min_users', (select min_users from params),
    'noise_people', (select noise_people from params),
    'users_at_least', (select (users / 10) * 10 from total),
    'simulations_at_least', (select (simulations / 10) * 10 from total),
    'clubs', case when (select users from total) >= (select min_users from params) then (
      select coalesce(jsonb_agg(jsonb_build_object(
          'club_id', club_id,
          'average_position', least((select clubs from total), greatest(1, round(average_position * 2) / 2)),
          'champion', least(1, greatest(0, round(champion * 20) / 20)),
          'relegated', least(1, greatest(0, round(relegated * 20) / 20)))
        order by average_position, club_id), '[]'::jsonb)
      from noisy) else '[]'::jsonb end
  );
$$;

revoke all on function public.sim_community(text, int) from public;
revoke all on function public.sim_consensus(text, int) from public;
grant execute on function public.sim_community(text, int) to anon, authenticated;
grant execute on function public.sim_consensus(text, int) to anon, authenticated;
