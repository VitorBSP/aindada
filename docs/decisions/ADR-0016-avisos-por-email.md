# ADR-0016 — Confirmação do e-mail e envio dos avisos de pontuação

- Status: **proposta**, aguardando decisão do dono do produto. Nada aqui foi implementado, aplicado ou contratado.
- Responsáveis: Agente 00 (decisão), 04 (banco e função de lista), 07 (job e segredos), 08 (textos), 06 (revisão).
- Origem: ressalva B do Agente 06 (ADR-0015, versão 3) e pedido do dono de avisar a pontuação por e-mail.
- Restrições: orçamento zero (D-013), sem criar contas nem usar chaves nesta etapa, sem aviso enviado antes da
  confirmação do endereço.

## Contexto

Hoje a tabela `sim_contacts` (migração `0003`) guarda um e-mail digitado pela pessoa, sem confirmação, e a função
`sim_notification_list` entrega a lista à chave de serviço (`python -m brasileirao.cli simulator-notifications`).
O envio não existe. Dois problemas:

1. **Qualquer pessoa pode cadastrar o e-mail de outra.** Enviar aviso a esse endereço seria mandar mensagem a quem
   nunca consentiu (LGPD, art. 8º) e queimaria a reputação do remetente.
2. **Não há remetente.** O Supabase Auth, no plano gratuito, só envia pelo serviço embutido, com limite de 2
   mensagens por hora (ver fontes). Isso já limita o **link de login por e-mail** da ADR-0015, que depende do mesmo
   envio.

## Fontes e limites (consulta em 2026-11-11)

**Método e ressalva.** Nesta sessão os sites dos provedores não abriram (o acesso de saída bloqueia esses
domínios). Os números abaixo vieram de **trechos devolvidos pela busca** de páginas oficiais, não de leitura direta
da página. Onde só achei fonte de terceiros ou fonte do próprio fornecedor em página de marketing, está dito. **O dono
(ou o Agente 07) deve conferir cada linha na página oficial antes de criar conta**, porque limites mudam sem aviso;
o próprio Supabase diz isso sobre o seu limite.

| Provedor | Limite gratuito | Fonte (consultada em 2026-11-11) | Observações |
|---|---|---|---|
| Supabase Auth, serviço embutido | 2 e-mails por hora (valor pode mudar) | <https://supabase.com/docs/guides/auth/auth-smtp>, <https://supabase.com/docs/guides/auth/rate-limits> | Só dá para alterar o limite com SMTP próprio ou *Send Email hook*. Intervalo mínimo de 60 s entre pedidos de link por pessoa; 360 OTPs por hora (padrões, ajustáveis). |
| Supabase Auth com SMTP próprio | começa em 30 mensagens por hora, ajustável em *Authentication → Rate Limits* | <https://supabase.com/docs/guides/auth/auth-smtp> | O teto real passa a ser o do provedor SMTP. |
| Validade do link/OTP de e-mail | 1 hora (guia de login sem senha); a referência Python cita 24 h | <https://supabase.com/docs/guides/auth/auth-email-passwordless> | Conflito entre páginas: conferir o valor em *Email OTP expiration* no painel. |
| Resend | 100 e-mails por dia (texto da documentação do Resend); 3.000 por mês só em fontes de terceiros | <https://resend.com/docs/knowledge-base/what-is-resend-pricing> | Número de domínios no plano gratuito **não confirmado** (fontes divergem). Plano pago a partir de US$ 20/mês, segundo terceiros. |
| Brevo | 300 e-mails por dia, SMTP *relay* e API incluídos, sem cartão (página do próprio Brevo) | <https://www.brevo.com/free-smtp-server/> | Página de marketing do fornecedor, não é regulamento. A ativação do SMTP pode exigir pedido ao suporte; autenticar o domínio remetente é o passo recomendado; o nome do servidor aparece com grafias diferentes entre páginas (conferir no painel). Marca do Brevo nos e-mails do plano gratuito: **não confirmado**. |
| Supabase Edge Functions | 500.000 invocações por mês no plano gratuito | <https://supabase.com/docs/guides/functions/pricing>, <https://supabase.com/docs/guides/platform/manage-your-usage/edge-function-invocations> | O limite de invocações não é o gargalo; o gargalo é o provedor de e-mail. |
| GitHub Actions | runners padrão gratuitos e sem limite em repositório **público** | <https://docs.github.com/en/actions/reference/runners/github-hosted-runners> | Em repositório privado vale a cota mensal do plano (US$ 12 em conta Free, segundo a página de cobrança). Confirmar se este repositório é público. |
| LGPD | art. 8º §2º (ônus da prova do consentimento é do controlador), §5º (revogação a qualquer momento, procedimento gratuito e facilitado); art. 18, VI e IX (eliminação e revogação) | <https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm> | Texto lido por trechos da busca; conferir a redação compilada. Não é parecer jurídico. |

