# Catálogo de fontes de dados (Agente 01)

Última revisão: 2026-10-26. Toda ingestão grava `data/raw/<fonte>/<versão>/manifest.json`, com origem,
versão/commit, data de coleta, SHA-256 dos arquivos, status de licença e usos permitidos.

| Fonte | Conteúdo | Cobertura | Acesso | Licença / restrições | Status no projeto |
|---|---|---|---|---|---|
| [brasileirao-dataset](https://github.com/leeofernandes1980/brasileirao-dataset) | Partidas, cartões, gols, estatísticas | 2003–2026, atualizado por GitHub Actions | `git clone` (adaptador `BrasileiraoDatasetSource`) | Sem arquivo LICENSE. 2003–2023 vêm do dataset de Adão Duque. 2024+ foi coletado da API não oficial do Sofascore, cujos termos restringem coleta automatizada e uso comercial | **Em uso**, `research_only_unverified`. Pesquisa e protótipo local apenas. Bloqueia publicação comercial |
| [CBF](https://www.cbf.com.br) | Tabela, súmulas, regulamentos (fonte oficial) | temporada corrente | site; sem API pública documentada | Termos do site a revisar antes de qualquer coleta automatizada | Regulamento 2026 usado para as regras. Resultados: conferência manual pendente. Rede deste ambiente bloqueada |
| [football-data.org](https://www.football-data.org) | API v4, competição BSA: jogos, tabela | temporadas recentes | token gratuito (`FOOTBALL_DATA_ORG_TOKEN`) | Plano gratuito com atribuição e limite de requisições. Verificar uso comercial | Adaptador `FootballDataOrgSource` implementado e testado com fixture sintética. Não validado contra a API real |
| [Football-Data.co.uk](https://www.football-data.co.uk) | Resultados e odds de fechamento (arquivo BRA) | 2012+ | download CSV | Uso livre para pesquisa com atribuição. Verificar termos para uso comercial | Planejado para o benchmark de mercado (etapa 3). Rede bloqueada aqui |
| [Dados Futebol](https://dadosfutebol.com.br) | Dados e análises | — | a investigar | a investigar | Não avaliado |
| Escudos de clubes ([Wikimedia Commons](https://commons.wikimedia.org) e [Wikipédia em português](https://pt.wikipedia.org)) | Escudo de cada clube (SVG ou PNG transparente) | os 20 clubes da Série A 2026, coletados em 2026-10-26 | download manual autorizado pelo usuário; arquivos em `apps/web/assets/crests/` (o `manifest.json` de lá só tem o nome do arquivo); proveniência por arquivo (URL, página, autor, licença, data de coleta, SHA-256) em `data/reference/crests_provenance.json`, fora da pasta servida pelo site | 17 do Commons sob **PD-textlogo** (Mirassol e São Paulo também PD-shape): domínio público por falta de originalidade, mas **marcas registradas** (`{{Trademarked}}`). 3 (Bragantino, Corinthians, Vasco) **não livres**: © dos clubes, enviados à pt.wikipedia como conteúdo restrito | **Em uso** na interface local. `livre` para os 17. Os 3 estão marcados `livre` por decisão do dono do produto (campo `license_status_override` em `data/reference/crests_provenance.json`), mas não têm licença livre e precisam de revisão antes de publicação. Marca registrada: só para identificar o clube como dado, nunca como marca do produto |

## Problemas de qualidade conhecidos

Registrados em `data/reference/known_exceptions.csv` e reportados em `data/gold/quality_report.json`:

- **2009**: Botafogo x Flamengo aparece duas vezes com o mesmo mando (rodadas 12 e 31). Mantido como
  na fonte até confirmação. Hipótese: o mando do jogo da rodada 12 era do Flamengo.
- **2016**: Chapecoense x Atlético-MG (38ª rodada) não foi disputada. É uma exceção histórica real.
- **2026**: 12 partidas com data passada sem placar na fonte em 26/10/2026, entre elas um jogo da
  rodada 21 (Chapecoense x Vasco), um da 31 e dez da rodada 32. Elas são simuladas, nunca
  preenchidas.

- **Cartões 2026**: a fonte só tem cartões para 185 dos 308 jogos observados. Abaixo de 95% de
  cobertura, o desempate por cartões (Art. 15, critérios 5 e 6) é substituído por sorteio, com aviso
  no snapshot. Os IDs de partida dos cartões de 2003–2014 não casam com os IDs das partidas.

## Política

1. Não usar uma fonte só porque está acessível: o status de licença precisa estar registrado.
2. Placar ausente é sempre `scheduled`. Nunca vira 0 x 0.
3. Diferenças entre ingestões (resultado, data, rodada) vão para `data/silver/changes.jsonl`.
4. Antes de qualquer publicação pública, é preciso substituir ou licenciar a fonte de 2024+.
