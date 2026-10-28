# Status do projeto — iteração 1 (2026-10-26)

Responsável pelo registro: Agente 00. Todo o trabalho desta iteração foi executado em uma única
sessão, seguindo os contratos dos agentes. A única execução como subagente separado foi a revisão
independente do Agente 06.

## Implementado (com evidência)

| Agente | Entrega | Evidência |
|---|---|---|
| 00 | Estrutura, AGENTS.md, 8 contratos, subagentes, 6 ADRs, roadmap, riscos, CLI e pipeline | `python -m brasileirao.cli --help`; `docs/` |
| 01 | Contratos Pydantic, registro de 46 clubes, ingestão raw/silver/gold com manifesto (SHA-256, commit, licença), log de mudanças, validação com exceções conhecidas, adaptador football-data.org | 9.545 jogos 2003–2026; `data/gold/quality_report.json` sem erros; testes `test_data_pipeline.py` |
| 03 | Regulamento 2026 versionado em TOML, desempate do Art. 15, vagas do Art. 6º §§1–5, Art. 7º e 8º, 32 cenários externos | 26 testes em `test_qualification.py`, `test_standings.py` e `test_scenarios.py` |
| 02 | Elo, ataque/defesa, forma, Poisson (A), Dixon-Coles (B), Monte Carlo vetorizado com ratings dinâmicos e fixos | 10 mil simulações em ~3 s; `test_simulation.py`, `test_ratings.py` |
| 06 | Backtesting temporal (partidas e temporadas), ajuste de hiperparâmetros, calibração, seleção de modelo, revisão independente | `data/gold/backtest_report.json`; `docs/methodology/validation.md` |
| 04 | Esquema do snapshot, SQLite, API FastAPI com 8 rotas, espelho estático | `test_pipeline_and_storage.py`; `test_api.py` (pulado aqui, sem FastAPI) |
| 05 | Interface: início, classificação com seletor de cenários, clubes, partidas, metodologia | capturas em 1280 e 375 px, sem erros de JS nem rolagem horizontal |
| 07 | Dockerfile, compose (API + pipeline), CI (ruff, mypy, pytest), workflow de atualização desativado, `.env.example` | arquivos em `.github/` e na raiz; **Docker não executado neste ambiente** |

Validação final: `ruff check`, `ruff format --check` e `mypy --strict` sem erros em 33 arquivos.
`pytest`: 88 passaram e 1 módulo foi pulado (API).

## Resultado atual (snapshot de 2026-10-18, 308/380 jogos, 10.000 simulações, semente 2026)

Probabilidades por clube (título e rebaixamento): retiradas deste arquivo pela decisão B1
(2026-10-27); ficam no registro local `data/editorial/status_numeros_reais.md`, não versionado.
Libertadores em faixa, por depender de três torneios em aberto.
Dados da fonte até 18/10. Os 12 jogos com data passada sem placar foram simulados.

## Parecer do Agente 06: aprovado com ressalvas

| Achado | Severidade | Situação |
|---|---|---|
| Backtest de temporada reaproveitava estado entre checkpoints e, com jogos adiados, via partidas futuras | Alta | **Corrigido** (estado reconstruído por checkpoint); relatório regenerado; conclusão mantida |
| Vice da Copa fora da Série A gerava vaga extra | Média | **Corrigido**, com 2 testes novos |
| Vagas liberadas ordenadas por fase vs. leitura literal "ainda não classificado" | Baixa–média (interpretação) | Documentado, fixado em teste, consulta à CBF pendente |
| Escolha dinâmico/fixo feita nas temporadas de teste | Baixa | **Corrigido**: agora escolhida na validação |
| Cartões não simulados no desempate | Baixa | Documentado. Em 2026 a cobertura de cartões é parcial (185/308), então o critério de cartões é substituído por sorteio, com aviso |
| Empate total na tabela observada exibido em ordem alfabética | Baixa | Pendente (só afeta exibição) |

## Pendências e próximos passos (por responsável)

1. **01**: obter token da football-data.org e validar o adaptador com a API real. Conferir com a
   CBF os 12 jogos sem placar e a duplicidade de 2009. Resolver a licença de 2024+ (bloqueia a
   publicação).
2. **03**: consultar a DCO/CBF sobre o § 5º e a ordem das vagas liberadas. Atualizar o TOML quando
   saírem os campeões (Sul-Americana em 21/11, Libertadores em 28/11, Copa do Brasil em 06/12).
3. **02**: ~~modelar empates e propagar incerteza~~ (avaliados na iteração 3; nenhum dos dois
   adotado pela validação). Falta: escolher `strength_sd` por origem móvel e criar o Modelo C
   (multiclasse calibrado).
4. **06**: benchmark com odds de fechamento (Football-Data.co.uk) e monitoramento de drift por rodada.
5. **04/07**: ~~rodar `pytest` com FastAPI instalado~~ (feito na iteração 2). Falta
   `docker compose up`. Migrar para PostgreSQL quando houver deploy.
6. **05**: migrar para Next.js/TypeScript (ADR-0005) e adicionar teste de interface automatizado.

## Limitações do ambiente desta iteração

Os registros PyPI e npm e os sites externos estavam bloqueados no shell. Só o GitHub estava
acessível. Por isso não foram executados aqui: FastAPI, Docker, Next.js e as fontes CBF,
football-data.org e Football-Data.co.uk.

## Iteração 2 (2026-10-26) — ambiente local com dependências completas

Responsável pelo registro: Agente 00. Handoff para 04, 06 e 07.

- **O que mudou**: Python 3.12.10 instalado na máquina local; `.venv` com
  `pip install -e ".[api,sources,dev]"` (FastAPI 0.162, pandas 3.1, pandas-stubs 3.0.5, mypy 2.4).
  `scripts/install_claude_agents.py` instalou os 8 subagentes em `.claude/agents/` e os workflows
  em `.github/workflows/`. Novo módulo `src/brasileirao/frame_values.py` (`as_int`, `as_timestamp`)
  usado em `pipeline.py`, `ratings/history.py`, `data_pipeline/validation.py`,
  `validation/backtest.py` e `validation/report.py`: com o pandas-stubs atual, o `mypy --strict`
  acusava 14 erros de tipagem em valores lidos via `itertuples`/`groupby`. Sem mudança de
  comportamento.
- **Evidência**: `pytest` → 95 passaram, 0 pulados (inclui `test_api.py`); `ruff check`,
  `ruff format --check` e `mypy` sem erros em 34 arquivos. `uvicorn apps.api.main:app` respondeu
  200 nas 8 rotas (`/api/health`, `/api/seasons` → 27 snapshots até 2026-10-18, standings, matches,
  predictions, teams/flamengo, probability-history, models/metrics) e em `/` (interface, sem erros
  de console).
- **Premissas e limitações**: a porta 8000 estava ocupada por outro processo local; a API foi
  verificada na porta 8001. Docker não foi executado. Aviso de depreciação do Starlette sobre
  `httpx` no `TestClient` (não afeta os testes).
- **Próximo responsável**: 07 (`docker compose up`), 06 (pendências do item 4), 02 (item 3).

## Adição — Agente 08 Brand Manager & Identidade Visual (2026-10-26)

O projeto passa a ter nove agentes (00–08).

- **O que mudou**: `agents/08-brand-manager.md`; subagente `brand-manager` em `.claude/agents/` e
  `infrastructure/claude-agents/`; `docs/brand/` (CONTEXT, EXPLORATION, DECISIONS, GUIDELINES);
  `AGENTS.md`, `README.md`, `docs/roadmap.md` (trilha de marca M1–M5), contratos 00, 02, 05 e 06 e
  `docs/architecture/frontend.md` atualizados com as responsabilidades e handoffs do 08.
- **Evidência**: arquivos acima. Contrastes WCAG das 3 paletas preliminares calculados pela fórmula
  de luminância relativa (valores em `BRAND_EXPLORATION.md`). Nenhum código alterado.
- **Premissas e limitações**: público-alvo é hipótese. Nenhum nome teve domínio, INPI ou perfis
  sociais verificados. Nenhum elemento de marca está aprovado; "Brasileirão em Probabilidades"
  segue como nome de trabalho.
- **Próximo responsável**: **00 / dono do produto** responde às questões Q1–Q9 e escolhe 1–2
  direções em `docs/brand/BRAND_DECISIONS.md`. Depois, **08** aprofunda nomes e faz a verificação
  formal da lista curta. O **05** não muda a interface até haver decisão.

## Agente 08 — aprofundamento das direções A e B (2026-10-26)

- **O que mudou**: decisão D-003 registrada; `BRAND_EXPLORATION.md` (iteração 2: variações de nome,
  verificação de domínios, símbolos, paletas, voz, comparação, descartes); 7 esboços SVG em
  `docs/brand/exploration/svg/`; quadro `docs/brand/exploration/board.html`; `.claude/launch.json`
  com o servidor `brand-board`; contexto, decisões (Q10, Q11) e roadmap atualizados.
- **Evidência**: consultas ao Registro.br e ao RDAP Verisign registradas com resultado; quadro
  aberto no navegador e símbolos inspecionados de 16 a 128 px. Dois problemas encontrados: A3
  confundido com ícone de menu (registrado) e B1 lido como "2" em 16 px (corrigido e reverificado).
- **Premissas e limitações**: INPI e perfis sociais não verificados; wordmarks usam fontes do
  sistema; contrastes calculados, não medidos em tela.
- **Próximo responsável**: dono do produto (Q1–Q11); depois, o Agente 08 na Etapa 3.

## Agente 08 — nome decidido e 8 estilos de símbolo (2026-10-26)

- **O que mudou**: decisões D-004 (nome "Ainda dá?"), D-005 (paleta principal Papel e tinta com
  vermelho-sinal) e D-006 (símbolo em exploração) registradas; Q4, Q8, Q10 e Q11 resolvidas ou sem
  objeto; Q12 (domínio) aberta. 8 SVGs em `docs/brand/exploration/svg/simbolos/` e quadro
  `docs/brand/exploration/simbolos.html`; `BRAND_EXPLORATION.md` (iteração 3), contexto, roadmap e
  `docs/architecture/frontend.md` atualizados.
- **Evidência**: quadro aberto no navegador; símbolos conferidos em 96, 48, 32 e 16 px e como ícone
  de app na paleta principal; console sem erros.
- **Premissas e limitações**: versões reversa e mono geradas, mas não inspecionadas visualmente;
  texto do selo e wordmark em fontes do sistema; INPI não verificado; domínios `aindada.com.br` e
  `aindada.com` com terceiros.
- **Próximo responsável**: dono do produto escolhe 2–3 estilos; o Agente 05 só troca o nome na
  interface depois do kit da Etapa 4.
- **Atualização**: questões Q1–Q12 respondidas no app e registradas como D-007 a D-014 (torcedor
  engajado; expansão além da Série A; odds só como referência; provocação leve; gratuito; Instagram,
  X e WhatsApp; sem orçamento; domínio preferido `aindada.app.br`, não registrado). Aberta: Q13
  (estilos de símbolo a refinar).
- **Rodada 2 de símbolos (D-015)**: 8 SVGs em `docs/brand/exploration/svg/simbolos-r2/` e quadro
  `simbolos-r2.html` com teste de avatar redondo. Conferidos visualmente: visão geral, 32/16 px e
  avatares; reversa e mono não. Aberta: Q14 (base do símbolo final).

## Iteração 3 (2026-10-26): empates e incerteza de parâmetros (Agente 02, gate do 06)

- **O que mudou**: `GoalsModel` ganhou `draw_inflation` (diagonal × (1 + δ), δ por MV),
  covariância dos coeficientes (`home_covariance`/`away_covariance`), `sample_parameters` e
  `expected_goals_by_draw`. Novo `SimulationUncertainty` em `config.py`; `SeasonSimulator.run`
  aceita `uncertainty` (coeficientes sorteados e força latente por clube, com geradores próprios
  derivados da semente). O backtest foi refatorado em `prepare_checkpoints` +
  `score_simulation_variants`. O relatório seleciona inflação e incerteza na validação e grava
  `draw_inflation` e `simulation_uncertainty` em `model_config.json`. O pipeline lê os dois campos.
  `ModelInfo` (snapshot) ganhou `draw_inflation` e `simulation_uncertainty`, opcionais e com
  padrão, portanto compatíveis com snapshots antigos (handoff para o 04).
- **Evidência**: `pytest` → 111 passaram (16 novos); `ruff`, `ruff format --check` e `mypy` sem
  erros. `python -m brasileirao.cli backtest` (10 min 51 s) regenerou `data/gold/backtest_report.json`
  e `model_config.json`. Resultados em `docs/methodology/validation.md`, etapa 2.
- **Resultado**: inflação de empates **não adotada** (corrige a taxa média de empates, 26,1% → 26,9%
  contra 27,3% observados, mas o log loss de posição na validação piora: 2,2614 → 2,2665). Incerteza
  **não adotada** (validação já tinha cobertura de 91,7%; toda incerteza extra piorou o log loss de
  posição). No teste, a força latente com sd entre 0,075 e 0,10 corrigiria a cobertura (86,9% →
  90–91%) sem piorar o log loss. Isso foi registrado, mas não foi usado para escolher.
- **Efeito em produção**: nenhum. `model_config.json` mantém a mesma configuração (inflação e
  incerteza desligadas) e a simulação sem incerteza é idêntica à anterior para a mesma semente;
  `MODEL_VERSION` não mudou e os snapshots publicados continuam válidos.
- **Premissas e limitações**: avaliação com 2.000 simulações por checkpoint; regras de 2026 aplicadas
  a temporadas antigas no backtest de temporada.
- **Próximo responsável**: 06 revisar a etapa 2. 02 avaliar `strength_sd` por origem móvel. 04
  expor os novos campos de `ModelInfo` na interface, se desejado.
