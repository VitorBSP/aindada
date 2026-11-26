-- Medida do achado A depois da 0008: o mesmo atacante (49 contas falsas calibradas sem ruído) contra o consenso novo.
-- 400 rodadas com sal sorteado de novo e voto da vítima sorteado. Sem informação, o acerto esperado é 0,50; o
-- desvio-padrão de 400 lances é 0,025, então 0,60 está a 4 desvios do chute.
create temp table attack as select * from t.attack_community(400);
select t.ok(hits::numeric / trials <= 0.65,
            format('DEPOIS da 0008: com %s contas falsas o atacante acerta %s de %s rodadas (%s%%; f=%s); antes, 100%%', fakes, hits, trials, round(hits * 100.0 / trials), tuned_f))
from attack;
select t.ok(users = 50, 'o ataque já precisa de 49 contas falsas (mínimo 50), contra 29 antes') from attack;
