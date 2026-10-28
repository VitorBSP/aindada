# ADR-0009 — Atualização do site depois de cada jogo e aba "Rodada atual"

- Status: **aceito** (2026-10-28) pelo Agente 00, como desenho. **Nada foi implementado.** O
  disparo real das publicações por jogo só é ligado depois da auditoria do 06 e de um dia de jogos
  em modo de ensaio (seção "Ligar").
- Histórico: **proposto** (2026-10-28) com um "vigia" a cada 10 minutos e um `schedule.json`
  publicado. O dono do produto recusou esse desenho no mesmo dia, por excesso de infraestrutura
  (registro abaixo). Este texto já é o desenho simplificado.
- Escopo da aba: **versão enxuta** da D-037 (`docs/brand/BRAND_DECISIONS.md`), decidida pelo dono do
  produto em 2026-10-28. Ver a Decisão 3.
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

Escopo, decidido pelo dono no mesmo dia (repassado pelo orquestrador): versão enxuta da aba
(D-037). Entram as abas, os jogos da rodada por dia com horário e status, a tabela "O que mudou
desde o início da rodada" e o aviso de atualização. Ficam **fora da v1**:
- o efeito de cada jogo;
- a chance antes do jogo;
- as faixas de Libertadores e Sul-Americana no início e agora;
- a próxima rodada.

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

- `MatchPrediction` (`storage/schema.py`) ganha dois campos opcionais:
  - `kickoff_utc: str | None`, em ISO 8601 UTC. Vem preenchido **só com horário confirmado**
    (`kickoff_time_confirmed` no silver). Sem confirmação, é `null` e a interface mostra "a definir";
  - `source_match_id: str | None`, usado pelo workflow para ligar o jogo da API ao do site.

  O 04 decide o novo `SNAPSHOT_SCHEMA_VERSION` (aditivo). O `predictions.json` passa a ter os dois
  campos em cada partida.
- Novo documento `current-round.json` (Decisão 3), com rota na API
  `GET /api/seasons/{season}/current-round` e espelho estático
  `data/api/seasons/{season}/current-round.json`.
- Licença: horário, rodada, data e placar da temporada exibida são fatos de partida cobertos por
  `public_display_derived` (ADR-0008, Decisão 2). O `current-round.json` só traz ids, datas e
  números derivados; os fatos e as atribuições ficam no `predictions.json`.
- Não há `schedule.json`. O horário vem no export normal.

## Decisão 3 — "Rodada atual" e "Última rodada" (versão enxuta da D-037)

### Escopo da v1

| Entra | Fica fora (sem campo no contrato) |
|---|---|
| abas "Rodada atual · Título · G4 · Rebaixamento" e "Última rodada · …", com a aba padrão da D-037 | efeito de cada jogo (`match.impact`) |
| jogos da rodada agrupados por dia, com horário de Brasília, status ("a jogar", "aguardando placar", "encerrado", "adiado") e placar só dos encerrados | chance antes do jogo (`pre_match`) |
| tabela "O que mudou desde o início da rodada": Título, G4 e Rebaixamento, valor de agora e variação, com o limiar de ruído da D-037, sem variação se o `model_version` mudou | faixas de Libertadores e Sul-Americana no início e agora |
| aviso "Atualizado às…" e do atraso | próxima rodada |

### Qual rodada o export mostra (04, em Python; nunca no navegador)

Parâmetros em `config.py` (o 04 pode editar este trecho, por este ADR): `ROUND_WINDOW_DAYS = 4` e
`STALE_RESULT_HOURS = 48`. T é o horário do export.

- **Âncora da rodada:** a mediana inferior das `match_date` dos jogos da rodada.
- **Jogo na janela:** jogo com `match_date` a até `ROUND_WINDOW_DAYS` dias da âncora. Um jogo da
  rodada remarcado para fora da janela não segura a rodada aberta. Por isso, um jogo adiado da
  rodada 21 e disputado durante a 30 não faz da 21 a rodada atual.
- **Jogo resolvido:** `finished`, `postponed` ou `cancelled`. Também conta `scheduled` com início há
  mais de `STALE_RESULT_HOURS` horas, quando falta placar na fonte (R2). Esse jogo nunca recebe
  placar.
- **Rodada concluída:** rodada com todos os jogos da janela resolvidos.
- **Rodada mostrada:**
  1. a menor rodada **não concluída** cujo primeiro jogo da janela é de uma data, em Brasília, igual
     ou anterior à de T. Assim, a publicação diária das 06:17 de um dia de rodada já abre a "Rodada
     atual", e os jogos aparecem como "a jogar". Fica com `state: "in_progress"`;
  2. senão, a maior rodada concluída. Fica com `state: "finished"`;
  3. senão (pré-temporada), sem rodada: `round: null`, e a aba não aparece (D-037).
