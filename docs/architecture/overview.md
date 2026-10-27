# Arquitetura (Agente 00)

```text
fontes ─► data_pipeline ─► data/raw ─► data/silver ─► data/gold
                                                        │
                    competition_rules (TOML por temporada)
                                                        ▼
                 ratings (Elo, ataque/defesa, forma) ─► prediction (Poisson, Dixon-Coles)
                                                        ▼
                              simulation (Monte Carlo vetorizado) ─► summary + regras de vagas
                                                        ▼
                         storage (snapshots SQLite) ─► apps/api (FastAPI, só leitura)
                                                        └► export estático ─► apps/web
validation (backtest, métricas) ─► data/gold/backtest_report.json + model_config.json
```

## Fluxo de atualização (`pipeline.py`)

1. `brasileirao ingest --fetch`: busca a fonte, grava em raw com manifesto e normaliza para silver e gold.
2. `brasileirao validate`: checagens de integridade, com exceções conhecidas registradas.
3. `brasileirao backtest`: só quando o modelo muda ou a cada temporada. Escolhe os hiperparâmetros e
   grava `model_config.json`.
4. `brasileirao simulate`: reconstrói os ratings até a data de referência, treina o modelo de gols
   com temporadas anteriores, simula, aplica as regras, grava o snapshot e exporta o JSON estático.

## Contratos

| Contrato | Arquivo |
|---|---|
| Partida normalizada, manifesto, clube | `src/brasileirao/contracts.py` |
| Regras da temporada | `src/brasileirao/competition_rules/seasons/serie_a_<ano>.toml` |
| Snapshot publicado | `src/brasileirao/storage/schema.py` (`schema_version`) |
| Configuração do modelo | `data/gold/model_config.json` |

## Reprodutibilidade

Um snapshot é determinado por: commit da fonte, data de referência, `model_config.json`, versão do
código (`MODEL_VERSION`) e semente. Todos esses itens ficam gravados no snapshot.
