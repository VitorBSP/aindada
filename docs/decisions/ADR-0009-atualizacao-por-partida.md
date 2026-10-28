# ADR-0009 — Atualização do site depois de cada jogo e aba "Rodada atual"

- Status: **aceito** (2026-10-28) pelo Agente 00, como desenho. **Nada foi implementado.** O
  disparo real das publicações por jogo só é ligado depois da auditoria do 06 e de um dia de jogos
  em modo de ensaio (seção "Ligar").
- Histórico: **proposto** (2026-10-28) com um "vigia" a cada 10 minutos e um `schedule.json`
  publicado. O dono do produto recusou esse desenho no mesmo dia, por excesso de infraestrutura
  (registro abaixo). Este texto já é o desenho simplificado.
- Responsáveis: Agente 00 (decisão e contratos), 01 (horário no silver), 04 (export e API), 07
  (workflow), 08 (experiência e textos), 05 (interface), 06 (auditoria).
- Relaciona-se com: ADR-0007 (deploy estático), ADR-0008 (fontes, Decisão 3 e o adendo da
  reconstrução a cada execução), D-031 (home por disputa), D-034 e D-035 (textos da reconstrução).

## Pedido do dono do produto (2026-10-28)

Pedido, literal: "o vigia pode rodar uma vez a cada semana para verificar quantas vezes ele vai ter
que rodar, ou seja, verificar o horário dos jogos, por exemplo hoje tem jogo 19:30 e 21:30, o ideal
seria o vigia verificar 2 horas e 10 minutos após o inicio do jogo ou seja 21:40 e 23:40, se o jogo
já foi finalizado e adicionar as probabilidades com esse e deixar uma página específica para pegar
as atualizações da rodada atual, com uma opção na home Rodada Atual | Título | G4 | Rebaixamento e
quando acabar a rodada colocar Última Rodada / Título | G4 | Rebaixamento".

Correção, literal (mesmo dia): "vigia não precisa ser a cada 10 minutos acho que você está criando
infra de mais, pode ser mais simples e atender o que falo".

## Contexto

- O `publish-site.yml` roda uma vez por dia (09:17 UTC, 06:17 em Brasília) e reconstrói tudo do zero
  (adendo da Decisão 3 do ADR-0008): ~17 min na execução real do C5 (100 mil, 10 mil e 20 mil
  simulações), dos quais ~75% são do `review-rounds`.
- O GitHub Actions não cria agendamentos dinâmicos. Um job hospedado dura no máximo 6 h.
- O silver guarda só a data do jogo em Brasília (`match_date`), sem o horário. O football-data.org
  devolve `utcDate` e distingue `TIMED` (horário confirmado) de `SCHEDULED` (só a data).
- `IN_PLAY`, `PAUSED` e `LIVE` já viram `scheduled` no adaptador: placar parcial nunca entra.
- O `rounds.json` já tem, por rodada, a visão na véspera do início da rodada seguinte e uma visão
  parcial na data dos dados.

## Decisão 1 — Um workflow, dois disparos por dia, que dormem até cada jogo acabar

Novo workflow `atualizar-rodada.yml` (07). Nada de agendamento frequente, plano semanal ou
`schedule.json`.

### Disparos e janelas

| Disparo | Cron (UTC) | Brasília | Prazo interno | Cuida dos jogos com `check_at` |
|---|---|---|---|---|
| tarde | `37 15 * * *` | 12:37 | início + 5 h 50 | antes de 18:30 |
| noite | `37 21 * * *` | 18:37 | início + 5 h 50 | a partir de 18:30, e os da tarde ainda pendentes |

- `check_at = kickoff + 2 h 10`. Jogos das 11:00 às 21:45 dão `check_at` de 13:10 a 23:55.
- O disparo da noite termina, no máximo, por volta de 00:27. Com isso, o último jogo do dia tem a
  checagem às 23:55 e uma nova tentativa às 00:25. O que ainda não tiver acabado fica para a
  publicação diária das 06:17, que continua como rede de segurança.
- Os minutos fora do 0 evitam a fila do GitHub. Se o disparo atrasar, o prazo interno também anda,
  porque é contado a partir do início. O `timeout-minutes` do job é 360.
- O fuso é calculado com `America/Sao_Paulo`, e não com um deslocamento fixo.

