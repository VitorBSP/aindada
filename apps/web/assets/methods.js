"use strict";

// Como o Elo é calculado e o que muda em cada competição (D-040). Compartilhado pelos sites de todas as
// competições; os números vêm de methods.json, gerado das configurações versionadas (python -m brasileirao.methods).
(function () {
  const script = document.currentScript;
  const base = script ? new URL(".", script.src) : new URL("assets/", location.href);
  const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
  const percent = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  const ELO_TEXT = `
    <h3 class="elo-title">Como o Elo é calculado</h3>
    <p>Cada clube tem um número de força, o Elo. Antes de cada jogo, a diferença entre os dois (somando ao mandante a vantagem de jogar em casa, <em>H</em>) vira um resultado esperado entre 0 e 1:</p>
    <p class="formula">esperado do mandante = 1 / (1 + 10<sup>−(Elo mandante + H − Elo visitante) / 400</sup>)</p>
    <p>Depois do jogo, o mandante ganha ou perde pontos de Elo conforme o resultado ficou acima ou abaixo do esperado, e o visitante recebe o oposto:</p>
    <p class="formula">variação = K × M × (resultado − esperado)</p>
    <p>O resultado vale 1 na vitória, 0,5 no empate e 0 na derrota. <em>K</em> controla a velocidade da mudança. <em>M</em> pesa o placar: 1 para vitória por um gol, 1,5 por dois e (11 + diferença) / 8 a partir de três. Entre uma temporada e outra, cada clube volta uma parte (<em>regressão</em>) do caminho até a média, porque elencos mudam. A diferença de Elo, junto com outros indicadores, entra num modelo de gols que dá a chance de cada placar, e cada simulação sorteia os jogos que faltam.</p>`;

  function panel(competition, current) {
    const elo = competition.elo;
    const validation = competition.validation;
    const gain = (1 - validation.log_loss / validation.base_rate) * 100;
    const link = competition.id === current ? "" : ` <a href="${escapeHtml(base.href.replace(/assets\/$/, "") + competition.path)}">Ver a página</a>`;
    return `
      <dl class="method-facts">
        <div><dt>K</dt><dd>${decimal.format(elo.k_factor)}</dd></div>
        <div><dt>Mando (H)</dt><dd>${decimal.format(elo.home_advantage)} pontos</dd></div>
        <div><dt>Regressão entre temporadas</dt><dd>${percent.format(elo.season_regression * 100)}%</dd></div>
        <div><dt>Acerto no teste</dt><dd>log loss ${decimal.format(validation.log_loss)} contra ${decimal.format(validation.base_rate)} da taxa base (${percent.format(gain)}% melhor), ${validation.n_matches.toLocaleString("pt-BR")} jogos de ${escapeHtml(validation.seasons)}</dd></div>
      </dl>
      <ul class="method-list">
        <li><strong>Clube novo:</strong> ${escapeHtml(elo.newcomer)}.</li>
        ${competition.extras.map((item) => `<li>${escapeHtml(item)}.</li>`).join("")}
        <li><strong>Dados:</strong> ${escapeHtml(competition.data)}</li>
        <li><strong>Regras:</strong> ${escapeHtml(competition.rules)}${link}</li>
      </ul>`;
  }

  function render(container, current) {
    fetch(new URL("methods.json", base), { cache: "no-cache" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => {
        const competitions = data.competitions;
        const tabs = competitions
          .map((competition) => `<button type="button" role="tab" id="metodo-tab-${competition.id}" aria-controls="metodo-painel-${competition.id}" aria-selected="${competition.id === current}" tabindex="${competition.id === current ? 0 : -1}">${escapeHtml(competition.name)}</button>`)
          .join("");
        const panels = competitions
          .map((competition) => `<div role="tabpanel" id="metodo-painel-${competition.id}" aria-labelledby="metodo-tab-${competition.id}"${competition.id === current ? "" : " hidden"}>${panel(competition, current)}</div>`)
          .join("");
        container.innerHTML = `${ELO_TEXT}
          <h3 class="elo-title">O que muda em cada competição</h3>
          <div class="method-tabs" role="tablist" aria-label="Competições">${tabs}</div>${panels}`;
        const buttons = [...container.querySelectorAll('[role="tab"]')];
        const select = (button) => {
          buttons.forEach((other) => {
            const selected = other === button;
            other.setAttribute("aria-selected", String(selected));
            other.tabIndex = selected ? 0 : -1;
            container.querySelector(`#${other.getAttribute("aria-controls")}`).hidden = !selected;
          });
          button.focus();
        };
        buttons.forEach((button, index) => {
          button.addEventListener("click", () => select(button));
          button.addEventListener("keydown", (event) => {
            const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (step) select(buttons[(index + step + buttons.length) % buttons.length]);
          });
        });
      })
      .catch(() => {
        container.innerHTML = ELO_TEXT;
      });
  }

  window.AIndaDaMetodo = { render };
})();
