# ADR-0002 — Fonte inicial: brasileirao-dataset, com licença restrita

- Status: aceito com restrição (2026-10-26)
- Responsáveis: Agentes 01 e 00

## Contexto
É preciso ter histórico de 2003 a 2026 e a temporada corrente com calendário. As fontes oficiais
(CBF) não têm API pública. O football-data.org exige token. Neste ambiente de desenvolvimento, a
rede só alcança o GitHub.

## Decisão
Usar o repositório `leeofernandes1980/brasileirao-dataset`, fixado por commit (`d677143069202`),
para pesquisa e protótipo local, com status `research_only_unverified` no manifesto.

## Alternativas
- football-data.org: há adaptador pronto; será a fonte de confirmação quando houver token.
- Scraping da CBF: não, até revisar os termos.

## Consequências
- Publicação pública ou comercial fica **bloqueada** até haver uma fonte licenciada para 2024+.
- Os resultados devem ser conferidos com a CBF antes de qualquer divulgação.

## Adendo (2026-10-27): fonte de publicação definida no ADR-0008
- O ADR-0008 (aceito com condições) define as fontes de **publicação**: Adão Duque, versão 18 no
  Kaggle (GPL-2), para 2003–2025, e football-data.org (plano gratuito, atribuição obrigatória) para
  2026 em diante.
- O `brasileirao-dataset` continua `research_only_unverified`. Ele passa a servir **só** para
  pesquisa e conferência local e sai do caminho de publicação.
- Este ADR continua valendo até o plano do ADR-0008 ser implementado e revalidado. Até lá, a
  publicação continua bloqueada.
