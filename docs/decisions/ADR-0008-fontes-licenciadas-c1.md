# ADR-0008 — Fontes licenciadas para publicação (condição C1): Adão Duque v18 até 2025 e football-data.org de 2026 em diante

- Status: **aceito com condições** (2026-10-27). Aprova, com ajustes, a proposta do Agente 01 em
  `docs/data-sources/c1-fonte-licenciada.md`. **Nada foi implementado.** A condição C1 do ADR-0007
  só é cumprida quando o plano da seção "Plano de implementação" estiver concluído com evidência, o
  Agente 06 tiver revalidado o backtest e o dono do produto tiver cumprido as pendências da seção
  "Pendências do dono do produto".
- Responsáveis: Agente 00 (decisão), Agente 01 (implementação), Agentes 02 e 06 (recálculo e
  revalidação), Agente 07 (persistência e gate), Agentes 08 e 05 (texto de atribuição, C2).
- Substitui em parte: ADR-0002 (fonte de publicação) e o item 4 do ADR-0007 (persistência do
  SQLite). Ver os adendos nesses ADRs.
- Não é parecer jurídico. Decide com base no texto das licenças e dos termos lidos pelo 01 em
  2026-10-27.

## Contexto

- A publicação pública está bloqueada (ADR-0002, C1 do ADR-0007) porque 2024+ vem do Sofascore via
  `brasileirao-dataset`, sem licença.
- O 01 avaliou 9 fontes. A consulta de teste ao football-data.org (seção 8 da proposta) mostrou:
  - o plano gratuito devolve 2024, 2025 e 2026 completas;
  - 0 divergências de placar em 1.079 jogos encerrados contra a fonte atual;
  - 207 jogos noturnos de 2024–2026 com a data do dia UTC na fonte atual, um dia depois da data de
    Brasília. O `FootballDataOrgSource` atual repetiria o erro, porque tira a data de `utcDate`;
  - 27 nomes de clubes sem alias em `data/reference/clubs.csv`.
- O snapshot persistido (`snapshots.payload`) contém placares observados da temporada
  (`MatchPrediction.home_goals/away_goals`, `MatchImpactInfo` da revisão por rodada) e a tabela. Um
  SQLite de snapshots é, portanto, um conjunto de placares, e não só de números derivados.
- O export do site (`apps/web/data/api/`) só tem a temporada corrente (2026) e métricas agregadas.
- `DataInfo` do snapshot e `load_inputs` em `pipeline.py` só aceitam um manifesto e uma fonte.

## Decisão 1 — Combinação de fontes: aprovada com ajustes

| Temporadas | Papel | Fonte | Entra no gold, no modelo e no site? |
|---|---|---|---|
| 2003–2025 | publicação | Adão Duque, "Campeonato Brasileiro de Futebol", **Kaggle versão 18**, fixada pelo SHA-256 de cada arquivo | sim |
| 2026+ | publicação | **football-data.org** v4, competição BSA, plano gratuito | sim |
| 2024–2025 | conferência local | football-data.org | **não** |
| 2003–2026 | conferência local | `brasileirao-dataset` (fonte atual) | **não** |
| corrente | conferência manual | CBF; Wikipédia (pt) e ge.globo como evidência pontual | **não** |

Regras:

- **Sem fallback silencioso.** Temporada sem fonte de publicação faz a ingestão falhar. Ela nunca
  cai para o `brasileirao-dataset`.
- Fontes de conferência nunca entram em `data/gold/`. Divergências vão para um relatório de
  conferência e para o `changes.jsonl`, sem correção automática. A correção manual continua exigindo
  evidência (política 5 do catálogo).
- 2024–2025 vêm do Adão Duque, e não do football-data.org, para limitar a dependência da cláusula
  9.1 à temporada corrente. É uma escolha de risco, não de cobertura.

### Avaliação dos riscos e condições

