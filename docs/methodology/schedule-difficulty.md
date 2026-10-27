# Dificuldade da tabela e pontos esperados por mando (Agente 02)

Código: `src/brasileirao/prediction/schedule.py` (`build_schedules`). Campos publicados no snapshot
(schema 1.1): `teams[].schedule` por clube e `schedule_scale` no nível do snapshot.

## Entradas

- Jogos restantes na data de referência: toda partida da temporada sem placar observado até a data,
  inclusive adiadas e sem data definida (a mesma lista que a simulação usa).
- Ratings na data de referência (Elo, ataque, defesa, forma) e o modelo de gols em produção. Nada
  posterior à data entra; os ratings ficam congelados (não há atualização dentro da tabela restante).

## Pontos esperados

Para cada jogo restante, o modelo de gols dá P(vitória), P(empate) e P(derrota) do clube.
Pontos esperados do jogo = 3 · P(vitória) + 1 · P(empate) (pontuação do regulamento da temporada).

- `expected_points`: soma nos jogos restantes (não inclui os pontos já conquistados);
- `expected_points_home` / `expected_points_away`: a mesma soma restrita aos jogos em casa / fora.

Diferença para `teams[].expected_points` (pontos finais da simulação): aquele valor soma os pontos
atuais e vem do Monte Carlo, em que os ratings mudam ao longo da temporada simulada. Os dois ficam
próximos, mas não são idênticos.

## Índice de dificuldade (0–100)

A dificuldade precisa separar o calendário da força do próprio clube: um clube forte faz muitos
pontos mesmo com tabela difícil. Por isso o índice mede a tabela pelos olhos de um **clube de força
média** (média simples de Elo, ataque, defesa e forma dos 20 clubes na data): quantos pontos esse
clube médio faria contra os mesmos adversários, com os mesmos mandos.

Para cada jogo, `average_team_points` = pontos esperados do clube médio naquele jogo. O índice do
jogo é linear nesses pontos:

    dificuldade = 50 + 50 · (referência − pontos do clube médio) / meia_escala

- **referência** (`schedule_scale.reference_points`): pontos por jogo do clube médio numa tabela
  média da liga, enfrentando cada clube uma vez em casa e uma fora. Uma tabela assim vale 50.
- **meia_escala** (`schedule_scale.half_range_points`): maior distância entre a referência e um jogo
  possível: fora contra o adversário mais difícil (perto de 100) ou em casa contra o mais fácil
  (perto de 0). Assim todo jogo fica entre 0 e 100.

Por ser linear, a dificuldade de um conjunto de jogos é a média simples das dificuldades dos jogos:

- `difficulty`: média de todos os jogos restantes;
- `difficulty_home` / `difficulty_away`: média dos jogos em casa / fora. Estão na mesma escala, então
  jogos em casa ficam tipicamente abaixo de 50 e jogos fora acima: o mando faz parte da dificuldade;
- `opponent_strength` (por jogo e média do clube): a mesma escala sem o mando, isto é, a média entre
  enfrentar aquele adversário em casa e fora. 50 = adversário médio da liga;
- `difficulty_rank`, `difficulty_home_rank`, `difficulty_away_rank`: 1 = tabela mais difícil entre os
  clubes, empates desfeitos pelo `club_id`. Ficam nulos quando o clube não tem jogos naquele mando.

**Para o torcedor:** "a dificuldade vai de 0 a 100; 50 é uma tabela média do campeonato, e quanto
maior o número, menos pontos um time comum conseguiria nesses jogos."

Exemplo ilustrativo (números inventados): o Clube A tem 6 jogos, 4 em casa, com dificuldade 40 (em
casa 30, fora 60) e o Clube B tem 6 jogos, 3 em casa, com dificuldade 58 (em casa 45, fora 71). Um
clube médio faria cerca de 9 pontos na tabela do Clube A e 7,5 na do Clube B. A diferença entre
`expected_points` e `average_team_points` mostra quanto a força do próprio clube acrescenta (ou tira).

## Campos por jogo (`teams[].schedule.matches[]`)

`match_id`, `round`, `match_date`, `opponent_id`, `venue` (`home`/`away`), `p_win`, `p_draw`,
`p_loss`, `expected_points`, `average_team_points`, `difficulty`, `opponent_strength`. As
probabilidades são as mesmas de `matches[]` (vistas do lado do clube).

## Limitações

- A escala é recalculada a cada data de referência: os extremos dependem dos ratings da data. Compare
  índices de datas diferentes com cautela; o ranking entre clubes é a leitura mais estável.
- O clube médio é uma média de ratings, não a média das probabilidades dos 20 clubes.
- Não considera desgaste, viagens, datas FIFA nem jogos de outras competições.
- O índice não é métrica preditiva nova: deriva das mesmas probabilidades por jogo já validadas pelo
  Agente 06 (`validation.md`). Ele não altera as probabilidades publicadas.
