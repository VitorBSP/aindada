# Guia de identidade

**Status: em construção.** Aprovados: nome (D-004, D-020), paleta principal (D-005), símbolo (D-017,
D-018), assinatura e tipografia da assinatura (D-019, D-021), ícone de app (D-023) e aplicação na
interface (D-024).
O restante segue pendente.
Este guia só recebe conteúdo depois de registrado em `BRAND_DECISIONS.md`. Seções marcadas como
"pendente" serão preenchidas nas Etapas 3 (Desenvolvimento) e 4 (Identidade final).

## Princípios já vigentes

Estes princípios já constam dos contratos dos Agentes 05 e 08 e valem para qualquer direção futura.

1. **Credibilidade sem frieza**: rigor nos números, voz de futebol nas palavras.
2. **Incerteza à vista**: probabilidade nunca é apresentada como certeza. "Garantido",
   "rebaixado" e "campeão" só com certeza matemática.
3. **Data de referência sempre visível** em qualquer peça com números.
4. **Neutralidade clubística**: nenhum clube é privilegiado na identidade. Cores e escudos dos
   clubes só aparecem como dado, nunca como elemento da marca.
5. **Acessibilidade**: texto com contraste mínimo WCAG AA (4,5:1; 3:1 para texto grande e
   gráficos); informação nunca depende só de cor; legível a partir de 360 px.
6. **Cores funcionais separadas da marca**: Libertadores, Sul-Americana, rebaixamento e afins têm
   tokens próprios, estáveis e independentes da paleta de marca.

## Nome — aprovado (D-004)

- Grafia: **AInda dá?**, com **A e I maiúsculos** (formando "AI", de inteligência artificial),
  "nda" minúsculo, acento e ponto de interrogação (D-020). Nunca "Ainda dá?" nem "AINDA DÁ?".
- Pronúncia: "ainda dá", como a palavra comum. O "AI" é efeito visual, não se soletra.
- Leitores de tela: quando o nome aparecer como imagem, usar `aria-label="AInda dá?"`.
- Em texto corrido, o "?" faz parte do nome: "o AInda dá? mostra…". Se a frase terminar no nome,
  não se acrescenta outro ponto.
- Onde não há acento nem "?" (domínio, @, nomes de arquivo): `aindada`.

## Símbolo — aprovado (D-017)

Interrogação com uma barra de chance em pílula no lugar do ponto. O preenchimento vermelho leva um
pequeno **%** claro, que mostra que a resposta é uma probabilidade.

Arquivos editáveis em `docs/brand/assets/simbolo/` (prévia: `index.html` e `previa.png`):

| Arquivo | Uso |
|---|---|
| `ainda-da-simbolo.svg` | principal, sobre papel `#F7F5EF` ou branco |
| `ainda-da-simbolo-reverso.svg` | sobre tinta `#17191C` ou fundos escuros |
| `ainda-da-simbolo-mono.svg` | uma cor (tinta); o % é vazado e mostra o fundo |
| `ainda-da-simbolo-mono-reverso.svg` | uma cor (branco) sobre fundo escuro; % vazado |
| `ainda-da-simbolo-compacto.svg` e `-compacto-reverso.svg` | de 30 a 63 px: mantém o %, com pílula e % maiores (ajuste óptico, D-027) |
| `ainda-da-simbolo-reduzido.svg` | abaixo de 30 px (favicon, ícones minúsculos): sem o %, traços mais grossos |
| `favicon.svg` | aba do navegador; troca a tinta por papel quando o navegador está em tema escuro |

**Tamanhos.** Completa a partir de 64 px; compacta (com %) de 30 a 63 px; reduzida (sem %) abaixo
de 30 px. O % da completa vira um ponto em 48 px (D-018); a compacta mantém o % legível em 40 px
numa tela comum e em 30 px numa tela de alta densidade (verificado, D-027).

**Área de proteção.** Espaço livre em volta igual à altura da pílula (15/64 da altura do símbolo).

**Cores e contraste** (WCAG, calculado):
- % `#F7F5EF` sobre o preenchimento `#D9381E`: 4,25:1.
- Preenchimento `#D9381E` sobre papel: 4,25:1; sobre tinta: 3,8:1 (≥ 3:1 para elementos gráficos).

**Não fazer:**
- Usar o símbolo sobre fundo vermelho-sinal: o preenchimento desaparece. Em peças vermelhas, use a
  versão mono reversa.
- Trocar as cores, girar, distorcer, contornar ou aplicar sombra.
- Mudar o tamanho do preenchimento para representar um dado real no logotipo. Uma versão animada ou
  com valor real para peças sociais é ideia futura e precisa de aprovação própria.
- Usar a versão completa abaixo de 64 px ou a reduzida (sem %) acima de 30 px.

## Assinatura (símbolo + nome) — aprovada (D-019, D-021)

"AInda dá" em Inter Tight 800 convertida em contorno, com o símbolo no lugar do "?". Arquivos em
`docs/brand/assets/assinatura/` (prévia: `index.html` e `previa.png`):

| Arquivo | Uso |
|---|---|
| `ainda-da-assinatura.svg` | principal, sobre papel ou branco |
| `ainda-da-assinatura-reversa.svg` | sobre tinta ou fundos escuros |
| `ainda-da-assinatura-mono.svg` | uma cor (tinta); % vazado |
| `ainda-da-assinatura-mono-reversa.svg` | uma cor (branco) sobre escuro; % vazado |
| `ainda-da-assinatura-compacta.svg` | de 30 a 63 px de altura, com o % (cabeçalho do site: 36 px; 32 px no celular), sobre papel |
| `ainda-da-assinatura-compacta-reversa.svg` | idem, sobre tinta |
| `ainda-da-assinatura-reduzida.svg` | abaixo de 30 px de altura, sem o %, sobre papel |
| `ainda-da-assinatura-reduzida-reversa.svg` | abaixo de 30 px de altura, sobre tinta |