| Risco | Avaliação do 00 | Condição |
|---|---|---|
| **GPL-2 em dados** (Adão Duque) | As obrigações da GPL-2 (aviso, texto da licença, mesma licença nas cópias e modificações) disparam ao **copiar e distribuir** o conjunto. Exibir resultados derivados (ratings, probabilidades) não é distribuição do conjunto. Placares históricos não vão para o site, cujo export só tem a temporada corrente | Os arquivos brutos e normalizados do Adão Duque **não são versionados** no repositório público nem publicados (`data/raw/`, `data/silver/` e `data/gold/matches_model.csv` continuam ignorados). Mesmo sem obrigação, o site dá crédito ao autor e cita a GPL-2 (C2). Qualquer redistribuição futura exige ADR próprio e vai com o texto da GPL-2, o aviso de origem e a mesma licença |
| **"Coletamos os dados de páginas do Google"** | Proveniência de segunda mão: o autor pode ter licenciado sob GPL-2 dados que não eram dele para licenciar. Placar é fato e não é obra (Lei 9.610/98), mas a compilação pode ser protegida. O risco é baixo para fatos exibidos como resultados derivados, e maior para redistribuição em lote, que não faremos | Risco aceito pelo dono por escrito. Conferência cruzada: 2024–2025 contra o football-data.org e 2003–2023 contra o `brasileirao-dataset`. Pedido de confirmação ao autor é recomendado, não obrigatório. Plano B registrado em "Alternativas" |
| **Cláusula 9.1** (cancelada a conta, o site não pode mais referenciar os dados) | Aceitável: plano gratuito declarado "Forever", conta no nome do dono, sem cobrança a cancelar. A exposição fica limitada a 2026+ | Cada snapshot registra as fontes que usou (contrato da Decisão 2), para que uma retirada seja executável. Procedimento: se a conta for cancelada, o site sai do ar ou volta a uma página sem dados até um novo ADR. Risco aceito pelo dono |
| **Cláusula 11.1** (termos mudam sem aviso) | Risco operacional | O 01 relê os termos no início de cada temporada e sempre antes de mudar o uso, registrando `terms_checked_at` no manifesto. Mudança material reabre este ADR |
| **Cláusula 6.1** (credencial fora de repositório de código aberto) | Segredo criptografado do GitHub Actions **é aceitável**: fica nas configurações do repositório, não no código nem no histórico do git, não é exposto em forks nem em logs (mascarado). É a leitura que o 00 adota. A literalidade da cláusula fica registrada como risco aceito pelo dono | Token só em `FOOTBALL_DATA_ORG_TOKEN` (segredo do Actions) e no `.env` local (ignorado). Nunca impresso, nem em log estruturado. Workflows que usam o segredo só rodam em `schedule` e `workflow_dispatch` na `main`, **nunca** em `pull_request_target` nem em PR de fork. O 06 audita com `git grep` antes de tornar o repositório público |
| **Cláusula 2.3** (uma chave por aplicação; na web, um domínio) | `<usuario>.github.io/<repo>` é um único nome de domínio servindo uma única aplicação. O uso local e o do Actions são da mesma aplicação, porque geram o mesmo site. **Aceitável** | A chave não é reutilizada em nenhum outro projeto, demonstração ou domínio. Domínio próprio no futuro: o site passa a responder só por ele (o `github.io` redireciona) e o 00 registra a mudança |
| **8.1 e 8.2** (sem garantia de exatidão ou disponibilidade) | Igual a qualquer fonte | Gate e conferência com a CBF dos jogos publicados (C1). Partida sem placar continua `scheduled`. `IN_PLAY` e `PAUSED` viram `scheduled`, o que elimina a captura de placar parcial vista em 26/10 |
| **Cartões 2026** | Sem fonte licenciada: a cobertura da temporada corrente cai de 185/308 para 0 | O desempate por cartões fica no sorteio com aviso (comportamento atual abaixo de 95%). O 03 confirma o comportamento com cobertura zero |

## Decisão 2 — Contrato de licença (`contracts.py`)

### `LicenseStatus` (valores exatos)

```python
class LicenseStatus(StrEnum):
    VERIFIED_OPEN = "verified_open"
    LICENSED_WITH_ATTRIBUTION = "licensed_with_attribution"
    RESEARCH_ONLY_UNVERIFIED = "research_only_unverified"
    REQUIRES_AGREEMENT = "requires_agreement"
    BLOCKED = "blocked"
```

- `licensed_with_attribution`: licença ou termos **lidos e registrados numa data**, que permitem
  exibir os dados e resultados derivados num site público **com atribuição obrigatória**. Pode
  haver obrigações adicionais, descritas em `license_notes`.
- `verified_open` continua reservado a licença aberta sem dúvida de proveniência (ex.: CC0 de
  origem própria). O Adão Duque **não** entra aqui, por causa da coleta de segunda mão.
- Ordem de restrição, da mais permissiva para a mais restritiva: `verified_open` <
  `licensed_with_attribution` < `research_only_unverified` < `requires_agreement` < `blocked`.

### `AllowedUse` (vocabulário fechado; substitui as strings livres)

```python
class AllowedUse(StrEnum):
    RESEARCH_LOCAL = "research_local"
    PROTOTYPE_LOCAL = "prototype_local"
    PUBLIC_DISPLAY_DERIVED = "public_display_derived"
    REDISTRIBUTION = "redistribution"
```

