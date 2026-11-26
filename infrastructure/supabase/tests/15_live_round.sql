-- Convivência da 0007_live_round com a 0008: o Ao vivo continua com leitura pública e escrita só pela chave de
-- serviço, e as regras de integridade do placar seguem valendo. Dados SINTÉTICOS (temporada 2099, ids fictícios).
delete from public.live_round_scores where season = 2099;
insert into public.live_round_scores (season, round, match_id, home_goals, away_goals, minute, status) values
  (2099, 38, '2099-synthetic-a-b', 1, 0, 63, 'live'),
  (2099, 38, '2099-synthetic-c-d', null, null, null, 'scheduled');

select t.is(t.count_as('anon', null, 'select count(*) from public.live_round_scores where season = 2099'), 2::bigint, 'anon lê os placares do Ao vivo depois da 0008');
select t.is(t.count_as('authenticated', t.user_id(1), 'select count(*) from public.live_round_scores where season = 2099'), 2::bigint, 'authenticated lê os placares do Ao vivo depois da 0008');
select t.is(t.error_as('anon', null, $q$insert into public.live_round_scores (season, round, match_id, status) values (2099, 38, '2099-synthetic-e-f', 'scheduled')$q$), '42501', 'anon não escreve no Ao vivo');
select t.is(t.error_as('authenticated', t.user_id(1), $q$update public.live_round_scores set home_goals = 5 where season = 2099$q$), '42501', 'authenticated não altera placar do Ao vivo');
select t.is(t.error_as('anon', null, 'truncate public.live_round_scores'), '42501', 'anon não esvazia o Ao vivo (TRUNCATE)');
select t.is(t.error_as('service_role', null, $q$update public.live_round_scores set home_goals = 2 where match_id = '2099-synthetic-a-b'$q$), null, 'service_role atualiza placar do Ao vivo');
select t.throws($q$insert into public.live_round_scores (season, round, match_id, home_goals, away_goals, status) values (2099, 38, '2099-synthetic-g-h', 0, 0, 'scheduled')$q$, '23514', 'jogo que não começou não aceita placar (sem 0 x 0 inventado)');
select t.throws($q$insert into public.live_round_scores (season, round, match_id, home_goals, away_goals, status) values (2099, 38, '2099-synthetic-g-h', 1, 1, 'live')$q$, '23514', 'jogo ao vivo exige o minuto');
delete from public.live_round_scores where season = 2099;
