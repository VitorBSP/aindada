-- RLS e permissões: o que anon, authenticated (cada pessoa) e service_role podem ler e escrever.
select t.reset(true);
select t.user_id(1), t.user_id(2);
insert into public.sim_profiles (user_id, nickname, show_in_ranking) values (t.user_id(1), 'Ana', true), (t.user_id(2), 'Beto', false);
insert into public.sim_contacts (user_id, email) values (t.user_id(1), 'ana@example.invalid'), (t.user_id(2), 'beto@example.invalid');
insert into public.sim_simulations (user_id, competition, season, mode, payload) values
  (t.user_id(1), 'synthetic-liga', 2026, 'vencedor', '{"picks": {"o1": "H"}}'),
  (t.user_id(2), 'synthetic-liga', 2026, 'vencedor', '{"picks": {"o1": "A"}}');

select t.is(t.error_as('anon', null, 'select 1 from public.sim_simulations'), '42501', 'anon não lê sim_simulations');
select t.is(t.error_as('anon', null, 'select 1 from public.sim_profiles'), '42501', 'anon não lê sim_profiles');
select t.is(t.error_as('anon', null, 'select 1 from public.sim_contacts'), '42501', 'anon não lê sim_contacts');
select t.is(t.error_as('anon', null, 'select 1 from public.sim_scores'), '42501', 'anon não lê a visão sim_scores');
select t.is(t.error_as('authenticated', t.user_id(1), 'select 1 from public.sim_scores'), '42501', 'authenticated não lê a visão sim_scores');
select t.is(t.error_as('anon', null, $q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (gen_random_uuid(), 'synthetic-liga', 2026, 'vencedor', '{}')$q$), '42501', 'anon não escreve sim_simulations');

select t.is(t.count_as('authenticated', t.user_id(1), 'select count(*) from public.sim_simulations'), 1::bigint, 'dono lê só a própria simulação (sim_simulations)');
select t.is(t.count_as('authenticated', t.user_id(1), 'select count(*) from public.sim_simulations where user_id = ''' || t.user_id(2) || ''''), 0::bigint, 'dono não vê a simulação de outra pessoa');
select t.is(t.count_as('authenticated', t.user_id(1), 'select count(*) from public.sim_profiles'), 1::bigint, 'dono lê só o próprio perfil');
select t.is(t.count_as('authenticated', t.user_id(1), 'select count(*) from public.sim_contacts'), 1::bigint, 'dono lê só o próprio e-mail de avisos');
select t.is(t.count_as('authenticated', t.user_id(2), $q$select count(*) from public.sim_contacts where email like 'ana%'$q$), 0::bigint, 'o e-mail de uma pessoa não aparece para outra');
select t.is(t.error_as('authenticated', t.user_id(1), format($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (%L, 'synthetic-liga', 2026, 'vencedor', '{}')$q$, t.user_id(2))), '42501', 'dono não cria simulação em nome de outra pessoa (RLS)');
select t.is(t.count_as('authenticated', t.user_id(1), $q$with u as (update public.sim_simulations set assist = true returning 1) select count(*) from u$q$), 1::bigint, 'dono altera a própria simulação (só a dele)');
select t.is(t.count_as('authenticated', t.user_id(1), $q$with d as (delete from public.sim_profiles where nickname = 'Beto' returning 1) select count(*) from d$q$), 0::bigint, 'dono não apaga o perfil de outra pessoa');

select t.ok(t.count_as('anon', null, 'select count(*) from public.sim_matches') > 0, 'anon lê os jogos (leitura pública)');
select t.ok(t.count_as('anon', null, 'select count(*) from public.sim_standings') > 0, 'anon lê a tabela (leitura pública)');
select t.is(t.error_as('anon', null, $q$update public.sim_matches set status = 'cancelled'$q$), '42501', 'anon não altera jogos');
select t.is(t.error_as('authenticated', t.user_id(1), $q$delete from public.sim_standings$q$), '42501', 'authenticated não apaga a tabela de classificação');

select t.is(t.error_as('anon', null, 'select 1 from public.sim_private'), '42501', 'anon não lê o sal do ruído (sim_private)');
select t.is(t.error_as('authenticated', t.user_id(1), 'select 1 from public.sim_private'), '42501', 'authenticated não lê o sal do ruído');
select t.is(t.error_as('service_role', null, 'select 1 from public.sim_private'), '42501', 'nem a chave de serviço lê o sal do ruído');
select t.is(t.error_as('anon', null, $q$select public.sim_noise('x')$q$), '42501', 'anon não chama sim_noise');
select t.is(t.error_as('authenticated', t.user_id(1), $q$select public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', '{}')$q$), '42501', 'authenticated não chama sim_final_order_ok');

select t.is(t.error_as('anon', null, $q$select public.sim_consensus('synthetic-liga', 2026)$q$), null, 'anon chama sim_consensus');
select t.is(t.error_as('anon', null, $q$select public.sim_community('synthetic-liga', 2026)$q$), null, 'anon chama sim_community');
select t.is(t.error_as('anon', null, $q$select * from public.sim_ranking('synthetic-liga', 2026, 'vencedor')$q$), null, 'anon chama sim_ranking');
select t.is(t.error_as('anon', null, $q$select * from public.sim_my_scores('synthetic-liga', 2026)$q$), '42501', 'anon não chama sim_my_scores');
select t.is(t.error_as('anon', null, $q$select * from public.sim_notification_list('synthetic-liga', 2026)$q$), '42501', 'anon não chama sim_notification_list');
select t.is(t.error_as('authenticated', t.user_id(1), $q$select * from public.sim_notification_list('synthetic-liga', 2026)$q$), '42501', 'authenticated não chama sim_notification_list');
select t.is(t.error_as('service_role', null, $q$select * from public.sim_notification_list('synthetic-liga', 2026)$q$), null, 'service_role chama sim_notification_list');
select t.is(t.error_as('anon', null, 'select public.sim_lock_picks()'), '42501', 'anon não chama a função do gatilho de trava');
select t.is(t.error_as('anon', null, 'select public.sim_delete_me()'), '42501', 'anon não chama sim_delete_me');

-- Ranking: só quem marcou "aparecer no ranking" e tem apelido.
insert into public.sim_simulations (user_id, competition, season, mode, payload) values
  (t.user_id(1), 'synthetic-liga', 2026, 'placar', '{"picks": {}}');
select t.is((select count(*) from public.sim_ranking('synthetic-liga', 2026, 'vencedor') where nickname = 'Beto'), 0::bigint, 'sim_ranking não mostra quem não marcou o ranking');
