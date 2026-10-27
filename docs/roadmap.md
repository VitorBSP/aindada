# Roadmap

| Fase | Entrega | Status |
|---|---|---|
| 0 | Estrutura, AGENTS.md, 8 agentes (00–07), ADRs, riscos | ✅ concluída |
| 1 | Catálogo de fontes, contratos, ingestão raw/silver/gold, validação, regras 2026 versionadas | ✅ concluída (fonte com licença restrita) |
| 2 | Elo, ataque/defesa, Poisson, Monte Carlo, vagas e cenários, backtesting | ✅ concluída |
| 3 | Snapshots, API, interface, execução local ponta a ponta | ✅ MVP (API não executada neste ambiente; ver status) |
| 4 | Fontes licenciadas (football-data.org com token; conferência com a CBF); atualização agendada | ⏳ próxima |
| 5 | Etapa 2 do modelo: modelagem de empates, ρ por temporada, incerteza de parâmetros, cobertura de 90% | ⏳ |
| 6 | Etapa 3: classificador multiclasse calibrado, benchmark de odds (Football-Data.co.uk), blending só com ganho validado | ⏳ |
| 7 | Frontend Next.js/TypeScript, PostgreSQL, deploy público após revisão | ⏳ deploy: ADR-0007 proposto (GitHub Pages estático); preparação liberada, publicação bloqueada por C1–C6 |

## Trilha de marca (Agente 08, paralela às fases técnicas)

| Etapa | Entrega | Status |
|---|---|---|
| M1 Descoberta | Agente 08, `docs/brand/`, briefing, público, diferenciais, questões abertas | ✅ primeira versão (2026-10-26) |
| M2 Exploração | 5 direções de naming/posicionamento e 3 de cor; A e B aprofundadas com esboços SVG e checagem de domínios | ✅ concluída: nome "AInda dá?" e paleta principal decididos (D-004, D-005) |
| M3 Desenvolvimento | símbolo ✅ (D-017), assinatura e tipografia da marca ✅ (D-019, D-021); faltam tokens, ícone de app, fontes de interface, aplicações; INPI e domínio | ⏳ em andamento |
| M4 Identidade final | kit (tokens, SVGs, favicon, ícone, guia) implementado pelo 05 e verificado pelo 06 | ⏳ antes do deploy público (fase 7) |
| M5 Evolução | revisão das diretrizes conforme o produto muda | contínua |

## Trilha de storytelling, UX e insights (Agente 08 e subagente 08A, D-026)

| Fase | Entrega | Status |
|---|---|---|
| B — Storytelling e UX | princípios, jornadas, estratégia editorial e de engajamento | ✅ v1 documentada (2026-10-26); layout definitivo da home depende dos insights |
| C — Inteligência editorial | contrato, catálogo de regras e critérios | ✅ especificado e implementado (4 de 18 regras); ⏳ demais regras e dados pedidos ao 02 |
| C — Primeira publicação | 4 regras (`TITLE_RISER`, `TITLE_FALLER`, `RELEG_RISER`, `MATCH_MOVED_MOST`) com revisão | ✅ módulo, portões, revisão, publicação e rota da API (2026-10-26); 2 insights publicados; ⏳ exibição na interface |
| D — Evolução | clube favorito, "E se meu time vencer?" (depende do 02), compartilhamento | ⏳ |

Critério para avançar de fase: evidência registrada em `docs/project/status.md` e parecer do Agente 06.
