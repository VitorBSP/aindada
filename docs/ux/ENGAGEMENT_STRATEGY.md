# Estratégia de engajamento

Versão 1 — 2026-10-26. Objetivo: que o torcedor volte depois de cada rodada porque há algo novo e
útil sobre o seu clube e as disputas, não por truque.

## O que traz o torcedor de volta
| Motivo | Recurso | Status | Dependência |
|---|---|---|---|
| Algo mudou depois da rodada | manchete e até 3 destaques que mudam a cada snapshot | existe (2026-10-26) | 08A + revisão do 08 |
| O meu clube | escolher um clube para acompanhar (guardado no próprio navegador) | proposto | 05 |
| Ver a curva do meu time | evolução das chances na página do clube | existe | — |
| Comparar com o rival | comparação entre clubes | existe na aba de rodadas | — |
| Entender o próximo jogo | "o que está em jogo" e "E se meu time vencer?" | proposto | 02 (simulação condicional) |
| Brincar com cenários | seletor de outros torneios | existe (corrigido em 2026-10-26) | — |
| Compartilhar | link direto e prévia com número e data | proposto | 05 |
| Marcos da temporada | histórias de turno, reta final, viradas | proposto | 08A |

## Hipóteses (a medir quando houver medição de uso)
- H1: a manchete da rodada aumenta a navegação para a página do clube.
- H2: o clube favorito aumenta a volta na rodada seguinte.
- H3: o link direto do destaque é a principal porta de entrada vinda das redes.

Medição prevista: contagem agregada de visitas por página, sem cookies de terceiros nem
identificação pessoal; decisão do Agente 00 antes de qualquer ferramenta.

## O que não fazemos
- Notificação enganosa ou alarmista; contagem regressiva falsa; "você não vai acreditar".
- Conteúdo repetido para simular novidade; destaque sem snapshot novo.
- Pedir cadastro para ver números.
- Gamificação vazia (pontos, medalhas) sem valor para entender o campeonato.

## Ordem sugerida de construção
1. Clube favorito + destaque do clube na home (só frontend).
2. Pipeline 08A com 4 regras de maior valor (`TITLE_RISER`, `TITLE_FALLER`, `RELEG_RISER`,
   `MATCH_MOVED_MOST`) + revisão editorial + publicação manual.
3. Manchete da rodada na home e narrativa no topo da aba "Rodada a rodada".
4. Pedido ao 02: simulação condicional por jogo → "o que está em jogo" e "E se meu time vencer?".
5. Compartilhamento com prévia.
