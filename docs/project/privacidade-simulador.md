# Privacidade do simulador — rascunho para revisão

> Rascunho técnico escrito a partir do que o código faz (ADR-0015). Não é parecer jurídico: precisa da revisão do
> dono do produto, e de alguém com conhecimento de LGPD, antes de virar página do site. Os campos entre colchetes
> dependem de decisões ainda não tomadas.

## O que coletamos

- **Se você só usa o simulador**: nada vai para o nosso servidor. A simulação fica guardada no seu navegador
  (armazenamento local) e some se você limpar os dados do site.
- **Se você clica em "Participar"**: criamos uma conta sem nome, identificada por um código aleatório, e guardamos as
  simulações que você fizer no simulador (ordem da tabela, vencedores e placares), com a data de cada alteração.
- **Se você escolhe um apelido**: guardamos o apelido e se você quer aparecer no ranking.
- **Se você liga um e-mail**: guardamos o e-mail, só para você entrar na mesma conta em outro aparelho.

## Para que usamos

- Mostrar a sua simulação em qualquer aparelho em que você entrar.
- Calcular a média dos visitantes (só números somados, com pelo menos 10 pessoas por jogo ou por clube).
- Calcular o ranking, que mostra apenas o apelido de quem escolheu aparecer nele.
- Não usamos os dados para publicidade, não vendemos e não compartilhamos com terceiros, exceto o provedor de
  infraestrutura abaixo.

## Quem vê o quê

- **Ninguém vê o seu e-mail**: nem os outros visitantes, nem o ranking. Ele fica no sistema de contas do
  provedor e não sai em nenhuma tela do site.
- O apelido aparece no ranking **só** se você marcar "Aparecer no ranking".
- As suas simulações individuais só são lidas pela sua própria conta.

## Onde ficam os dados

No Supabase (Supabase Inc.), que hospeda o banco e as contas, na região us-east-1 (Estados Unidos), o que é transferência internacional de dados (LGPD, art. 33). A página do site
também carrega a biblioteca do Supabase pelo jsDelivr.

## Seus direitos

- **Apagar**: o botão "Apagar minha participação" apaga a conta, o apelido, o e-mail e as simulações do servidor, na
  hora e sem volta.
- **Corrigir**: você pode trocar o apelido e as simulações quando quiser (palpites de jogos já iniciados ficam
  travados para o ranking).
- Para outros pedidos (acesso, portabilidade, dúvidas): [contato do controlador a definir].

## Base legal e controlador

- Base legal: [consentimento (art. 7º, I) ao clicar em "Participar" — a confirmar].
- Controlador: [nome e contato a definir].
- Guardamos os dados enquanto a conta existir. [Política para contas anônimas sem uso: a definir.]
