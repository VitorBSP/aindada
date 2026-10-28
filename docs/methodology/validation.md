# Validação e backtesting (Agente 06)

Relatório completo e reprodutível: `data/gold/backtest_report.json`, gerado por
`python -m brasileirao.cli backtest --simulations 10000` (semente 7) sobre o gold de **publicação**
do ADR-0008: `adaoduque_kaggle@kaggle-v18` (2003–2025) + `football_data_org@v4-20261027T205022Z`
(2026), 9.545 jogos. Modelo `cmp-elo-ad-0.3.0`. As tabelas de partidas e de temporadas abaixo são
desse relatório. As seções de 2026-10-26 e 2026-10-27 (etapa 2, deslocamento de data, dispersão)
foram medidas sobre os dados anteriores (`brasileirao_dataset`, 2.000 simulações) e ficam como
histórico. A comparação e as decisões novas estão em "Passo 11 do ADR-0008" (fim do arquivo).

## Desenho

| Etapa | Temporadas | Uso |
|---|---|---|
| Treino do modelo de gols | as 10 anteriores à temporada avaliada (a partir de 2006) | regressões Poisson e ρ de Dixon-Coles |
| Validação | 2013–2018 | escolha de hiperparâmetros dos ratings e do conjunto de variáveis |
| Teste | 2019–2025 (2.660 jogos) | métricas reportadas |

- As features pré-jogo vêm do processamento online: cada jogo só "vê" partidas anteriores.
- Jogos da mesma data usam o estado da véspera (sem vazamento intradia).
- Nenhuma divisão aleatória de partidas é usada.
- Seleção: menor log loss na validação. Diferenças de até 0,001 favorecem o modelo mais simples.

## Hiperparâmetros escolhidos (busca coordenada na validação)

| Parâmetro | Grade | Escolhido |
|---|---|---|
| Elo K | 6, 8, 10, 15, 20, 30 | 10 |
| Elo mando (pontos) | 50, 80 | 50 |
| Elo regressão entre temporadas | 0,15, 0,3, 0,5 | 0,3 |
| Ataque/defesa taxa de aprendizado | 0,015, 0,03, 0,05 | 0,015 |
| Ataque/defesa regressão entre temporadas | 0,15, 0,3, 0,5 | 0,15 |
| Forma (span em jogos) | 2, 3, 6, 12 | 2 |

As diferenças entre combinações vizinhas são pequenas (até ~0,002 de log loss). Por isso o modelo é
pouco sensível a esses parâmetros. No gold de publicação a escolha é a mesma, com os mesmos log loss
de validação até a 15ª casa (validação 2013–2018 tem os mesmos placares e datas nas duas fontes).

## Partidas — teste 2019–2025 (menor é melhor)

| Modelo | Log loss | Brier | RPS |
|---|---|---|---|
| Taxa-base (frequências 1X2 do treino) | 1,0610 | 0,6403 | 0,2210 |
| Poisson sem variáveis | 1,0601 | 0,6397 | 0,2207 |
| Elo | 1,0220 | 0,6131 | 0,2078 |
| Ataque/defesa | 1,0228 | 0,6135 | 0,2082 |
| **Elo + ataque/defesa (escolhido)** | **1,0213** | **0,6126** | **0,2078** |
| Elo + ataque/defesa + forma | 1,0208 | 0,6123 | 0,2076 |
| Escolhido sem Dixon-Coles | 1,0212 | 0,6126 | 0,2077 |

Leitura:
- Ganho claro sobre os benchmarks (−3,7% de log loss em relação à taxa-base).
- A variável de forma melhora 0,0005, abaixo da tolerância de parcimônia na validação. Ficou fora.
- Dixon-Coles não trouxe ganho (ρ estimado ≈ +0,02). Está mantido no código como Modelo B, mas não é
  justificável pelas métricas; ver ADR-0006.
- Empates: previstos 26,1% e observados 27,3%. Há uma leve subestimação de empates. A correção foi
  avaliada na etapa 2 (abaixo) e não foi adotada.

Por temporada (modelo escolhido):

| Temporada | Log loss | Brier | RPS |
|---|---|---|---|
| 2019 | 0,9804 | 0,5842 | 0,1976 |
| 2020 | 1,0427 | 0,6292 | 0,2119 |
| 2021 | 1,0391 | 0,6262 | 0,2085 |
| 2022 | 1,0253 | 0,6140 | 0,2067 |
| 2023 | 1,0364 | 0,6221 | 0,2161 |
| 2024 | 1,0235 | 0,6132 | 0,2096 |
| 2025 | 1,0020 | 0,5993 | 0,2038 |

Calibração (erro de calibração esperado, 10 faixas): mandante 1,4 p.p., empate 1,2 p.p.,
visitante 1,6 p.p.

## Temporadas — snapshots históricos (rodadas 10, 19 e 28, 10.000 simulações)

O estado de cada checkpoint é reconstruído do zero com `build_state_as_of`. A primeira versão
reaproveitava o estado entre checkpoints e, com jogos adiados (2021, 2024), incluía partidas futuras.
O defeito foi apontado na revisão do Agente 06, corrigido, e os números abaixo já são os corrigidos.
A escolha entre ratings dinâmicos e fixos é feita nas temporadas de **validação** e reportada no
teste.

| Métrica (média) | Validação 2013–2018: dinâmico | Validação: fixo | Teste 2019–2025: dinâmico | Teste: fixo |
|---|---|---|---|---|
| Brier título (por clube) | 0,0164 | 0,0154 | 0,0292 | 0,0294 |
| Brier G4 | 0,0554 | 0,0538 | 0,0685 | 0,0683 |
| Brier rebaixamento | 0,0934 | 0,0940 | 0,0897 | 0,0912 |
| Log loss da posição final | 2,265 | **2,257** | **2,213** | 2,232 |
| Erro absoluto médio dos pontos finais | 4,71 | 4,71 | 5,12 | 5,12 |
| Cobertura do intervalo de 90% dos pontos | **91,7%** | 87,5% | **86,4%** | 83,3% |

