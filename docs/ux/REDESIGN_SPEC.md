# REDESIGN_SPEC — AInda dá? v2.1 (App Esportivo Mobile-First, Dark Default)

> **Status:** Especificação revisada e aprovada pelo dono do produto após validação em protótipo interativo (D-051, 2026-11-24).
> **Objetivo:** Transformar o AInda dá? de "caderno de dados com muito texto" em um **app esportivo limpo, rápido e visual no celular** (390/375 px primeiro, desktop 1080/1280 px fluido), preservando a paleta oficial da marca, zero build step (HTML/CSS/JS puros em `apps/web/`) e 100% de compatibilidade com os JSONs, o gate G4 e as regras do modelo.
> **Lição aprendida da primeira tentativa da T4 (`2bdf09a`):** apenas pintar o layout antigo de escuro manteve paredes de texto (`.lede`, `.note`, legendas longas), 3 andares de cabeçalho, fonte serifa (Georgia), `<select>` nativo e botões redundantes ("Ver detalhes") dentro dos cards. Esta v2.1 define cortes e trocas **obrigatórios**.

---

## 1. Princípios Inegociáveis da v2.1

1. **Zero parede de texto nas telas principais (`#/`, `#/classificacao`, `#/jogos`):**
   - **Remover** parágrafos `.lede`, `.note` explicativas longas, legendas de 3 linhas na Tabela e o bloco *"Continue explorando"* da Home/Tabela/Jogos.
   - Toda explicação metodológica, data completa da edição e notas de cálculo saem do corpo da tela e vão para o **sheet `(i)` no cabeçalho** e para a página `#/metodologia` (*Como calculamos*).
   - **Exceção obrigatória (Gate G4 + ADR-0014):** o `<footer>` no HTML estático (`index.html`) continua presente e compacto no fim da página com as atribuições exatas do `football-data.org`, Adão Duque v18 e link de retirada de escudos (nunca remover nem quebrar palavras das atribuições, senão o gate G4 reprova o deploy).
2. **Tipografia 100% app (`Inter Tight`), zero serifa na UI:**
   - Remover `Georgia` / `var(--serif)` dos textos de interface, subtítulos e cards. Tudo usa `"Inter Tight"` com `font-variant-numeric: tabular-nums` em placares, posições e percentuais.
3. **Vocabulário da marca (D-046):** usar **"probabilidade"** (ou rótulos curtos como `Título · G4 · Queda`) no lugar de "chance" nos textos visíveis.
4. **Paleta oficial AInda dá? — Escuro por padrão:**
   - `:root` usa o tema escuro; toggle discreto salva `data-theme="light"` em `localStorage` (`ainda-da:tema`).

| Token | Dark (Padrão) | Light (Opcional) | Uso |
|---|---|---|---|
| `--paper` | `#17191C` | `#FAFAF7` | Fundo principal |
| `--surface` | `#1D2024` | `#FFFFFF` | Cards principais (`radius: 16px`, `border: 1px solid var(--rule)`) |
| `--surface-2` | `#24282E` | `#F1F0EA` | Pílulas 1X2, chips inativos, steppers, botão secundário, skeleton |
| `--surface-3` | `#2C3138` | `#E7E5DD` | Hover/active sobre `--surface-2` |
| `--ink` | `#F7F5EF` | `#17191C` | Texto principal e números em destaque |
| `--ink-soft` | `#B9BBBF` | `#4A4E55` | Metadados secundários |
| `--ink-faint` | `#8D9198` | `#6B6F76` | Rótulos auxiliares, horários, 0% |
| `--rule` | `#2D3138` | `#E2E1DB` | Bordas finas de 1 px (sem `box-shadow` pesado) |
| `--signal` | `#FF6A4D` | `#D9381E` | Item ativo na nav, borda de destaque da maior probabilidade, links curtos |
| `--signal-fill` | `#D9381E` | `#D9381E` | Botão primário cheio e badge `AO VIVO` |
| `--on-signal-fill` | `#FFFFFF` | `#FFFFFF` | Texto sobre `--signal-fill` (contraste 4,63:1 WCAG AA) |
| `--libertadores` | `#8FB2EE` | `#1F4F99` | G4 / Libertadores (soft: `rgba(143,178,238,0.14)` / `#E3EBF7`) |
| `--sudamericana` | `#E6AC58` | `#8A5300` | Sul-Americana (soft: `rgba(230,172,88,0.14)` / `#F6EAD6`) |
| `--danger` | `#F08A82` | `#B3261E` | Z4 / Rebaixamento (soft: `rgba(240,138,130,0.14)` / `#F8E1DF`) |

