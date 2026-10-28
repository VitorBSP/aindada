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
| `GET /api/seasons/{season}/current-round` | rodada da aba "Rodada atual" / "Última rodada" (`CurrentRound`, ADR-0009); `round` nulo na pré-temporada |
| `GET /api/seasons/{season}/insights` | insights editoriais **publicados** (`PublishedInsight`), ordenados por posição e prioridade; candidatos e reprovados nunca saem por aqui. Fonte: `data/editorial/{season}/published.json` (D-026) |
| `GET /api/models/metrics` | relatório de backtesting (sem registros brutos) |

A API nunca executa simulações: só lê snapshots e revisões gravados pela CLI (tabelas `snapshots`
e `round_reviews` no SQLite; a revisão mais recente da temporada é a servida). O espelho estático
(`apps/web/data/api/*.json`) tem o mesmo conteúdo dos endpoints GET.

## Horário do jogo e rodada atual (ADR-0009, passo 2)

Snapshot `schema_version` **1.3** (aditivo; snapshots 1.2 e anteriores continuam legíveis, com os campos
novos `null`). Cada `MatchPrediction` ganhou:

- `kickoff_utc`: ISO 8601 UTC (`2026-10-28T22:30:00Z`), **só** com horário confirmado na fonte
  (`confirmed_kickoff_utc` do 01); senão `null` e a interface mostra "a definir";
- `source_match_id`: id da partida na fonte (o workflow do 07 liga o jogo da API ao do site por ele).

O `status` de jogo sem resultado na data de referência passa a manter `postponed` e `cancelled` da fonte
(antes saía sempre `scheduled`). Jogo sem resultado nunca sai `finished` nem com placar.

`current-round.json` (`data/api/seasons/{season}/current-round.json`, `CURRENT_ROUND_SCHEMA_VERSION` 1.0)
segue o contrato da Decisão 3 do ADR-0009. A lógica fica em `src/brasileirao/storage/current_round.py` e só
lê o snapshot publicado e a revisão por rodada mais recente; o horário do export (`now`, injetável em
`export_static_api`) decide a rodada. Parâmetros em `config.py`: `ROUND_WINDOW_DAYS = 4`,
`STALE_RESULT_HOURS = 48`.

- Âncora da rodada: mediana inferior das `match_date`; jogo na janela: a até 4 dias da âncora.
- Resolvido: `finished`, `postponed`, `cancelled`, ou `scheduled` com início há mais de 48 h. Sem
  `kickoff_utc`, o início considerado é o fim do dia em Brasília (hipótese mais tardia).
- Rodada mostrada: a menor não concluída com primeiro jogo da janela até a data de `now` em Brasília
  (`in_progress`); senão a maior concluída já iniciada (`finished`); senão `round: null`.
- `match_ids`: jogos da janela mais os jogos de **outras** rodadas remarcados para fora da janela delas e
  marcados entre `starts_on` e `ends_on`; ordem por dia, `kickoff_utc` e, no fim do dia, os sem horário.
  Jogos sem rodada (`round` nulo) não entram. `rescheduled_match_ids`: jogos da rodada fora da janela.
- `baseline`: a visão do `rounds.json` com a maior `reference_date` anterior a `starts_on`, só com
  `title`, `top4` e `relegation` por clube; `n_simulations` e `model_version` da revisão;
  `reconstructed: true`. É `null` sem revisão, sem visão anterior ou com revisão de outro `data_version`.
  Clubes diferentes dos do snapshot fazem o export falhar (`BaselineMismatchError`). A visão da
  pré-temporada (rodada 0) é a véspera da rodada 1, então a rodada 1 tem ponto de partida sempre que o
  `rounds.json` existir.
- `updated_at`, `model_version` e `data_version` são os do `predictions.json` (`generated_at`).