- **Rodada 3 de símbolos (D-016)**: dono do produto escolheu as linhas R5, R4 e R8 (ordem %?); o
  descarte de R5 foi revertido. 7 variações novas em `docs/brand/exploration/svg/simbolos-r3/` e
  quadro `simbolos-r3.html`. Achado: R5c falha na versão mono. Reversa e mono de R4c e R8a–c não
  conferidas visualmente. Aberta: Q15 (variante e papel de cada símbolo).

## Agente 08 — símbolo aprovado (2026-10-26)

- **O que mudou**: D-017 registrada (símbolo = R5 com % claro no preenchimento). Arquivos em
  `docs/brand/assets/simbolo/`: principal, reverso, mono e mono reverso (% vazado por máscara),
  reduzido para menos de 48 px, `favicon.svg` com troca para tema escuro, prévia `index.html` e
  `previa.png`. Seções de nome, símbolo e paleta no `BRAND_GUIDELINES.md`. Servidor `brand-assets`
  (porta 8092) em `.claude/launch.json`.
- **Evidência**: prévia renderizada com o Edge em modo headless (`previa.png`), mostrando as quatro
  versões em 192/96/48/32 px, a reduzida de 40 a 16 px, o avatar e a assinatura provisória. Depois do
  ajuste D-018 (% cerca de 25% menor), o % vira um ponto em 48 px; daí o limite de 64 px para a
  versão completa.
- **Premissas e limitações**: troca do favicon no tema escuro não verificada visualmente; tipografia
  da assinatura em aberto (Q16); ícone de app não definido; a interface ainda usa o nome antigo.
- **Próximo responsável**: dono do produto (Q16, tipografia); depois, o Agente 08 (assinatura e
  tokens) e o Agente 05 (aplicação na interface após o kit).
- **Assinatura (D-019)**: o "?" do nome passa a ser o símbolo. Estudo com Archivo, Inter Tight,
  Space Grotesk e Fraunces em `docs/brand/exploration/assinatura.html`, renderizado com o Edge em
  modo headless (`assinatura-previa.png`). Aberta: Q16 (fonte).
- **Grafia (D-020)**: nome corrigido para "AInda dá?" (A e I maiúsculos = "AI") nos documentos de
  referência e nos arquivos do símbolo. Estudo de assinatura refeito: nas fontes sem serifa o "I"
  se confunde com "l" ("Alnda"); Fraunces ou "AI" em vermelho resolvem. Aberta: Q16 (fonte e destaque).
- **Tipografia (D-021)**: Inter Tight 800, sem destaque no "AI"; regras no guia. Pendente: converter
  a assinatura em contorno (requer baixar a fonte e a biblioteca fontTools, com autorização).
- **Assinatura entregue**: 6 SVGs em contorno em `docs/brand/assets/assinatura/` (principal,
  reversa, mono, mono reversa, reduzida e reduzida reversa). Fonte Inter Tight e `OFL.txt` baixados
  com autorização do dono do produto (procedência e SHA-256 em `docs/brand/assets/fontes/PROVENIENCIA.md`);
  `fonttools` 4.67.0 instalado no `.venv`. Conferência: largura do texto em contorno 382,01 contra
  382,02 medidos no Edge com a mesma fonte. Prévia renderizada em `previa.png`.

## Agente 08 — ícone de app e delegação de frontend/UX (2026-10-26)

- **Decisões**: D-022 (dono do produto delega ao Agente 08 as decisões de marca, frontend e UX, com
  revisão posterior) e D-023 (ícone de app: símbolo reverso sobre tinta). Ícone em
  `docs/brand/assets/icone/` (SVG + PNG 512, 192 e 180, exportados com o Edge em modo headless).
- **Em andamento**: redesenho do frontend com a marca. Linha de base capturada em 1280 px. Os arquivos
  `apps/web/index.html`, `assets/styles.css` e `assets/app.js` foram alterados às 18:43 por outra
  sessão ("Instalação e testes do projeto", nova página "Rodadas"); mensagem de coordenação enviada.
  **Nenhuma alteração no frontend foi feita pelo Agente 08 ainda.**
- **Próximo passo**: após a resposta da outra sessão, aplicar tokens, cabeçalho com a assinatura,
  favicon e ajustes de UX; verificar em 1280 e 375 px.

## Iteração 4 (2026-10-26): origem móvel e revisão rodada a rodada (Agentes 02, 04, 05, gate do 06)

- **Origem móvel** (`strength_sd` escolhido nas 6 temporadas anteriores): avaliada no relatório
  (`rolling_origin_selection`) e **não adotada**: log loss de posição no teste 2,2205 contra 2,2144,
  cobertura 87,6% contra 86,9%. Detalhes em `docs/methodology/validation.md`. Produção inalterada.
- **Revisão rodada a rodada**: `simulation/round_review.py` (cortes por rodada, impacto por jogo,
  decomposição resultados/força, resíduo e ruído esperado); `prepare_simulation` e
  `build_round_review` em `pipeline.py`; tabela `round_reviews` e esquema `RoundReview` (Agente 04);
  CLI `review-rounds`; rota `GET /api/seasons/{season}/rounds`; espelho estático
  `apps/web/data/api/seasons/2026/rounds.json`; aba "Rodadas" na interface (Agente 05).
- **Diagnóstico do histórico anterior**: começava na rodada 6 e usava "último jogo da rodada" como
  data, o que, com jogos adiados (rodada 4 até 02/09, rodada 21 até 03/10), suprimia ou deslocava
  visões. O histórico de snapshots (`probability-history`) não foi alterado; a revisão por rodada é
  um artefato separado.
- **Evidência**: `pytest` → 135 passaram (20 novos nesta iteração); `ruff`, `ruff format --check` e
  `mypy` sem erros. `review-rounds --simulations 20000` gerou 32 visões (rodadas 0 a 31, a 31
  parcial). Interface verificada no navegador (rodadas 17 e 23), sem erros de console.
- **Limitações**: resíduo de atribuição acima do ruído no rebaixamento no início da temporada
  (interação entre jogos); o JSON tem ~1,1 MB; a execução com 20.000 simulações levou 21 min (com outro processo concorrente).
- **Próximo responsável**: 06 revisar a decomposição; 05/08 aplicar a marca à aba "Rodadas"
  (coordenado com a sessão do Agente 08); 04 avaliar enxugar o JSON (impactos abaixo do ruído).
- **Interface com a marca (D-024)**: `apps/web/index.html` (título, meta, favicon, ícones, manifest,
  assinatura no cabeçalho, rodapé), `assets/styles.css` (reescrito com tokens claros/escuros, mesmos
  nomes de classe) e textos de `assets/app.js` (início, tabela, jogos, metodologia, aviso de jogos
  sem placar recolhível). Arquivos novos: `manifest.webmanifest`, `assets/fonts/` (Inter Tight WOFF
  + OFL), `assets/brand/` (assinaturas, favicon, ícones). Lógica de dados e aba "Rodadas" intactas.
- **Evidência**: capturas em 1280 px (Edge headless) das 5 rotas principais; no navegador do app em
  375 px, as 6 rotas sem rolagem horizontal (`scrollWidth = 375`), fonte carregada, tema escuro
  conferido; console só com os 404 esperados de `/api/*` no servidor estático. `pytest`: 135 passaram.
  Servido pela API (TestClient do FastAPI 0.162): `/`, `manifest.webmanifest`, fonte, assinatura,
  favicon e `/api/seasons/2026/predictions` respondem 200.
- **Próximo responsável**: dono do produto revisa o visual (D-022); Agente 06 confere contraste.

## Iteração 5 (2026-10-26): avaliação por rodada, por time e comparativo (Agentes 02, 05)

- **O que mudou**: a aba "Rodada a rodada" saiu de `app.js` para `apps/web/assets/rounds.js` e
  `rounds.css` (combinado com o Agente 08; `app.js` só delega a rota e `index.html` inclui os dois
  arquivos). Três visões: por rodada (agora com a tabela real da data e a "Avaliação de todas as
  rodadas", com intensidade calma/normal/agitada pelos quartis do movimento), por time (gráficos de
  chances e posição, momentos que mais mudaram a temporada, tabela rodada a rodada com os jogos do
  time) e comparativo (até 3 times, 6 métricas, tabela de valores e a tabela de todos os times em
  qualquer rodada). `team_metrics` passou a gravar a tabela real (posição, pontos, jogos, saldo) em
  cada visão; revisão regenerada com 20.000 simulações.
- **Escudos**: sessão separada "Escudos dos clubes da Série A 2026" busca os escudos com licença
  registrada em `apps/web/assets/crests/manifest.json`; a interface já os exibe quando o manifest
  existe e funciona sem ele.
- **Evidência**: `pytest` → 136 passaram; ruff e mypy sem erros. Paleta de séries validada com o
  validador de paleta do skill de visualização (vermelho e âmbar juntos falham para deuteranopia,
  ΔE 1,4, por isso o limite de 3 séries). Navegador: as três visões em 1024 px e em 375 px no tema
  escuro, sem rolagem horizontal e sem erros de console.
- **Próximo responsável**: Agente 08 revisar o visual da aba; integrar os escudos quando a sessão
  de escudos entregar o manifest (nenhuma mudança de código necessária).

## Agente 08 — seletor corrigido, interface mais calma e novo papel (2026-10-26)

- **Seletor de cenários (D-025)**: as escolhas parciais eram apagadas a cada redesenho, então o
  seletor não funcionava. Agora as escolhas ficam guardadas, a faixa estreita (32 → 16 → 4 → 2 → 1
  cenário no teste), cada seletor só oferece combinações possíveis, o foco volta ao seletor e há
  "Limpar escolhas". Evidência: teste por JavaScript no navegador do app, rota `#/classificacao`.
- **Menos "cara de IA" (D-025)**: serifa no texto corrido, fim dos rótulos em maiúsculas espaçadas
  (`styles.css` e `.intensity` em `rounds.css`, com aval da sessão da aba de rodadas), pesos
  menores. Evidência: capturas em 1280 px; 7 rotas em 375 px sem rolagem horizontal; console sem
  erros além dos 404 esperados de `/api/*` no servidor estático.
- **Novo papel (D-026)**: `agents/08-brand-storytelling-ux.md` (substitui `08-brand-manager.md`,
  com anexo da Fase A), `agents/08A-insights-intelligence.md`, subagentes em `.claude/agents/` e
  `infrastructure/claude-agents/`; `docs/storytelling/` (estratégia, catálogo com 18 regras,
  validação, guia de conteúdo, contrato `contracts/insight.schema.json` e critérios
  `contracts/insight-criteria.toml`); `docs/ux/` (princípios, jornadas, engajamento); fixture
  `tests/fixtures/insights/insight_batch.synthetic.json`. `AGENTS.md`, README, roadmap e contratos
  02, 04, 05 e 06 atualizados.
- **Verificação**: schema e TOML carregam sem erro; a fixture tem aritmética conferida (Δ 12 p.p.,
  limiar de ruído 1,84 p.p. com z = 3, pontuação 0,84). **Não validada formalmente contra o
  schema**: `jsonschema` não está instalado (instalar exige autorização).
- **Pendências**: módulo `src/brasileirao/insights/` (08A) e testes (06); armazenamento e endpoints
  editoriais (04); dados pedidos ao 02 (pontos esperados pela força; simulação condicional por
  jogo). Nenhum insight publicado.

## Subagente 08A implementado: 4 regras e fluxo editorial (2026-10-26)

- **O que mudou**: módulo `src/brasileirao/insights/` (contratos, critérios, regras, portões,
  gerador, registro editorial); `INSIGHT_RULES_VERSION` e caminhos `editorial`/`insight_criteria`
  em `config.py`; comandos `insights-generate`, `insights-list`, `insights-review` e
  `insights-publish` em `cli.py` (arquivo do Agente 00); rota `GET /api/seasons/{s}/insights` em
  `apps/api/main.py` (arquivo do Agente 04); `rule_id` acrescentado ao `published_insight` do
  contrato; `tests/unit/test_insights.py` (21 testes, dados sintéticos).
- **Evidência**: `ruff check` e `ruff format --check` sem apontamentos; `mypy --strict` sem erros
  em 42 arquivos; `pytest`: 157 passaram. Execução real (lote `2026-s27-rules-2026.10.1-743786ab`):
  2 candidatos, nenhum reprovado nos portões; números conferidos direto nos arquivos de dados
  (valores por clube no registro local `data/editorial/status_numeros_reais.md`, decisão B1). Revisados e aprovados pelo Agente 08, publicados e servidos pela API (200, 2 itens).
- **Premissas e limitações**: o snapshot anterior (13/10) tem 2.000 simulações e o atual 10.000; o
  teste de ruído considera os dois. A decomposição resultados × força só é citada quando a revisão
  por rodada cobre o mesmo intervalo (não foi o caso). O armazenamento editorial é em arquivos
  JSON, não no SQLite. O título e o texto no terminal do Windows aparecem com acentos trocados
  (codificação do console; os arquivos são UTF-8).
- **Próximo responsável**: **05/08** exibir os insights publicados na home e na aba de rodadas;
  **04** avaliar mover o registro editorial para o SQLite e incluir `insights.json` no
  `export-web`; **06** auditar as regras; **02** dados pedidos no catálogo.

## Escudos dos 20 clubes da Série A 2026 (Agente 01, 2026-10-26)

- **O que mudou**: escudos novos em `apps/web/assets/crests/` (16 SVG e 4 PNG, um por `club_id` da
  temporada 2026 de `data/gold/matches_model.csv`) e `manifest.json` no formato combinado (`file`,
  `source_url`, `file_page_url`, `author`, `license`, `license_status`, `retrieved_at`, `sha256`).
  Nova linha "Escudos de clubes" em `docs/data-sources/catalog.md`. Nenhum arquivo de interface foi
  editado.