Leitura (gold de publicação, `cmp-elo-ad-0.3.0`): na validação, ratings **fixos** têm log loss de
posição menor; a regra do código (menor log loss de posição na validação) os escolhe, e a média de
seis sementes confirma o sinal (+0,0027 a favor dos fixos, erro-padrão 0,0016; ver "Passo 11").
Estão em produção (`dynamic_ratings_in_simulation: false`). O custo é conhecido: os ratings
dinâmicos cobrem melhor o intervalo de 90% nos dois períodos e têm log loss de posição menor no
teste. Com os dados anteriores e 2.000 simulações a escolha era a oposta (dinâmico 2,261 × fixo
2,268), o que mostra que a diferença está no nível do ruído de Monte Carlo. No teste, a cobertura
fica abaixo de 90% nos dois modos, o que indica excesso de confiança.

Limitação: o backtest de temporada avalia título, G4 e rebaixamento, que independem das regras
continentais. Para temporadas antigas foram usadas as regras de desempate de 2026.

## Etapa 2 (2026-10-26): inflação de empates e incerteza de parâmetros

Gerado por `python -m brasileirao.cli backtest` (2.000 simulações, semente 7). Mesmo desenho de
validação/teste, mesmos 18 checkpoints de validação e 21 de teste. Seções do relatório:
`season_simulation.draw_inflation` e `season_simulation.uncertainty`. Os critérios foram fixados
antes de rodar o relatório.

### Diagnóstico dos empates

Poisson independente subestima empates **dentro da própria amostra de treino** (taxa prevista
1,5–2 p.p. abaixo da observada em todas as janelas de 2013 a 2025). Não se trata, portanto, só de
mudança entre períodos. Correção avaliada: multiplicar a diagonal da matriz de placares por
`1 + δ` e renormalizar, com δ estimado por máxima verossimilhança do placar em cada janela de treino
(`GoalsModel.fit_draw_inflation`). Os δ estimados caíram de 0,13 (janela de 2013) para 0,01–0,07
(janelas de 2019–2025).

| Partidas, teste 2019–2025 | Log loss | Brier | RPS | Empates previstos |
|---|---|---|---|---|
| Modelo escolhido | 1,0213 | 0,6126 | 0,2077 | 26,1% |
| Modelo escolhido + inflação de empates | 1,0211 | 0,6125 | 0,2078 | 26,9% |
| Observado | | | | 27,3% |

Na validação, o log loss das partidas foi de 1,01324 para 1,01341 com a inflação (piora de
0,0002, dentro da tolerância).

| Temporadas, log loss da posição final | Validação | Teste |
|---|---|---|
| Sem inflação | **2,2614** | **2,2144** |
| Com inflação | 2,2665 | 2,2167 |

**Decisão: não adotada.** Regra: o log loss das partidas na validação não pode piorar mais que
0,001 e o log loss da posição na validação tem que melhorar mais que 0,001. A segunda condição
falhou. A inflação corrige o viés da **taxa média** de empates (−1,2 → −0,4 p.p.), mas não melhora
nenhuma métrica própria, nem de partidas nem de temporada. Conclusão: o empate a mais é
praticamente imprevisível jogo a jogo com estas variáveis. O resíduo de calibração de empates
(ECE 1,2 p.p.) permanece.

### Propagação de incerteza

Duas fontes, implementadas em `SimulationUncertainty` (`config.py`) e aplicadas por simulação:

- **Coeficientes do modelo de gols**: sorteio da normal assintótica (inversa da informação de
  Fisher da regressão Poisson, com a penalização L2). Os erros-padrão analíticos foram conferidos
  contra 200 reamostragens bootstrap (janela 2016–2025, 3.799 jogos) e ficaram de 5% a 20% acima
  dos bootstrap, ou seja, levemente conservadores.
- **Força latente por clube**: deslocamento N(0, sd²) na escala log dos gols, fixo ao longo da
  temporada simulada (`+s_mandante − s_visitante` no gol do mandante e o inverso no do visitante).
  Representa o erro do rating no início da simulação.

Os sorteios de incerteza usam geradores próprios derivados da semente. O fluxo dos placares é o
mesmo em todas as variantes (números aleatórios comuns), então as diferenças entre linhas não são
ruído de Monte Carlo independente. Para referência, o log loss de posição da configuração base
varia ~0,0025 entre sementes.

| Variante | Validação: log loss posição | Validação: cobertura 90% | Teste: log loss posição | Teste: cobertura 90% | Teste: Brier rebaixamento |
|---|---|---|---|---|---|
| **Sem incerteza (escolhida)** | **2,2614** | 91,7% | 2,2144 | 86,9% | 0,0892 |
| Coeficientes sorteados | 2,2701 | 91,7% | 2,2115 | 86,7% | 0,0894 |
| Força latente sd 0,025 | 2,2648 | 91,7% | 2,2138 | 87,9% | 0,0894 |
| Força latente sd 0,05 | 2,2768 | 92,2% | 2,2151 | 88,6% | 0,0888 |
| Força latente sd 0,075 | 2,2730 | 93,9% | 2,2140 | 90,0% | 0,0883 |
| Força latente sd 0,10 | 2,2875 | 94,4% | 2,2148 | 91,4% | 0,0881 |

**Decisão: nenhuma incerteza adicional em produção** (menor log loss de posição na validação, com
parcimônia). O que os números mostram:

- Na validação (2013–2018), o modelo **não** era excessivamente confiante: a cobertura já era
  91,7%. Qualquer incerteza extra piora o log loss de posição.