## Parte 1 — Confirmação do e-mail

### Opções

**A. Usar o e-mail confirmado do Supabase Auth (recomendada).** A pessoa liga o e-mail pelo mesmo caminho do login
(`updateUser({ email })` na conta anônima). O Auth envia o link de confirmação e só marca
`auth.users.email_confirmed_at` quando ela clica. O aviso vai **apenas** para `auth.users.email` confirmado; o campo
`sim_contacts.email` digitado deixa de valer. Em `sim_contacts` fica só a escolha `notify` e um token de descadastro.

- Prós: nenhuma tabela de tokens, validade, limite por pessoa e reenvio já são do Auth; um só e-mail para entrar e
  para receber aviso; menos código e menos superfície de ataque.
- Contras: o aviso só pode ir ao e-mail de login (não a um endereço diferente); exige SMTP próprio no Auth para
  funcionar acima de 2 mensagens por hora, o que o login por e-mail já exigiria de qualquer forma.

**B. Dupla confirmação própria** (`confirmed_at` em `sim_contacts` mais a tabela `sim_contact_tokens`). Permite avisar
um e-mail diferente do login, mas obriga a escrever e revisar: geração e hash do token, validade, uso único, limite
por conta, página ou rota de confirmação e envio do e-mail de confirmação (que, sem servidor, só sai pelo job ou por
uma Edge Function). Esboço comentado no fim do rascunho de migração.

**Recomendação: A.** Resolve a ressalva B com o mínimo de código novo. Só adotar B se o dono quiser avisar um endereço
diferente do de login.

### Fluxo (opção A)

1. A pessoa participa (conta anônima) e, em "Avisos por e-mail", digita o endereço e marca "Quero receber avisos de
   pontuação". O navegador chama `updateUser({ email })` e grava `notify = true` em `sim_contacts`.
2. O Auth envia o e-mail de confirmação. Até o clique, a tela diz "Falta confirmar. Veja a sua caixa de entrada" e
   oferece "Reenviar" (espera de 60 s do Auth) e "Trocar o e-mail".
3. Ao clicar, o Auth confirma e a pessoa volta ao site. Só então ela entra em `sim_notification_list`.
4. Trocar o endereço refaz o ciclo; o antigo para de receber assim que o Auth deixa de tê-lo como confirmado.
5. Todo aviso traz um link de descadastro e o cabeçalho `List-Unsubscribe` (ver Parte 2).

**Validade do token:** a do Auth. O painel mostra o padrão (1 hora, segundo o guia de login sem senha; há página que
diz 24 horas). **Proposta: 24 horas**, o suficiente para quem abre o e-mail mais tarde, e abaixo do limite de 86.400 s
que a documentação desaconselha ultrapassar. Decisão do dono.

