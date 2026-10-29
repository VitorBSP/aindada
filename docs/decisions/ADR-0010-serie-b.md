# ADR-0010 — Série B: fontes, regras com playoffs e site próprio em `/serie-b/`

- Status: **proposto** (2026-10-29). Implementado na `main` local com evidência (seção "Evidência").
  A publicação depende do parecer do Agente 06 (gate) e do 00, como toda publicação (AGENTS.md).
- Responsáveis: Agente 00 (decisão), 01 (fontes), 03 (regras), 02 (modelo), 04/05 (export e site),
  06 (validação), 07 (workflow), 08 (marca e textos, pendências abaixo).
- Origem: pedido do dono do produto (chat, 2026-10-29): "criar a versão para a Série B, com tudo o que
  aprendemos, e tentar o deploy"; "o frontend completamente diferente, o foco ainda é a Série A".

## Decisões do dono do produto (chat, 2026-10-29)

1. **Fontes**: Wikipédia em português (matriz de confrontos, CC BY-SA 4.0) para os resultados de 2025 e da
   temporada corrente; openfootball (`openfootball/south-america`, CC0-1.0) para 2018–2024 e para o
   calendário de 2025. A procedência de segunda mão do openfootball foi aceita como risco.
2. **Publicação**: no mesmo repositório e no mesmo workflow do Pages, no subcaminho `/serie-b/`, com um
   app separado (`apps/web-serie-b/`). O site da Série A não muda.

## Contexto

- O plano gratuito do football-data.org só tem a Série A: `GET /v4/competitions` lista só `BSA`, e
  `GET /v4/competitions/BSB/matches?season=2026` devolveu **403** (2026-10-29). O Adão Duque só cobre a
  Série A.
- O openfootball tem `YYYY_br2.txt` de 2018 a 2025, mas o de 2025 só tem placar em 57 dos 380 jogos, e
  não há arquivo de 2026 (commit `f51b2dcf5e0f`, 2026-10-20).
- A matriz da Wikipédia tem o placar de cada confronto, mas **não tem data nem rodada**.
- Regulamento da Série B 2026 (REC, CBF, 2026-02-06): Art. 5º (2 sobem direto, 2 pelos playoffs,
  4 caem), Art. 12 (desempate igual ao da Série A; confronto direto pelo agregado, só entre dois clubes)
  e Art. 13 (playoffs: 3º x 6º e 4º x 5º, ida e volta, volta na casa do 3º e do 4º, pontos, depois saldo,
  depois a melhor posição; sem pênaltis).

## Decisão 1 — Composição por temporada

| Temporadas | Resultado | Data e rodada | `date_source` |
|---|---|---|---|
| 2018–2024 | openfootball | openfootball | `openfootball` |
| 2025 | Wikipédia, revisão fixada `73254466` | calendário do openfootball | `openfootball_schedule` |
| 2026 (corrente) | Wikipédia, revisão mais recente na ingestão | **imputada** (encerrados); desconhecida (sem placar) | `imputed` / `unknown` |

- Fixação em `data/reference/serie_b_source_pins.json`: commit e SHA-256 dos 8 arquivos do openfootball;
  revisão da Wikipédia de cada temporada encerrada. A temporada corrente usa a revisão mais recente, que
  fica registrada no manifesto (`version = <temporada>-r<revid>`) e no `sources.json`.
- Sem fallback: temporada sem fonte, matriz incompleta, placar ilegível ou par fora do calendário
  fazem a ingestão falhar (`CompositionError`/`SourceFormatError`).
- **Data de corte** da temporada corrente = campo `update` da matriz ("27 de outubro"). Jogo sem placar
  nunca vira 0 x 0: fica `scheduled`, com data `corte + 1` só para ordenar.
- **Ordem imputada de 2026**: os jogos encerrados são distribuídos em rodadas em que cada clube joga no
  máximo uma vez, em ordem estável por SHA-256 do par, com datas espaçadas entre o início (campo `início`
  da página) e o corte. A ordem real é desconhecida; a imputação só evita que os ratings vejam 350 jogos
  num lote só. Não há backtest possível dentro de 2026.
