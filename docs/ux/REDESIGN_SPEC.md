# REDESIGN_SPEC — AInda dá? v2 (Mobile-First, Dark Default)

> **Status:** Especificação aprovada pelo dono do produto em 2026-11-23.
> **Objetivo:** Elevar o acabamento visual e a ergonomia no celular (375 px primeiro, desktop 1280 px fluido) mantendo a identidade **AInda dá?**, zero build step (HTML/CSS/JS puros em `apps/web/`) e 100% de compatibilidade com os JSONs e rotas atuais.
> **Como executar:** Dividir a implementação no executor (Claude Sonnet) em duas fatias sequenciais (**T4: Base visual + Home/Jogos/Navegação** e **T5: Simulador/Bolão com stepper vertical**), somente após o merge da **T1 (Última Rodada Ao Vivo)** para evitar conflito em `index.html`, `app.js` e `styles.css`.

---

## 1. Direção Visual e Travas Anti-"Cara de IA"

### 1.1 Tema padrão: Escuro com a paleta oficial do AInda dá?
O site passa a abrir em **tema escuro por padrão** (`:root` usa os tokens escuros; toggle opcional salva `data-theme="light"` em `localStorage`).

| Token | Dark (Padrão) | Light (Opcional) | Papel |
|---|---|---|---|
| `--paper` | `#17191C` | `#FAFAF7` | Fundo principal da página |
| `--surface` | `#1D2024` | `#FFFFFF` | Cartões (Match Card, Seu Time, Simulador) |
| `--surface-2` | `#24282E` | `#F2F1EC` | Pílulas, steppers, seletores inativos, skeleton |
| `--ink` | `#F7F5EF` | `#17191C` | Texto principal e números em destaque |
| `--ink-soft` | `#B9BBBF` | `#4A4E55` | Subtítulos, metadados de jogo |
| `--ink-faint` | `#8D9198` | `#6B6F76` | Rodapé, rótulos secundários |
| `--rule` | `#30343A` | `#E2E1DB` | Bordas finas de 1 px (cartões, divisores) |
| `--signal` | `#FF6A4D` | `#D9381E` | Marca, item ativo, foco, CTA principal (contraste 6,2:1 no dark) |
| `--signal-fill` | `#D9381E` | `#D9381E` | Preenchimento sólido com texto `#F7F5EF` (botão primário, badge ao vivo) |
| `--libertadores` | `#8FB2EE` | `#1F4F99` | Dado funcional: G4 / Libertadores (soft: `#1B2840` / `#E3EBF7`) |
| `--sudamericana` | `#E6AC58` | `#8A5300` | Dado funcional: Sul-Americana (soft: `#3A2B14` / `#F6EAD6`) |
| `--danger` | `#F08A82` | `#B3261E` | Dado funcional: Rebaixamento (soft: `#3D1C1A` / `#F8E1DF`) |
| `--draw` | `#8D9198` | `#6B6F76` | Dado funcional: Empate |

### 1.2 Tipografia e assinatura
- **Fonte única de interface e números:** `"Inter Tight"` (local em `apps/web/assets/fonts/inter-tight-latin.woff`), com `font-variant-numeric: tabular-nums` obrigatório em todo placar, tabela e percentual.
- **Cabeçalho:** usar `ainda-da-assinatura-compacta-reversa.svg` no tema escuro (altura 32 px no celular, 36 px no desktop) e `ainda-da-assinatura-compacta.svg` no tema claro. Nunca recriar o nome em texto puro com "?" do teclado.
- **Data de referência** sempre visível de forma discreta no topo da tela (princípio 3 do `BRAND_GUIDELINES.md`).

### 1.3 Travas obrigatórias (o que NÃO fazer)
- **Zero fotos de jogadores/estádio e zero campo 3D** (sem licença de imagem e peso desnecessário no 4G).
- **Zero verde-neon de casa de aposta, zero gradiente roxo/cyan e zero sombras pesadas (`box-shadow` difuso).** Profundidade vem apenas da escada de superfícies (`--paper` -> `--surface` -> `--surface-2`) + borda `1px solid var(--rule)`.
- **Zero texto em caixa alta com `letter-spacing` largo** (manter rótulos naturais, D-025).
- **Raio de borda consistente:** `14px` para cards principais, `10px` para botões/inputs/pílulas de probabilidade, `999px` apenas para chips de filtro e badges de status.