- No teste (2019–2025), a força latente com sd entre 0,075 e 0,10 levaria a cobertura para 90–91%
  **sem** piorar o log loss de posição (2,2140–2,2148 contra 2,2144) e com Brier de rebaixamento
  ligeiramente melhor. Adotar com base nisso seria escolher pelo teste, o que viola o protocolo.
- A incerteza dos coeficientes é pequena (com ~3.800 jogos de treino) e não muda a cobertura. O
  excesso de confiança de 2019–2025 vem da força dos clubes, não dos coeficientes, e parece ser uma
  mudança entre períodos (temporadas recentes menos previsíveis que 2013–2018).

### Origem móvel para a força latente (2026-10-26)

Para deixar o período recente informar a escolha sem usar o teste, cada temporada de teste S usou a
variante com menor log loss de posição nas 6 temporadas anteriores (S − 6 a S − 1), com a mesma regra
de parcimônia. As simulações são as mesmas da tabela acima (mesmos checkpoints e números aleatórios
comuns); só muda a regra de escolha. Relatório: `season_simulation.uncertainty.rolling_origin`.

| Temporada de teste | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| Variante escolhida | nenhuma | nenhuma | sd 0,025 | nenhuma | coeficientes | coeficientes | sd 0,10 |

| Teste 2019–2025 | Log loss posição | Cobertura 90% | Brier título | Brier rebaixamento |
|---|---|---|---|---|
| Sem incerteza (validação fixa) | **2,2144** | 86,9% | 0,0288 | 0,0892 |
| Origem móvel (6 temporadas) | 2,2205 | 87,6% | 0,0289 | 0,0890 |

**Decisão: não adotada.** A escolha oscila de ano para ano, o log loss de posição piora 0,006 e a
cobertura sobe só 0,7 p.p. Com 3 checkpoints por temporada, as diferenças entre variantes dentro de
uma temporada (±0,03 de log loss) estão no nível do ruído, então a janela de 6 temporadas não
consegue distinguir as opções. Para 2026 a regra escolheria "coeficientes", o que não muda a
cobertura. Produção segue sem incerteza adicional.

Caminhos que ainda podem resolver o excesso de confiança de 2019–2025: mais checkpoints por
temporada (todas as rodadas, não só 10, 19 e 28) para reduzir o ruído da escolha, ou um modelo de
força com variância própria por clube (por exemplo, filtro de Kalman) em vez de um sd global.

## Deslocamento de data UTC na fonte atual (2026-10-27)

Achado do Agente 01 (`docs/data-sources/c1-fonte-licenciada.md`, seção 8): em 2024–2026 a fonte
atual grava a data do dia UTC do pontapé inicial. Jogos a partir das 21h de Brasília ficam com a
data do dia seguinte. Na base gold, 208 linhas estão deslocadas em +1 dia: 186 encerradas (71 em
2024, 67 em 2025 e 48 em 2026) e 22 agendadas de 2026. Nenhum jogo tem data armazenada **anterior**
à real. A reexecução foi feita localmente, com as datas corrigidas para `America/Sao_Paulo` fora do
repositório, sem alterar dados nem código.

**Vazamento: não há.** Todos os cortes usam `match_date <= data de referência`
(`ratings/history.py:221`, `simulation/engine.py:55`, `pipeline.py:306`,
`data_pipeline/ingest.py:133`, `simulation/round_review.py:142`). Como a data armazenada nunca é
anterior à real, um jogo dentro do corte sempre aconteceu de fato até aquela data. O erro só exclui
jogos ou atrasa o rótulo da data. Isso é conservador. Datas de referência derivadas da própria
coluna (`pipeline.py:397` e `:410`, `validation/backtest.py:214` e `round_review.py:120`) ficam um
dia depois do real, mas o conjunto observado continua consistente com o rótulo. Os ratings processam
cada data em lote com o estado da véspera (`ratings/history.py:186`), então mudar o dia de um jogo
não deixa outro jogo ver o resultado dele antes da hora.

| Efeito medido | 2024 | 2025 | 2026 |
|---|---|---|---|
| Checkpoints do backtest (rodadas 10, 19, 28) com data de referência +1 dia | 1 de 3 | 1 de 3 | — |
| Checkpoints com algum jogo do lado errado do corte | 0 | 0 | — |
| Visões do review-rounds com data de corte diferente | 4 | 4 | 3 |
| Visões que deixam de fora um jogo já disputado até a data do rótulo (jogos) | 5 (7) | 4 (5) | 3 (3) |
| Visões cujo conjunto de jogos muda após a correção | 2 | 0 | 0 |
| Pontos do probability-history com data diferente | 9 de 37 | 6 de 36 | 6 de 32 |
| Pontos do probability-history que deixam de fora um jogo já disputado | 2 | 1 | 0 |

Backtest completo reexecutado com as datas originais (reproduz o relatório gold) e com as
corrigidas, mesmas sementes:

- Validação 2013–2018, hiperparâmetros, conjunto de variáveis, inflação de empates e incerteza:
  **idênticos**. As decisões do modelo não mudam.
- Partidas, teste 2019–2025, modelo escolhido: log loss 1,02133 → 1,02134 (+0,000006) e RPS sem
  mudança na 5ª casa. Em 2024 o log loss vai de 1,02346 para 1,02348 e em 2025 de 1,00193 para
  1,00196. A maior mudança de probabilidade por jogo é 0,0013.
- Temporada (42 registros de checkpoint): log loss de posição 2,2144 → 2,2143, MAE de pontos
  5,111 → 5,115 e cobertura de 90% igual (86,9%). Os 12 registros de 2024–2025 variam até ±0,10 cada,
  em direções opostas. É ruído de Monte Carlo: os jogos restantes são ordenados por data
  (`simulation/engine.py:57`), e a ordem muda quais números aleatórios cada jogo recebe.