- **Jogos listados**, ordenados por `kickoff_utc` (os sem horário vão no fim do dia):
  - em `match_ids`: os jogos da janela da rodada mais os jogos atrasados de **outras** rodadas
    disputados no intervalo da rodada (de `starts_on` a `ends_on`). A interface reconhece estes
    pelo `round` diferente do da rodada e escreve "Jogo atrasado da rodada N";
  - em `rescheduled_match_ids`: os jogos da rodada remarcados para fora da janela. A interface os
    mostra como "adiado".

### Ponto de partida da comparação

- É a visão do `rounds.json` com a maior `reference_date` anterior a `starts_on`, ou seja, a
  véspera do primeiro jogo da rodada. Ela é calculada na mesma execução, com o mesmo modelo, o mesmo
  `data_version` e 20 mil simulações. **Agora** é o `predictions.json` da mesma execução (100 mil).
- O export grava só o ponto de partida. O 05 tira os valores de agora do `predictions.json` e
  calcula a variação e o limiar de ruído da D-037 (`n0` = `baseline.n_simulations`, `n1` =
  `predictions.n_simulations`), sem mudar número nenhum.
- Se `baseline.model_version` for diferente de `predictions.model.model_version`, a interface não
  mostra variação, com o texto da D-037. Com a reconstrução completa a cada execução isso não
  deve acontecer, mas o campo garante a regra.
- `baseline.reconstructed` é sempre `true` neste desenho: o ponto é recalculado (D-034 e D-035). A
  interface usa a nota "recalculadas com o mesmo modelo de agora" da D-037.
- Sem visão anterior (rodada 1): `baseline: null`, e a interface mostra só as chances de agora.

### Status do jogo (texto da D-037)

| Dado | Relógio do navegador | Texto |
|---|---|---|
| `status == "finished"`, com placar | — | encerrado |
| `scheduled` | antes de `kickoff_utc` | a jogar |
| `scheduled` | depois de `kickoff_utc` (aviso de atraso 4 h depois, D-037) | aguardando placar |
| `postponed` ou `cancelled`, ou id em `rescheduled_match_ids` | — | adiado |

O relógio só troca "a jogar" por "aguardando placar" e decide a aba padrão (regra 2 da D-037, até
23:59 em Brasília do dia seguinte ao do último jogo encerrado). Ele nunca marca jogo como encerrado
nem muda número. Jogo `scheduled` sem `kickoff_utc` aparece como "a jogar", com "a definir" no lugar
da hora. O 08 decide se "cancelado" merece texto próprio; na v1, vira "adiado".

### Contrato

**`predictions.json`, em cada partida** (Decisão 2): `kickoff_utc` (horário confirmado ou `null`) e
`source_match_id`. Os demais campos já existem: `round`, `match_date`, `status`, `home_goals` e
`away_goals`. Os placares da aba saem daqui.

**`current-round.json`** (novo; rota `GET /api/seasons/{season}/current-round` e espelho estático
`data/api/seasons/{season}/current-round.json`). Exemplo com valores fictícios, que não são dados
reais:

```json
{
  "schema_version": "1.0",
  "season": 2099,
  "updated_at": "2099-01-01T23:58:00Z",
  "model_version": "exemplo-0.0.0",
  "data_version": "exemplo",
  "round": {
    "round_number": 7,
    "state": "in_progress",
    "starts_on": "2099-01-01",
    "ends_on": "2099-01-03",
    "match_ids": ["exemplo-1", "exemplo-2", "exemplo-9"],
    "rescheduled_match_ids": ["exemplo-3"],
    "baseline": {
      "reference_date": "2098-12-31",
      "model_version": "exemplo-0.0.0",
      "n_simulations": 20000,
      "reconstructed": true,
      "teams": {
        "clube-a": {"title": 0.10, "top4": 0.50, "relegation": 0.01},
        "clube-b": {"title": 0.0, "top4": 0.05, "relegation": 0.30}
      }
    }
  }
}
```

- `updated_at` é o `generated_at` do snapshot publicado, e `model_version` e `data_version` são os
  dele. É a hora de "Atualizado às…".
- `state` assume `in_progress` ou `finished`, os nomes da D-037.
- `starts_on` e `ends_on` são as datas, em Brasília, do primeiro e do último jogo da janela.
- Mapeamento para os campos provisórios da D-037:
  - `state.round` → `current-round.json` › `round`;
  - `round.matches` → `predictions.matches`, filtrado por `match_ids` e `rescheduled_match_ids`;
  - `baseline.recomputed` → `baseline.reconstructed`;
  - `updated_at` mantém o nome.

  Os campos `pre_match` e `match.impact` não existem na v1.
- O arquivo não repete placar, nome de clube nem atribuição. Isso já está no `predictions.json` e no
  HTML, e o G4 continua cobrindo os dois.

Regras do contrato (o 06 testa):

