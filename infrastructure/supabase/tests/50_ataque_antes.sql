-- Baseline: o consenso da 0004 (mínimo 30, arredondado a 0,05, sem ruído) deixa deduzir o voto da 30ª pessoa.
select t.ok(a.hits = a.trials, format('ANTES da 0007: com %s contas falsas o atacante acerta o voto da vítima em %s de %s rodadas (f=%s)',
                                      a.fakes, a.hits, a.trials, a.tuned_f))
from t.attack_community(40) a;
