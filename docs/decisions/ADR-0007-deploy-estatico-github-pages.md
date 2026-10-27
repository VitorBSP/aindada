# ADR-0007 — Deploy estático gratuito no GitHub Pages, com repositório público

- Status: **proposto** (2026-10-26). Arquitetura e preparação aprovadas com condições pelo Agente 00.
  **A publicação pública continua bloqueada** (ADR-0002) até as condições C1–C6 abaixo serem
  cumpridas e os Agentes 00 e 06 registrarem o parecer final.
- Responsáveis: Agente 00 (decisão), Agente 07 (implementação), Agente 06 (gate)
- Origem: proposta do Agente 07 em `docs/architecture/deploy.md` ("Proposta: deploy gratuito")

## Contexto
O projeto precisa de um deploy público gratuito (D-013: sem orçamento). A interface (ADR-0005) já
funciona sem a API: `fetchJson` cai no espelho estático `apps/web/data/api/*.json`, o roteamento é
por hash e os caminhos são relativos. A API só lê snapshots (ADR-0004), então não há consulta
dinâmica que justifique um servidor.

Decisão do dono do produto (chat, 2026-10-26): **repositório público** e **deploy no GitHub
Pages**, com site estático gerado por GitHub Actions agendado e sem API no ar. Ainda não
confirmados: o subdomínio gratuito `<usuario>.github.io/<repo>` (proposto sob D-013) e a
frequência do agendamento.

Bloqueio vigente: os dados de 2024+ vêm do Sofascore via `brasileirao-dataset`
(`research_only_unverified`, ADR-0002). Os de 2003–2023 vêm do mesmo repositório, que não tem
arquivo LICENSE, e a licença do dataset de origem não está registrada no catálogo. Os três escudos
de Bragantino, Corinthians e Vasco são © dos clubes; o `license_status_override` não muda a licença
real. *Resolvido em 2026-10-27 (D-028/D-029): os três foram substituídos por um marcador neutro com
sigla e cores, e `crests_provenance.json` passou a registrá-los como `nao_livre`, `used: false`.*

## Decisão
1. **Arquitetura**: site estático (`apps/web` + export JSON) publicado no GitHub Pages por um
   workflow do GitHub Actions (`actions/deploy-pages`). Nenhuma API pública nesta fase.
2. **Fluxo do workflow** (quando ligado):
   `restaura SQLite → ingest --fetch → validate → simulate → review-rounds → export-web →
   gate → salva SQLite → deploy`. Com `concurrency` (uma publicação por vez) e permissões mínimas.
3. **O que pode ser versionado no repositório público.** Um repositório público redistribui tudo o
   que está nele, inclusive no histórico do git, que não pode ser apagado com segurança depois do
   primeiro push (forks e caches). Por isso a política vale **desde o primeiro commit**:

   | Caminho | Versionar? | Motivo |
   |---|---|---|
   | `src/`, `apps/api/`, `apps/web/` (código, CSS, fontes, marca), `tests/`, `docs/`, `scripts/`, `agents/`, configs | sim | código e documentação próprios; fixtures marcadas `synthetic` |
   | `data/reference/` (`clubs.csv`, `known_exceptions.csv`, `crests_provenance.json`) | sim | cadastro e procedência próprios |
   | `data/gold/model_config.json`, `data/gold/backtest_report.json` | sim | hiperparâmetros e métricas agregadas; conferido em 2026-10-26 que o relatório não tem `match_id` nem clubes |
   | `data/raw/` (inteiro) | **não** | cópia da fonte restrita |
   | `data/silver/`, `data/gold/matches_model.csv`, `data/gold/quality_report.json` | **não** | derivados linha a linha da fonte restrita |
   | `data/snapshots/` | **não** | contém placares e probabilidades derivados; persiste fora do git (item 4) |
   | `apps/web/data/` | **não** | export com placares e probabilidades; gerado só no workflow |
   | `data/editorial/` | **não**, até C1 | textos aprovados citam números derivados da fonte restrita; depois de C1 passa a ser versionado como trilha de auditoria |
   | `apps/web/assets/crests/bragantino.png`, `corinthians.png`, `vasco.svg` | **não** | © dos clubes, sem licença livre |
   | Os outros 17 escudos | sim, condicionado a C3 | PD-textlogo; marcas registradas, só para identificar o clube como dado |

4. **Persistência do SQLite** entre execuções: **asset de uma release fixa `snapshots-db`**, que
   não expira, com o artefato da última execução como cópia secundária e uma cópia local mantida
   pelo dono. O asset é público num repositório público, então só pode ser criado depois de C1. O
   workflow verifica que o número de snapshots e a última `reference_date` nunca diminuem antes de
   substituir o asset.
5. **Métricas**: o workflow não roda o backtest (~4 min; ADR-0006 manda revisar por temporada ou
   quando o modelo muda). `backtest_report.json` versionado alimenta `metrics.json`. O gate falha se
   o `model_version` do relatório for diferente do `model_version` do snapshot.
6. **Revisão por rodada**: `review-rounds` entra no workflow, com semente e número de simulações
   registrados. O gate falha se a data de referência de `rounds.json` for diferente da do snapshot.
