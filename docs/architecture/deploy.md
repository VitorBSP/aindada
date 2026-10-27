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

- Agendamento sugerido: após cada rodada (por exemplo, terças e quintas às 06:00), rodando o serviço
  `pipeline`. O workflow agendado está desativado até a revisão de licença dos dados.
- Rollback: os snapshots são imutáveis. Para voltar, basta apagar o snapshot mais recente ou servir
  um banco anterior (`BRASILEIRAO_SNAPSHOT_DB`).
- Logs: JSON em stderr (`brasileirao.logging_utils`).
- Custo: o pipeline completo roda em ~1 min de CPU e o backtest em ~4 min. Não há serviços pagos.
- **Publicação pública: bloqueada** até a licença dos dados de 2024+ e a revisão dos Agentes 00 e 06.

## Proposta: deploy gratuito

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
2. **Escudos**: Bragantino, Corinthians e Vasco são © dos clubes; o `license_status_override` do
   dono do produto não muda a licença real. Os outros 17 são PD-textlogo, mas são marcas registradas.
   Cabe a 00/06 decidir entre autorização, uso nominativo avaliado ou marcador neutro no build público.
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
- Os 3 escudos não livres continuam no disco local (não foram apagados) e em
  `apps/web/assets/crests/manifest.json`, que é versionado. Num checkout limpo, `rounds.js` montaria
  `<img>` para arquivos inexistentes (404). O marcador com a sigla é do 05 (C3).
