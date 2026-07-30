#!/usr/bin/env python3
"""Cut out a representative product per department for the circular browse row.
Transparent, trimmed, opaque product (no colour bleed). Saved to assets/dept/."""
import os
import numpy as np
from scipy import ndimage
from PIL import Image
from rembg import remove, new_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "dept")
os.makedirs(OUT, exist_ok=True)
SESSION = new_session("isnet-general-use")

ICONS = {
    "cooking":       "assets/img/electrolux-lkr655210x-cooker.jpg",
    "refrigeration": "assets/img/fridge-honfq2t718exk.jpg",
    "laundry":       "assets/img/indesit-ima864-mytime-washing-machines.jpg",
    "dishwashers":   "assets/img/sms2hvw67g.png",
    "mobile-phones": "assets/img/61LFeKye45L._AC_UF1000,1000_QL80_.jpg",
}

def cutout(path, max_side=560):
    src = Image.open(path).convert("RGBA")
    out = remove(src, session=SESSION)
    arr = np.array(out)
    a = arr[..., 3]
    arr[..., 3] = np.where(ndimage.binary_fill_holes(a > 128), 255, a).astype(np.uint8)
    res = Image.fromarray(arr, "RGBA")
    b = res.getbbox()
    if b: res = res.crop(b)
    if max(res.size) > max_side:
        s = max_side / max(res.size)
        res = res.resize((int(res.width * s), int(res.height * s)), Image.LANCZOS)
    return res

for slug, src in ICONS.items():
    img = cutout(src)
    p = os.path.join(OUT, f"{slug}.png")
    img.save(p)
    print(f"  {slug:14} {img.width}x{img.height}")
print("Done.")
