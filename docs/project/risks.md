# Riscos, dependências e decisões em aberto

| # | Risco | Impacto | Mitigação | Dono |
|---|---|---|---|---|
| R1 | Licença dos dados 2024+ (Sofascore via repositório sem licença) | Bloqueia publicação | Status `research_only_unverified`. Caminho aprovado no ADR-0008: Adão Duque v18 até 2025 e football-data.org de 2026 em diante, com conferência com a CBF | 01 |
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
| R12 | SQLite de estado perdido entre execuções do Actions | Histórico de probabilidades e revisão por rodada quebrados | Asset de release num **repositório privado** de estado, com 3 versões anteriores e cópia local, e checagem de contagem não regressiva (ADR-0008, Decisão 3; o asset público do ADR-0007 foi revogado). A credencial do repositório privado expira: o 07 monitora a validade | 07/04 |
| R13 | Cláusula 9.1 do football-data.org: cancelada a conta, o site não pode mais referenciar os dados de 2026+, nem nos snapshots antigos | Site sem dados da temporada corrente | Plano gratuito na conta do dono; fontes por snapshot (`data.sources`) para tornar a retirada executável; risco aceito pelo dono (ADR-0008) | 00/dono |
| R14 | Termos do football-data.org mudam sem aviso (11.1) | Uso atual pode deixar de ser permitido | Releitura no início de cada temporada, com `terms_checked_at` no manifesto | 01 |
| R15 | Adão Duque: GPL-2 aplicada a dados e coleta de segunda mão ("páginas do Google") | Cadeia de licença frágil no histórico 2003–2025 | Sem redistribuição dos dados; conferência cruzada local; crédito ao autor; plano B no ADR-0008 | 01/dono |
| R16 | Datas de 207 jogos noturnos de 2024–2026 no dia UTC na fonte atual | Validação temporal deslocada em um dia no backtest atual | Conversão para `America/Sao_Paulo` no `FootballDataOrgSource`; troca de fonte; avaliação de impacto pelo 06 (em andamento) | 01/06 |
