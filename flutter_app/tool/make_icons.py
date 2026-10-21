"""Generate the NewsVista launcher icon (Android mipmaps + web icons).

    pip install pillow
    python tool/make_icons.py        (run from flutter_app/)

Design: blue -> purple gradient (mockup palette #2563EB -> #8B5CF6), white globe
(news from around the world) and a small four-point sparkle (AI analysis).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 1024  # master size
BLUE, PURPLE = (37, 99, 235), (139, 92, 246)


def gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(int(BLUE[i] + (PURPLE[i] - BLUE[i]) * t) for i in range(3))
    return img


def sparkle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    k = r * 0.28
    draw.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
                  (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill="white")


def artwork(size: int, rounded: bool) -> Image.Image:
    base = gradient(size).convert("RGBA")
    d = ImageDraw.Draw(base)
    w = max(2, int(size * 0.035))  # stroke width
    cx, cy, r = size * 0.46, size * 0.54, size * 0.27
    box = [cx - r, cy - r, cx + r, cy + r]
    d.ellipse(box, outline="white", width=w)                                   # globe
    d.ellipse([cx - r * 0.45, cy - r, cx + r * 0.45, cy + r], outline="white", width=w)  # meridian
    d.line([cx, cy - r, cx, cy + r], fill="white", width=w)
    d.line([cx - r, cy, cx + r, cy], fill="white", width=w)                    # equator
    for f in (-0.55, 0.55):                                                    # latitudes
        y = cy + r * f
        half = (r ** 2 - (r * f) ** 2) ** 0.5 - w * 0.6  # stay inside the outline
        d.line([cx - half, y, cx + half, y], fill="white", width=w)
    sparkle(d, size * 0.77, size * 0.24, size * 0.13)                          # AI sparkle
    sparkle(d, size * 0.88, size * 0.40, size * 0.055)
    if rounded:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
        base.putalpha(mask)
    return base


def main() -> None:
    rounded = artwork(S, rounded=True).filter(ImageFilter.SMOOTH)
    full = artwork(S, rounded=False)
    mip = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for name, px in mip.items():
        out = ROOT / "android" / "app" / "src" / "main" / "res" / f"mipmap-{name}" / "ic_launcher.png"
        rounded.resize((px, px), Image.LANCZOS).save(out)
    web = ROOT / "web"
    rounded.resize((32, 32), Image.LANCZOS).save(web / "favicon.png")
    for px in (192, 512):
        rounded.resize((px, px), Image.LANCZOS).save(web / "icons" / f"Icon-{px}.png")
        full.resize((px, px), Image.LANCZOS).save(web / "icons" / f"Icon-maskable-{px}.png")
    rounded.save(ROOT / "tool" / "icon_1024.png")
    print("icons written")


if __name__ == "__main__":
    main()
