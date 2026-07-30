#!/usr/bin/env python3
"""Generate two Currys-style hero images: a clean product cutout on a transparent
background, floating on the page's gradient panel. No cloud, no contact shadow.
The product is kept FULLY OPAQUE (interior holes filled) so the panel colour can
never show through glass/dark areas — the product is never distorted, only the
surrounding white background is removed."""
import os
import numpy as np
from scipy import ndimage
from PIL import Image, ImageFilter, ImageDraw
from rembg import remove, new_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION = new_session("isnet-general-use")

def cutout(path):
    """Remove the white background but keep the product solid & opaque."""
    src = Image.open(path).convert("RGBA")
    out = remove(src, session=SESSION)          # RGBA, RGB untouched
    arr = np.array(out)
    alpha = arr[..., 3]
    # solid silhouette, then fill any interior holes (oven glass, drum, gaps)
    mask = alpha > 128
    filled = ndimage.binary_fill_holes(mask)
    # interior -> fully opaque; keep the soft anti-aliased outer edge as-is
    arr[..., 3] = np.where(filled, 255, alpha).astype(np.uint8)
    res = Image.fromarray(arr, "RGBA")
    bbox = res.getbbox()
    return res.crop(bbox) if bbox else res

def glow(size, colour):
    """A soft ambient light behind the product — not a shadow."""
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    w, h = size
    ImageDraw.Draw(g).ellipse([w * 0.20, h * 0.14, w * 0.80, h * 0.80],
                              fill=colour + (150,))
    return g.filter(ImageFilter.GaussianBlur(int(w * 0.13)))

def build(product_path, out_name, glow_rgb):
    prod = cutout(product_path)
    CW, CH = 1200, 1120
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))

    target_h = int(CH * 0.74)
    scale = target_h / prod.height
    pw, ph = int(prod.width * scale), target_h
    prod = prod.resize((pw, ph), Image.LANCZOS)
    px, py = (CW - pw) // 2, (CH - ph) // 2

    canvas = Image.alpha_composite(canvas, glow((CW, CH), glow_rgb))
    canvas.alpha_composite(prod, (px, py))

    out = os.path.join(ROOT, "assets", out_name)
    canvas.save(out)
    print(f"  wrote {out_name}  ({canvas.width}x{canvas.height})")

if __name__ == "__main__":
    print("Generating hero art...")
    build("assets/img/beko-kdvc90x-cooker.jpg", "hero-cooker.png",
          glow_rgb=(255, 226, 210))
    build("assets/img/indesit-ima864-mytime-washing-machines.jpg", "hero-washer.png",
          glow_rgb=(214, 244, 244))
    print("Done.")
