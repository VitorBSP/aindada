/* Estado de carregamento com o Duck (marca Duck AI, do dono do projeto; BRAND_DECISIONS D-053).
   Só em carregamento real (fetch ou cálculo) da Home e do Simulador. Quando aparece, fica pelo menos
   MIN_VISIBLE_MS na tela (pedido do dono, 2026-11-28): quem chama pega o instante em que ele foi pintado
   com painted() e espera hold(instante) antes de trocar pelo resultado. Com movimento reduzido, só a imagem. */
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

  const MIN_VISIBLE_MS = 1000;
  /* Resolve quando o Duck já ficou MIN_VISIBLE_MS na tela desde `startedAt` (na hora, se já ficou). */
  const hold = (startedAt) => new Promise((resolve) => {
    setTimeout(resolve, Math.max(0, MIN_VISIBLE_MS - (performance.now() - startedAt)));
  });

  /* Espera o Duck ser pintado antes de um cálculo pesado no mesmo processo, e devolve esse instante como
     início: o segundo mínimo conta a partir de quando ele aparece de fato. Aba oculta não pinta: 100 ms bastam. */
  const painted = () => new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(performance.now()); } };
    requestAnimationFrame(() => setTimeout(finish, 0));
    setTimeout(finish, 100);
  });

  window.AIndaDaLoading = { html, hold, painted, MIN_VISIBLE_MS };
})();
