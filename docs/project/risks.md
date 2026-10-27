# Riscos, dependências e decisões em aberto

| # | Risco | Impacto | Mitigação | Dono |
|---|---|---|---|---|
| R1 | Licença dos dados 2024+ (Sofascore via repositório sem licença) | Bloqueia publicação | Status `research_only_unverified`; obter token football-data.org e conferir com a CBF | 01 |
| R2 | Atraso da fonte (12 jogos com data passada sem placar em 26/10) | Previsões defasadas | Aviso na interface e na API; jogos simulados, nunca preenchidos; segunda fonte | 01 |
| R3 | Ambiguidade do Art. 6º § 5º | Vagas erradas em cenários raros | Política configurável; consulta formal à DCO | 03 |
| R4 | Situação dos torneios externos mantida manualmente | Cenários desatualizados | Campos no TOML com data `as_of` e fontes; revisar após cada fase | 03 |
| R5 | Leve excesso de confiança (cobertura de 87% no intervalo de 90%) | Probabilidades extremas otimistas | Propagar incerteza de parâmetros (fase 5) | 02 |
| R6 | Subestimação de empates (26,1% previsto contra 27,3% observado) | 1X2 levemente enviesado | Modelagem de empates (fase 5) | 02 |
| R7 | FastAPI não executado neste ambiente (registro PyPI bloqueado) | Bugs na camada HTTP | Testes de integração rodam no CI e localmente (`pytest`), com `importorskip` aqui | 04/07 |
| R8 | Cartões dos jogos simulados são desconhecidos | Desempate por cartões aproximado | Usa só cartões observados; impacto raríssimo | 03 |
| R9 | Duplicidade Botafogo x Flamengo em 2009 | Ruído mínimo no Elo histórico | Exceção registrada; confirmar com a CBF | 01 |
| R10 | Repositório público redistribui tudo o que estiver no histórico do git, sem volta segura | Dados restritos (raw, silver, snapshots, export) ou escudos não livres expostos | `.gitignore` antes do primeiro commit; `git ls-files` auditado pelo 06 com o repositório ainda privado (ADR-0007, C4) | 07/06 |
| R11 | GitHub desativa workflows agendados após 60 dias sem atividade em repositório público (a verificar) | Site para de atualizar sem aviso | Gate de `reference_date`; monitoramento pelo 07; commits legítimos (lotes editoriais, TOML) | 07 |
| R12 | SQLite de estado perdido entre execuções do Actions | Histórico de probabilidades e revisão por rodada quebrados | Asset de release `snapshots-db` + artefato + cópia local; checagem de contagem não regressiva (ADR-0007) | 07/04 |