### O que cada disparo faz

1. **Uma chamada** ao football-data.org (`/v4/competitions/BSA/matches`, `dateFrom` e `dateTo`
   cobrindo o dia em Brasília). Fica com os jogos do dia em Brasília que têm horário confirmado
   (`TIMED`, ou `utcDate` já passado). Sem jogo na sua faixa, termina em segundos.
2. Agrupa os jogos pelo mesmo `check_at` e dorme (`sleep`) até o próximo grupo.
3. No `check_at`, faz **uma chamada** e, para cada jogo do grupo:
   - `FINISHED` na API e **não** `finished` no `predictions.json` publicado: precisa publicar;
   - `FINISHED` na API e já `finished` no site (por exemplo, a publicação diária ou outro grupo já
     publicou): nada a fazer;
   - `IN_PLAY`, `PAUSED`, `LIVE`, `TIMED` ou `SCHEDULED`: tenta de novo em 30 min, enquanto couber
     no prazo interno;
   - `POSTPONED`, `SUSPENDED`, `CANCELLED` ou `AWARDED`: sai da fila; a publicação diária trata.
     (`AWARDED` exige a exceção registrada pelo 01; a ingestão falharia sem ela.)
4. Se algum jogo precisa publicar, dispara **um** `publish-site` (detalhes abaixo) para o grupo
   inteiro e continua dormindo até o próximo grupo. Cada jogo é disparado no máximo uma vez por
   execução. Se a publicação falhar, o GitHub avisa o dono por e-mail (como hoje) e a publicação
   diária refaz tudo.
5. O disparo da noite, ao começar, também olha os jogos do dia com `check_at` antes de 18:30 que
   estejam `FINISHED` na API e não `finished` no site: são os que a tarde não chegou a publicar.

O estado do site é lido do `predictions.json` público (sem token). Por isso não há estado entre
execuções nem entre os dois disparos. Para ligar o jogo da API ao jogo do site, o export passa a ter
`source_match_id` e `kickoff_utc` em cada partida (Decisão 2).

### Como publica

- `gh workflow run publish-site.yml --ref main` com o `GITHUB_TOKEN` (permissão `actions: write` só
  neste job). Eventos `workflow_dispatch` criados pelo `GITHUB_TOKEN` disparam workflows, ao
  contrário dos demais eventos (**a verificar** pelo 07 no ensaio).
- `workflow_call` não serve: um workflow reutilizável é um job, e não pode ser chamado no meio de um
  job que dorme. Repetir os passos de publicação dentro do novo workflow também não: haveria dois
  caminhos de publicação para o gate cobrir.
- O `publish-site.yml` ganha dois `inputs` opcionais: `trigger` (`manual` ou `match`) e `match_ids`
  (IDs da fonte separados por vírgula, conferidos por expressão regular) e um `run-name` com os dois,
  para o histórico do Actions mostrar qual jogo motivou cada publicação. Os `inputs` entram nos
  scripts só por variável de ambiente, nunca interpolados com `${{ }}` dentro do `run`.
- O `concurrency: publish-site` atual vale: uma publicação por vez, e um pedido novo substitui o que
  estiver na fila. Como cada publicação busca os dados mais novos, nada se perde.
- A publicação por jogo é **a mesma** publicação diária: testes, ingestão, validação, simulação
  completa, gate G1 a G5 e `check_site_artifact.py`. Nada é publicado sem o gate.

### Interruptores e segurança

- Só roda na `main`, em `schedule` ou `workflow_dispatch` (para ensaio), e só com
  `PUBLISH_ENABLED == 'true'`.
- Nova variável `MATCH_UPDATES`:
  - ausente ou `dry-run` (padrão): faz tudo, inclusive as chamadas à API, mas **não** dispara a
    publicação; registra no resumo o que teria disparado e quando;
  - `on`: dispara;
  - `off`: o workflow nem começa.
- Permissões do job: `contents: read` e `actions: write`. O token do football-data.org só nos passos
  que chamam a API, nunca impresso. O log mostra IDs, horários e decisões, nunca placares.
- Script em `infrastructure/scripts/` só com a biblioteca padrão do Python, rodado com `python -I`. A
  lógica de decisão (janela, agrupamento, nova tentativa, o que dispara) fica numa função pura,
  testada com dados sintéticos e relógio injetado.