**Parecer: aprovado com ressalvas. Não bloqueia a migração de fontes.** O efeito nas métricas é
desprezível e não há vazamento. Ressalvas:

1. O `FootballDataOrgSource` não pode usar a data UTC (`data_pipeline/sources.py:218`). A conversão
   para `America/Sao_Paulo` é critério de aceite do adaptador. Com a fonte atual, 2026 seguiria
   deslocada até a troca.
2. Os rótulos de data errados aparecem para o usuário: datas de jogos na API/frontend, a data de
   referência do snapshot quando o último jogo é noturno e as datas do review-rounds e do
   probability-history. Depois da migração, o review-rounds e o probability-history de 2024–2026
   precisam ser regenerados.
3. Não foi verificado se a fonte de 2003–2023 tem o mesmo problema (validação 2013–2018 e teste
   2019–2023). O football-data.org só foi consultado para 2024–2026.

Teste de regressão pedido ao 01, junto com o adaptador:

- `utcDate` `2026-10-27T00:30:00Z` (21h30 de Brasília) gera `match_date` 2026-10-26, e
  `2026-10-26T23:00:00Z` (20h) também gera 2026-10-26.
- Um caso de horário de verão histórico (UTC−2, por exemplo novembro de 2018) converte corretamente.
- Na qualidade dos dados, nenhuma partida `finished` pode ter `match_date` posterior à data de coleta
  em Brasília, e um snapshot não pode ter jogo `finished` com data posterior à `reference_date`.
- Na conferência local de 2024–2025 entre a fonte nova e o football-data.org, deve haver zero
  divergências de data entre jogos encerrados.

## Testes automatizados

`pytest` (2026-10-27): 204 testes passando, nenhum pulado (regras, desempate, ratings, modelo, métricas,
invariantes da simulação, seleção de modelo, dados, pipeline, snapshots e API). Os invariantes cobertos incluem: 380 jogos por
temporada, posições como permutação, P(título) somando 1, P(rebaixamento) somando 4, 6 vagas de
Sul-Americana por cenário, reprodutibilidade por semente, independência da ordem de jogos
simultâneos e ausência de dados posteriores à data de referência. Na etapa 2 entraram: inflação
de empates, covariância e sorteio de coeficientes, incerteza desligada reproduzindo a execução
padrão, força latente ampliando a dispersão de pontos e regras de parcimônia.

## Distribuição de gols e dispersão (Agente 02, 2026-10-27)

Pedido do dono do produto: "inflar" o número de gols, porque o placar mais provável de quase todos
os jogos restantes é 1×0, 1×1 ou 0×1. O critério combinado com o 00: ajustar só se o backtest
mostrar viés, com parâmetro estimado nos dados, e só adotar se as métricas 1X2 não piorarem.

Gerado por `python -m brasileirao.cli backtest` (2.000 simulações, semente 7), seções
`goal_distribution` e `season_simulation.goal_dispersion` do relatório. A partir desta entrega o
relatório também traz `score_log_loss` (placar exato) e `total_goals_log_loss` (total de gols) em
todas as métricas de partidas. Os dados são os mesmos do snapshot publicado em 2026-10-27
(`brasileirao_dataset@838614d`). Previsões fora da amostra: a temporada S usa modelo treinado só
com S − 10 a S − 1, e as variáveis de cada jogo só veem jogos anteriores. Para 2026, o corte é
2026-10-26 (319 jogos).

### Diagnóstico: previsto × observado (modelo em produção até aqui, Poisson + Dixon-Coles)

Percentuais, exceto as médias e variâncias. "Pearson" é a média de (y − μ)² / Var prevista: abaixo
de 1, os gols variam menos que o modelo supõe.

| Medida | Validação 2013–2018 (2.279) | Teste 2019–2025 (2.660) | 2026 até 26/10 (319) |
|---|---|---|---|
| Gols por jogo, total | 2,485 / 2,350 | 2,381 / 2,406 | 2,546 / 2,661 |
| Gols do mandante | 1,518 / 1,434 | 1,414 / 1,403 | 1,480 / 1,527 |
| Gols do visitante | 0,967 / 0,916 | 0,967 / 1,003 | 1,067 / 1,135 |
| Variância do total | 2,52 / 2,38 | 2,42 / 2,33 | 2,57 / 2,19 |
| Pearson mandante / visitante / total | 0,85 / 0,94 / 0,95 | 0,88 / 0,99 / 0,96 | 0,81 / 0,89 / 0,90 |
| Total 0 gols | 8,9 / 9,0 | 9,3 / 8,3 | 7,7 / 5,3 |
| Total 1 gol | 19,8 / 24,1 | 22,3 / 21,9 | 20,4 / 16,6 |
| Total 2 gols | 26,1 / 24,9 | 25,9 / 25,8 | 25,1 / 27,3 |
| Total 3 gols | 21,2 / 21,4 | 20,6 / 23,5 | 21,4 / 25,4 |
| Total 4 gols | 13,2 / 11,9 | 12,3 / 11,7 | 13,7 / 12,9 |
| Total 5+ gols | 10,8 / 8,8 | 9,5 / 8,9 | 11,6 / 12,5 |
| Mais de 1,5 | 71,3 / 67,0 | 68,3 / 69,9 | 71,8 / 78,1 |
| Mais de 2,5 | 45,2 / 42,1 | 42,4 / 44,0 | 46,7 / 50,8 |
| Mais de 3,5 | 24,0 / 20,7 | 21,8 / 20,5 | 25,3 / 25,4 |
| 0×0 | 8,9 / 9,0 | 9,3 / 8,3 | 7,7 / 5,3 |
| 1×0 | 12,1 / 15,7 | 13,0 / 13,5 | 11,7 / 10,7 |
| 0×1 | 7,7 / 8,4 | 9,3 / 8,4 | 8,8 / 6,0 |
| 1×1 | 12,5 / 11,9 | 12,1 / 13,5 | 11,8 / 15,7 |
| 2×0 | 9,6 / 9,4 | 9,2 / 8,0 | 8,6 / 9,7 |
| 2×1 | 9,0 / 9,7 | 8,5 / 10,5 | 8,7 / 12,2 |
| 1×2 | 5,9 / 5,5 | 6,0 / 7,0 | 6,5 / 8,5 |
| 2×2 | 4,3 / 4,8 | 4,0 / 4,8 | 4,6 / 5,0 |
| Empates | 26,5 / 26,2 | 26,1 / 27,3 | 24,9 / 27,9 |