- Conferência: em 2025, os 57 jogos com placar no openfootball batem com a Wikipédia (0 divergências);
  qualquer divergência faz a ingestão falhar.
- **Conferência da temporada corrente** (condição M1 do 06): a ingestão baixa também a predefinição
  "Tabela do Campeonato Brasileiro da Série B - <temporada>" (`standings.wikitext`, no mesmo manifesto) e
  exige que vitórias, empates, derrotas e gols de cada clube calculados da matriz batam com ela, com o
  mesmo campo `update`. Matriz e classificação são editadas à parte, então um placar vandalizado ou
  atrasado num dos dois faz a ingestão falhar. Ajuste de pontos (`adjust_points`, perda de pontos no STJD)
  não é modelado: a ingestão falha até haver ADR. A data de corte não pode ser posterior à data da coleta.
- Clubes: cadastro próprio `data/reference/clubs_serie_b.csv` (51 clubes, 2018–2026), com os mesmos
  `club_id` da Série A quando o clube existe lá. O `clubs.csv` da Série A não muda.

### Licenças (`SourceManifest`)

| Fonte | `license_status` | `license_name` | Atribuição |
|---|---|---|---|
| `wikipedia_pt` | `licensed_with_attribution` | CC BY-SA 4.0 (rodapé da página conferido em 2026-10-29) | "Resultados de <temporada>: Wikipédia em português, "<título>" (CC BY-SA 4.0)" |
| `openfootball` | `licensed_with_attribution` | CC0-1.0 (API de licenças do GitHub) | "Resultados históricos: openfootball (domínio público, CC0)" (cortesia) |

Usos declarados: `research_local`, `prototype_local`, `public_display_derived`, `redistribution`. Como
no ADR-0008, declarar `redistribution` não autoriza exercê-la: raw, silver e previsão da Série B ficam
fora do git (`data/serie_b/`, `apps/web-serie-b/data/`). Placar é fato; a CC BY-SA vale para a cópia da
matriz, que o projeto não redistribui. Não é parecer jurídico.

## Decisão 2 — Regras (Agente 03)

`competition_rules/seasons/serie_b_2026.toml` + `serie_b/rules.py`. A tabela usa o motor da Série A
(`SeasonRules` sem vagas continentais). Cartões: nenhuma fonte, então os critérios 5 e 6 viram sorteio,
com aviso (mesmo comportamento da Série A 2026).

## Decisão 3 — Modelo e simulação (Agente 02)

- **Mesmo modelo da Série A** (`cmp-elo-ad-0.3.0`: Elo + ataque/defesa, dispersão de gols, ratings fixos na
  simulação), com **hiperparâmetros calibrados na própria Série B** desde 2026-10-29
  (`data/gold/serie_b_model_config.json`, versão `serie-b-0.2.0+cmp-elo-ad-0.3.0`; a 0.1.0 usava os da
  Série A). Calibração em `serie_b/tuning.py` (`serie_b.cli tune`): busca coordenada da Série A escolhida
  em 2020–2022 e só relatada em 2023–2025; incerteza da simulação escolhida na mesma grade da Série A
  (nenhuma variante melhorou a validação: fica sem incerteza extra). Ratings só com jogos da Série B;
  treino do modelo de gols a partir de 2019 (2018 é aquecimento). O backtest exibido no site usa só
  2023–2025.
- Restante da temporada: um lote só (sem datas), com ratings fixos.
- Playoffs: placares sorteados do mesmo modelo, com os ratings da data de referência; semente própria
  `(seed, 3)`.
- "Subiu", "caiu", "não dá mais": só por aritmética de pontos (condição suficiente), nunca por simulação.
- Quem não jogou a Série B no ano anterior (os 4 rebaixados da Série A e os 4 promovidos da Série C)
  começa com a força média dos clubes que deixaram a divisão (`RatingEngine.start_season`). Em 2026 isso
  vale para Ceará, Fortaleza, Juventude e Sport, que podem começar subestimados (achado M4 do 06).

