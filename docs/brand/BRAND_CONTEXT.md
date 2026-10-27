# Contexto de marca — memória evolutiva do Agente 08

Documento vivo. Atualizado sempre que o produto, o público ou o posicionamento mudarem.
Cada atualização entra no registro de alterações no fim do arquivo.

**Estado atual:** Etapa 3 (Desenvolvimento) iniciada. Nome **"AInda dá?"** (D-004, grafia D-020) e paleta
principal "Papel e tinta" com vermelho-sinal (D-005) decididos pelo dono do produto. Símbolo
aprovado (D-017). Tipografia, tom de voz final e guia ainda não aprovados.

## 0. Onde está cada coisa (desde D-026)

Marca: `docs/brand/`. Estratégia editorial, catálogo e validação de insights, guia de conteúdo:
`docs/storytelling/`. Princípios, jornadas e engajamento: `docs/ux/`. Contratos:
`agents/08-brand-storytelling-ux.md` e `agents/08A-insights-intelligence.md`.

## 1. Briefing inicial (2026-10-26)

### O produto hoje
Plataforma que estima, rodada a rodada, as chances de cada clube da Série A em título, G4,
Libertadores (grupos e preliminar), Sul-Americana, rebaixamento e cada posição final.
Funciona com dados de 2003 a 2026 (9.545 jogos), ratings Elo e de ataque/defesa, modelo de gols
Dixon-Coles e 10 mil simulações Monte Carlo da temporada com o regulamento oficial, incluindo os
critérios de desempate.

Estágio: MVP local e experimental. A publicação está bloqueada até resolver a licença dos dados
de 2024+ (ADR-0002). A marca, portanto, pode ser construída sem pressa de lançamento.

Nome de trabalho atual no MVP: **"Brasileirão em Probabilidades"** (`apps/web/index.html`). É um
rótulo descritivo provisório, **não uma marca aprovada**.

### O que a interface já oferece (Agente 05)
- Início: chance de título, risco de rebaixamento, disputa pela Libertadores em faixas,
  mudanças desde o snapshot anterior.
- Classificação: tabela real e projetada, com intervalo de 90% de pontos e seletor de cenário externo.
- Clubes: distribuição de posição, evolução temporal, força estimada, próximos jogos, cenários.
- Partidas: 1X2, gols esperados e placar mais provável.
- Metodologia: modelo, regras, validação, fontes, licença e limitações.
- Estilo atual: editorial, papel claro, serifa nos títulos, tema escuro automático, legível em 360 px.

### Objetivo da marca
Transformar um motor estatístico rigoroso numa experiência esportiva que o torcedor queira abrir
toda rodada: interessante, útil e envolvente. A sofisticação técnica fica nos bastidores e
aparece como credibilidade, não como jargão.

## 2. Público-alvo

Decidido em 2026-10-26 (D-007): o público prioritário é o **torcedor engajado**. A tabela abaixo
era a hipótese inicial e fica como referência dos segmentos secundários.

| Segmento | O que procura | Implicação para a marca |
|---|---|---|
| Torcedor engajado (principal, hipótese) | "Ainda dá?", "Meu time cai?", secar o rival | linguagem de arquibancada, emoção, compartilhável |
| Jornalistas e criadores de conteúdo | números confiáveis e citáveis, gráficos prontos | credibilidade, fonte clara, peças exportáveis |
| Curiosos de dados e estatística | método transparente, validação | metodologia acessível, sem esconder incerteza |
| Apostadores | probabilidades para comparar com odds | **risco de posicionamento**; ver questão aberta Q3 |

Comportamentos esperados: picos de acesso perto e depois das rodadas (quarta/quinta e
fim de semana), consumo majoritário no celular, compartilhamento em WhatsApp, X, Instagram e
TikTok, discussão clubística e rivalidade.

### Implicações das respostas de 2026-10-26 (D-007 a D-014)

- **Torcedor + Instagram, X e WhatsApp:** o símbolo precisa funcionar recortado em círculo (foto de
  perfil) e as peças em 1:1, 4:5 (Instagram) e 16:9 (X); cartões leves para encaminhar no WhatsApp.
- **Expansão além da Série A:** nenhum elemento fixo de marca usa "Brasileirão", "Série A" ou
  "38 rodadas"; a competição aparece como dado, ao lado da marca.
- **Comparação com o mercado:** odds aparecem só como referência de calibração. Proibido: chamada
  para apostar, link de casa de aposta, "palpite", "cravar", "aposta certa".
- **Provocação leve:** permitida brincadeira com a situação e com rivalidades ("Modo secador"),
  nunca ofensa a clube, torcida, jogador ou cidade, nem piada com violência, tragédia ou
  discriminação. Limites detalhados entram no guia.
- **Gratuito e sem orçamento:** nada de compra por enquanto. O domínio preferido
  (`aindada.app.br`) e a marca no INPI **não estão protegidos**.

## 3. Diferenciais conhecidos

