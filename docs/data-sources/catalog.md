# Catálogo de fontes de dados (Agente 01)

Última revisão: 2026-10-27 (implementação do ADR-0008, passos 1 a 9). Toda ingestão grava
`data/raw/<fonte>/<versão>/manifest.json` (`contracts.SourceManifest`), com origem, versão/commit,
data de coleta, SHA-256 dos arquivos, status de licença, usos permitidos (`AllowedUse`) e, para
fontes publicáveis, nome da licença, URL e data de leitura dos termos e texto exato da atribuição.

## Fontes

| Fonte (`source_name`) | Conteúdo | Cobertura | Acesso | Licença / restrições | Papel no projeto (ADR-0008) |
|---|---|---|---|---|---|
| [Adão Duque, "Campeonato Brasileiro de Futebol"](https://www.kaggle.com/datasets/adaoduque/campeonato-brasileiro-de-futebol) (`adaoduque_kaggle`) | Partidas (data dd/mm/aaaa, hora, rodada, mandante, visitante, placar), cartões, gols, estatísticas | 2003–2025 (9.165 partidas segundo a descrição) | Kaggle **versão 18**, baixada pelo dono do produto para `data/raw/adaoduque/v18/` (adaptador `AdaoDuqueSource`, que não baixa nada). SHA-256 fixado em `data/reference/source_pins.json` (`brasileirao pin-adaoduque`). O espelho do GitHub serve só para comparar hashes | `licensed_with_attribution`: GPL-2 declarada no Kaggle (v18; "only" ou "or later" não especificado), termos lidos em 2026-10-27. Coleta do autor "de páginas do Google" (proveniência de segunda mão, risco aceito no ADR). Usos: `research_local`, `prototype_local`, `public_display_derived`, `redistribution` (a licença permitiria; o projeto **não** redistribui sem ADR próprio) | **Publicação 2003–2025.** Implementado e testado só com fixture sintética. **Arquivos reais ainda não baixados** (pendência do dono); hashes ainda não fixados, então a ingestão de publicação falha com mensagem clara |
| [football-data.org](https://www.football-data.org) (`football_data_org`) | API v4, competição BSA: partidas, rodada, status, placar de tempo normal | 2024, 2025 e 2026 confirmadas no plano gratuito (consulta de 2026-10-27) | token gratuito só por `FOOTBALL_DATA_ORG_TOKEN` (`.env` local ou segredo do Actions), nunca em log; 1 chamada por temporada, ≥ 6 s entre chamadas, espera `X-RequestCounter-Reset` em 429 (adaptador `FootballDataOrgSource`) | `licensed_with_attribution`: Terms and Conditions em vigor desde 2018-06-01, lidos em 2026-10-27. Atribuição exata (7.1): "Football data provided by the Football-Data.org API". Cláusulas 2.3, 6.1, 9.1 e 11.1 no ADR-0008. Usos: `research_local`, `prototype_local`, `public_display_derived` (sem redistribuição) | **Publicação 2026+**; 2024–2025 só **conferência local**. Data = `utcDate` convertido para America/Sao_Paulo; `IN_PLAY`/`PAUSED`/`LIVE` → `scheduled`; `AWARDED` só com placar decidido em `known_exceptions.csv` (`code=awarded`), senão a ingestão falha. Testado só com fixture sintética; nenhuma chamada real nesta implementação |
| [brasileirao-dataset](https://github.com/leeofernandes1980/brasileirao-dataset) (`brasileirao_dataset`) | Partidas, cartões, gols, estatísticas | 2003–2026, atualizado por GitHub Actions | `git clone` (adaptador `BrasileiraoDatasetSource`) | `research_only_unverified`. Sem arquivo LICENSE. 2003–2023 vêm do dataset de Adão Duque; 2024+ foi coletado da API não oficial do Sofascore, cujos termos restringem coleta automatizada e uso comercial. Usos: `research_local`, `prototype_local` | **Fora da publicação.** Só pesquisa local (`brasileirao ingest --research-source brasileirao_dataset`) e conferência 2003–2023. Em 2024+ a data é o dia UTC do pontapé inicial, sem hora: não dá para converter, e a conferência usa tolerância de ±1 dia |
| [CBF](https://www.cbf.com.br) | Tabela, súmulas, regulamentos (fonte oficial) | temporada corrente | site; sem API pública documentada | Termos do site **a verificar** (falha de TLS em 2026-10-27) | Regulamento 2026 usado para as regras. Conferência manual dos jogos publicados: pendência do dono |
| [ge.globo](https://ge.globo.com/futebol/brasileirao-serie-a/) | Placar final e tabela (conferência) | temporada corrente | consulta manual no navegador, sem coleta automatizada | Conteúdo jornalístico protegido; usado só como evidência pontual, citando a URL | Evidência de correções manuais (`data/reference/manual_corrections.csv`, ignorado pelo git) |
| [Wikipédia (pt)](https://pt.wikipedia.org) | Classificação e matriz de confrontos | por temporada | consulta manual | CC BY-SA 4.0 | Só conferência manual pontual; sem automação |
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

## Conferência local (ADR-0008, passo 7)

`brasileirao conference` compara fontes já normalizadas por `match_id` estável e grava o detalhe em
`data/silver/conference_report.json` (não versionado) e as divergências no `changes.jsonl`, sem
corrigir nada. Pares:

| Candidata | Referência | Temporadas | Tolerância de data | Objetivo |
|---|---|---|---|---|
| `football_data_org` | `adaoduque_kaggle` | 2024–2025 | 0 dia | testar a premissa de data de Brasília do Adão Duque (esperado zero divergência) |
| `adaoduque_kaggle` | `brasileirao_dataset` | 2003–2023 | ±1 dia | medir o efeito da troca de fonte no histórico |

**Contagens: pendentes.** Os arquivos da v18 do Adão Duque não foram baixados e a ingestão real do
football-data.org não foi executada nesta implementação. Só contagens entram aqui (decisão B1).

## Problemas de qualidade conhecidos

Registrados em `data/reference/known_exceptions.csv` e reportados em `data/gold/quality_report.json`:

- **2009**: Botafogo x Flamengo aparece duas vezes com o mesmo mando (rodadas 12 e 31) na fonte
  histórica. Mantido como na fonte até confirmação. Hipótese: o mando do jogo da rodada 12 era do
  Flamengo. Os dois jogos recebem `match_id` com sufixo de rodada.
- **2016**: Chapecoense x Atlético-MG (38ª rodada) não foi disputada. É uma exceção histórica real.
- **2026**: Chapecoense x Vasco (rodada 21) segue sem placar e não foi disputado; é simulado, nunca
  preenchido.
- **2026, captura durante o jogo (fonte de pesquisa)**: a atualização do `brasileirao-dataset` de
  26/10 (commit `838614d`) gravou um jogo em andamento como encerrado, com o placar parcial, e um
  jogo terminado depois da atualização ficou sem placar. As 2 correções com evidência estão no
  registro local `data/reference/manual_corrections.csv` (placares fora do repositório, decisão B1),
  já com o `match_id` estável. Segundo a conferência da seção 8.3 da proposta C1, o football-data.org
  já mostra os valores corrigidos: na primeira ingestão real de publicação elas devem sair como
  `manual_correction_redundant` no `changes.jsonl` e então ser removidas.
- **2024–2026, data do dia UTC no `brasileirao-dataset`**: 207 jogos noturnos com a data do dia
  seguinte (parecer do 06 em `docs/methodology/validation.md`). Some com a troca de fonte.
- **Cartões 2026**: o football-data.org gratuito não traz cartões. Com a fonte de publicação, a
  cobertura de 2026 é zero e o desempate por cartões fica no sorteio com aviso. Os cartões do Adão
  Duque cobrem só temporadas encerradas.

## Política

1. Não usar uma fonte só porque está acessível: o status de licença precisa estar registrado no
   manifesto e neste catálogo. `public_display_derived` e `redistribution` só com `verified_open` ou
   `licensed_with_attribution`, e `licensed_with_attribution` exige atribuição, URL e data dos termos.
2. Placar ausente é sempre `scheduled`. Nunca vira 0 x 0. Placar parcial (`IN_PLAY`, `PAUSED`) nunca
   entra.
3. Diferenças entre ingestões (resultado, data, rodada), divergências de conferência e correções
   redundantes ou não aplicadas vão para `data/silver/changes.jsonl`.
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