## Decisão 4 — Site (Agentes 05 e 08)

`apps/web-serie-b/`: página única (acesso, playoff provável, rebaixamento, tabela com faixa de posição
final, jogos restantes, método). Marca "AInda dá?" (D-004, D-008: a marca vale além da Série A) e tokens
da paleta aprovada (D-005); layout próprio. Sem escudos (procedência não verificada): selo com a sigla.

## Decisão 5 — Publicação (Agente 07)

- `publish-site.yml`: depois das checagens da Série A, o passo `serie_b` (com `continue-on-error`) ingere,
  simula, exporta para `$RUNNER_TEMP/serie-b` e passa o **gate da Série B** (`serie_b.cli gate`: esquema,
  somas de probabilidade, coerência com a aritmética, 38 jogos por clube, fontes publicáveis e creditadas,
  `reference_date` não regressiva contra o site no ar e nunca posterior à data da execução nem à coleta da
  fonte, todas as marcações aritméticas coerentes com as simulações, nada além de `forecast.json` em `data/`).
- Só depois do gate o site da Série B entra em `_site/serie-b`. Se o passo falhar, a Série A é publicada
  assim mesmo. O `forecast.json` que estava no ar volta com o app novo só se passar no
  `gate --standalone` (esquema, somas e aritmética); senão `/serie-b` sai do artefato.
- Nenhum segredo novo. O backtest não roda no workflow; `data/gold/serie_b_backtest_report.json`
  (só agregados) é versionado, como o da Série A.

## Evidência (2026-10-29)

- Ingestão real: 3.420 jogos (9 temporadas x 380); 2026: 350 encerrados, 30 sem placar, corte 2026-10-27.
- Backtest (`docs/methodology/validation.md`, seção Série B): log loss 1,0404 contra 1,0545 da taxa base em
  1.900 jogos de 2021–2025, melhor em todas as temporadas.
- Previsão real (100 mil simulações, semente 2026) aprovada no gate, 0 achados. Os 3 rebaixados pela
  aritmética (Londrina, América-MG, Ponte Preta) são os que a Wikipédia lista.
- Auditoria do 06 (2026-10-29): aprovado com condições (M1–M4), resolvidas na mesma data (ver status.md).
- `pytest`: 779 testes passaram (38 novos); `ruff`, `ruff format --check` e `mypy` sem achados.

## Pendências

Situação em 2026-10-29 (segunda rodada de trabalho):

- **06**: parecer dado (aprovado depois das condições M1–M4). Nova auditoria para a rodada abaixo.
- **08**: **feito.** Textos revisados contra o guia de conteúdo e a D-025, e cor própria decidida (não
  terá): D-038 em `docs/brand/BRAND_DECISIONS.md`.
- **02**: **feito.** Hiperparâmetros próprios adotados pelo protocolo (log loss de validação 1,0474 contra
  1,0486; teste 1,0365 contra 1,0369). A cobertura de 0,84 na rodada 19 (medida em 2021–2025) não aparece no teste
  2023–2025, com os novos parâmetros, fica em 0,93, 0,92 e 0,92 nas rodadas 19, 28 e 33. Detalhe em
  `docs/methodology/validation.md`.
- **01**: **investigado, sem fonte adotada.** A tabela da CBF é `blocked` pelos termos de uso; a
  alternativa (páginas de temporada de clube da Wikipédia em inglês, cerca de 81% dos jogos) é proposta
  ao 00 e ao dono no catálogo e recusada pelo dono em 2026-10-29. Segue a ordem imputada. Reler os termos no início de cada temporada.
- **03**: regulamento de 2027 quando a CBF publicar (não há como antecipar).
- **07**: **feito.** actionlint 1.7.7 sem achados nos workflows (shellcheck não executado).
