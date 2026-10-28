# Frontend (Agente 05)

MVP estático em `apps/web` (ADR-0005). Rotas por hash:

| Rota | Conteúdo |
|---|---|
| `#/` e `#/inicio/{titulo,g4,rebaixamento}` | home por disputa (D-031): sem parâmetro, mostra a disputa que mais mudou desde o snapshot anterior (soma das variações por vaga ≥ 5 p.p.) ou, sem mudança relevante, a mais aberta (Σ p(1−p) por vaga); o usuário pode trocar. Manchete e texto da disputa, mosaico de 1.000 pontos (vagas da disputa), faixas da Libertadores na visão G4, mudanças da disputa desde o snapshot anterior, aviso de jogos recentes sem placar |
| `#/classificacao/{visão}` | colunas fixas (Pts, J, V, SG, Pts proj. com intervalo de 90%, Pos. média) e um grupo variável escolhido pelo usuário: `titulo`, `libertadores` (G4, Liberta. grupos, Liberta. total, com seletor de cenário), `sul-americana` (com seletor de cenário), `rebaixamento`, `forca` (Elo, ataque, defesa com posição no quesito) e `dificuldade` (índice total, em casa e fora, pontos esperados em casa e fora, lidos de `team.schedule` do snapshot, e escudos dos próximos 5 adversários) |
| `#/clubes` e `#/clubes/{id}` | sem id: grade de escudos em ordem de classificação. Com id: faixa de escudos para trocar de clube, probabilidades, distribuição de posição, evolução temporal, força estimada, dificuldade do que falta (`team.schedule`), próximos jogos (adiados no fim), cenários favorável e desfavorável |
| `#/partidas` | jogos restantes com 1X2, gols esperados, os 3 placares mais prováveis (`top_scores`) e a chance de 3 gols ou mais (`p_three_plus_goals`), com volta ao placar mais provável quando o snapshot não traz esses campos; seção "Adiado, data a definir" para jogo sem placar com data mais de 7 dias antes da data de referência (provisório até o Agente 01 marcar `postponed` na fonte); últimos resultados |
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

Escudos aparecem em todas as páginas (D-031): `crest()` em `app.js` lê `assets/crests/manifest.json`, com a mesma regra do marcador neutro de `rounds.js` (D-028/D-029).

Tabela (`#/classificacao/{visão}`): todas as colunas, menos "Próximos jogos", ordenam ao clicar no cabeçalho (`aria-sort` no `th`); a ordem vale para a visão aberta. Rodada a rodada (`rounds.js`): comparativo com até 5 times (`SERIES`, tokens `--series-4` e `--series-5`) e dica própria nos gráficos de série, que mostra valor, jogo e placar de cada time na rodada (`view.matches`), por `pointermove`/`pointerdown`, com `touch-action: pan-y` para arrastar o dedo sem rolar a página na horizontal.
