-- Modo Ao vivo da Série A (#/ao-vivo, T1 para a última rodada de 02/12/2026): placares parciais da rodada.
--
-- O dono escreve com scripts/update_live_scores.py (chave de serviço, fora do navegador); a página lê com a chave
-- pública a cada 15 segundos e recalcula tabela e chances no navegador, sem depender do publish-site.yml.
-- O snapshot publicado continua o oficial: jogo encerrado nele ganha do placar daqui.
--
-- Integridade (AGENTS.md): jogo que não começou não tem placar (nunca 0 x 0 inventado); ao vivo, intervalo e
-- encerrado exigem os dois placares; ao vivo exige o minuto.
-- Acesso: SELECT para anon e authenticated; INSERT, UPDATE e DELETE só para service_role (que ignora a RLS).

create table if not exists public.live_round_scores (
  season int not null check (season between 2000 and 2100),
  round int not null check (round between 1 and 38),
  match_id text primary key check (match_id ~ '^[0-9]{4}-[a-z0-9-]+$' and left(match_id, 4)::int = season),
  home_goals int check (home_goals between 0 and 30),
  away_goals int check (away_goals between 0 and 30),
  minute int check (minute between 0 and 130),
  status text not null default 'scheduled' check (status in ('scheduled', 'live', 'ht', 'finished')),
  updated_at timestamptz not null default now(),
  constraint live_round_scores_score_matches_status
    check ((status = 'scheduled') = (home_goals is null and away_goals is null)
           and (home_goals is null) = (away_goals is null)),
  constraint live_round_scores_live_has_minute check (status <> 'live' or minute is not null)
);

create index if not exists live_round_scores_season_round on public.live_round_scores (season, round);

-- updated_at é sempre a hora do servidor (o selo "Atualizado às" da página não depende do relógio de quem escreve).
create or replace function public.live_round_scores_touch() returns trigger
language plpgsql set search_path = public as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists live_round_scores_touch on public.live_round_scores;
create trigger live_round_scores_touch before insert or update on public.live_round_scores
  for each row execute function public.live_round_scores_touch();

alter table public.live_round_scores enable row level security;

drop policy if exists "leitura pública" on public.live_round_scores;
create policy "leitura pública" on public.live_round_scores for select to anon, authenticated using (true);

-- Defesa em profundidade: políticas restritivas negam escrita a anon e authenticated mesmo que alguém crie, no
-- futuro, uma política permissiva por engano. Sem política permissiva de escrita, a RLS já nega.
drop policy if exists "sem escrita pública (insert)" on public.live_round_scores;
create policy "sem escrita pública (insert)" on public.live_round_scores as restrictive for insert
  to anon, authenticated with check (false);
drop policy if exists "sem escrita pública (update)" on public.live_round_scores;
create policy "sem escrita pública (update)" on public.live_round_scores as restrictive for update
  to anon, authenticated using (false) with check (false);
drop policy if exists "sem escrita pública (delete)" on public.live_round_scores;
create policy "sem escrita pública (delete)" on public.live_round_scores as restrictive for delete
  to anon, authenticated using (false);

revoke all on public.live_round_scores from public, anon, authenticated;
grant select on public.live_round_scores to anon, authenticated;
grant select, insert, update, delete on public.live_round_scores to service_role;
revoke all on function public.live_round_scores_touch() from public, anon, authenticated;
