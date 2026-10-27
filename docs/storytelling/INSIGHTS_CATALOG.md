# Catálogo de insights — regras do 08A

Versão das regras: `rules-2026.10.1` (2026-10-26). Status: **4 regras implementadas** em
`src/brasileirao/insights/` (`TITLE_RISER`, `TITLE_FALLER`, `RELEG_RISER`, `MATCH_MOVED_MOST`); as demais
estão especificadas.

Histórico: `2026.10.0` primeira especificação; `2026.10.1` texto de `MATCH_MOVED_MOST` sem repetir o
nome do clube vencedor e versão das regras incluída no `insight_id`.
Os limiares citados (`[criteria.*]`) estão em `contracts/insight-criteria.toml`.

## Fontes de dados disponíveis hoje
| Sigla | Endpoint | O que tem |
|---|---|---|
| SNAP | `/api/seasons/{s}/predictions` | por clube: título, G4, Libertadores (grupos, prévia, total em faixa por cenário), Sul-Americana, rebaixamento, distribuição de posição, pontos projetados e intervalo de 90%, ratings; jogos com 1X2 e gols esperados |
| HIST | `/api/seasons/{s}/probability-history` | por snapshot: título, G4, rebaixamento, faixa de Libertadores, pontos projetados |
| ROUND | `/api/seasons/{s}/rounds` | por rodada: variação por clube, efeito de resultados × força, impacto de cada jogo, "em jogo" por partida, ruído esperado |

Regras marcadas **[depende do 02]** precisam de dado que ainda não é produzido.

## Teste de ruído comum a todas as regras de variação
Para uma probabilidade `p1` (atual, `N1` simulações) e `p0` (anterior, `N0`):
`erro = sqrt(p1(1−p1)/N1 + p0(1−p0)/N0)`. A variação `Δ = p1 − p0` só é candidata se
`|Δ| ≥ max(materialidade, z · erro)` (`[criteria.noise] z`). Quando ROUND trouxer
`expected_noise_movement`, ele substitui a estimativa.

## Regras

### Disputa pelo título
| ID | Pergunta | Fonte | Dispara quando | Visual sugerido |
|---|---|---|---|---|
| `TITLE_RISER` | Quem mais ganhou chance de título? | HIST/ROUND | maior Δ positivo, passa no teste de ruído e `Δ ≥ title_pp` | barra antes/depois |
| `TITLE_FALLER` | Quem mais perdeu? | HIST/ROUND | maior Δ negativo, idem | barra antes/depois |
| `TITLE_CONCENTRATION` | A disputa ficou mais aberta ou concentrada? | HIST | nº efetivo de candidatos `1/Σp²` muda ≥ `concentration_delta` | frase + mini-série |
| `TITLE_OUTSIDER` | Alguém fora do G4 virou candidato relevante? | SNAP | clube com posição atual > 4 e título ≥ `outsider_min` | destaque de clube |

### Rebaixamento
| ID | Pergunta | Fonte | Dispara quando | Visual |
|---|---|---|---|---|
| `RELEG_RISER` | Quem mais aumentou o risco de queda? | HIST/ROUND | maior Δ positivo acima do ruído e `≥ relegation_pp` | barra antes/depois |
| `RELEG_ESCAPE` | Alguém saiu da situação crítica? | HIST | risco passou de ≥ `critical_high` para ≤ `critical_low` desde a última publicação | frase + série |
| `RELEG_HIDDEN_RISK` | Quem está fora do Z4 mas tem risco relevante? | SNAP | posição atual ≤ 14 e risco ≥ `hidden_risk_min` | destaque de clube |

### Libertadores e Sul-Americana (sempre em faixa, ADR-0003)
| ID | Pergunta | Fonte | Dispara quando | Visual |
|---|---|---|---|---|
| `LIBERTA_CLOSER` | Quem mais se aproximou da Libertadores? | HIST | maior subida do **limite inferior** da faixa acima do ruído | faixa antes/depois |
| `LIBERTA_DEPENDS` | Quem depende dos outros torneios? | SNAP | largura da faixa (máx − mín) ≥ `range_wide` | faixa + seletor de cenários |
| `SULA_OUTSIDE_ZONE` | Fora da faixa típica com boa chance de Sul-Americana? | SNAP | posição atual > 11 e limite inferior ≥ `sula_outside_min` | destaque |

### Surpresas e tendências
| ID | Pergunta | Fonte | Dispara quando | Visual |
|---|---|---|---|---|
| `POSITION_GAP` | Quem está bem acima/abaixo do lugar onde deve terminar? | SNAP | \|posição atual − posição média projetada\| ≥ `position_gap` | tabela atual × projetada |
| `UNCERTAIN_FINISH` | Quem tem o fim mais imprevisível? | SNAP | intervalo de 90% de posição ≥ `position_spread` lugares | distribuição de posição |
| `TREND_STREAK` | Quem sobe (ou cai) há várias rodadas? | HIST | mesma direção em ≥ `streak_rounds` snapshots seguidos, soma acima do ruído | mini-série |
| `POINTS_VS_STRENGTH` | Quem tem mais pontos do que a força sugere? | **[depende do 02]** | precisa de pontos esperados pela força em jogos já disputados | — |

### Jogos
| ID | Pergunta | Fonte | Dispara quando | Visual |
|---|---|---|---|---|
| `MATCH_MOVED_MOST` | Qual jogo mais mexeu nas chances? | ROUND | `decisive_match_id` com impacto acima do ruído | placar + chips de efeito |
| `MATCH_SURPRISE` | Qual resultado foi a maior surpresa? | ROUND | resultado com probabilidade pré-jogo ≤ `surprise_max` | placar + chance antes |
| `MATCH_UPSET_FAVORITE` | Jogo em que o favorito contraria a tabela? | SNAP | mandante/visitante pior colocado com P(vitória) ≥ `upset_favorite_min` | linha de jogo |
| `MATCH_STAKES_NEXT` | Qual próximo jogo mais pode mexer na disputa? | **[depende do 02]** | precisa de simulação condicional por resultado de jogo futuro | linha de jogo + "em jogo" |

### Fora do catálogo
Novas regras entram por proposta do 08A, com teste de ruído definido e aprovação do 08 registrada
aqui com nova versão de `rules_version`.

## Pedidos ao Agente 02
1. Pontos esperados pela força nos jogos já disputados (para `POINTS_VS_STRENGTH`).
2. Simulação condicional por resultado dos próximos jogos (para `MATCH_STAKES_NEXT` e para o
   recurso "E se meu time vencer o próximo jogo?").
