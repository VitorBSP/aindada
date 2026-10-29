# ADR-0011 — Ligas europeias: Premier League e LaLiga (e a Champions League em seguida)

- Status: **proposto** (2026-10-29). Implementado na `main` local com evidência; a publicação depende do
  parecer do 06 e do 00 (AGENTS.md).
- Responsáveis: Agente 00 (decisão), 01 (fontes), 03 (regras), 02 (modelo), 04/05 (export e site),
  06 (validação), 07 (workflow), 08 (seletor de competições, D-039).
- Origem: pedido do dono do produto (chat, 2026-10-29): "vamos construir Premier League, La Liga e
  Champions League". Ordem decidida pelo dono: PL e LaLiga primeiro, Champions depois.

## Decisão 1 — Fontes (decisão do dono, chat de 2026-10-29)

| Temporadas | Fonte | Papel |
|---|---|---|
| PL 2010/11–2025/26; LaLiga 2012/13–2025/26 | openfootball (`england`, `espana`; CC0-1.0), commit e SHA-256 de cada temporada em `data/reference/league_source_pins.json` | publicação (histórico) |
| 2026/27 (corrente) | football-data.org v4 (`PL`, `PD`), plano gratuito, mesma chave e atribuição da Série A | publicação |
| 2023/24–2025/26 | football-data.org | só conferência local (`ingest --conference`) |

- O dono recusou usar só o football-data.org (histórico curto e exposição à cláusula 9.1 em todas as
  temporadas) e aprovou esta composição: a cláusula 9.1 fica limitada à temporada corrente, como na Série A.
- Procedência dos resultados do openfootball não informada (risco aceito pelo dono, como na Série B).
  **Conferência** (2026-10-29): nas temporadas em comum, **2.280 de 2.280 jogos** iguais em data e placar
  (PL e LaLiga, 2023/24–2025/26). A ingestão com `--conference` falha com qualquer divergência.
- Data do jogo no fuso da liga (Europe/London, Europe/Madrid). `IN_PLAY`/`PAUSED` viram `scheduled` (nunca
  placar parcial); `AWARDED` faz a ingestão falhar; `POSTPONED`/`CANCELLED` ficam pendentes e são simulados.
- Data de referência: o último dia com jogo encerrado na temporada corrente; não pode passar da coleta.
- Cadastros de clubes próprios (`data/reference/clubs_premier_league.csv`, `clubs_la_liga.csv`), montados
  cruzando os nomes das duas fontes pelos jogos em comum e revisados à mão.
- Token: a cláusula 6.1 do ADR-0008 continua valendo, generalizada: o segredo só aparece em passos de
  **ingestão** (`Ingestão de publicação` e `Ingestão das ligas europeias`), o que o teste de workflow verifica.

## Decisão 2 — Regras (Agente 03)

`competition_rules/seasons/premier_league_2026.toml` e `la_liga_2026.toml`, com a ordem de desempate do
regulamento e zonas exibidas (título, top 4, rebaixamento).

- **PL** (Handbook, regras C.4–C.7 e C.17, conferidas no explicativo oficial da liga): pontos, saldo, gols
  pró, pontos no confronto direto, gols como visitante no confronto direto, jogo extra (sorteio).
  Pendência do 03: conferir contra o Handbook 2026/27.
- **LaLiga** (RFEF, bases de competição 2026/27, Art. 8.7 e 10): pontos; confronto direto (dois clubes:
  saldo entre eles; três ou mais: mini-tabela de pontos e, para quem seguir empatado, saldo entre eles);
  saldo geral; gols pró; fair play (sem dados: sorteio); campo neutro (sorteio). Rebaixam 18º–20º.
- Desempate configurável em `leagues/ranking.py`: cada critério divide o grupo empatado e o confronto direto
  é recalculado só entre quem segue empatado. O `LeagueSimulator` troca só a ordenação final do motor da
  Série A; a Série A não muda.
- "Top 4" é posição, não vaga: o 5º pode ir à Champions pelo desempenho europeu do país, o que não é
  modelado (nota na página).

## Decisão 3 — Modelo (Agente 02)

Mesmo modelo da Série A, com hiperparâmetros calibrados por liga (`leagues/validation.py`,
`... cli <liga> tune`): escolha na validação 2020/21–2022/23, teste só relatado em 2023/24–2025/26
(protocolo do ADR-0006). Configuração em `data/gold/league_model_config_<liga>.json` e relatório em
`data/gold/league_tuning_report_<liga>.json` (só agregados). Versão `ligas-0.1.0+cmp-elo-ad-0.3.0`.
O backtest por temporada usa a ordenação da Série A (só empates exatos mudam) e não mede rebaixamento,
porque o helper conta 4 rebaixados e as ligas rebaixam 3.

## Decisão 4 — Site (Agentes 05 e 08)

App único `apps/web-ligas/`, publicado em `/premier-league/` e `/la-liga/`, cada um com o seu
`data/forecast.json`. Mesmas regras de marca da D-038. Seletor de competições (D-039) em todos os sites.

## Decisão 5 — Publicação (Agente 07)

No `publish-site`, depois da Série B: `Ingestão das ligas europeias` (com o token, `continue-on-error`),
`Ligas europeias — previsão e gate` (sem token, `continue-on-error`) e `incluir no artefato`, com o mesmo
fallback da Série B (o `forecast.json` no ar só volta se passar no `gate --standalone`). Cada liga falha
sozinha. Duas chamadas novas à API por execução (uma por liga), com 6,5 s entre elas.

## Champions League (próxima etapa, ainda não decidida)

O plano gratuito cobre a fase de liga 2026/27 (144 jogos) e as temporadas 2024/25 e 2025/26 completas. O
problema é de modelo: comparar a força de 36 clubes de ligas diferentes. Proposta a decidir: Elo único com
as ligas do plano gratuito (PL, LaLiga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga) ligadas
pelos jogos europeus, regulamento da UEFA 2026/27 (Art. 18 para o desempate da fase de liga) e mata-mata
simulado com prorrogação e pênaltis.
