# Modelo estatístico (Agente 02)

## Ratings (estado de cada clube)

| Componente | Definição | Código |
|---|---|---|
| Elo | Escala 1500. Expectativa com mando H. Passo `K · G(saldo) · (S − E)`, com `G` igual a 1, 1,5 ou (11+N)/8 | `ratings/elo.py` |
| Ataque/defesa | `log λ_mand = base + mando + atq_m − def_v` e `log λ_vis = base + atq_v − def_m`. Passo de gradiente da log-verossimilhança de Poisson após cada jogo, o que ajusta pela força do adversário | `ratings/attack_defense.py` |
| Forma | Média exponencial de (resultado − expectativa Elo), ou seja, desempenho ajustado pelo adversário | `ratings/history.py` |
| Entre temporadas | Regressão à média (Elo 30%, ataque/defesa 15%) e recentralização | `RatingEngine.start_season` |
| Promovidos | Recebem a média dos clubes que saíram da liga na temporada anterior | `RatingEngine.start_season` |

Política de jogos simultâneos: todas as partidas de uma data usam o estado da véspera e as
atualizações são somadas ao fim da data. O resultado independe da ordem de processamento
(teste `test_simultaneous_matches_independent_of_processing_order`).

### Exemplos do Elo com dados reais (`ratings/examples.py`)

Para a seção "Como calculamos", cada competição publica `data/elo-examples.json` (esquema 2.0) com **um confronto
direto** entre os dois clubes do par de `EXAMPLE_CLUBS`: o mais recente até a data de referência, na temporada atual
ou, se não houver, na anterior (na Champions, só jogos da própria Champions). O arquivo traz:

- `match`: a conta passo a passo do confronto (`variação = K × M × (resultado − esperado)`);
- para cada lado, `previous_season` (a temporada anterior à atual) e `ledger`, que explica o Elo antes do jogo:
  - `seasons`: cada temporada do clube na competição, com `entry_elo + net = end_elo` e `newcomer_rule` quando ele
    entrou como clube novo;
  - `current`: a entrada da temporada do confronto (regressão: `1500 + (fim − média) × (1 − regressão)` nas ligas e
    `média do país + (fim − média do país) × (1 − regressão)` na Champions, ou a regra de clube novo), os jogos até a
    véspera com a variação de cada um e `entry.after + net_until = elo_before_match`;
  - `weights`: Elo ≈ 1500 + (entrada da última chegada como clube novo − 1500) × (1 − r)^anos + Σ saldo da temporada
    × (1 − r)^anos. A entrada como clube novo substitui o rating, então o que veio antes dela não conta. Nas ligas, a
    média da divisão fica em 1500 a cada virada (soma zero e clube novo com a média de quem saiu), e a decomposição
    fecha com o motor com diferença abaixo de 0,01 ponto. Na Champions, a regressão vai para a média de cada país,
    que se move, e a diferença fica em alguns pontos.

Notas de implementação:

- Os números saem de subclasses instrumentadas do motor (`TracedRatingEngine`, `TracedGlobalElo`), que só registram o
  estado antes e depois de cada passo. Cada variação é refeita com `ratings/elo.py`. Os saldos são `fim − entrada`
  (subtração exata entre valores próximos) e são conferidos com a soma jogo a jogo. Divergência levanta
  `ExampleMismatchError`: o arquivo não é gravado e a previsão segue.
- Os testes com dados sintéticos (`tests/unit/test_elo_examples.py`) conferem:
  - o estado final igual ao de `build_state_as_of` e do `GlobalElo`;
  - a variação do confronto igual à mudança do Elo no motor sem instrumentação;
  - `entry_elo + net = end_elo` e `entry.after + net_until = elo_before_match` sem tolerância.
- Data de referência e versões de dados e modelo são as do forecast (ou snapshot) publicado no mesmo site.
- Na Série B de 2026, a fonte não traz datas nem rodadas: o confronto e os jogos até a véspera seguem a ordem
  aproximada usada pelo motor (`date_is_approximate: true`, `round: null`).
- São números de clubes reais: o arquivo fica só nas pastas de dados ignoradas pelo git (decisão B1), nunca em
  `methods.json`.

## Modelo de gols

- **Modelo A (em produção)**: duas regressões de Poisson (scikit-learn, α = 1e-3).
  - Gols do mandante ~ diferença de Elo + log-taxa de ataque/defesa do mandante.
  - Gols do visitante ~ diferença de Elo + log-taxa de ataque/defesa do visitante.
- **Modelo B**: correção Dixon-Coles com ρ estimado por máxima verossimilhança. Está implementado e
  avaliado, sem ganho até agora.
- **Inflação de empates** (opcional, `draw_inflation`): diagonal da matriz de placares × (1 + δ),
  com δ por máxima verossimilhança no treino. Corrige a taxa média de empates, mas não foi adotada
  por falta de ganho nas métricas (ver `validation.md`, etapa 2).
