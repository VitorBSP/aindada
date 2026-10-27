# C1 — Fonte de dados com licença verificada para publicação pública

- Status: **aprovada com ajustes (ADR-0008)**, em 2026-10-27. Os ajustes valem sobre este texto:
  `AllowedUse` fechado (`research_local`, `prototype_local`, `public_display_derived`,
  `redistribution`) no lugar das strings da seção 5, SQLite de snapshots em repositório privado e
  fonte de conferência nunca no gold. Passos 1 a 9 do plano implementados pelo Agente 01 em
  2026-10-27, testados só com fixtures sintéticas (ver `docs/data-sources/catalog.md` e
  `docs/project/status.md`). A ingestão real depende do download da v18 do Adão Duque pelo dono.
  A consulta de teste ao football-data.org foi feita em 2026-10-27 (seção 8), só localmente e sem
  gravar dados no repositório.
- Responsável: Agente 01. Origem: condição C1 do ADR-0007; bloqueio do ADR-0002.
- Escopo: pesquisa de termos e licenças. **Não é parecer jurídico.** Registra só o que cada fonte
  permite por contrato ou licença declarada. Placares são fatos, e a Lei 9.610/98 protege obras, não
  fatos. Mas uma base de dados pode ser protegida como compilação (art. 7º, XIII) e os termos
  de uso de um site podem restringir a coleta. Por isso a decisão segue o que está escrito em cada
  fonte.
- Todas as páginas abaixo foram acessadas em **2026-10-27**.

## 1. O que o modelo precisa

| Campo | Uso | Obrigatório |
|---|---|---|
| data da partida (fuso de Brasília), mandante, visitante | ordem temporal, mando, validação temporal | sim |
| gols do mandante e do visitante (tempo normal) | ratings, modelo de gols, tabela | sim |
| rodada | calendário e revisão por rodada | desejável |
| status (`finished`/`scheduled`/`postponed`) | partida sem placar é simulada, nunca vira 0 x 0 | sim |
| cartões por clube na temporada corrente | desempate (Art. 15, critérios 5 e 6) | não: abaixo de 95% de cobertura já vale o sorteio com aviso (hoje são 185 de 308 jogos) |

## 2. Fontes avaliadas

### 2.1 football-data.org (API v4, competição BSA)

