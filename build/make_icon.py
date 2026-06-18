#!/usr/bin/env python3
"""Generate the application icon (purple 'FS' badge).

Build-time only; requires Pillow (not shipped to players). Produces a multi-size
.ico for Windows and a .png that can be converted to .icns on macOS.

Usage:
    python build/make_icon.py
Outputs:
    build/icon.ico
    build/icon.png
"""

import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
PURPLE_BG = (88, 42, 156, 255)      # deep purple
PURPLE_HL = (140, 90, 220, 255)     # lighter purple accent
TEXT_COLOR = (240, 235, 255, 255)
SIZES = [16, 32, 48, 64, 128, 256]


def _font(size):
    # Try a few common bold fonts; fall back to PIL's default.
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded-rect badge background.
    radius = max(2, size // 6)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius,
                        fill=PURPLE_BG)
    # Subtle top highlight bar.
    d.rounded_rectangle([0, 0, size - 1, size // 2], radius=radius,
                        fill=PURPLE_HL)
    d.rounded_rectangle([0, size // 4, size - 1, size - 1], radius=radius,
                        fill=PURPLE_BG)

    # "FS" text centered.
    text = "FS"
    font = _font(int(size * 0.5))
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) / 2 - bbox[0]
        ty = (size - th) / 2 - bbox[1]
    except AttributeError:
        tw, th = d.textsize(text, font=font)
        tx, ty = (size - tw) / 2, (size - th) / 2
    d.text((tx, ty), text, fill=TEXT_COLOR, font=font)
    return img


def main():
    images = [_render(s) for s in SIZES]
    ico_path = os.path.join(OUT_DIR, "icon.ico")
    png_path = os.path.join(OUT_DIR, "icon.png")
    # Save .ico with all sizes embedded.
    images[-1].save(ico_path, format="ICO",
                    sizes=[(s, s) for s in SIZES])
    images[-1].save(png_path, format="PNG")
    print(f"wrote {ico_path}")
    print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
