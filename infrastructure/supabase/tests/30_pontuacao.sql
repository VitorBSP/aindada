-- Pontuação (sim_match_points, sim_pick_max, sim_scores) na versão da 0006.
-- Atenção: a 0003 tinha "só o vencedor = 4" e Vencedor = 4 por acerto; a 0006 trocou para 3 (e 5 no empate).
select t.reset(false);
select t.is(public.sim_match_points('placar', '[2,1]', 2, 1), 10, 'Placar exato: 10');
select t.is(public.sim_match_points('placar', '[2,0]', 2, 1), 7, 'vencedor e gols do vencedor: 7');
select t.is(public.sim_match_points('placar', '[3,2]', 2, 1), 6, 'vencedor e diferença de gols: 6');
select t.is(public.sim_match_points('placar', '[4,1]', 2, 1), 5, 'vencedor e gols do perdedor: 5');
select t.is(public.sim_match_points('placar', '[2,2]', 1, 1), 5, 'empate certo com outro placar: 5');
select t.is(public.sim_match_points('placar', '[1,1]', 1, 1), 10, 'empate com placar exato: 10');
select t.is(public.sim_match_points('placar', '[3,0]', 2, 1), 3, 'só o vencedor: 3 (era 4 na 0003)');
select t.is(public.sim_match_points('placar', '[1,2]', 2, 1), 2, 'placar invertido: 2');
select t.is(public.sim_match_points('placar', '[2,1]', 1, 1), 0, 'palpite de vitória num empate: 0');
select t.is(public.sim_match_points('vencedor', '"H"', 2, 1), 3, 'Vencedor: vitória certa vale 3 (era 4 na 0003)');
select t.is(public.sim_match_points('vencedor', '"D"', 1, 1), 5, 'Vencedor: empate certo vale 5');
select t.is(public.sim_match_points('vencedor', '"A"', 2, 1), 0, 'Vencedor: erro vale 0');
select t.is(public.sim_match_points('vencedor', '"X"', 2, 1), 0, 'palpite malformado vale 0, sem erro');
select t.is(public.sim_match_points('placar', '[2,1]', null, null), 0, 'jogo sem placar vale 0 (nunca 0 x 0)');
select t.is(public.sim_match_points('placar', '["2", 1]', 2, 1), 0, 'placar com texto vale 0');
select t.is(public.sim_pick_max('placar', '[0,0]'), 10, 'máximo do Placar exato: 10');
select t.is(public.sim_pick_max('vencedor', '"D"'), 5, 'máximo do Vencedor em empate: 5');
select t.is(public.sim_pick_max('vencedor', '"H"'), 3, 'máximo do Vencedor em vitória: 3');
select t.is(public.sim_pick_max('vencedor', '"X"'), 0, 'máximo de palpite inválido: 0');

-- sim_scores: f1 terminou 2 x 1 e f2 0 x 0. Palpites de jogo encerrado só entram com o gatilho desligado (como se
-- tivessem sido salvos antes do jogo).
select t.user_id(1), t.user_id(2);
alter table public.sim_simulations disable trigger sim_lock_picks;
insert into public.sim_simulations (user_id, competition, season, mode, payload) values
  (t.user_id(1), 'synthetic-liga', 2026, 'placar', '{"picks": {"f1": [2,1], "f2": [1,1], "o1": [3,0]}}'),
  (t.user_id(2), 'synthetic-liga', 2026, 'vencedor', '{"picks": {"f1": "H", "f2": "D"}}');
alter table public.sim_simulations enable trigger sim_lock_picks;
select t.is((select (points, max_points, exact_hits, scored_picks) from public.sim_scores where mode = 'placar'), (15, 20, 1, 2),
            'sim_scores Placar exato: 10 + 5, máximo 20, 1 exato, 2 jogos pontuados (jogo aberto não pontua)') ;
select t.is((select (points, max_points, exact_hits, scored_picks) from public.sim_scores where mode = 'vencedor'), (8, 8, 2, 2),
            'sim_scores Vencedor: 3 + 5, máximo 8');

-- Classificação igual à tabela de hoje: 3x8 posições + 10 campeão + 3x4 G4 + 5x4 rebaixados = 66; x 7 jogos que faltam.
insert into public.sim_simulations (user_id, competition, season, mode, payload) values
  (t.user_id(1), 'synthetic-liga', 2026, 'classificacao', '{"order": ["a","c","d","b","e","f","g","h"]}');
select t.is((select (points, max_points, scored_picks) from public.sim_scores where mode = 'classificacao'), (66 * 7, 102 * 7, 7),
            'sim_scores Classificação: 66 pontos x 7 jogos que faltavam (máximo 102 x 7)');
