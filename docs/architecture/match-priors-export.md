# Exportador de probabilidades pré-jogo (`export-match-priors`)

Contrato inicial da futura **Base Global de Partidas & Probabilidades** (multi-campeonatos, 2010+). Hoje cobre só a
Série A (`--competition serie_a`). Somente leitura: não escreve em `data/`, no banco nem nos snapshots.

```bash
python -m brasileirao.cli export-match-priors --competition serie_a --seasons 2024,2025,2026 \
  --output exports/match_priors_serie_a_2024_2026.parquet [--csv]
```

Gera `match_priors_serie_a_2024_2026.parquet` (e `.csv` com `--csv`) e
`match_priors_serie_a_2024_2026.manifest.json` ao lado. Requer `pip install -e ".[export]"` (pyarrow) e a ingestão
feita (`data/gold/matches_model.csv`, `data/silver/sources.json`). Sai com código 1 se qualquer regra abaixo falhar.

## Regra point-in-time (zero leakage)

- A previsão da rodada **R** usa só partidas **encerradas com data (Brasília) anterior ao primeiro jogo da rodada R**.
  Resultado de jogo posterior é apagado antes de chegar ao motor (`point_in_time_view`); o calendário (quem joga com
  quem) é público antes da temporada e fica.
- O modelo de gols (regressões, ρ de Dixon-Coles, dispersão) treina **só com temporadas anteriores à da partida**
  (janela e primeira temporada de `ModelTrainingConfig`: 10 temporadas, a partir de 2006), com os ratings de cada
  jogo já calculados antes dele. Os ratings (Elo e ataque/defesa) aquecem com todo o histórico da base (2003+).
- Jogo remarcado para depois do início da rodada vale com a informação do início da rodada, não da data nova.
- `as_of_round`: maior rodada da temporada entre as partidas usadas (0 = nenhuma da temporada, como na rodada 1).
- Mesmo motor dos snapshots (`RatingEngine`, `GoalsModel`, `data/gold/model_config.json`,
  `config.MODEL_VERSION`). Determinístico: não há sorteio, então não há semente (`seed: null` no manifesto).

## Schema (1 linha por partida)

`competition_id` (`brasileirao_serie_a`), `season`, `round`, `match_id` (`<temporada>-<home_club_id>-<away_club_id>`),
`kickoff_utc` (ISO 8601 UTC só com horário confirmado na fonte; senão nulo), `status` (`finished`, `scheduled`,
`postponed`), `home_club_id|name|short` e `away_club_id|name|short` (de `data/reference/clubs.csv`),
`home_score`, `away_score` (nulos fora de `finished`; nunca 0 x 0), `home_win_probability`, `draw_probability`,
`away_win_probability` (somam 1), `home_expected_goals`, `away_expected_goals` (λ pré-jogo), `home_clean_sheet_probability`
(= P(gols do visitante = 0)), `away_clean_sheet_probability` (= P(gols do mandante = 0)), `over_1_5_probability`,
`over_2_5_probability`, `under_2_5_probability` (= 1 − over 2,5), `model_version`, `as_of_round`. As probabilidades de
mercado saem da matriz de placares (0 a 10 gols, normalizada) do mesmo modelo.

## Validações (falham a exportação)

Colunas do schema; `match_id` único; zero NaN em probabilidades e lambdas; probabilidades em [0, 1]; resultado soma 1
(tolerância 1e-9); over 2,5 + under 2,5 = 1 e over 2,5 ≤ over 1,5; placar nulo se e só se não `finished`; contagem por
temporada (padrão 380; `--expected-matches-per-season 0` desliga); fonte do gold igual à composição
(`check_g1_gold_sources`: 2024–2025 `adaoduque_kaggle` v18, 2026 `football_data_org`).

## Manifesto

Fontes (versão, origem, licença, usos permitidos, atribuição, SHA-256 do manifesto raw), SHA-256 do gold, de
`clubs.csv`, de `model_config.json` e dos arquivos gerados, modelo e parâmetros, regra point-in-time, commit do
código, data de geração e o resumo de validação.

## Licença e uso

Os dados de partida são de terceiros (Adão Duque v18, GPL-2 declarada; football-data.org, sem redistribuição). O export
é **uso local/protótipo** do dono do produto e **não é redistribuível** sem ADR (ADR-0008); `exports/` está no
`.gitignore` (linha a linha de fonte restrita, ADR-0007). Ao exibir, manter a atribuição de cada fonte (no manifesto).

## Limitações

- Só Série A. Outras competições entram quando tiverem fonte, regras e `competition_id` registrados.
- Histórico anterior a 2010 aquece os ratings; o export em si cobre só as temporadas pedidas.
- Previsão de rodadas futuras usa o que já está encerrado hoje; muda quando a rodada anterior termina.
