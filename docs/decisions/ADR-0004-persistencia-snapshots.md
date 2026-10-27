# ADR-0004 — Snapshots imutáveis em SQLite (local); PostgreSQL em produção

- Status: aceito (2026-10-26)
- Responsável: Agente 04

## Decisão
Cada execução grava um snapshot completo (JSON validado por Pydantic) com data de referência, versão
de modelo e de dados, semente e número de simulações. A API apenas lê. O histórico de probabilidades
usa o snapshot mais recente de cada data de referência. A migração para PostgreSQL deve manter o
mesmo esquema de tabela.

## Consequências
- Rollback = servir um snapshot anterior.
- Nenhuma requisição pública dispara simulação.
- Snapshots sintéticos (`is_synthetic`) nunca aparecem na listagem pública.