**Limite contra abuso:** (a) 60 s entre pedidos de link por pessoa e o limite de e-mails por hora do Auth, ambos
padrões do Supabase e ajustáveis; (b) ajustar o limite do projeto abaixo do teto diário do provedor escolhido, para que
um ataque não consuma a cota dos avisos reais; (c) CAPTCHA (Turnstile), já recomendado em
`docs/architecture/simulator-supabase.md`, nas contas anônimas e no pedido de e-mail; (d) um e-mail só recebe aviso
depois de confirmado, então digitar o e-mail alheio gera no máximo **um** e-mail de confirmação por tentativa, não
avisos recorrentes. Esse é o resíduo de risco: alguém ainda pode provocar mensagens de confirmação a terceiros, daí (a)
a (c).

### Impacto na LGPD

- **Base legal: consentimento** (art. 7º, I). Para os avisos, o consentimento é **específico**: caixa própria,
  desmarcada por padrão, separada do "Participar". A confirmação por clique é a **prova** que o controlador precisa
  guardar (art. 8º, §2º): `email_confirmed_at` mais `sim_contacts.created_at`. Sugestão de acrescentar
  `consented_at` à migração quando o texto do consentimento for aprovado (guardar a versão do texto).
- **Revogar:** link de descadastro em todo e-mail (sem login) e alternância no site, de graça e sem conta nova
  (art. 8º, §5º).
- **Apagar:** `sim_delete_me` já apaga `auth.users`; `sim_contacts` e o novo `sim_notification_log` saem por
  `on delete cascade` (art. 18, VI).
- **Operador:** o provedor de e-mail passa a tratar o endereço e o apelido: entra na lista de terceiros da página de
  privacidade, com a localização dos servidores (**a conferir** no contrato do provedor; transferência internacional,
  art. 33).
- **Retenção:** guardar o e-mail só enquanto a conta existir; sugestão de apagar `notify` e o token de quem pedir
  descadastro, mantendo a conta.

### O que muda em `docs/project/privacidade-simulador.md`

Quando (e só quando) isto for implementado, o rascunho precisa de:

1. Em "O que coletamos": o e-mail passa a ter **duas finalidades**, entrar em outro aparelho e, se marcado, receber
   avisos; e a confirmação por link.
2. Em "Para que usamos": avisos de pontuação (frequência máxima e conteúdo: apelido, ID e pontos da simulação).
3. Em "Quem vê o quê": o e-mail continua invisível aos outros visitantes; o provedor de envio o recebe para entregar
   a mensagem.
4. Em "Onde ficam os dados": o provedor de e-mail e o país dos servidores (a confirmar).
5. Em "Seus direitos": descadastro por link em cada e-mail, revogação a qualquer momento, apagar a participação
   também apaga o histórico de avisos.
6. Em "Base legal": consentimento específico para os avisos, comprovado pela confirmação.
Esta ADR **não altera** esse arquivo agora: ele descreve o que o código faz hoje.

## Parte 2 — Envio dos avisos

### Comparação

| Opção | Limite gratuito (acima) | Segredos | Onde roda | Entregabilidade | Principais riscos |
|---|---|---|---|---|---|
| **1. SMTP próprio no Supabase Auth** (Brevo ou Resend como SMTP) | o do provedor; o Auth começa em 30/h | usuário e senha SMTP, guardados no painel do Supabase | no Supabase, só para e-mails do **Auth** (confirmação, login) | boa se o domínio estiver autenticado | Não serve para o aviso de pontuação, porque o Auth só envia os seus próprios modelos. Resolve a Parte 1. |
| **2. Resend** (API) | 100/dia | chave de API | job do CI ou Edge Function | boa com domínio verificado; depende da regra de domínio do plano gratuito, **não confirmada** | Teto de 100/dia é o menor da lista; o plano gratuito pode exigir domínio próprio. |
| **3. Brevo** (API ou SMTP) | 300/dia | chave de API ou SMTP | job do CI ou Edge Function | boa com domínio autenticado; sem domínio, o remetente é um endereço único validado e a entrega cai | Ativação de SMTP pode passar pelo suporte; marca do plano gratuito não confirmada. |
| **4. GitHub Actions + provedor** (2 ou 3) | Actions grátis em repositório público | chave do provedor como *secret* do repositório | `publish-site.yml`, passo novo e opcional | a do provedor | Não é tempo real (roda com a publicação, duas vezes por dia); a chave fica no CI. |
| **5. Supabase Edge Function + provedor** | 500.000 invocações/mês | chave do provedor como *secret* da função | no Supabase, disparada por agendamento (`pg_cron`) ou chamada | a do provedor | Código novo (Deno) fora do repositório Python, mais uma peça para testar e vigiar. |

