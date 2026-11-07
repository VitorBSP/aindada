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

## Versão 3: um modo por vez e simulador agregado (2026-11-07, pedido do dono)

Pedido: "uma aba que tu seleciona qual vai fazer, sem poder ficar trocando facilmente, se selecionou tem que
finalizar", UX mais intuitiva, e o simulador agregado com a posição média de todas as simulações.

1. **Sessão única**: escolher um modo cria uma simulação em andamento (`store.active`). Enquanto ela existe, os outros
   modos ficam travados no início ("Termine a simulação em andamento para começar esta"), e um endereço de outro modo
   volta ao início com o aviso. Sair guarda o rascunho no passo em que parou; "Descartar" pede confirmação. As abas
   de modo saíram do topo (ficaram Início, Ranking e Agregado), e o passo a passo esconde abas e painel da conta.
2. **Passo a passo** com indicador de passos: Classificação (Ordenar → Revisar e salvar); Vencedor e Placar exato
   (Como preencher → Rodada por rodada → Revisar e salvar). "Como preencher" oferece "Eu preencho tudo", "Eu preencho
   e o modelo completa" e "O modelo sorteia tudo e eu reviso"; a chave do modelo continua disponível nas rodadas.
   As rodadas vêm uma por vez, com botões por rodada (cheia, parcial, vazia). Salvar leva à página da simulação
   (`#/simular/ver/{id}`), com pontuação, tabela, editar (abre o passo a passo de novo), copiar link e excluir.
3. **Agregado** (`#/simular/agregado`): "As minhas" (média das simulações completas do aparelho, sempre visível) e
   "Todas as simulações do site" (`sim_consensus`, migração `0004`: todas as simulações completas de cada pessoa,
   cada pessoa pesando igual, mínimo de 30 pessoas).
4. Ressalvas do 06 tratadas: D (jogo cancelado fora do máximo de pontos, como no `supabase_sync`), E (depois do
   envio, a cópia local vira o que o servidor guardou), C e F na `0004` (trava contra envios simultâneos; média por
   jogo só com palpites das pessoas, sem os sorteados). Abertas: A (dedução com contas falsas) e B (e-mail de avisos
   sem confirmação).

## Versão 4: cartões (2026-11-07, pedido do dono)

Pedido: "faça algo mais bonito, alguns cards vá escolhendo, coloque mensagens diferentes".