Por time, no teste (previsto / observado): mandante com 0, 1, 2, 3, 4 e 5+ gols em 25,5/23,4,
33,8/35,9, 23,4/24,7, 11,3/10,9, 4,3/3,8 e 1,9/1,3; visitante em 38,7/36,0, 36,1/37,9, 17,5/18,9,
5,8/5,1, 1,5/1,5 e 0,4/0,6.

Leitura:

- **Média de gols: sem viés sistemático.** No teste o modelo prevê 2,381 gols por jogo para 2,406
  observados (−1%, z = +0,86 com a variância do modelo). Na validação ele **superestima** (2,485 contra
  2,350). Em 2026 subestima 0,116 gol por jogo (−4%), mas com 319 jogos isso dá z = +1,29, e Mais de
  2,5 dá z = +1,47: dentro do ruído. De 2022 a 2025 o observado ficou acima do previsto em todas as
  temporadas (+0,03 a +0,08), cada uma com |z| < 1,1. É um sinal fraco de tendência, a acompanhar.
- **Não há superdispersão.** A variância observada é **menor** que a prevista nos três períodos, e
  a dispersão de Pearson fica abaixo de 1. A binomial negativa ajustada por máxima verossimilhança
  nas janelas de treino de 2013, 2019 e 2026 cai no limite α = 0 (Poisson). Gols por time são
  levemente **subdispersos**.
- **As caudas estão superestimadas, não subestimadas**: 5+ gols por time e 4+ no total saem acima do
  observado. Faltam jogos com 2 a 3 gols (2×1, 1×2, 1×1, 2×2) e sobram 0×0 e goleadas. É o padrão
  da subdispersão.

### Ajustes avaliados (mesmas temporadas, previsões de partidas)

Métricas: log loss 1X2, log loss do placar exato e log loss do total de gols.

| Ajuste (parâmetro escolhido nos dados) | Validação: 1X2 / placar / total | Teste: 1X2 / placar / total | Resultado |
|---|---|---|---|
| Nenhum (produção até aqui) | 1,01324 / 2,72522 / 1,79554 | 1,02133 / 2,73797 / 1,78224 | referência |
| Peso decrescente por temporada no treino, ξ = 0,05 a 1 | 1X2 piora em toda a grade (até 1,01707) | piora em todas | não adotado |
| Janela de treino de 3, 5, 7 ou 15 temporadas | 1X2 1,01320 a 1,01655 | 1X2 1,02116 a 1,02207 | sem ganho consistente |
| Taxa global de nível dos ratings, 0 a 0,016 | 1X2 1,01223 a 1,01324; placar piora | 1X2 1,02089 a 1,02141; placar piora | sem ganho consistente |
| Fator de escala fixo nos gols esperados | a validação pede **0,96** (menos gols) | 0,96 piora placar e total | rejeitado: "inflar" pioraria a validação |
| Inflação das células 1×0 e 0×1 (ML no treino) | 1,01286 / 2,72286 | 1,02174 / 2,73797 | 1X2 piora no teste |
| Inflação das células 2×1 e 1×2 (ML no treino) | 1,01309 / 2,72528 | 1,02172 / 2,73614 | 1X2 piora no teste |
| **Dispersão (Conway-Maxwell-Poisson, ν por ML no treino)** | **1,01303 / 2,72375 / 1,79575** | **1,02093 / 2,73443 / 1,78140** | **adotado** |

O ν estimado em cada janela de treino sobe de 1,05 (2013) para 1,17 (2025 e 2026). Teste de razão de
verossimilhança no treino: 2,5 (2013) a 29,3 (2026), significativo a 5% (3,84) a partir da janela
de 2015. Ganho pareado no log loss do placar exato: −0,0015 (erro-padrão 0,0007) na validação,
−0,0035 (0,0015) no teste e −0,016 (0,005) em 2026. Ganho no log loss 1X2: −0,0002 (0,0002),
−0,0004 (0,0003) e −0,0021 (0,0011).

| Partidas | Log loss 1X2 | Brier | RPS | Log loss placar | Log loss total |
|---|---|---|---|---|---|
| Validação, Poisson | 1,01324 | 0,60665 | 0,20691 | 2,72522 | 1,79554 |
| Validação, dispersão | **1,01303** | **0,60652** | **0,20685** | **2,72375** | 1,79575 |
| Teste, Poisson | 1,02133 | 0,61260 | 0,20775 | 2,73797 | 1,78224 |
| Teste, dispersão | **1,02093** | **0,61241** | **0,20768** | **2,73443** | **1,78140** |
| 2026 até 26/10, Poisson | 1,01371 | 0,60759 | 0,20289 | 2,78932 | 1,80967 |
| 2026 até 26/10, dispersão | **1,01158** | **0,60663** | **0,20252** | **2,77304** | **1,80443** |

