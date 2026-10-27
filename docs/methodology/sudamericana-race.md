# Corrida pela Sul-Americana (Agente 02)

Código: `src/brasileirao/simulation/summary.py` (`continental_probabilities`, `sudamericana_race`).
Campo publicado: `teams[].sudamericana_race` no snapshot (schema 1.1), ao lado da faixa já existente
`teams[].sudamericana` (`min`, `max`, `by_scenario`).

## Problema

A vaga na Sul-Americana (Art. 7º: os seis melhores clubes fora da Libertadores) depende de três
torneios externos ainda abertos: campeão da Libertadores, campeão da Sul-Americana e campeão/vice da
Copa do Brasil. Cada combinação possível é um cenário (`competition_rules/scenarios.py`). A regra de
integridade proíbe dar uma chance a cada cenário, então não existe "a" probabilidade de Sul-Americana:
existe uma por cenário. Para montar uma classificação da corrida é preciso uma ordem que não dependa
de pesos para os cenários.

## Medidas publicadas

| Campo | Significado | É probabilidade? |
|---|---|---|
| `sudamericana.min` / `max` | menor e maior P(vaga \| cenário) entre os cenários | sim, condicional ao cenário |
| `sudamericana_race.all_scenarios` | P(o clube fica com a vaga **qualquer que seja** o cenário) | sim, sem cenário |
| `sudamericana_race.any_scenario` | P(o clube fica com a vaga **em pelo menos um** cenário) | sim, sem cenário |
| `sudamericana_race.midpoint` | (mín. + máx.) / 2, o centro da faixa | não: só ordena |
| `sudamericana_race.rank` | posição na classificação da corrida (1 = mais perto da vaga) | não |
| `sudamericana_race.rank_best` / `rank_worst` | melhor e pior posição do clube quando os clubes são ordenados por P(vaga \| cenário) em cada cenário | não |

`all_scenarios` e `any_scenario` são calculadas por simulação: numa temporada simulada, a vaga vale
"em todos os cenários" se o clube a recebe nos 32; vale "em algum" se a recebe em pelo menos um. Por
construção, `all_scenarios ≤ min ≤ max ≤ any_scenario`. Elas respondem perguntas que o torcedor faz
sem depender de nenhum torneio externo: "qual a chance de a vaga já estar garantida pela tabela?" e
"qual a chance de o clube ainda estar no páreo depois dos torneios externos?".

## Ordenação

`rank` ordena por `midpoint` (decrescente), depois `max`, depois `all_scenarios`, depois posição
final esperada e, por fim, `club_id`. Empates numéricos são comparados com 12 casas decimais.

Por que o centro da faixa e não a média entre cenários: a média trata cada cenário enumerado como
igualmente provável, e a enumeração não é equilibrada (com as semifinais da Copa em aberto há oito
combinações campeão/vice para cada par Libertadores/Sul-Americana). O centro da faixa depende só dos
extremos e não muda se um cenário for listado duas vezes ou desdobrado em outros. Ele não é
apresentado como chance; a interface deve exibir a faixa (`min`–`max`) e usar `midpoint` e `rank`
apenas para ordenar.

Exemplo ilustrativo (números inventados): o Clube A tem faixa 50%–90% e o Clube B 0%–80%. O Clube A
fica à frente (centro 70% contra 40%). O Clube B tem `all_scenarios = 0` porque, em algum cenário
(por exemplo, se ele próprio ganhar um torneio externo), vai à Libertadores e sai da corrida.

## Faixa de posições

A posição que dá vaga muda com o cenário e com a própria simulação (um campeão da Copa do Brasil que
termina em 9º, por exemplo, empurra a zona da Sul-Americana uma posição para baixo). Por isso a
medida é a vaga efetivamente alocada pelo regulamento em cada cenário, e não uma faixa fixa de
posições.

## Implementação e desempenho

`allocate_slots` (Agente 03) só distingue os clubes citados nos cenários externos; os demais
entram apenas pela posição final. A agregação calcula as vagas uma vez por arranjo de posições
desses clubes citados (uma classificação canônica por arranjo) e lê o resultado pela posição de cada
clube em cada simulação. O resultado é idêntico à aplicação direta de `allocate_slots` a cada
classificação simulada (teste `tests/unit/test_sudamericana_race.py`; conferido também na base
real com 10 mil simulações, diferença máxima 0). Se o Agente 03 passar a distinguir outros clubes na
alocação (por exemplo, um clube impedido de disputar torneios), esses clubes precisam entrar no
conjunto de citados em `_external_clubs`.

Custo medido (2026-10-27, 61 jogos restantes, 32 cenários): com 10 mil simulações a agregação caiu
de ~6 s (uma chamada de `allocate_slots` por classificação única e cenário) para ~0,7 s; com 100 mil,
todo o resumo por clube (`build_team_summaries`) leva ~4 s.
