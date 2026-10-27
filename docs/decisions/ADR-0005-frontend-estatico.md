# ADR-0005 — Frontend MVP estático, sem build; Next.js depois

- Status: aceito (2026-10-26)
- Responsável: Agente 05

## Contexto
O pedido sugere Next.js. Neste ambiente, os registros npm e PyPI estão bloqueados, o que impede
instalar e verificar um app Next.js. Para o MVP, era essencial verificar a interface (capturas de tela,
largura de celular).

## Decisão
O MVP usa HTML, CSS e JavaScript sem dependências (`apps/web`). Ele consome a API (`/api/...`) ou o
espelho estático (`apps/web/data/api/...json`) gerado por `brasileirao export-web`.

## Consequências
- Roda em qualquer servidor estático e é servido pela própria API.
- A migração para Next.js/TypeScript/Tailwind entra no roadmap (fase 4), reaproveitando o contrato
  `PredictionSnapshot`.
