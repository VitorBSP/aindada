/* Estado de carregamento com o Duck (marca Duck AI, do dono do projeto; BRAND_DECISIONS D-053).
   Sem atraso artificial: o bloco entra invisível e só aparece se a espera passar de ~300 ms (CSS),
   para não piscar quando o cálculo ou o fetch terminam rápido. Com movimento reduzido, só a imagem. */
(() => {
  const BASE = "assets/media/duck-simulador-loading";
  const reducedMotion = () => {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (error) { return false; }
  };

  /* Compacto: só a imagem (o dono do produto prefere a imagem parada no tamanho pequeno). Completo: o vídeo,
     com pôster tirado do 1º quadro (sem salto quando o vídeo começa); com movimento reduzido, só o pôster. */
  function media(compact) {
    if (compact) return `<img class="duck-media" src="${BASE}-compacto.webp" alt="" width="96" height="96" decoding="async">`;
    if (reducedMotion()) return `<img class="duck-media" src="${BASE}.webp" alt="" width="400" height="400" decoding="async">`;
    return `<video class="duck-media" autoplay loop muted playsinline disablepictureinpicture preload="auto" poster="${BASE}.webp" aria-hidden="true" tabindex="-1">
      <source src="${BASE}.webm" type="video/webm"><source src="${BASE}.mp4" type="video/mp4"></video>`;
  }

  /* text: frase curta, sem "chance" (D-046). compact: versão em linha (cálculo da probabilidade conjunta); page: ocupa a altura da tela. */
  function html(text, { compact = false, page = false, detail = "" } = {}) {
    const extra = detail ? `<span class="duck-loading-detail">${detail}</span>` : "";
    return `<div class="duck-loading${compact ? " duck-loading--compact" : ""}${page ? " duck-loading--page" : ""}" role="status" aria-busy="true">
      <span class="duck-frame">${media(compact)}</span>
      <span class="duck-loading-text"><span class="duck-loading-title">${text}</span>${extra}</span></div>`;
  }

  window.AIndaDaLoading = { html };
})();