---

## 2. Arquitetura de Layout (Mobile 375 px -> Desktop 1280 px)

### 2.1 Navegação mobile (375 px)
- **Cabeçalho enxuto (56 px de altura):** Assinatura `AInda dá?` à esquerda + botão discreto de tema (Sol/Lua) e data/status à direita.
- **Faixa horizontal rolável de competições (pills):** logo abaixo do cabeçalho (`Série A · Série B · Premier · LaLiga · Champions · LoL`), com `overflow-x: auto; scrollbar-width: none` e scroll automático para manter a competição ativa visível.
- **Barra inferior fixa (`mobile-nav.js`):** 4 destinos principais + `Mais` (altura `60px + env(safe-area-inset-bottom)`, fundo `rgba(23, 25, 28, 0.92)` com `backdrop-filter: blur(10px)` e borda superior `1px solid var(--rule)`):
  1. `Início` (`#/`)
  2. `Tabela` (`#/classificacao`)
  3. `Jogos` (`#/jogos`)
  4. `Simular` (`#/simular`)
  5. `Mais` (sheet inferior com Rodada a rodada, Ao vivo, Clubes, Como calculamos, outras ligas).
- **Área de toque mínima:** `44 × 44 px` em todo botão, chip, seta de placar e item de barra inferior.

### 2.2 Desktop (>= 960 px)
- Container centralizado `max-width: 1080px`, mantendo o mesmo sistema de cards em grid de 2 colunas para listas de jogos e 12 colunas para Home/Tabela.
- Barra inferior oculta no desktop; navegação principal no cabeçalho em linha única.

---

## 3. Componentes-Chave (Especificação para o Executor)

### 3.1 Match Card v2 (Home, Jogos, Rodada a rodada, Ao Vivo)
Inspirado na hierarquia limpa das referências mobile esportivas, adaptado aos dados reais do AInda dá?:

```text
+----------------------------------------------------+
| Rodada 37 · Dom 29/11 16:00          [Agendado]    |  <- 12px --ink-soft + badge
|                                                    |
|  [Escudo 36px]        1 × 0        [Escudo 36px]   |  <- placar 26px 800 tnum (ou "vs")
|    Palmeiras                         Flamengo      |  <- nome curto 14px 600
|                                                    |
|  [ 48% Mandante ] [ 27% Empate ] [ 25% Visitante ] |  <- 3 pílulas 1X2 (proporção ou destaque no favorito)
|                                                    |
|  342 palpites no simulador · Ver impacto ->        |  <- opcional (só quando há dado real)
+----------------------------------------------------+
```

- **Regras do Match Card:**
  - Card inteiro (ou ação "Ver impacto") abre o `<dialog>` de detalhes (`match-popup.js`).
  - As 3 pílulas de probabilidade (`p_home`, `p_draw`, `p_away`) usam fundo `--surface-2`; a maior probabilidade recebe borda `1px solid var(--signal)` ou fundo suavemente destacado sem quebrar contraste WCAG AA.
  - Em jogo **ao vivo** (T1): badge vermelho sólido `--signal-fill` com texto `AO VIVO · 34'`.
  - **Prova social:** só exibir contagem de palpites quando o dado real existir no consenso do Supabase (nunca inventar número).

### 3.2 Card "Seu Time" (Topo da Home)
- Primeiro bloco da Home quando o visitante já segue um clube (e seletor rápido de 1 toque quando ainda não escolheu).
- Mostra escudo (40 px), posição atual + pontos, e **3 mini-blocos em linha** com as disputas relevantes (ex.: `Título 12%`, `G4 68%`, `Queda 2%`) com barra fina de progresso na cor funcional correspondente (`--title`, `--libertadores`, `--danger`).
- CTA direto: `Simular jogos do <Time>` -> abre `#/simular`.

### 3.3 Seletor Horizontal de Rodadas / Disputas
- Substituir `<select>` nativo nas telas principais por faixa horizontal de chips (`Rod 34 · Rod 35 · Rod 36 · [Rod 37] · Rod 38`), com chip ativo em `--ink` (fundo `#F7F5EF`, texto `#17191C` no dark) ou borda `--signal`.

### 3.4 Card de Palpite com Stepper Vertical (T5 — Simulador / Bolão)
Inspirado na referência `HM0JDkSWEAMbisU.webp`, otimizado para uso rápido com uma mão no celular:

