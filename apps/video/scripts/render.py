"""Renderiza apps/video/index.html quadro a quadro em MP4 (H.264, 1920x1080 ou 1080x1920).

Uso:
  python render.py                 # vídeo inteiro em out/aindada-apresentacao.mp4
  python render.py --stills 5 12   # só quadros soltos em out/still-<t>.png
  python render.py --format vertical   # 1080x1920 em out/aindada-apresentacao-vertical.mp4

Requer playwright e imageio-ffmpeg; usa o Edge instalado (channel="msedge").
"""

import argparse
import subprocess
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--stills", type=float, nargs="*")
    parser.add_argument("--format", choices=["horizontal", "vertical"], default="horizontal")
    parser.add_argument("--output")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    vertical = args.format == "vertical"
    width, height = (1080, 1920) if vertical else (1920, 1080)
    args.output = args.output or ("aindada-apresentacao-vertical.mp4" if vertical else "aindada-apresentacao.mp4")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto((ROOT / "index.html").as_uri() + ("?format=vertical" if vertical else ""))
        page.evaluate("window.ready")
        duration = page.evaluate("window.DURATION")

        if args.stills is not None:
            for moment in args.stills:
                page.evaluate(f"renderAt({moment})")
                page.screenshot(path=str(OUT / f"still{'-v' if vertical else ''}-{moment:05.1f}.png"))
            print(f"duration={duration:.2f}s")
            browser.close()
            return

        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "image2pipe",
            "-framerate",
            str(args.fps),
            "-c:v",
            "png",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(OUT / args.output),
        ]
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
        total = round(duration * args.fps)
        for frame in range(total):
            page.evaluate(f"renderAt({frame / args.fps})")
            encoder.stdin.write(page.screenshot(type="png"))
            if frame % 150 == 0:
                print(f"{frame}/{total}", flush=True)
        encoder.stdin.close()
        encoder.wait()
        browser.close()
        print(f"ok: {OUT / args.output} ({duration:.1f}s, {total} quadros)")


if __name__ == "__main__":
    main()
