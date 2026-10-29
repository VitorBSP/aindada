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
