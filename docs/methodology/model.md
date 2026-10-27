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

## Modelo de gols

- **Modelo A (em produção)**: duas regressões de Poisson (scikit-learn, α = 1e-3).
  - Gols do mandante ~ diferença de Elo + log-taxa de ataque/defesa do mandante.
  - Gols do visitante ~ diferença de Elo + log-taxa de ataque/defesa do visitante.
- **Modelo B**: correção Dixon-Coles com ρ estimado por máxima verossimilhança. Está implementado e
  avaliado, sem ganho até agora.
- **Inflação de empates** (opcional, `draw_inflation`): diagonal da matriz de placares × (1 + δ),
  com δ por máxima verossimilhança no treino. Corrige a taxa média de empates, mas não foi adotada
  por falta de ganho nas métricas (ver `validation.md`, etapa 2).
- **Modelo C** (classificador multiclasse calibrado): planejado como benchmark (etapa 3).

Treino: as 10 temporadas anteriores à temporada simulada. A temporada corrente não entra nos
coeficientes; ela atualiza apenas os ratings.

Placar: matriz de probabilidades 0–10 × 0–10, normalizada. 1X2, placar mais provável e gols
esperados saem dessa matriz.

## Simulação de Monte Carlo

1. Parte da tabela real na data de referência e preserva os jogos concluídos.
2. Simula apenas os jogos restantes, incluindo adiados ou sem placar na fonte, em ordem de data.
3. Os estados (Elo, ataque, defesa, forma) são matrizes `simulações × clubes`. Cada linha é uma
   temporada independente.
4. Após cada data simulada, os ratings da linha são atualizados com as mesmas funções usadas no
   histórico real. O modo de ratings fixos fica disponível para comparação.
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