### Recomendação

- **Confirmação e login**: opção 1 com **Brevo** (300/dia, SMTP incluído). O mesmo provedor serve ao aviso, o que
  evita contas duplicadas.
- **Aviso de pontuação**: opção 4, um passo novo e **opcional** em `.github/workflows/publish-site.yml`, depois do
  passo "Simulador — sincronizar com o Supabase", com `if: vars.PUBLISH_ENABLED == 'true' && vars.NOTIFICATIONS_ENABLED
  == 'true'`, `continue-on-error: true` e a mesma lógica de "sem segredo, não envia nada". Motivos: o gerador da
  lista já existe e fica em Python (`simulator-notifications`), o job já roda duas vezes por dia, e nada novo
  precisa ser hospedado.
- **Resend** só se o dono tiver domínio próprio e preferir a API; o teto de 100/dia e a regra de domínio pesam contra.
- **Edge Function** fica para depois, se um dia houver necessidade de aviso em tempo real.

### Como o job funciona (proposta)

1. `python -m brasileirao.cli simulator-notifications --season "$SEASON" --out "$RUNNER_TEMP/avisos.csv"`: o arquivo
   fica fora do repositório e fora do artefato do site, e o passo termina apagando-o.
2. Novo subcomando `send-notifications` (a implementar pelos Agentes 04 e 07, **não** criado agora): lê a lista, agrupa
   por pessoa, compara o `fingerprint` (hash dos pontos) com `sim_notification_log` e só envia quando a pontuação
   mudou desde o último aviso e depois de um evento relevante (rodada fechada). Registra o envio no log.
3. **Teto por execução**: no máximo `NOTIFICATIONS_MAX_PER_RUN` e, no total do dia, abaixo do limite diário do
   provedor menos a folga reservada ao Auth (as mensagens de confirmação usam a mesma cota). Sugestão: reservar 100 dos
   300 do Brevo para o Auth. O que sobrar espera a próxima execução, e o job registra quantas pessoas ficaram na fila.
4. Todo e-mail leva `List-Unsubscribe` e link de descadastro (`sim_unsubscribe`, rascunhado na migração).
5. Logs estruturados sem o endereço (só contagens), por `brasileirao.logging_utils`.
6. **Escala**: 300 por dia (Brevo) sustenta algumas centenas de participantes com aviso por rodada. Se o número de
   pessoas com aviso passar de ~150, o aviso semanal precisa virar resumo ou o plano deve mudar. Esse número é uma
   conta de ordem de grandeza, não medida.

### Segredos necessários (nomes sugeridos, não criados)

| Onde | Nome | Para quê |
|---|---|---|
| GitHub (segredo) | `EMAIL_PROVIDER_API_KEY` | envio dos avisos pelo job |
| GitHub (variável) | `NOTIFICATIONS_ENABLED`, `NOTIFICATIONS_FROM`, `NOTIFICATIONS_MAX_PER_RUN` | liga o passo, remetente e teto |
| GitHub (existentes) | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | ler a lista e gravar o log |
| Painel do Supabase | SMTP do provedor | e-mails de confirmação e login do Auth |
| DNS do remetente | registros SPF, DKIM e (recomendado) DMARC | entregabilidade, se houver domínio |

## Rascunhos de texto (para revisão do Agente 08 e do dono)

### E-mail de confirmação

Assunto: **Confirme o seu e-mail no AInda dá?**

