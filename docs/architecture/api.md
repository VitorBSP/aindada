# API (Agente 04)

`uvicorn apps.api.main:app --reload` (requer `pip install -e .[api]`). A interface web fica servida em `/`.

| Rota | Resposta |
|---|---|
| `GET /api/health` | `{"status": "ok"}` |
| `GET /api/seasons` | temporadas com snapshot, última data de referência e quantidade |
| `GET /api/seasons/{season}/standings` | tabela observada |
| `GET /api/seasons/{season}/matches` | jogos com resultado ou previsão 1X2, gols esperados e placar mais provável |
| `GET /api/seasons/{season}/predictions` | snapshot completo (`PredictionSnapshot`) |
| `GET /api/seasons/{season}/teams/{team_id}` | previsão do clube, jogos e cenários |
| `GET /api/seasons/{season}/probability-history` | título, G4, rebaixamento, Libertadores e pontos esperados por data |
| `GET /api/seasons/{season}/rounds` | revisão rodada a rodada (`RoundReview`): visões desde a pré-temporada, variação decomposta em resultados e força, impacto de cada jogo por clube |
| `GET /api/seasons/{season}/insights` | insights editoriais **publicados** (`PublishedInsight`), ordenados por posição e prioridade; candidatos e reprovados nunca saem por aqui. Fonte: `data/editorial/{season}/published.json` (D-026) |
| `GET /api/models/metrics` | relatório de backtesting (sem registros brutos) |

A API nunca executa simulações: só lê snapshots e revisões gravados pela CLI (tabelas `snapshots`
e `round_reviews` no SQLite; a revisão mais recente da temporada é a servida). O espelho estático
(`apps/web/data/api/*.json`) tem o mesmo conteúdo dos endpoints GET.