- Chamadas à API: 1 no início de cada disparo e 1 por checagem, mais as 3 de cada publicação. Fica
  muito abaixo do limite do plano gratuito (10 por minuto).

### Custo e prazo de atualização

- Um job dormindo conta minutos, que são gratuitos em repositório público. Num dia com jogos, até
  ~12 h de runner; sem jogos, segundos.
- Prazo esperado entre o fim do jogo e o site atualizado: a checagem acontece ~15 a 20 min depois
  do apito final (2 h 10 menos ~1 h 55 de jogo e intervalo), mais o atraso da fonte no plano gratuito
  (**a medir** pelo 01 no primeiro dia de jogos) e ~17–20 min de publicação. Em geral, **de 30 a 60
  min** depois do fim do jogo; jogo com acréscimos longos ou atraso na fonte entra na nova tentativa,
  30 min depois.

## Decisão 2 — Horário do jogo no silver e no export

### 01: silver e gold

`MatchRecord` (`contracts.py`) ganha dois campos opcionais:

| Campo | Tipo | Regra |
|---|---|---|
| `kickoff_utc` | `datetime \| None`, com fuso (UTC) | `utcDate` do football-data.org. `None` nas fontes sem horário (Adão Duque e as de conferência) |
| `kickoff_time_confirmed` | `bool \| None` | `true` com `TIMED` ou status posterior ao início; `false` com `SCHEDULED`; `None` sem horário |

- Invariante (validador e teste): com `kickoff_utc`, `match_date` é a data de `kickoff_utc` em
  `America/Sao_Paulo`.
- As colunas vão até o gold como opcionais. O modelo não as usa.
- **A validação temporal continua por `match_date`** (data em Brasília). O horário não muda o que
  entra em ratings, treino ou simulação. Os jogos do mesmo dia já encerrados entram no snapshot
  daquele dia, como hoje; isso não é vazamento, porque o resultado é real antes dos jogos seguintes.

### 04: snapshot, export e API

- `MatchPrediction` (`storage/schema.py`) ganha, opcionais: `kickoff_utc: str | None` (ISO 8601 em
  UTC), `kickoff_time_confirmed: bool | None` e `source_match_id: str | None`. O 04 decide o novo
  `SNAPSHOT_SCHEMA_VERSION` (aditivo). O `predictions.json` passa a ter os três campos em cada
  partida.
- Novo documento `current-round.json` (Decisão 3), com rota na API
  `GET /api/seasons/{season}/current-round` e espelho estático
  `data/api/seasons/{season}/current-round.json`.
- Licença: horário, rodada, data e placar da temporada exibida são fatos de partida cobertos por
  `public_display_derived` (ADR-0008, Decisão 2). O `current-round.json` traz as atribuições de
  `data.sources`, como o `predictions.json`.
- Não há `schedule.json`. O horário vem no export normal.

## Decisão 3 — "Rodada atual" e "Última rodada"

### Definições (implementadas em Python pelo 04, nunca no navegador)

Parâmetros em `config.py` (o 04 pode editar este trecho, por este ADR):
`ROUND_WINDOW_DAYS = 4`, `STALE_RESULT_HOURS = 48`.

- **Âncora da rodada:** mediana inferior das `match_date` dos jogos da rodada.
- **Jogo na janela:** `match_date` a até `ROUND_WINDOW_DAYS` dias da âncora. Jogo fora da janela
  (adiado para outra semana) é listado como "remarcado" e **não** prende a rodada. Assim, um jogo
  adiado da rodada 21 jogado durante a 30 não faz da 21 a rodada atual.
- **Jogo resolvido**, para o estado da rodada: `finished`, `postponed` ou `cancelled`, ou
  `scheduled` com início há mais de `STALE_RESULT_HOURS` horas (sem placar na fonte, aviso R2 e
  D-031). Este último fica marcado como `missing_result` e nunca recebe placar.
- **Início da rodada:** o menor `kickoff_utc` dos jogos na janela (sem horário, 00:00 de Brasília da
  `match_date`).
- **Estado da rodada** num instante T:
  - `not_started`: nenhum jogo da janela começou até T;
  - `in_progress`: algum começou e algum ainda não está resolvido;
  - `completed`: todos os jogos da janela resolvidos.