- `public_display_derived`: o site público pode exibir resultados derivados (tabela, ratings,
  probabilidades, revisão por rodada) **e** os fatos de partida que a interface precisa (placar,
  data, rodada) da temporada exibida, dentro do export do produto e com a atribuição. Não inclui
  arquivos de dados em lote.
- `redistribution`: a licença permite publicar os dados brutos ou normalizados em lote (CSV,
  SQLite, dump). Declarar o uso **não autoriza exercê-lo**: a política do projeto (Decisão 3) não
  redistribui nada sem ADR próprio.
- `research_local` e `prototype_local` mantêm o sentido atual. Manifestos antigos continuam válidos.

### `SourceManifest`: campos novos

| Campo | Tipo | Obrigatório quando |
|---|---|---|
| `allowed_uses` | `list[AllowedUse]` | sempre (já existe; passa a ser validado) |
| `license_name` | `str \| None` | `licensed_with_attribution` ou `verified_open` |
| `terms_url` | `str \| None` | idem |
| `terms_checked_at` | `date \| None` | idem |
| `attribution` | `str \| None` (texto exato) | `licensed_with_attribution` |

Validação (`model_validator`): `public_display_derived` ou `redistribution` só com status
`verified_open` ou `licensed_with_attribution`. `licensed_with_attribution` sem `attribution`,
`terms_url` ou `terms_checked_at` é erro.

### Valores por fonte

| Fonte (`source_name`) | `license_status` | `allowed_uses` | `attribution` |
|---|---|---|---|
| `adaoduque_kaggle` | `licensed_with_attribution` | `research_local`, `prototype_local`, `public_display_derived`, `redistribution` | crédito ao autor, ao Kaggle v18 e à GPL-2.0 (texto final em C2, 08 e dono) |
| `football_data_org` | `licensed_with_attribution` | `research_local`, `prototype_local`, `public_display_derived` | `Football data provided by the Football-Data.org API` (exato, cláusula 7.1) |
| `brasileirao_dataset` | `research_only_unverified` (sem mudança) | `research_local`, `prototype_local` | — |

`license_name`: "GPL-2.0 (declarada no Kaggle, versão 18; 'only' ou 'or later' não especificado)"
e "football-data.org Terms and Conditions (em vigor desde 2018-06-01)". `terms_checked_at`:
2026-10-27 para as duas, até a próxima releitura.

### Snapshot (`storage/schema.py`, interface do 00)

`DataInfo` ganha `sources: list[DataSourceInfo]`, com `source_name`, `origin`, `version`,
`seasons: list[int]`, `retrieved_at`, `license_status`, `allowed_uses` e `attribution`. Os campos
atuais ficam: `source` (nomes unidos), `version` (versão composta, que vira o `data_version`) e
`license_status` (**o mais restritivo** entre as fontes). `schema_version` sobe.

### O que o gate de publicação aceita

O gate (07 implementa, 06 audita) só libera o deploy se **todas** valerem:

- **G1.** Cada linha de `data/gold/matches_model.csv` tem fonte-base cujo manifesto inclui
  `public_display_derived` e status `verified_open` ou `licensed_with_attribution`. Uma linha de
  `brasileirao_dataset` ou de fonte de conferência reprova.
- **G2.** Linha com correção manual só passa se a fonte-base dela passar no G1 e houver URL de
  evidência. A coluna `source` passa a guardar a fonte-base, por exemplo
  `football_data_org+manual_correction@<evidência>:<data>`.
- **G3.** `data.sources` do snapshot cobre todas as temporadas de `model.training_seasons` e a
  temporada exibida, e `data.license_status` é `verified_open` ou `licensed_with_attribution`.
- **G4.** O texto exato de `attribution` de cada fonte `licensed_with_attribution` aparece no export
  (`predictions.json`, em `data.sources`) e no HTML servido (rodapé).
- **G5.** O artefato do Pages só contém o site estático e os 6 JSON do export: nenhum `*.sqlite`,
  `*.csv`, `data/raw/`, `data/silver/` nem `data/gold/matches_model.csv`.

Se qualquer item falhar, nada é publicado e o site anterior fica no ar (ADR-0007, item 8).

## Decisão 3 — Persistência do SQLite: repositório privado separado

> **Substituída em 2026-10-28** pelo adendo do Agente 07, confirmado pelo 00 com ajustes (fim deste
> arquivo): não há repositório de estado nem `STATE_REPO_TOKEN`; o site é reconstruído do zero a cada
> execução. Continuam valendo desta seção: a revogação do asset público, a proibição de SQLite, raw e
> silver em artefatos públicos e a identificação da história como reconstrução. O texto abaixo fica
> como registro.

- **Revogado:** o asset público `snapshots-db` (item 4 do ADR-0007). Ele nunca é criado no
  repositório público.