- **Travas anti-"cara de IA":** zero verde-neon de casa de aposta, zero gradiente colorido, zero fotos sem licença, zero campo 3D, zero caixa alta com `letter-spacing` largo fora de cabeçalho mínimo de tabela (10–11 px).

---

## 2. Cabeçalho em 1 Andar e Navegação (Mobile 375 px -> Desktop 1080 px)

### 2.1 Cabeçalho único (56 px no celular — fim dos 3 andares)
- **Esquerda:** assinatura SVG oficial (`ainda-da-assinatura-compacta-reversa.svg` no escuro / `compacta.svg` no claro, altura 26–30 px no mobile, 32 px no desktop) + **chip único da competição atual** (ex.: `Série A ▾`, estilo pílula em `--surface-2`). Tocar no chip abre um **bottom-sheet limpo com grade 2 colunas** das 6 competições (`Série A`, `Série B`, `Premier League`, `LaLiga`, `Champions League`, `Mundial de LoL`).
- **Centro (somente desktop `>= 900px`):** links horizontais `Início · Tabela · Jogos · Simular · Rodadas · Ao vivo`.
- **Direita:** botão circular compacto `(i)` (abre sheet com data completa da edição, contagem de jogos/simulações e link para `#/metodologia`) + botão Sol/Lua de tema (`40–44 px`).
- **A antiga faixa `#reference-bar` e a barra `.leagues` empilhada no topo somem no celular** (a data de referência continua visível no sheet `(i)` e como subtítulo curto `R37 · 24/11` dentro da tela, sem comer um andar inteiro de cabeçalho).

### 2.2 Barra inferior fixa no celular (`mobile-nav.js` — ordem obrigatória)
- Altura `64px + env(safe-area-inset-bottom)`, fundo translúcido `--nav-bg` com `backdrop-filter: blur(12px)`, borda superior `1px solid var(--rule)`.
- **Ordem exata dos 5 itens na Série A** (não depender apenas dos "4 primeiros do `<nav>`" se `Clubes` vier antes de `Simular`):
  1. `Início` (`#/`)
  2. `Tabela` (`#/classificacao`)
  3. `Jogos` (`#/jogos`)
  4. `Simular` (`#/simular`)
  5. `Mais` (abre bottom-sheet com: *Ao vivo*, *Rodada a rodada*, *Clubes*, *Trocar competição*, *Como calculamos*).
- Nas outras 5 competições (sem simulador ainda), manter até 4 itens principais + `Mais`.

---

## 3. Anatomia das 4 Telas Principais (Zero Poluição)

### 3.1 Botões e controles padrão app (substituem os antigos)
- **Botão primário (`.btn-primary`):** altura `44px`, `border-radius: 12px`, fundo `--signal-fill` (`#D9381E`), texto `#FFFFFF`, peso `700`, sem borda.
- **Botão secundário (`.btn-secondary`):** altura `44px`, `border-radius: 12px`, fundo `--surface-2`, texto `--ink`, borda `1px solid var(--rule)`.
- **Chips / Pílulas de filtro (`.chip`):** `border-radius: 999px`, altura `34–38px`, fundo `--surface-2`, texto `--ink-soft`; ativo inverte para fundo `--ink` (`#F7F5EF`) e texto `--paper` (`#17191C`), peso `700`.
- **Proibido em listas/cards:** botão de texto sublinhado ou retângulo quadrado *"Ver detalhes"* / *"Ver o que aconteceu"* dentro do Match Card. O card inteiro é o alvo de toque (com um `›` sutil no canto superior direito).

