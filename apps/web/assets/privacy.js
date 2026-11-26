/* Página de privacidade (#/privacidade). O texto descreve o que o código faz hoje; mudou o código (armazenamento,
   serviço externo, campo guardado no Supabase), muda esta página. Rascunho de origem: docs/project/privacidade-simulador.md. */
(function () {
  "use strict";

  /* ---- Parâmetros do controlador: troque aqui, não no texto. ---- */
  const CONTROLLER = {
    name: "Vítor Pereira",
    brand: "Duck AI Labs",
    // Canal público do projeto. Pedido de privacidade não deve trazer dados pessoais numa issue aberta.
    repositoryUrl: "https://github.com/VitorBSP/aindada/issues",
    // E-mail público para pedidos de privacidade. Vazio: a página indica só o repositório.
    email: "",
  };
  const UPDATED_AT = "26/11/2026";
  const SUPABASE_REGION = "us-east-1 (Norte da Virgínia, Estados Unidos)";

  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

  function contactHtml() {
    const repository = `<a href="${escapeHtml(CONTROLLER.repositoryUrl)}">repositório do projeto no GitHub</a>`;
    if (CONTROLLER.email) {
      return `escreva para <a href="mailto:${escapeHtml(CONTROLLER.email)}">${escapeHtml(CONTROLLER.email)}</a>. Para dúvidas gerais, há também o ${repository}.`;
    }
    return `abra um pedido no ${repository} sem escrever nele e-mail, apelido nem outro dado pessoal (o pedido fica público); combinamos ali um canal privado para seguir.`;
  }

  function render(main) {
    const config = window.AINDA_DA_SIMULATOR || {};
    const serverOn = Boolean(config.supabaseUrl && config.supabaseAnonKey);
    const captchaOn = serverOn && Boolean(config.turnstileSiteKey);
    const controller = `${escapeHtml(CONTROLLER.name)} (${escapeHtml(CONTROLLER.brand)})`;
    main.innerHTML = `
      <a class="back-link" href="#/">‹ Início</a>
      <div class="screen-head"><h1 class="screen-title">Privacidade</h1></div>
      <p class="lede">O que fica no seu navegador, o que vai para serviços de fora e o que acontece se você participar do ranking do Simulador.</p>

      <section class="card privacy-summary" aria-labelledby="privacy-summary">
        <h2 id="privacy-summary">Em resumo</h2>
        <ul>
          <li>Usar o site não pede conta, nome nem e-mail. Simulações, time do coração e tema ficam no seu navegador.</li>
          <li>Algumas telas consultam serviços de fora do site (lista abaixo). Eles recebem o seu endereço IP e o tipo de navegador, como em qualquer acesso à internet, mas não recebem as suas simulações.</li>
          ${serverOn ? `<li>As simulações só vão para o nosso servidor se você clicar em <strong>Participar</strong> no Simulador. A participação se apaga na hora, pelo botão <strong>Apagar minha participação</strong>.</li>` : ""}
          <li>Não há anúncio, ferramenta de análise de audiência nem cookie de rastreamento.</li>
        </ul>
      </section>

      <section class="privacy-section" aria-labelledby="privacy-local">
        <h2 id="privacy-local">No seu navegador</h2>
        <p>O site guarda estas informações no armazenamento local do navegador (<code>localStorage</code>). Elas não saem do aparelho por conta própria e somem quando você limpa os dados do site.</p>
        <dl class="privacy-list">
          <div><dt><code>ainda-da:tema</code></dt><dd>Tema claro ou escuro.</dd></div>
          <div><dt><code>ainda-da:meu-time:…</code></dt><dd>O time que você escolheu, uma vez por competição.</dd></div>
          <div><dt><code>ainda-da:simulador:serie-a:…</code></dt><dd>Rascunhos e simulações salvas no Simulador, com os palpites e as datas.</dd></div>
          ${serverOn ? `<div><dt><code>ainda-da-simulador-auth</code></dt><dd>Só depois de Participar: a sessão da conta sem nome, gravada pela biblioteca do Supabase para você continuar conectado.</dd></div>` : ""}
        </dl>
      </section>

      <section class="privacy-section" aria-labelledby="privacy-third">
        <h2 id="privacy-third">Serviços de fora do site</h2>
        <p>Mesmo sem Participar, estes serviços recebem o endereço IP, o navegador e o horário de cada acesso:</p>
        <dl class="privacy-list">
          <div><dt>GitHub Pages (GitHub, Inc., Estados Unidos)</dt><dd>Hospeda o site. Recebe cada página e arquivo que o navegador pede.</dd></div>
          ${serverOn ? `<div><dt>Supabase (Supabase, Inc., região ${escapeHtml(SUPABASE_REGION)})</dt><dd>Nos dias de jogo, as páginas da Série A pedem ao Supabase os placares parciais da rodada; a aba Ao vivo repete o pedido a cada 15 segundos. Ao abrir o Simulador, o navegador também consulta a média dos visitantes. Esses pedidos levam só a chave pública do site, sem simulação nem dado seu.</dd></div>
          <div><dt>jsDelivr (Estados Unidos e rede mundial de servidores)</dt><dd>Ao abrir o Simulador, o navegador baixa a biblioteca do Supabase pelo jsDelivr, numa versão fixa conferida por um código de integridade: se o arquivo vier diferente, o navegador não o executa.</dd></div>` : ""}
          ${captchaOn ? `<div><dt>Cloudflare Turnstile (Cloudflare, Inc., Estados Unidos)</dt><dd>Ao clicar em Participar ou pedir o link de entrada por e-mail, uma verificação contra robôs roda no seu navegador. A Cloudflare recebe dados técnicos do aparelho e do navegador para decidir se o acesso é automatizado.</dd></div>` : ""}
        </dl>
      </section>

      ${serverOn ? `<section class="privacy-section" aria-labelledby="privacy-join">
        <h2 id="privacy-join">Se você clicar em Participar</h2>
        <p>Criamos no Supabase uma <strong>conta sem nome</strong>, identificada por um código aleatório. Na hora, as simulações já salvas neste aparelho também são enviadas (até 10 por pessoa a cada jogo novo). O servidor guarda:</p>
        <dl class="privacy-list">
          <div><dt>Conta</dt><dd>O código aleatório, a data de criação e os registros técnicos de acesso que o Supabase mantém (como data e endereço IP das entradas).</dd></div>
          <div><dt>Simulações</dt><dd>Modo, temporada, ordem da tabela, vencedores ou placares (os seus e os sorteados pelo modelo), a tabela final, se o modelo ajudou e as datas de cada alteração.</dd></div>
          <div><dt>Apelido (opcional)</dt><dd>O apelido e se você quer aparecer no ranking.</dd></div>
          <div><dt>E-mail de entrada (opcional)</dt><dd>Para entrar na mesma conta em outro aparelho. O Supabase manda o link de confirmação e o de entrada.</dd></div>
          <div><dt>E-mail de avisos (opcional)</dt><dd>Separado do de entrada, numa tabela que só a sua conta lê, para mandarmos a sua pontuação. A lista de avisos só sai do banco com a chave de administrador, fora do site.</dd></div>
        </dl>
        <h3>Para que usamos</h3>
        <ul>
          <li>Mostrar as suas simulações em qualquer aparelho em que você entrar.</li>
          <li>Calcular a sua pontuação e o ranking, que mostra só o apelido de quem marcou "Aparecer no ranking".</li>
          <li>Calcular a média dos visitantes: só números somados e só com participantes suficientes para não expor a escolha de ninguém (o mínimo aparece na própria tela).</li>
          <li>Mandar a pontuação para o e-mail de avisos, se você ligou os avisos.</li>
        </ul>
        <p>Não vendemos os dados, não usamos para publicidade e não os passamos a ninguém além dos serviços desta página.</p>
        <h3>Quem vê o quê</h3>
        <ul>
          <li>O seu e-mail não aparece para outros visitantes, nem no ranking, nem em tela nenhuma do site.</li>
          <li>O apelido aparece só no ranking e só se você marcar "Aparecer no ranking". Não use e-mail nem nome completo como apelido.</li>
          <li>As regras do banco deixam cada conta ler só as próprias simulações, o próprio perfil e o próprio e-mail de avisos.</li>
          <li>O responsável pelo site, com acesso de administrador ao banco, consegue ver os dados guardados. Ele só os usa para o que está nesta página.</li>
        </ul>
      </section>

      <section class="privacy-section" aria-labelledby="privacy-transfer">
        <h2 id="privacy-transfer">Transferência para fora do Brasil</h2>
        <p>O banco fica no Supabase, na região ${escapeHtml(SUPABASE_REGION)}, e os outros serviços desta página também estão fora do Brasil. É transferência internacional de dados (LGPD, art. 33). Ao clicar em Participar, você consente com o tratamento descrito aqui (art. 7º, I) e com essa transferência (art. 33, VIII).</p>
      </section>

      <section class="privacy-section" aria-labelledby="privacy-rights">
        <h2 id="privacy-rights">Seus direitos</h2>
        <dl class="privacy-list">
          <div><dt>Apagar</dt><dd>No Simulador, <strong>Apagar minha participação</strong> apaga do servidor, na hora e sem volta, a conta, o apelido, os dois e-mails e as simulações. As do aparelho continuam lá até você excluí-las ou limpar os dados do site.</dd></div>
          <div><dt>Corrigir</dt><dd>Troque o apelido, os e-mails e as simulações quando quiser. Palpites de jogos que já começaram ficam travados para o ranking.</dd></div>
          <div><dt>Desligar os avisos</dt><dd>Em "Avisos por e-mail", desmarque o aviso ou use "Remover e-mail".</dd></div>
          <div><dt>Sair</dt><dd>"Sair" desconecta este aparelho, mas não apaga a participação.</dd></div>
          <div><dt>Outros pedidos</dt><dd>Para acesso, cópia dos dados, revogar o consentimento ou tirar dúvidas, ${contactHtml()} Você também pode reclamar à Autoridade Nacional de Proteção de Dados (ANPD).</dd></div>
        </dl>
        <p>Guardamos os dados da participação enquanto a conta existir. Ainda não há prazo para apagar sozinhas as contas sem uso.</p>
      </section>` : ""}

      <section class="privacy-section" aria-labelledby="privacy-controller">
        <h2 id="privacy-controller">Quem é o responsável</h2>
        <p>Controlador: ${controller}. Contato: ${contactHtml()}</p>
        <p class="note">Atualizada em ${UPDATED_AT}. Projeto independente e gratuito, sem relação com a CBF, as ligas nem os clubes.</p>
      </section>`;
  }

  window.AIndaDaPrivacidade = { render, CONTROLLER };
})();