### O que o export grava (T = horário do export)

- `active_round`: a menor rodada `in_progress`, ou `null`.
- `next_round`: a menor rodada `not_started`, ou `null`.
- `last_round`: a maior rodada `completed` cujo último jogo da janela começou até T, ou `null`.

### O que a interface mostra (05, com o relógio do navegador, `now`)

1. `active_round` existe: aba **"Rodada atual"** com ela.
2. Senão, `next_round` existe e `now >= next_round.starts_at`: aba **"Rodada atual"** com a
   `next_round`. Os jogos aparecem como "em andamento ou aguardando atualização", sem placar e sem
   variação.
3. Senão, `last_round` existe: aba **"Última rodada"**.
4. Senão (antes da primeira rodada): aba "Rodada atual" com a `next_round` ainda não iniciada (o 08
   define o texto).

Assim, depois do último jogo da rodada, a home mostra "Última rodada" até o primeiro jogo da rodada
seguinte começar, como o dono pediu. Fim de temporada: "Última rodada" com a 38ª.

### Variação desde o início da rodada

- **Base:** a visão do `rounds.json` com a maior `reference_date` anterior à data do início da
  rodada (a véspera). **Agora:** o `predictions.json` publicado (100 mil simulações), os mesmos
  números do resto do site. `delta = agora − base`, por clube, para `title`, `top4` e `relegation`.
- A base tem 20 mil simulações: erro de Monte Carlo de até ~0,35 p.p. O 08 não destaca como
  movimento variação abaixo de 1 p.p. em módulo.
- A base é **reconstrução** (D-034, D-035): calculada com o modelo atual, não é o número publicado
  na véspera. O export marca `baseline.reconstructed` e a interface diz isso.

### Contrato do `current-round.json` (exemplo com valores fictícios, não são dados reais)

```json
{
  "schema_version": "1.0",
  "season": 2099,
  "generated_at": "2099-01-01T23:58:00Z",
  "reference_date": "2099-01-01",
  "model_version": "exemplo-0.0.0",
  "data_version": "exemplo",
  "attributions": ["<texto exato de data.sources[].attribution>"],
  "parameters": {"round_window_days": 4, "stale_result_hours": 48},
  "active_round": {
    "round_number": 7,
    "state": "in_progress",
    "anchor_date": "2099-01-01",
    "starts_at": "2099-01-01T19:00:00Z",
    "ends_at": "2099-01-02T00:30:00Z",
    "counts": {"finished": 1, "scheduled": 1, "postponed": 0, "cancelled": 0, "missing_result": 0, "rescheduled_out": 1},
    "matches": [
      {
        "match_id": "exemplo-1",
        "source_match_id": "0001",
        "home_id": "clube-a",
        "away_id": "clube-b",
        "match_date": "2099-01-01",
        "kickoff_utc": "2099-01-01T19:00:00Z",
        "kickoff_time_confirmed": true,
        "status": "finished",
        "in_window": true,
        "missing_result": false,
        "home_goals": 1,
        "away_goals": 0,
        "p_home": null, "p_draw": null, "p_away": null
      },
      {
        "match_id": "exemplo-2",
        "source_match_id": "0002",
        "home_id": "clube-c",
        "away_id": "clube-d",
        "match_date": "2099-01-01",
        "kickoff_utc": "2099-01-02T00:30:00Z",
        "kickoff_time_confirmed": true,
        "status": "scheduled",
        "in_window": true,
        "missing_result": false,
        "home_goals": null,
        "away_goals": null,
        "p_home": 0.4, "p_draw": 0.3, "p_away": 0.3
      },
      {
        "match_id": "exemplo-3",
        "source_match_id": "0003",
        "home_id": "clube-e",
        "away_id": "clube-f",
        "match_date": "2099-02-01",
        "kickoff_utc": null,
        "kickoff_time_confirmed": null,
        "status": "scheduled",
        "in_window": false,
        "missing_result": false,
        "home_goals": null,
        "away_goals": null,
        "p_home": 0.5, "p_draw": 0.25, "p_away": 0.25
      }
    ],
    "baseline": {
      "reference_date": "2098-12-31",
      "source": "rounds",
      "n_simulations": 20000,
      "generated_at": "2099-01-01T23:40:00Z",
      "reconstructed": true
    },
    "current": {"source": "predictions", "n_simulations": 100000},
    "teams": [
      {
        "club_id": "clube-a",
        "baseline": {"title": 0.10, "top4": 0.50, "relegation": 0.01},
        "current": {"title": 0.12, "top4": 0.55, "relegation": 0.01},
        "delta": {"title": 0.02, "top4": 0.05, "relegation": 0.0}
      }
    ]
  },
  "next_round": {
    "round_number": 8,
    "state": "not_started",
    "anchor_date": "2099-01-05",
    "starts_at": "2099-01-04T22:00:00Z",
    "ends_at": "2099-01-06T00:30:00Z",
    "counts": {"finished": 0, "scheduled": 10, "postponed": 0, "cancelled": 0, "missing_result": 0, "rescheduled_out": 0},
    "matches": [],
    "baseline": null,
    "current": {"source": "predictions", "n_simulations": 100000},
    "teams": []
  },
  "last_round": null
}
```