- **Decidido:** repositório **privado** e gratuito na conta do dono (nome sugerido:
  `brasileirao-predictions-state`). Guarda:
  - o `snapshots.sqlite` como asset de release, com as **3 versões anteriores** mantidas como cópia
    secundária;
  - os arquivos da versão 18 do Adão Duque e o manifesto com SHA-256, para o workflow não depender
    de credencial do Kaggle.
- **Acesso:** credencial restrita só a esse repositório, com leitura e escrita de conteúdo, guardada
  num segredo do repositório público (nome sugerido: `STATE_REPO_TOKEN`). Pode ser um
  fine-grained PAT ou uma deploy key: o 07 escolhe e registra a validade máxima e a renovação
  (**a verificar**). Mesmas regras de uso do segredo da Decisão 1, cláusula 6.1.
- **Artefatos do Actions no repositório público não levam SQLite, raw nem silver.** Em repositório
  público, os artefatos podem ser baixados por terceiros (**a verificar** pelo 07). Hoje o
  `update-predictions.yml` envia `data/snapshots/snapshots.sqlite` como artefato: isso precisa sair
  antes de qualquer execução no repositório público.
- A checagem de não regressão do ADR-0007 (número de snapshots e última `reference_date`) continua,
  agora contra o asset privado.
- **Histórico publicado recomeça limpo.** O banco atual (snapshots 1 a 29) foi gerado com dados do
  Sofascore e continua só como arquivo local de pesquisa. O banco privado nasce só com snapshots de
  fontes licenciadas. A história de probabilidades de 2026 pode ser **reconstruída** (02 e 04),
  rodando snapshots nas datas de referência passadas com as fontes novas e respeitando a validação
  temporal. Cada snapshot reconstruído registra `generated_at` real e é identificado como
  reconstrução, nunca como previsão feita na época.

Alternativas descartadas:

- Asset público só com snapshots derivados: o payload tem placares e a tabela, então continuaria
  sendo redistribuição em lote, e copiado não volta (cláusula 9.1).
- Asset público criptografado: exige gestão de chave, e o arquivo continua sendo uma cópia pública
  de dados de terceiros. Não é mais simples que o repositório privado.
- Não persistir: perde a história de probabilidades e a revisão por rodada.

## Plano de implementação (ordem obrigatória)

### Agente 01

1. **Contrato.** Em `contracts.py`: `LicenseStatus.LICENSED_WITH_ATTRIBUTION`, `AllowedUse`, os
   campos novos de `SourceManifest` e o validador da Decisão 2. Testes do validador, com uma
   asserção por teste.
2. **`FootballDataOrgSource`:**
   - `match_date` = `utcDate` convertido para `ZoneInfo("America/Sao_Paulo")` antes de `.date()`;
   - teste com fixture sintética de um jogo às 21h30 de Brasília (`00:30Z` do dia seguinte), que
     tem de cair no dia de Brasília;
   - token só por `FOOTBALL_DATA_ORG_TOKEN`, nunca em log;
   - intervalo mínimo de 6 s entre chamadas e respeito a `X-RequestCounter-Reset` em 429;
   - `retrieved_at` por requisição e payload bruto em `data/raw/football_data_org/<versão>/`, com
     manifesto e SHA-256;
   - `AWARDED` só vira `finished` se estiver registrado em `known_exceptions.csv` com o placar
     decidido. Fora disso, a ingestão falha com mensagem clara, sem gravar nada.
3. **`AdaoDuqueSource`:**
   - lê `data/raw/adaoduque/v18/`, com os arquivos baixados pelo dono. Não baixa do Kaggle nem guarda
     credencial;
   - data `dd/mm/aaaa`, tratada como data de Brasília. A premissa é verificada no passo 7, contra o
     football-data.org 2024–2025 convertido;
   - sem placar, a partida fica `scheduled`;
   - manifesto com os valores da Decisão 2 e SHA-256 por arquivo;
   - fixture sintética em `tests/fixtures/`, marcada `synthetic` no conteúdo;
   - o espelho do GitHub só serve para comparar hashes, nunca como fonte.
4. **Aliases** em `data/reference/clubs.csv`: os 27 da seção 8.4 e os nomes do Adão Duque. Testes:
   todo nome das fixtures resolve, nenhum alias fica órfão e nenhum alias aponta para dois clubes.
5. **Ingestão por temporada com precedência:**
   - tabela de precedência da Decisão 1 em `config.py`. O 00 autoriza o 01 a adicionar só essa
     constante, com handoff;
   - `data/silver/sources.json` registra a composição (temporada → fonte → versão do manifesto);
   - `match_id` estável entre fontes, definido e documentado pelo 01 no catálogo. Ele precisa
     tratar a duplicidade de 2009 (exceção conhecida);
   - temporada sem fonte de publicação faz a ingestão falhar;
   - o `brasileirao-dataset` sai do caminho padrão e só roda com opção explícita de pesquisa.