> Oi, {apelido}!
>
> Alguém (esperamos que você) pediu para receber avisos de pontuação do simulador do AInda dá? neste endereço.
>
> **[Confirmar o meu e-mail]**
>
> O link vale por 24 horas. Se não foi você, ignore esta mensagem: sem o clique, não enviamos nenhum aviso.
>
> AInda dá? · Para parar de receber, ou apagar a sua participação, use o site: {link}.

### Aviso de pontuação

Assunto: **Sua pontuação no AInda dá?: {pontos} pontos na rodada {n}**

> Oi, {apelido}!
>
> A rodada {n} fechou. Veja como ficaram as suas simulações:
>
> - {modo} · #{id}: **{pontos} pontos** (máximo ainda possível: {max_pontos})
>
> Ver as minhas simulações: {link}
>
> Você recebe este aviso porque confirmou o e-mail e marcou "Quero receber avisos". [Parar de receber]({link de
> descadastro}) · [Apagar a minha participação]({link}).

## Riscos

- **Entrega**: sem domínio próprio autenticado, parte dos e-mails cai em spam ou é recusada. Mitigação: domínio ou
  remetente validado no provedor, volume baixo, descadastro visível.
- **Cota compartilhada**: confirmação, login e aviso dividem o teto diário do provedor. Mitigação: reserva para o Auth e
  teto por execução.
- **Provocar e-mail a terceiros** pelo pedido de confirmação: reduzido por CAPTCHA, 60 s entre pedidos e limite por hora,
  não eliminado.
- **Limites podem mudar** e as fontes acima não foram lidas direto: conferir antes de contratar.
- **Segredo no CI**: a chave do provedor fica no GitHub; usar chave restrita a envio e rotacioná-la.
- **Dados pessoais em arquivo do job**: o CSV com e-mails só existe no *runner* e é apagado ao final; o log não grava
  endereços.
- **Migração não testada**: o SQL do rascunho não rodou em Postgres; testar num projeto de teste com duas contas.
- **Repositório privado** muda a conta do Actions (cota mensal); confirmar a visibilidade.

## O que depende do dono

**Decidir**

1. Opção A (e-mail de login confirmado, recomendada) ou B (outro endereço, mais código).
2. Provedor: Brevo (recomendado), Resend ou outro; e se há domínio próprio para o remetente.
3. Validade do link (proposta: 24 h) e a frequência máxima de avisos (proposta: no máximo um por rodada fechada).
4. Texto do consentimento específico e o controlador/contato que entram na página de privacidade.
5. Se o repositório é público (custo do Actions).
6. Se o login por e-mail e o aviso ficam ligados juntos, já que ambos exigem o SMTP próprio.

**Configurar (só depois das decisões)**

1. Conta no provedor, validação do remetente ou domínio e registros SPF/DKIM/DMARC.
2. SMTP do provedor em *Authentication → SMTP Settings* do Supabase e ajuste de *Rate Limits*.
3. Segredos e variáveis do GitHub da tabela acima.
4. Aplicar a migração (renumerada) num projeto de teste, depois em produção, com revisão dos Agentes 00 e 06.
5. Atualizar `docs/project/privacidade-simulador.md` e o texto da interface (Agentes 08 e 05).

## Consequências

- Nenhum código ou migração muda agora. O rascunho `infrastructure/supabase/migrations/0007_rascunho_avisos_email.sql`
  não entra em nenhuma execução (o prefixo `0007_rascunho` e o cabeçalho "RASCUNHO, não aplicar" impedem aplicar por
  engano na ordem). Conferido em 2026-11-11: nenhum workflow, script ou teste do repositório aplica os `.sql` da pasta; o dono as roda à mão no SQL Editor.
- A ressalva B do Agente 06 continua **aberta** até a implementação; até lá o aviso não deve ser enviado.
- Handoff: Agente 04 (migração e subcomando de envio), 07 (passo opcional no workflow e segredos), 05 (tela de
  confirmação), 08 (textos), 06 (revisão e teste com duas contas).
