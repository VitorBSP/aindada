# Deploy e operação (Agente 07)

## Local (sem Docker)

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[api,dev]"
python -m brasileirao.cli simulate --season 2026
uvicorn apps.api.main:app --port 8000             # http://localhost:8000
```

## Docker

```bash
docker compose up --build          # API + interface em http://localhost:8000
docker compose run --rm pipeline   # atualiza dados e gera novo snapshot
```

## Operação

- Agendamento: `publish-site.yml` (seção seguinte), todo dia às 09:00 UTC, só com a publicação ligada.
- Rollback local: os snapshots são imutáveis. Para voltar, basta apagar o snapshot mais recente ou
  servir um banco anterior (`BRASILEIRAO_SNAPSHOT_DB`).
- Logs: JSON em stderr (`brasileirao.logging_utils`).
- Não há serviços pagos.
- **Publicação pública: bloqueada** até o parecer final dos Agentes 00 e 06 (C1–C6 do ADR-0007).

## Publicação no GitHub Pages (ADR-0008, passo 13) — runbook

Estado em 2026-10-28: workflow pronto na branch `deploy/publish-site`, **não mergeado, nunca
executado no GitHub, nada publicado**. Repositório `VitorBSP/aindada`, privado.

### Como funciona

`.github/workflows/publish-site.yml` reconstrói tudo do zero a cada execução, num runner efêmero.
**Não há estado entre execuções**: nem repositório privado de estado, nem `STATE_REPO_TOKEN`, nem
SQLite em artefato ou cache (adendo à Decisão 3 do ADR-0008, a confirmar pelo 00).

```text
checkout -> pip install -> pytest (sem dados) -> baixa Adão Duque v18 do Kaggle e confere SHA-256
  -> ingest --fetch --season (FOOTBALL_DATA_ORG_TOKEN) -> validate
  -> simulate (1 snapshot por rodada, 10 mil; atual com 100 mil; semente 2026)
  -> review-rounds (20 mil, semente 2026) -> export-web -> _site/ = apps/web + export
  -> publication-gate G1–G5 -> check_site_artifact.py -> upload-pages-artifact -> deploy-pages
