# Regras da competição (Agente 03)

Fonte: [Regulamento Específico da Competição — Série A 2026](https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/REC_Brasileiro_Serie_A_2026_c984f8cf05.pdf),
CBF, 15/12/2025. Arquivo versionado: `src/brasileirao/competition_rules/seasons/serie_a_2026.toml`.
Cada nova temporada ganha um arquivo `serie_a_<ano>.toml`. Nada é presumido fixo no código.

## Implementado

| Artigo | Regra | Implementação |
|---|---|---|
| 14 | 20 clubes, turno e returno | validação de 380 jogos e checagem no simulador |
| 15 | Pontos, vitórias, saldo, gols pró, confronto direto, menos vermelhos, menos amarelos, sorteio | `standings.rank_clubs` |
| 15 § 1º | Confronto direto: soma de pontos nos dois jogos e, depois, saldo nesses jogos | `_resolve_tie_group` |
| 15 § 2º | Mais de dois clubes empatados: não se usa confronto direto | idem |
| 6º a–e | 1º–4º Libertadores fase de grupos; 5º fase preliminar | `league_slots` |
| 6º § 1º | Campeão da Copa do Brasil fase de grupos; vice fase preliminar | `allocate_slots` |
| 6º § 2º | Campeão da Libertadores ou da Sul-Americana 2026 ocupa a vaga CONMEBOL; a vaga nacional desce | idem |
| 6º § 3º | Classificado pela Copa e pelo Brasileirão fica com a vaga mais benéfica; a outra desce | idem |
| 6º § 4º–5º | Vagas idênticas: fica a do Brasileirão; a vaga direta da Copa vai ao vice da Copa e a preliminar do vice volta à tabela | idem |
| 7º | Sul-Americana: seis melhores não classificados à Libertadores | idem |
| 8º | Rebaixamento dos quatro últimos | idem |

"Vaga desce" significa: o melhor colocado do Brasileirão ainda não classificado recebe a vaga.
Quando várias vagas são liberadas, as de fase de grupos são atribuídas antes das preliminares.

## Ambiguidades e interpretação adotada

1. **Alcance do § 5º.** O texto remete à "hipótese elencada no parágrafo supra" (§ 4º, Copa e
   Brasileirão), mas fala em acesso "através de outras Competições".
   - Leitura textual (padrão, `cup_redirect_policy = "equivalent_slot_only"`): o redirecionamento ao
     vice da Copa só ocorre quando o campeão da Copa também tem vaga equivalente pelo Brasileirão.
     Se o campeão da Copa for campeão continental, vale o § 2º e a vaga da Copa desce na tabela.
   - Leitura ampla (`"any_other_qualification"`): o vice da Copa herda a vaga direta também nesse
     caso.
   - Pendência: confirmar com a DCO/CBF (Art. 37, casos omissos).
2. **Vice da Copa já classificado.** O regulamento não trata o caso. Adotamos: se o vice já tem
   vaga igual ou melhor pela tabela, a vaga da Copa desce. Se a vaga da Copa for melhor, ele fica
   com ela e a da tabela desce (aplicação análoga do § 3º).
3. **Vagas liberadas ordenadas por fase.** Vagas da tabela e vagas liberadas formam um único
   conjunto, distribuído pela ordem da tabela, com a fase de grupos antes da preliminar. Assim, um
   clube que teria a vaga preliminar pela tabela sobe para a fase de grupos quando uma vaga de grupos
   é liberada. A leitura estritamente literal ("ao melhor colocado *ainda não classificado*")
   entregaria a vaga de grupos ao clube seguinte. Essa divergência foi apontada pelo Agente 06 e está
   fixada no teste `test_freed_groups_slot_upgrades_best_placed_club`. Confirmar com a CBF.
4. **Vice da Copa fora da Série A.** Ele mantém a própria vaga e não gera vaga extra na tabela.
5. **Clube rebaixado com vaga continental.** É permitido (ex.: campeão da Copa no Z4). O clube
   aparece nas duas categorias.

## Cenários externos (situação em 26/10/2026)

| Torneio | Situação | Opções enumeradas |
|---|---|---|
| Libertadores 2026 | Final Palmeiras x Estudiantes, 28/11, Montevidéu | 2 |
| Sul-Americana 2026 | Final Atlético-MG x Boca Juniors, 21/11, Barranquilla | 2 |
| Copa do Brasil 2026 | Semifinais Palmeiras x Vasco e Grêmio x Atlético-MG; final 06/12, Brasília | 8 (campeão × vice de semifinais diferentes) |

São 32 cenários no total. Nenhuma probabilidade é atribuída aos torneios externos. Cada saída
continental é publicada por cenário e como faixa (mínimo–máximo), e a interface permite escolher o
cenário. Quando um torneio terminar, basta preencher `libertadores_champion`, `sudamericana_champion`
ou `cup_champion`/`cup_runner_up` no arquivo da temporada.

