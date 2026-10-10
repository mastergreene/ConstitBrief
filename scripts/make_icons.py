"""Generate the PWA icons (run once; PNGs are committed). Requires Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "frontend" / "icons"
NAVY, WHITE, RED = (18, 53, 91), (255, 255, 255), (179, 18, 46)


def icon(size: int, maskable: bool = False) -> Image.Image:
    img = Image.new("RGB", (size, size), NAVY)
    d = ImageDraw.Draw(img)
    pad = int(size * (0.2 if maskable else 0.1))  # maskable keeps content in the safe zone
    inner = size - 2 * pad
    font = ImageFont.load_default(size=int(inner * 0.62))
    d.text((size / 2, size / 2 - inner * 0.06), "M", fill=WHITE, font=font, anchor="mm")
    # tick underline = "resolved"
    w = max(2, size // 28)
    y = pad + inner * 0.86
    d.line([(pad + inner * 0.22, y - inner * 0.06), (pad + inner * 0.38, y + inner * 0.04),
            (pad + inner * 0.78, y - inner * 0.12)], fill=RED, width=w * 2, joint="curve")
    return img


OUT.mkdir(parents=True, exist_ok=True)
icon(192).save(OUT / "icon-192.png")
icon(512).save(OUT / "icon-512.png")
icon(512, maskable=True).save(OUT / "maskable-512.png")
icon(180).save(OUT / "apple-touch-icon.png")
print("icons written to", OUT)
