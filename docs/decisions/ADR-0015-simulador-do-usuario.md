# ADR-0015 — Simulador do usuário, em fases

- Status: **fase 1 aceita pelo dono do produto** (2026-11-07). Fase 2 **implementada e desligada** (2026-11-07):
  provedor e identidade decididos pelo dono; falta criar o projeto no Supabase, a página de privacidade e a revisão
  dos Agentes 00 e 06.
- Responsáveis: Agente 00 (decisão), 05 (interface), 02 (matriz de placares), 04 (campo no snapshot),
  08 (textos e forma), 06 (validação), 07 (publicação).
- Origem: pedido do dono do produto (chat, 2026-11-07): uma seção em que o visitante simula jogos ou posições, com
  modos rápido e completo, salva a simulação, compara com a dos outros usuários e, se quiser, entra num ranking;
  referência de estilo: wcpredictor.app. "É uma feature a mais, não o principal do site."

## Contexto

O site é estático no GitHub Pages, sem servidor e sem orçamento (ADR-0007, D-013). Salvar simulações de
visitantes, mostrar a média deles e montar ranking exige guardar dados de terceiros num servidor, com conta e
consentimento (LGPD). Diante das opções (fases, base gratuita já ou só no aparelho), o dono escolheu **fases**,
**começar só pela Série A** e, depois, os nomes **Classificação · Vencedor · Placar exato**, com a opção
**"Completar com o modelo"** nos dois últimos.

## Decisão

### Fase 1 (implementada)

1. Rota `#/simular/{classificacao|vencedor|placar}` no site da Série A, item "Simulador" no menu.
   - **Classificação**: o visitante ordena os 20 clubes. Cada linha mostra a probabilidade do modelo de o clube
     terminar exatamente naquela posição, e o simulador avisa quando uma ordem é impossível pela matemática
     (o clube de cima não alcança os pontos que o de baixo já tem).
   - **Vencedor**: vitória do mandante, empate ou vitória do visitante em cada jogo restante.
   - **Placar exato**: o placar de cada jogo restante.
2. **Completar com o modelo** (Vencedor e Placar exato): os jogos sem palpite são sorteados 5.000 vezes, com
   semente fixa, a partir da matriz de placares que o modelo publica. No Vencedor, só o vencedor fica fixo e o
   placar é sorteado dentro dele. O resultado mostra pontos esperados, título, G4 e queda, com a diferença para o
   modelo oficial.
3. Sem "Completar com o modelo", a tabela final é calculada com o Art. 15: pontos, vitórias, saldo, gols marcados
   e confronto direto só entre dois clubes. Empate depois disso fica marcado ("cartões ou sorteio"), sem inventar
   desempate.
4. **O navegador não refaz o modelo.** O snapshot ganhou `matches[].score_probabilities`, a matriz de placares de
   cada jogo restante calculada pelo Python (`pipeline._simulator_scores`). O navegador só sorteia dela.
   Simplificações declaradas na página: a força dos clubes fica a da data de referência (no oficial ela muda a cada
   jogo simulado) e, depois de gols marcados, o desempate é sorteado. A página mede e mostra, a cada snapshot, a
   distância do cálculo sem palpites para o oficial (1,2 p.p. no máximo no snapshot de 26/10/2026).
5. Salvamento só no aparelho (`localStorage`, chave `ainda-da:simulador:serie-a:<temporada>`) e compartilhamento por
   link (`#/simular/<modo>/<código>`). Nada vai para servidor, não há conta nem dado pessoal. Uma simulação aberta
   por link não substitui a do visitante até ele escolher "Salvar como minha"; palpites de jogos que já aconteceram
   são descartados com aviso.
6. Vagas mostradas: 1º a 4º Libertadores (grupos), 5º pré-Libertadores, 6º a 11º Sul-Americana, 17º a 20º
   rebaixados (Art. 6º a 8º). A página avisa que títulos de copas podem empurrar as vagas e que isso não é
   calculado (regra de integridade sobre torneios externos).

### Fase 2 (implementada, desligada até a configuração)

Decisões do dono (chat, 2026-11-07): **Supabase**; entrada **anônima**, com **e-mail pessoal opcional** para trocar de
aparelho; **apelido** para salvar e aparecer, "para não vazar o e-mail da pessoa". A pontuação não foi escolhida;
vale a recomendada (bolão clássico), fácil de trocar em `sim_match_points`.

1. Esquema em `infrastructure/supabase/migrations/0001_simulador.sql`: `sim_seasons`, `sim_matches`, `sim_standings`
   (escritas só pelo CI), `sim_profiles` e `sim_simulations` (cada pessoa só as suas, por RLS).