- **Dispersão dos gols** (`goal_dispersion`, em produção desde `cmp-elo-ad-0.2.0`, 2026-10-27): as
  marginais de gols deixam de ser Poisson e passam a ser Conway-Maxwell-Poisson, P(k) ∝ λᵏ / (k!)^ν. O λ de cada jogo é escolhido
  para que a média seja exatamente o gol esperado da regressão, então o ν muda só a **forma** da
  distribuição, não os gols esperados. ν = 1 é a Poisson; ν > 1 dá variância menor que a média
  (subdispersão); ν < 1, maior (superdispersão, o caso da binomial negativa). O ν é estimado por
  máxima verossimilhança do placar exato na janela de treino, com as regressões e o ρ fixos
  (`GoalsModel.fit_goal_dispersion`). Código: `prediction/goals_model.py` (`goal_pmf`, `score_matrix`).
  O ν estimado sobe de 1,05 (janela de 2006–2012) para 1,17 (janela de 2016–2025, usada em 2026): os
  gols por time variam menos que numa Poisson. Diagnóstico, regra de adoção e métricas: `validation.md`,
  seção "Distribuição de gols e dispersão".
- **Modelo C** (classificador multiclasse calibrado): planejado como benchmark (etapa 3).

Treino: as 10 temporadas anteriores à temporada simulada. A temporada corrente não entra nos
coeficientes; ela atualiza apenas os ratings.

Placar: matriz de probabilidades 0–10 × 0–10, normalizada. 1X2, placar mais provável e gols
esperados saem dessa matriz.

Campos por partida restante em `matches[]` (`MatchPrediction`), todos da mesma matriz (modelo de
gols com Dixon-Coles e dispersão, estado dos ratings na data de referência):

| Campo | Definição |
|---|---|
| `p_home`, `p_draw`, `p_away` | soma da matriz abaixo, sobre e acima da diagonal |
| `xg_home`, `xg_away` | gols esperados das regressões (a dispersão não muda a média) |
| `most_likely_score`, `most_likely_score_probability` | placar de maior probabilidade, `"m-v"`; igual a `top_scores[0]` |
| `top_scores` (desde `cmp-elo-ad-0.2.0`) | lista dos 3 placares mais prováveis, `{"home_goals", "away_goals", "probability"}`, em ordem decrescente de probabilidade. Empate exato fica na ordem da matriz: menos gols do mandante e, depois, menos gols do visitante (`goals_model.top_scores`) |
| `p_three_plus_goals` (desde `cmp-elo-ad-0.2.0`) | P(gols do mandante + gols do visitante ≥ 3) = 1 − P(0) − P(1) − P(2), o complemento de "até 2 gols" (`goals_model.total_goals_at_least`) |

`top_scores` e `p_three_plus_goals` são opcionais no schema: ficam `null` em jogos encerrados e em
snapshots anteriores a `cmp-elo-ad-0.2.0`. A matriz é truncada em 10 gols por time e normalizada.
Por isso a soma das 3 probabilidades é sempre menor que 1.

### Por que o placar mais provável é quase sempre 1×0, 1×1 ou 0×1

O "placar mais provável" é o placar exato com maior probabilidade, e há dezenas de placares
possíveis. Num jogo típico, com 1,5 gol esperado do mandante e 1,0 do visitante, o número de gols
mais provável de cada time é 1 (ou 0 para o visitante mais fraco), mesmo que a média seja maior. Por
isso a moda do placar fica em 1×0 ou 1×1. O número de gols mais provável de um time só passa a 2
quando ele tem mais de ~1,9 a 2,0 gols esperados, e passa de 0 a 1 a partir de ~0,9 a 1,0. Essa moda acontece em só 11% a 14% dos jogos: em média os três placares mais prováveis
somam ~35%, e 2×1, 2×0, 0×0 e 1×2 ficam logo atrás.

O backtest mostra que o modelo não subestima gols (2019–2025: 2,38 previstos contra 2,41 por jogo).
Um placar mais provável maior exigiria inflar os gols esperados, e isso piora a validação. A
dispersão (acima) deixa a distribuição mais fiel: menos 0×0 e menos goleadas, mais 1×1, 2×1 e 1×2.
Ela não muda a média, e o 1×1 passa a ser a moda mais frequente. Para mostrar jogos com mais gols
sem distorcer o modelo, o snapshot traz os 3 placares mais prováveis (`top_scores`) e a chance de 3
ou mais gols (`p_three_plus_goals`), além dos gols esperados.

## Simulação de Monte Carlo

1. Parte da tabela real na data de referência e preserva os jogos concluídos.
2. Simula apenas os jogos restantes, incluindo adiados ou sem placar na fonte, em ordem de data.
3. Os estados (Elo, ataque, defesa, forma) são matrizes `simulações × clubes`. Cada linha é uma
   temporada independente.
4. Dois modos, escolhidos pela validação (`dynamic_ratings_in_simulation` em `model_config.json`):
   ratings **fixos** na data de referência (em produção desde `cmp-elo-ad-0.3.0`, 2026-10-28) ou
   **dinâmicos**, em que os ratings da linha são atualizados após cada data simulada com as mesmas
   funções usadas no histórico real (produção até `cmp-elo-ad-0.2.0`). A troca e o custo em
   cobertura dos intervalos estão em `validation.md`, seção "Passo 11 do ADR-0008".
