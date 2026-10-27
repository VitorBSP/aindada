# Análise dos projetos de referência

## WC_22_Predictions (Copa 2022) — analisado em 2026-10-26

Conteúdo: notebooks de Elo, engenharia e análise de atributos, modelagem com Random Forest,
Gradient Boosting e regressão logística, e `utils/modelling_functions.py` para simular grupos e
mata-mata.

| Ideia | Reaproveitada? | Como |
|---|---|---|
| Diferenças entre equipes como atributos (rank, gols, últimos 5) | Sim, adaptada | `elo_diff`, log-taxa de ataque/defesa e forma |
| Gols ajustados pela força do adversário (`points_by_rank`, `rank_suf`) | Sim | ratings de ataque/defesa por gradiente de Poisson, que ajustam pelo adversário |
| Média das duas ordens mandante/visitante | Não | o Brasileirão tem mando real, modelado explicitamente |
| Ranking FIFA | Não | proibido para clubes; substituído por Elo |
| Simulação determinística (vencedor = maior probabilidade, empate por regra heurística) | **Não** | substituída por Monte Carlo com sorteio de placares. A versão determinística subestima a incerteza e nunca gera zebras |
| Estado global (`team_stats_raw` em variável de módulo) | Não | estados por simulação, imutáveis entre linhas |
| Validação por AUC em divisão aleatória | Não | validação temporal por temporada, com log loss, Brier e RPS |

## Projeto Copa 2026 (dois Poisson, Elo dinâmico, Monte Carlo, odds)

Não havia arquivos locais na pasta do projeto, e o repositório não foi encontrado nos materiais
acessíveis. As ideias descritas no pedido foram incorporadas a partir da descrição: dois Poisson,
Elo dinâmico, ataque/defesa, forma, atualização dentro da simulação e ajuste pelo adversário.
Odds ficaram para a etapa 3. Se o código existir, vale compará-lo no próximo ciclo.