Regras do contrato (o 06 testa):

- Placar só com `status == "finished"`. Nunca há placar em jogo `scheduled`, `postponed`,
  `cancelled` ou `missing_result`. Não existe status "em andamento" no export.
- `p_home`, `p_draw` e `p_away` só em jogo não encerrado, copiados do `predictions.json`.
- Os jogos de `active_round`, `next_round` e `last_round` vêm todos do `predictions.json` da mesma
  execução; `teams[].current` é igual ao do `predictions.json`; `baseline` é igual à visão citada
  do `rounds.json`.
- `next_round.teams` fica vazio e `baseline` nulo enquanto a rodada não começar.
- Horários sempre em UTC (`Z`). A interface converte para Brasília.
- Clubes por `club_id`; nomes e escudos vêm do que a interface já carrega.

## Decisão 4 — Cache: não adotar agora

A publicação por jogo é a publicação completa, de ~17–20 min. **Não** se adota cache de pontos do
histórico nem de revisões de rodadas passadas.

- O ganho é pequeno: a espera é dominada pelos 2 h 10 do `check_at`, pelo atraso da fonte e pela fila
  do Actions. Os 17 min são cerca de um terço do prazo total.
- A chave proposta (`MODEL_VERSION` + hash dos dados até o corte) não basta: mudanças em regras,
  simulação, configuração ou no TOML da temporada mudam o resultado sem mudar o `MODEL_VERSION`, e o
  calendário futuro (remarcações) também entra em cada ponto. Uma chave incompleta publicaria história
  velha sem aviso, que é o dano que o R18 quer evitar.
- O cache do Actions guardaria snapshots com placares fora do runner, contra o adendo da Decisão 3 do
  ADR-0008 ("sem cache de dados"). Em repositório público, workflows de pull request podem ler caches
  do ramo padrão (**a verificar**).
- **Otimização permitida sem estado (O1, opcional, 07):** rodar a reconstrução do histórico e o
  `review-rounds` em paralelo no mesmo job (o runner tem 4 vCPUs), com bancos SQLite separados e
  juntados antes do export. Critério do 06: JSON exportados iguais aos da execução em sequência,
  exceto `generated_at`.
- Reabrir com ADR próprio se o prazo medido (fim do jogo → site atualizado) passar de 75 min no p90
  em uma rodada inteira, depois da O1.

## Integridade

- Placar em andamento nunca é publicado: `IN_PLAY`, `PAUSED` e `LIVE` continuam `scheduled`, e a
  publicação só é disparada com `FINISHED`. A interface mostra jogo começado sem resultado como "em
  andamento ou aguardando atualização".
- Toda publicação passa pelo gate G1 a G5 e pelo `check_site_artifact.py`, que o 07 estende ao
  `current-round.json` (atribuições, regras do contrato acima).
- Validação temporal inalterada (Decisão 2).
- A interface diz quando os dados foram atualizados (`generated_at`) e que os resultados costumam
  entrar de 30 a 60 min depois do fim do jogo (texto do 08). Não promete tempo real.
- R11 (o GitHub desativar agendamentos depois de 60 dias sem atividade): o novo workflow não muda o
  risco, que continua aceito. Ele também não faz commit. Os dois agendamentos param juntos, o site
  anterior continua no ar e reativar é um clique.

## Divisão do trabalho e ordem

