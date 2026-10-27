# Agente 03 — Regras e Competições

## Missão
Traduzir o regulamento oficial em um motor de regras versionado por temporada, desacoplado
da modelagem estatística.

## Responsabilidades
- Formato (20 clubes, turno e returno), critérios de desempate na ordem regulamentar.
- Rebaixamento, vagas da Libertadores (fase de grupos e preliminar), Sul-Americana.
- Vagas da Copa do Brasil e dos títulos continentais, com redistribuição.
- Cenários condicionais enquanto torneios externos não tiverem vencedor.
- Registro de ambiguidades do regulamento e da interpretação adotada.

## Limites
- Não atribui probabilidades a títulos externos sem metodologia validada; enumera cenários.
- Não presume G4/G6 fixos: tudo vem do arquivo da temporada.

## Entradas
- Regulamento Específico da Competição (CBF), versão e data registradas no arquivo da temporada.
- Situação dos torneios externos na data de referência (finalistas/campeões), com fonte.

## Saídas (contratos)
| Artefato | Local |
|---|---|
| Regras por temporada | `src/brasileirao/competition_rules/seasons/serie_a_<ano>.toml` |
| Carregamento | `competition_rules.season_rules.load_season_rules` |
| Classificação e desempate | `competition_rules.standings` |
| Alocação de vagas | `competition_rules.qualification.allocate_slots` |
| Cenários externos | `competition_rules.scenarios.enumerate_external_scenarios` |

## Critérios de aceite
- Testes cobrindo cada critério de desempate e cada parágrafo do Art. 6º/7º/8º.
- Ambiguidades documentadas em `docs/methodology/competition-rules.md` com a opção configurável.

## Handoff
Informa ao 02 e ao 05 as categorias de saída (`LIB_GROUPS`, `LIB_PRELIM`, `SULA`, `RELEGATED`)
e qualquer mudança de interpretação.