```

- Gatilhos: `schedule` diário às 09:00 UTC (06:00 em Brasília, depois dos jogos da noite) e
  `workflow_dispatch` (entrada opcional `season`). Só na `main`. Nunca em `pull_request` nem
  `pull_request_target`.
- **Interruptor `PUBLISH_ENABLED`** (variável do repositório):
  - ausente ou diferente de `true`: o agendamento não roda; o `workflow_dispatch` é um **ensaio**
    (reconstrói, passa no gate, não publica). Com o repositório privado, o ensaio envia o artefato do
    site (retenção de 1 dia) para conferência; com o repositório público, não envia nada, porque
    artefato de repositório público pode ser baixado por qualquer pessoa;
  - `true`: o agendamento roda, o artefato sobe e o job `deploy` publica.
- Permissões: `contents: read` no workflow; `pages: write` e `id-token: write` só no job `deploy`.
  `persist-credentials: false` no checkout. `concurrency: publish-site` sem cancelar execução em
  andamento.
- O token só existe no passo de ingestão, como variável de ambiente; nunca é impresso (o GitHub
  mascara o valor e o `FootballDataOrgSource` só o usa no header).
- Adão Duque v18 (GPL-2): `infrastructure/scripts/fetch_adaoduque_v18.py` baixa o zip público do
  Kaggle (sem login), extrai só os 2 arquivos fixados em `data/reference/source_pins.json` e falha se
  o SHA-256 divergir. A ingestão confere os hashes de novo. Os arquivos ficam só no runner.
- Artefato (G5): só `apps/web` versionado mais o export (`data/api/*.json`). O gate e
  `infrastructure/scripts/check_site_artifact.py` reprovam SQLite, CSV, `raw/`, `silver/`, `gold/`,
  escudos não livres, `model_version`/`data_version` divergentes entre `predictions`, `rounds` e
  `metrics`, `rounds.data_until` diferente do snapshot, histórico com data posterior ao snapshot e
  `reference_date` menor que a do site no ar. Se qualquer checagem falhar, nada é publicado e o site
  anterior continua no ar.
- Insights: nenhum job aprova insight (D-026). O export publicado não tem `insights.json`, e a home
  aparece sem manchete. Publicar insights exige um fluxo editorial próprio (pendência do 08/04).

### Tempos medidos (2026-10-27, código do `main` `e44ea6a`, máquina local, 8 núcleos)

Reconstrução do zero num diretório de dados copiado (`BRASILEIRAO_ROOT`), sem SQLite prévio, 2026 com
319 jogos encerrados (32 rodadas):

| Passo | Configuração | Tempo |
|---|---|---|
| download da v18 do Kaggle + SHA-256 | zip de 0,7 MB | ~2 s |
| `ingest` (sem `--fetch`; com `--fetch` soma ~20 s: 3 chamadas com ≥ 6 s entre elas) | 9.545 partidas | 3–4 s |
| `validate` | 24 temporadas | 2 s |
| `simulate --history-from-round 1` | 31 pontos × 10 mil + atual × 100 mil | 379 s (~11 s por ponto; ~29 s o atual) |
| `review-rounds` | 33 visões × 20 mil | 1.231 s |
| `export-web`, `publication-gate`, `check_site_artifact.py` | 0 achados nos dois gates | ~10 s |
| **Total de processamento** | | **~27 min** |

- Estimativa no runner `ubuntu-latest` (mais `pip install` e `pytest`, ~3 min): **30 a 45 min**
  por execução, a confirmar na primeira execução (C5). O `timeout-minutes` do job é 180.
- A revisão rodada a rodada é ~75% do tempo. Com 100 mil simulações na revisão (5×) seriam ~1 h 45
  só nesse passo localmente, e com 100 mil em cada ponto do histórico, mais ~30 min: cabe no limite de
  6 h do job, mas não é recomendado para execução diária. O 07 manteve os valores do `config.py`
  (`n_simulations` 100 mil no snapshot atual, `round_review_simulations` 20 mil) e 10 mil por ponto
  do histórico (o padrão antigo do CLI era 2 mil).
- Custo: zero em repositório público. Execução diária ≈ 15–23 h de runner por mês.
- Reprodutibilidade: reexecutar o ponto de 2026-02-12 deu probabilidades de título e rebaixamento
  idênticas; os demais números diferem em até 5e-13 (ruído de ponto flutuante do ajuste do modelo).
- O artefato tem 40 arquivos e 2,4 MB (export 1,7 MB).

### O que o dono do produto faz (uma vez)

Ver a lista no handoff do 07 em `docs/project/status.md` (2026-10-28). Resumo: cadastrar o secret
`FOOTBALL_DATA_ORG_TOKEN`; depois do merge, rodar o ensaio manual; depois do parecer final 00/06,
tornar o repositório público, escolher "GitHub Actions" como fonte do Pages e criar a variável
`PUBLISH_ENABLED = true`.

### Rollback

- **Tirar o site do ar já** (por exemplo, cláusula 9.1 do football-data.org): Settings → Pages →
  "Unpublish site". Depois, apagar a variável `PUBLISH_ENABLED` (ou mudar para `false`) para o
  agendamento parar.
- **Parar as atualizações e manter o site como está**: mudar `PUBLISH_ENABLED` para `false`.
- **Voltar a uma versão anterior do código ou do modelo**: reverter o commit na `main` e rodar o
  workflow (Actions → publish-site → Run workflow). Como a história é reconstruída, o site inteiro
  volta a ser o que aquele código gera com os dados de hoje. A checagem de não regressão impede só
  que a `reference_date` publicada diminua.
- **Execução que falhou**: nada foi publicado; o site anterior fica no ar. Os logs mostram o passo e a
  regra (só contagens, nomes de fonte e até 5 `match_id`, sem placar).

### Riscos operacionais

- Em repositório público, o GitHub desativa workflows agendados após 60 dias sem atividade no
  repositório (a verificar). Execuções agendadas não contam como atividade; um commit conta. Se o
  agendamento parar, o GitHub avisa por e-mail e basta reativar em Actions.
- O endpoint de download do Kaggle não é documentado como API estável para anônimos (funcionou sem
  login em 2026-10-27). Se mudar ou exigir login, o passo falha e o site anterior fica no ar.
- Execuções agendadas do GitHub podem atrasar ou ser puladas em horários de pico.
- Limites do Pages (~1 GB por site, ~100 GB/mês de banda, cache de ~10 min) e do Actions (6 h por
  job) estão "a verificar" na data da implantação.

## Proposta: deploy gratuito (histórico, 2026-10-26)

> Registro da proposta original. A persistência do SQLite (release `snapshots-db`, depois
> repositório privado de estado) foi substituída pela reconstrução a cada execução (seção anterior).

- **Status: arquitetura aprovada com condições pelo Agente 00 e pelo Agente 06; decisão em
  `docs/decisions/ADR-0007-deploy-estatico-github-pages.md` (proposto).** O dono do produto escolheu
  repositório público e GitHub Pages (2026-10-26). A publicação pública continua bloqueada até
  C1–C6 do ADR-0007. Nada foi publicado e nenhuma conta foi criada.
- **2026-10-26**: `.gitignore` reescrito pela tabela do ADR-0007 (item 3) e repositório git
  **local** criado com o primeiro commit (seção "Repositório git local"). Sem remote e sem push.
- Responsável: Agente 07 (2026-10-26). Restrição de orçamento: D-013 (sem compras nesta fase).
- Os limites de provedores abaixo vêm do conhecimento do Agente 07, **sem consulta às páginas
  oficiais nesta sessão**. Tudo marcado "(a verificar)" precisa ser conferido na data da implantação.

### Diagnóstico

- A interface funciona sem a API. `fetchJson` em `apps/web/assets/app.js` tenta `/api/...` e, se a
  resposta não for JSON com status 2xx, usa `data/api/<rota>.json`. As 5 rotas que a interface
  carrega (`predictions`, `probability-history`, `models/metrics`, `rounds`, `insights`) existem em
  `apps/web/data/api/`. O roteamento é por hash (`#/...`), então o servidor não precisa reescrever
  URLs. Os caminhos de assets são relativos, então o site funciona também em subcaminho
  (`usuario.github.io/repo/`).
- Custo do modo estático: 5 requisições `/api/*` que dão 404 (ou HTML de fallback) antes do JSON
  estático. Nada quebra, mas o console fica com erros e a primeira pintura atrasa.
- Tamanho medido de `apps/web`: 42 arquivos, 2,34 MB. Export de dados: 1,58 MB. Desse total,
  `rounds.json` tem 1,18 MB (169 KB com gzip -9), `predictions.json` 293 KB (23 KB gzip) e
  `probability-history.json` 90 KB (10 KB gzip). `rounds.json` cresce a cada rodada.
- Lacunas no pipeline para publicar só o estático:
  1. `update-predictions.yml` roda `ingest → validate → simulate`, mas não roda `review-rounds`.
     Assim, `rounds.json` ficaria parado na última execução local.
  2. `insights.json` só é escrito por `insights-publish` (fora de `export_static_api`). Isso está
     correto, porque insight precisa de aprovação do 08 (D-026) e um job agendado não pode aprovar.
     Depois de um snapshot novo, os insights do snapshot anterior deixam de aparecer até uma nova
     revisão.
  3. `data/snapshots/snapshots.sqlite` (11 MB) guarda estado: o histórico de probabilidades e a
     revisão por rodada dependem dele. Um runner do Actions começa vazio.
  4. `metrics.json` depende de `data/gold/backtest_report.json`, que o workflow não gera (o backtest
     leva ~4 min).
- (Resolvido em 2026-10-26.) O `.gitignore` antigo só excluía `data/raw/_sources/` e os JSON
  brutos; `data/silver/`, `data/gold/matches_model.csv`, o SQLite e o export seriam versionados.

### Opções avaliadas

| Opção | Custo | Prós | Contras |
|---|---|---|---|
| **A1. GitHub Pages + Actions** | zero (repo público) | um provedor só; deploy pelo próprio workflow (`actions/deploy-pages`); HTTPS em `*.github.io` | Pages em repo privado exige plano pago (a verificar); repo público expõe o código e tudo o que estiver versionado; limites "soft" de ~1 GB por site e ~100 GB/mês de banda (a verificar); cache fixo de ~10 min |
| **A2. Cloudflare Pages + Actions** | zero | aceita repo privado; plano free sem limite declarado de banda (a verificar); upload direto do artefato via `wrangler pages deploy`; ~25 MiB por arquivo e ~20 mil arquivos (a verificar) | segunda conta e um segredo (`CLOUDFLARE_API_TOKEN`) no GitHub |
| A3. Netlify | zero até a cota | deploy simples | plano free passou a usar créditos em 2025 (a verificar); cotas de banda e build mais apertadas |
| B1. Render (web service free) | zero | roda o Dockerfile atual | hiberna após ~15 min sem tráfego, com cold start de dezenas de segundos; disco efêmero, então o SQLite some a cada deploy ou reinício (a verificar) |
| B2. Fly.io | sem plano gratuito para contas novas (a verificar) | volumes persistentes | exige cartão; tem custo |
| B3. Google Cloud Run | cota gratuita mensal de requisições e CPU (a verificar) | escala a zero | exige conta de faturamento com cartão; sistema de arquivos efêmero; o SQLite teria de ir dentro da imagem |
| B4. Koyeb / HF Spaces | free com restrições (a verificar) | Docker | hibernação; Spaces é voltado a demos de ML; disco efêmero |

Por que descartar a API (B) agora: a API só lê snapshots (`apps/api/main.py` não simula durante a
requisição), e tudo o que a interface usa já existe no export estático. Uma API em free tier traria
cold start, hibernação, SQLite efêmero (o banco teria de ir na imagem a cada atualização) e, em
vários provedores, cartão de crédito, sem ganho para o usuário. Ela volta a fazer sentido só se
houver consulta dinâmica (data de referência arbitrária, terceiros consumindo a API).

### Recomendação

**Site estático (A) gerado por GitHub Actions agendado.** Escolha do provedor:

- **A1 (GitHub Pages)** se o dono do produto aceitar repositório público. Tem menos peças e não
  exige conta extra.
- **A2 (Cloudflare Pages)** se o repositório tiver de ser privado. Os minutos cabem na cota do
  plano Free do GitHub (estimativa abaixo).

Arquitetura:

```text
cron (Actions) -> restaura snapshots.sqlite -> ingest --fetch -> validate -> simulate
               -> review-rounds -> export-web -> gate (testes + checagem do export)
               -> salva snapshots.sqlite novo -> upload de apps/web -> Pages
```

Mudanças necessárias (com os ajustes do 00 no ADR-0007 e do 06 no parecer de 2026-10-26):

1. **07 (feito em 2026-10-26)**: `.gitignore` conforme a tabela do ADR-0007. Fora do git:
   `data/raw/` inteiro (inclusive manifestos), `data/silver/`, `data/gold/*` exceto
   `model_config.json` e `backtest_report.json` (logo, também `matches_model.csv` e
   `quality_report.json`), `data/snapshots/` e qualquer `*.sqlite`, `apps/web/data/` (export com
   placares e probabilidades), `data/editorial/` (até C1; ajuste do 00, que reverteu a proposta
   original do 07) e os 3 escudos não livres (`bragantino.png`, `corinthians.png`, `vasco.svg`).
   O repositório no GitHub, quando existir, nasce **privado** e só fica público depois da
   auditoria de `git ls-files` pelo 06 (C4).
2. **07**: novo workflow `publish-site.yml` (ou evolução de `update-predictions.yml`). Ele restaura
   o SQLite anterior (asset de uma release `snapshots-db`, que não expira, com o artefato da última
   execução como cópia secundária; a release é pública num repositório público e **só pode ser
   criada depois de C1**; antes de substituí-la, conferir que o número de snapshots e a última
   `reference_date` não diminuem); roda `ingest --fetch`, `validate`, `simulate`,
   `review-rounds` e `export-web`; publica o SQLite novo; empacota `apps/web/` e faz o deploy.
   Usa `concurrency` para impedir duas publicações simultâneas e `permissions` mínimas
   (`pages: write`, `id-token: write`; `contents: write` só se usar release).
3. **07**: gate antes do deploy com `pytest`; presença e esquema dos 6 JSON do export;
   `reference_date` não regressiva em relação ao site no ar; datas e `model_version` consistentes
   entre `predictions`, `rounds`, `metrics` e insights; nenhum escudo não livre no artefato. O gate
   incorpora a lista B4 do 06: invariantes do export (somas de probabilidades, 20 clubes, 380 jogos),
   placares contra o bruto, proveniência e `is_synthetic`, lista permitida de `license_status`,
   semente e versões em `probability-history` e smoke test em subcaminho. Se falhar, nada é
   publicado e o site anterior fica no ar.
4. **07**: rollback reexecutando o workflow num commit anterior ou republicando o artefato do site de
   uma execução anterior. Os snapshots continuam imutáveis no SQLite.
5. **04/05 (opcional, recomendado)**: modo estático explícito, por exemplo
   `<meta name="data-source" content="static">` lido por `fetchJson`, para pular as 5 chamadas
   `/api/*`. O arquivo é do 05; o contrato é do 04.
6. **08**: o rodapé diz "Dados para pesquisa local, com licença em verificação". O texto precisa de
   revisão antes de qualquer publicação.
7. **08/04**: em produção, a revisão editorial dos insights continua manual (CLI local ou
   `workflow_dispatch` com entradas), seguida de `insights-publish` e de um novo deploy.

Minutos do GitHub Actions (estimativa; medir na primeira execução): instalação ~1–2 min, clone da
fonte (~85 MB) ~1 min, pipeline ~1 min de CPU (seção Operação) e `review-rounds` com 10 mil
simulações por rodada, que não foi medido. Com ~10 min por execução e 2 execuções por semana, são
cerca de 90 min/mês, mais o CI. Em repo público, os runners padrão são gratuitos e sem cota. Em repo
privado no plano Free, a cota é de 2.000 min/mês (a verificar). Atenção: em repo público, o GitHub
desativa workflows agendados após 60 dias sem atividade no repositório (a verificar). Publicar o
SQLite como asset de release provavelmente não conta como atividade; um push conta.

Domínio: D-013 proíbe compras nesta fase. A proposta usa subdomínio gratuito
(`<usuario>.github.io/<repo>` ou `<projeto>.pages.dev`). `docs/brand/BRAND_DECISIONS.md` registra
`aindada.com.br` e `aindada.com` com terceiros. Nenhum domínio é declarado disponível aqui. Um
domínio próprio pode ser apontado depois sem mudar a arquitetura.

### Bloqueios (antes de qualquer publicação)

1. **Licença dos dados 2024+** (ADR-0002, `docs/data-sources/catalog.md`): a fonte é
   `research_only_unverified` e vem do Sofascore. O site publica dados derivados (placares, tabela e
   probabilidades). É preciso uma fonte licenciada (por exemplo, football-data.org com token, cujos
   termos também precisam ser verificados) ou um parecer do 00.
2. **Escudos** (resolvido em 2026-10-27, D-028/D-029): Bragantino, Corinthians e Vasco aparecem com
   um marcador neutro (sigla e cores); os arquivos ficam só no disco local, ignorados pelo git e pelo
   `.dockerignore`. Os outros 17 são PD-textlogo, marcas registradas usadas só para identificar os
   clubes, com atribuição no rodapé e em "Como calculamos".
3. **Gate 00/06** (AGENTS.md e contrato do 07): nenhum deploy público sem as duas revisões.
4. **Docker e compose** ainda não foram executados (status.md). Isso não afeta a opção estática, mas
   o critério de aceite do 07 continua aberto.
5. O repositório git é **só local** (primeiro commit em 2026-10-26, sem remote). Falta criar o
   repositório **privado** no GitHub, a auditoria do 06 (C4) e o workflow verificado (C5).

### Repositório git local (2026-10-26)

- `git init -b main` e primeiro commit local, a pedido do dono do produto. Sem remote, sem push.
- Conferência antes do commit: `git status --porcelain --ignored` e `git check-ignore -v` para cada
  caminho excluído; busca de segredos e de arquivos acima de 1 MB no que seria versionado; `pytest`
  num clone limpo do repositório (só arquivos versionados). Resultados no handoff do 07 em
  `docs/project/status.md`.
- Os 3 escudos não livres continuam no disco local como evidência (não foram apagados), mas o
  `manifest.json` usa `badge` para eles desde 2026-10-27 (D-029); nenhum arquivo do site os referencia.