6. **Correções manuais:** as 2 de `manual_corrections.csv` estão ligadas a IDs do
   `brasileirao-dataset`. Segundo a seção 8.3, o football-data.org já concorda com os valores
   corrigidos, então elas devem sair como redundantes, com o registro no `changes.jsonl`. A coluna
   `source` passa a guardar a fonte-base (G2).
7. **Relatório de conferência local:**
   - football-data.org 2024–2025 contra o Adão Duque (placar, data de Brasília, rodada);
   - Adão Duque 2003–2023 contra o `brasileirao-dataset`;
   - saída em `data/silver/`, que não é versionado. No catálogo entram só as contagens, sem placares
     reais (decisão B1);
   - divergência de placar não é corrigida automaticamente: é resolvida com evidência ou registrada
     como exceção antes da publicação.
8. **Catálogo e proveniência:**
   - linha nova para o Adão Duque; football-data.org e `brasileirao-dataset` atualizados para o
     papel da Decisão 1;
   - status da proposta C1 trocado para "aprovada com ajustes (ADR-0008)".
9. **Evidência:** `pytest`, `ruff check` e `mypy` verdes; ingestão real local com contagens por
   temporada e fonte; o CI sem dados continua passando.

**Fora do escopo do 01 agora:**
- automação da Wikipédia (fica manual);
- conferência com a CBF (pendência do dono);
- fonte de cartões para 2026;
- API-Football, openfootball e Football-Data.co.uk (o benchmark de odds segue como estava);
- temporadas do football-data.org anteriores a 2024;
- qualquer redistribuição de dados;
- mudanças no workflow (07), no `schema.py` (00) e no modelo (02);
- **corrigir a data no `BrasileiraoDatasetSource`**: a fonte só traz a data do dia UTC, sem hora,
  então não dá para converter com segurança. Ela sai do caminho de publicação. A limitação fica
  documentada e a conferência com ela usa tolerância de ±1 dia. O 06 decide se precisa de algo mais
  (ver dependência abaixo).

### Depois do 01

10. **00 e 04:** `DataInfo.sources` e `schema_version` em `storage/schema.py`; `load_inputs` em
    `pipeline.py` lê a composição (`sources.json`) em vez de um único manifesto; `data_version`
    composto. *Implementado pelo 00 em 2026-10-27 (commit `bbf2a92`, schema 1.2), com o gate G1 a
    G5 em `brasileirao.publication_gate`; revisão do 04 e auditoria do 06 pendentes. Ver
    `docs/project/status.md`.*
11. **02:** recalcular ratings, treino e `model_config.json` sem o Sofascore; `model_version` e
    `data_version` novos; regenerar a revisão por rodada; reconstruir a história de probabilidades
    de 2026, identificada como reconstrução (Decisão 3).
12. **06:**
    - revalidar o backtest com as datas corretas e registrar as métricas em
      `docs/methodology/validation.md`;
    - auditar a validação temporal, o relatório de conferência e as regras G1 a G5;
    - **dependência em aberto:** a avaliação do impacto do deslocamento de data de 2024–2026, já em
      andamento no 06. Ela não bloqueia os passos 1 a 9, mas é entrada obrigatória do passo 12, e o
      `model_version` novo só é aceito depois dela.
13. **07:** ~~repositório privado de estado~~ (substituído pela reconstrução a cada execução, adendo
    de 2026-10-28), segredo, gate G1 a G5, remoção do SQLite dos artefatos
    públicos e adendo em `docs/architecture/deploy.md`.
14. **08 e 05:** texto de atribuição (C2), com aprovação do dono.

## Pendências do dono do produto

1. **Baixar a versão 18 do dataset de Adão Duque no Kaggle** (exige conta) para
   `data/raw/adaoduque/v18/` e depois enviá-la ao repositório privado de estado.
2. **Aceitar por escrito os riscos residuais:** cláusulas 9.1 e 11.1, GPL-2 em dados com coleta "de
   páginas do Google", ausência de garantia de exatidão e a leitura do 00 sobre as cláusulas 6.1 e
   2.3.
3. *(Reduzido em 2026-10-28: sem repositório de estado, resta só cadastrar o segredo
   `FOOTBALL_DATA_ORG_TOKEN`.)* **Criar o repositório privado de estado** e a credencial restrita a ele. Cadastrar os segredos
   `FOOTBALL_DATA_ORG_TOKEN` e `STATE_REPO_TOKEN`. Nenhum agente manipula o valor dos tokens.