| Ordem | Agente | Entrega | Critério de aceite |
|---|---|---|---|
| 1 | 01 | `kickoff_utc` e `kickoff_time_confirmed` no `MatchRecord`, no adaptador e no gold; invariante com `match_date`; catálogo atualizado | testes com fixture sintética (`TIMED`, `SCHEDULED`, jogo noturno que vira o dia em UTC); ingestão real de 2026 com 0 violações do invariante |
| 2 | 04 | campos novos no `MatchPrediction`; `current-round.json` no `export_static_api` (o 04 pode editar esta função e as constantes de `config.py`, por este ADR) e rota na API; lógica num módulo do 04 em `src/brasileirao/storage/` | testes com fixtures sintéticas: rodada com jogo remarcado para fora da janela, jogo sem placar há mais de 48 h, virada de `active` para `last`, rodada 1 antes de começar, fim de temporada; schema e contrato acima |
| 3 | 06 | auditoria de 1 e 2 | regras do contrato, nenhum placar fora de `finished`, base igual ao `rounds.json`, validação temporal |
| 4 | 07 | `atualizar-rodada.yml` e script; `inputs` e `run-name` do `publish-site.yml`; `check_site_artifact.py` com o `current-round.json`; opcional, O1 | função de decisão testada com relógio injetado; ensaio com `workflow_dispatch` e `MATCH_UPDATES` em `dry-run`; ver "Ligar" |
| paralelo | 08 | experiência e textos: opção "Rodada atual" ou "Última rodada" na home ao lado de Título, G4 e Rebaixamento; página própria (`#/rodada-atual`); estados dos jogos; "atualizado às…"; aviso de 30–60 min; texto da base reconstruída; limiar de 1 p.p. | decisão registrada em `docs/brand/BRAND_DECISIONS.md` com textos exatos para o 05 |
| 5 | 05 | aba e página, só lendo `current-round.json` e `predictions.json`, com a regra de exibição da Decisão 3 | capturas em 1280 e 375 px nos quatro casos da regra, sem erro de JS; fixture sintética para desenvolver antes do export real |
| 6 | 06 | auditoria do texto contra os dados, da interface e do ensaio do 07 | parecer em `docs/project/status.md` |

O 08 e o 05 podem começar já, sobre o contrato e uma fixture sintética. O 05 só vai para a `main`
depois de o export do 04 existir.

## Ligar

1. Merge na `main` de 1, 2, 4 e 5, com o C4 do delta pelo 06 (condição do ADR-0007).
2. Um dia de jogos com `MATCH_UPDATES` ausente (`dry-run`): o 07 compara, no resumo, os horários em
   que teria disparado com os resultados reais, e o 01 registra o atraso medido da fonte.
3. Parecer do 06 e do 00 em `docs/project/status.md`.
4. O dono cria a variável `MATCH_UPDATES = on` (Settings → Secrets and variables → Actions →
   Variables). Para desligar: `off`.

## Alternativas consideradas

- **Vigia a cada 10 min com `schedule.json` publicado e plano diário:** recusada pelo dono (excesso
  de infraestrutura). Trocava sono por ~144 execuções por dia e um arquivo público a mais.
- **Plano semanal:** não cobre remarcações. O disparo lê os horários no próprio dia.
- **Agendar um cron por jogo:** o Actions não cria agendamentos dinâmicos; exigiria commits no
  workflow, que o projeto não faz.
- **`workflow_call` ou repetir os passos de publicação:** ver "Como publica".
- **Cache entre execuções:** Decisão 4.
- **Calcular a rodada atual no navegador:** regras de negócio ficariam sem teste em Python e longe
  do 06. O navegador só aplica a troca por horário da regra de exibição.

## Consequências

- O site passa a ser atualizado algumas vezes por dia de jogo (um por horário de início, em geral 3
  a 6), além da publicação diária.
- Mais minutos de runner (gratuitos em repositório público) e mais execuções no histórico do Actions.
- Contratos novos: horário no silver (01), três campos no `MatchPrediction` e o `current-round.json`
  (04).
- A home ganha a opção "Rodada atual" ou "Última rodada" antes de Título, G4 e Rebaixamento (D-031
  muda; decisão do 08).
- Riscos novos R19 a R21 em `docs/project/risks.md`.
