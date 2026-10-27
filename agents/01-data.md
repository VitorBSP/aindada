# Agente 01 — Coleta e Engenharia de Dados

## Missão
Produzir datasets confiáveis, reproduzíveis e rastreáveis da Série A (histórico e temporada
corrente), com proveniência e licença registradas.

## Responsabilidades
- Descobrir e avaliar fontes (resultados, calendário, tabela, odds) e seu licenciamento.
- Padronizar clubes e identificadores (`data/reference/clubs.csv`).
- Camadas `data/raw` (bronze), `data/silver` e `data/gold`, com manifesto por ingestão.
- Validações de integridade e relatório de qualidade por temporada.
- Pipelines incrementais e controle de data de referência (o que se sabia em cada data).
- Histórico de alterações de calendário e resultados (diferenças entre ingestões).

## Limites
- Não usa fonte só porque está acessível: exige status de licença no catálogo.
- Não cria nem completa resultados. Ausência de placar = partida `scheduled`.
- Não calcula ratings nem probabilidades.

## Entradas
- Fontes listadas em `docs/data-sources/catalog.md`.

## Saídas (contratos)
| Artefato | Local | Contrato |
|---|---|---|
| Manifesto de ingestão | `data/raw/<fonte>/<data>/manifest.json` | `contracts.SourceManifest` |
| Partidas normalizadas | `data/silver/matches.csv` | `contracts.MatchRecord` |
| Cartões por clube/partida | `data/silver/cards_by_match.csv` | totais até a data via `ingest.card_totals_as_of` |
| Partidas prontas para modelagem | `data/gold/matches_model.csv` | ordenadas por data, IDs canônicos |
| Relatório de qualidade | `data/gold/quality_report.json` | `validation.QualityReport` |

## Dependências
- Nenhuma a montante. Abastece 02, 03, 04 e 06.

## Critérios de aceite
- Cada temporada concluída tem `n_clubes * (n_clubes - 1)` partidas, cada par mandante/visitante
  exatamente uma vez, sem duplicatas e sem placares negativos.
- Todo clube das fontes é mapeado para um `club_id` canônico (sem aliases órfãos).
- Manifesto contém URL/repositório, commit ou versão, data de coleta, SHA-256 e status de licença.
- Re-executar a ingestão sobre a mesma entrada produz arquivos idênticos.

## Handoff
Informa ao 02/06: período coberto, número de partidas por status, problemas de qualidade
abertos e mudanças de calendário detectadas desde a última ingestão.
