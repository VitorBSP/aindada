# Catálogo de fontes de dados (Agente 01)

Última revisão: 2026-10-28 (conferência local de 2026, pendência 5 do ADR-0008). Antes: 2026-10-27
(ADR-0008, passos 1 a 9, e primeira ingestão real de publicação). Toda ingestão grava
`data/raw/<fonte>/<versão>/manifest.json` (`contracts.SourceManifest`), com origem, versão/commit,
data de coleta, SHA-256 dos arquivos, status de licença, usos permitidos (`AllowedUse`) e, para
fontes publicáveis, nome da licença, URL e data de leitura dos termos e texto exato da atribuição.

## Fontes

| Fonte (`source_name`) | Conteúdo | Cobertura | Acesso | Licença / restrições | Papel no projeto (ADR-0008) |
|---|---|---|---|---|---|
| [Adão Duque, "Campeonato Brasileiro de Futebol"](https://www.kaggle.com/datasets/adaoduque/campeonato-brasileiro-de-futebol) (`adaoduque_kaggle`) | Partidas (data dd/mm/aaaa, hora, rodada, mandante, visitante, placar), cartões, gols, estatísticas | 2003–2025: 9.165 partidas; cartões 2014–2024 (20.953 cartões; sem 2025) | Kaggle **versão 18**, baixada pelo dono do produto para `data/raw/adaoduque/v18/` (adaptador `AdaoDuqueSource`, que não baixa nada). SHA-256 fixado em `data/reference/source_pins.json` (`brasileirao pin-adaoduque`). O espelho do GitHub serve só para comparar hashes | `licensed_with_attribution`: GPL-2 declarada no Kaggle (v18; "only" ou "or later" não especificado), termos lidos em 2026-10-27. Coleta do autor "de páginas do Google" (proveniência de segunda mão, risco aceito no ADR). Usos: `research_local`, `prototype_local`, `public_display_derived`, `redistribution` (a licença permitiria; o projeto **não** redistribui sem ADR próprio) | **Publicação 2003–2025.** v18 baixada e fixada em 2026-10-27 (proveniência abaixo); ingestão real executada |
| [football-data.org](https://www.football-data.org) (`football_data_org`) | API v4, competição BSA: partidas, rodada, status, placar de tempo normal | 2024, 2025 e 2026 confirmadas no plano gratuito (consulta de 2026-10-27) | token gratuito só por `FOOTBALL_DATA_ORG_TOKEN` (`.env` local ou segredo do Actions), nunca em log; 1 chamada por temporada, ≥ 6 s entre chamadas, espera `X-RequestCounter-Reset` em 429 (adaptador `FootballDataOrgSource`) | `licensed_with_attribution`: Terms and Conditions em vigor desde 2018-06-01, lidos em 2026-10-27. Atribuição exata (7.1): "Football data provided by the Football-Data.org API". Cláusulas 2.3, 6.1, 9.1 e 11.1 no ADR-0008. Usos: `research_local`, `prototype_local`, `public_display_derived` (sem redistribuição) | **Publicação 2026+**; 2024–2025 só **conferência local**. Data = `utcDate` convertido para America/Sao_Paulo, exceto jogo só com data (`SCHEDULED`/`POSTPONED` às 00:00Z, seção "Horário do jogo"); `kickoff_utc` e `kickoff_time_confirmed` desde o ADR-0009; `IN_PLAY`/`PAUSED`/`LIVE` → `scheduled`; `AWARDED` só com placar decidido em `known_exceptions.csv` (`code=awarded`), senão a ingestão falha. Ingestão real em 2026-10-27 (3 chamadas, 2024–2026, versão `v4-20261027T205022Z`) |
| [brasileirao-dataset](https://github.com/leeofernandes1980/brasileirao-dataset) (`brasileirao_dataset`) | Partidas, cartões, gols, estatísticas | 2003–2026, atualizado por GitHub Actions | `git clone` (adaptador `BrasileiraoDatasetSource`) | `research_only_unverified`. Sem arquivo LICENSE. 2003–2023 vêm do dataset de Adão Duque; 2024+ foi coletado da API não oficial do Sofascore, cujos termos restringem coleta automatizada e uso comercial. Usos: `research_local`, `prototype_local` | **Fora da publicação.** Só pesquisa local (`brasileirao ingest --research-source brasileirao_dataset`) e conferência 2003–2023. Em 2024+ a data é o dia UTC do pontapé inicial, sem hora: não dá para converter, e a conferência usa tolerância de ±1 dia |
| [CBF](https://www.cbf.com.br) | Tabela, súmulas, regulamentos (fonte oficial) | temporada corrente | site; sem API pública documentada | Termos do site **a verificar** (falha de TLS em 2026-10-27) | Regulamento 2026 usado para as regras. Nenhum programa lê o site (pendência 5 do ADR-0008, decidida pelo 00 em 2026-10-28): quem confere 2026 é o 01, com evidência pontual nas divergências (seção "Conferência local") |
| [ge.globo](https://ge.globo.com/futebol/brasileirao-serie-a/) | Placar final e tabela (conferência) | temporada corrente | consulta manual no navegador, sem coleta automatizada | Conteúdo jornalístico protegido; usado só como evidência pontual, citando a URL | Evidência de correções manuais (`data/reference/manual_corrections.csv`, ignorado pelo git) |
| [Wikipédia (pt)](https://pt.wikipedia.org) | Classificação e matriz de confrontos | por temporada | consulta manual | CC BY-SA 4.0 | Só conferência pontual; sem automação no pipeline. Na conferência de 2026 o wikitexto da página da Série A 2026 foi baixado uma vez (2026-10-28, `action=raw`) para ler a matriz de confrontos fora do repositório |
| [ESPN](https://africa.espn.com/football/fixtures/_/league/bra.1) | Placar final, status e calendário por data | temporada corrente | consulta pontual de páginas (WebFetch), sem coleta automatizada | Conteúdo protegido; só evidência pontual, citando a URL | Evidência das divergências da conferência de 2026 |
| [Football-Data.co.uk](https://www.football-data.co.uk) | Resultados e odds de fechamento (arquivo BRA) | 2012+ | download CSV | "My data is free", sem licença declarada | Benchmark de odds local (etapa 3). Não é fonte publicada |
| [openfootball](https://github.com/openfootball/south-america) | Resultados | 2018–2026 | GitHub | CC0 declarado, mas o Brasil recente vem do football-data.org | Descartado para publicação (ADR-0008) |
| API-Football | — | a verificar | — | proíbe revenda; termos não lidos (403) | Descartada |
| [Dados Futebol](https://dadosfutebol.com.br) | Dados e análises | — | a investigar | a investigar | Não avaliado |
| Escudos de clubes ([Wikimedia Commons](https://commons.wikimedia.org) e [Wikipédia em português](https://pt.wikipedia.org)) | Escudo de cada clube (SVG ou PNG transparente) | os 20 clubes da Série A 2026, coletados em 2026-10-26 | download manual autorizado pelo usuário; arquivos em `apps/web/assets/crests/`; proveniência por arquivo (URL, página, autor, licença, data de coleta, SHA-256) em `data/reference/crests_provenance.json`, fora da pasta servida pelo site | 17 do Commons sob **PD-textlogo** (Mirassol e São Paulo também PD-shape): domínio público por falta de originalidade, mas **marcas registradas** (`{{Trademarked}}`). 3 (Bragantino, Corinthians, Vasco) **não livres**: © dos clubes | **Em uso** os 17 `livre`. Os 3 não livres estão com `license_status: "nao_livre"`, `used: false` e `replacement: "marcador_neutro"` (decisão do dono de 2026-10-27, histórico em `license_status_history`): a interface mostra um marcador neutro no lugar deles. Marca registrada: só para identificar o clube como dado, nunca como marca do produto |

## Composição por temporada (ADR-0008, Decisão 1)

- A precedência fica em `config.PUBLICATION_SOURCE_BY_SEASON`: 2003–2025 `adaoduque_kaggle`,
  2026+ `football_data_org`. Cada temporada vem de exatamente uma fonte.
- **Sem fallback.** Temporada fora da tabela, fonte sem ingestão, fonte sem partidas da temporada ou
  fonte sem `public_display_derived` fazem a ingestão falhar (`CompositionError`), sem gravar silver
  nem gold. O `brasileirao_dataset` nunca entra no caminho padrão.
- `data/silver/sources.json` (não versionado) registra o modo (`publication` ou `research`), cada
  temporada → fonte → versão do manifesto e número de partidas, e por fonte: origem, versão,
  `retrieved_at`, status de licença, usos, atribuição, temporadas e SHA-256 do manifesto.
- Nenhuma partida `finished` pode ter data posterior ao dia de Brasília da coleta (falha na
  composição) nem à data de referência (`finished_after_reference`, erro no relatório de qualidade).

### `match_id` estável entre fontes

- Formato: `<temporada>-<mandante>-<visitante>`, com os `club_id` canônicos de `clubs.csv`
  (ex.: `2032-clube-a-clube-b`). Cada par mandante/visitante é único na temporada, então o mesmo
  jogo tem o mesmo ID em qualquer fonte. O ID da fonte continua em `source_match_id`.
- Par repetido na mesma temporada (exceção conhecida de 2009): todas as ocorrências recebem o
  sufixo `-r<rodada com 2 dígitos>`. Se a rodada não desambiguar, a ingestão falha.
- A coluna `source` guarda `<fonte>@<versão[:12]>`; com correção manual,
  `<fonte>+manual_correction@<evidência>:<data>` (regra G2).
- Substitui o antigo `bds-<partida_id>`: snapshots e a revisão por rodada precisam ser regerados
  (passo 11 do ADR, Agente 02).

### Temporada do Adão Duque

O dataset não tem coluna de temporada. A temporada é o ano da data, exceto a de 2020, disputada de
agosto de 2020 a fevereiro de 2021 (`adaoduque.CROSS_YEAR_SEASONS`). A contagem de 380 partidas
por temporada no relatório de qualidade confirma a regra.

### Proveniência da v18 do Adão Duque

- Download em 2026-10-27, sem login, pelo endpoint público
  `https://www.kaggle.com/api/v1/datasets/download/adaoduque/campeonato-brasileiro-de-futebol?datasetVersionNumber=18`:
  zip de 707.334 bytes (data de modificação 2026-02-05). Do zip foram copiados para
  `data/raw/adaoduque/v18/` (ignorado pelo git) só os dois arquivos usados; `Legenda.txt`,
  `campeonato-brasileiro-estatisticas-full.csv` e `campeonato-brasileiro-gols.csv` ficaram de fora.
- SHA-256 fixados em `data/reference/source_pins.json`:
  - `campeonato-brasileiro-full.csv`: `4e5bee3000f27dfa71f30389aa4af11c03725393a82d8814fb373659ee94891b`
    (9.165 partidas, 2003–2025, coluna extra `arrecadacao`, fim de linha CRLF; o adaptador lê os dois,
    teste `test_v18_header_with_arrecadacao_and_crlf_is_read`).
  - `campeonato-brasileiro-cartoes.csv`: `6b48b7ceaf2ea5018972f12821571870a9ebd277fca1ccb66045465911fc6b33`
    (20.953 cartões, 2014–2024).
- Os 46 nomes de clube da v18 resolvem para `club_id` canônico sem alias novo
  (`test_club_aliases.py`, lista conferida no arquivo baixado).
- Manifesto: `data/raw/adaoduque_kaggle/v18/manifest.json`. Reingerir os mesmos arquivos produziu
  silver, gold, `sources.json` e manifesto byte a byte idênticos (conferido por SHA-256).
- `retrieved_at` (achado N7 do 06): é o maior mtime dos dois arquivos baixados, porque o Kaggle não informa
  a data do download e o adaptador não baixa nada. A identidade dos dados é a versão (`kaggle-v18`) e o
  SHA-256 fixado, não a data. Na primeira ingestão de uma pasta raw a data fica registrada. Ingestões
  seguintes com os mesmos hashes a mantêm, mesmo que o mtime mude. No workflow, que reconstrói tudo do
  zero, ela é a hora da extração do zip. Essa data não entra em nenhum cálculo: a checagem de resultado
  futuro da composição só pega 2003–2025, todas anteriores.
- 2026-10-28: `license_notes` perdeu a frase "Texto de atribuição provisório até a aprovação do C2". A
  D-033 tornou final a atribuição, que não mudou. Quando só os termos do adaptador mudam, a ingestão
  regrava o manifesto com a mesma data de coleta. Muda o SHA-256 do manifesto, e só o
  `manifest_sha256` do `sources.json` muda junto. Silver e gold ficam idênticos (conferido numa cópia).

### Partidas por temporada e fonte (silver de publicação de 2026-10-27)

| Temporadas | Fonte | Partidas por temporada | Status |
|---|---|---|---|
| 2003, 2004 | `adaoduque_kaggle` v18 | 552 | todas `finished` |
| 2005 | `adaoduque_kaggle` v18 | 462 | todas `finished` |
| 2006–2015, 2017–2025 | `adaoduque_kaggle` v18 | 380 | todas `finished` |
| 2016 | `adaoduque_kaggle` v18 | 379 (exceção conhecida) | todas `finished` |
| 2026 | `football_data_org` `v4-20261027T205022Z` | 380 | 319 `finished`, 60 `scheduled`, 1 `postponed` |

Total: 9.545 partidas (9.165 da v18 + 380 do football-data.org). Cartões na silver: 2014–2024
(7.719 linhas clube × partida); 2025 e 2026 sem cartões.

### Conferência com o espelho do GitHub

Espelho `adaoduque/Brasileirao_Dataset`, HEAD `15f027c3`, comparado com a v18 pela chave
(data, mandante, visitante). Só contagens; o detalhe jogo a jogo fica fora do repositório (decisão B1).

| Arquivo | Resultado |
|---|---|
| Cartões | idênticos linha a linha |
| Partidas | Kaggle 9.165 (2003–2025, `arrecadacao`, CRLF); espelho 8.785 (2003–2024, LF). 8.784 chaves comuns, das quais 3 divergem no placar; 1 chave só no espelho; 381 só na Kaggle (380 de 2025 + a outra ponta da chave órfã) |

Classificação das 4 diferenças, conferidas na RSSF (`rsssf.org/tablesb/braz03.html`, `braz04`,
`braz05` e `braz09`, consulta de 2026-10-27):

| Tipo | Jogos | Temporadas | O que a RSSF registra |
|---|---|---|---|
| Placar errado na v18, mesmo vencedor | 2 | 2003, 2004 | o placar do espelho |
| Placar de campo (v18) × resultado dado pelo tribunal (espelho, com `vencedor` incoerente) | 1 | 2005 | os dois: placar de campo e a decisão do STJD |
| Mando invertido na v18 (a chave órfã; é a duplicidade conhecida de 2009) | 1 | 2009 | o mando do espelho |

Nenhuma foi corrigida: `manual_corrections.csv` não troca mando, e a escolha entre placar de campo e
de tribunal é decisão de modelagem e regra (pendência em `docs/project/status.md`).

## Conferência local (ADR-0008, passo 7)

`brasileirao conference` compara fontes já normalizadas por `match_id` estável e grava o detalhe em
`data/silver/conference_report.json` (não versionado) e as divergências no `changes.jsonl`, sem
corrigir nada. Pares:

| Candidata | Referência | Temporadas | Tolerância de data | Objetivo |
|---|---|---|---|---|
| `football_data_org` | `adaoduque_kaggle` | 2024–2025 | 0 dia | testar a premissa de data de Brasília do Adão Duque (esperado zero divergência) |
| `adaoduque_kaggle` | `brasileirao_dataset` | 2003–2023 | ±1 dia | medir o efeito da troca de fonte no histórico |
| `football_data_org` | `brasileirao_dataset` | 2026 | ±1 dia | conferência local de 2026 (pendência 5 do ADR-0008); divergência em jogo encerrado exige evidência pontual |

Resultado da primeira execução real (2026-10-27; `football_data_org` versão `v4-20261027T205022Z`,
`adaoduque_kaggle` v18, `brasileirao_dataset` `838614dbaee3`). Só contagens (decisão B1):

| Par | Partidas (cand./ref.) | Casadas | Só em uma | Mesma data | Data fora da tolerância | Status diferente | Placar diferente | Rodada diferente |
|---|---|---|---|---|---|---|---|---|
| football-data.org × Adão Duque, 2024–2025 | 760 / 760 | 760 | 0 | 760 | 0 | 0 | 0 | 0 |
| Adão Duque × brasileirao-dataset, 2003–2023 | 8.405 / 8.405 | 8.405 | 0 | 8.405 | 0 | 0 | 0 | 0 |

A premissa de data de Brasília do Adão Duque se confirmou nos 760 jogos de 2024–2025. Em 2003–2023 o
`brasileirao-dataset` repete a v18 inclusive nas 4 diferenças com o espelho (mesma linhagem), então a
troca de fonte não muda nenhum resultado histórico.

### Conferência de 2026 (2026-10-28)

Pendência 5 do ADR-0008, como o 00 a redefiniu: nenhum programa lê o site da CBF; o 01 confere 2026 e
resolve as divergências com evidência pontual. Mesmas ingestões da tabela acima (`v4-20261027T205022Z`
× `838614dbaee3`, ambas de 2026-10-27), sem chamada nova à API. Só contagens (decisão B1); o detalhe
jogo a jogo fica em `data/silver/conference_report.json` e fora do repositório.

| Par | Partidas (cand./ref.) | Casadas | Só em uma | Mesma data | ±1 dia | Data fora da tolerância | Status diferente | Encerradas nas duas | Placar diferente | Rodada diferente |
|---|---|---|---|---|---|---|---|---|---|---|
| football-data.org × brasileirao-dataset, 2026 | 380 / 380 | 380 | 0 | 280 | 75 | 25 | 2 | 318 | 1 | 0 |

Classificação das divergências:

- **Jogos encerrados (2)**, os dois da 32ª rodada, de 26/10. São a captura durante o jogo do
  `brasileirao-dataset` já registrada em "Problemas de qualidade conhecidos":
  - 1 placar diferente, com o jogo encerrado nas duas fontes;
  - 1 jogo encerrado no football-data.org e ainda `scheduled` na fonte de pesquisa.

  Nos dois, a ESPN (página do jogo e calendário do dia) e a matriz de confrontos da Wikipédia (atualizada
  em 26/10) confirmam o football-data.org. **Classificação**: erro ou defasagem da fonte de pesquisa;
  a fonte de publicação está correta, e nenhuma correção manual é necessária.
- **Status de jogo não encerrado (1)**: o jogo adiado da 21ª rodada é `postponed` no football-data.org
  e `scheduled` no `brasileirao-dataset`, sem placar nas duas. A ESPN mostra "Postponed". O
  football-data.org está correto.
- **Datas fora da tolerância (25)**, todas em jogos sem placar:
  - 1 é o adiado;
  - 4 são remarcações das rodadas 33 e 34. Em 3 delas, a ESPN confirma a data do football-data.org; a
    quarta é posterior à página consultada;
  - 20 são das rodadas 36 e 37, ainda sem detalhamento. Cada fonte usa uma data-base diferente, e a ESPN
    mostra horário "TBD". São datas provisórias, que as próximas ingestões atualizam.
- **±1 dia (75)**: o `brasileirao-dataset` grava o dia UTC (jogos noturnos), como em 2024–2025.
- **Checagem extra**: os 319 jogos encerrados no football-data.org foram comparados com a matriz de
  confrontos da Wikipédia. Os 319 placares são iguais; nenhum jogo encerrado falta na matriz, e a matriz
  não tem placar de jogo não encerrado.

## Horário do jogo (ADR-0009, Decisão 2; 2026-10-28)

`MatchRecord` tem dois campos opcionais, gravados em `data/silver/matches.csv` e em
`data/gold/matches_model.csv` (últimas colunas): `kickoff_utc` (ISO 8601 UTC, `2026-10-29T00:30:00Z`)
e `kickoff_time_confirmed` (`True`, `False` ou vazio). Regra do football-data.org
(`football_data_org.kickoff_of`):

| Status na fonte | `kickoff_utc` | `kickoff_time_confirmed` | `match_date` |
|---|---|---|---|
| `TIMED`, `IN_PLAY`, `PAUSED`, `LIVE`, `FINISHED` | `utcDate` | `True` | dia de `utcDate` em Brasília |
| `SCHEDULED`, `POSTPONED`, `SUSPENDED`, `CANCELLED` com `utcDate` às 00:00:00Z | vazio | `False` | dia do próprio `utcDate`, sem conversão |
| esses status com outro horário, e `AWARDED` | `utcDate` (provisório ou que não vale mais) | `False` | dia de `utcDate` em Brasília |

- **Invariante**: com `kickoff_utc`, `match_date` é a data dele em America/Sao_Paulo. O `MatchRecord`
  recusa o contrário, e o `run_quality_checks` acusa `kickoff_date_mismatch` (erro) na silver e no gold.
- **Só a data**: no football-data.org, jogo `SCHEDULED` vem com `utcDate` às 00:00:00Z, um marcador sem
  horário. Na ingestão de 2026-10-27, os 40 `SCHEDULED` (rodadas 35 a 38) e o adiado da rodada 21 estão
  às 00:00Z. As datas desse marcador são as da tabela básica da CBF (rodada 21: 29/07; 35: 18/11; 36:
  21/11; 37: 28/11; 38: 02/12, na tabela do Palmeiras publicada pela Itatiaia, consultada em
  2026-10-28), e não o dia anterior que a conversão para Brasília dava. Por isso esses 41 jogos
  **avançaram 1 dia** na silver (`match_date` no `changes.jsonl`). Jogo encerrado ou com horário
  confirmado não muda de data. Um jogo `TIMED` às 00:00Z é horário real (21h em Brasília) e é
  convertido.
- **Exportação**: `ingest.confirmed_kickoff_utc(kickoff_utc, kickoff_time_confirmed)` devolve o texto
  ISO só com horário confirmado, e `None` nos demais casos. É a regra do `MatchPrediction.kickoff_utc`
  do 04.
- **Fontes sem horário**: Adão Duque e as de conferência ficam com os dois campos vazios. Silver ou
  gold antigos, sem as colunas, continuam válidos: `read_matches` as cria vazias.
- **Histórico de mudanças**: mudança de `kickoff_utc` ou de `kickoff_time_confirmed` entre ingestões vai
  para o `changes.jsonl`, mas só quando a versão anterior já tinha o valor. A primeira ingestão com as
  colunas novas não registra uma linha por jogo.
- **Validação temporal**: inalterada, por `match_date` (dia de Brasília). O horário não muda o que entra
  em ratings, treino ou simulação.
- **Ingestão real de 2026** (raw `v4-20261027T205022Z`, sem chamada nova, em cópia local dos dados):
  319 `finished` e 20 `scheduled` com horário confirmado, 40 `scheduled` e 1 `postponed` sem horário,
  0 violações do invariante em 339 jogos com horário. Nenhum jogo de 2003–2025 tem horário.
- **`hora` do Adão Duque, avaliada e não usada**: a coluna está preenchida em 100% das 9.165 partidas.
  Lida como hora de Brasília, ela bate com o `utcDate` do football-data.org a até 5 min em 755 de 760
  jogos de 2024–2025 (335 exatos; a diferença típica é de 1 a 4 min, então parece o início real, e não
  o marcado). Não foi usada: nenhum consumidor precisa do horário antes de 2026, 2003–2023 não tem uma
  segunda fonte para conferir, e o ADR-0009 fixa os campos vazios para essa fonte. Se for preciso,
  entra com decisão nova.
- **Atraso da fonte no plano gratuito: a medir no ensaio (`dry-run`) do ADR-0009.** A página de
  preços do football-data.org (consultada em 2026-10-28) diz só "Scores delayed" e "Schedules delayed"
  para o plano gratuito, sem números. O `lastUpdated` não serve de medida: é a última alteração do
  registro, e 12 jogos das rodadas 31 e 32 têm o mesmo `2026-10-26T20:20:24Z` (atualização em lote).
  Os 2 jogos encerrados mais recentes (26/10) têm `lastUpdated` 3 h 30 a 4 h depois do fim estimado
  (início + 115 min). Isso é só um limite superior, mas, se o atraso real for desse tamanho, a checagem
  às 2 h 10 do início quase nunca acha o jogo encerrado. Nenhuma chamada nova foi feita: às 18h59 de
  2026-10-28, em Brasília, nenhum jogo do dia tinha começado. A medida pede várias consultas perto do
  fim de um jogo, que é o que o ensaio faz.

## Problemas de qualidade conhecidos

Registrados em `data/reference/known_exceptions.csv` e reportados em `data/gold/quality_report.json`:

- **2009**: Botafogo x Flamengo aparece duas vezes com o mesmo mando (rodadas 12 e 31) na v18.
  Erro de mando confirmado em 2026-10-27 (espelho do GitHub e RSSF): o jogo da rodada 12 foi com
  mando do Flamengo. Mantido como na fonte (a correção manual não troca mando; decisão pendente do
  Agente 00). Os dois jogos recebem `match_id` com sufixo de rodada.
- **2003 e 2004**: 1 placar errado em cada temporada na v18, sem mudar o vencedor (conferência com o
  espelho e a RSSF, acima). Mantidos como na fonte; decisão pendente.
- **2005**: 1 jogo com o placar de campo na v18, mas resultado dado pelo tribunal a outro clube
  (RSSF). Mantido como na fonte; decisão pendente (placar de campo serve ao modelo de gols, o do
  tribunal à classificação).
- **2016**: Chapecoense x Atlético-MG (38ª rodada) não foi disputada. É uma exceção histórica real.
- **2026**: Chapecoense x Vasco (rodada 21) segue sem placar e não foi disputado; é simulado, nunca
  preenchido.
- **2026, captura durante o jogo (fonte de pesquisa)**: a atualização do `brasileirao-dataset` de
  26/10 (commit `838614d`) gravou um jogo em andamento como encerrado, com o placar parcial, e um
  jogo terminado depois da atualização ficou sem placar. As 2 correções com evidência estão no
  registro local `data/reference/manual_corrections.csv` (placares fora do repositório, decisão B1),
  já com o `match_id` estável. Na primeira ingestão real de publicação (2026-10-27) as 2 saíram como
  `manual_correction_redundant` (o football-data.org já mostra os valores conferidos) e foram
  removidas do registro local, que ficou só com o cabeçalho.
- **2024–2026, data do dia UTC no `brasileirao-dataset`**: 207 jogos noturnos com a data do dia
  seguinte (parecer do 06 em `docs/methodology/validation.md`). Sumiu com a troca de fonte: entre a
  silver de pesquisa anterior (`838614d`) e a de publicação, 71 (2024), 67 (2025) e 70 (2026) jogos
  recuaram 1 dia. Em 2026 outros 30 jogos mudaram de data em mais de 1 dia (22 recuaram 2 dias, 8
  avançaram 1 a 3 dias): diferença de calendário entre as fontes, não de fuso.
- **Cartões 2026**: o football-data.org gratuito não traz cartões. Com a fonte de publicação, a
  cobertura de 2026 é zero e o desempate por cartões fica no sorteio com aviso. Os cartões do Adão
  Duque v18 cobrem 2014–2024 (sem 2025).

## Política

1. Não usar uma fonte só porque está acessível: o status de licença precisa estar registrado no
   manifesto e neste catálogo. `public_display_derived` e `redistribution` só com `verified_open` ou
   `licensed_with_attribution`, e `licensed_with_attribution` exige atribuição, URL e data dos termos.
2. Placar ausente é sempre `scheduled`. Nunca vira 0 x 0. Placar parcial (`IN_PLAY`, `PAUSED`) nunca
   entra.
3. Diferenças entre ingestões (resultado, data, rodada), divergências de conferência e correções
   redundantes ou não aplicadas vão para `data/silver/changes.jsonl`. Diferenças são eventos e entram a
   cada ocorrência; divergências e correções são estados e entram uma vez, de novo só se mudarem (N3).
4. Publicação só com a composição do ADR-0008; fontes de conferência nunca entram em `data/gold/`.
   Os termos do football-data.org são relidos no início de cada temporada e antes de mudar o uso
   (`terms_checked_at`).
5. Correção de resultado só com evidência: `data/reference/manual_corrections.csv` (ignorado pelo
   git; formato em `manual_corrections.example.csv`, sintético) registra o valor que a fonte
   mostrava, o valor conferido, o nome e a URL da evidência e a data da conferência, pelo `match_id`
   estável. A ingestão (`data_pipeline/corrections.py`) só aplica a correção enquanto a fonte mostrar
   exatamente o valor registrado. Se a fonte passar a concordar, a correção vira redundante
   (`manual_correction_redundant` no `changes.jsonl`) e deve ser removida; se mudar para um terceiro
   valor, não é aplicada e o conflito vai para o `changes.jsonl` (`manual_correction_not_applied`).
   Mudanças causadas por correção saem no `changes.jsonl` com `origin = manual_correction` e a URL, e
   a coluna `source` da partida passa a `<fonte-base>+manual_correction@<evidência>:<data>`.
6. W.O. (`AWARDED` no football-data.org) só entra com o placar decidido registrado em
   `known_exceptions.csv` (`code=awarded`, `source_name`, `source_match_id`, `home_goals`,
   `away_goals` e a evidência na nota).

## Série B (ADR-0010, 2026-10-29)

| Fonte (`source_name`) | Conteúdo | Cobertura | Acesso | Licença | Papel |
|---|---|---|---|---|---|
| [Wikipédia (pt)](https://pt.wikipedia.org/wiki/Campeonato_Brasileiro_de_Futebol_de_2026_-_S%C3%A9rie_B) (`wikipedia_pt`) | Matriz de confrontos (módulo `sports results`): placar por mandante x visitante, campo `update` | 2025 (revisão fixada `73254466`) e temporada corrente (revisão mais recente na ingestão) | API do MediaWiki (`action=query&prop=revisions`), 1 chamada por temporada; adaptador `serie_b.sources.fetch_wikipedia` | `licensed_with_attribution`: CC BY-SA 4.0 (rodapé conferido em 2026-10-29). Sem data nem rodada | **Publicação Série B**: resultados de 2025 e 2026 |
| [openfootball/south-america](https://github.com/openfootball/south-america) (`openfootball`) | `brazil/YYYY_br2.txt` (Football.TXT): rodada, data, hora, placar | 2018–2024 completos; 2025 só calendário (57 de 380 placares) | raw do GitHub no commit fixado `f51b2dcf5e0f`, SHA-256 em `data/reference/serie_b_source_pins.json` | `licensed_with_attribution`: CC0-1.0 declarada; procedência dos resultados não informada (risco aceito pelo dono) | **Publicação Série B**: 2018–2024 e datas de 2025 |

- Composição, data de corte e ordem imputada de 2026: ADR-0010, Decisão 1. Cadastro de clubes próprio:
  `data/reference/clubs_serie_b.csv`.
- football-data.org: a Série B (`BSB`) devolve 403 no plano gratuito (2026-10-29); não é fonte da Série B.
- Conferência: os 57 placares de 2025 em comum entre openfootball e Wikipédia são iguais.
- Raw, silver e previsão ficam em `data/serie_b/` (fora do git).