### 3.2 Match Card v2.1 (Home, Jogos, Clubes, Ao Vivo)
```text
+----------------------------------------------------+
| R37 · Dom 16:00                          ›         |  <- 11px --ink-faint (ou badge AO VIVO / Encerrado)
|                                                    |
|  [Escudo 38px]        1 × 1        [Escudo 38px]   |  <- placar 24px 900 tnum (ou pílula "VS" se futuro)
|    Palmeiras                         Flamengo      |  <- 12px 700, truncate
|                                                    |
|  [ 31% PAL ]     [ 35% Empate ]     [ 34% FLA ]    |  <- 3 pílulas --surface-2; a maior com borda --signal
+----------------------------------------------------+
```
- **O que SAI do card:** linha textual *"Gols esperados 1,3 × 1,4..."* e botão *"Ver detalhes"*. Tudo isso abre dentro do **bottom-sheet / `<dialog>`** ao tocar em qualquer lugar do card (`match-popup.js`).
- **Rótulo das pílulas 1X2:** usar sigla/nome curto dos clubes (`PAL`, `Empate`, `FLA`) em vez de *"Mandante / Visitante"*.
- **Rodapé opcional (só se houver dado real):** 1 linha compacta com divisor superior fino para prova social ou impacto curto (nunca inventar contagem de palpites).

### 3.3 Home (`#/`) — Apenas 3 blocos limpos
1. **Card "Seu Time":**
   - Escudo 40 px + Nome + `14º lugar · 42 pts` + chip compacto `Trocar` (abre bottom-sheet em grade de escudos para escolher/trocar o clube em 1 toque).
   - **3 blocos numéricos lado a lado** (com tintura suave funcional): `Título` (`--surface-2`), `G4` (`--libertadores-soft` / `--libertadores`), `Queda` (`--danger-soft` / `--danger`).
   - 1 botão primário cheio (`height: 44px`): `Simular jogos do <Time>`.
   - *(Quando ainda não escolheu time: card compacto de 1 linha "Escolha seu time" com botão que abre o mesmo bottom-sheet).*
2. **Rodada atual / Próximos jogos:**
   - Cabeçalho curto `Rodada N` + link `Ver todos ›` -> `#/jogos`.
   - 3 a 4 Match Cards v2.1 (1 coluna no mobile, grid 2 colunas no desktop).
3. **Disputas rápidas:**
   - Card único com 3 chips no topo (`Título · G4 · Z4`) + link `Tabela ›`.
   - Top 5 clubes da disputa selecionada: escudo 26 px + nome + percentual à direita + barra fina de 6 px na cor funcional.
   - *(O mosaico de bolinhas pode ir para uma sub-aba ou seção recolhível opcional, sem empurrar os jogos e números para baixo da dobra no celular).*

### 3.4 Tabela (`#/classificacao`)
- **Faixa horizontal de chips de visão:** `Geral · Título · Libertadores · Sul-Americana · Z4 · Força · Dificuldade` (sem legenda de 3 linhas abaixo da tabela; explicação de colunas fica num ícone `(i)`).
- **Cenários externos em CHIPS clicáveis (substituem `<select>`):**
  - Card compacto no topo quando relevante: `Vagas extras (G4/G5/G6)` + chips que alternam o campeão em aberto (`Liberta: Em aberto / Palmeiras / Estudiantes` · `Copa BR: Em aberto / Palmeiras / Grêmio`), atualizando a tabela imediatamente.