1. **Vencedor e Placar exato**: um cartão por jogo ("Jogo 5 de 61 · Rodada 34 · data"), escudos grandes e uma frase
   do modelo que muda com o jogo ("Favoritaço", "é favorito, mas zebra acontece", "Cheiro de empate", "Jogo
   parelho"). Vencedor: três botões grandes, e o cartão avança sozinho. Placar exato: botões + e − por time, atalhos
   com os 3 placares mais prováveis e "Confirmar placar". Em cada cartão: anterior, pular (deixar em branco),
   "Sortear este" (o modelo sorteia só aquele jogo) e próximo; um mapa recolhível com todos os jogos (seus,
   sorteados, em branco) permite pular para qualquer um e sortear ou tirar todos os sorteados de uma vez. Mensagens
   variam com a escolha (zebra, lógica) e com o progresso ("Metade do caminho!", "Faltam só 5!").
2. **Classificação** em cartões: "Quem leva o título?" (só quem ainda alcança o 1º lugar), "Quem completa o G4?",
   "Quem cai?" (só quem ainda pode cair), depois o ajuste da tabela montada (campeão, G4 e rebaixados no lugar, o meio
   na ordem do modelo) e a revisão.
3. **Revisão** com cartões de destaque (campeão, rebaixados, maior zebra, palpites ousados); ao salvar, uma
   mensagem de comemoração; "Minhas simulações" em cartões com o modo, o ID, a pontuação e onde ela está.
4. Achados do 06 tratados: 1 (a cópia local guarda o que a pessoa escolheu; o aviso diz que palpites de jogos já
   iniciados ficam na simulação, mas não contam para o ranking), 2 (salvar trava durante o envio), 3 (link aberto com
   rascunho em andamento fica guardado, com "Descartar este rascunho e abrir o link"), 5 (sair sem e-mail marca as
   simulações enviadas como de outra participação e não as reenvia; o aviso de sair indica "Apagar minha
   participação" para tirá-las do servidor).

## Versão 5: eventos, trava antes do jogo, posições travadas e chance de tudo junto (2026-11-07, pedido do dono)

Pedidos: "limite a 10 a cada evento novo [...] a cada partida realizada ele pode refazer as simulações. Mas não mudar
as antigas"; "tranque as simulações de uma partida [...] 10, 15 ou 30 minutos antes de ela começar, pense em como
fazer isso"; na Classificação, quem a matemática já pôs no G4 ou no rebaixamento fica travado; "uma probabilidade
geral, de acontecer o campeão, g4 e rebaixamento de cada simulação" e, na Classificação, "uma combinação de
resultados [...] que gerariam aquilo"; "Confirmar placar" no último jogo vira "Revisar"; voltar às simulações
depois de salvar.

1. **Trava 30 minutos antes do pontapé** (`sim_lock_margin`, migração `0005`; `LOCK_MARGIN_MINUTES` no navegador).
   Escolha do Agente 08 entre 10, 15 e 30: a sincronização roda duas vezes por dia, então a margem maior cobre
   relógios e horários que mudam em cima da hora, e o palpite fecha antes de qualquer lance. Sem horário, continua
   00:00 de Brasília do dia. Depois da trava, o cartão do jogo fica sem botões para todos (antes, só não contava para
   o ranking).
   **Jogo adiado fica aberto** (pedido do dono, "esse jogo ainda vai ser jogado"): sem placar mais de 7 dias depois
   da data marcada (mesma regra do site), o `supabase_sync` envia o jogo como `postponed` e sem horário, e a `0005`
   deixa `sim_keep_match_lock` tirar a trava antiga só nesse caso (jogo sem placar). Quando a data nova chega, a trava
   volta a valer. Risco para o 06: um jogo disputado cujo placar demore mais de 7 dias na fonte seria reaberto.
2. **Evento** é cada trava de jogo (`sim_event_start`: a trava mais recente que já passou).
3. **Limite**: até 10 simulações novas por pessoa (somando os três modos) desde o último evento. Sai o limite de 3 por
   modo na temporada. No aparelho não há limite: a que passar das 10 fica só no aparelho, com aviso.
4. **Simulação fechada**: salva antes do último evento, não pode mais ser editada (pode ser excluída). O banco recusa
   a alteração (`P0001`, "simulação fechada"), e a página mostra "fechada" no lugar de "Editar".
5. **Classificação**: no passo do campeão, do G4 e do rebaixamento, entra marcado e não sai o clube que a matemática
   já pôs naquela faixa (pior posição possível ≤ 4 para o G4; melhor posição possível ≥ 17 para o rebaixamento) **e**,
   por decisão do dono (chat, 2026-11-07, "Travar os 100% também"), o que ficou nela em todas as simulações do modelo.
   A etiqueta diz qual dos dois ("garantido no G4 pela matemática" ou "no G4 em todas as N simulações"); a página não
   chama de certeza o que é só 100% das simulações. No ajuste fino, tirar um clube travado da faixa bloqueia o avanço,
   com o motivo na linha. O banco não confere essa trava (é escolha de interface, não regra de pontuação).
6. **Chance de tudo junto** na revisão e na simulação salva, nos três modos (Vencedor e Placar exato quando completos):
   chance do campeão, do G4 (em qualquer ordem), dos rebaixados e dos três juntos, em 20.000 campeonatos sorteados das
   chances publicadas de cada jogo (o navegador só sorteia, como na versão 1; força fixa e empate sem critério
   sorteado, avisados na página). Na Classificação, "um caminho possível": os resultados (vitória, empate, derrota) do
   sorteio mais provável entre os que chegam à combinação; se nenhum chega, um caminho achado puxando os resultados a
   favor dela, com aviso. Abaixo de 1 em 20.000 aparece como "menos de 1 em 20.000".
7. **Placar exato**: no último jogo, o botão é "Revisar": guarda o placar, se houver, e vai para a revisão.
8. **Voltar**: a simulação salva tem "← Minhas simulações" e o botão "Minhas simulações" (`#/simular/minhas`).
9. Ordem de publicação: aplicar `0005` no Supabase antes de publicar o site; sem ela, o banco continua com o limite
   de 3 por modo e a trava no pontapé.
10. **Classificação sem trava da temporada e pontuação nova** (pedidos do dono: "não faz sentido essa trava [...] a
    pontuação ser por partidas que ainda tinha a realizar quando ele fez a classificação"; "dê pontuação extra para o
    G4, aumente a pontuação do rebaixado [...] crie o deflator"; "Deixe 3 para o vencedor só [...] Se acertar o empate
    pontua 5"; migração `0006`).
    - Toda Classificação salva entra no ranking (`classificacao_locks_at` deixa de ser usado).
    - Classificação: 3 por posição exata, 1 a uma posição, 10 pelo campeão, **3 por clube do G4 acertado** (em
      qualquer ordem), **5 por rebaixado**: máximo 102, com a tabela de hoje (provisória até o fim).
    - **Deflator**: × (jogos que ainda faltavam no último salvamento ÷ jogos da temporada). Ex.: 70 pontos × 61/380 =
      10,6. O banco guarda pontos × jogos que faltavam (inteiro, mesma ordem); a página divide pelo total.
    - Vencedor: **3 por vitória certa, 5 por empate certo**. Placar exato: 10, 7, 6, 5 (gols do perdedor), **5 por
      empate certo sem o placar**, **3 só o vencedor**, 2 invertido. O máximo de cada palpite depende dele
      (`sim_pick_max`).
