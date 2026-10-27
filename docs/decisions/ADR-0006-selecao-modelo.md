# ADR-0006 — Modelo em produção: Poisson com Elo + ataque/defesa; ratings dinâmicos na simulação

- Status: aceito (2026-10-26)
- Responsáveis: Agentes 02 e 06

## Evidência
`docs/methodology/validation.md`. No teste 2019–2025, o log loss foi 1,0213 contra 1,0610 da
taxa-base. Variável de forma: +0,0005 (abaixo da tolerância). Dixon-Coles: sem ganho (ρ ≈ +0,02).
Ratings dinâmicos na simulação, escolhidos na validação: log loss de posição 2,261 contra 2,268 e
cobertura de 90% de 91,7% contra 86,7%. No teste: 2,214 contra 2,237, e 86,9% contra 83,6%.

## Decisão
`feature_set = elo_attack_defense`, Dixon-Coles mantido (efeito praticamente nulo) e ratings
dinâmicos ligados. Revisar a cada temporada com `brasileirao backtest`.

## Pendências
Modelo C (multiclasse calibrado), benchmark de mercado (odds de fechamento), modelagem explícita
de empates e incerteza de parâmetros.
