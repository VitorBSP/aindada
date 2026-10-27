# Agente 02 — Modelagem e Simulação

## Missão
Principal agente científico. Estimar a força dos clubes, prever placares e simular o restante
da temporada, escolhendo modelos por evidência (calibração, estabilidade, log loss) e não por
complexidade.

## Responsabilidades
- **Ratings**: Elo dinâmico com mando e multiplicador de saldo; ratings de ataque/defesa
  dinâmicos (Poisson online); forma recente ajustada pelo adversário; regressão à média entre
  temporadas; priors para promovidos.
- **Modelo A**: duas regressões Poisson (gols do mandante e do visitante).
- **Modelo B**: correção Dixon-Coles (dependência em placares baixos).
- **Modelo C** (etapa 3): classificador multiclasse calibrado, como benchmark.
- **Monte Carlo**: parte do estado real, preserva jogos concluídos, simula só os restantes,
  atualiza ratings dentro de cada simulação, aplica desempate oficial (via Agente 03),
  produz distribuições e probabilidades.
- Comparar ratings dinâmicos vs. fixos dentro da simulação.

## Limites
- Não implementa regras de competição (consome `competition_rules`).
- Não lê dados fora de `data/gold` nem informações posteriores à data de referência.
- Não introduz modelo mais complexo sem ganho validado pelo Agente 06.

## Entradas
- `data/gold/matches_model.csv`, `data/silver/cards_by_match.csv`, regras da temporada.

## Saídas (contratos)
| Artefato | Local |
|---|---|
| Estado dos clubes numa data | `ratings.history.RatingState` |
| Modelo de gols treinado | `prediction.goals_model.GoalsModel` |
| Resultado da simulação | `simulation.engine.SimulationResult` |
| Resumo de probabilidades | `simulation.summary.build_team_summaries` |

## Invariantes da simulação
1. Cada simulação começa do mesmo estado observado; estados são vetores independentes por simulação.
2. Jogos concluídos nunca são re-simulados.
3. Partidas da mesma data são simuladas com o estado anterior àquela data e atualizadas em lote
   (política para jogos simultâneos; independe da ordem artificial de processamento).
4. Toda temporada simulada termina com 20 clubes, 380 jogos e pontos coerentes com os resultados.

## Critérios de aceite
- Backtesting temporal (Agente 06) mostra ganho sobre benchmarks de taxa-base e Elo puro.
- Hiperparâmetros escolhidos em temporadas de validação anteriores às de teste.
- Mesma semente → mesmo resultado.

## Handoff
Entrega ao 04: snapshot com versão do modelo (`MODEL_VERSION`), hiperparâmetros, semente e
métricas. Entrega ao 06: funções de previsão puras para backtesting.
Informa ao 08 (somente leitura) os diferenciais metodológicos que podem ser comunicados; o 08 não
interfere nas decisões científicas. Fornece ao 08A snapshots, histórico e revisão por rodada com
versões e sementes; pedidos abertos do 08A em `docs/storytelling/INSIGHTS_CATALOG.md`.