Com a dispersão, a média prevista não muda (por construção), e a variância prevista do total fica
mais perto da observada. No teste vai de 2,42 para 2,25, contra 2,33 observado. As frequências por
total se aproximam do observado: no teste, 0 gols vai de 9,3 para 8,4 (observado 8,3), 3 gols de
20,6 para 21,4 (23,5) e 5+ de 9,5 para 8,8 (8,9). Mais de 1,5 passa de 68,3 para 69,5 (69,9) e Mais
de 2,5 de 42,4 para 42,7 (44,0). Placares: 1×1 de 12,1 para 13,1 (13,5), 2×1 de 8,5 para 9,2 (10,5)
e 0×0 de 9,3 para 8,4 (8,3). A taxa de empates prevista vai de 26,1% para 26,4% (27,3%).

### Regra de adoção e nível de temporada

Regra fixada no código antes de rodar o relatório (`select_goal_dispersion`). Na validação: o log
loss 1X2 não piora, o log loss do placar exato melhora mais que 0,001, e o log loss da posição final
(simulação da temporada) não piora mais que 0,001.

| Temporadas, ratings dinâmicos | Validação: log loss posição | Validação: cobertura 90% | Teste: log loss posição | Teste: cobertura 90% |
|---|---|---|---|---|
| Poisson, 2.000 simulações (relatório) | 2,2614 | 91,7% | 2,2144 | 86,9% |
| Dispersão, 2.000 simulações (relatório) | 2,2612 | 91,7% | 2,2277 | 86,9% |
| Diferença com 10.000 simulações, semente 7 | −0,0052 (ep 0,0017) | | +0,0053 (ep 0,0029) | |
| Diferença com 10.000 simulações, semente 11 | +0,0004 (ep 0,0027) | | −0,0007 (ep 0,0019) | |

Entre as variantes, os Brier de título, G4 e rebaixamento mudam no máximo 0,0007 e o erro médio dos
pontos no máximo 0,01.

**Decisão: adotada** (`model_config.json`: `goal_dispersion: true`; `MODEL_VERSION` =
`cmp-elo-ad-0.2.0`). As três condições valem na validação. No teste, todas as métricas de partidas
melhoram. No nível de temporada a diferença é ruído de Monte Carlo. Com 2.000 simulações o teste
mostrou +0,013, mas com 10.000 simulações e duas sementes a média é +0,002 no teste e −0,002 na
validação, com erros-padrão de 0,002 a 0,003. Com 2.000 simulações, só trocar a semente ou a ordem
dos sorteios já desloca o log loss de posição em até ~0,015.

As linhas de 10.000 simulações foram rodadas fora do comando `backtest`, com os checkpoints do
relatório. Rodaram sobre o gold de publicação (mesmos placares, ver abaixo), então não somam com as
linhas de 2.000.

O que **não** foi feito: nenhum fator para aumentar a média de gols. A validação pede o contrário
(escala 0,96), e no teste a média já está calibrada. A dispersão não aumenta os gols esperados. Ela
tira probabilidade de 0×0, de jogos de 1 gol e das goleadas e a passa para 1×1, 2×1, 1×2 e totais de
2 a 3 gols. Por isso o placar mais provável continua baixo e fica **mais vezes** 1×1. Nos 61 jogos
restantes de 2026, a moda 1×1 passa de 31 para 43 jogos. A probabilidade da moda fica entre 11% e
14%.

### Achado lateral: rerun sobre a ingestão de publicação

O backtest também foi rodado sobre o gold novo do ADR-0008 (Adão Duque v18 + football-data.org),
gravado durante esta sessão pelo 01. Os placares são os mesmos, mas `match_id` e algumas datas
mudaram. As métricas de partidas ficaram iguais até a 5ª casa. As decisões de temporada com 2.000
simulações **mudaram**:

- dinâmico × fixo na validação: 2,2708 × 2,2538, o que inverteria para ratings fixos;
- a dispersão falharia na terceira condição (2,2619 × 2,2538, com ratings fixos);
- a origem móvel passaria a escolher força latente sd 0,075 para 2023–2026.

A causa é a ordem dos sorteios (`remaining` é ordenado por data e `match_id`), não a informação dos
dados. Esse relatório **não** foi adotado: `data/gold/` ficou com o relatório dos dados do snapshot
publicado, que reproduz exatamente as decisões anteriores. A cópia do rerun ficou fora do
repositório. Antes do passo 11 do ADR-0008, as escolhas de temporada precisam de mais simulações (ou
mais checkpoints) para que a decisão não dependa da ordem dos IDs (ver `status.md`). Feito no passo 11
(seção abaixo): 10.000 simulações e seis sementes.

## Passo 11 do ADR-0008: backtest sobre o gold de publicação (Agente 02, 2026-10-28)

O `data/gold/backtest_report.json` versionado (que vira o `metrics.json` do site) ainda era o
relatório sobre os dados do `brasileirao_dataset`. Ele foi refeito sobre o gold de publicação
(Adão Duque v18 2003–2025 + football-data.org 2026, `sources.json` em `mode: publication`, 9.545
jogos). Comandos, com `BRASILEIRAO_ROOT` apontando para uma cópia dos dados fora do repositório:

- `python -m brasileirao.cli backtest --rules-season 2026 --simulations 2000` (mesmo número de
  simulações do relatório anterior);
- `python -m brasileirao.cli backtest --rules-season 2026 --simulations 10000` (relatório adotado);
- seis sementes (7, 11, 13, 17, 19 e 23) com 10.000 simulações nos 18 checkpoints de validação,
  fora do comando `backtest`, com `prepare_checkpoints` e `score_simulation_variants` e os
  hiperparâmetros do relatório. A semente 7 reproduz exatamente os números do relatório de 10.000.

### Comparação com o relatório anterior

