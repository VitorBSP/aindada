-- Dados SINTÉTICOS de teste (AGENTS.md: fixtures sintéticas ficam em tests/ e são marcadas como tal). Nada daqui é
-- resultado real do Brasileirão: competição 'synthetic-liga', 8 clubes fictícios a..h.

create function t.user_id(p_n int) returns uuid language plpgsql as $$
declare id uuid := ('00000000-0000-0000-0000-' || lpad(p_n::text, 12, '0'))::uuid;
begin
  insert into auth.users (id, email) values (id, 'synthetic' || p_n || '@example.invalid') on conflict do nothing;
  return id;
end $$;

create function t.refresh_standings() returns void language sql as $$
  delete from public.sim_standings where competition = 'synthetic-liga' and season = 2026;
  insert into public.sim_standings (competition, season, club_id, position, points, max_points)
  select 'synthetic-liga', 2026, club_id, (row_number() over (order by points desc, club_id))::int, points,
         points + 3 * (select count(*) from public.sim_matches m
                       where m.competition = 'synthetic-liga' and m.season = 2026 and m.status <> 'finished'
                         and club_id in (m.home_id, m.away_id))::int
  from (select c.club_id,
               coalesce(sum(case when m.status <> 'finished' then 0
                                 when (m.home_id = c.club_id and m.home_goals > m.away_goals)
                                   or (m.away_id = c.club_id and m.away_goals > m.home_goals) then 3
                                 when m.home_goals = m.away_goals then 1 else 0 end), 0)::int as points
        from (select unnest(array['a','b','c','d','e','f','g','h']) as club_id) c
        left join public.sim_matches m on m.competition = 'synthetic-liga' and m.season = 2026 and c.club_id in (m.home_id, m.away_id)
        group by c.club_id) p;
$$;

-- p_started = true: s1 já começou e s2 trava em 10 minutos (sem placar). false: nenhum jogo em andamento.
create function t.reset(p_started boolean default true) returns void language plpgsql as $$
begin
  truncate public.sim_simulations, public.sim_contacts, public.sim_profiles, public.sim_matches,
           public.sim_standings, public.sim_seasons cascade;
  delete from auth.users;
  insert into public.sim_seasons (competition, season, classificacao_locks_at)
  values ('synthetic-liga', 2026, now() - interval '30 days');
  insert into public.sim_matches (competition, season, match_id, round, home_id, away_id, kickoff_utc, status, home_goals, away_goals)
  values ('synthetic-liga', 2026, 'f1', 1, 'a', 'b', now() - interval '10 days', 'finished', 2, 1),
         ('synthetic-liga', 2026, 'f2', 1, 'c', 'd', now() - interval '10 days', 'finished', 0, 0),
         ('synthetic-liga', 2026, 's1', 2, 'e', 'f', case when p_started then now() - interval '1 hour' else now() + interval '5 days' end, 'scheduled', null, null),
         ('synthetic-liga', 2026, 's2', 2, 'g', 'h', case when p_started then now() + interval '10 minutes' else now() + interval '6 days' end, 'scheduled', null, null),
         ('synthetic-liga', 2026, 'o1', 3, 'a', 'c', now() + interval '2 days', 'scheduled', null, null),
         ('synthetic-liga', 2026, 'o2', 3, 'b', 'd', now() + interval '2 days', 'scheduled', null, null),
         ('synthetic-liga', 2026, 'o3', 3, 'e', 'g', now() + interval '3 days', 'scheduled', null, null),
         ('synthetic-liga', 2026, 'o4', 3, 'f', 'h', now() + interval '3 days', 'scheduled', null, null),
         ('synthetic-liga', 2026, 'o5', 4, 'a', 'd', now() + interval '4 days', 'scheduled', null, null);
  perform t.refresh_standings();
end $$;
