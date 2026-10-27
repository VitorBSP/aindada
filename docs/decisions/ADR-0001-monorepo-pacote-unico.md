# ADR-0001 — Monorepositório com um único pacote Python

- Status: aceito (2026-10-26)
- Responsável: Agente 00

## Contexto
O pedido sugeria `packages/data_pipeline`, `ratings`, `prediction`, `simulation` e `competition_rules`
como pacotes separados. Esses módulos são versionados juntos, compartilham contratos e não têm
consumidores externos.

## Decisão
Um pacote instalável `brasileirao`, em `src/brasileirao/`, com subpacotes de mesmos nomes
(`data_pipeline`, `ratings`, `prediction`, `simulation`, `competition_rules`, mais `validation` e
`storage`). As aplicações ficam em `apps/api` e `apps/web`.

## Consequências
- A instalação é única (`pip install -e .`) e os imports são simples.
- As fronteiras são mantidas por convenção e revisão: `simulation` não importa `storage`, e a API
  não importa `simulation`.
- O pacote pode ser dividido no futuro sem mudar a API pública dos módulos.