1. **Regulamento oficial aplicado**: desempate do Art. 15 e vagas do Art. 6º–8º, incluindo vagas
   herdadas da Copa do Brasil e das copas continentais.
2. **Honestidade com a incerteza**: faixas quando a vaga depende de torneios externos não
   resolvidos; "0%" explicado como "não ocorreu nas simulações".
3. **Validação publicada**: backtesting temporal sem vazamento, com log loss, Brier e RPS
   comparados à taxa-base e ao Elo puro.
4. **Proveniência**: fonte, licença e data de referência sempre visíveis.
5. **Histórico rodada a rodada**: evolução das chances de cada clube ao longo da temporada.
6. **Memória longa**: 24 temporadas de pontos corridos (2003–2026) como base.
7. **Reprodutibilidade**: semente e versões registradas em cada snapshot.

Ainda não são diferenciais (planejados): modelo de empates, comparação com odds, Next.js, deploy.

## 4. Restrições e cuidados identificados

- **Neutralidade clubística**: a marca não pode parecer de um clube. Combinações fortes como
  vermelho+preto, verde+branco, preto+branco e tricolores específicos precisam ser evitadas como
  cor principal ou usadas com cuidado. O verde também remete à seleção e à CBF.
- **"Brasileirão"** é nome associado à competição organizada pela CBF e pode ter proteção de marca
  (não verificado). Usá-lo no nome traz risco jurídico e limita a expansão para outros campeonatos.
- **Apostas**: a regulamentação de apostas de quota fixa no Brasil e a imagem pública do setor
  tornam sensível qualquer associação. Palavras como "palpite", "cravar" e "odd" exigem cuidado.
- **Acessibilidade**: o produto já assume contraste, navegação por teclado e informação que não
  depende só de cor. A marca precisa respeitar isso.
- **Licença de dados pendente**: nenhuma peça pública antes da liberação de deploy (00 + 06).

## 5. Decisões do produto que afetam a marca

| Data | Decisão | Fonte | Efeito na marca |
|---|---|---|---|
| 2026-10-26 | Frontend estático editorial (ADR-0005), migração futura para Next.js | ADR-0005 | tokens devem funcionar em CSS puro e depois em TS |
| 2026-10-26 | Vagas dependentes de torneios externos mostradas como cenários/faixas | ADR-0003 | linguagem visual precisa representar faixas, não só pontos |
| 2026-10-26 | Publicação bloqueada até resolver licença 2024+ | ADR-0002 | sem lançamento público; marca pode amadurecer |

## 6. Ideias registradas para avaliar

- Peça social por rodada: "quem subiu, quem caiu" nas chances (setas e variação em p.p.).
- "Linha de corte" como elemento gráfico recorrente (G4, Libertadores, Z4).
- Cartão compartilhável por clube com a distribuição de posições.
- Comparar "o que a tabela diz" × "o que as simulações dizem".
- "Modo secador": de quem o seu clube precisa que perca (recurso; depende da Q9 e de dado do Agente 02).
- Regra de voz: "não dá mais" e "já deu" só com certeza matemática.

## Registro de alterações

| Data | Alteração | Autor |
|---|---|---|
| 2026-10-26 | Criação: briefing inicial, público, diferenciais, restrições | Agente 08 |
| 2026-10-26 | Dono do produto seleciona A e B para aprofundamento (D-003); verificação preliminar de domínios; esboços SVG em `exploration/` | Agente 08 |
| 2026-10-26 | Nome "Ainda dá?" e paleta principal decididos (D-004, D-005); 8 estilos de símbolo em exploração (D-006) | Agente 08 |
| 2026-10-26 | Questões Q1–Q12 respondidas (D-007 a D-014); implicações registradas | Agente 08 |
| 2026-10-26 | Rodada 2 de símbolos (D-015): fusões %+?, balão, barra e opções usuais; teste de avatar redondo | Agente 08 |
| 2026-10-26 | Rodada 3 (D-016): variações de R5, R4 e R8 com %?; proposta de papéis por símbolo | Agente 08 |
| 2026-10-26 | Símbolo aprovado (D-017): R5 com %; arquivos em `assets/simbolo/` e seção no guia | Agente 08 |
| 2026-10-26 | % reduzido (D-018); símbolo no lugar do "?" da assinatura (D-019); estudo com 4 fontes | Agente 08 |
| 2026-10-26 | Grafia corrigida para "AInda dá?" (D-020): A e I maiúsculos formam "AI". Registros anteriores com "Ainda dá?" são histórico | Agente 08 |
| 2026-10-26 | Assinatura em Inter Tight 800, sem destaque no "AI" (D-021); risco "Alnda" aceito | Agente 08 |
| 2026-10-26 | Assinatura em contorno entregue (6 SVGs); fonte Inter Tight e licença OFL incluídas no repositório | Agente 08 |
| 2026-10-26 | Seletor de cenários corrigido e interface mais calma (D-025). Agente 08 vira Marca, Storytelling, UX e Engajamento; subagente 08A criado (D-026). Documentos em `docs/storytelling/` e `docs/ux/` | Agente 08 |