5. A classificação final aplica o Art. 15. Empates exatos em pontos, vitórias, saldo e gols pró
   são resolvidos com confronto direto (só entre dois clubes), cartões (só jogos observados) e
   sorteio aleatório reprodutível.
6. As vagas são alocadas para cada um dos cenários externos (ver `competition-rules.md`).
7. Incerteza opcional (`SimulationUncertainty`): sorteio dos coeficientes do modelo de gols e força
   latente por clube. Usa geradores próprios derivados da semente, então a execução sem incerteza
   é idêntica à anterior. Está desligada em produção pela validação (ver `validation.md`, etapa 2).

Saídas por clube: P(posição k) para k = 1..20, título, vice, G4, rebaixamento, Libertadores
(grupos, preliminar, total) e Sul-Americana por cenário e em faixa, pontos esperados, mediana,
intervalo de 90%, gols pró e contra esperados. Desde o schema 1.1 também saem a corrida pela
Sul-Americana (`sudamericana_race`, ver `sudamericana-race.md`) e a tabela restante com pontos
esperados por mando e índice de dificuldade (`schedule`, ver `schedule-difficulty.md`).

Os placares são sorteados em blocos de 100 mil jogos simulados (`SAMPLING_CHUNK_ROWS`) para limitar
a memória; os uniformes são consumidos na mesma ordem, então a semente reproduz o mesmo resultado
com ou sem blocos.

Número de simulações (2026-10-27): o snapshot da data de referência usa **100 mil** temporadas
(`SimulationConfig.n_simulations`, padrão de `simulate --simulations`). O erro-padrão de Monte Carlo
de uma probabilidade p é √(p(1−p)/n): no pior caso (p = 50%) cai de 0,50 p.p. com 10 mil para
0,16 p.p. com 100 mil. Medição local (i5-11300H, 61 jogos restantes, 32 cenários): `build_snapshot`
leva ~4 s com 10 mil e ~20 s com 100 mil; o pico de memória do processo (working set) passa de
~380 MiB para ~700 MiB, graças ao sorteio em blocos. O `simulate` completo (carga, simulação,
gravação e exportação) levou ~22 s com 100 mil.

Fora dos 100 mil, por custo:

- **Snapshots históricos** (`--history-simulations`, padrão 2.000): não foram reprocessados; o
  histórico de probabilidades mistura snapshots de 2 mil e 10 mil com o atual de 100 mil, e o
  `n_simulations` de cada ponto fica registrado em `probability-history.json`.
- **Revisão rodada a rodada** (`review-rounds`): roda duas simulações da temporada inteira por
  rodada (66 simulações para 33 visões). Com 10 mil levou ~25 min (pico rastreado de ~290 MB); com
  100 mil seriam ~4 h e alguns GB. O padrão passa a ser `SimulationConfig.round_review_simulations
  = 20_000`, o mesmo valor da revisão publicada.

## Revisão rodada a rodada

`python -m brasileirao.cli review-rounds` (código em `simulation/round_review.py`) gera uma visão por
rodada desde a pré-temporada e explica o que mudou entre visões.

- **Data de cada visão**: véspera do primeiro jogo da rodada seguinte; a rodada 0 é a véspera do
  primeiro jogo da temporada. Jogos adiados entram na visão do intervalo em que foram disputados.
  A última visão é parcial quando a rodada seguinte ainda não começou na data dos dados.
- **Decomposição exata da variação** de título, G4 e rebaixamento entre duas visões:
  - *efeito dos resultados*: simulação intermediária com os jogos do intervalo na tabela e a força
    dos clubes da visão anterior;
  - *reavaliação de força*: visão nova menos a intermediária. As duas usam os mesmos jogos restantes
    e a mesma semente (números aleatórios comuns), então essa diferença tem pouco ruído.
- **Atribuição por jogo**: P(X | resultado real) − P(X) nas simulações da visão anterior, em que o
  jogo estava em aberto. "Em jogo" é a diferença entre o melhor e o pior dos três resultados.
- **Resíduo**: efeito dos resultados menos a soma dos impactos por jogo. Vem do ruído das
  estimativas condicionais e da interação entre jogos simultâneos. O relatório traz o ruído esperado
  para comparação; a interface só mostra efeitos acima de 2 erros-padrão.

Execução de 2026-10-26 (20.000 simulações por visão, semente 2026, 32 visões): o efeito dos
resultados responde em média por ~70% da variação de título de cada rodada (de ~35% a ~95%, conforme a rodada) e a reavaliação de força pelo restante,
com peso maior no começo da temporada. Rodadas de maior movimento na corrida pelo título: 17
(23,7 p.p. redistribuídos, puxados por um confronto direto), 23 (18,0 p.p.) e 25 (15,6 p.p.); o
jogo e o placar ficam fora do repositório (decisão B1, 2026-10-27). O resíduo fica
próximo do ruído esperado no título (razão ~1 a 2) e chega a ~2× no rebaixamento no início da
temporada, quando muitos jogos simultâneos afetam os mesmos clubes.
