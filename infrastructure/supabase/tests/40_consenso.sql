-- sim_consensus, sim_community, sim_final_order_ok (0008): mínimo, ruído limitado e determinístico, tabela final
-- conferida com os palpites e com sim_standings.
select t.reset(false);

-- ---- sim_final_order_ok. Pontos de hoje: a 3, c 1, d 1, demais 0. Palpites (Vencedor) nos 7 jogos que faltam:
-- o1 a-c H, o2 b-d A, o3 e-g H, o4 f-h H, o5 a-d H, s1 e-f H, s2 g-h H  =>  a 9, e 6, d 4, f 3, g 3, c 1, b 0, h 0.
create function t.picks() returns jsonb language sql as
  $$ select '{"o1":"H","o2":"A","o3":"H","o4":"H","o5":"H","s1":"H","s2":"H"}'::jsonb $$;
create function t.payload(p_order text[]) returns jsonb language sql as
  $$ select jsonb_build_object('picks', t.picks(), 'sampled', '[]'::jsonb, 'final_order', to_jsonb(p_order)) $$;

select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['a','e','d','f','g','c','b','h'])), true, 'final_order igual ao calculado dos palpites é aceito');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['a','e','d','g','f','c','h','b'])), true, 'empates em pontos aceitam qualquer ordem (sem critério de desempate no banco)');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['e','a','d','f','g','c','b','h'])), false, 'ordem que põe 6 pontos acima de 9 é recusada');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['c','a','e','d','f','g','b','h'])), false, 'campeão forjado (c, com 1 ponto) é recusado');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', jsonb_set(t.payload(array['a','e','d','f','g','c','b','h']), '{picks}', t.picks() - 's2')), false, 'palpite faltando em jogo que falta é recusado');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['a','e','d','f','g','c','b'])), false, 'ordem incompleta é recusada');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['a','e','d','f','g','c','b','b'])), false, 'ordem com clube repetido é recusada');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', jsonb_set(t.payload(array['a','e','d','f','g','c','b','h']), '{final_order}', 'null')), false, 'sem final_order não conta');
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'placar',
  jsonb_build_object('picks', '{"o1":[1,0],"o2":[0,2],"o3":[3,1],"o4":[2,0],"o5":[1,0],"s1":[1,0],"s2":[1,0]}'::jsonb,
                     'final_order', '["a","e","d","f","g","c","b","h"]'::jsonb)), true, 'Placar exato: o resultado dos placares palpitados dá a mesma tabela');
update public.sim_standings set max_points = 8 where club_id = 'a';
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['a','e','d','f','g','c','b','h'])), false, 'clube acima de max_points em sim_standings é recusado');
select t.refresh_standings();
-- o1 (a x c) termina 1 x 0: igual ao palpite H, a tabela continua valendo; termina 0 x 1: o palpite fica furado.
update public.sim_matches set status = 'finished', home_goals = 1, away_goals = 0 where match_id = 'o1';
select t.refresh_standings();
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['a','e','d','f','g','c','b','h'])), true, 'jogo que terminou como o palpite não invalida a tabela');
update public.sim_matches set home_goals = 0, away_goals = 1 where match_id = 'o1';
select t.refresh_standings();
select t.is(public.sim_final_order_ok('synthetic-liga', 2026, 'vencedor', t.payload(array['a','e','d','f','g','c','b','h'])), false, 'jogo que terminou diferente do palpite deixa a tabela antiga de fora');
select t.reset(false);

-- ---- Mínimo de pessoas e precisão. 49 pessoas com a mesma tabela (= classificação de hoje): nada sai.
create function t.populate_classification(p_people int) returns void language sql as $$
  select t.user_id(g) from generate_series(1, p_people) g;
  insert into public.sim_simulations (user_id, competition, season, mode, payload)
  select t.user_id(g), 'synthetic-liga', 2026, 'classificacao', '{"order": ["a","c","d","b","e","f","g","h"]}'
  from generate_series(1, p_people) g;