Fontes da situação externa: listadas em `[external].sources` no arquivo da temporada.

## Série B 2026 (ADR-0010)

Fonte: [REC Brasileiro Série B 2026](https://stcbfsiteprdimgbrs.blob.core.windows.net/img-site/cdn/REC_Brasileiro_Serie_B_2026_85d55b9f72.pdf)
(CBF, 2026-02-06), lido em 2026-10-29. Versionado em `competition_rules/seasons/serie_b_2026.toml`.

- **Art. 11**: pontos corridos, turno e returno, 38 rodadas.
- **Art. 12**: desempate por vitórias, saldo, gols pró, confronto direto (agregado de 180 minutos, só
  entre dois clubes), cartões vermelhos, amarelos, sorteio. É a mesma ordem da Série A; o confronto
  direto por agregado dá o mesmo resultado que "pontos e depois saldo" entre dois clubes. Sem fonte de
  cartões: os critérios 5 e 6 viram sorteio, com aviso.
- **Art. 5º**: os 2 primeiros sobem; os 4 últimos caem para a Série C.
- **Art. 13**: playoffs com o 3º x 6º (grupo A) e o 4º x 5º (grupo B), ida e volta, começando com zero ponto;
  volta na casa do 3º e do 4º; sobe quem somar mais pontos; empate em pontos: saldo de gols nos dois jogos
  e depois a melhor posição na classificação final. Não há pênaltis nem final entre os vencedores.
- Simulação: `serie_b/playoffs.py` sorteia os dois jogos de cada grupo com o modelo de gols e os ratings
  da data de referência.

## Premier League e LaLiga 2026/27 (ADR-0011)

Versionados em `competition_rules/seasons/premier_league_2026.toml` e `la_liga_2026.toml`; desempate em
`leagues/ranking.py` (critérios de tabela no campeonato inteiro; confronto direto recalculado entre os clubes
que seguem empatados).

- **Premier League** (Handbook, C.4–C.7 e C.17; texto conferido no
  [explicativo oficial](https://www.premierleague.com/en/news/4183163), que cita o Handbook 2024-25): pontos,
  saldo, gols pró; depois pontos no confronto direto e gols como visitante no confronto direto; por fim jogo
  extra em campo neutro (simulado como sorteio). Em rigor, o C.17 só vale quando título, vaga ou queda dependem
  do empate; aplicá-lo sempre não muda nenhuma zona. Rebaixam 3. Pendência do 03: conferir no Handbook 2026/27.
- **LaLiga** ([RFEF, bases 2026/27](https://rfef.es/sites/default/files/2026-06/1._CNL_Primera_y_Segunda_Division.pdf),
  Art. 8.7 e 10): pontos; dois clubes: saldo entre eles, saldo geral, gols pró, juego limpio, campo neutro;
  três ou mais: pontos entre eles (mini-tabela) e, para quem segue empatado, saldo entre eles, saldo geral,
  gols pró, juego limpio, campo neutro. Entre dois clubes, os pontos entre eles nunca contradizem o saldo
  entre eles, então uma ordem só serve aos dois casos. Juego limpio sem dados: sorteio. Rebaixam 18º–20º.
- **Leitura do Art. 10 (b), três ou mais clubes**: "diferencia de goles ... entre ellos" é calculada só entre
  os clubes que seguem empatados depois da mini-tabela (achado do 06, 2026-10-29). A RFEF não detalha; é
  a leitura adotada até uma consulta.
- **Tabela atual** (temporada em andamento): só pontos, saldo e gols pró, como a PL faz pelo C.4–C.7; os
  critérios de confronto direto valem para a classificação final e entram em toda simulação (achado M1 do 06).
- Zonas exibidas: título, top 4 e rebaixamento. "Top 4" é posição; a vaga extra pelo desempenho europeu do
  país não é modelada.

## Champions League 2026/27 (ADR-0012)

Regulamento da UEFA 2026/27 (documents.uefa.com). Art. 18 (fase de liga): pontos, saldo, gols, gols fora,
vitórias, vitórias fora, pontos, saldo e gols dos adversários, pontos disciplinares e coeficiente; sem confronto
direto; os dois últimos viram sorteio. Art. 19 (mata-mata): playoff 9/10 x 23/24, 11/12 x 21/22, 13/14 x 19/20,
15/16 x 17/18; oitavas 1/2, 3/4, 5/6 e 7/8 contra os vencedores das seções IV, III, II e I; quartas A x D e B x C
em cada lado; o melhor colocado decide em casa e quem elimina herda a posição. Onde a UEFA sorteia, a simulação
sorteia com chances iguais. Agregado sem gol fora, prorrogação e pênaltis; final em jogo único (pendência do 03:
conferir o Art. 21 no texto oficial).
