# Simulador do usuário no Supabase (ADR-0015, fase 2)

Código pronto, **desligado**: enquanto `apps/web/assets/simulator-config.js` estiver vazio, o simulador funciona só no
aparelho (fase 1) e a página não carrega nada do Supabase.

## Peças

| Peça | Onde | O que faz |
|---|---|---|
| Esquema, regras de acesso e funções | `infrastructure/supabase/migrations/0001_simulador.sql` | tabelas, RLS, trava dos palpites, pontuação, ranking, média dos visitantes, apagar a conta |
| Sincronização do CI | `src/brasileirao/storage/supabase_sync.py`, `cli sync-simulator`, passo "Simulador — sincronizar com o Supabase" do `publish-site.yml` | envia jogos (com horário de trava), placares, tabela e a trava da Classificação |
| Navegador | `apps/web/assets/simulator-config.js`, `simulator-cloud.js`, `simulator.js` | participar (conta anônima), apelido, e-mail opcional, salvar, média, ranking, apagar |

## Modelo de privacidade

- **Conta anônima** criada só quando o visitante clica em "Participar". Sem clique, nada vai para o servidor.
- **E-mail opcional**, só para entrar em outro aparelho. Fica em `auth.users`, que a API pública não expõe; nenhuma
  função do esquema devolve e-mail.
- **Apelido** é a única identificação pública, e só aparece no ranking de quem marcou "Aparecer no ranking".
  O banco recusa apelido com `@`, e a interface pede para não usar e-mail nem nome completo.
- **Média dos visitantes** só sai com pelo menos 10 participantes por jogo ou por clube (`sim_community`).
- **Apagar**: "Apagar minha participação" chama `sim_delete_me()`, que apaga a conta, o perfil e as simulações.
- RLS em todas as tabelas: cada pessoa lê e escreve só as próprias simulações e o próprio perfil. Jogos, tabela e
  trava são escritos só pela chave de serviço do CI. A visão `sim_scores`, que junta todo mundo, não tem leitura
  pública; o acesso é só pelas funções `sim_ranking`, `sim_my_scores` e `sim_community`.

## Regras do jogo (no banco, não no navegador)

- Palpite de jogo trava no pontapé (`kickoff_utc`; sem horário, 00:00 de Brasília do dia do jogo). Depois disso, o
  trigger `sim_lock_picks` mantém o valor salvo antes e descarta palpite novo para aquele jogo.
- Classificação: a ordem continua editável, mas o ranking usa `ranked_order`, a última ordem salva antes de
  `sim_seasons.classificacao_locks_at`. Padrão: o primeiro jogo da temporada. Para 2026, já passou, então **não há
  ranking da Classificação em 2026** a menos que o dono defina outra trava (variável `SIMULATOR_CLASSIFICACAO_LOCK`).
- Pontuação (bolão clássico, `sim_match_points`): Placar exato 5 (placar), 3 (vencedor ou empate com o saldo
  certo) e 2 (só o vencedor ou empate); Vencedor 1 por acerto; Classificação 3 (posição exata) e 1 (uma posição de
  diferença), só com `final_at` preenchido. Jogos completados pelo modelo não são palpites e não pontuam.

## Como ligar (passos do dono do produto)

1. Criar o projeto em supabase.com (plano gratuito; região sugerida: São Paulo).
2. Em **SQL Editor**, rodar em ordem as migrações de `infrastructure/supabase/migrations/` (`0001`, `0002`, `0003`), cada uma inteira.
3. Em **Authentication → Sign In / Providers**: ligar **Allow anonymous sign-ins** e o provedor **Email** (link
   mágico). Em **URL Configuration**: Site URL = endereço do site no GitHub Pages; em Redirect URLs, acrescentar
   `http://localhost:8080/**` para testes locais.
4. Em **Project Settings → API**: copiar a Project URL e a chave `anon` para `apps/web/assets/simulator-config.js`.
   A chave `anon` é pública por desenho. **A chave `service_role` nunca vai para o site nem para o repositório.**
5. No GitHub (`Settings → Secrets and variables → Actions`): variável `SUPABASE_URL`, segredo
   `SUPABASE_SERVICE_ROLE_KEY` e, opcional, variável `SIMULATOR_CLASSIFICACAO_LOCK` (ISO 8601 com fuso).
6. Primeira carga, antes de abrir o site (as simulações dependem da linha da temporada): com o export local
   atualizado, `SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python -m brasileirao.cli sync-simulator --season 2026`.
   Depois, o `publish-site` sincroniza a cada publicação.

## Antes de publicar

- Página de privacidade no site (rascunho em `docs/project/privacidade-simulador.md`), revisada pelo dono.
- Revisão dos Agentes 00 e 06 (AGENTS.md), incluindo rodar a migração num projeto de teste e conferir as regras de
  acesso com duas contas: uma não lê a simulação da outra, e o ranking não mostra quem não marcou a opção.
- O plano gratuito do Supabase pausa projetos sem uso por uma semana; o CI diário mantém o projeto ativo.
- Recomendado depois: CAPTCHA (Turnstile) nas contas anônimas, contra criação em massa. Pede uma mudança pequena em
  `simulator-cloud.js` (`captchaToken`).

## Limitações conhecidas

- O SQL não foi executado neste ambiente (sem Postgres local). O navegador foi testado com um servidor simulado,
  não com o Supabase de verdade.
- A biblioteca `@supabase/supabase-js@2.45.4` vem do jsDelivr, com a versão fixada e sem hash de integridade.
- Vagas e rebaixados da média dos visitantes usam 4 rebaixados (regra da Série A).