| Item | Anterior (`brasileirao_dataset`, 2.000) | Publicação, 2.000 | Publicação, 10.000 (adotado) |
|---|---|---|---|
| Hiperparâmetros dos ratings | K 10, mando 50, regr. 0,3; A/D 0,015 e 0,15; forma 2 | iguais | iguais |
| Conjunto de variáveis | Elo + ataque/defesa | igual | igual |
| Log loss de validação (escolhido) | 1,013239 | 1,013239 | 1,013239 |
| Teste: log loss / Brier / RPS | 1,02133 / 0,61260 / 0,20775 | 1,02134 / 0,61261 / 0,20775 | 1,02134 / 0,61261 / 0,20775 |
| Teste com dispersão: log loss / placar exato | 1,02093 / 2,73443 | 1,02093 / 2,73441 | 1,02093 / 2,73441 |
| ECE mandante / empate / visitante (p.p.) | 1,55 / 1,17 / 1,57 | 1,44 / 1,17 / 1,56 | 1,44 / 1,17 / 1,56 |
| Validação: log loss posição, dinâmico × fixo | **2,2614** × 2,2681 | 2,2708 × **2,2538** | 2,2651 × **2,2571** |
| Ratings na simulação | dinâmicos | fixos | fixos |
| Dispersão de gols (regra `select_goal_dispersion`) | adotada | rejeitada (2,2619 × 2,2538) | adotada (2,2561 × 2,2571) |
| Inflação de empates / incerteza extra | não / nenhuma | não / nenhuma | não / nenhuma |
| Configuração escolhida, validação: log loss posição / cobertura 90% / MAE pontos | 2,2612 / 91,7% / 4,70 | 2,2538 / 87,5% / 4,70 | 2,2561 / 87,2% / 4,70 |
| Configuração escolhida, teste: log loss posição / cobertura 90% / MAE pontos | 2,2277 / 86,9% / 5,12 | 2,2323 / 83,6% / 5,12 | 2,2411 / 83,1% / 5,12 |
| Configuração escolhida, teste: Brier título / G4 / rebaixamento | 0,0288 / 0,0688 / 0,0899 | 0,0293 / 0,0681 / 0,0909 | 0,0293 / 0,0688 / 0,0915 |

Por que mudou:

- **Partidas: nada relevante.** Os placares de 2003–2025 coincidem nas duas fontes. A diferença na
  5ª casa vem das 138 datas de 2024–2025 que agora estão um dia antes (fuso de Brasília em vez de UTC).
  É o mesmo efeito medido na seção "Deslocamento de data UTC" (+0,000006 de log loss). Uma
  probabilidade de mandante que cruza o limite de uma faixa de calibração muda a contagem de duas
  faixas (613 → 611 e 815 → 817 jogos), e o ECE do mandante cai 0,1 p.p.
- **Temporadas: ruído de Monte Carlo.** Na validação (2013–2018), placares e datas são idênticos.
  Só o `match_id` mudou, e os jogos restantes são ordenados por data e `match_id`
  (`simulation/engine.py:57`). A ordem muda quais números aleatórios cada jogo recebe (N9). Com
  2.000 simulações essa troca sozinha inverteu as três decisões de temporada.

### Sensibilidade à semente (validação 2013–2018, 10.000 simulações por semente)

| Semente | Dinâmico | Fixo | Dinâmico + dispersão | Fixo + dispersão |
|---|---|---|---|---|
| 7 | 2,26509 | 2,25711 | 2,25990 | 2,25608 |
| 11 | 2,26466 | 2,26031 | 2,26507 | 2,25536 |
| 13 | 2,26315 | 2,25759 | 2,26038 | 2,25874 |
| 17 | 2,26362 | 2,26468 | 2,26670 | 2,26620 |
| 19 | 2,26415 | 2,26371 | 2,26696 | 2,26155 |
| 23 | 2,26029 | 2,26167 | 2,25987 | 2,26408 |
| **Média (60.000)** | 2,26349 | **2,26085** | 2,26315 | **2,26033** |
| Cobertura 90%, média | 91,9% | 87,4% | 91,9% | 87,3% |

Diferenças pareadas de log loss de posição (média e erro-padrão entre sementes): dinâmico − fixo
= +0,0027 (0,0016); fixo + dispersão − fixo = −0,0005 (0,0011); dinâmico + dispersão − dinâmico =
−0,0003 (0,0013).

### Decisões

Regra fixada antes de ver as sementes: aplicar as mesmas regras do código à média das seis sementes.

- **Ratings fixos na simulação** (`dynamic_ratings_in_simulation: false`). A média favorece os
  fixos em 0,0027, 1,7 erro-padrão e acima da tolerância de 0,001. O relatório de 10.000 simulações
  chega à mesma escolha.
- **Dispersão de gols mantida** (`goal_dispersion: true`). As condições de partidas valem
  (1X2 1,01324 → 1,01303; placar 2,72522 → 2,72375), e a posição não piora (−0,0005 com fixos).
- **Sem inflação de empates e sem incerteza extra**, como antes. No relatório de 10.000, "sem
  incerteza" (2,2561) empata com a força latente sd 0,05 (2,2566), e a parcimônia escolhe a mais
  simples. A origem móvel escolheria sd 0,10 para 2026 e segue não adotada.
- **Hiperparâmetros dos ratings e conjunto de variáveis: inalterados.**
- **`MODEL_VERSION` = `cmp-elo-ad-0.3.0`.** Muda o comportamento da simulação (fixos em vez de
  dinâmicos) e muda a base de dados (N9). O backtest rodou antes da troca da constante. Por isso o
  rótulo `model_version` do relatório e do `model_config.json` foi trocado à mão, como no
  `cmp-elo-ad-0.2.0`. Os números são do mesmo código.

