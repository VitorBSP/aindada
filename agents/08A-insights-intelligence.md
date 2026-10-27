# Subagente 08A — Insights e Inteligência Editorial

Coordenado pelo Agente 08 (D-026). Criado em 2026-10-26.

## Missão
Ler os resultados estruturados das simulações e encontrar histórias que os dados realmente
sustentam. Gera **candidatos**; não decide o que é publicado.

## Responsabilidades
- Comparar o snapshot atual com os anteriores (histórico de probabilidades e revisão por rodada).
- Aplicar as regras do catálogo (`docs/storytelling/INSIGHTS_CATALOG.md`) e os critérios
  configuráveis (`docs/storytelling/contracts/insight-criteria.toml`).
- Produzir candidatos no formato `insight_candidate`
  (`docs/storytelling/contracts/insight.schema.json`), com evidências, valores atual e anterior,
  incertezas e visualização sugerida.
- Priorizar qualidade: poucos candidatos, cada um materialmente relevante e acima do ruído.
- Manter o processamento reproduzível: mesma entrada e mesma versão das regras produzem os mesmos
  candidatos, com o mesmo `insight_id`.

## Limites (inegociáveis)
- Nunca inventa número, fato ou acontecimento. Todo número vem do snapshot citado.
- Nunca usa informação posterior à data de referência do snapshot.
- Não trata oscilação dentro do erro de Monte Carlo como acontecimento.
- Não atribui causa a um único jogo quando outros jogos ou a reavaliação de força também mudaram
  o número; usa a decomposição resultados × força quando ela existir.
- Diferencia probabilidade de fato consumado e probabilidade de vaga de posição na tabela.
- Não trata vagas que dependem de torneios externos como probabilidade única: usa as faixas.
- Não publica nada. Não altera a modelagem.
- LLM é opcional e só para redação de texto a partir de dados já validados; nunca substitui as
  regras determinísticas nem a validação estatística.

## Entradas
| Fonte | Conteúdo |
|---|---|
| `GET /api/seasons/{s}/predictions` | snapshot atual: probabilidades por clube, distribuição de posições, pontos projetados, jogos e probabilidades 1X2 |
| `GET /api/seasons/{s}/probability-history` | série de snapshots: título, G4, rebaixamento, faixa de Libertadores, pontos projetados |
| `GET /api/seasons/{s}/rounds` | revisão por rodada: variações, efeito de resultados e de força, impacto por jogo, ruído esperado |
| `GET /api/models/metrics` | qualidade do modelo, para calibrar a linguagem de incerteza |

## Saída
Lote `insight_batch` com `snapshot_ref`, `rules_version`, `criteria_hash` e a lista de candidatos.

## Implementação (2026-10-26)
Módulo Python determinístico em `src/brasileirao/insights/`:

| Arquivo | Papel |
|---|---|
| `contracts.py` | modelos Pydantic que espelham `docs/storytelling/contracts/insight.schema.json` |
| `criteria.py` | carrega `insight-criteria.toml` e calcula o `criteria_hash` |
| `rules.py` | regras `TITLE_RISER`, `TITLE_FALLER`, `RELEG_RISER`, `MATCH_MOVED_MOST`, teste de ruído, textos |
| `gates.py` | portões automáticos: schema, rastreabilidade de números, temporalidade, ruído, aritmética, faixas |
| `generator.py` | lê snapshots e revisão por rodada do `SnapshotStore`, pontua, salva o lote e aplica os portões |
| `editorial.py` | lotes, revisões (`reviews.jsonl`), publicação e retirada, exportação estática |

Comandos: `insights-generate`, `insights-list`, `insights-review`, `insights-publish`. Dados em
`data/editorial/{temporada}/`; exportação em `apps/web/data/api/seasons/{temporada}/insights.json`.
Versão das regras em `brasileirao.config.INSIGHT_RULES_VERSION` (entra no `insight_id`). O arquivo
`.claude/agents/08A-insights.md` serve para análises exploratórias e revisão das regras.

## Critérios de aceite
- 100% dos candidatos validam contra o schema.
- Cada candidato pode ser reconstruído a partir de `snapshot_ref` + `rules_version` + critérios.
- Testes com fixtures sintéticas (marcadas `synthetic`) cobrem cada regra do catálogo, inclusive
  os casos em que a regra **não** deve disparar (ruído).
