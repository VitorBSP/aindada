"use strict";

/* Popup com os detalhes de um jogo (D-049): "Clubes" e "Rodada a rodada" abrem o mesmo painel, para o visitante ver o
   que aconteceu e por quê. Usa <dialog>, então fecha com Esc, com o botão ou tocando fora, e prende o foco. */
(function () {
  const METRICS = [["title", "Título"], ["top4", "G4"], ["relegation", "Queda"]];
  const MIN_EFFECT = 0.005;

  const escape = (text) => String(text).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const signedPoints = (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} p.p.`;

  function dialogElement() {
    let dialog = document.getElementById("match-popup");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "match-popup";
    dialog.className = "match-popup";
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    document.body.append(dialog);
    return dialog;
  }

  /* impacts = {clube: {title, top4, relegation}}: o quanto o resultado mexeu em cada chance (pontos percentuais).
     Os dois clubes do jogo vêm primeiro; depois só os outros que mais mexeram (o resto não ajuda a entender o jogo). */
  function effectRows(impacts, nameOf, focus = [], extra = 3) {
    if (!impacts) return "";
    const weight = (values) => Math.max(...METRICS.map(([key]) => Math.abs(values[key] || 0)));
    const entries = Object.entries(impacts).map(([clubId, values]) => ({ clubId, values, weight: weight(values) }))
      .filter((entry) => entry.weight >= MIN_EFFECT);
    const line = (entry) => {
      const lines = METRICS.filter(([key]) => Math.abs(entry.values[key] || 0) >= MIN_EFFECT)
        .map(([key, label]) => `<li><span>${label}</span><strong class="${entry.values[key] > 0 ? "up" : "down"}">${signedPoints(entry.values[key])}</strong></li>`).join("");
      return `<div class="match-popup-club"><h3>${escape(nameOf(entry.clubId))}</h3><ul class="match-popup-effects">${lines}</ul></div>`;
    };
    const mine = entries.filter((entry) => focus.includes(entry.clubId)).sort((left, right) => focus.indexOf(left.clubId) - focus.indexOf(right.clubId));
    const others = entries.filter((entry) => !focus.includes(entry.clubId)).sort((left, right) => right.weight - left.weight).slice(0, extra);
    const otherTitle = mine.length ? `<h3 class="match-popup-sub">Outros clubes que mais mexeram</h3>` : "";
    return mine.map(line).join("") + (others.length ? `${otherTitle}${others.map(line).join("")}` : "")
      || `<p class="note">Este jogo não mexeu nas chances de título, G4 nem queda além do ruído da simulação.</p>`;
  }

  function open(title, body) {
    const dialog = dialogElement();
    dialog.innerHTML = `<div class="match-popup-panel">
        <div class="match-popup-head"><h2>${title}</h2><button type="button" class="match-popup-close" aria-label="Fechar">×</button></div>
        ${body}
      </div>`;
    dialog.querySelector(".match-popup-close").addEventListener("click", () => dialog.close());
    if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
  }

  /* Dica de gráfico (D-049): qualquer elemento com data-tip mostra o conteúdo ao passar o mouse ou tocar. */
  let floating = null;
  let hideTimer = null;
  const tipTarget = (node) => (node && node.closest ? node.closest("[data-tip]") : null);

  function placeTip(target, x, y) {
    if (!floating) {
      floating = document.createElement("div");
      floating.className = "chart-float";
      floating.setAttribute("role", "tooltip");
      document.body.append(floating);
    }
    floating.innerHTML = target.dataset.tip;
    floating.hidden = false;
    const width = floating.offsetWidth, height = floating.offsetHeight;
    const left = Math.min(Math.max(8, x + 14), window.innerWidth - width - 8);
    const top = y - height - 14 > 8 ? y - height - 14 : y + 18;
    floating.style.left = `${left + window.scrollX}px`;
    floating.style.top = `${top + window.scrollY}px`;
  }

  function hideTip() { if (floating) floating.hidden = true; }

  document.addEventListener("pointerover", (event) => {
    const target = tipTarget(event.target);
    if (target && event.pointerType !== "touch") placeTip(target, event.clientX, event.clientY);
  });
  document.addEventListener("pointermove", (event) => {
    const target = tipTarget(event.target);
    if (target && event.pointerType !== "touch") placeTip(target, event.clientX, event.clientY);
    else if (event.pointerType !== "touch") hideTip();
  });
  document.addEventListener("pointerout", (event) => {
    const target = tipTarget(event.target);
    if (target && !target.contains(event.relatedTarget)) hideTip();
  });
  document.addEventListener("pointerdown", (event) => {
    const target = tipTarget(event.target);
    clearTimeout(hideTimer);
    if (target && event.pointerType === "touch") {
      placeTip(target, event.clientX, event.clientY);
      hideTimer = setTimeout(hideTip, 4000);
    } else if (!target) hideTip();
  });
  window.addEventListener("scroll", hideTip, { passive: true });

  window.MatchPopup = { open, effectRows, escape };
})();
