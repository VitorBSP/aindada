# Validação editorial de insights

Responsável: Agente 08. Auditoria: Agente 06. Versão 1 — 2026-10-26.

## Estados
| Estado | Significado | Pode ser publicado? |
|---|---|---|
| `candidate` | gerado pelo 08A, ainda não revisado | não |
| `needs_revision` | ideia boa, mas falta dado, contexto ou o texto exagera | não; volta ao 08A ou é reescrito pelo 08 |
| `rejected` | não deve ser publicado (motivo obrigatório) | não |
| `approved` | aprovado para publicação | sim, pela API |
| `published` | no ar (registrado pelo 04) | — |
| `retired` | saiu do ar (substituído por snapshot novo ou corrigido) | — |

## Portões automáticos (antes da revisão humana/editorial)
Um candidato que falhe em qualquer portão é rejeitado automaticamente, com o motivo registrado:
1. **Schema**: valida contra `contracts/insight.schema.json`.
2. **Rastreabilidade**: `snapshot_ref` existe, com `model_version`, `data_version`,
   `reference_date` e `seed`; todo número do texto aparece em `evidence`.
3. **Temporalidade**: nenhuma evidência com data posterior a `reference_date`.
4. **Ruído**: variações passam no teste de `INSIGHTS_CATALOG.md` (`z` e materialidade).
5. **Aritmética**: `delta_pp = (current − previous) × 100` confere; variação relativa só quando
   `previous ≥ relative_min_base`.
6. **Faixas**: insights de Libertadores ou Sul-Americana que dependem de torneios externos usam a
   faixa, nunca um único número.

## Checklist do editor (08)
Cada item recebe sim/não no `editorial_review`:
- [ ] Matematicamente correto?
- [ ] Os dados sustentam a conclusão (sem causa indevida)?
- [ ] Interessa ao torcedor?
- [ ] Acrescenta algo além da tabela?
- [ ] Fácil de entender em uma leitura?
- [ ] No tom da marca (`CONTENT_GUIDELINES.md`)?
- [ ] Não repete um insight publicado nas últimas `novelty_window` rodadas?
- [ ] Tem forma visual clara?
- [ ] Sem risco de leitura enganosa ou sensacionalista?

Regra de decisão: qualquer "não" nos três primeiros itens → `rejected` ou `needs_revision`;
"não" em tom ou visual → `needs_revision`.

## Pontuação editorial (para ordenar os aprovados)
`score = w_rel·relevância + w_nov·novidade + w_mat·materialidade + w_div·diversidade`
(pesos em `[criteria.scoring]`), cada componente entre 0 e 1:
- **relevância**: peso da disputa (título e queda > Libertadores > Sul-Americana > curiosidade) e
  número de clubes afetados;
- **novidade**: 1 se o formato e o clube não apareceram nas últimas `novelty_window` publicações;
- **materialidade**: `min(1, |Δ| / materiality_full)`;
- **diversidade**: penaliza o mesmo clube ou o mesmo pilar já escolhido na mesma página.

A pontuação ordena; não aprova. Só `approved` entra na disputa por posição.

## Registro e aprendizado
Toda revisão grava: `insight_id`, `insight_version`, estado, motivo, checklist, editor, data e
`criteria_hash`. A cada 5 rodadas o 08 revisa as taxas de rejeição por regra; regras com mais de
50% de rejeição têm limiares revistos (nova `rules_version`).

## Histórico de revisões
O registro completo fica em `data/editorial/{temporada}/reviews.jsonl`. Resumo:

| Data | Lote | Insight | Regra | Decisão | Motivo |
|---|---|---|---|---|---|
| 2026-10-26 | `2026-s27-rules-2026.10.1-743786ab` (dados até 18/10) | `ins_2cebc29feb581e57` | `RELEG_RISER` | approved · home_lead 1 | Risco de queda de um clube passou da metade, com alta acima do limiar de 5 p.p.; título editado (formato: "Risco de queda do Clube X passa da metade", ilustrativo); sem causa atribuída (o intervalo do snapshot, 13/10–18/10, não coincide com o da revisão por rodada) |
| 2026-10-26 | idem | `ins_eef611997b3470ef` | `MATCH_MOVED_MOST` | approved · home_secondary 1 | Jogo que mais mexeu na chance de G4 de um clube nas simulações pré-jogo (acima do limiar de 6 p.p.), com um resultado a que o modelo dava menos de 50% de chance; texto editado para fluir melhor |

Clubes, placares e probabilidades desses dois insights ficam fora do repositório (decisão B1 de
2026-10-27, dados derivados da fonte restrita): ver `data/editorial/{temporada}/` e o registro local
`data/editorial/status_numeros_reais.md`.

Verificação independente dos números nos arquivos de dados antes da aprovação (status do projeto).