7. **Insights**: nenhum job aprova insight (D-026). Depois de um snapshot novo, os insights do
   anterior saem do ar, o que é o comportamento correto (a home volta ao layout sem manchete). O
   workflow pode gerar candidatos do 08A como artefato. A revisão do 08 é manual e é seguida de
   `insights-publish` e de um novo deploy (`workflow_dispatch`).
8. **Gate antes do deploy**: `pytest`; os 6 JSON do export presentes e válidos no esquema;
   `reference_date` não regressiva em relação ao site no ar; datas e `model_version` consistentes
   entre `predictions`, `rounds` e `metrics`; nenhum arquivo de escudo não livre no artefato. Se o
   gate falhar, nada é publicado e o site anterior fica no ar.
9. **Agendamento**: o bloco `schedule` fica comentado até o parecer final. A frequência é decisão
   do dono do produto (sugestão do 07: terças e quintas às 06:00 de Brasília).

## Condições para publicação pública (todas obrigatórias)
- **C1 — Licença dos dados (bloqueia).** Fonte com termos verificados para 2024+ (por exemplo,
  football-data.org com token, termos e atribuição conferidos na data) e ratings, treino e
  simulação recalculados sem dados do Sofascore. Registro da licença de 2003–2023 no catálogo
  (`docs/data-sources/catalog.md`) e no manifesto. Conferência com a CBF dos jogos publicados.
  Responsável: 01, parecer 00/06.
- **C2 — Textos de licença e fonte.** O rodapé ("Dados para pesquisa local…") e o parágrafo de
  fonte em `app.js` ("Uso restrito a pesquisa local…") são reescritos para refletir a fonte real e
  a atribuição exigida. Responsáveis: 08 (texto) e 05 (implementação).
- **C3 — Escudos.** Os três não livres saem do repositório e do site (marcador neutro com a sigla)
  até haver autorização dos clubes. Os 17 PD-textlogo só identificam o clube, com atribuição na
  página de metodologia. Responsáveis: 01 (procedência), 05 (marcador), 06 (conferência).
- **C4 — Repositório limpo.** `.gitignore` aplicado antes do primeiro commit e `git ls-files`
  auditado pelo 06 contra a tabela do item 3, com o repositório no GitHub ainda **privado**. Só
  depois disso ele é tornado público. Responsáveis: 07 e 06.
- **C5 — Workflow verificado.** Uma execução completa com `workflow_dispatch` e deploy desligado
  produz o artefato, passa no gate e mede o tempo de `review-rounds`. Responsáveis: 07 e 06.
- **C6 — Marca.** Busca gratuita do nome "AInda dá?" no INPI registrada (D-013 permite verificações
  gratuitas) e kit M4 do roadmap aprovado, ou aceite explícito do dono do produto de publicar sem
  isso. Responsável: 08, decisão do dono.

## Alternativas descartadas
- **Cloudflare Pages (A2)**: aceita repositório privado, mas exige uma segunda conta e um segredo.
  O dono escolheu repositório público, então o GitHub Pages tem menos peças.
- **Netlify (A3)**: cotas do plano gratuito mais apertadas (a verificar).
- **API em free tier (Render, Fly.io, Cloud Run, Koyeb, HF Spaces)**: hibernação, cold start,
  disco efêmero (o SQLite teria de ir na imagem) e, em alguns casos, cartão obrigatório, sem ganho
  para a interface. Volta a ser avaliada se houver consulta dinâmica.
- **Persistir o SQLite por commit no repositório**: 11 MB por atualização incham o histórico para
  sempre. Descartado.
- **`actions/cache`**: o cache é removido após dias sem uso (a verificar). Não serve como fonte de
  verdade.
- **Só artefato do Actions**: expira em até 90 dias (a verificar). Fica apenas como cópia secundária.
- **Publicar só "temporadas com licença verificada"**: hoje nenhuma temporada tem licença
  verificada, e as previsões de 2026 dependem dos resultados de 2024–2026. A opção só se torna real
  com C1. Uma página só com marca e metodologia, sem dados derivados, é possível, mas não é
  recomendada antes de C2 e C6.

## Consequências
- Custo zero. Código e documentação ficam públicos; os dados derivados só aparecem quando C1 for
  cumprida.
- O CI público funciona sem os dados: em 2026-10-26, `pytest` passou (158 testes) numa cópia com
  apenas `data/reference/`, `model_config.json`, `backtest_report.json` e
  `docs/storytelling/contracts/`.
- Em repositório público, o GitHub desativa workflows agendados depois de 60 dias sem atividade (a
  verificar). Atualizar o asset de release provavelmente não conta como atividade. Commits
  legítimos (lotes editoriais, TOML da temporada) contam. O 07 monitora isso.
- Os limites do GitHub Pages (~1 GB por site, ~100 GB/mês de banda, cache de ~10 min) estão "a
  verificar" na data da implantação. O export atual tem 1,58 MB.
- Rollback: reexecutar o workflow num commit anterior ou republicar o artefato do site de uma
  execução anterior. Os snapshots continuam imutáveis (ADR-0004).
- Recomendado, não obrigatório: modo estático explícito em `fetchJson` (contrato do 04, arquivo do
  05) para evitar as 5 chamadas `/api/*` com 404.
- Para virar "aceito", este ADR precisa de C1–C6 cumpridas e dos pareceres do 00 e do 06
  registrados em `docs/project/status.md`.
