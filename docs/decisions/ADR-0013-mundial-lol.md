# ADR-0013 — Mundial de LoL: Elo de liga + time e mata-mata em melhor de 5

- Status: **proposto** (2026-10-30). Implementado na `main` local com evidência; publicação depende do parecer
  do 06 e do 00 (AGENTS.md).
- Responsáveis: Agente 00 (decisão), 01 (fontes), 03 (regras do torneio), 02 (modelo), 04/05 (export e site),
  06 (validação), 07 (workflow), 08 (seletor e aviso da Riot).
- Origem: pedido do dono do produto (chat, 2026-10-30): "construir um para o LoL, para o mundial de LoL", na
  forma "Página rápida 2026", com "Seguir com Wikipédia". Prazo: antes das quartas (3/11/2026).

## Decisão 1 — Fontes

| Fonte | Situação | Motivo |
|---|---|---|
| Wikipédia em inglês (API MediaWiki), artigos dos eventos | **usada** | CC BY-SA 4.0; API pública; resultados por série e placar em mapas no modelo `{{Esports match}}` |
| Leaguepedia (Fandom) | descartada | os Termos da Fandom proíbem acesso por "robot, spider, scraper or other automated means" sem permissão escrita; a API respondeu com limite de taxa e desafio do Cloudflare. Sem raspagem nem contorno de proteção |
| Oracle's Elixir (CSVs por partida) | adiada | download aprovado pelo dono, mas o Google Drive devolveu "Quota exceeded". Entra depois se os CSVs forem colocados em `data/raw/oracles_elixir/` |
| API oficial da Riot / lolesports | não usada | sem chave de produção; a política de fãs da Riot vale para o uso de nomes e marcas |

- Eventos: MSI 2025, Mundial 2025 e MSI 2026 fixados por revisão (`data/reference/lol_source_pins.json`); o
  Mundial 2026 entra na revisão mais recente a cada execução. Cada artigo tem manifesto com URL da revisão,
  data de coleta, SHA-256, licença e atribuição.
- Só resultados (quem venceu, placar em mapas, data, fase); nenhum texto da Wikipédia é reproduzido.
- A página lista série agendada com `0` e `0` e atualiza placares ao vivo: uma série só conta como jogada quando
  o vencedor chega às vitórias do formato (fase suíça: 1, ou 2 quando decide vaga ou eliminação; mata-mata: 3).
  Placar parcial volta a ser agendado (`score1 = score2 = None`); nunca vira resultado nem treina o Elo.
- Cadastro revisado à mão `data/reference/lol_teams.csv` (27 times, liga e grafias). Time fora do cadastro faz a
  ingestão falhar: nada é adivinhado. A tabela de classificados do artigo foi testada e descartada como fonte da
  liga (o `rowspan` misturava ligas).
- **Política da Riot ("Legal Jibber Jabber")**: projeto de fãs, gratuito e não comercial; aviso obrigatório no
  rodapé ("AInda dá? foi criado sob a política…"); sem logos da Riot nem dos times (só siglas em texto). A Riot
  pode revogar a permissão a qualquer momento: **risco aceito pelo dono do produto** ("Aceito", 2026-10-30).

## Decisão 2 — Regras do torneio (Agente 03)

Do artigo do Mundial 2026: fase suíça com 16 times, 3 vitórias classificam e 3 derrotas eliminam; rodadas 1 e 2
em melhor de 1, jogos que decidem vaga ou eliminação em melhor de 3. Sorteio das quartas: os dois times 3–0 em
lados opostos, contra times 3–2; os demais são sorteados. Quartas 1 e 2 formam a semi 1; 3 e 4, a semi 2. Mata-mata
em melhor de 5; final em 14/11. Onde a organização sorteia, a simulação sorteia com chances iguais. Confronto já
definido na página é respeitado (quartas definidas em parte: o resto é sorteado entre os classificados); série
já jogada entra com o resultado real, procurada pelos dois times em toda a fase; semi definida na página manda
no pareamento.

## Decisão 3 — Modelo (Agente 02; ideia do dono do produto)

- **Elo em dois níveis** (`esports/model.py`): força do time = força da liga + ajuste do time dentro da liga.
  Cada série atualiza os ajustes com `k_team` e, se as ligas forem diferentes, a força das ligas com `k_league`,
  pela surpresa em mapas (mapas vencidos − mapas jogados × chance esperada por mapa). Na virada do ano, o ajuste
  do time volta parte do caminho a zero (`team_regression`). Sem lado do mapa nem mando.
- Um Elo só por time (sem a liga) perde para o de dois níveis já na validação (0,669 a 0,670 contra 0,632 por
  mapa; no teste, 0,681 a 0,731, sem superar a moeda): cada time joga poucas séries internacionais. Com a liga, os resultados de todos os times de uma região se somam.
- Série: mapas independentes, chance de vencer uma melhor de N a partir da chance por mapa.
- Calibração (`esports.cli tune`): grade de 75 combinações; escolha na validação (Mundial 2025 e MSI 2026, 155
  mapas); teste só relatado (séries jogadas do Mundial 2026). Escolhidos: `k_league` 24, `k_team` 8,
  `team_regression` 1,0. Versão `lol-0.1.0`.
- Simulação (`esports/worlds.py`): ratings fixos na data de referência; completa a fase suíça rodada a rodada,
  sorteia as quartas pela regra e joga o mata-mata. Semente registrada.

## Decisão 4 — Site e publicação

`apps/web-lol/` em `/mundial-lol/`; seletor de competições (D-039) com "Mundial de LoL" em todos os sites
(D-042). No `publish-site`, passo próprio `Mundial de LoL — ingestão, previsão e gate`, sem segredo, com falha
isolada (`continue-on-error`) e fallback: sem previsão nova, o `forecast.json` no ar volta só se passar no gate;
sem versão válida, o site sai sem `/mundial-lol`. Gate (`esports/gate.py`): esquema, data de referência, aviso
da Riot, somas por fase (8, 4, 2 e 1), fases em ordem, eliminado sem chance, classificado com 100%, fontes com
licença e atribuição e nada além do `forecast.json` em `data/`. A API local monta `/mundial-lol/`.

"Como calculamos" da página do LoL é próprio: o módulo comum de métodos (D-040) não tem aba de LoL. Fica com o
Agente 08 decidir se entra.

## Evidência e pendências

Ver `docs/methodology/validation.md` (Mundial de LoL) e `docs/project/status.md`. Pendências: parecer do 06; teste
curto (61 mapas); jogos das ligas nacionais fora (Oracle's Elixir); conferir as regras no regulamento oficial da
Riot quando houver texto público; aba do LoL em "Como calculamos" (08).
