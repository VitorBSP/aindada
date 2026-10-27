# AGENTS.md — Diretrizes de desenvolvimento e orquestração

Este repositório é desenvolvido por nove agentes especializados (00–08) e um subagente (08A),
coordenados pelo
**Agente 00 — Arquitetura e Comando**. Cada agente tem um contrato em `agents/NN-*.md`
com responsabilidades, limites, entradas, saídas, dependências, critérios de aceite e handoff.

Os mesmos contratos estão disponíveis como subagentes executáveis do Claude Code em
`.claude/agents/`. Quando o ambiente não permitir subagentes, os arquivos funcionam como
instruções reutilizáveis. Nunca registre que um agente "executou" algo sem evidência
verificável (commit, arquivo, teste ou log).

## Mapa de responsabilidade

| Agente | Domínio | Código principal | Documentação |
|---|---|---|---|
| 00 Arquitetura e Comando | arquitetura, prioridades, integração, revisão | `src/brasileirao/pipeline.py`, `src/brasileirao/cli.py`, `src/brasileirao/config.py` | `docs/architecture/`, `docs/decisions/`, `docs/roadmap.md`, `docs/project/` |
| 01 Coleta e Engenharia de Dados | fontes, ingestão, contratos, qualidade | `src/brasileirao/data_pipeline/`, `src/brasileirao/contracts.py`, `data/reference/` | `docs/data-sources/` |
| 02 Modelagem e Simulação | ratings, modelos de gols, Monte Carlo | `src/brasileirao/ratings/`, `src/brasileirao/prediction/`, `src/brasileirao/simulation/` | `docs/methodology/` |
| 03 Regras e Competições | regulamento, desempate, vagas | `src/brasileirao/competition_rules/` | `docs/methodology/competition-rules.md` |
| 04 Backend e API | API, persistência, snapshots | `apps/api/`, `src/brasileirao/storage/` | `docs/architecture/api.md` |
| 05 Frontend e Experiência | interface | `apps/web/` | `docs/architecture/frontend.md` |
| 06 Validação e Qualidade | testes, backtesting, calibração | `tests/`, `src/brasileirao/validation/` | `docs/methodology/validation.md` |
| 07 Deploy e Infraestrutura | Docker, CI, operação | `infrastructure/`, `.github/workflows/`, `Dockerfile`, `docker-compose.yml` | `docs/architecture/deploy.md` |
| 08 Marca, Storytelling, UX e Engajamento | marca, editor-chefe dos insights, UX e textos da interface (D-022, D-026) | `docs/brand/assets/`, CSS/marcação/textos de `apps/web/` | `docs/brand/`, `docs/storytelling/`, `docs/ux/` |
| 08A Insights e Inteligência Editorial (subagente do 08) | candidatos a insight a partir dos snapshots | `src/brasileirao/insights/` | `docs/storytelling/INSIGHTS_CATALOG.md`, `docs/storytelling/contracts/` |

Mudanças em arquivos de outro agente exigem handoff explícito (ver abaixo).

## Fluxo de orquestração

1. O Agente 00 define a entrega, os contratos de interface e o critério de aceite.
2. Agentes produtores (01 → 03 → 02) entregam dados, regras e modelos nessa ordem de dependência.
3. O Agente 04 expõe resultados persistidos; o Agente 05 apenas consome a API ou o export estático.
4. O Agente 06 valida cada entrega antes de ela ser considerada concluída.
5. O Agente 07 empacota e só publica após aprovação do Agente 00 e do Agente 06.
6. O Agente 08 acompanha o produto em paralelo: recebe estratégia do 00 e diferenciais do 02,
   propõe identidade e entrega tokens/SVGs ao 05, que implementa; o 06 verifica contraste e
   consistência. Nenhuma proposta de marca vale sem decisão registrada em
   `docs/brand/BRAND_DECISIONS.md`.
7. Insights editoriais: 02 publica o snapshot → 08A gera candidatos → 08 revisa (approved,
   needs_revision, rejected) → 04 armazena e publica só os aprovados → 05 apresenta; o 06 audita
   as regras. Ninguém altera números da modelagem para melhorar uma história.

```text
01 Dados ──► 03 Regras ──► 02 Modelagem/Simulação ──► 04 API/Snapshots ──► 05 Frontend
   │             │                 │                          │
   └─────────────┴────── 06 Validação (gate em cada entrega) ─┘
                                   07 Infra empacota o que foi aprovado

00 Estratégia ──► 08 Marca ──► tokens, SVGs, tom de voz ──► 05 Frontend
02 Diferenciais ─┘     └──── critérios de contraste e uso ──► 06 Validação

02 Snapshot ──► 08A candidatos ──► 08 revisão editorial ──► 04 API ──► 05 Frontend
                                        └──── 06 audita regras e publicação
```

## Protocolo de handoff

Todo handoff entre agentes registra, no PR ou em `docs/project/status.md`:

- **O que mudou**: arquivos e contratos afetados.
- **Evidência**: comando executado e resultado (testes, métricas, contagens de dados).
- **Premissas e limitações** conhecidas.
- **Próximo responsável** e o que ele precisa fazer.
- Para o Agente 08: **decisões pendentes** do dono do produto e o que o Agente 05 deve implementar.

## Definição de pronto

Uma etapa só é concluída quando existem arquivos concretos, testes passando e, para modelos,
métricas de backtesting registradas em `docs/methodology/validation.md`. Etapas sem evidência
ficam como "em andamento" ou "pendente" em `docs/project/status.md`.

## Padrões de código

- Python 3.12+, tipado, compatível com Ruff/Flake8, Pylint e Mypy.
- Nomes descritivos. Não use `df`; prefira `matches_data`, `standings_data`, `predictions_data`.
- Sem comentários para código óbvio. Docstrings curtas quando a intenção não for evidente.
- Testes unitários com uma asserção principal por teste.
- Configuração centralizada em `src/brasileirao/config.py` e nos arquivos de temporada
  em `src/brasileirao/competition_rules/seasons/`.
- Logs estruturados (JSON) via `brasileirao.logging_utils`.
- Reprodutibilidade: toda simulação recebe semente e registra versões de modelo e dados.
- Cálculos estatísticos não dependem da API nem do frontend.

## Regras de integridade (inegociáveis)

- Nunca gerar resultados fictícios como dados reais. Fixtures sintéticas ficam em
  `tests/fixtures/` e são marcadas como `synthetic` no conteúdo.
- Nunca preencher resultados desconhecidos com 0 x 0. Partida sem placar é `scheduled`.
- Toda fonte tem proveniência registrada (URL, commit/versão, data de coleta, hash, licença).
- Não usar fonte apenas por estar acessível: o status de licença fica no catálogo
  (`docs/data-sources/catalog.md`) e no manifesto de ingestão.
- Validação temporal: nenhuma informação posterior à data de referência entra em ratings,
  treino ou simulação daquela data.
- Probabilidades continentais dependentes de torneios externos não resolvidos são
  apresentadas como cenários condicionais ou faixas, nunca com probabilidades arbitrárias.
- Nenhum deploy público sem revisão dos Agentes 00 e 06.
- Nenhum nome, paleta ou elemento de marca é tratado como aprovado sem decisão registrada; nenhuma
  marca ou domínio é declarado disponível sem verificação com fonte e data.