- **Fontes**: 17 escudos do Wikimedia Commons sob PD-textlogo, com aviso Trademarked (Mirassol e São
  Paulo também PD-shape). Os arquivos foram escolhidos pela imagem principal da página do clube na
  pt.wikipedia. Bragantino, Corinthians e Vasco não têm escudo atual livre no Commons; os arquivos
  vieram da pt.wikipedia, onde estão como "conteúdo restrito" (© dos clubes). A lista de URLs foi
  aprovada pelo usuário antes do download. Arquivos descartados: o "Official Logo … Corinthians …
  crest 2026.png" do Commons, que diz ser "obra própria" sob CC BY-SA mas reproduz o escudo oficial,
  e os arquivos de Vasco no Commons, que são bandeiras de fantasia ou escudos históricos.
- **Evidência**: o SHA-1 de cada download foi conferido com o da API da Wikimedia, e o SHA-256 do
  manifest foi recalculado sobre os arquivos entregues (20/20 iguais; 20 clubes, 20 arquivos, nenhum
  extra). Cada SVG foi analisado como XML, sem script, eventos, `foreignObject` ou `href` externo. O
  do Fluminense tem só o DOCTYPE público padrão do SVG 1.0, sem entidades. Cada PNG tem canal alfa,
  cantos transparentes e pelo menos 323 px no menor lado. Os 20 renderizam em `<img>` a 64 px
  servidos por `http://127.0.0.1:8001/assets/crests/`.
- **Premissas e limitações**: `botafogo.svg` e `chapecoense.svg` receberam um atributo `viewBox`
  (sem mudança no desenho) para escalar dentro de `<img>`. O manifest guarda `source_sha256` e
  `modification` nesses dois. PD-textlogo é uma avaliação dos editores do Commons, não do clube.
  Domínio público de direito autoral não autoriza uso como marca: os escudos só podem identificar o
  clube como dado (BRAND_GUIDELINES, princípio 4). Os escudos atuais podem mudar (estrelas, redesenho);
  a coleta vale para 2026-10-26.
- **Pendências de licença**: `bragantino`, `corinthians` e `vasco` estão como
  `nao_livre_uso_local`. Antes de qualquer deploy público é preciso obter autorização dos clubes,
  avaliar juridicamente o uso nominativo ou trocar por um marcador neutro (sigla). Revisão dos
  Agentes 00 e 06 obrigatória.
- **Próximo responsável**: a sessão da aba "Rodadas" (05) lê o manifest e exibe os escudos; **08**
  define tamanho e tratamento visual; **06** confere o manifest; **00/07** decidem como tratar os
  três não livres num deploy público (por exemplo, filtrar `license_status != "livre"` no export).

## Escudos: status de licença alterado por decisão do dono do produto (2026-10-26)

- **O que mudou**: em `apps/web/assets/crests/manifest.json`, `bragantino`, `corinthians` e
  `vasco` passaram de `nao_livre_uso_local` para `livre` por decisão explícita do dono do produto.
  Cada um ganhou um campo `license_status_override` com quem decidiu, a data e o status anterior.
- **Limitação**: a decisão não muda a licença real. Os três escudos continuam © dos clubes e sem
  licença livre (o campo `license` não foi alterado). Antes de um deploy público, os Agentes 00 e 06
  devem considerar `license_status_override` e não só `license_status`.

## Escudos: procedência fora do frontend (2026-10-26)

- **O que mudou**: a pedido do dono do produto, a procedência completa dos escudos (fonte, autor,
  licença, `license_status`, `license_status_override`, SHA-256) saiu de
  `apps/web/assets/crests/manifest.json` e foi para `data/reference/crests_provenance.json`, fora da
  pasta servida pelo site. O manifest da web ficou só com `{"<club_id>": {"file": "..."}}`, que é
  o único campo lido por `rounds.js`.
- **Próximo responsável**: **06/00** fazem auditoria e revisão de licença pelo arquivo em
  `data/reference/`. **07** não precisa empacotar esse arquivo no site.

## Insights publicados na interface (2026-10-26)

- **O que mudou**: `apps/web/assets/app.js` (carrega `/insights`; manchete e destaques na home;
  bloco "Destaques desta rodada" via `highlights(view)`), `assets/styles.css` (`.highlights`,
  `.highlight`, `.highlight-links`) e uma linha em `assets/rounds.js` (gancho opcional
  `helpers.highlights`, combinado com a sessão dona da aba).
- **Evidência**: capturas em 1280 px (Edge headless) da home e da aba; no navegador do app, em 375 px
  e tema escuro: home com manchete e 1 destaque; aba com 2 destaques só na rodada 31; 0 na rodada 30
  e em "Por time"; o bloco continua depois de trocar a métrica; sem rolagem horizontal; console sem
  erros além dos 404 esperados de `/api/*` no servidor estático.
- **Premissas**: só aparecem insights do snapshot exibido; sem manchete aprovada, a home volta ao
  layout anterior. O snapshot citado (nº 27, 18/10) segue o mais recente depois da regeneração da
  revisão por rodada, e os números do jogo citado não mudaram.
- **Próximo responsável**: **04** incluir `insights.json` no `export-web`; **08A/08** mais regras.

## Atualização de dados (2026-10-26, noite): rodada 32 (Agentes 01, 02, 04)

