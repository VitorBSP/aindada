# Validação e backtesting (Agente 06)

Relatório completo e reprodutível: `data/gold/backtest_report.json`, gerado por
`python -m brasileirao.cli backtest` (dados do commit `d677143069202` do brasileirao-dataset).

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
pouco sensível a esses parâmetros.

## Partidas — teste 2019–2025 (menor é melhor)

| Modelo | Log loss | Brier | RPS |
|---|---|---|---|
| Taxa-base (frequências 1X2 do treino) | 1,0610 | 0,6403 | 0,2210 |
| Poisson sem variáveis | 1,0601 | 0,6397 | 0,2207 |
| Elo | 1,0220 | 0,6131 | 0,2078 |
| Ataque/defesa | 1,0228 | 0,6135 | 0,2082 |
| **Elo + ataque/defesa (escolhido)** | **1,0213** | **0,6126** | **0,2077** |
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
| 2025 | 1,0019 | 0,5993 | 0,2038 |

Calibração (erro de calibração esperado, 10 faixas): mandante 1,6 p.p., empate 1,2 p.p.,
visitante 1,6 p.p.

## Temporadas — snapshots históricos (rodadas 10, 19 e 28, 2.000 simulações)

O estado de cada checkpoint é reconstruído do zero com `build_state_as_of`. A primeira versão
reaproveitava o estado entre checkpoints e, com jogos adiados (2021, 2024), incluía partidas futuras.
O defeito foi apontado na revisão do Agente 06, corrigido, e os números abaixo já são os corrigidos.
A escolha entre ratings dinâmicos e fixos é feita nas temporadas de **validação** e reportada no
teste.

| Métrica (média) | Validação 2013–2018: dinâmico | Validação: fixo | Teste 2019–2025: dinâmico | Teste: fixo |
|---|---|---|---|---|
| Brier título (por clube) | 0,0164 | 0,0153 | 0,0288 | 0,0290 |
| Brier G4 | 0,0550 | 0,0538 | 0,0684 | 0,0680 |
| Brier rebaixamento | 0,0929 | 0,0940 | 0,0892 | 0,0907 |
| Log loss da posição final | **2,261** | 2,268 | **2,214** | 2,237 |
| Erro absoluto médio dos pontos finais | 4,70 | 4,70 | 5,11 | 5,12 |
| Cobertura do intervalo de 90% dos pontos | **91,7%** | 86,7% | **86,9%** | 83,6% |

Leitura: a atualização dinâmica dentro da simulação melhora a distribuição de posições e a
cobertura dos intervalos, nos dois períodos, sem piorar o erro dos pontos. As diferenças nos Brier
de título e G4 são pequenas e mistas. Ela está ligada (`data/gold/model_config.json`). No teste, a
cobertura fica abaixo de 90%, o que indica leve excesso de confiança. A propagação de incerteza
foi avaliada na etapa 2 (abaixo).

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

## Testes automatizados

`pytest`: 135 testes passando, nenhum pulado (regras, desempate, ratings, modelo, métricas,
invariantes da simulação, seleção de modelo, dados, pipeline, snapshots e API). Os invariantes cobertos incluem: 380 jogos por
temporada, posições como permutação, P(título) somando 1, P(rebaixamento) somando 4, 6 vagas de
Sul-Americana por cenário, reprodutibilidade por semente, independência da ordem de jogos
simultâneos e ausência de dados posteriores à data de referência. Na etapa 2 entraram: inflação
de empates, covariância e sorteio de coeficientes, incerteza desligada reproduzindo a execução
padrão, força latente ampliando a dispersão de pontos e regras de parcimônia.
