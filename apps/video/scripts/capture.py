"""Captura os visuais do site publicado para o vídeo: só o gráfico, a tabela ou o mosaico, sem os textos explicativos.

Uso: python capture.py [--mobile] [--local-code] [nome ...]
  --mobile      390 px em 3x (para o vertical); sem a opção, 1280 px em 2x.
  --local-code  dados do site publicado com HTML/JS/CSS deste checkout (textos ainda não publicados).
Saída: captures/<nome>.png (ou captures/mobile/<nome>.png), recortada no conteúdo.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://vitorbsp.github.io/aindada/"
OUT = Path(__file__).resolve().parents[1] / "captures"
APPS = Path(__file__).resolve().parents[2]
SITE_DIRS = {
    "serie-b": "web-serie-b",
    "premier-league": "web-ligas",
    "la-liga": "web-ligas",
    "champions-league": "web-champions",
    "mundial-lol": "web-lol",
}

# Alvos: seletor CSS (primeiro), "seletor@n" (n-ésimo), "h2=Texto" (título) ou "next:h2=Texto" (o bloco depois dele).
SHOTS = {
    "home-titulo": ("#/inicio/titulo", ["figure.mosaic"]),
    "home-rebaixamento": ("#/inicio/rebaixamento", ["figure.mosaic"]),
    "tabela": ("#/classificacao", ["table.standings", "main > div.legend"]),
    "clube-gremio": ("#/clubes/gremio", ["h1.club-heading", "main > svg@1"]),
    "partidas": ("#/partidas", ["main > div.legend", "section.match-day@2"]),
    "rodadas": ("#/rodadas", ["h2=Onde o campeonato mudou", "next:h2=Onde o campeonato mudou"]),
    "serie-b": ("serie-b/", ["div.races"]),
    "premier-league": ("premier-league/", ["div.races"]),
    "la-liga": ("la-liga/", ["div.races"]),
    "champions-league": ("champions-league/", ["div.races"]),
    "mundial-lol": ("mundial-lol/", ["h2=Chave do mata-mata", "next:h2=Chave do mata-mata"]),
}

HIDE_TEXT = """
main p.lede, main .note, main .lede-method, main .mosaic-key, main .match-meta, main .impact-row,
main span.kicker, main p.more, main .race > p { display: none !important; }
"""

TIGHT_BOX = """(targets) => {
  const find = (spec) => {
    if (spec.startsWith("next:")) { const h = find(spec.slice(5)); let n = h && h.nextElementSibling;
      while (n && getComputedStyle(n).display === "none") n = n.nextElementSibling; return n; }
    if (spec.includes("=")) { const [tag, text] = spec.split("=");
      return [...document.querySelectorAll("main " + tag)].find((el) => el.textContent.trim().startsWith(text)); }
    const [sel, idx] = spec.split("@"); return document.querySelectorAll(sel)[Number(idx || 0)];
  };
  let box = null;
  const grow = (r) => {
    if (r.width < 1 || r.height < 1) return;
    box = box
      ? { l: Math.min(box.l, r.left), t: Math.min(box.t, r.top),
          r: Math.max(box.r, r.right), b: Math.max(box.b, r.bottom) }
      : { l: r.left, t: r.top, r: r.right, b: r.bottom };
  };
  const hidden = (el) => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.display === "none" || s.visibility === "hidden") return true;
    }
    return false;
  };
  const roots = targets.map((spec) => {
    const el = find(spec);
    if (!el) throw new Error("alvo não encontrado: " + spec);
    return el;
  });
  for (const root of roots) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let node = walker.currentNode; node; node = walker.nextNode()) {
      if (node.nodeType === Node.TEXT_NODE) { if (!node.textContent.trim() || hidden(node.parentElement)) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        grow(range.getBoundingClientRect());
        continue; }
      if (hidden(node)) continue;
      const style = getComputedStyle(node);
      const leaf = !node.firstElementChild || ["IMG", "use", "rect", "path", "circle", "line"].includes(node.tagName);
      const ruled = parseFloat(style.borderTopWidth) > 0 || parseFloat(style.borderBottomWidth) > 0
        || style.backgroundColor !== "rgba(0, 0, 0, 0)";
      if (leaf || ruled) grow(node.getBoundingClientRect());
    }
  }
  // Some com o que está fora da área (título da página, notas vizinhas) sem mexer no layout.
  for (const el of document.body.querySelectorAll("*")) {
    if ((el instanceof SVGElement && el.tagName !== "svg") || el.querySelector("symbol, defs")) continue;
    const r = el.getBoundingClientRect();
    const inside = r.bottom > box.t && r.top < box.b && r.right > box.l && r.left < box.r;
    if (!inside) el.style.visibility = "hidden";
  }
  return { x: box.l + scrollX, y: box.t + scrollY, width: box.r - box.l, height: box.b - box.t };
}"""


# Mosaicos viram dados (bolinhas com o desenho de cada clube e a legenda) para o vídeo animar bolinha a bolinha.
MOSAIC_DATA = """() => {
  const fig = document.querySelector("figure.mosaic"), svg = fig.querySelector("svg.mosaic-chart");
  const dots = [...svg.querySelectorAll(":scope > use")].map((u) =>
    [u.getAttribute("href"), +u.getAttribute("x"), +u.getAttribute("y"), +u.getAttribute("width")]);
  const legend = [...fig.querySelectorAll(".mosaic-legend li")].map((li) => ({
    href: li.querySelector("use").getAttribute("href"),
    name: li.querySelector(".club-cell span").textContent.trim(),
    pct: li.querySelector("strong").textContent.trim() }));
  return { viewBox: svg.getAttribute("viewBox"), defs: svg.querySelector("defs").outerHTML, dots, legend };
}"""


def local_code(route):
    rel = route.request.url.split("/aindada/", 1)[1].split("?")[0].split("#")[0] or "index.html"
    first, _, rest = rel.partition("/")
    target = APPS / SITE_DIRS[first] / (rest or "index.html") if first in SITE_DIRS else APPS / "web" / rel
    if target.suffix in {".html", ".js", ".css"} and target.is_file():
        route.fulfill(path=str(target))
    else:
        route.continue_()


def main() -> None:
    args = sys.argv[1:]
    mobile = "--mobile" in args
    only = {name for name in args if not name.startswith("--")}
    out_dir = OUT / "mobile" if mobile else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    pad = 16 if mobile else 28
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        if mobile:
            page = browser.new_page(
                viewport={"width": 390, "height": 844},
                device_scale_factor=3,
                is_mobile=True,
                has_touch=True,
                color_scheme="light",
            )
        else:
            page = browser.new_page(
                viewport={"width": 1280, "height": 800}, device_scale_factor=2, color_scheme="light"
            )
        if "--local-code" in args:
            page.route("**/aindada/**", local_code)
        for name, (path, targets) in SHOTS.items():
            if only and name not in only:
                continue
            page.goto("about:blank")
            page.goto(BASE + path, wait_until="networkidle")
            if name.startswith("home-"):
                data = json.dumps(page.evaluate(MOSAIC_DATA), ensure_ascii=False)
                key = f"{name}-mobile" if mobile else name
                (OUT / f"{key}.mosaic.js").write_text(
                    f"(window.MOSAICS = window.MOSAICS || {{}})[{json.dumps(key)}] = {data};\n", encoding="utf-8"
                )
            page.add_style_tag(content=HIDE_TEXT)
            page.wait_for_timeout(1200)
            box = page.evaluate(TIGHT_BOX, targets)
            width = page.evaluate("document.documentElement.clientWidth")
            clip = {"x": max(0, box["x"] - pad), "y": max(0, box["y"] - pad)}
            clip["width"] = min(width, box["x"] + box["width"] + pad) - clip["x"]
            clip["height"] = box["y"] + box["height"] + pad - clip["y"]
            page.screenshot(path=str(out_dir / f"{name}.png"), clip=clip, full_page=True)
            print(name, {key: round(value) for key, value in clip.items()})
        browser.close()


if __name__ == "__main__":
    main()