- **O que mudou**: `brasileirao.cli ingest --fetch` trouxe o commit `838614d` do brasileirao-dataset
  (atualização automática de 26/10 18:45 -04). Entraram 10 resultados: 1 jogo atrasado da
  rodada 31 e 9 jogos da rodada 32. Um deles era placar parcial, corrigido depois (ver "Conferência
  com o ge.globo"); placares no registro local `data/editorial/status_numeros_reais.md`. Total de 2026:
  318 jogos com placar (antes, 308). Restam 2 jogos com data passada sem placar na fonte:
  Chapecoense × Vasco (30/07) e Flamengo × Atlético-MG (26/10, ainda não registrado), ambos
  simulados. `validate`: sem erros.
- **Snapshot**: id 28, data de referência 2026-10-26, 10.000 simulações, semente 2026, mesmo modelo
  (`poisson-elo-ad-0.1.0`). O líder da tabela não era o favorito ao título, porque o segundo tinha
  um jogo a menos. Pontos, probabilidades e variações por clube no registro local
  `data/editorial/status_numeros_reais.md` (decisão B1). O snapshot 28 usou um placar parcial errado
  e foi substituído pelo 29.
- **Revisão rodada a rodada**: regenerada com os dados novos (20.000 simulações por visão).
- **Escudos**: 20 de 20 clubes em `apps/web/assets/crests/` (sessão "Escudos dos clubes da Série A
  2026"; procedência em `data/reference/crests_provenance.json`), exibidos na aba Rodadas.
- **Pendente**: novo lote de insights editoriais para o snapshot 28 (fluxo 08A/08; os insights
  publicados eram do snapshot de 18/10 e deixam de aparecer).

## Proposta de deploy gratuito (Agente 07, 2026-10-26) — pendente

- **O que mudou**: só documentação. Nova seção "Proposta: deploy gratuito" em
  `docs/architecture/deploy.md` (status: proposta, pendente de aprovação 00/06 e do dono do
  produto). Nenhum workflow, código, conta ou publicação.
- **Recomendação**: site estático (`apps/web` + export JSON) gerado por GitHub Actions agendado.
  GitHub Pages se o repositório for público; Cloudflare Pages se for privado. API em free tier
  (Render, Cloud Run, Fly.io, Koyeb, HF Spaces) descartada por hibernação, cold start, SQLite
  efêmero e, em alguns casos, cartão obrigatório, sem ganho para a interface.
- **Evidência**: `git status` → "not a git repository". `fetchJson` (`apps/web/assets/app.js`) cai em
  `data/api/*.json` quando `/api` não responde JSON. As 5 rotas usadas existem no export. `apps/web`:
  42 arquivos, 2,34 MB; export 1,58 MB (`rounds.json` 1,18 MB, 169 KB com gzip -9);
  `snapshots.sqlite` 11 MB; `data/raw` 106 MB. Arquivos lidos: `agents/07-deploy.md`,
  `docs/architecture/deploy.md`, `docs/data-sources/catalog.md`, ADR-0002, ADR-0005, os dois
  workflows, `Dockerfile`, `docker-compose.yml`, `.gitignore`, `apps/api/main.py`, `index.html`,
  `export_static_api` (`pipeline.py`) e `cli.py`.
- **Premissas e limitações**: limites dos provedores vêm de conhecimento prévio, sem consulta às
  páginas oficiais; ficaram marcados "a verificar". O tempo de `review-rounds` no runner não foi
  medido (localmente usou 20.000 simulações por visão).
- **Lacunas encontradas**: o workflow agendado não roda `review-rounds`; o SQLite (estado do
  histórico) não persiste entre execuções do Actions; `backtest_report.json` não é gerado no
  workflow; o `.gitignore` deixaria `data/silver/`, `data/gold/matches_model.csv` e o SQLite
  versionados; o rodapé diz "pesquisa local".
- **Bloqueios**: licença dos dados de 2024+ (ADR-0002); 3 escudos não livres e marcas registradas;
  gate 00/06; diretório sem git.
- **Decisões pendentes do dono do produto**: repositório público ou privado (define Pages ou
  Cloudflare); aceitar subdomínio gratuito (D-013); frequência do agendamento.
- **Próximo responsável**: **00/06** revisam a proposta e decidem o que pode ser versionado e
  publicado. **01** resolve a licença de 2024+. **08** revisa o texto do rodapé. **04/05** avaliam o
  modo estático explícito. **07** implementa o workflow só depois dessas aprovações.

## Símbolo compacto com % no cabeçalho e correção do 08A (2026-10-26)

- **O que mudou (D-027)**: `ainda-da-simbolo-compacto(-reverso).svg` e
  `ainda-da-assinatura-compacta(-reversa).svg` em `docs/brand/assets/` e cópias em
  `apps/web/assets/brand/`; cabeçalho de `apps/web/index.html` usa a compacta (36 px; 32 px no
  celular). Guia atualizado com as faixas de tamanho.
- **Evidência**: comparação renderizada (Edge headless) de reduzida, compacta e completa em 30 e
  40 px com densidade 1 e 2: o % da compacta é legível em 40 px (densidade 1) e em 30 px
  (densidade 2). No navegador do app, em 375 px: logo de 32 px, densidade 2, sem rolagem horizontal.
- **08A**: `MATCH_MOVED_MOST` agora exige revisão por rodada com a mesma data do snapshot. Antes,
  com um snapshot novo e a revisão ainda antiga, a regra republicaria o jogo da rodada anterior.
  Novo teste; `pytest`: 158 passaram; ruff e mypy sem apontamentos.
- **Dados novos (sessão "Instalação e testes")**: snapshot 28 (26/10). Os insights de 18/10 saíram
  da home e da aba automaticamente. Novo lote editorial: pendente até a revisão por rodada ser
  regenerada com os dados de 26/10.

## Revisão visual da aba Rodada a rodada com escudos (Agente 08, 2026-10-26)

- **Parecer**: aprovada com ajustes. Escudos como dado (16–20 px em listas e tabelas, 48 px no título
  do time, sem moldura), 20/20 carregando, sem rolagem horizontal em 375 px nas três visões, tema
  escuro conferido.
- **Corrigido pelo 08**: `select` com largura total restrito a `.scenario-panel` (o seletor de
  rodada ficava desalinhado por causa da regra global); `.compare-picker` em rounds.css sem caixas,
  com sublinhado no selecionado.
- **Pedido à sessão dona da aba (rounds.js)**: rebaixamento em --danger na visão do time; métrica
  padrão pela disputa relevante do clube e limiar de ruído nos "momentos"; esconder clubes sem
  chance na tabela da rodada; trocar "@" por "fora".
- **Ainda não feito**: novo lote editorial para 26/10, que depende da regeneração da revisão por
  rodada.

## Revisão do Agente 00: deploy gratuito no GitHub Pages (2026-10-26) — ADR-0007 proposto

- **Decisão do dono do produto (chat, 2026-10-26)**: repositório **público** e deploy no **GitHub
  Pages** (site estático gerado por Actions agendado, sem API no ar). Ainda não confirmados: o
  subdomínio `<usuario>.github.io/<repo>` (D-013) e a frequência do agendamento.
- **Parecer do 00 sobre a proposta do 07**: **aprovada com condições**. A arquitetura estática
  (opção A1) e a preparação com o deploy desligado estão liberadas. **A publicação pública continua
  bloqueada** (ADR-0002) até C1–C6 do ADR-0007 e os pareceres finais do 00 e do 06.
- **O que mudou**: novo `docs/decisions/ADR-0007-deploy-estatico-github-pages.md` (status
  "proposto"), com a tabela do que pode ser versionado no repositório público, a persistência do
  SQLite (asset de release `snapshots-db` + artefato + cópia local), métricas, `review-rounds`,
  insights, gate, alternativas descartadas e condições C1–C6. Riscos R10–R12 em
  `docs/project/risks.md`. Linha da fase 7 em `docs/roadmap.md`. Nenhum código, workflow,
  `.gitignore` ou arquivo de outro agente foi alterado; nenhum repositório git foi criado.
- **Ajustes do 00 à proposta do 07**:
  1. Também **não** versionar `apps/web/data/` (o export tem placares e probabilidades),
     `data/gold/quality_report.json`, `data/editorial/` (até C1) e os 3 escudos não livres. O 07
     propunha versionar `data/editorial/` e não citava o export nem os escudos.
  2. O asset de release do SQLite é público num repositório público: só pode existir depois de C1.
  3. A licença de 2003–2023 também precisa ser registrada (o repositório de origem não tem LICENSE).
  4. O repositório no GitHub nasce **privado** e só fica público depois da auditoria de
     `git ls-files` pelo 06 (C4), porque o histórico não pode ser limpo com segurança depois do push.
  5. Gate com consistência de datas e `model_version` entre `predictions`, `rounds` e `metrics`, e
     sem escudos não livres no artefato.
- **Evidência**:
  - `pytest` com `BRASILEIRAO_ROOT` apontando para uma cópia com só `data/reference/`,
    `data/gold/model_config.json`, `data/gold/backtest_report.json` e
    `docs/storytelling/contracts/` (simula o checkout público): **158 passaram**. Com a raiz vazia,
    houve 23 erros e 1 falha, todos por `FileNotFoundError` em `data/reference/clubs.csv` e nos
    contratos do 08A. Isso confirma que esses arquivos precisam ser versionados.
  - `data/gold/backtest_report.json`: chaves de nível superior só com métricas agregadas,
    calibração, parâmetros e registros de ajuste; a busca por `match_id` e por campos de clube
    não encontrou nada.
  - Tamanhos: `data/raw` 106 MB, `data/snapshots` 11 MB, `data/silver` 1,5 MB, `apps/web/data`
    1,6 MB (6 JSON). O `.gitignore` atual só exclui `data/raw/_sources/` e os JSON brutos.
  - Textos de licença a revisar: `apps/web/index.html:44` (rodapé) e `apps/web/assets/app.js:421`
    ("Uso restrito a pesquisa local").
  - Nenhum segredo encontrado fora de `.venv`/`data` (`.env.example` tem só o nome da variável do
    token). `git` 2.56 disponível; `gh` não está instalado.
- **Premissas e limitações**: os limites do GitHub (Pages, artefatos, cache, desativação após 60
  dias) não foram consultados nas páginas oficiais e seguem "a verificar". O tempo de
  `review-rounds` no runner não foi medido. O Agente 06 revisa em paralelo e seu parecer ainda não
  está registrado aqui.
- **Ordem das entregas e responsáveis**:
  1. **06**: parecer sobre o ADR-0007 (tabela de versionamento, gate e C1–C6).
  2. **07**: `.gitignore` conforme a tabela do ADR-0007; `git init` local; primeiro commit **sem**
     os caminhos excluídos; repositório GitHub **privado**. Atualizar `docs/architecture/deploy.md`
     com os ajustes do 00.
  3. **06**: auditoria de `git ls-files` contra a tabela (C4).
  4. **07**: workflow `publish-site.yml` com `workflow_dispatch`, `schedule` comentado e o job de
     deploy desligado; restauração e checagem do SQLite; `review-rounds`; gate. Uma execução que
     só gera o artefato e mede os tempos (C5). Sem release `snapshots-db` antes de C1.
  5. **01**: C1. Token da football-data.org, termos verificados, adaptador validado contra a API
     real, ratings e treino de 2024+ sem dados do Sofascore, licença de 2003–2023 no catálogo,
     conferência com a CBF. **02** recalcula o snapshot e **06** revalida o backtest com a nova fonte.
  6. **08**: C2 (rodapé e parágrafo de fonte com a atribuição exigida) e C6 (busca no INPI). **05**
     implementa os textos.
  7. **01/05**: C3. Retirar os 3 escudos não livres do repositório e do build e usar marcador com a
     sigla. **04/05** (recomendado): modo estático explícito em `fetchJson`.
  8. **00 + 06**: parecer final. Só então o ADR-0007 passa a "aceito", o repositório fica público,
     o deploy e o `schedule` são ligados e a release `snapshots-db` é criada.
- **Decisões pendentes do dono do produto**: confirmar o subdomínio gratuito e o nome do
  repositório/usuário (definem a URL); frequência do agendamento; aceitar o marcador com sigla para
  Bragantino, Corinthians e Vasco ou pedir autorização aos clubes; se aceita publicar antes do kit
  de marca M4 e da busca no INPI; se quer uma página só com marca e metodologia, sem dados, antes
  de C1 (não recomendado).

## Parecer do Agente 06: deploy gratuito no GitHub Pages (2026-10-26)

Registrado pelo orquestrador a partir do relatório do 06, que revisou sem editar arquivos.

- **Parecer**: arquitetura estática no GitHub Pages **aprovada com condições**; publicação pública
  **reprovada no estado atual**.
- **Evidência**:
  - `pytest -q`: 158 passed, 1 warning (depreciação httpx/TestClient).
  - Fallback estático de `fetchJson` e subcaminho `/web/` servidos via `http.server`: todos os
    assets e os 5 JSON retornaram 200, e `/api/...` deu 404, o que aciona o fallback.
  - Invariantes conferidas à mão no export atual, todas OK:
    - 20 clubes; 380 jogos, sendo 318 `finished` e 62 `scheduled`.
    - Soma de P(título) = 1, de P(rebaixamento) = 4 e de top-4 = 4. Linhas e colunas de posição
      somam 1. 1X2 = 1.
    - Placares batem com o bruto e o silver (0 divergências). Jogos sem placar seguem `scheduled`.
    - Libertadores = 9 e Sul-Americana = 6 nos 32 cenários.
  - A simulação do `.gitignore` atual versionaria 273 arquivos, entre eles cerca de 13,5 MB em
    `data/`, o export `apps/web/data/api/` e os 20 escudos. Nenhum segredo.
  - Tamanhos: `apps/web` tem 44 arquivos e 2,37 MB; o export tem 1,58 MB.
- **Bloqueantes**:
  - **B1, licença**: 2024+ é Sofascore, `research_only_unverified`, com `allowed_uses` só local.
  - **B2, `.gitignore` antes do primeiro commit**: incluir `apps/web/data/api/` e
    `quality_report.json`; reavaliar `data/editorial/`.
  - **B3, escudos**: Bragantino, Corinthians e Vasco não são livres; os outros 17 são marcas.
  - **B4, gate do workflow**: invariantes do export; integridade de placar contra o bruto e
    `reference_date`; proveniência e `is_synthetic`; coerência de versões entre
    `predictions`/`rounds`/insights; seed e versões em `probability-history`; lista permitida de
    `license_status`; smoke test em subcaminho. O SQLite não fica em artefato nem em release
    públicos antes de B1.
- **Não bloqueantes**:
  - **C1**: modo estático explícito (`/api` absoluto aponta para a raiz de `*.github.io`).
  - **C2**: textos do rodapé e da metodologia.
  - **C3**: `review-rounds` e métricas na mesma versão de dados.
  - **C4**: fixar a versão da fonte por execução.
  - **C5**: conferir nas páginas oficiais os limites marcados "a verificar".
  - **C6**: Docker sem execução.
- **Convergência com o ADR-0007**: as exclusões, o repositório privado até a auditoria e a release
  `snapshots-db` só depois de C1 (ADR) / B1 (06) são as mesmas nos dois pareceres. A lista B4 do
  06 é mais detalhada que o gate do ADR e deve ser incorporada pelo 07 no `publish-site.yml`.
- **Próximo responsável**: 07, para o `.gitignore`, o `git init` e o primeiro commit privado, e
  depois o 06, para auditar `git ls-files`.
- **Ajustes da aba conferidos (08)**: cores fixas na visão do time; métrica inicial pela disputa em
  aberto (Inter: Rebaixamento; Flamengo: Título) e limiar de 2 erros-padrão nos "momentos"; tabela
  da rodada com 2 linhas mais o resumo dos outros 18; "(fora)" no lugar de "@". Aprovados. O 404
  de `/api/seasons/{s}/insights` em 127.0.0.1:8001 vinha de um processo uvicorn iniciado antes da
  rota existir; a rota responde 200 no código atual.

## Agente 07: `.gitignore` do ADR-0007, `git init` e primeiro commit local (2026-10-26)

A pedido do dono do produto (chat). Repositório **só local**: sem remote, sem push, sem
repositório no GitHub.

- **O que mudou**:
  - `.gitignore` reescrito pela tabela do ADR-0007 (item 3) e pelo parecer do 06 (B2, B3). Fora do
    git: `data/raw/` inteiro (inclusive manifestos), `data/silver/`, `data/gold/*` com exceção de
    `model_config.json` e `backtest_report.json` (sai `matches_model.csv` e `quality_report.json`),
    `data/snapshots/` e `*.sqlite`/`*.sqlite3`/`*.db`, `data/editorial/` (até C1),
    `apps/web/data/` (export), os 3 escudos não livres (`apps/web/assets/crests/bragantino.png`,
    `corinthians.png`, `vasco.svg`), `.venv/`, caches, `.env`/`.env.*` (exceto `.env.example`),
    `*.pem`, `*.key`, `.claude/settings.local.json`, `*.log`.
  - Novo `.gitattributes` (`* text=auto`; imagens, fontes e SQLite como binários).
  - `git init -b main` e primeiro commit local. Identidade: a configuração global já existente
    (`user.email` vitorpereira3115@gmail.com); nada foi alterado no git config.
  - `docs/architecture/deploy.md`: status da proposta, ajustes do 00 (exclusões, release
    `snapshots-db` só depois de C1, repositório nasce privado), gate com a lista B4 do 06 e nova
    seção "Repositório git local".
- **Evidência** (antes do commit):
  - `git check-ignore -v` confirmou a regra para cada caminho excluído (ver `.gitignore`); as
    negações `!data/gold/model_config.json` e `!data/gold/backtest_report.json` os mantêm.
  - Itens versionados: 252 arquivos, ~2,7 MB; maior arquivo `docs/brand/assets/fontes/InterTight[wght].ttf`
    (582 KB, OFL). Nenhum arquivo acima de 1 MB.
  - Busca de segredos (padrões de chave/token/senha atribuídos, `ghp_`, `github_pat_`, `sk-`,
    `AKIA`, chaves privadas) nos arquivos versionados: nada. Ocorrências de "token" são nomes de
    variável (`FOOTBALL_DATA_ORG_TOKEN=` vazio em `.env.example`, `api_token` em `sources.py`) e
    tokens numéricos do 08A.
  - Primeiro commit `682e1fb` (252 arquivos, 2.698.659 bytes). `git clone` local num diretório
    temporário, só com os arquivos versionados (`data/` contém apenas `reference/` e
    `gold/{model_config,backtest_report}.json`; 17 escudos + `manifest.json`), com
    `BRASILEIRAO_ROOT` e `PYTHONPATH` apontando para o clone (conferido que `brasileirao.config` e
    `apps.api.main` foram importados do clone): `pytest -q` **158 passed, 1 warning** (depreciação
    httpx/TestClient).
- **Premissas e limitações**:
  - Os 3 escudos não livres **continuam no disco local** e em
    `apps/web/assets/crests/manifest.json` (versionado). Num checkout limpo, `rounds.js` monta
    `<img>` para arquivos que não existem (404, imagem quebrada). Os 17 outros escudos estão
    versionados, condicionados a C3.
  - `crests_provenance.json` marca os 3 como `license_status: "livre"` por override do dono do
    produto; o campo `license` diz "Não livre". O `.gitignore` segue o ADR-0007, não o override.
  - O texto do repositório (docs, status) cita números agregados derivados da fonte restrita
    (ex.: contagens, métricas de backtest). A auditoria C4 do 06 deve conferir isso também.
- **Próximo responsável**:
  - **06**: auditoria de `git ls-files` contra a tabela do ADR-0007 (C4), antes de qualquer remote.
  - **05** (C3): marcador com a sigla para Bragantino, Corinthians e Vasco e retirada das 3 entradas
    do `manifest.json` (ou `file: null`) para o build público.
  - **07**: depois do C4, repositório GitHub **privado** e `publish-site.yml` com deploy desligado (C5).

## Auditoria C4 do Agente 06: repositório git local (2026-10-27)

Registrado pelo orquestrador a partir do relatório do 06, que auditou sem editar arquivos.

- **Parecer**:
  - Push de `main` para um repositório GitHub **privado**: **aprovado**.
  - Tornar o repositório **público**: **reprovado por enquanto**.
- **Evidência**:
  - Commits 682e1fb e 3f935bf; 252 arquivos; um único ref.
  - `git rev-list --objects --all` não traz nenhum caminho proibido pelo ADR-0007.
  - A busca por segredos em todo o histórico não achou nada.
  - `backtest_report.json` só tem agregados. As fixtures são sintéticas e marcadas como tal.
  - pytest num clone limpo: 158 passed.
- **Bloqueios para tornar público**:
  - **B1, números da fonte restrita em docs versionados** (decisão do 00):
    - Resultados por jogo e probabilidades de snapshots aparecem em:
      - `docs/project/status.md`, linhas 25–26, 295 e 377–385;
      - `docs/methodology/model.md:80`;
      - `docs/storytelling/INSIGHTS_VALIDATION.md:63-64`;
      - `docs/brand/BRAND_EXPLORATION.md`;
      - `docs/brand/exploration/board.html:71`;
      - `data/reference/known_exceptions.csv:2`.
    - Opções: retirar e reescrever o histórico (barato antes do push) ou fazer adendo ao ADR-0007.
    - `status.md:378` registrava o placar parcial de um jogo da rodada 32, não o final, segundo
      `manual_corrections.csv`. Corrigido no registro local pelo 00 (ver "Decisão B1" abaixo).
  - **B2, escudos (C3)**:
    - O `manifest.json` ainda lista os 3 escudos excluídos. O 05 precisa implementar o marcador
      com a sigla.
    - Em `crests_provenance.json`, o campo `license_status` desses 3 escudos diz "livre", contra
      a licença real. O 01 corrige e registra a decisão do dono num campo à parte.
    - A atribuição dos escudos ainda não aparece na interface.
  - **B3, workflow**: `update-predictions.yml` publica o SQLite e o export como artifact. Não deve
    ser disparado antes de C1. O gate do C5 ainda não existe.
- **Observações**:
  - Não há LICENSE do projeto na raiz; a escolha é do dono do produto.
  - Há trabalho não versionado na árvore: `cli.py` e `ingest.py` alterados;
    `manual_corrections.csv` e `corrections.py` novos. O CSV tem `match_id` e placares da fonte e
    precisa passar pelo critério do B1 antes de ser commitado.
- **Próximo responsável**:
  - 00: decidir o B1.
  - 07: push privado de `main`, depois da decisão do B1.
  - 01: corrigir os escudos e o placar.
  - 05: implementar o marcador.

## Conferência com o ge.globo e correções manuais (2026-10-27, Agente 01)

- **Achado**: tabela e placares conferidos com o ge.globo. Rodadas 31 e 32 e a tabela acumulada dos
  20 clubes batiam, exceto dois jogos de 26/10: um jogo estava com o placar parcial na fonte (o gol
  saiu nos acréscimos) e outro não tinha placar; placares no registro local. Causa: a atualização
  da fonte de 26/10 (commit `838614d`, 18:45 -04 = 19:45 em Brasília) capturou o jogo das 19:30 em
  andamento e o gravou como encerrado.
- **O que mudou**: novo `src/brasileirao/data_pipeline/corrections.py` (`ManualCorrection`,
  `apply_corrections`, `load_corrections`); `write_silver` aplica as correções e registra no
  `changes.jsonl` (com `origin`, `evidence_url` e `checked_at`); a CLI `ingest` lê
  `data/reference/manual_corrections.csv`. Arquivo criado com as 2 correções e as URLs das páginas
  dos jogos no ge.globo. Política no catálogo de fontes (item 5).
- **Evidência**: `pytest` → 172 passaram (14 novos em `test_corrections.py`); ruff e mypy sem
  erros. Reingestão do mesmo commit: 2 correções aplicadas e 4 linhas de mudança no `changes.jsonl`.
  `validate` sem erros. Snapshot 29 (2026-10-26, 319 jogos, 10.000 simulações, semente 2026): tabela
  idêntica à do ge.globo nas 20 linhas, na mesma ordem. Probabilidades e variações por clube
  em relação ao snapshot 28 (errado) no registro local `data/editorial/status_numeros_reais.md`. O snapshot
  28 continua no banco, mas não é exibido (o 29 é o mais recente para a mesma data).
- **Revisão rodada a rodada**: regenerada sobre o snapshot corrigido (33 visões, rodadas 0 a 32, 20.000 simulações). Regra de "parcial" corrigida em `round_cutoffs`: a última visão só é parcial se ainda faltar jogo da própria rodada (a 32, completa, aparecia como parcial). `pytest`: 173 passaram.
- **Próximo responsável**: 08/08A rodar o lote editorial de 26/10 sobre o snapshot 29; 01 remover
  as correções quando a fonte passar a concordar (a ingestão as reporta como redundantes).

## Decisão B1 do Agente 00: números reais fora do git e histórico reescrito (2026-10-27)

- **Decisão do dono do produto** (2026-10-27, no chat), executada pelo 00:
  - retirar dos docs versionados os placares e as probabilidades reais derivados da fonte restrita;
  - trocá-los por exemplos marcados como ilustrativos ("Clube A", "Clube B");
  - corrigir o registro de Coritiba x Grêmio (era captura parcial da fonte);
  - reescrever o histórico git local antes de qualquer push. Não há remote.
- **Registro local dos números reais**: `data/editorial/status_numeros_reais.md`, ignorado pelo
  `.gitignore` (`data/editorial/`). Tem os trechos originais, literais, com caminho e linha, e o
  placar de Coritiba x Grêmio já corrigido conforme `data/reference/manual_corrections.csv`.
- **O que mudou** (os números saíram; o sentido técnico ficou):
  - `docs/project/status.md`: "Resultado atual", 08A, "Atualização de dados (rodada 32)", auditoria
    C4 e "Conferência com o ge.globo" apontam para o registro local.
  - `docs/methodology/model.md` (02): a rodada 17 fica sem o jogo e o placar; os agregados em p.p.
    ficam.
  - `docs/storytelling/INSIGHTS_VALIDATION.md` (08): o histórico de revisões mantém lote, IDs e
    decisões, sem clubes nem números.
  - `docs/storytelling/CONTENT_GUIDELINES.md` (08): exemplos com Clube A/B/C.
  - `docs/brand/BRAND_EXPLORATION.md` (08): exemplos com Clube A/B/C.
  - `docs/brand/exploration/board.html` (08): cartões com Clube A/B/C, marcados como ilustrativos.
  - `data/reference/known_exceptions.csv` (01): a nota de 2009 fica sem IDs da fonte (`bds-*`) e
    sem placares. As chaves (`season`, `code`) não mudaram.
  - `.gitignore`: passa a ignorar `data/reference/manual_corrections.csv`, que tem `match_id` e
    placares da fonte.
- **known_exceptions.csv continua versionado.** Quem lê: `load_known_exceptions` em
  `cli.py validate` e em `pipeline.py`. O arquivo ausente vira `{}`, e aí as exceções de 2009 e 2016
  deixariam de ser rebaixadas, mudando o `quality_report` num clone limpo. A opção mais conservadora
  é limpar só o texto da nota: código e testes ficam como estão, e a modelagem não muda.
- **Histórico**: os commits 682e1fb e 3f935bf foram substituídos por um novo commit raiz com a árvore
  limpa. Refs antigas, reflog e objetos soltos foram apagados (`reflog expire` + `gc --prune=now`).
  Hash e evidência ficam na seção seguinte.
- **Fora do commit, intacto na árvore** (trabalho do 01, ainda não versionado): `cli.py` e
  `ingest.py` alterados; `corrections.py`, `test_corrections.py` e `manual_corrections.csv` novos;
  `docs/data-sources/catalog.md` alterado. A alteração do catálogo cita placares reais de 26/10.
  Por isso ficou fora do commit e precisa da mesma limpeza antes de ser commitada. A seção
  "Conferência com o ge.globo" descreve esse código, que só vai para o git com o commit do 01.
- **Próximo responsável**:
  - **01**:
    - limpar os placares da alteração de `catalog.md` antes de commitá-la;
    - versionar `corrections.py` e os testes com um `manual_corrections.example.csv` marcado como
      `synthetic`, com o código aceitando a falta do CSV real (hoje ignorado);
    - corrigir o `license_status` dos 3 escudos (B2), com a decisão do dono num campo à parte;
    - confirmar o novo texto de `known_exceptions.csv`.
  - **02**: revisar o parágrafo da rodada 17 em `model.md` e não citar jogo, placar nem
    probabilidade por clube em docs versionados.
  - **08/08A**:
    - revisar os exemplos ilustrativos (`CONTENT_GUIDELINES.md`, `BRAND_EXPLORATION.md`,
      `board.html`) e o histórico de `INSIGHTS_VALIDATION.md`;
    - de agora em diante, números reais só em `data/editorial/`.
  - **06**: refazer a auditoria do B1 sobre o novo histórico: `git grep` em todos os commits,
    `git fsck` e `git rev-list --objects --all`.
  - **07**: o `.gitignore` ganhou uma linha (`manual_corrections.csv`). O push privado depende da
    reauditoria do 06.

## Evidência da reescrita do histórico (Agente 00, 2026-10-27)

- **Novo histórico**: o commit raiz `5bd17d0` ("Commit inicial do brasileirao-predictions (histórico
  reescrito, decisão B1)"), mais este commit de evidência. Os commits 682e1fb e 3f935bf foram
  apagados, sem remote e sem push.
- **Evidência**:
  - Depois de `git reflog expire --expire=now --all` e `git gc --prune=now --aggressive`:
    - `git rev-list --all` lista só `5bd17d0`;
    - `git cat-file -t 682e1fb` e `git cat-file -t 3f935bf` respondem "Not a valid object name";
    - `git fsck --unreachable --no-reflogs` não lista nada;
    - `git rev-list --objects --all` e `git cat-file --batch-all-objects` contam o mesmo número
      de objetos (272), ou seja, não sobrou objeto fora do histórico;
    - os blobs antigos dos 7 arquivos limpos não existem mais no repositório.
  - A varredura com `git grep` em todos os commits não encontra nenhum desses padrões:
    - clube real seguido de placar, %, pontos ou p.p.;
    - os valores retirados;
    - `bds-<n>`.
  - pytest num clone limpo (PYTHONPATH e BRASILEIRAO_ROOT apontando para o clone; o import vem do
    clone): **158 passed**.
  - pytest na árvore de trabalho, com o trabalho do 01 ainda fora do git: 173 passed em 4 de 5
    execuções. A primeira teve 1 falha intermitente, que não se repetiu e não foi identificada. O
    06 deve acompanhar.
  - `sha256sum -c`: os 6 arquivos não versionados ou alterados do 01 estão idênticos ao backup
    feito antes da reescrita.
- **Backup do histórico antigo**: fica só fora do repositório, no scratchpad da sessão do 00, e
  contém os números reais. Não deve ser publicado. Apagar depois da reauditoria do 06.

## Reauditoria B1 do Agente 06 (2026-10-27)

Registrado pelo orquestrador a partir do relatório do 06, que auditou sem editar arquivos.

- **Parecer**:
  - Push de `main` para um repositório GitHub **privado**: **aprovado**.
  - **B1 resolvido**.
  - Tornar **público**: ainda **reprovado**. Faltam B2 (escudos), B3 (workflow), um LICENSE na raiz
    e C1 (licença da fonte de 2024+).
- **Evidência**:
  - O único ref é `refs/heads/main` (3c368c0). `fsck --unreachable` não lista nada.
  - Há 277 objetos, iguais ao que `rev-list --objects --all` alcança.
  - Os commits 682e1fb e 3f935bf não existem mais.
  - A varredura de todos os blobs e mensagens deu 62 ocorrências, todas aceitáveis: falsos
    positivos, agregados sem clube e nomes sem resultado.
  - pytest: 158 passed num clone limpo; 173 passed três vezes na árvore de trabalho.
- **Achados de baixa severidade**:
  1. **Edição sem handoff em `round_review.py` e `test_round_review.py`** (domínio do 02). Ela
     explica a falha intermitente: houve uma corrida com o teste antigo. O 02 precisa registrar o
     handoff.
  2. **`model.md:79-81`**: "confronto direto" permite deduzir qual foi o jogo, mas não o placar. A
     remoção é opcional (02).
  3. **`CONTENT_GUIDELINES.md:17,19` e `BRAND_EXPLORATION.md:195`**: faltam a marca "ilustrativo" e
     a troca de um clube real por "Clube X". Retoque opcional (08).
  4. **`catalog.md:27-29`**, só na árvore de trabalho: tem placares reais. O 01 limpa antes de
     commitar.
- **Próximos responsáveis**:
  - 07: push privado.
  - 02: handoff de `round_review`.
  - 01: `catalog.md`, `corrections` com exemplo sintético e B2.
  - 05: marcador e atribuição dos escudos.
  - Dono do produto: LICENSE e C1.

## Agente 08: marcador neutro para os 3 escudos não livres (2026-10-27)

- **Decisão**: D-028 (conceito, aprovado pelo dono do produto no chat em 2026-10-27). Red Bull
  Bragantino, Corinthians e Vasco passam a usar um círculo com sigla e cores do clube; os outros 17
  mantêm os escudos do Commons. D-029 é a especificação, proposta do Agente 08 e aberta à revisão do
  dono (Q17). A especificação completa está em `docs/brand/BRAND_DECISIONS.md`, seção "Marcador
  neutro dos clubes sem escudo livre".
- **O que mudou**: só `docs/brand/BRAND_DECISIONS.md` e esta seção. Nenhum arquivo de `apps/web/`
  foi editado.
- **Evidência**: as siglas RBB, COR e VAS são o `short_name` de `data/reference/clubs.csv` e
  aparecem assim no export `apps/web/data/api/seasons/2026/rounds.json`. Os contrastes foram
  calculados pela luminância relativa WCAG: texto 5,88:1 (RBB) e 21:1 (COR, VAS); fio do círculo
  4,63:1 no tema claro e 5,57:1 no escuro. Não houve renderização nem medição em tela.
- **Próximo responsável**:
  - **05**:
    - trocar as 3 entradas do `manifest.json` para `badge`;
    - fazer `crest()` em `rounds.js` aceitar `badge` (inicial abaixo de 32 px, sigla a partir de 32 px,
      `aria-hidden`, validação de hex);
    - adicionar `.crest-badge` em `rounds.css`;
    - colocar a frase de atribuição no rodapé e a seção "Escudos" em "Como calculamos";
    - conferir em 375 e 1280 px, nos temas claro e escuro, nos tamanhos 16, 18, 20 e 48 px.
  - **01**: remover `bragantino.png`, `corinthians.png` e `vasco.svg` de `apps/web/assets/crests/`;
    atualizar as 3 entradas de `data/reference/crests_provenance.json` (marcador próprio, sem fonte
    externa; corrigir o `license_status` conforme B2).
  - **06**: conferir o contraste na tela, o `aria-hidden`, o modo `forced-colors` e a ausência dos 3
    arquivos no build (B2/C3).
  - **Dono do produto**: revisar as siglas e as cores (Q17).

## Escudos não livres substituídos por marcador neutro — B2, parte do 01 (2026-10-27)

- **O que mudou**: em `data/reference/crests_provenance.json`, `bragantino`, `corinthians` e
  `vasco` agora têm `license_status: "nao_livre"`, `used: false` e
  `replacement: "marcador_neutro"`. O `license_status_override` ("livre", de 2026-10-26) saiu e foi
  para `license_status_history`, junto com a nova decisão do dono do produto (2026-10-27): os três
  escudos não serão usados. URL, licença original e SHA-256 continuam no arquivo. O campo
  `research_2026_10_27` registra a pesquisa: o Commons não tem versão livre do escudo atual de
  nenhum dos três. Corinthians e Vasco já tiveram arquivos apagados de lá por copyright. Do
  Bragantino só existe a versão 1995–2020, de antes da Red Bull, com PD-textlogo em revisão. O
  escudo do Vasco de 1920 (domínio público por idade) foi avaliado e descartado por uniformidade.
- **Evidência**: `python -m json.tool data/reference/crests_provenance.json` deu OK. O pytest está
  na resposta do 01 ao orquestrador. Nenhum código em `src/`, `tests/`, `apps/` ou `.github/` lê
  `crests_provenance.json`.
- **Premissas e limitações**: os arquivos locais `apps/web/assets/crests/bragantino.png`,
  `corinthians.png` e `vasco.svg` foram mantidos (são ignorados pelo git). O
  `apps/web/assets/crests/manifest.json` (do 05) ainda pode apontar para eles. As menções ao
  override em `docs/architecture/deploy.md` e no ADR-0007 (do 00/07) estão desatualizadas.
- **Próximo responsável**: **08** decide a forma do marcador (sigla e cores). **05** tira as
  entradas dos três do manifest da web e implementa o marcador. **00/07** atualizam
  `deploy.md` e o ADR-0007. **06** revalida o B2.

## Agente 05: marcador neutro e atribuição dos escudos (D-028, D-029) (2026-10-27)

- **O que mudou** (só em `apps/web/`):
  - `assets/crests/manifest.json`: `bragantino`, `corinthians` e `vasco` passaram a usar `badge`
    (RBB `#C8102E`/`#FFFFFF`, COR `#FFFFFF`/`#000000`, VAS `#000000`/`#FFFFFF`), sem `file`;
  - `assets/rounds.js`: `crest()` lê `file`, depois `badge` e só então cai no comportamento sem
    entrada. Valida `bg`/`fg` com `/^#[0-9A-Fa-f]{6}$/` e `label` com `/^[A-Z]{2,4}$/`, passa o texto
    por `escapeHtml` e usa `aria-hidden="true"`. Abaixo de 32 px mostra a inicial (corpo
    `round(size × 0.6)`); a partir de 32 px mostra a sigla (corpo `round(size × 0.32)`);
  - `assets/rounds.css`: `.crest-badge` conforme D-029;
  - `index.html`: linha de atribuição dos escudos no rodapé. O texto de licença dos dados (C2)
    continua igual;
  - `assets/app.js`: seção "Escudos" em "Como calculamos".
- **Evidência**: com o site servido por `http.server` e aberto no Chrome headless, o DOM mostra os
  marcadores com 16 px/10 px (chips da rodada 3), 18 px/11 px (lista de times e comparativo),
  20 px/12 px (tabelas) e 48 px/15 px ("VAS" no título da página do time). Há capturas a 1280 px
  nos temas claro e escuro. O servidor não recebeu nenhum pedido dos 3 arquivos antigos e não
  houve 404 de escudo (os únicos 404 foram as rotas `/api/...`, que são o fallback esperado do
  site estático). O console ficou sem mensagens: a captura do console foi testada antes com uma
  mensagem de prova. `grep` em `apps/` e `src/` não acha referência a `bragantino.png`,
  `corinthians.png` ou `vasco.svg`. `pytest`: 173 passaram.
- **Limitações**: não houve conferência visual real em 375 px, porque o Chrome headless no
  Windows não renderiza viewport menor que cerca de 500 px. O marcador tem tamanho fixo e
  `flex: none`, então a largura da página não deveria mudar sua aparência, mas isso não foi
  confirmado. O modo `forced-colors` não foi testado. Os 3 arquivos continuam em
  `apps/web/assets/crests/`, ignorados pelo git e sem uso. Se o build copiar a pasta inteira,
  eles vão junto, e a remoção cabe ao 01 (B2/C3).
- **Próximo responsável**:
  - **06**: conferir o contraste na tela, o `forced-colors`, 375 px num navegador real e a
    ausência dos 3 arquivos no build;
  - **01**: remover os arquivos locais;
  - **Dono do produto**: Q17 (siglas e cores).

## Parecer do Agente 06: marcador neutro, B2 (2026-10-27)

Registrado pelo orquestrador a partir do relatório do 06, que verificou sem editar arquivos.

- **Parecer**: B2 **resolvido com condições**.
- **Evidência**:
  - **`crest()`**: valida cor e sigla, passa o texto por `escapeHtml` e segue a ordem
    `file` → `badge` → fallback.
  - **Contraste**: os valores recalculados conferem com a D-029. O fio do círculo tem razão de pelo
    menos 4,63 com o fundo.
  - **`forced-colors`**: o marcador continua visível, sem precisar de CSS próprio.
  - **Escudos**: nenhum dos 3 está em arquivo versionado ou no histórico, e o `manifest.json` só tem
    `badge` para eles.
  - **Atribuição**: os textos conferem com `crests_provenance.json`.
  - **pytest**: 173 passed.
  - **Visual em 375 px**: conferido pelo orquestrador no navegador, nos temas claro e escuro, sem
    rolagem horizontal.
- **Ressalvas tratadas**:
  - R1: criado o `.dockerignore`, que exclui os 3 arquivos locais e os dados não versionáveis.
  - Notas de resolução no ADR-0007 e no `deploy.md`.
- **Pendências**:
  - **01**: `catalog.md:14` ainda descreve o override antigo. É uma alteração não commitada, que
    também precisa ter os placares retirados.
  - **06**: teste `test_crests_manifest.py`.
  - **Dono do produto**: Q17 (siglas e cores).

## Agente 08: mosaico, cabeçalho de edição e anotações (D-030, 2026-10-27)

- **O que mudou**: `apps/web/assets/app.js` (`titleMosaic`/`allocateDots`; `renderReferenceBar` como
  cabeçalho de edição com `editionRound`; `lineChart` com rótulos diretos e anotações via
  `chartAnnotations`/`openMetric`; `signedPercent` corrige "-0%" em ataque e defesa) e
  `apps/web/assets/styles.css` (seções de edição, mosaico e anotações). Na home com mosaico, a lista
  de chance de título sai e o risco de queda vira seção própria.
- **Evidência**: capturas em 1280 px (home, dois clubes) e 520 px no tema escuro, com o Edge em modo
  headless; navegador do app em 375 px: 6 rotas sem rolagem horizontal, mosaico com exatamente 1.000
  pontos, anotações presentes nas páginas de clube, console sem erros além dos 404 esperados de
  `/api/*` no servidor estático. Valores exibidos no registro local (decisão B1).
- **Premissas**: o mosaico representa a probabilidade agregada do snapshot (pontos alocados pelo maior
  resto), não sorteios individuais; a legenda diz isso. As anotações são fatos do histórico e não
  passam pelo fluxo editorial, porque não atribuem causa.
- **Observação para o 00/02**: rótulos "100%" aparecem quando o desfecho ocorre em todas as
  simulações, o que não é certeza matemática; avaliar exibir ">99,9%" nesses casos.

## Agente 01: proposta de fonte licenciada para C1 (2026-10-27)

- **O que mudou**: criado `docs/data-sources/c1-fonte-licenciada.md`, com status **proposta**.
  Nenhum código, dado ou manifesto foi alterado e nenhuma conta foi criada.
- **Proposta**:
  - Histórico de 2003 a 2025: dataset de Adão Duque, versão 18 no Kaggle, sob GPL 2 declarada.
  - Temporada corrente: football-data.org no plano gratuito, competição BSA, com a atribuição
    obrigatória da cláusula 7.1.
  - Wikipédia (pt), `brasileirao-dataset` e CBF entram só como conferência local ou manual.
- **Evidência**: páginas oficiais acessadas em 2026-10-27 (URLs e trechos na proposta):
  - `/coverage` e `/pricing` do football-data.org: "Serie A" do Brasil entre as 12 competições
    gratuitas, com limite de 10 chamadas por minuto.
  - T&C do football-data.org, cláusulas 2.3, 6.1, 7.1 e 9.1.
  - Metadados do Kaggle: `licenseNameNullable: "GPL 2"` e versão 18, cobrindo 2003 a 2025.
  - API do GitHub: o repositório do Adão Duque não tem `license`, e o openfootball tem CC0.
  - O openfootball Brasil recente vem do football-data.org (README `yorobot/fbup` e gem
    `footballdata-api` com `bin/fbdat`). Ele está 5 semanas atrasado: 277 placares em 2026.
  - Wikidata: 0 partidas da Série A, segundo consulta SPARQL.
- **Premissas e limitações**:
  - Não há parecer jurídico.
  - Ainda não se sabe quais temporadas o plano gratuito devolve.
  - Os termos da CBF não foram lidos (falha de TLS) e os da API-Football também não (403).
  - O `FootballDataOrgSource` atual tira a data em UTC. Os jogos das 21h30 de Brasília caem no dia
    seguinte, e isso precisa ser corrigido antes do uso.
- **Próximos responsáveis**:
  - **Dono do produto**: os itens 1 a 7 da seção 6 da proposta. O principal é criar a conta, gerar o
    token, guardá-lo em segredo e rodar a sondagem das temporadas.
  - **00**: aprovar a combinação e o novo valor de `LicenseStatus`.
  - **00 e 07**: decidir a persistência do SQLite, já que o asset público redistribuiria placares.
  - **01**: implementar o adaptador e a ingestão por precedência depois da aprovação.
  - **02 e 06**: recalcular ratings, treino e backtest sem os dados do Sofascore.
  - **08 e 05**: texto de atribuição (C2).

### Handoff do Agente 01: consulta de teste do football-data.org (2026-10-27)

- **O que mudou**: `docs/data-sources/c1-fonte-licenciada.md` ganhou a seção 8, "Consulta de teste
  (2026-10-27)", e os itens de temporadas e atraso saíram de "a verificar". Nenhum código, dado,
  manifesto ou `clubs.csv` foi alterado. As respostas brutas ficaram fora do repositório.
- **Evidência**: 4 chamadas locais autorizadas pelo dono, todas com HTTP 200 e sem erro:
  - `/v4/competitions/BSA`: temporada corrente de 2026-01-28 a 2026-12-02, rodada atual 33.
  - BSA 2024: 380 partidas, todas `FINISHED`.
  - BSA 2025: 380 partidas, todas `FINISHED`.
  - BSA 2026: 380 partidas (319 `FINISHED`, 40 `SCHEDULED`, 20 `TIMED`, 1 `POSTPONED`).
  - Todo `FINISHED` tem placar `fullTime`. O limite ficou entre 9 e 7 requisições livres por minuto.
- **Comparação local** com `data/silver/matches.csv`: os 1.140 pares casam e há 0 divergências de
  placar em 1.079 jogos encerrados. O atraso em 2026 é de horas: nenhum jogo disputado está faltando.
- **Problema de qualidade aberto (01, 06)**: em 207 jogos de 2024 a 2026, a fonte atual
  (`brasileirao-dataset`/Sofascore) grava a data do dia UTC, um dia depois da data de Brasília (71,
  67 e 69 por temporada). A validação temporal desses jogos fica deslocada em um dia. O
  `FootballDataOrgSource` atual repetiria o erro (usa a data UTC), então a conversão para
  `America/Sao_Paulo` passa a ser obrigatória.
- **Premissas e limitações**:
  - Não foram consultadas temporadas anteriores a 2024.
  - O atraso foi medido num único ponto.
  - Os 27 nomes de clubes da API não têm alias no `clubs.csv`. A lista está na seção 8.4 e entra
    junto com o adaptador.
- **Próximos responsáveis**:
  - **00**: aprovar a combinação (Adão Duque até 2025, football-data.org de 2026 em diante, e o
    football-data.org 2024–2025 como conferência local), além do valor de `LicenseStatus`.
  - **01**: depois da aprovação, implementar o adaptador com a correção de fuso e os aliases.
  - **06**: avaliar o impacto do deslocamento de data de 2024 a 2026 no backtest.

## Decisão do Agente 00: fontes licenciadas para C1, ADR-0008 (2026-10-27)

- **O que mudou** (só documentação; nenhum código, dado ou contrato foi alterado ainda):
  - `docs/decisions/ADR-0008-fontes-licenciadas-c1.md` criado, com status **aceito com condições**;
  - adendos nos ADR-0002 e ADR-0007 (C1, itens 4 e 8);
  - `docs/project/risks.md`: R1 e R12 atualizados, R13 a R16 novos.
- **Decisão 1, combinação aprovada com ajustes:**
  - publicação: Adão Duque, versão 18 no Kaggle, para 2003–2025, e football-data.org para 2026+;
  - conferência local: football-data.org 2024–2025 e `brasileirao-dataset`;
  - conferência manual: CBF;
  - sem fallback silencioso, e fonte de conferência nunca entra no gold;
  - riscos 9.1, 11.1, 6.1 (segredo do Actions aceito), 2.3 (`github.io` aceito como domínio único) e
    GPL-2 com coleta "de páginas do Google": avaliados com condições no ADR.
- **Decisão 2, contrato:**
  - `LicenseStatus.LICENSED_WITH_ATTRIBUTION = "licensed_with_attribution"`;
  - `AllowedUse` fechado: `research_local`, `prototype_local`, `public_display_derived`,
    `redistribution`;
  - `SourceManifest` ganha `license_name`, `terms_url`, `terms_checked_at` e `attribution`, com
    validador;
  - `DataInfo.sources` no snapshot;
  - gate com as regras G1 a G5.
- **Decisão 3, persistência:**
  - SQLite e Adão Duque v18 vão para um repositório **privado** de estado, gratuito;
  - o asset público `snapshots-db` foi revogado;
  - nenhum SQLite, raw ou silver em artefato público;
  - a história publicada recomeça com fontes licenciadas, com reconstrução identificada como tal.
- **Evidência:**
  - leitura da proposta do 01 (seções 1 a 8) e do `catalog.md` versionado (`git show HEAD:`);
  - leitura de `contracts.py` (hoje com 4 valores de `LicenseStatus` e `allowed_uses` como strings
    livres) e de `sources.py` (o `FootballDataOrgSource` tira `.date()` de `utcDate` em UTC);
  - leitura de `storage/schema.py` (`MatchPrediction` e `MatchImpactInfo` têm placares) e de
    `snapshots.py` (o payload é o snapshot inteiro);
  - `update-predictions.yml` envia `snapshots.sqlite` como artefato;
  - o export atual só tem a temporada 2026 e as métricas.
- **Premissas e limitações:**
  - não é parecer jurídico;
  - "a verificar": validade máxima da credencial do repositório privado e visibilidade dos artefatos
    do Actions em repositório público (07);
  - a premissa de que a data do Adão Duque está no fuso de Brasília será testada no relatório de
    conferência.
- **Dependência em aberto:** a avaliação do 06 sobre o deslocamento de data de 2024–2026, já em
  andamento. Não bloqueia o 01, mas é entrada obrigatória da revalidação do backtest, e o
  `model_version` novo só é aceito depois dela.
- **Próximos responsáveis**, na ordem do plano do ADR-0008:
  1. **01**, passos 1 a 9:
     - contrato;
     - fuso `America/Sao_Paulo` no `FootballDataOrgSource`;
     - `AdaoDuqueSource` com fixture sintética;
     - 27 aliases e os do Adão Duque;
     - precedência por temporada em `config.py` (autorizada só essa constante);
     - `sources.json`;
     - correções manuais migradas;
     - relatório de conferência;
     - catálogo e testes.
     - Fora do escopo: corrigir a data do `BrasileiraoDatasetSource`, cartões de 2026, Wikipédia
       automatizada e redistribuição.
  2. **00 e 04:** `DataInfo.sources`, `schema_version` e `load_inputs` com várias fontes.
  3. **02:** recalcular sem o Sofascore, com `model_version` e `data_version` novos, revisão por
     rodada e reconstrução da história de 2026.
  4. **06:** revalidar o backtest (`validation.md`), a validação temporal e as regras G1 a G5.
  5. **07:** repositório privado de estado, segredos, gate e remoção do SQLite do artefato.
  6. **08 e 05:** atribuição (C2).
  7. **03:** confirmar o desempate por cartões com cobertura zero em 2026.
- **Pendências do dono do produto:**
  - baixar o Kaggle v18 (exige conta);
  - aceitar os riscos por escrito;
  - criar o repositório privado, a credencial e os segredos;
  - aprovar a atribuição;
  - ler os termos da CBF e definir quem faz a conferência;
  - confirmar o domínio único;
  - aceitar o recomeço ou a reconstrução da história publicada;
  - opcional: escrever ao autor do dataset.
- **Estado de C1:** em andamento. A publicação continua bloqueada.

### Handoff do Agente 06: impacto do deslocamento de data UTC (2026-10-27)

- **Parecer: aprovado com ressalvas. Não bloqueia a migração de fontes.** Não há vazamento e o
  efeito nas métricas é desprezível. A correção de fuso no adaptador é critério de aceite.
- **O que mudou**: `docs/methodology/validation.md` ganhou a seção "Deslocamento de data UTC na
  fonte atual (2026-10-27)", e a contagem de testes foi atualizada. Código, dados e relatórios gold
  não foram tocados. A reexecução com datas corrigidas ficou fora do repositório.
- **Evidência**:
  - Na gold há 208 linhas com data +1 dia: 186 encerradas (71, 67 e 48) e 22 agendadas de 2026.
  - Nenhuma linha tem data anterior à real. Como todos os cortes usam `<=`, isso só pode excluir
    jogos, nunca vazar.
  - Backtest completo com datas originais e corrigidas, mesmas sementes. A versão original reproduz
    os registros gold.
  - Validação, hiperparâmetros e escolhas do modelo ficaram idênticos.
  - Teste de partidas: log loss 1,02133 → 1,02134. Temporada: log loss de posição 2,2144 → 2,2143
    e cobertura de 90% igual. Os registros de 2024–2025 só mostram ruído de Monte Carlo.
  - Checkpoints: 2 dos 6 de 2024–2025 têm data de referência +1 dia e 0 têm jogo do lado errado.
  - Review-rounds: 5, 4 e 3 visões (2024, 2025 e 2026) deixam de fora um jogo já disputado até a
    data do rótulo. Só 2 visões de 2024 mudam de conjunto de jogos depois da correção.
  - Probability-history: 9, 6 e 6 pontos mudam de data.
  - `pytest`: 204 passaram.
- **Premissas e limitações**:
  - A referência de data correta é o football-data.org convertido para Brasília (seção 8 da proposta
    C1).
  - Não foi verificado se 2003–2023 tem o mesmo problema.
- **Próximos responsáveis**:
  - **01**: no `FootballDataOrgSource` (`data_pipeline/sources.py:218`), converter `utcDate` para
    `America/Sao_Paulo` e incluir os testes de regressão listados em `validation.md`. São eles:
    21h30 fica no mesmo dia, horário de verão histórico, nenhum jogo `finished` com data posterior
    à coleta em Brasília e zero divergências de data na conferência de 2024–2025. Também verificar
    o problema em 2003–2023, se houver fonte com horário.
  - **02/04**: depois da migração, regenerar review-rounds, probability-history e snapshots de
    2024–2026.
  - **06**: reexecutar o backtest e validar quando a nova base estiver ingerida.

## Agente 02: corrida pela Sul-Americana, 100 mil simulações e dificuldade da tabela (2026-10-27)

- **O que mudou** (nada commitado):
  - `simulation/summary.py`: vagas continentais agregadas por arranjo de posições dos clubes citados
    nos cenários externos (resultado idêntico ao cálculo direto, ~9× mais rápido); novas
    `sudamericana_all_scenarios`/`sudamericana_any_scenario` e `sudamericana_race` (classificação
    da corrida sem pesos para os cenários). Método: `docs/methodology/sudamericana-race.md`.
  - `prediction/schedule.py` (novo): pontos esperados nos jogos restantes (total, casa, fora) e
    índice de dificuldade 0–100 (50 = tabela média da liga), com ranking e força do adversário por
    jogo. Método e escala: `docs/methodology/schedule-difficulty.md`.
  - `ratings/history.py`: `match_features` e `average_rating` extraídos (sem mudança de resultado).
  - `simulation/engine.py`: sorteio de placares em blocos de 100 mil jogos simulados; mesma semente,
    mesmo resultado (teste com blocos de 7 linhas).
  - `config.py` (Agente 00): `SimulationConfig.n_simulations = 100_000`, novo
    `round_review_simulations = 20_000`, `SNAPSHOT_SCHEMA_VERSION = "1.1"`. `cli.py` (Agente 00): os
    padrões de `simulate` e `review-rounds` passam a vir de `SimulationConfig`.
  - `pipeline.py` (Agente 00): `build_snapshot` publica `teams[].sudamericana_race`,
    `teams[].schedule` e `schedule_scale`.
  - `storage/schema.py` (**handoff ao Agente 04**): novos `SudamericanaRace`, `ScheduleInfo`,
    `ScheduleMatchInfo` e `ScheduleScaleInfo`; campos opcionais em `TeamPrediction` e
    `PredictionSnapshot`, então os snapshots antigos continuam válidos. A API (`apps/api`) não
    precisou mudar: devolve `TeamPrediction` inteiro.
  - `competition_rules/` (Agente 03) **não foi alterado**. A agregação supõe que `allocate_slots`
    só distingue os clubes citados nos cenários; se isso mudar, ajustar `_external_clubs`.
  - Testes novos: `tests/unit/test_schedule.py`, `tests/unit/test_sudamericana_race.py`,
    `tests/integration/test_snapshot_schedule_and_race.py` (dados sintéticos).
- **Evidência**:
  - `.venv/Scripts/python.exe -m pytest -q`: 204 passed; `-m ruff check .`: ok;
    `-m ruff format --check .`: ok; `-m mypy src`: sem erros em 43 arquivos.
  - Equivalência da agregação na base real, 10 mil simulações: diferença máxima 0 em grupos,
    preliminar e Sul-Americana, nos 32 cenários.
  - Snapshot de 2026-10-26 regenerado com `simulate --season 2026 --reference-date 2026-10-26`
    (100 mil, semente 2026, schema 1.1, mesma versão de dados) e reexportado com
    `export-web --season 2026`. `build_snapshot`: ~4 s com 10 mil e ~20 s com 100 mil; pico de
    working set de ~380 MiB para ~700 MiB; `simulate` completo em ~22 s.
  - `predictions.json`: de ~293 kB para ~348 kB (gzip: ~24 kB para ~38 kB). O aumento vem dos campos
    novos, não do número de simulações.
- **Decisões**:
  - Snapshots históricos não foram reprocessados (seguem com 2 mil e 10 mil); o `n_simulations` de
    cada ponto está no `probability-history.json`.
  - `review-rounds` fica em 20 mil (o valor da revisão publicada). Com 10 mil a revisão completa levou
    ~25 min; com 100 mil seriam ~4 h estimadas.
- **Premissas e limitações**:
  - O centro da faixa (`midpoint`) só ordena; não é probabilidade e não deve ser exibido como chance.
  - A dificuldade usa ratings congelados na data e uma escala recalculada a cada data; o ranking é a
    leitura mais estável entre datas.
  - O jogo adiado sem data entra na tabela restante e na simulação como os demais.
- **Próximos responsáveis**:
  - **04**: revisar e aceitar as mudanças em `storage/schema.py`.
  - **06**: auditar os testes novos e a equivalência da agregação; avaliar se o índice de dificuldade
    precisa de registro em `validation.md` (não é modelo preditivo novo).
  - **08/05**: exibir a classificação da Sul-Americana com a faixa `min`–`max` e ordenar por
    `sudamericana_race.rank`, e a tabela restante por `schedule`. Campos em
    `docs/methodology/sudamericana-race.md` e `docs/methodology/schedule-difficulty.md`.
  - **00**: ciente das mudanças em `config.py`, `cli.py` e `pipeline.py`.

## Agente 08: revisão do front, home por disputa, tabela por visões e dificuldade (D-031, 2026-10-27)

- **O que mudou**: `apps/web/assets/app.js`, `apps/web/assets/styles.css`, `apps/web/index.html` (cor de tema e
  texto "100 mil simulações"), `docs/architecture/frontend.md`, `docs/brand/BRAND_DECISIONS.md` (D-031) e
  `docs/brand/BRAND_GUIDELINES.md`. Fundo da interface `#FAFAF7`; home `#/inicio/{titulo,g4,rebaixamento}`
  com destaque automático (disputa que mais mudou ou mais aberta); mosaico por vagas; escudos em todas as
  páginas (`crest()` próprio em `app.js`, mesma regra do marcador neutro); tabela `#/classificacao/{visão}`
  com colunas fixas e grupos Título, Libertadores, Sul-Americana (ordenada por `sudamericana_race.rank`),
  Rebaixamento, Força e Dificuldade (ordenada por `schedule.difficulty_rank`); grade e faixa de escudos em
  Clubes; seção "Dificuldade do que falta" na página do clube; jogo sem placar há mais de 7 dias da data de
  referência aparece como "adiado, data a definir". Consome os campos `schedule` e `sudamericana_race`
  entregues pelo Agente 02 (schema 1.1); `midpoint` não é exibido.
- **Evidência**: navegador do app em 1280 px e 375 px: 15 rotas sem rolagem horizontal e com conteúdo,
  console só com os 404 esperados de `/api/*` no servidor estático; contraste WCAG das cores de texto sobre
  `#FAFAF7` entre 4,8:1 e 16,8:1 (vermelho-sinal 4,4:1, só texto grande, como antes).
- **Premissas**: a regra "adiado" do front é provisória.
- **Próximo responsável**: Agente 01 deve marcar `postponed` na fonte/contrato para o jogo adiado (hoje
  `scheduled` com data antiga); Agente 06 deve auditar contraste do novo fundo e a leitura do índice de
  dificuldade; a aba Rodada a rodada (sessão parceira) ainda trata o adiado pela própria regra.

## Agente 01: migração de fontes do ADR-0008, passos 1 a 9 (2026-10-27) — implementado, ingestão real pendente

- **O que mudou** (nada commitado; só fixtures sintéticas, nenhuma chamada real à API, nenhum dado
  real versionado):
  - **Passo 1, contrato** (`contracts.py`): `LicenseStatus.LICENSED_WITH_ATTRIBUTION`; `AllowedUse`
    fechado; `SourceManifest` com `allowed_uses: list[AllowedUse]`, `license_name`, `terms_url`,
    `terms_checked_at`, `attribution` e validador da Decisão 2 (para `verified_open` e
    `licensed_with_attribution` exige nome, URL e data dos termos; para `licensed_with_attribution`,
    também a atribuição). Novos `most_restrictive_license` e `SourceManifest.allows_public_display`,
    para o passo 10. Manifestos antigos do `brasileirao_dataset` continuam válidos.
  - **Passo 2**, `data_pipeline/football_data_org.py` (novo; a classe saiu de `sources.py`):
    - data = `utcDate` → America/Sao_Paulo → `.date()`;
    - token só por `FOOTBALL_DATA_ORG_TOKEN`, com `repr` mascarado e fora de log e de mensagens;
    - ≥ 6 s entre chamadas e espera de `X-RequestCounter-Reset` em 429;
    - `IN_PLAY`, `PAUSED` e `LIVE` → `scheduled`; status desconhecido ou duração diferente de
      `REGULAR` falham;
    - `AWARDED` só com placar em `known_exceptions.csv`, senão `AwardedMatchError` antes de gravar;
    - payload bruto byte a byte em `data/raw/football_data_org/v4-<UTC>/matches_<temporada>.json`,
      mais `requests.json` (`retrieved_at` por requisição) e manifesto com SHA-256.
  - **Passo 3**, `data_pipeline/adaoduque.py` (novo):
    - lê `data/raw/adaoduque/v18/` (`campeonato-brasileiro-full.csv` e `-cartoes.csv`) e confere o
      SHA-256 contra `data/reference/source_pins.json` (novo, versionado, hashes ainda vazios);
    - falha com mensagem clara se faltam arquivos, hashes ou se o hash diverge;
    - `brasileirao pin-adaoduque` fixa os hashes, passo humano depois de conferir com o espelho;
    - data dd/mm/aaaa tratada como Brasília; temporada pelo ano, com 2020 indo até fevereiro de 2021;
    - sem placar → `scheduled`;
    - fixture sintética em `tests/fixtures/adaoduque_synthetic/`.
  - **Passo 4**: os 27 aliases da seção 8.4 em `data/reference/clubs.csv`. Os 45 nomes do formato
    Adão Duque (2003–2023) já resolviam. Os de 2024–2025 da v18 só se confirmam depois do download.
  - **Passo 5**:
    - `config.PUBLICATION_SOURCE_BY_SEASON`: só essa constante em `config.py`, autorizada pelo 00;
    - `data_pipeline/composition.py` (novo) monta a composição por temporada sem fallback e grava
      `data/silver/sources.json`;
    - G1 na ingestão: fonte sem `public_display_derived` falha;
    - partida `finished` com data posterior ao dia de coleta em Brasília falha;
    - `match_id` estável `<temporada>-<mandante>-<visitante>`, com sufixo `-r<rodada>` para par
      repetido (2009), documentado no catálogo; ele substitui `bds-<id>`;
    - `ingest_raw` mantém o manifesto se os hashes não mudaram (reingestão idêntica);
    - CLI: `ingest` é publicação por padrão. O `brasileirao_dataset` só roda com
      `--research-source brasileirao_dataset` e grava `sources.json` com `mode: research`.
  - **Passo 6**:
    - `corrections.py` grava a fonte-base na coluna `source`
      (`<fonte>+manual_correction@<evidência>:<data>`, G2);
    - correção redundante vai para o `changes.jsonl` (`manual_correction_redundant`);
    - `manual_corrections.example.csv` (sintético) versionado;
    - o `manual_corrections.csv` local (ignorado) foi migrado para os IDs estáveis
      `2026-coritiba-gremio` e `2026-flamengo-atletico-mg`. Elas ficam até a primeira ingestão
      real registrá-las como redundantes; depois o 01 as remove.
    - O trabalho não commitado anterior do 01 (`corrections.py`, `test_corrections.py`, `ingest.py`,
      `cli.py`) foi integrado.
  - **Passo 7**, `data_pipeline/conference.py` (novo) e `brasileirao conference`:
    - pares football-data.org × Adão Duque (2024–2025, tolerância 0) e Adão Duque ×
      `brasileirao_dataset` (2003–2023, ±1 dia);
    - detalhe em `data/silver/conference_report.json` e divergências no `changes.jsonl`;
    - só contagens na saída e no catálogo.
  - **Qualidade** (`validation.py`): erro `finished_after_reference`, pedido pelo 06;
    `load_awarded_results`; `known_exceptions.csv` ganhou as colunas `source_name`,
    `source_match_id`, `home_goals` e `away_goals` (vazias nas 4 linhas atuais). `validate` usa o
    dia de Brasília como referência padrão.
  - **Passo 8**:
    - `catalog.md` reescrito: linha do Adão Duque, papéis da Decisão 1, composição, `match_id`,
      conferência e política 6 (W.O.);
    - os placares reais da alteração não commitada saíram (B1);
    - a linha dos escudos reflete `nao_livre`, `used: false` e marcador neutro;
    - `c1-fonte-licenciada.md` marcada "aprovada com ajustes (ADR-0008)".
- **Evidência**:
  - `.venv/Scripts/python.exe -m pytest -q`: **374 passed** (eram 204). São 170 testes novos:
    `test_license_contract.py` 15, `test_football_data_org.py` 28, `test_adaoduque.py` 16,
    `test_club_aliases.py` 78, `test_composition.py` 19, `test_conference.py` 8, mais 4 em
    `test_data_pipeline.py` e 2 em `test_corrections.py`.
  - Os testes de regressão do 06 estão cobertos:
    - `2026-10-27T00:30Z` → 26/10;
    - `2026-10-26T23:00Z` → 26/10;
    - `2018-11-11T02:30Z` → 11/11 (UTC−2);
    - partida `finished` posterior à coleta ou à referência falha.
  - `ruff check src apps tests scripts`: ok. `ruff format --check`: ok. `mypy`: sem erros em 48
    arquivos. Antes da mudança, os três já estavam verdes (204 passed), então não há erro
    preexistente a separar.
  - `brasileirao ingest` sem os arquivos da v18 sai com a mensagem de arquivos ausentes, e
    `data/silver` não muda. `brasileirao conference` sai com "nenhum par de fontes disponível".
  - Caminho de pesquisa rodado numa cópia em scratchpad, fora de `data/` do projeto:
    - 9.545 partidas de 2003 a 2026 com `match_id` único;
    - só os 2 jogos de 2009 recebem sufixo (`-r12` e `-r31`);
    - `quality_report` sem erros, com 1 aviso de 2026 como antes;
    - segunda escrita byte a byte idêntica.
- **Decisões onde o ADR deixava margem**:
  - hashes da v18 fixados em `data/reference/source_pins.json` (versionado; hashes não são dados);
  - bronze do Adão Duque copiado para `data/raw/adaoduque_kaggle/v18/`, com a pasta de entrada do
    dono separada;
  - `retrieved_at` do Adão Duque = maior mtime dos arquivos baixados;
  - football-data.org 2024–2025 baixado no mesmo `--fetch`, 3 chamadas, para a conferência;
  - atribuição do Adão Duque provisória até o C2;
  - status desconhecido e duração diferente de `REGULAR` falham, em vez de virar `scheduled`;
  - colunas novas em `known_exceptions.csv` para o placar de W.O.
- **Premissas e limitações**:
  - Nomes dos arquivos da v18 supostos iguais aos do espelho do GitHub (conferido em 2026-10-27).
  - `data/raw/adaoduque/v18/` vazio; contagens reais por temporada e fonte e a conferência
    **pendentes** (passo 9, parte real).
  - `pipeline.load_inputs` ainda lê só o manifesto do `brasileirao_dataset` (passo 10, 00/04).
    `DataInfo.sources`, workflow e `storage/schema.py` não foram tocados.
  - `zoneinfo` no Windows depende do pacote `tzdata` (instalado no `.venv`, 2026.5, mas não
    declarado no `pyproject.toml`). No Linux do CI usa a base do sistema.
  - Alterações não commitadas de outro agente, **não tocadas**: `src/brasileirao/simulation/round_review.py`
    e `tests/unit/test_round_review.py` (domínio do 02, sem handoff registrado). O `cli.py` também
    tem as mudanças do 00/02 em `simulate` e `review-rounds`, preservadas.
  - Pedido do 08 (jogo adiado como `postponed`): o football-data.org já devolve `POSTPONED`, então
    resolve com a migração. O `brasileirao_dataset` não distingue adiado.
- **Próximos responsáveis**:
  - **Dono do produto**:
    - baixar a v18 do Kaggle para `data/raw/adaoduque/v18/`;
    - rodar `brasileirao pin-adaoduque`, conferir os hashes contra o espelho e versionar
      `source_pins.json`;
    - depois rodar `brasileirao ingest --fetch` com o token no `.env`.
  - **01**:
    - rodar a ingestão real e `brasileirao conference`;
    - registrar no catálogo as contagens por temporada e fonte e as contagens da conferência;
    - remover as 2 correções redundantes;
    - confirmar os nomes de 2024–2025 da v18.
  - **00/04**: passo 10 (`DataInfo.sources`, `load_inputs` lendo `data/silver/sources.json`,
    `data_version` composto). Avaliar se `tzdata` entra no `pyproject.toml` (00/07).
  - **02**: o `match_id` mudou de formato; snapshots e revisão por rodada precisam ser regerados
    (passo 11).
  - **06**: auditar contrato, fuso, G1/G2 na ingestão e os testes novos; a conferência real entra no
    passo 12.


## Parecer do Agente 06: entrega do 01, passos 1–9 do ADR-0008 (2026-10-27)

Registrado pelo orquestrador a partir do relatório do 06, que auditou sem editar arquivos.

- **Parecer**: **aprovado com condições** para commit e push no repositório privado.
- **Evidência**:
  - **Checagens**: pytest com 374 passed; `ruff check` e `ruff format --check` sem erros; mypy sem
    erros em 48 arquivos.
  - **Regressão numa cópia**: o pipeline atual com o gold antigo continua funcionando. O `ingest` de
    publicação sem a v18 falha sem gravar nada. O `ingest --research-source brasileirao_dataset` é
    idempotente, e `simulate` e `export-web` funcionam com os IDs novos.
  - **`.gitignore`**: cobre os dados brutos e derivados das novas fontes.
  - **Arquivos versionados**: nenhum placar real nem ID da fonte.
  - **Fixtures**: marcadas `synthetic`.
  - **Token**: só no header, e o `repr` aparece mascarado.
- **Condições**:
  1. O commit leva só o escopo do 01. Ficam fora `round_review.py`, `test_round_review.py`,
     `.claude/launch.json`, `apps/web/assets/app.js` e `apps/web/assets/styles.css`, que são
     alterações paralelas sem handoff.
  2. Não rodar `simulate` nem `export-web` sobre a ingestão nova antes do passo 10 (00/04). O
     `DataInfo` ainda aponta para o `brasileirao_dataset`.
  3. Não disparar o `update-predictions.yml` antes do passo 13 (07).
- **Não bloqueantes**:
  - **N1, 00/07**: declarar `tzdata` nas dependências.
  - **N2, 01**: `validate --reference-date` com data passada agora dá erro em jogos reais.
  - **N3, 01**: o `changes.jsonl` acumula entradas repetidas a cada ingestão.
  - **N4, 01**: testes fracos (log com `extra`; teste de correção que passa sem verificar no CI).
  - **N5, 01**: `SourceManifest` sem `frozen`.
  - **N6, 01**: `compose` não confere o nome do manifesto.
  - **N7, 01**: `retrieved_at` do Adão Duque vem do mtime dos arquivos.
  - **N8, 07**: o gate deve rejeitar `sources.json` com `mode` diferente de `publication`.
  - **N9, 02**: o `match_id` novo muda a ordem dos sorteios; exige `data_version` e `model_version`
    novos.
  - **N10, 07**: passar `--season` explicitamente no workflow.
  - **N11, 00**: confirmar a menção a IDs de confrontos, sem placar, neste arquivo.


## Handoff do Agente 01: primeira ingestão real de publicação (2026-10-27)

- **O que mudou**:
  - Ingestão de publicação executada com a v18 do Adão Duque (baixada pelo orquestrador a pedido do
    dono) e o football-data.org (3 chamadas, 2024–2026, ≥ 6 s entre elas). Antes de gravar, a silver
    e o gold anteriores (pesquisa, `brasileirao_dataset`) foram copiados para fora do repositório.
  - `data/silver/` e `data/gold/matches_model.csv` (não versionados) agora vêm da composição do
    ADR-0008 (`sources.json` com `mode: publication`). `quality_report.json` regerado.
  - Testes: `tests/unit/test_adaoduque.py` ganhou o teste do cabeçalho da v18 (coluna `arrecadacao`,
    CRLF). `tests/unit/test_club_aliases.py`: comentário atualizado; a lista de 46 nomes é exatamente
    a da v18 (nenhum alias novo foi preciso). Nenhuma mudança de código de produção.
  - `data/reference/known_exceptions.csv`: nota de 2009 atualizada (erro de mando confirmado).
  - `data/reference/manual_corrections.csv` (ignorado): as 2 correções saíram como
    `manual_correction_redundant` e foram removidas; o arquivo ficou só com o cabeçalho.
  - `data/reference/source_pins.json`: hashes fixados pelo `pin-adaoduque`. O campo `note` antigo
    ("Vazio: a ingestão de publicação falha") ficou obsoleto e não voltou; a proveniência está no
    catálogo e no manifesto.
  - `docs/data-sources/catalog.md`: proveniência da v18, partidas por temporada e fonte, conferência
    com o espelho do GitHub e com as fontes de conferência, problemas de qualidade.
- **Evidência**:
  - `ingest --fetch --season 2026`: 2003–2025 `adaoduque_kaggle` (9.165 partidas), 2026
    `football_data_org` (380: 319 `finished`, 60 `scheduled`, 1 `postponed`). Total 9.545.
  - Reexecução sem `--fetch`: silver, gold, `sources.json` e manifesto idênticos por SHA-256.
  - `conference`: football-data.org × Adão Duque 2024–2025, 760 casadas e zero divergência de data,
    status, placar ou rodada; Adão Duque × brasileirao-dataset 2003–2023, 8.405 casadas e zero
    divergência.
  - `validate`: 24 temporadas, sem erros; 4 avisos `info` de exceções conhecidas (2009, 2016) e 1
    `warning` (1 jogo de 2026 adiado, sem placar, tratado como não disputado).
  - Espelho do GitHub × v18: 4 diferenças (2 placares errados na v18, 1 placar de campo × tribunal,
    1 mando invertido na v18), classificadas no catálogo; detalhe só fora do repositório.
  - pytest 393 passed; `ruff check` e `ruff format --check` sem erros; mypy sem erros em 48 arquivos.
- **Mudanças desde a última ingestão** (silver de pesquisa `838614d` × publicação, por temporada,
  mandante e visitante): nenhum placar mudou; 1 status (o adiado de 2026 passou de `scheduled` a
  `postponed`); datas: 71 (2024), 67 (2025) e 70 (2026) recuaram 1 dia (fim do dia UTC), e 30 de
  2026 mudaram mais de 1 dia (calendário). O `changes.jsonl` recebeu 9.545 `new_match` porque o
  formato do `match_id` mudou (`bds-N` → estável); é efeito único da migração.
- **Premissas e limitações**:
  - Cartões: a v18 cobre 2014–2024. 2025 e 2026 ficam sem cartões; em 2026 o desempate por cartões
    cai no sorteio com aviso (já previsto no ADR-0008).
  - As 4 diferenças da v18 seguem como na fonte. `manual_corrections.csv` não corrige mando, e o
    caso de 2005 exige decidir entre placar de campo e de tribunal.
- **Próximos responsáveis**:
  - **00**: decidir o tratamento das 4 diferenças da v18 (corrigir 2003/2004 por correção manual
    com evidência; mando de 2009; campo × tribunal em 2005) e se `manual_corrections` passa a
    aceitar troca de mando. Passo 10 com 04.
  - **02**: depois do passo 10, regerar snapshots e revisão por rodada com os IDs e a fonte novos
    (não rodei `simulate` nem `export-web`, condição 2 do 06).
  - **06**: auditar a ingestão real (passo 12) e as contagens do catálogo.
