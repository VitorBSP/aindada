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