```text
+----------------------------------------------------+
| PALPITE O PLACAR                     Rodada 37     |
| Dom 29/11 · 16:00 · Trava às 15:30                 |
|                                                    |
|        [ ↑ ]                [ ↑ ]                  |  <- botões 48x40px em --surface-2
|  [Escudo]  2        ×        1  [Escudo]           |  <- número 40px 800 tnum
|    INT  [ ↓ ]              [ ↓ ]  GRE              |
|                                                    |
|  Modelo: 46% · 28% · 26%   |   [ Sortear ] [ Pular]|
+----------------------------------------------------+
```

- **Modo Vencedor:** 3 botões largos empilhados ou lado a lado (`Mandante` / `Empate` / `Visitante`) com avanço automático suave ao tocar.
- **Card de Cenário Combinado ("Chance de tudo junto"):** exibir a probabilidade conjunta real das simulações em destaque (`1 em cada X simulações · Y%`) com aviso curto quando eventos são correlacionados (nunca multiplicar probabilidades independentes na mão).

### 3.5 Estados Obrigatórios (Loaders, Empty States e Erros)
Inspirado no achado de UX mobile (`@luiz_7727`), **toda tela** deve implementar os 3 estados com o mesmo cuidado do estado populado:
1. **Loading (`skeleton`):** blocos pulsantes discretos em `--surface-2` com a mesma altura aproximada dos cards (evita layout shift no celular).
2. **Empty state:** ícone geométrico simples em SVG (traço fino, sem ilustração pesada), título de 1 linha explicando o motivo real (ex.: *"Sem jogos ao vivo agora"*, *"Você ainda não salvou simulações"*) e 1 botão de ação útil.
3. **Erro de rede/API:** mensagem clara em português simples + botão `Tentar novamente` que refaz o `fetch` sem recarregar a página inteira.

---

## 4. Plano de Execução Fatiado (Para o Claude Sonnet)

### Fatia T4 — Base Visual Dark-First + Home, Jogos e Navegação
- **Arquivos-alvo:** `apps/web/assets/styles.css`, `apps/web/index.html`, `apps/web/assets/app.js`, `apps/web/assets/mobile-nav.js`, `apps/web/assets/current-round.js`, `apps/web/assets/match-popup.js`.
- **Entregáveis:**
  1. Tema escuro padrão com toggle claro/escuro persistido e troca automática da assinatura SVG no cabeçalho.
  2. Faixa horizontal de competições + barra inferior refinada.
  3. Match Card v2 com pílulas 1X2 e novo card "Seu Time".
  4. Skeleton loaders, empty states e estados de erro na Home, Tabela e Jogos.
  5. Garantir que os outros 5 sub-sites (`web-serie-b`, `web-ligas`, `web-champions`, `web-lol`) herdem os tokens sem quebrar.

### Fatia T5 — Refactor do Simulador (Stepper Vertical + Prova Social)
- **Arquivos-alvo:** `apps/web/assets/simulator.js`, `apps/web/assets/simulator.css`, `apps/web/assets/simulator-cloud.js`.
- **Entregáveis:**
  1. Novo card de Placar Exato com stepper vertical `↑ / ↓` (mínimo `44×44 px` por botão).
  2. Novo card de Vencedor com pílulas grandes e feedback imediato.
  3. Card destacado de "Chance de tudo junto" (probabilidade conjunta real) e contador de prova social quando o consenso do Supabase atingir o mínimo configurado.
  4. Estados de loading, vazio e erro no carregamento/salvamento do Supabase.
  5. Zero regressão nas regras de trava (30 min), pontuação e ranking (migração `0006`).

---

## 5. Critérios de Aceite (Gate Obrigatório)
- **Mobile 375 px:** `document.documentElement.scrollWidth <= 375` em todas as rotas (`#/`, `#/classificacao`, `#/jogos`, `#/rodadas`, `#/simular`, `#/ao-vivo`, `#/metodologia`).
- **Desktop 1280 px:** layout equilibrado sem cards esticados em linha inteira desnecessariamente.
- **Contraste WCAG AA:** mínimo `4,5:1` para texto normal e `3:1` para números grandes/elementos gráficos no tema escuro e no claro.
- **Console limpo:** zero erros de JS no console.
- **Suite de qualidade:** `ruff check`, `mypy` e `pytest -q` 100% verdes.