- **Altura:** a assinatura tem a altura do símbolo. Completa com 64 px ou mais; compacta de 30 a
  63 px; reduzida abaixo de 30 px (mínimo recomendado: 20 px).
- **Área de proteção:** espaço livre em volta igual à metade da altura da assinatura.
- **Não fazer:** reescrever o nome com outra fonte ou com o "?" do teclado; separar o símbolo do
  texto mudando o espaço; aplicar cor no "AI" (D-021); usar sobre fundo vermelho-sinal.
- **Texto alternativo:** `AInda dá?`.

## Ícone de aplicativo — aprovado (D-023)

Símbolo reverso sobre fundo tinta `#17191C`, com 60% da altura do ícone, dentro da zona segura de
80% dos ícones adaptáveis do Android. O formato (cantos ou círculo) é aplicado pelo sistema; o
arquivo é quadrado e sem cantos.

| Arquivo | Uso |
|---|---|
| `docs/brand/assets/icone/ainda-da-icone.svg` | matriz editável |
| `ainda-da-icone-512.png` | PWA e ícone adaptável (maskable) |
| `ainda-da-icone-192.png` | PWA (Android) |
| `ainda-da-icone-180.png` | `apple-touch-icon` (iOS) |

Na aba do navegador, use `docs/brand/assets/simbolo/favicon.svg`.

## Paleta — principal aprovada (D-005)

| Nome | Hex | Uso |
|---|---|---|
| Papel | `#F7F5EF` | fundo |
| Tinta | `#17191C` | texto e símbolo |
| Vermelho-sinal | `#D9381E` | cor da marca; texto só em tamanho grande (4,25:1 sobre papel) |
| Sinal no escuro | `#FF6A4D` | texto em vermelho sobre tinta (6,2:1) |

Tokens de interface (dados, estados, tema escuro): ver "Aplicações em interface" e `apps/web/assets/styles.css`.

## Tipografia — assinatura aprovada (D-021)

| Uso | Fonte | Peso | Espaçamento |
|---|---|---|---|
| Assinatura "AInda dá?" | Inter Tight | ExtraBold (800) | -0,04 em |

- Licença: SIL Open Font License 1.1, confirmada no arquivo. Fonte e licença em
  `docs/brand/assets/fontes/` (procedência em `PROVENIENCIA.md`).
- O "?" da assinatura é sempre o símbolo, nunca o caractere da fonte (D-019): altura de 0,86 em,
  base 0,03 em abaixo da linha de base, 0,11 em de espaço depois do "á". Símbolo completo quando
  ele tiver 64 px ou mais; reduzido abaixo disso.
- Sem destaque de cor no "AI" (D-021). Risco conhecido: o "I" maiúsculo da Inter Tight é uma haste
  igual ao "l"; a leitura "Alnda" é possível. Monitorar em testes com usuários.
- Interface (D-024): Inter Tight 400 a 800, numerais tabulares (`tnum`) ligados em todo o site.
  Arquivo reduzido a latim em `apps/web/assets/fonts/inter-tight-latin.woff` (38 KB), com `OFL.txt`.
## Elementos gráficos — pendente
## Tom de voz e estilo editorial — ver `docs/storytelling/CONTENT_GUIDELINES.md` (D-026)
## Comunicação de probabilidades e mudanças — ver `docs/storytelling/CONTENT_GUIDELINES.md`
## Redes sociais — pendente
## Aplicações em interface — aprovada (D-024)

Implementada em `apps/web/` (tokens no topo de `assets/styles.css`). Princípios:
- **Caderno de dados, não painel:** seções separadas por fio de 3 px em tinta; sem cartões em
  caixa, sombras, degradês nem cantos arredondados.
- **Tipografia calma (D-025):** texto corrido e linha fina em serifa (Georgia e equivalentes do
  sistema); interface, títulos, tabelas e números em Inter Tight; rótulos em letra normal, sem
  maiúsculas espaçadas; manchete 700, seção 650.
- **Vermelho-sinal só como marca e indicação:** item ativo do menu e sublinhado ao passar o mouse.
  Nunca para dado. Sobretítulos são texto discreto em cinza (D-025).
- **Cores de dado (funcionais):** título em tinta; G4/Libertadores em azul `#1F4F99`; Sul-Americana
  em âmbar `#8A5300`; queda em vermelho `#B3261E`; empate em cinza `#6B6F76`. Todas com 4,5:1 ou mais
  sobre o papel; no tema escuro, versões claras com 5,5:1 ou mais sobre tinta.
- **Tema escuro:** fundo tinta `#17191C`, texto papel; assinatura reversa no cabeçalho.
- **Voz:** sobretítulo + manchete curta ("Flamengo na frente. Palmeiras: ainda dá."); números em
  negrito no texto; "não dá mais" só com certeza matemática.
## Usos incorretos — ver o símbolo; demais elementos pendentes

## Entrega ao frontend (Etapa 4)

Formato previsto, a combinar com o Agente 05:
- `docs/brand/assets/tokens.json` e `tokens.css` (cores, tipografia, espaçamento, raios).
- `docs/brand/assets/logo/*.svg` (todas as versões, com `viewBox` e sem texto convertido em imagem).
- `favicon.svg`, ícones de app em PNG gerados a partir do SVG.
- Checklist de verificação para o Agente 06 (contraste, tamanhos mínimos, uso correto).
