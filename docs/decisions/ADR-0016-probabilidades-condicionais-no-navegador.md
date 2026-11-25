# ADR-0016 — Probabilidades condicionais do "seu time" calculadas no navegador

- Status: **aceita pelo dono do produto** (2026-11-25, chat: "Faça o 2.").
- Responsáveis: Agente 00 (decisão e exceção à regra), 05 (interface), 02 (método), 06 (validação).
- Origem: opção B3 do canvas de UI (Home centrada no seu time). Os blocos "Se o jogo terminar em…" e "O que mais
  mexe na sua probabilidade" precisam de probabilidades **condicionadas a resultados de jogos futuros**, que o
  snapshot publicado não traz.

## Contexto

O `AGENTS.md` diz que "cálculos estatísticos não dependem da API nem do frontend". Havia duas saídas:

1. Calcular em Python e publicar um campo novo no snapshot. É o caminho mais alinhado à regra, mas muda o
   contrato do JSON (Agentes 02 e 04) e o tamanho do export.
2. Calcular no navegador com o motor que o modo Ao vivo já usa (`live-round.js`, que reaproveita o sorteio,
   a tabela e o desempate do simulador e as vagas do Art. 6º–8º).

O dono escolheu a opção 2.

## Decisão

1. `LiveRound.simulate` ganha a opção `track: { clubId, matchIds }`. Na mesma rodada de simulações (20.000,
   semente fixa `2026`), conta, para cada jogo acompanhado e cada resultado sorteado nele (mandante, empate,
   visitante), em quantas simulações o clube terminou em 1º, no G4 ou no Z4. A probabilidade condicionada é a
   fração dessas simulações. Nada no sorteio muda; sem `track`, o resultado é o mesmo de antes.
2. A Home do seu time (`app.js`) acompanha os próximos 20 jogos com data (mais o jogo do time, se estiver mais
   longe) e mostra:
   - **Se o jogo terminar em…**: vitória, empate e derrota do seu time no próximo jogo. Em jogo ao vivo, o
     resultado de agora aparece marcado ("como está") e a simulação parte do placar atual.
   - **O que mais mexe na sua probabilidade de <disputa>**: os 3 jogos com a maior diferença entre o melhor e o
     pior resultado para o seu time (diferença mínima de 1 ponto percentual), com os dois valores.
3. Salvaguardas:
   - O número grande da Home continua sendo o publicado no snapshot. Os condicionais vêm com
     "Calculado no seu navegador: 20.000 simulações", e o botão `(i)` explica que podem diferir um pouco do número
     publicado.
   - Resultado sorteado em menos de 300 simulações aparece como "–" (amostra pequena demais).
   - Entradas são só as probabilidades publicadas (`score_probabilities`) e, quando houver, o placar ao vivo de
     `live_round_scores`; o navegador não reestima força de clube nem altera número do modelo.
   - Semente fixa: o mesmo snapshot e os mesmos placares dão os mesmos números.
   - Testes em `tests/unit/test_live_round_js.py`: as contagens por resultado somam o total de simulações; a soma
     ponderada das condicionais devolve a probabilidade geral da mesma rodada (lei da probabilidade total); jogo
     encerrado não é acompanhado; sem `track`, nada muda.

## Consequências

- Exceção explícita à regra do `AGENTS.md`, limitada a estes blocos de leitura da Home. O modo Ao vivo (T1) já
  calculava no navegador. Qualquer número novo calculado no navegador precisa de decisão própria.
- O cálculo leva cerca de 3 s num computador; durante esse tempo os blocos mostram skeleton, e a tela não trava
  (as simulações cedem a vez a cada 2.000).
- Se o projeto migrar para a opção 1 (campo no snapshot), a interface troca a fonte do número e mantém os blocos.
