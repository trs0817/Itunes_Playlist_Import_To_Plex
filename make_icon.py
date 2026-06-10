"""Build-time script: generate icon.ico for the ItunesToPlex PyInstaller build.

Draws a 256x256 RGBA image — orange circle with a white music note — then
saves it as a multi-resolution .ico (256, 48, 32, 16 px) using PIL's ICO
plugin, which requires passing each resized frame via the `sizes` kwarg on
the largest image.

Run once: python make_icon.py
"""
from PIL import Image, ImageDraw
import pathlib

BG_COLOR = (255, 130, 0, 255)    # Plex orange
FG_COLOR = (255, 255, 255, 255)  # white
SIZES    = [256, 48, 32, 16]


def _draw_base(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    m   = size // 16

    # Background circle
    d.ellipse([m, m, size - m - 1, size - m - 1], fill=BG_COLOR)

    s = size
    # Note head
    nhw, nhh = int(s * 0.22), int(s * 0.16)
    cx, cy   = int(s * 0.38), int(s * 0.68)
    d.ellipse([cx - nhw, cy - nhh, cx + nhw, cy + nhh], fill=FG_COLOR)

    # Stem
    sw    = max(2, int(s * 0.06))
    sx    = cx + nhw - sw // 2
    sy_top = int(s * 0.30)
    d.rectangle([sx, sy_top, sx + sw, cy], fill=FG_COLOR)

    # Two flags
    fw, fh = int(s * 0.22), int(s * 0.20)
    lw = max(2, sw)
    d.line([(sx + sw, sy_top),
            (sx + sw + fw, sy_top + fh)],
           fill=FG_COLOR, width=lw)
    d.line([(sx + sw, sy_top + int(s * 0.10)),
            (sx + sw + fw, sy_top + int(s * 0.10) + fh)],
           fill=FG_COLOR, width=lw)

    return img


def main():
    out  = pathlib.Path(__file__).parent / "icon.ico"
    base = _draw_base(256)

    # Build each size as a separate RGBA image
    frames = [base.resize((sz, sz), Image.LANCZOS) for sz in SIZES]

    # Pillow ICO: save first frame, embed all sizes
    frames[0].save(
        str(out),
        format="ICO",
        sizes=[(sz, sz) for sz in SIZES],
        append_images=frames[1:],
    )
    print(f"Written: {out}  ({out.stat().st_size:,} bytes, sizes={SIZES})")


if __name__ == "__main__":
    main()