4. **Aprovar os textos de atribuição** (C2), com o 08.
5. **Termos da CBF:** ler no navegador e definir quem faz a conferência manual dos jogos publicados
   (exigida pelo C1).
6. **Confirmar o domínio único** `<usuario>.github.io/<repo>` como o domínio da chave (2.3).
7. **Aceitar que a história publicada de probabilidades recomeça** ou é reconstruída e identificada
   como tal (Decisão 3).
8. Opcional: escrever ao autor do dataset, pedindo confirmação da GPL-2 para 2024–2025 e para o
   espelho do GitHub, e perguntando a origem dos dados.

### Registro do dono do produto (2026-10-27)

Mensagem do dono no chat, literal: "Aceito os riscos residuais do ADR-0008 (cláusulas 9.1, 11.1, 6.1
e 2.3 do football-data.org, GPL-2 do Adão Duque com coleta de segunda mão, sem garantia de
exatidão, história publicada reconstruída) e a licença MIT para o código."

- Itens 2, 6 e 7: **aceitos**.
- Item 1: **feito** pelo orquestrador, a pedido do dono. A v18 foi baixada do endpoint público do
  Kaggle, sem login, e os hashes foram fixados em `data/reference/source_pins.json`. Ver
  `docs/data-sources/catalog.md`.
- Item 3: **reduzido** (00, 2026-10-28). Sem repositório de estado nem `STATE_REPO_TOKEN` (adendo
  confirmado no fim deste arquivo). Resta ao dono **só** cadastrar o segredo `FOOTBALL_DATA_ORG_TOKEN`.
- Item 4: **cumprido por D-033** (00, 2026-10-28). Ver "Registro do 00 sobre as pendências 4 e 5".
- Item 5: **decidido pelo 00** (2026-10-28), sem ação do dono. Ver o mesmo registro.
- Item 8: em aberto (opcional; não bloqueia).

### Registro do 00 sobre as pendências 4 e 5 (2026-10-28)

- **Pendência 4 (textos de atribuição, C2): cumprida por D-033**, decisão do Agente 08 sob a delegação
  D-022 (`docs/brand/BRAND_DECISIONS.md`). Motivos:
  - D-022 delega ao 08 os textos da interface sem aprovação prévia, e o dono pediu para participar o
    mínimo;
  - o conteúdo jurídico dos textos não é discricionário. A atribuição do football-data.org é a frase
    exata da cláusula 7.1. A do Adão Duque é o crédito ao autor, ao Kaggle v18 e à GPL-2.0 que a
    Decisão 1 já exigia, e o dono aceitou por escrito os riscos da GPL-2 em 2026-10-27;
  - o G4 confere as duas atribuições, literalmente, no export e no HTML do artefato.
  A Q18 continua aberta só como revisão posterior do dono (D-022), sem bloquear. Se ele mudar o texto
  do Adão Duque, o manifesto, o `index.html` e o G4 mudam juntos.
- **Pendência 5 (CBF): decidida pelo 00, sem ação do dono.**
  - Nenhum programa lê o site da CBF: não há coleta, cópia nem redistribuição. Ela é só consultada
    por uma pessoa, como qualquer leitor, para conferir um fato pontual. Por isso a leitura dos termos
    de uso deixa de ser pré-requisito. Uma coleta automatizada exigiria ler os termos e um ADR.
  - **Quem confere: o Agente 01.** Antes da primeira publicação, e depois a cada mudança de fonte ou
    de temporada, ele roda a conferência local dos jogos encerrados da temporada exibida
    (football-data.org contra o `brasileirao-dataset`, só local, tolerância de ±1 dia na data). Toda
    divergência de placar é resolvida com evidência pontual (página da partida na CBF ou no ge.globo,
    com URL e data) ou registrada como exceção. O catálogo recebe só as contagens.
  - Não se exige conferir cada placar contra a súmula da CBF. O controle adotado é o G1 a G5, mais a
    conferência cruzada e as 0 divergências em 1.079 jogos (seção 8 da proposta do 01). É isso que
    "conferência com a CBF" passa a significar no C1 do ADR-0007.
- Licença do código: MIT (`LICENSE` na raiz). Ela não cobre dados de terceiros nem marcas.

## Alternativas

- **football-data.org para 2024–2025 também:** possível pela cobertura, mas amplia a dependência da
  9.1. É o plano B se o dono não aceitar o risco do Adão Duque para essas temporadas.
- **Plano B para 2003–2023**, se o Adão Duque for recusado: consultar quais das 10 temporadas
  listadas o plano gratuito do football-data.org devolve. O resto do histórico ficaria sem fonte
  publicável, o que exige reavaliar a janela de treino (02 e 06).
