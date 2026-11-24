-- Trava de palpites (sim_lock_picks, versão da 0006): jogo iniciado, ranked_order, imutáveis, limite por evento.
select t.reset(true);
select t.user_id(g) from generate_series(1, 3) g;
insert into public.sim_matches (competition, season, match_id, round, home_id, away_id, kickoff_utc, status)
values ('synthetic-liga', 2026, 's3', 2, 'a', 'b', now() + interval '45 minutes', 'scheduled');

-- Palpites: só jogo aberto, formato válido e jogo existente entram.
insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(1), 'synthetic-liga', 2026, 'vencedor',
  '{"picks": {"s1": "H", "s2": "H", "f1": "H", "o1": "H", "o2": "X", "zzz": "H", "s3": "A"}, "evil": 1}');
select t.is((select array_agg(k order by k) from public.sim_simulations s, jsonb_object_keys(s.payload -> 'picks') k where user_id = t.user_id(1)),
            array['o1', 's3'], 'só entram palpites de jogo aberto (a 45 min do pontapé), válido e existente');
select t.ok(not exists (select 1 from public.sim_simulations where payload ? 'evil'), 'chaves desconhecidas do payload são descartadas');

-- Jogo que começou ou trava em menos de 30 min (margem) não aceita palpite novo.
select t.is((select payload -> 'picks' ? 's1' from public.sim_simulations where user_id = t.user_id(1)), false, 'jogo já iniciado recusa palpite novo');
select t.is((select payload -> 'picks' ? 's2' from public.sim_simulations where user_id = t.user_id(1)), false, 'jogo que começa em 10 min (dentro da margem de 30 min) recusa palpite novo');
select t.is((select payload -> 'picks' ? 'f1' from public.sim_simulations where user_id = t.user_id(1)), false, 'jogo encerrado recusa palpite novo');

-- Palpite antigo de jogo travado é mantido; o de jogo aberto muda.
alter table public.sim_simulations disable trigger sim_lock_picks;
insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(2), 'synthetic-liga', 2026, 'vencedor',
  '{"picks": {"s1": "H", "o1": "H"}}');
alter table public.sim_simulations enable trigger sim_lock_picks;
update public.sim_simulations set payload = '{"picks": {"s1": "A", "o1": "A"}}' where user_id = t.user_id(2);
select t.is((select payload -> 'picks' ->> 's1' from public.sim_simulations where user_id = t.user_id(2)), 'H', 'palpite de jogo iniciado não muda ao salvar de novo');
select t.is((select payload -> 'picks' ->> 'o1' from public.sim_simulations where user_id = t.user_id(2)), 'A', 'palpite de jogo aberto muda');
update public.sim_simulations set payload = '{"picks": {"o1": "A"}}' where user_id = t.user_id(2);
select t.is((select payload -> 'picks' ->> 's1' from public.sim_simulations where user_id = t.user_id(2)), 'H', 'apagar o palpite de jogo iniciado também não vale');

-- Placar: formato [gols, gols].
insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(3), 'synthetic-liga', 2026, 'placar',
  '{"picks": {"o1": [2, 1], "o2": [100, 1], "o3": [1], "o4": ["1", 2], "o5": [0, 0]}}');
select t.is((select array_agg(k order by k) from public.sim_simulations s, jsonb_object_keys(s.payload -> 'picks') k where user_id = t.user_id(3)),
            array['o1', 'o5'], 'Placar exato descarta formato inválido (3 dígitos, tamanho errado, texto)');

-- Classificação: ordem completa, sem repetição, de clubes da temporada, e possível; ranked_order = order (0006).
select t.throws($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(1), 'synthetic-liga', 2026, 'classificacao', '{"order": ["a","c","d","b","e","f","g"]}')$q$, '22023', 'Classificação com clube faltando é recusada');
select t.throws($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(1), 'synthetic-liga', 2026, 'classificacao', '{"order": ["a","a","d","b","e","f","g","h"]}')$q$, '22023', 'Classificação com clube repetido é recusada');
select t.throws($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(1), 'synthetic-liga', 2026, 'classificacao', '{"order": ["a","c","d","b","e","f","g","zz"]}')$q$, '22023', 'Classificação com clube desconhecido é recusada');
update public.sim_standings set max_points = 2 where club_id = 'h';
select t.throws($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(1), 'synthetic-liga', 2026, 'classificacao', '{"order": ["h","a","c","d","b","e","f","g"]}')$q$, '22023', 'Classificação impossível (h, que só chega a 2 pontos, acima de a, que já tem 3) é recusada');
update public.sim_standings set max_points = 6 where club_id = 'h';
insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(1), 'synthetic-liga', 2026, 'classificacao', '{"order": ["a","c","d","b","e","f","g","h"], "evil": 1}');
select t.is((select payload from public.sim_simulations where user_id = t.user_id(1) and mode = 'classificacao'),
            '{"order": ["a","c","d","b","e","f","g","h"], "ranked_order": ["a","c","d","b","e","f","g","h"]}'::jsonb,
            'Classificação válida guarda order e ranked_order (sem trava da temporada na 0006) e nada além');
update public.sim_simulations set payload = '{"order": ["c","a","d","b","e","f","g","h"], "ranked_order": ["h"]}' where user_id = t.user_id(1) and mode = 'classificacao';
select t.is((select payload -> 'ranked_order' from public.sim_simulations where user_id = t.user_id(1) and mode = 'classificacao'),
            '["c","a","d","b","e","f","g","h"]'::jsonb, 'ranked_order acompanha a última ordem salva; o cliente não escolhe o valor');

-- Chaves imutáveis.
select t.throws(format($q$update public.sim_simulations set mode = 'placar' where user_id = %L and mode = 'vencedor'$q$, t.user_id(1)), '42501', 'simulação não troca de modo');
select t.throws(format($q$update public.sim_simulations set user_id = %L where user_id = %L$q$, t.user_id(3), t.user_id(2)), '42501', 'simulação não troca de dono');
select t.throws(format($q$update public.sim_simulations set created_at = now() - interval '1 year' where user_id = %L$q$, t.user_id(2)), '42501', 'simulação não troca a data de criação');

-- Simulação fechada: um jogo travou depois que ela foi salva.
alter table public.sim_simulations disable trigger sim_lock_picks;
update public.sim_simulations set created_at = now() - interval '2 hours' where user_id = t.user_id(3);
alter table public.sim_simulations enable trigger sim_lock_picks;
select t.throws(format($q$update public.sim_simulations set assist = true where user_id = %L$q$, t.user_id(3)), 'P0001', 'simulação anterior ao último evento fica fechada');

-- Limite de 10 por pessoa desde o último evento (o limite de 3 por modo saiu na 0005).
select t.reset(true);
select t.user_id(1), t.user_id(2);
select t.throws(format($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) select %L, 'synthetic-liga', 2026, 'vencedor', '{"picks": {}}' from generate_series(1, 10)$q$, t.user_id(1)), null, '10 simulações de uma pessoa desde o último evento entram (mais que as 3 por modo da 0003)');
select t.throws(format($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (%L, 'synthetic-liga', 2026, 'placar', '{"picks": {}}')$q$, t.user_id(1)), 'P0001', 'a 11ª simulação da mesma pessoa é recusada');
select t.throws(format($q$insert into public.sim_simulations (user_id, competition, season, mode, payload) values (%L, 'synthetic-liga', 2026, 'placar', '{"picks": {}}')$q$, t.user_id(2)), null, 'o limite é por pessoa: outra pessoa ainda salva');
