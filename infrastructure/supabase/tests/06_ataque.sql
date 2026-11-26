-- Medida do achado A (Agente 06): quanto uma pessoa com (mínimo - 1) contas próprias aprende sobre o voto da última.
--
-- Atacante: min_users - 1 contas falsas votam H ou A no mesmo jogo; ele escolhe quantas votam H (f) de modo que, SEM
-- ruído, 1 voto a mais em H mude o número publicado, e depois adivinha o voto da vítima (H ou A) pelo número publicado
-- mais próximo do que o modelo sem ruído prevê. Com ruído secreto, o sal é sorteado de novo em cada rodada, que é o
-- que o atacante não conhece. Devolve a taxa de acerto: 1,0 = deduz sempre; 0,5 = chute.
create function t.attack_community(p_trials int) returns table (fakes int, users int, tuned_f int, hits int, trials int)
language plpgsql as $$
declare
  min_users int;
  n int;
  f int; tuned int;
  victim uuid;
  model_without numeric; model_with numeric; observed numeric;
  vote text; guessed text; hit int := 0; i int;
  has_salt boolean := to_regclass('public.sim_private') is not null;
begin
  perform t.reset(false);
  min_users := (public.sim_community('synthetic-liga', 2026) ->> 'min_users')::int;
  n := min_users;
  -- contas falsas 1..n-1 e vítima n
  for f in 1..n loop
    perform t.user_id(f);
    insert into public.sim_simulations (user_id, competition, season, mode, payload)
    values (t.user_id(f), 'synthetic-liga', 2026, 'vencedor', '{"picks": {"o1": "A"}}');
  end loop;
  victim := t.user_id(n);
  -- f: quantas contas falsas votam H, escolhido pelo modelo sem ruído (arredondamento a 0,05)
  for f in 0..n - 1 loop
    if round(f::numeric / n * 20) / 20 <> round((f + 1)::numeric / n * 20) / 20 then tuned := f; exit; end if;
  end loop;
  update public.sim_simulations set payload = '{"picks": {"o1": "H"}}'
   where user_id in (select t.user_id(g) from generate_series(1, tuned) g);
  model_without := round(tuned::numeric / n * 20) / 20;
  model_with := round((tuned + 1)::numeric / n * 20) / 20;
  for i in 1..p_trials loop
    if has_salt then execute $q$update public.sim_private set value = md5(random()::text || clock_timestamp()::text) where name = 'noise_salt'$q$; end if;
    vote := case when random() < 0.5 then 'H' else 'A' end;
    update public.sim_simulations set payload = jsonb_build_object('picks', jsonb_build_object('o1', vote))
     where user_id = victim;
    observed := (public.sim_community('synthetic-liga', 2026) -> 'matches' -> 'o1' ->> 'H')::numeric;
    -- o voto H da vítima soma 1 ao H das contas falsas; A não soma
    guessed := case when abs(observed - model_with) < abs(observed - model_without) then 'H'
                    when abs(observed - model_with) > abs(observed - model_without) then 'A'
                    else case when random() < 0.5 then 'H' else 'A' end end;
    if guessed = vote then hit := hit + 1; end if;
  end loop;
  return query select n - 1, n, tuned, hit, p_trials;
end $$;