- **Tabela compacta mobile:** indicador lateral colorido de 3 px (`inset 3px 0 0`) marcando zona de Libertadores e Z4, colunas alinhadas à direita em `tabular-nums`, posição + escudo 22 px + nome curto + Pts + percentuais limpos.

### 3.5 Jogos (`#/jogos` e `#/partidas`)
- **Faixa horizontal rolável de chips de rodada** (`Rodada 35 · Rodada 36 · [Rodada 37] · Rodada 38`), sem parágrafo `.lede` no topo.
- Lista de Match Cards v2.1 (1 coluna no celular, 2 colunas no desktop).

### 3.6 Simulador / Bolão (`#/simular` — Fatia T5)
- Barra de progresso fina no topo (`1 / N`).
- **Card de Placar Exato com stepper vertical `↑ / ↓`** (referência `HM0JDkSWEAMbisU.webp`):
  - Botões `52 × 44 px` em `--surface-2` acima e abaixo de cada número (`40px 900 tnum`), escudo `44 px` ao lado, sigla do clube embaixo.
  - 1 linha discreta com as probabilidades 1X2 do modelo.
  - 2 botões largos embaixo: `Sortear` (secundário) e `Próximo jogo →` / `Salvar palpite` (primário).
- **Card compacto "Probabilidade de tudo junto":** número em destaque `--signal` + frequência (`1 em cada X simulações`), preservando o cálculo real de simulações correlacionadas (achado `@andyweb_3`).

### 3.7 Estados obrigatórios (Loaders, Empty States e Erros)
- **Skeleton loaders** em `--surface-2` no formato dos cards durante carregamento.
- **Empty states** curtos (1 título + 1 frase curta + 1 botão) sem blocos de texto.
- **Erro de rede** com botão primário `Tentar novamente` (refaz `fetch` sem recarregar a página).

---

## 4. Plano de Execução no Claude Sonnet

1. **T1 (`claude/inspiring-lamport-mstzks` — Última Rodada Ao Vivo):** já implementada e testada; mergear primeiro na `main` + rodar migração `0007` no Supabase (prazo 02/12).
2. **T4 v2.1 (refino da branch `feat/redesign-v2` após rebase na `main`):** aplicar esta especificação v2.1 — cortar paredes de texto, cabeçalho 1 andar com sheet de competições, 100% `Inter Tight`, Match Card v2.1 sem botão extra, cenários e rodadas em chips, barra inferior `Início · Tabela · Jogos · Simular · Mais`, e compatibilidade visual nos outros 5 sub-sites e em `#/ao-vivo`.
3. **T5 (Simulador / Bolão):** aplicar stepper vertical `↑ / ↓`, novo fluxo de cartões e estados em `simulator.js` / `simulator.css`, mantendo 100% das regras das migrações `0001`–`0006`.

---

## 5. Critérios de Aceite (Gate Obrigatório)
- **Mobile 375 px:** `scrollWidth <= 375` em todas as rotas da Série A (inclusive `#/ao-vivo`) e nos outros 5 sites.
- **Desktop 1080/1280 px:** navegação em linha no topo, barra inferior oculta, Match Cards em grid de 2 colunas.
- **Gate G4 e acessibilidade:** atribuições intactas no HTML estático, contraste WCAG AA (`>= 4,5:1` texto normal; `>= 3:1` elementos gráficos), área de toque `>= 44 px` nos controles principais, zero erro de JS no console.
- **Testes:** `ruff check`, `ruff format --check`, `mypy` e `pytest -q` 100% verdes.

---

## 6. Adendo v2.2 — Polimento Desktop 1280 px, Simulador e Rodada a rodada (D-052, Kanban #43)

Aprovado pelo dono do produto em 2026-11-26 na combinação **`1C · 2C · 3B · 4A · 5B+Jornada · 6C expandida`**. A Home mobile aprovada na v2.1 (`< 900 px`) permanece intacta.