2. Trava no banco: palpite de jogo trava no pontapé; a ordem da Classificação vale para o ranking só se salva antes
   de `classificacao_locks_at`. Palpites malformados ou de jogos inexistentes são descartados.
3. Pontuação: Placar exato 5/3/2, Vencedor 1, Classificação 3/1 no fim da temporada. Ranking separado por modo, só
   com quem marcou "Aparecer no ranking", identificado pelo apelido.
4. Média dos visitantes por jogo (vencedor) e por clube (posição média, campeão, rebaixado), só com 10 ou mais
   participantes.
5. "Apagar minha participação" apaga conta, perfil e simulações (`sim_delete_me`).
6. O CI sincroniza jogos, tabela e trava a cada publicação (`sync-simulator`), só com `PUBLISH_ENABLED` e com os
   segredos definidos; uma falha nesse passo não derruba o site.
7. Passos para ligar, modelo de privacidade e limitações: `docs/architecture/simulator-supabase.md`. Rascunho do
   aviso de privacidade: `docs/project/privacidade-simulador.md`.

## Consequências

- O `predictions.json` cresce cerca de 70 KB por temporada com jogos restantes. Campo aditivo e opcional: o
  `SNAPSHOT_SCHEMA_VERSION` não muda, e snapshots antigos ficam com `null` (o simulador então desliga "Completar com
  o modelo" e avisa).
- O mesmo componente pode ir para as outras ligas depois, trocando as vagas por competição.

## Versão 2 (2026-11-07, pedido do dono)

Pedido no chat: fluxo explícito por modo, várias simulações com IDs diferentes, chave clara para ligar o modelo
(que sorteia na hora um resultado concreto, não só uma probabilidade), pontuação detalhada do Placar exato,
Classificação sem ordens impossíveis e com bônus de campeão e rebaixados (pontuação atual e máxima possível),
classificação mais provável segundo os visitantes e e-mail para avisos de pontuação. Respostas do dono: até 3
simulações por pessoa e modo entram no ranking ("Todas, com limite"), cada uma com o seu ID; os jogos sorteados pelo
modelo valem pontos.

1. **Fluxo**: `#/simular` mostra os três modos (o que fazer, como pontua, tempo) e "Minhas simulações" (ID, modo,
   data, pontuação). Cada modo tem um editor com rascunho; "Salvar simulação" cria um ID novo e devolve o rascunho
   ao começo; uma simulação salva pode ser editada (`#/simular/{modo}/s/{id}`) ou salva como nova.
2. **Modelo**: chave "Jogos em branco: Deixar em branco | Modelo sorteia". Ligada, sorteia na hora um resultado
   para cada jogo em branco (Vencedor: pelas probabilidades 1X2; Placar exato: pela matriz de placares), mostrado
   tracejado e com a etiqueta "sorteado pelo modelo"; "Sortear de novo" refaz o sorteio; qualquer jogo pode ser
   trocado. O Monte Carlo de 5.000 sorteios da versão 1 saiu.
3. **Pontuação** (navegador e banco, migração `0003`): Placar exato 10 (placar), 7 (vencedor e gols do vencedor),
   6 (vencedor e diferença), 5 (vencedor e gols do perdedor), 4 (só o vencedor ou o empate), 2 (placar invertido);
   Vencedor 4 por acerto, mostrado como "X de Y". Classificação: 3 (posição exata), 1 (uma posição), 10 (campeão),
   3 por rebaixado (máximo 82), mostrada como pontos com a tabela de hoje e teto ainda alcançável (pelas faixas de
   posição que cada clube ainda alcança). A tabela final completa de um Vencedor ou Placar exato também é avaliada
   como Classificação, à parte.
4. **Ordem impossível**: não pode ser salva no navegador (botão desligado, com o motivo) nem no banco
   (`sim_valid_order`, com `points` e `max_points` em `sim_standings`, enviados pelo `sync-simulator`).
5. **Visitantes** (`#/simular/visitantes`, `sim_consensus`): a tabela mais recente de cada pessoa, ordenada pela
   posição média, com % de campeão e de rebaixado; só com 30 ou mais pessoas. A média por jogo (`sim_community`)
   também passou a exigir 30.
6. **E-mail para avisos**: tabela `sim_contacts` (só o dono lê), separada do login. A lista para envio sai de
   `sim_notification_list`, que só a chave de serviço chama (`python -m brasileirao.cli simulator-notifications
   --out <arquivo fora do repositório>`). O envio em si ainda não existe: falta escolher o provedor e confirmar os
   endereços antes do primeiro envio.
7. **Ranking**: uma linha por simulação ("apelido · #ID"), com "pontos de máximo".