- Todo id de `match_ids` e de `rescheduled_match_ids` existe no `predictions.json` da mesma
  execução, e nenhum aparece nas duas listas.
- `baseline.teams` tem exatamente os clubes do `predictions.json`, com valores iguais aos da visão
  do `rounds.json` com a mesma `reference_date`. Essa `reference_date` é anterior a `starts_on`.
- `updated_at`, `model_version` e `data_version` são iguais aos do `predictions.json`.
- Não há placar fora de `finished` em lugar nenhum: o `predictions.json` já é auditado assim, e o
  `IN_PLAY` continua `scheduled`.

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
  publicação só é disparada com `FINISHED`. A interface mostra jogo começado sem resultado como
  "aguardando placar" (D-037).
- Toda publicação passa pelo gate G1 a G5 e pelo `check_site_artifact.py`, que o 07 estende ao
  `current-round.json` (regras do contrato acima).
- Validação temporal inalterada (Decisão 2).
- A interface diz quando os dados foram atualizados (`updated_at`) e que os resultados costumam
  entrar de 30 a 60 min depois do fim do jogo (texto do 08). Não promete tempo real.
- R11 (o GitHub desativar agendamentos depois de 60 dias sem atividade): o novo workflow não muda o
  risco, que continua aceito. Ele também não faz commit. Os dois agendamentos param juntos, o site
  anterior continua no ar e reativar é um clique.

## Divisão do trabalho e ordem

| Ordem | Agente | Entrega | Critério de aceite |
|---|---|---|---|
| 1 | 01 | `kickoff_utc` e `kickoff_time_confirmed` no `MatchRecord`, no adaptador e no gold; invariante com `match_date`; catálogo atualizado | testes com fixture sintética (`TIMED`, `SCHEDULED`, jogo noturno que vira o dia em UTC); ingestão real de 2026 com 0 violações do invariante |
| 2 | 04 | `kickoff_utc` e `source_match_id` no `MatchPrediction`; `current-round.json` no `export_static_api` (o 04 pode editar esta função e as constantes de `config.py`, por este ADR) e rota na API; lógica num módulo do 04 em `src/brasileirao/storage/` | testes com fixtures sintéticas: jogo remarcado para fora da janela, jogo atrasado de outra rodada dentro do intervalo, jogo sem placar há mais de 48 h, rodada que começa hoje e ainda sem jogo encerrado (`in_progress`), virada para `finished`, pré-temporada (`round: null`), rodada 1 sem ponto de partida; regras do contrato |
| 3 | 06 | auditoria de 1 e 2 | regras do contrato, nenhum placar fora de `finished`, ponto de partida igual ao `rounds.json`, validação temporal |
| 4 | 07 | `atualizar-rodada.yml` e script; `inputs` e `run-name` do `publish-site.yml`; `check_site_artifact.py` com o `current-round.json`; opcional, O1 | função de decisão testada com relógio injetado; ensaio com `workflow_dispatch` e `MATCH_UPDATES` em `dry-run`; ver "Ligar" |
| paralelo | 08 | marcar na D-037 o que é v1 e o que fica fora (Decisão 3); trocar os campos provisórios pelos do contrato; ajustar a linha "a jogar" sem `pre_match`, o "encerrado" sem efeito nem chance anterior e o bloco "Última rodada" sem próxima rodada | D-037 revisada em `docs/brand/BRAND_DECISIONS.md` |
| 5 | 05 | escopo v1: abas e aba padrão da D-037 (rota `#/inicio/rodada`), jogos por dia com horário de Brasília e status, tabela "O que mudou desde o início da rodada" com o limiar de ruído e a regra do `model_version`, aviso de atualização; só lendo `current-round.json` e `predictions.json` | capturas em 1280 e 375 px: rodada em andamento, rodada que começa hoje, última rodada, rodada 1 sem ponto de partida e pré-temporada sem aba; sem erro de JS; fixture sintética para desenvolver antes do export real |
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
  do 06. O navegador só aplica a aba padrão e a troca de "a jogar" para "aguardando placar".
- **Versão completa da D-037 já na v1** (efeito por jogo, chance antes do jogo, faixas
  continentais, próxima rodada): adiada pelo dono. Cada item volta por decisão nova, com campo novo
  no contrato.

## Consequências

- O site passa a ser atualizado algumas vezes por dia de jogo (um por horário de início, em geral 3
  a 6), além da publicação diária.
- Mais minutos de runner (gratuitos em repositório público) e mais execuções no histórico do Actions.
- Contratos novos: horário no silver (01), dois campos no `MatchPrediction` e o `current-round.json`
  (04).
- A home ganha a opção "Rodada atual" ou "Última rodada" antes de Título, G4 e Rebaixamento (D-031
  muda; decisão do 08).
- Riscos novos R19 a R21 em `docs/project/risks.md`.
