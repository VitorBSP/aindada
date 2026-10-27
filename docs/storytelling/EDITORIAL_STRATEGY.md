# Estratégia editorial — AInda dá?

Responsável: Agente 08 (editor-chefe). Versão 1 — 2026-10-26 (D-026). Status: **critérios
definidos; nenhum insight publicado ainda.**

## Para que serve o conteúdo
O torcedor abre o AInda dá? para responder uma pergunta: **o meu time ainda dá?** — para o título,
para a Libertadores ou para escapar. O conteúdo editorial existe para responder essa pergunta
melhor que uma tabela sozinha: dizer o que mudou, por que mudou (até onde os dados permitem) e o
que vem pela frente.

## O que contamos (pilares)
| Pilar | Pergunta do torcedor | Exemplo de formato (ilustrativo) |
|---|---|---|
| A rodada | O que mudou depois desses jogos? | "Quem mais ganhou chance nesta rodada" |
| As disputas | Como estão título, Libertadores, Sul-Americana e queda? | "A briga pelo título ficou mais aberta?" |
| O meu clube | E o meu time? | "O que o próximo jogo vale para o Bahia" |
| Os jogos | Qual jogo importa? | "O jogo que mais mexe na zona de queda" |
| A temporada | Como chegamos até aqui? | "As viradas da temporada em chance de título" |

Títulos da tabela são **formatos**, não fatos. Nenhum título é publicado sem os dados que o
sustentam (ver `INSIGHTS_VALIDATION.md`).

## Ritmo
- **Depois de cada rodada** (novo snapshot): até 3 destaques na home, a narrativa da rodada e
  atualização das páginas de clube.
- **Antes da rodada**: jogos que mais podem mexer nas disputas (quando o dado existir, ver catálogo).
- **Mensal ou em marcos** (meio do turno, fim do turno, últimas 5 rodadas): uma história de
  temporada.
- Sem snapshot novo, não há destaque novo. Não requentamos conteúdo para parecer movimento.

## Hierarquia na home (2026-10-26: itens 1 e 2 implementados; item 3 parcial, sem Sul-Americana)
1. **Manchete da rodada**: um único destaque, o de maior pontuação editorial aprovado.
2. **Mais duas histórias** de pilares diferentes (diversidade obrigatória).
3. **As quatro disputas** em blocos curtos (título, Libertadores em faixa, Sul-Americana, queda).
4. **Seu clube** (se o torcedor escolheu acompanhar um).
5. **Próximos jogos que importam**.
6. Tabela e explorações ficam a um clique, não na home.

**Regras de exibição implementadas:** só aparecem insights `published` do snapshot exibido (mesma
data de referência). Destaque de rodada antiga não aparece como atual. Sem manchete aprovada, a
home volta ao layout da briga pelo título. Na aba "Rodada a rodada", o bloco "Destaques desta
rodada" aparece só na rodada mais recente, com o mesmo snapshot.

## Princípios editoriais
- **Futebol primeiro, estatística por trás.** Falamos de clubes, jogos e disputas; o método fica
  em "Como calculamos".
- **Uma ideia por destaque.** Título curto, um número principal, uma frase de contexto.
- **Mudança acima do ruído.** Só vira notícia o que passa dos limiares de materialidade e de erro
  de simulação.
- **Causa com cuidado.** "Depois da vitória sobre X" é permitido quando o jogo aconteceu; "por
  causa da vitória sobre X" só quando a decomposição mostrar que o efeito veio daquele jogo.
- **Diversidade.** Nenhum clube aparece em mais de um destaque da home na mesma rodada; nenhum
  formato repete por mais de 2 rodadas seguidas sem fato novo.
- **Neutralidade.** Provocação leve permitida (D-010), sem preferência por clube.

## Quem faz o quê
Ver o fluxo em `agents/08-brand-storytelling-ux.md`. O 08A propõe; o 08 decide; o 04 armazena e
publica; o 05 apresenta; o 06 audita.