- **openfootball (CC0):** descartado para publicação. O Brasil recente vem do football-data.org e
  está 5 semanas atrasado.
- **API-Football:** descartada (proíbe revenda, termos não lidos, sem vantagem).
- **Wikipédia (CC BY-SA):** só conferência. Sem data por jogo e com compartilhamento pela mesma
  licença.

## Consequências

- C1 passa a ter um caminho executável com custo zero. A publicação continua bloqueada até o plano
  e as pendências estarem concluídos, com evidência.
- Os números do site vão mudar: o modelo é recalculado sem o Sofascore e 207 datas mudam de dia. O
  `model_version` novo é obrigatório.
- O desempate por cartões em 2026 vai para o sorteio com aviso.
- Novo segredo e novo repositório para o 07 operar. O risco R12 muda de forma (ver
  `docs/project/risks.md`).
- `contracts.py` (01), `schema.py` (00) e o gate (07) passam a carregar a licença de ponta a ponta,
  do manifesto ao deploy.

## Adendo proposto pelo Agente 07 (2026-10-27): Decisão 3 sem repositório de estado — **confirmado pelo 00 com ajustes (2026-10-28)**

- **Proposta:** substituir o repositório privado de estado e o `STATE_REPO_TOKEN` por
  **reconstrução completa a cada execução** do `publish-site.yml`. O runner começa vazio e termina
  sem guardar nada: sem SQLite em release, artefato, cache ou outro repositório.
  - A história de probabilidades de 2026 vira um snapshot por rodada (`simulate
    --history-from-round 1`, 10 mil simulações por ponto) e o snapshot atual (100 mil), com semente
    2026. A revisão rodada a rodada é refeita do zero (`review-rounds`, 20 mil). A validação temporal
    continua a do `build_snapshot`: cada ponto só usa partidas até a sua data de referência.
  - A v18 do Adão Duque é baixada do endpoint público do Kaggle (sem login) e conferida pelo SHA-256
    de `data/reference/source_pins.json`; divergência faz o workflow falhar. Os arquivos não são
    versionados nem publicados (GPL-2, Decisão 1). Isso substitui "os arquivos da versão 18 ... no
    repositório de estado".
- **Por quê:** é o desenho com menos peças para o dono (um segredo só, `FOOTBALL_DATA_ORG_TOKEN`; nenhum
  repositório extra, nenhuma credencial com validade a renovar) e com menos superfície para vazar
  placares em lote. Em repositório público os minutos do Actions são gratuitos. Tempo medido: ver
  `docs/architecture/deploy.md`, "Tempos medidos".
- **Consequências que o 00 precisa aceitar:**
  1. Todo ponto da história publicada é uma **reconstrução**, feita com o modelo e os dados do dia da
     execução, não uma previsão registrada na época (já exigido por esta Decisão 3). Quando o modelo
     ou um placar muda, a história inteira muda junto. O `generated_at` de cada ponto é o da execução.
     O schema não tem um campo "reconstrução"; o texto da interface precisa dizer isso (08/05).
  2. A checagem de não regressão (número de snapshots e `reference_date`) passa a comparar a
     `reference_date` do artefato novo com a do `predictions.json` no ar.
  3. Snapshots por rodada perdem o papel de registro histórico imutável no deploy (ADR-0004 continua
     valendo para o SQLite local). O registro do que foi publicado fica no histórico do Actions.
  4. O risco R12 (`docs/project/risks.md`) deixa de existir na forma atual: não há estado a perder.
     Novo risco: o endpoint do Kaggle mudar ou exigir login (o workflow falha e o site anterior fica no ar).
- **Alternativa, se o 00 recusar:** a Decisão 3 original (repositório privado com `STATE_REPO_TOKEN`)
  continua implementável sem mudar o resto do workflow: bastaria restaurar o SQLite antes do
  `simulate`, trocar `--history-from-round 1` pelo snapshot do dia e salvar o banco no fim.

### Decisão do 00 sobre o adendo (2026-10-28): **confirmado, com ajustes**

O 00 confirma a reconstrução completa a cada execução. A Decisão 3 original deixa de valer na parte do
repositório privado e do `STATE_REPO_TOKEN`.

- **Por que confirmar.** São menos peças para o dono: um segredo só, nenhum repositório extra, nenhuma
  credencial com validade a renovar. Também há menos superfície de vazamento: nenhum SQLite com placares
  sobrevive à execução. Os riscos que a Decisão 3 tratava somem (R12) ou diminuem:
  - a v18 é baixada do endpoint público e conferida pelo SHA-256 fixado, então não há cópia nossa a
    proteger;
  - o custo é tempo de runner, gratuito em repositório público: ~27 min medidos localmente, 30–45 min
    estimados no runner;
  - a reprodutibilidade foi medida: ao reexecutar um ponto, as probabilidades de título e rebaixamento
    saíram idênticas, e o resto diferiu no máximo 5e-13. Com o mesmo código e os mesmos dados, a
    história publicada não muda de um dia para o outro. Ela só muda quando mudam o modelo, um placar
    passado ou o calendário.
