# Agente 04 — Backend e API

## Missão
Expor dados observados e previsões persistidas por uma API REST tipada, sem executar
simulações pesadas no caminho das requisições públicas.

## Responsabilidades
- FastAPI + Pydantic; schemas de resposta versionados.
- Persistência de snapshots (SQLite local; PostgreSQL em produção — ADR-0004).
- Histórico de probabilidades por data de referência.
- Versionamento de modelo e de dados em cada snapshot.
- Export estático equivalente à API para o frontend sem servidor.

## Limites
- Não recalcula probabilidades em requisição pública; lê snapshots.
- Não contém lógica estatística.

## Endpoints
| Método | Rota | Fonte |
|---|---|---|
| GET | `/api/health` | — |
| GET | `/api/seasons` | snapshots |
| GET | `/api/seasons/{season}/standings` | snapshot mais recente |
| GET | `/api/seasons/{season}/matches` | snapshot mais recente |
| GET | `/api/seasons/{season}/predictions` | snapshot mais recente |
| GET | `/api/seasons/{season}/teams/{team_id}` | snapshot mais recente |
| GET | `/api/seasons/{season}/probability-history` | todos os snapshots da temporada |
| GET | `/api/models/metrics` | relatório de backtesting |

## Entradas
- `data/snapshots/snapshots.sqlite`, `data/gold/backtest_report.json`.

## Saídas
- `apps/api/main.py`, `src/brasileirao/storage/`, export estático em `apps/web/data/`.

## Critérios de aceite
- Respostas validadas por modelos Pydantic; 404 para temporada/clube inexistente.
- Testes de integração da API (executados quando FastAPI está instalado).

## Handoff
Informa ao 05 mudanças de schema com antecedência e versão (`schema_version` no payload).
Para o fluxo editorial (D-026): armazenar lotes do 08A, revisões do 08 e insights publicados
conforme `docs/storytelling/contracts/insight.schema.json`, e expor só os `published`.
