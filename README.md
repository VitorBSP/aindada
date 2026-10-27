# brasileirao-predictions

Modelo preditivo e simulador de temporadas do **Campeonato Brasileiro Série A**: ratings Elo e de
ataque/defesa, modelo de gols de Poisson, simulação de Monte Carlo do restante da temporada e
regulamento oficial versionado. O resultado são probabilidades de título, G4, Libertadores (fase de
grupos e preliminar), Sul-Americana, rebaixamento e de cada posição final.

> **Status:** MVP local, experimental. Os dados de 2024+ têm licença não verificada (ver
> `docs/data-sources/catalog.md`). **Não publicar** antes de resolver isso (ADR-0002).

## Rodando localmente

Requer Python 3.12+ e git.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (no Linux/macOS: source .venv/bin/activate)
pip install -e ".[api,sources,dev]"
python scripts/install_claude_agents.py   # opcional: ativa os 10 subagentes (00–08 e 08A) no Claude Code

# 1. Dados: clona/atualiza a fonte e gera raw → silver → gold
python -m brasileirao.cli ingest --fetch
python -m brasileirao.cli validate

# 2. Modelo: ajuste de hiperparâmetros + backtesting temporal (~5 min)
python -m brasileirao.cli backtest

# 3. Previsões: snapshot atual (10 mil simulações) + histórico rodada a rodada
python -m brasileirao.cli simulate --season 2026 --history-from-round 5

# 3b. Insights editoriais (08A gera, 08 revisa, só os aprovados são publicados)
python -m brasileirao.cli insights-generate --season 2026
python -m brasileirao.cli insights-list --season 2026
python -m brasileirao.cli insights-review --season 2026 --insight-id <id> --decision approved \
    --placement home_lead --priority 1 --reason "<motivo>"
python -m brasileirao.cli insights-publish --season 2026

# 4. Interface + API em http://localhost:8000
uvicorn apps.api.main:app --port 8000
```

Sem instalar a API, a interface também abre como site estático:
`python -m http.server 8080 --directory apps/web` → http://localhost:8080.

Os dados, o backtest e os snapshots de 2026 (data de referência 18/10/2026) já vêm gerados no
repositório. Por isso o passo 4 funciona direto.

Opções úteis de `simulate`: `--simulations 100|1000|10000`, `--seed`, `--reference-date AAAA-MM-DD`
(reproduz qualquer data histórica) e `--history-simulations`.

## Qualidade

```bash
ruff check src apps tests scripts && mypy && pytest
```

## Estrutura

```text
AGENTS.md                      diretrizes e orquestração dos 9 agentes
agents/                        contratos dos agentes 00–08 e do subagente 08A
infrastructure/claude-agents/  definições de subagentes do Claude Code (instale com scripts/install_claude_agents.py)
src/brasileirao/
  data_pipeline/               fontes, ingestão raw/silver/gold, validação
  competition_rules/           regulamento por temporada (seasons/*.toml), desempate, vagas, cenários
  ratings/                     Elo, ataque/defesa, forma, histórico sem vazamento
  prediction/                  modelos de gols (Poisson, Dixon-Coles), métricas
  simulation/                  Monte Carlo vetorizado e agregação
  validation/                  backtesting e seleção de modelo
  storage/                     esquema do snapshot e persistência SQLite
  pipeline.py, cli.py          orquestração
apps/api/                      FastAPI (só leitura de snapshots)
apps/web/                      interface (HTML/CSS/JS, sem build)
data/                          raw, silver, gold, reference, snapshots
docs/                          arquitetura, ADRs, metodologia, fontes, marca, roadmap, status
tests/                         unitários e integração (fixtures sintéticas identificadas)
```

## Documentação

- Arquitetura: `docs/architecture/overview.md` · API: `docs/architecture/api.md`
- Modelo: `docs/methodology/model.md` · Validação: `docs/methodology/validation.md`
- Regras e vagas: `docs/methodology/competition-rules.md`
- Fontes e licenças: `docs/data-sources/catalog.md`
- Decisões: `docs/decisions/` · Roadmap: `docs/roadmap.md`
- Marca: `docs/brand/` · Storytelling e insights: `docs/storytelling/` · UX: `docs/ux/`
- Status, pendências e riscos: `docs/project/status.md`, `docs/project/risks.md`