- **Validação temporal.** Cada ponto usa só partidas até a sua `reference_date` (`build_snapshot`). Os
  hiperparâmetros de `model_config.json` foram escolhidos com validação em 2013–2018 e teste em
  2019–2025, sem 2026. Já as escolhas de desenho do modelo (por exemplo, `goal_dispersion`) foram feitas
  em outubro de 2026. Por isso cada ponto é uma reconstrução, e não uma previsão da época.
- **Ajuste 1: a reconstrução é identificada nos dados e na interface (bloqueia a publicação).**
  A Decisão 3 já exigia isso para cada snapshot reconstruído. No CI, a história inteira é sempre
  reconstruída com o modelo do dia e muda inteira quando o modelo muda. Quem lê o JSON público e quem lê
  o site precisa saber disso. Contrato (aditivo; o formato de lista não muda):
  - `probability-history.json` e `GET /api/seasons/{s}/probability-history`: cada ponto ganha
    `generated_at` (do snapshot), `model_version` e `reconstructed: bool`. `reconstructed` é `true`
    quando a data do `generated_at`, em `America/Sao_Paulo`, é posterior à `reference_date` do ponto
    seguinte, ou seja, quando o ponto foi calculado depois que já havia resultados mais novos. O último
    ponto é sempre `false`.
  - `seasons.json`: cada temporada ganha `history_mode`: `"reconstructed"` se algum ponto for
    reconstruído, `"recorded"` se nenhum for.
  - Responsáveis:
    - **00**: implementa em `pipeline.probability_history` e `export_static_api` (interfaces do 00),
      com testes, **depois que o 06 fechar a auditoria em curso**, para não mudar o que ele está
      auditando. O `PredictionSnapshot` não muda e o `schema_version` não sobe, porque `generated_at`
      e `model_version` já estão nele;
    - **07**: faz o `check_site_artifact.py` exigir `history_mode` e `reconstructed` em todos os pontos.
  - Interface: o **08** escreve e o **05** implementa um texto curto, perto do gráfico de evolução e em
    "Como calculamos", com este sentido: "a evolução é recalculada a cada atualização com o modelo atual
    (`model_version`) e os dados até cada data; não são as previsões publicadas na época". A data do
    recálculo vem do `generated_at` do snapshot. O 05 só consome o export, e o 06 audita o texto contra
    os dados.
- **Ajuste 2: registro do que foi publicado.** Os snapshots do deploy deixam de ser um registro
  imutável; o ADR-0004 continua valendo para o SQLite local. Para manter a rastreabilidade sem guardar
  placares fora do site, o **07** acrescenta ao resumo da execução (`GITHUB_STEP_SUMMARY`) a
  `reference_date`, o `model_version`, o `data_version` e o SHA-256 de cada JSON do export. Não
  bloqueia. Guardar versões antigas do site não é objetivo: em repositório público, cada artefato
  retido seria mais uma cópia sujeita à cláusula 9.1.
- **Ajuste 3: URL do site no ar na checagem de não regressão (bloqueia ligar `PUBLISH_ENABLED`; não
  bloqueia o C5).** Em `publish-site.yml`, `LIVE_URL` é montada com `github.event.repository.name`. O
  campo vem no evento `workflow_dispatch`, mas nada garante que venha no `schedule`, cujo payload é
  mínimo (**a verificar**). Se vier vazio, a URL fica errada e o script **pula a checagem em silêncio**
  em todas as execuções agendadas. O **07** passa a derivar o nome de `github.repository` (por exemplo,
  `${GITHUB_REPOSITORY#*/}` no shell) e cobre o caso num teste de `test_workflows.py`.
- **Consequências aceitas pelo 00:**
  - a não regressão compara com o `predictions.json` no ar;
  - um modelo novo reescreve a história publicada, o que conta como mudança de produto: o commit que
    muda `MODEL_VERSION` registra em `docs/methodology/validation.md` que a história do site será
    recalculada;
  - o endpoint do Kaggle vira dependência operacional (R17). Se falhar, o workflow falha e o site
    anterior fica no ar. O plano B é um ADR novo, e não a volta automática ao repositório de estado.
- **Nenhuma pendência nova para o dono.** A única mudança para ele é que a pendência 3 se reduz a um
  segredo.