$$;
select t.populate_classification(49);
select t.is(public.sim_consensus('synthetic-liga', 2026) -> 'clubs', '[]'::jsonb, 'com 49 pessoas o consenso não publica clubes (mínimo 50)');
select t.is((public.sim_consensus('synthetic-liga', 2026) ->> 'users_at_least')::int, 40, 'a contagem sai em faixas de 10 (49 vira 40)');
select t.populate_classification(50);
select t.is(jsonb_array_length(public.sim_consensus('synthetic-liga', 2026) -> 'clubs'), 8, 'com 50 pessoas o consenso publica os 8 clubes');
select t.is((public.sim_consensus('synthetic-liga', 2026) ->> 'min_users')::int, 50, 'min_users publicado é 50');

-- Determinístico: a mesma consulta devolve o mesmo resultado.
select t.is(public.sim_consensus('synthetic-liga', 2026), public.sim_consensus('synthetic-liga', 2026), 'mesma consulta, mesmo resultado (ruído fixo por sal e nome)');

-- Erro limitado: |publicado - verdadeiro| <= 3 * (clubes - 1) / 50 + passo de 0,5 / 2 (posição) e 3 / 50 + 0,025 (frações).
with published as (
  select c ->> 'club_id' as club_id, (c ->> 'average_position')::numeric as pos, (c ->> 'champion')::numeric as champion, (c ->> 'relegated')::numeric as relegated
  from jsonb_array_elements(public.sim_consensus('synthetic-liga', 2026) -> 'clubs') c),
truth as (select * from (values ('a', 1, 1, 0), ('c', 2, 0, 0), ('d', 3, 0, 0), ('b', 4, 0, 0), ('e', 5, 0, 1), ('f', 6, 0, 1), ('g', 7, 0, 1), ('h', 8, 0, 1)) v(club_id, pos, champion, relegated))
select t.ok(bool_and(abs(p.pos - v.pos) <= 3 * 7 / 50.0 + 0.25 + 0.0001), 'posição média publicada fica a no máximo 3 pessoas de ruído (3 x 7 / 50) + arredondamento do valor verdadeiro')
from published p join truth v using (club_id);
with published as (
  select c ->> 'club_id' as club_id, (c ->> 'champion')::numeric as champion, (c ->> 'relegated')::numeric as relegated
  from jsonb_array_elements(public.sim_consensus('synthetic-liga', 2026) -> 'clubs') c),
truth as (select * from (values ('a', 1, 0), ('c', 0, 0), ('d', 0, 0), ('b', 0, 0), ('e', 0, 1), ('f', 0, 1), ('g', 0, 1), ('h', 0, 1)) v(club_id, champion, relegated))
select t.ok(bool_and(abs(p.champion - v.champion) <= 3 / 50.0 + 0.025 + 0.0001 and abs(p.relegated - v.relegated) <= 3 / 50.0 + 0.025 + 0.0001),
            'campeão e rebaixado publicados ficam a no máximo 3/50 + 0,025 do valor verdadeiro')
from published p join truth v using (club_id);
select t.ok((select bool_and((c ->> 'average_position')::numeric * 2 = round((c ->> 'average_position')::numeric * 2)
                           and (c ->> 'champion')::numeric * 20 = round((c ->> 'champion')::numeric * 20))
            from jsonb_array_elements(public.sim_consensus('synthetic-liga', 2026) -> 'clubs') c), 'posição média em passos de 0,5 e frações em passos de 0,05');

-- O sal muda o ruído: com sais diferentes o resultado não é sempre o mesmo.
create temp table salts as select (public.sim_consensus('synthetic-liga', 2026) -> 'clubs')::text as clubs;
do $$ declare i int; begin
  for i in 1..8 loop
    update public.sim_private set value = md5(i::text) where name = 'noise_salt';
    insert into salts select (public.sim_consensus('synthetic-liga', 2026) -> 'clubs')::text;
  end loop;
end $$;
select t.ok((select count(distinct clubs) from salts) > 1, 'sais diferentes dão ruídos diferentes (o sal é o que o atacante não conhece)');
update public.sim_private set value = 'sal-de-teste' where name = 'noise_salt';

