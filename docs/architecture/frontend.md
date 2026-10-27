# Frontend (Agente 05)

MVP estático em `apps/web` (ADR-0005). Rotas por hash:

| Rota | Conteúdo |
|---|---|
| `#/` | chance de título, risco de rebaixamento, disputa pela Libertadores (faixas), mudanças desde o snapshot anterior, aviso de jogos sem placar |
| `#/classificacao` | tabela real e projeção (pontos com intervalo de 90%, posição média, título, G4, Libertadores grupos/total, Sul-Americana, rebaixamento) e seletor de cenário externo |
| `#/clubes/{id}` | probabilidades, distribuição de posição, evolução temporal, força estimada, próximos jogos, cenários favorável e desfavorável |
| `#/partidas` | jogos restantes com 1X2, gols esperados e placar mais provável; últimos resultados |
| `#/rodadas/{n}` | por rodada: gráfico de onde o campeonato mudou (resultados vs. força), resumo da rodada (quem mais subiu e caiu, jogo decisivo, maior surpresa), tabela real com variação decomposta, jogos do intervalo com os clubes afetados e a avaliação de todas as rodadas (intensidade, líder, favorito, jogo decisivo, surpresa) |
| `#/rodadas/time/{id}` | por time: posição e chances atuais com variação desde a pré-temporada, gráficos de chances e de posição (real e projetada) por rodada, momentos que mais mudaram a temporada e tabela rodada a rodada com os jogos do time e o efeito de cada um |
| `#/rodadas/comparar/{ids}` | comparativo de até 3 times numa métrica (título, G4, rebaixamento, posição, pontos, pontos projetados), com tabela de valores, e a tabela de todos os times em qualquer rodada escolhida |
| `#/metodologia` | modelo, regras, validação, fontes, licença e limitações |

Código da aba Rodada a rodada em `assets/rounds.js` e `assets/rounds.css` (`app.js` só delega a rota). Escudos opcionais lidos de `assets/crests/manifest.json`; sem manifest, só os nomes. Gráficos de séries usam no máximo 3 cores (`--title`, `--libertadores`, `--sudamericana`, validadas para daltonismo nos dois temas) e também diferenciam as séries por traço, marcador e rótulo.

Princípios: a data de referência e os jogos observados aparecem sempre; "0%" é explicado como
"não ocorreu nas simulações"; faixas aparecem quando o resultado depende de torneios externos; há
tema escuro automático; o layout cabe em 360 px.

Identidade visual: tokens atuais em `apps/web/assets/styles.css`. Elementos de marca vêm do
Agente 08 (`docs/brand/`) e só são implementados após decisão registrada em
`docs/brand/BRAND_DECISIONS.md`. Marca "AInda dá?" aplicada na interface (D-024): assinatura no cabeçalho, favicon, ícones e
`manifest.webmanifest`, Inter Tight servida localmente, tokens claros e escuros no topo de
`assets/styles.css`. Desde D-022 o Agente 08 também responde pelo visual e pela UX da interface. Seletor de cenários
(D-025): escolhas parciais ficam em `state.scenarioChoice`; a faixa considera só os cenários
compatíveis, cada seletor só oferece valores possíveis e o foco volta ao seletor alterado.
Princípios e jornadas: `docs/ux/`.

Insights editoriais: `start()` carrega `/seasons/{s}/insights` (com o espelho estático
`data/api/seasons/{s}/insights.json` gerado por `insights-publish`). A home usa `home_lead` como
manchete (h1 + texto + links) e até 2 `home_secondary`. A aba de rodadas recebe
`highlights(view)` no contexto de `Rounds.render`, uma função síncrona e sem efeitos, e mostra o
bloco só na rodada mais recente. Só entram insights cuja data de referência é a do snapshot exibido.

Verificação: capturas de tela em 1280 px e 375 px via Playwright, sem erros de JavaScript e sem
rolagem horizontal.
