# Princípios de UX — AInda dá?

Responsável: Agente 08 (D-022, D-026). Versão 1 — 2026-10-26.

## 1. Produto esportivo editorial, não painel
A tela conta uma história com hierarquia clara: manchete, contexto, dado. Evitamos grades de
cartões com métricas soltas, excesso de gráficos, widgets disputando atenção e animações gratuitas.

## 2. Uma pergunta por tela
Cada página responde uma pergunta principal ("Meu time ainda dá?", "O que mudou na rodada?",
"Qual jogo importa?"). O resto é aprofundamento, abaixo ou a um clique.

## 3. Número com contexto
Nenhuma porcentagem aparece sozinha: sempre com o que ela significa, a comparação (antes, rival,
média) e a data de referência.

## 4. Incerteza visível, sem drama
Faixas quando o resultado depende de outros torneios; intervalos quando ajudam; "não aconteceu nas
simulações" em vez de 0% seco. Sem linguagem de certeza.

## 5. O clube no centro
O torcedor pode escolher um clube para acompanhar e encontrá-lo em destaque na home, na rodada e
nos jogos. Escudo e nome são dados, nunca decoração da marca.

## 6. Explorar é opcional, encontrar é fácil
Tabela completa, cenários e rodada a rodada existem para quem quer ir fundo, mas a home já
responde o essencial em 30 segundos de leitura.

## 7. Calma visual (menos "cara de IA")
- Texto corrido em serifa (Georgia), interface e números em Inter Tight.
- Rótulos em letra normal; nada de rótulos em maiúsculas espaçadas espalhados pela tela.
- Fios separando seções; sem caixas com sombra, degradês, brilhos, ícones de robô ou chatbot.
- Vermelho-sinal só para marca e estado ativo; cores de dado são funcionais e poucas.
- Pesos tipográficos contidos: manchete 700, títulos de seção 650.

## 8. Acessível por padrão
Contraste AA, navegação por teclado com foco preservado ao redesenhar (ex.: seletor de cenários),
textos alternativos, informação nunca só por cor, legível em 360 px, tema escuro.

## 9. Rápido e honesto
Sem carregamento artificial, sem pop-up, sem pedido de cadastro para ver números. Desempenho:
primeira tela útil com uma fonte (38 KB) e um JSON de dados.

## 10. Medir antes de mudar
Mudanças de navegação ou hierarquia entram com hipótese registrada em `ENGAGEMENT_STRATEGY.md` e
são revistas com dados de uso quando houver medição (sem rastreamento invasivo).