-- Classificação malformada gravada por fora do gatilho não entra.
alter table public.sim_simulations disable trigger sim_lock_picks;
update public.sim_simulations set payload = '{"order": ["a","a","a"]}' where user_id in (select t.user_id(g) from generate_series(1, 10) g);
alter table public.sim_simulations enable trigger sim_lock_picks;
select t.is((public.sim_consensus('synthetic-liga', 2026) ->> 'users_at_least')::int, 40, 'ordem malformada gravada fora do gatilho é ignorada no consenso (40 válidas)');
select t.is(public.sim_consensus('synthetic-liga', 2026) -> 'clubs', '[]'::jsonb, 'com 40 pessoas válidas o consenso volta a esconder os clubes');

-- ---- Achado 6 no consenso: 49 tabelas de Vencedor válidas + 11 forjadas de outras pessoas.
select t.reset(false);
select t.user_id(g) from generate_series(1, 60) g;
insert into public.sim_simulations (user_id, competition, season, mode, payload)
select t.user_id(g), 'synthetic-liga', 2026, 'vencedor', t.payload(case when g <= 49 then array['a','e','d','f','g','c','b','h'] else array['c','a','e','d','f','g','b','h'] end)
from generate_series(1, 60) g;
select t.is((public.sim_consensus('synthetic-liga', 2026) ->> 'users_at_least')::int, 40, 'consenso não conta as 11 tabelas de Vencedor que não batem com os palpites (49 válidas -> faixa 40)');
select t.is(public.sim_consensus('synthetic-liga', 2026) -> 'clubs', '[]'::jsonb, '49 pessoas válidas ainda ficam abaixo do mínimo');
update public.sim_simulations set payload = t.payload(array['a','e','d','f','g','c','b','h']) where user_id in (select t.user_id(g) from generate_series(50, 60) g);
select t.is((public.sim_consensus('synthetic-liga', 2026) ->> 'users_at_least')::int, 60, 'corrigidas as 11, as 60 entram (faixa 60)');
select t.is(jsonb_array_length(public.sim_consensus('synthetic-liga', 2026) -> 'clubs'), 8, 'com 60 tabelas válidas o consenso publica os clubes');

-- ---- sim_community: mínimo 50, sorteados do modelo não contam, ruído limitado.
select t.reset(false);
select t.user_id(g) from generate_series(1, 50) g;
insert into public.sim_simulations (user_id, competition, season, mode, payload)
select t.user_id(g), 'synthetic-liga', 2026, 'vencedor', '{"picks": {"o1": "H"}}' from generate_series(1, 49) g;
select t.is(public.sim_community('synthetic-liga', 2026) -> 'matches', '{}'::jsonb, 'com 49 pessoas no jogo, sim_community não publica nada');
insert into public.sim_simulations (user_id, competition, season, mode, payload) values (t.user_id(50), 'synthetic-liga', 2026, 'vencedor', '{"picks": {"o1": "H"}}');
select t.ok((public.sim_community('synthetic-liga', 2026) -> 'matches' -> 'o1' ->> 'H')::numeric between 0.90 and 1, 'com 50 pessoas votando H, H publicado fica entre 0,90 e 1 (ruído de até 3 votos de 50 + passo de 0,05)');
select t.ok((public.sim_community('synthetic-liga', 2026) -> 'matches' -> 'o1' ->> 'D')::numeric between 0 and 0.10
        and (public.sim_community('synthetic-liga', 2026) -> 'matches' -> 'o1' ->> 'A')::numeric between 0 and 0.10, 'empate e visitante, com 0 votos, ficam entre 0 e 0,10');
select t.is((public.sim_community('synthetic-liga', 2026) -> 'matches' -> 'o1' ->> 'users_at_least')::int, 50, 'contagem de pessoas em faixa de 10');
update public.sim_simulations set payload = '{"picks": {"o1": "H"}, "sampled": ["o1"]}';
select t.is(public.sim_community('synthetic-liga', 2026) -> 'matches', '{}'::jsonb, 'jogos sorteados pelo modelo não contam como palpite de pessoas');