1. **Desktop `1C` (`>= 900 px`, `app.js` + `styles.css`):**
   - Home com time escolhido: faixa Hero panorâmica (`.team-hero` à esquerda; `.home-next` + CTA `.home-cta` à direita) seguida de 2 colunas equilibradas (`Impacto + Disputas` | `Próximos jogos`).
   - Home sem time escolhido: banner de escolha em largura cheia + 2 colunas (`Próximos jogos` | `Disputas`).
   - Removidas travas antigas de `620/720 px` encostadas à esquerda no PC; Tabela `C2` (`.rg-list`) usa 2 colunas no PC.
2. **Simulador `2C` + Passo 2 em 2 colunas (`simulator.js` + `simulator.css`):**
   - Cabeçalho v2.1 com `Simulador`, botão `(i)` (regras/privacidade em sheet) e pílula compacta de conta (`@apelido` / `Entrar no ranking`) abrindo o sheet de conta (`openSheet`, mantendo Turnstile, apelido, avisos e exclusão).
   - Abas `Início · Ranking · Agregado` em `.chip-row`.
   - Início em 2 colunas no PC (`1.3fr | 1fr`, empilhado no celular): esquerda com preview interativo do próximo jogo aberto (`Placar exato`, `Vencedor` 1X2 ou resumo de `Classificação`) levando o 1º palpite direto ao Passo 2; direita com lista compacta `Minhas simulações`.
   - Passo 2 (`renderDeck`) em 2 colunas no PC (`.sim-deck-grid`: card fixo à esquerda, lista de jogos agrupada por dia à direita).
3. **Ranking e Agregado `3B` (`simulator.js` + `simulator.css`):**
   - Destaques em 3 cards no topo (`Pódio` no Ranking; `"Onde a torcida mais discorda do modelo"` no Agregado quando o consenso está publicado) — 3 colunas no PC, faixa horizontal com `scroll-snap` no celular.
   - Tabela em `.table-card` com pílula `vs. Modelo` (`+N`, `−N`, `=`) e estados vazios no padrão `.state`.
4. **Rodada a rodada · Visão geral `4A` (`rounds.js` + `rounds.css`):**
   - Abas `Visão geral · Por time · Comparar` em `.chip-row` no cabeçalho.
   - Gráfico padrão **"Corrida rodada a rodada"** (4 clubes de maior pico na disputa escolhida `Título · G4 · Z4`, rótulos coloridos diretos no fim da linha com valor atual e barra de leitura viva ao passar o mouse/dedo).
   - Alternância `Corrida | Agito`: `Agito` usa barras de 1 cor (`--libertadores`) destacando apenas a rodada de pico em `--signal` com anotação direta.
   - Rodadas decisivas em grade de 2 colunas no PC, com expansão recolhível de todas as rodadas.
5. **Rodada a rodada · Por time `5B + Jornada` (`rounds.js` + `rounds.css`):**
   - Substitui a grade de 20 links por seletor `[escudo] Nome ▾` em sheet + atalho `Comparar ›` e 4 cards de resumo.
   - Grid 2 colunas no PC (`1.3fr | 1fr`): esquerda com gráfico único alternando `Probabilidades | Posição` + tabela completa recolhível; direita com **Momentos decisivos** (2 extremos) e **Jornada na temporada** (linha do tempo cronológica clicável que foca a rodada no gráfico).
6. **Rodada a rodada · Comparar `6C expandida` (`rounds.js` + `rounds.css`):**
   - Até 4 clubes em chips com aro colorido da série (`×` e `+ time` em sheet).
   - Grid 2 colunas no PC (`1.15fr | 0.85fr`): gráfico + barra `▶ Evoluir` e slider de rodada sincronizados ao vivo com a **Foto da Rodada** ao lado (`Comparados (N) | Tabela`), incluindo setas `▲/▼` de variação de posição frente à rodada anterior.

