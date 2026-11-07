-- Simulador do usuário: limite por evento, simulações antigas fechadas e trava 30 minutos antes do jogo
-- (ADR-0015, versão 5, pedido do dono em 2026-11-07).
--
-- 1. Trava dos palpites: cada jogo trava 30 minutos antes do pontapé (sim_lock_margin), não mais no pontapé. Sem
--    horário, continua 00:00 de Brasília do dia (o supabase_sync manda esse horário em kickoff_utc).
-- 2. Evento: cada vez que um jogo trava. sim_event_start devolve o instante da trava mais recente da temporada
--    (ou -infinity antes do primeiro jogo).
-- 3. Limite: até 10 simulações novas por pessoa (somando os três modos) desde o último evento. Sai o limite de 3 por
--    modo na temporada; as simulações antigas continuam no ranking.
-- 4. Simulação de antes do último evento fica fechada: não pode mais ser alterada (pode ser apagada).
-- 5. Jogo adiado sem data nova (status 'postponed', enviado sem horário pelo supabase_sync) fica aberto: a trava da
--    data original sai e volta quando a data nova chegar. É a única exceção à regra de que a trava não volta atrás,
--    e só vale para jogo sem placar.

create or replace function public.sim_lock_margin() returns interval
language sql immutable as $$ select interval '30 minutes' $$;

create or replace function public.sim_event_start(p_competition text, p_season int) returns timestamptz
language sql stable security definer set search_path = public as $$
  select coalesce(max(m.kickoff_utc - public.sim_lock_margin()), '-infinity'::timestamptz)
  from sim_matches m
  where m.competition = p_competition and m.season = p_season
    and m.kickoff_utc is not null and m.kickoff_utc - public.sim_lock_margin() <= now();
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

create or replace function public.sim_keep_match_lock() returns trigger
language plpgsql set search_path = public as $$
begin
  new.updated_at := now();
  if old.kickoff_utc is not null and old.kickoff_utc <= now()
     and (new.kickoff_utc is null or new.kickoff_utc > old.kickoff_utc)
     and not (new.status = 'postponed' and new.home_goals is null and old.home_goals is null) then
    new.kickoff_utc := old.kickoff_utc;
  end if;
  return new;
end;
$$;
revoke all on function public.sim_keep_match_lock() from public, anon, authenticated;

revoke all on function public.sim_lock_picks() from public, anon, authenticated;
revoke all on function public.sim_event_start(text, int) from public;
grant execute on function public.sim_event_start(text, int) to anon, authenticated;