- **Cobertura no plano gratuito.** A página de cobertura lista 12 competições gratuitas, entre elas
  "Serie A" com a bandeira do Brasil, e diz: *"Access to data of these leagues & cups is free.
  Forever."* (<https://www.football-data.org/coverage>). A página de preços descreve o plano
  gratuito como *"12 competitions"*, *"Scores delayed"*, *"Schedules delayed"*, *"League Tables"*,
  *"10 calls/minute"* e não inclui escalações, artilheiros nem cartões
  (<https://www.football-data.org/pricing>). A política de limites confirma *"Registered clients are
  allowed for 10 requests/minute in the free plan"*
  (<https://docs.football-data.org/general/v4/policies.html>).
- **Temporadas.** As páginas oficiais não dizem quais temporadas passadas o plano gratuito
  devolve, e fontes secundárias diziam que era só a corrente. **Verificado em 2026-10-27
  (seção 8):** o plano gratuito devolveu 2024, 2025 e 2026 completas (380 partidas cada, HTTP 200).
  Temporadas anteriores a 2024 não foram consultadas.
- **Termos** (Terms and Conditions na página de cadastro,
  <https://www.football-data.org/client/register>, em vigor desde 2018-06-01, cláusula 12.1):
  - 7.1, **atribuição obrigatória**: *"You agree to include the following attribution to
    Football-Data in your app or website"*: **"Football data provided by the Football-Data.org
    API"**. A página <https://www.football-data.org/about> pede local visível, como rodapé ou
    página "sobre".
  - 2.3, uma aplicação: *"The API Key applies to a single Application […] (i.e. for the web
    Application: the Subscription applies to a single domain name)."*
  - 6.1, credenciais: *"Developer credentials may not be stored in code repositories of open
    source projects."* No nosso caso, o token vai em segredo do GitHub Actions e no `.env` local,
    nunca no repositório.
  - 9.1, **dependência contínua**: *"After cancellation of the subscription to the Service, the
    Customer is not permitted to reference the football data obtained through the Football-Data
    API on their own site or service."*
  - 9.2: escudos e fotos *"are copyrighted by their legal owner"*. Não usamos escudos da API.
  - 8.1 e 8.2: sem garantia de disponibilidade nem de exatidão.
  - 11.1: os termos podem mudar a qualquer momento.
  - Os termos **não têm** cláusula sobre uso comercial ou não comercial, revenda, redistribuição,
    sublicenciamento ou cache. O serviço se apresenta para uso *"in your app or website"*. Exibir
    placares, tabela e probabilidades num site público com a atribuição é o uso previsto.
    **Redistribuir os dados brutos**, como um dump ou um SQLite público com placares, **não está
    autorizado expressamente**.
- **Atualização.** Placares têm atraso no plano gratuito. Isso basta para um site atualizado algumas
  vezes por semana (ADR-0007, item 9).
- **Cartões.** Não vêm no plano gratuito.
- **Origem dos dados**, segundo o próprio site: *"different upstreams, doing manual data checking
  each day"*.

### 2.2 Adão Duque, "Campeonato Brasileiro de Futebol" (Kaggle)

- O Kaggle declara a licença **"GPL 2"**, versão 18, atualizada em 2026-02-05. A descrição diz
  *"No total 9.165 partidas de 2003 a 2025"* e *"Coletamos os dados de páginas do Google."* Também
  diz *"Criamos rotinas que validam as rodadas e a tabela do campeonato."* Fontes: a página
  <https://www.kaggle.com/datasets/adaoduque/campeonato-brasileiro-de-futebol> e os metadados
  públicos em `https://www.kaggle.com/api/v1/datasets/view/adaoduque/campeonato-brasileiro-de-futebol`
  (`licenseNameNullable: "GPL 2"`, `currentVersionNumberNullable: 18`).
- Espelho no GitHub: <https://github.com/adaoduque/Brasileirao_Dataset>. **Não tem arquivo
  LICENSE** (`"license": null` na API do GitHub). Último commit em 2026-02-05 ("Brasileirão 2025").
  O `campeonato-brasileiro-full.csv` da raiz termina na 38ª rodada de 2024.
- Este é o dataset de origem do trecho 2003–2023 do `brasileirao-dataset` que usamos hoje. Ele
  também cobre 2024 e 2025 **sem passar pelo Sofascore**.
- Conteúdo: data, hora, rodada, mandante, visitante, placar, técnicos, estádio, além de arquivos de
  cartões, gols e estatísticas.
- **Obrigações da GPL-2** se os dados forem redistribuídos: manter o aviso de licença, entregar o
  texto da GPL-2 e distribuir as cópias e modificações sob a mesma licença. A GPL foi escrita para
  software, e aplicá-la a dados é incomum. Fica registrado como está, sem interpretação.
- **Limitações.** A coleta foi feita "de páginas do Google", que exibem dados licenciados de
  terceiros, então a proveniência do autor é de segunda mão. Não há atualização a cada rodada: as
  temporadas são publicadas depois de encerradas.

### 2.3 openfootball (`south-america/brazil` e `football.json`)

- Licença **CC0-1.0** nos dois repositórios (API do GitHub; o `LICENSE.md` é o texto do CC0 1.0
  Universal). Fontes: <https://github.com/openfootball/south-america> (último push 2026-10-20) e
  <https://github.com/openfootball/football.json>.
- Cobertura: `brazil/2018_br1.txt` a `2026_br1.txt`. O `football.json` só tem `br.1.json` para 2019,
  2020, 2025 e 2026; `2024/br.1.json` dá 404.
- Atualização: o `2026_br1.txt` foi atualizado pela última vez em 2026-09-21 ("auto-update week
  39"). Em 2026-10-27, o `2026/br.1.json` tinha 277 partidas com placar em 380, contra 308
  observadas na fonte atual. **Está cerca de cinco semanas atrasado.**
- **Origem dos dados.** O README de atualização do mantenedor (<https://github.com/yorobot/fbup>)
  lista `br.1 2024` no passo *"Step 1 - Get Match Data via fbdat (api)"*. O `fbdat` é o executável
  da gem `footballdata-api`, do mesmo autor, descrita como *"get football data via Daniel Freitag's
  football-data.org api v4"* (<https://rubygems.org/gems/footballdata-api>, versão 2026.7.12, que
  contém `bin/fbdat`). Ou seja, o Brasil recente do openfootball **vem do football-data.org** e foi
  publicado como CC0, coisa que os termos do football-data.org não concedem expressamente. Ele
  **não é** uma fonte independente, e o rótulo CC0 não remove a dúvida sobre a origem.

### 2.4 Wikipédia em português e Wikidata

- A página da Série A 2026 na Wikipédia em português tinha a matriz "Confrontos" (mandante x
  visitante) e a classificação *"Atualizado até os jogos disputados em 26 de outubro"*, com edição
  em 2026-10-27 (<https://pt.wikipedia.org/wiki/Campeonato_Brasileiro_de_Futebol_de_2026_-_S%C3%A9rie_A>).
  A matriz não traz a data de cada jogo. O texto é **CC BY-SA 4.0**, com atribuição e
  compartilhamento pela mesma licença (Termos de Uso da Wikimedia). Riscos: edições sem revisão,
  formato de tabela instável e ausência de data por partida.
- **Wikidata** (CC0): uma consulta SPARQL em 2026-10-27 (temporadas com `P3450 = Q206813` e partidas
  `P31 = Q16466010` com `P361` na temporada) **devolveu 0 partidas** em todas as temporadas de 2003 a
  2026. Não serve como fonte de resultados.

### 2.5 CBF

- É a fonte oficial: tabela, súmulas e regulamento. Não tem API pública documentada.
- Os termos de uso **não foram lidos**: <https://www.cbf.com.br/termos-de-uso> falhou no certificado
  TLS ao ser acessado em 2026-10-27. **A verificar.**
- Uso proposto: só a **conferência manual** dos jogos publicados, como pede o C1. Nada de coleta
  automatizada.

### 2.6 Football-Data.co.uk (`BRA.csv`)

- A página do Brasil (<https://www.football-data.co.uk/brazil.php>, atualizada em 27/10/26) diz
  *"My data is free"* e não traz licença nem permissão de redistribuição.
- O aviso legal (<https://www.football-data.co.uk/disclaimer.php>) só trata de exatidão e de
  apostas.
- O `notes.txt` credita os resultados a *"XScores […] BBC, Flashscore, ESPN Soccer"*.
- Uso: o benchmark de odds já planejado, só local. Não serve como fonte publicada.

### 2.7 API-Football (api-football.com)

- A página de termos (<https://www.api-football.com/terms>) devolveu 403 ao ser acessada
  diretamente. Pela busca, o texto diz *"The data we provide is obtained from partners, it is
  prohibited to resell this data to third parties"* e proíbe várias contas para aumentar o limite
  gratuito.
- Plano gratuito: 100 requisições por dia, segundo fontes secundárias. A profundidade de temporadas
  do plano gratuito é **contraditória** entre as fontes. **A verificar.**
- Exigiria aceitar um segundo conjunto de termos, com dados de parceiros, sem vantagem sobre o
  football-data.org. Não recomendada.

## 3. Tabela comparativa

| Fonte | Cobertura Série A | Atualiza a cada rodada? | Licença ou termos | Atribuição | Redistribuir dados brutos | Confiabilidade | Papel proposto |
|---|---|---|---|---|---|---|---|
| football-data.org (grátis, BSA) | 2024, 2025 e 2026 confirmadas (seção 8); antes de 2024 não consultado | sim, com atraso (horas, seção 8) | T&C próprios; sem cláusula de uso comercial | **obrigatória** (7.1) | não autorizada expressamente | média-alta (QA manual diária, sem garantia) | **corrente (2026+)** |
| Adão Duque (Kaggle v18) | 2003–2025 | não (por temporada) | **GPL 2** declarada no Kaggle | aviso GPL | sim, sob GPL-2 | média (coleta de "páginas do Google", com validação de rodadas) | **histórico 2003–2025** |
| Adão Duque (GitHub) | 2003–2024 na raiz, 2025 em `data/` | não | sem LICENSE | — | não declarada | igual | só para conferir o hash contra o Kaggle |
| openfootball | 2018–2026 | não (semanal e irregular; 5 semanas de atraso) | CC0 declarado | não exigida | sim, pelo rótulo, mas a origem é o football-data.org | média | nenhum na publicação; conferência local, sem ser independente |
| Wikipédia (pt) | por temporada | sim, por voluntários | CC BY-SA 4.0 | obrigatória | sim, sob CC BY-SA | média (sem data por jogo; risco de vandalismo) | conferência cruzada **independente**, só local |
| Wikidata | nenhuma partida | — | CC0 | — | — | — | descartada |
| CBF | oficial | sim | termos **a verificar** | — | — | alta | conferência manual dos jogos publicados |
| Football-Data.co.uk | 2012+ | sim | "my data is free", sem licença | — | não declarada | média | benchmark de odds local |
| API-Football (grátis) | a verificar | sim | proíbe revenda; dados de parceiros | a verificar | não | média-alta | descartada |
| brasileirao-dataset (atual) | 2003–2026 | sim | sem LICENSE; 2024+ do Sofascore | — | não | média | **sai da publicação**; só conferência local |

## 4. Recomendação

**Combinação de menor risco e custo zero:**

1. **Histórico 2003–2025: Adão Duque, Kaggle versão 18, sob GPL-2.** A versão é fixada pelo número
   e pelo SHA-256 dos arquivos. Isso elimina o Sofascore também de 2024 e 2025, e não só de 2026.
   Se os dados brutos forem versionados ou publicados, vão junto o texto da GPL-2 e o aviso de
   origem.
2. **Temporada corrente (2026+): football-data.org, plano gratuito.** Usa o token do dono em segredo
   do Actions, mostra a atribuição exata da cláusula 7.1 no rodapé e na metodologia (texto do C2:
   08 e 05) e se limita a um único domínio (o `github.io` do projeto). Publica **só dados exibidos e
   derivados**: placares na interface, tabela e probabilidades. **Dados brutos não vão para o
   repositório nem para assets públicos.**
3. **Conferência, só local e nunca publicada:**
   - Wikipédia (pt) como conferência independente dos placares. É a única fonte livre que não
     deriva do football-data.org.
   - O `brasileirao-dataset` atual, para medir as diferenças antes da troca.
   - A CBF na conferência manual dos jogos publicados, como exige o C1.
   - Divergências vão para `data/silver/changes.jsonl` ou para o relatório de qualidade. Nenhuma é
     corrigida automaticamente.
4. **Cartões.** Sem fonte licenciada para 2026, o desempate por cartões continua no sorteio com
   aviso, que já é o comportamento abaixo de 95% de cobertura. Os cartões do Adão Duque só cobrem
   temporadas encerradas.
5. **O plano gratuito devolveu 2024 e 2025** (seção 8). A recomendação se mantém: o histórico
   publicado vem do Adão Duque até 2025, que não depende da conta (cláusula 9.1) e permite
   redistribuição sob GPL-2, e o football-data.org 2024–2025 vira **conferência cruzada local**
   entre as duas fontes. Usar o football-data.org também para 2024–2025 na publicação seria
   possível, mas ampliaria a dependência da cláusula 9.1 sem ganho de cobertura.

**Riscos residuais que o dono precisa aceitar:**

- (a) A cláusula 9.1 do football-data.org: se a conta for cancelada, o site não pode mais
  referenciar esses dados, nem nos snapshots antigos.
- (b) Os termos do football-data.org podem mudar (11.1).
- (c) A GPL-2 aplicada a dados, e a proveniência de segunda mão do Adão Duque.
- (d) Nenhuma das fontes garante exatidão.

## 5. Impacto no pipeline (proposta para o 00 aprovar; nada implementado)

- **Novo adaptador `AdaoDuqueSource`** em `data_pipeline/sources.py`:
  - Lê os CSVs da versão 18 do Kaggle, baixados pelo dono para `data/raw/adaoduque/v18/`.
  - Registra no manifesto `license_status` com a GPL-2 declarada, origem, versão, data e SHA-256.
  - O formato de data é `dd/mm/aaaa` e o placar pode faltar: sem placar, a partida fica
    `scheduled`.
  - Fixture sintética em `tests/fixtures/`.
- **`FootballDataOrgSource`:**
  - **Corrigir a data.** Hoje o código usa `utcDate` e tira a data em UTC, o que joga os jogos das
    21h30 de Brasília para o dia seguinte e afeta a validação temporal. A conversão deve ser para
    `America/Sao_Paulo` antes de `.date()`.
  - Gravar `retrieved_at` por requisição.
  - Respeitar 10 requisições por minuto. Uma por temporada já basta.
  - Mapear `AWARDED` com cuidado: o placar do W.O. deve ir para as exceções conhecidas.
- **Contrato** (`contracts.LicenseStatus`, que é do 01 mas precisa do aval do 00): hoje não há
  valor para "termos aceitos com atribuição".
  - Proposta: `licensed_with_attribution`.
  - `allowed_uses` como `("public_display_with_attribution",)` para o football-data.org e
    `("public_display", "redistribution_gpl2")` para o Adão Duque.
  - O gate do workflow (07) passa a falhar se uma partida publicada vier de fonte sem esses usos.
- **Ingestão por temporada com precedência explícita:** 2003–2025 vêm do Adão Duque e 2026+ do
  football-data.org. O `brasileirao_dataset` sai do caminho de publicação.
- **Clubes:** novos aliases em `data/reference/clubs.csv` para os nomes do football-data.org
  ("CR Flamengo", "SE Palmeiras" etc.) e do Adão Duque. Pelo critério de aceite, não pode sobrar
  alias órfão.
- **Recalcular tudo sem o Sofascore** (02 e 06): ratings, treino, backtest e `model_version`/
  `data_version` novos. A validação temporal continua igual: cada data de referência só usa
  partidas com `match_date` anterior a ela.
- **Persistência (07 e 00):** o SQLite de snapshots contém placares do football-data.org. Um asset
  de release público num repositório público redistribui dados brutos, o que os termos não
  autorizam expressamente. Alternativas:
  - guardar o asset num **repositório privado** separado, que também é gratuito;
  - ou guardar no asset público só os snapshots derivados, sem a tabela de partidas.
  - Decisão do 00 e do 07, com reflexo no item 4 do ADR-0007.

## 6. O que depende do dono do produto

1. **Criar a conta gratuita no football-data.org e aceitar os T&C.** Gerar o token e guardá-lo no
   `.env` local e no segredo `FOOTBALL_DATA_ORG_TOKEN` do repositório. Nunca versionar (cláusula
   6.1). Quem faz isso é o dono, não um agente.
2. **Feito em 2026-10-27 (seção 8), pelo 01 com autorização.** Era: fazer uma sondagem única com
   o token, ou autorizar o 01 a rodá-la localmente: chamar
   `/v4/competitions/BSA` e `/v4/competitions/BSA/matches?season=2024`, `2025` e `2026`, e
   registrar o código HTTP e a contagem de partidas por temporada. Isso fecha o "a verificar" sobre
   temporadas.
3. **Baixar a versão 18 do dataset de Adão Duque no Kaggle** (exige conta) ou autorizar o uso do
   espelho no GitHub conferido por hash. Opcional, mas recomendado: escrever ao autor
   (adaoduquesn@gmail.com) pedindo confirmação de que a GPL-2 vale para o GitHub e para 2024–2025,
   e perguntando quais "páginas do Google" foram usadas.
4. **Aceitar os riscos residuais** da seção 4: a cláusula 9.1, a GPL-2 em dados e a ausência de
   garantia.
5. **Aprovar o texto de atribuição no rodapé:** "Football data provided by the Football-Data.org
   API", mais o crédito GPL-2 ao dataset de Adão Duque (C2, com 08 e 05).
6. **Decidir onde fica o SQLite de snapshots:** asset público ou repositório privado.
7. **Ler os termos de uso da CBF** num navegador e definir quem faz a conferência manual dos jogos
   publicados.

## 7. A verificar

- ~~Quais temporadas da BSA o plano gratuito do football-data.org devolve.~~ Resolvido na seção 8:
  2024, 2025 e 2026. Antes de 2024 não foi consultado (a competição lista 10 temporadas).
- ~~Se o atraso de placares do plano gratuito combina com o agendamento.~~ Resolvido na seção 8: o
  último jogo (26/10, 20h de Brasília) já estava `FINISHED` com placar em 27/10 às 04h25 UTC.
  Atraso de horas, compatível com atualização algumas vezes por semana. A medição tem só esse
  ponto.
- Os termos da CBF (falha de TLS no acesso).
- Os termos completos e as temporadas gratuitas da API-Football (403 no acesso direto).
- Se a versão 18 do Kaggle é idêntica ao GitHub do Adão Duque (comparar os hashes depois do
  download).
- O quanto o Adão Duque 2003–2023 coincide com o `brasileirao-dataset` atual (comparação local).

## 8. Consulta de teste (2026-10-27)

Feita pelo Agente 01 com autorização do dono do produto, só localmente. O token foi lido do `.env`
dentro do script e enviado apenas no header `X-Auth-Token`. Foram 4 chamadas, entre 19h42 e 19h43
UTC, com 7 s de intervalo. As respostas brutas ficaram fora do repositório e nada foi ingerido.
Esta seção traz só agregados: nenhum placar e nenhuma credencial.

### 8.1 Resultados por chamada

| Chamada | HTTP | Erro | `X-Requests-Available-Minute` | Partidas | Status | Datas (Brasília) | `FINISHED` com placar `fullTime` |
|---|---|---|---|---|---|---|---|
| `GET /v4/competitions/BSA` | 200 | nenhum | 9 | — | — | `currentSeason` de 2026-01-28 a 2026-12-02, `currentMatchday` 33, 10 temporadas listadas | — |
| `GET .../matches?season=2024` | 200 | nenhum | 9 | 380 | 380 `FINISHED` | 2024-04-13 a 2024-12-08 | 380 de 380 |
| `GET .../matches?season=2025` | 200 | nenhum | 8 | 380 | 380 `FINISHED` | 2025-03-29 a 2025-12-07 | 380 de 380 |
| `GET .../matches?season=2026` | 200 | nenhum | 7 | 380 | 319 `FINISHED`, 40 `SCHEDULED`, 20 `TIMED`, 1 `POSTPONED` | 2026-01-28 a 2026-12-01 | 319 de 319 |

- Headers de limite: `X-RequestCounter-Reset` (segundos até zerar a janela) e
  `X-Requests-Available-Minute`. Também vêm `X-API-Version: v4` e `X-Authenticated-Client`.
- Todas as partidas `FINISHED` têm `score.duration = REGULAR`. Não há `AWARDED`, prorrogação nem
  pênaltis.
- Rodadas de 1 a 38 em todas as temporadas. Nenhum par mandante/visitante se repete. A rodada da
  API coincide com a da fonte atual em todas as 1.140 partidas.
- Cartões não vêm no endpoint de partidas do plano gratuito, como já estava previsto.

### 8.2 Atraso aparente em 2026

- Último jogo `FINISHED`: 2026-10-26, 20h de Brasília. O campo `lastUpdated` mais recente era
  2026-10-27T04:25Z.
- Jogos com início já passado (até 27/10, 16h43 de Brasília) que não estão `FINISHED`: **1**, que é
  o `POSTPONED` da rodada 21 (data original 2026-07-28). A fonte atual também o tem sem placar.
- A rodada 33 começa em 28/10. Não há jogo disputado faltando.

### 8.3 Comparação local com `data/silver/matches.csv`

Usou um mapeamento provisório de nomes (os aliases da seção 8.4), mantido fora do repositório. As
chaves de comparação foram mandante, visitante e temporada (cada par é único na temporada) e depois a
data.

| Temporada | Pares casados | Mesma data (Brasília) | Data diferente: UTC da fonte atual | Data diferente: outras | Divergência de status | Divergência de placar |
|---|---|---|---|---|---|---|
| 2024 | 380 de 380 | 309 | 71 | 0 | 0 | 0 de 380 |
| 2025 | 380 de 380 | 313 | 67 | 0 | 0 | 0 de 380 |
| 2026 | 380 de 380 | 280 | 69 | 31 | 0 | 0 de 319 |

- **Placares: nenhuma divergência** nos 1.079 jogos encerrados das três temporadas, e os 319
  `FINISHED` de 2026 são os mesmos 319 `finished` da fonte atual. Isso não prova exatidão, porque
  as duas podem vir de fornecedores parecidos.
- **Achado de qualidade na fonte atual:** as 207 datas da coluna "UTC da fonte atual" são
  exatamente a data em UTC do pontapé inicial, um dia depois da data de Brasília (jogos noturnos). A
  fonte atual (`partidas_resumo.json` do `brasileirao-dataset`, 2024+ do Sofascore) já traz a data
  sem hora e no dia UTC. O nosso parser não erra aqui, mas a validação temporal de 2024 a 2026 está
  deslocada em um dia nesses jogos. O problema é aberto em `docs/project/status.md` e some com a
  troca de fonte, se o `FootballDataOrgSource` converter para `America/Sao_Paulo`. Com o código
  atual, que usa a data UTC, o football-data.org reproduziria o mesmo erro em 96 das 380 partidas
  de 2026, 71 de 2024 e 67 de 2025.
- As 31 outras diferenças de data em 2026 são todas de jogos não disputados: 1 `POSTPONED` da
  rodada 21, 10 jogos já detalhados (`TIMED`) nas rodadas 33 e 34, e 20 jogos das rodadas 36 e 37
  (`SCHEDULED`, sem horário confirmado). Isso é diferença de calendário, não de resultado.

### 8.4 Nomes de clubes sem alias em `data/reference/clubs.csv`

Nenhum dos 27 nomes distintos da API casa hoje com o registro. Os aliases necessários são:

| Nome no football-data.org | `club_id` |
|---|---|
| AC Goianiense | atletico-go |
| Botafogo FR | botafogo |
| CA Mineiro | atletico-mg |
| CA Paranaense | athletico-pr |
| Ceará SC | ceara |
| Chapecoense AF | chapecoense |
| Clube do Remo | remo |
| Coritiba FBC | coritiba |
| CR Flamengo | flamengo |
| CR Vasco da Gama | vasco |
| Criciúma EC | criciuma |
| Cruzeiro EC | cruzeiro |
| Cuiabá EC | cuiaba |
| EC Bahia | bahia |
| EC Juventude | juventude |
| EC Vitória | vitoria |
| Fluminense FC | fluminense |
| Fortaleza EC | fortaleza |
| Grêmio FBPA | gremio |
| Mirassol FC | mirassol |
| RB Bragantino | bragantino |
| Santos FC | santos |
| São Paulo FC | sao-paulo |
| SC Corinthians Paulista | corinthians |
| SC Internacional | internacional |
| SC Recife | sport |
| SE Palmeiras | palmeiras |

Gravados no `clubs.csv` em 2026-10-27, com o adaptador (ADR-0008, passo 4), e cobertos por
`tests/unit/test_club_aliases.py`. Com eles, as 1.140 partidas casam com a fonte atual, sem alias órfão.

### 8.5 Implicações

- O "a verificar" sobre temporadas e atraso está fechado (seção 7).
- O encaixe da seção 4 continua igual: Adão Duque publica até 2025 e o football-data.org publica de
  2026 em diante. O football-data.org 2024–2025 passa a servir de conferência cruzada local contra o
  Adão Duque, e essa conferência agora é possível com o plano gratuito.
- A correção de fuso no `FootballDataOrgSource` (seção 5) passa de "recomendada" a **obrigatória**,
  porque afeta 25% das partidas de 2026.
- Com 1 chamada por temporada e cerca de 7 por minuto ainda livres, uma atualização de 2026 por
  execução do workflow cabe com folga no limite.
