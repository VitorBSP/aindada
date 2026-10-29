# ADR-0012 — Champions League: Elo entre ligas, fase de liga e mata-mata

- Status: **proposto** (2026-10-29). Implementado na `main` local com evidência; publicação depende do parecer
  do 06 e do 00 (AGENTS.md).
- Responsáveis: Agente 00 (decisão), 01 (fontes), 03 (regulamento), 02 (modelo), 04/05 (export e site),
  06 (validação), 07 (workflow), 08 (seletor, D-039).
- Origem: pedido do dono do produto (chat, 2026-10-29): "Sim, começar" a Champions pelo desenho proposto no
  ADR-0011.

## Decisão 1 — Fontes (mesmo princípio aprovado no ADR-0011)

| Temporadas | Fonte | Uso |
|---|---|---|
| 2021/22–2025/26 | openfootball (CC0): 7 ligas (`england`, `espana`, `deutschland`, `italy`, `europe/france`, `europe/netherlands`, `europe/portugal`) e `champions-league` (Champions, Liga Europa e Conference; EL e Conference de 2025/26 não existem no repositório) | ratings e treino do modelo de gols |
| 2026/27 | football-data.org: `CL` e `PL`, `PD`, `BL1`, `SA`, `FL1`, `DED`, `PPL` | ratings e simulação |

- Commit e SHA-256 dos 48 arquivos em `data/reference/europe_source_pins.json`; a composição confere cada um.
- Placar dos 90 minutos para o modelo; prorrogação e pênaltis guardados à parte. Jogo cancelado e resultado dado
  pela organização (W.O.) ficam fora dos ratings (não foram disputados).
- Cadastro `data/reference/clubs_europe.csv` (304 clubes, 48 países), montado por nome normalizado dentro de cada
  país, com 38 fusões revisadas à mão (ex.: "Inter" = "FC Internazionale Milano"; Monaco aparece como MCO nas
  copas e joga a liga francesa) e o id estável do football-data.org (`fd:<id>`) para a temporada corrente. 170
  dos 175 clubes do football-data.org foram ligados pelo cruzamento por data e placar com o openfootball; os 5
  restantes à mão (Fenerbahçe, AEK, LASK; Viking e Sabah sem histórico europeu desde 2021/22).
- Data de referência: último dia com jogo encerrado da Champions; não pode passar da coleta.

## Decisão 2 — Regulamento (Agente 03)

Regulations of the UEFA Champions League 2026/27 (documents.uefa.com, em vigor desde 29/07/2026):
- **Art. 18**: pontos; saldo; gols; gols fora; vitórias; vitórias fora; pontos, saldo e gols dos adversários da
  fase de liga; pontos disciplinares; coeficiente. Sem confronto direto. Os dois últimos viram sorteio (sem dados).
- **Art. 19**: playoff 9/10 x 23/24, 11/12 x 21/22, 13/14 x 19/20, 15/16 x 17/18; oitavas 1/2 x vencedores
  15/16–17/18, 3/4 x 13/14–19/20, 5/6 x 11/12–21/22, 7/8 x 9/10–23/24; quartas A x D e B x C em cada lado da chave;
  o melhor colocado decide em casa (posição herdada por quem elimina). Onde a UEFA sorteia, a simulação sorteia
  com chances iguais.
- Desempate dos confrontos (conferido no resumo da Wikipédia do mata-mata de 2025/26): agregado, sem gol fora,
  prorrogação de 30 minutos e pênaltis; final em jogo único. Pendência do 03: ler o Art. 21 no texto oficial.

## Decisão 3 — Modelo (Agente 02)

- **Elo único** (`europe/ratings.py`): jogos das ligas ordenam os clubes de cada país; as copas europeias ligam os
  países. Mando somado à diferença (zero em campo neutro). Entre temporadas, regressão à média do país. Primeira
  temporada: todo clube de liga começa no valor base; depois, clube novo de liga entra abaixo da média do país e
  clube de país sem outro conhecido entra abaixo do valor base.
- Modelo de gols `elo_only` com dispersão, treinado só com jogos das copas europeias das 4 temporadas anteriores.
- Calibração (`europe.cli tune`): busca coordenada na validação (Champions 2023/24), teste só relatado
  (2024/25 e 2025/26). Escolhidos: K = 30, mando 100, regressão 0,05, recém-chegado −150, país desconhecido −200.
  Vários na borda da grade, mas a superfície é plana (log loss de validação entre 0,9286 e 0,9317 em toda a grade).
- Simulação (`europe/simulation.py`): ratings fixos; fase de liga com o Art. 18; mata-mata com o Art. 19;
  prorrogação com um terço das taxas; pênaltis 50/50. Versão `champions-0.1.0+cmp-elo-ad-0.3.0`.

## Decisão 4 — Site e publicação

`apps/web-champions/` em `/champions-league/`; seletor de competições (D-039) atualizado em todos os sites. No
`publish-site`, a ingestão da Champions entra no passo `Ingestão das ligas europeias` (token só ali) e a
previsão e o gate no passo seguinte, com falha isolada e o mesmo fallback (`gate --standalone`). 8 chamadas ao
football-data.org por execução, com 6,5 s entre elas.

## Evidência e pendências

Ver `docs/methodology/validation.md` (Champions League) e `docs/project/status.md`. Pendências: parecer do 06;
03 confere o Art. 21; EL e Conference 2025/26 quando o openfootball publicar; clubes de países fora das 7 ligas
dependem só dos jogos europeus.