**Custo da escolha (para a revisão do 06 e do 00).** A diferença na validação está perto do ruído.
Os ratings dinâmicos cobrem melhor o intervalo de 90% nos dois períodos (validação 91,9% × 87,4%;
teste 86,4% × 83,3%) e têm log loss de posição menor no **teste** (2,2133 × 2,2321 na semente 7). A
configuração em produção piora no teste em relação à anterior: log loss de posição 2,2277 → 2,2411
e cobertura de 90% 86,9% → 83,1%. As métricas de partidas não mudam. Escolher dinâmicos olhando o
teste violaria o protocolo. Se o 06 ou o 00 preferirem priorizar a cobertura, o caminho é mudar o
critério antes de rodar de novo, por exemplo com a cobertura como restrição ou com mais
checkpoints por temporada. Não é trocar o resultado à mão.

Limitações: as sementes cobrem só a validação de dinâmico × fixo e da dispersão. A escolha da
incerteza usa uma semente (7) com 10.000 simulações. O teste da configuração final não foi repetido
com outras sementes.

### Revalidação do Agente 06 (passo 12, 2026-10-28): aceito com ressalvas

- **Reprodução**: `python -m brasileirao.cli backtest --rules-season 2026 --simulations 10000`
  (semente 7) num clone limpo da branch `model/backtest-publicacao` (`b656b31`), sobre o gold de
  publicação (`matches_model.csv` SHA-256 `2bfaa90d…0902`, 9.545 jogos). Todas as métricas de partidas e
  de temporada e todas as seleções são idênticas ao relatório versionado. As únicas diferenças (até
  7e-11) estão no ajuste do parâmetro de dispersão (`fitted_nu_by_season`) e nas distribuições de gols
  previstas de 2026, por ponto flutuante.
- **Sementes**: recalculadas dos seis arquivos (10.000 simulações cada). Dinâmico − fixo = +0,0027
  (EP 0,0016), fixo + dispersão − fixo = −0,0005 (0,0011), dinâmico + dispersão − dinâmico = −0,0003
  (0,0013). Sem a semente 7 (já vista antes da regra): dinâmico − fixo = +0,0016 (0,0014). A escolha
  dos fixos não depende dela.
- **Protocolo**: escolha só na validação 2013–2018, sem dado posterior à data de cada checkpoint. A
  regra da média das sementes foi definida depois de o relatório de 10.000 (que já trazia o teste) estar
  pronto. A regra é a do código, e o resultado vai contra o teste, o que afasta escolha guiada pelo
  teste. A regra dinâmico × fixo do código não tem tolerância. Os fixos também são o modo mais simples.
- **Relatórios versionados**: só agregados. Nenhum identificador de clube ou de jogo do gold aparece em
  `backtest_report.json` nem em `model_config.json`.
- **Métricas aceitas (`cmp-elo-ad-0.3.0`: ratings fixos, dispersão de gols, sem inflação de empates, sem
  incerteza extra)**: partidas, teste 2019–2025: log loss 1,0213, Brier 0,6126, RPS 0,2078. Temporadas,
  validação: log loss de posição 2,2561, cobertura do intervalo de 90% 87,2%, MAE dos pontos 4,70.
  Teste: 2,2411, 83,1%, 5,12.
- **Ressalva (integridade da interface)**: o intervalo rotulado como 90% cobriu 83,1% no teste.
  Antes de publicar com esta versão, "Como calculamos" precisa dizer que o modo em produção é o de
  ratings fixos, dar a cobertura medida dele e usar o MAE dele (`season_simulation.overall.fixed`). Hoje
  usa o dinâmico.
- **Critério**: não muda nesta versão. Um critério que leve em conta a cobertura (restrição ou
  calibração do intervalo) tem de ser registrado aqui antes da próxima rodada do backtest. Se for adotado
  agora, depois de ver estes resultados, fica marcado como decisão a posteriori, e a confirmação passa a
  ser prospectiva (rodadas de 2026 em diante).

## Histórico publicado e `MODEL_VERSION` (Agente 00, 2026-10-28)

Registro pedido pela Decisão 3 do ADR-0008 (adendo confirmado, ajuste 1). O site é reconstruído do zero a
cada execução do `publish-site.yml`, com `simulate --history-from-round 1`. Por isso:

- **Um `MODEL_VERSION` novo implica recálculo da história publicada.** Na execução seguinte, todos os
  pontos de `probability-history.json` são refeitos com o modelo novo. O commit que muda
  `MODEL_VERSION` (`src/brasileirao/config.py`) registra nesta seção a versão antiga, a nova e o motivo,
  e avisa que a curva do site vai mudar inteira.
- **Cada ponto declara a origem**: `generated_at` (ISO com fuso), `model_version` e `reconstructed`. O
  `seasons.json` traz `history_mode` (`reconstructed` ou `recorded`). Regra e contrato: ADR-0008,
  "Implementação do ajuste 1".
- **O que o 06 audita**: no modo `reconstructed`, nenhum ponto pode usar partida posterior à sua
  `reference_date` (já coberto pelos testes de validação temporal), e todos os pontos de uma mesma
  execução têm o mesmo `model_version`. Um ponto com `model_version` diferente indica mistura de
  execuções, e a interface mostra o aviso B de D-034.

| Data | `MODEL_VERSION` anterior | Novo | Motivo | História recalculada |
|---|---|---|---|---|
| — | — | `cmp-elo-ad-0.2.0` (vigente em 2026-10-28) | linha de base do registro | sim, a cada execução |
| 2026-10-28 | `cmp-elo-ad-0.2.0` | `cmp-elo-ad-0.3.0` | backtest sobre o gold de publicação (passo 11 do ADR-0008); ratings fixos na simulação (validação, média de 6 sementes) | sim, a curva inteira muda na execução seguinte |
