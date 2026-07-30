#!/usr/bin/env python3
"""Export the two-panel hero as ONE fully-editable SVG (editable gradients, text,
glow, pill, drop-shadows) with the product photos embedded as clean transparent
cutouts. Also drops the two cutout PNGs alongside for Canva. Output -> Desktop."""
import os, base64, io
import numpy as np
from scipy import ndimage
from PIL import Image
from rembg import remove, new_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.expanduser("~/Desktop/EME-hero-editable")
os.makedirs(OUT, exist_ok=True)
SESSION = new_session("isnet-general-use")

def cutout(path, max_h=900):
    src = Image.open(path).convert("RGBA")
    out = remove(src, session=SESSION)
    arr = np.array(out)
    a = arr[..., 3]
    filled = ndimage.binary_fill_holes(a > 128)
    arr[..., 3] = np.where(filled, 255, a).astype(np.uint8)
    res = Image.fromarray(arr, "RGBA")
    b = res.getbbox()
    if b: res = res.crop(b)
    if res.height > max_h:
        s = max_h / res.height
        res = res.resize((int(res.width * s), max_h), Image.LANCZOS)
    return res

def b64(img):
    buf = io.BytesIO(); img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()

# ---- build cutouts ----
print("Cutting out products...")
cooker = cutout("assets/img/beko-kdvc90x-cooker.jpg")
washer = cutout("assets/img/indesit-ima864-mytime-washing-machines.jpg")
cooker.save(os.path.join(OUT, "cooker-cutout.png"))
washer.save(os.path.join(OUT, "washer-cutout.png"))

# ---- layout maths ----
PW, PH = 560, 620          # panel size
GAP = 40
X0, X1 = 20, 20 + PW + GAP # panel x origins
PY = 150                   # panels top
IMG_MAXH, IMG_MAXW = 320, 430
IMG_CY = PY + 372          # product vertical centre inside panel

def place(img, panel_x):
    s = min(IMG_MAXH / img.height, IMG_MAXW / img.width)
    w, h = img.width * s, img.height * s
    x = panel_x + (PW - w) / 2
    y = IMG_CY - h / 2
    return x, y, w, h

cx0, cy0, cw0, ch0 = place(cooker, X0)
cx1, cy1, cw1, ch1 = place(washer, X1)

def panel_svg(pid, px, grad, eyebrow, l1, l2, cta, glow_id, img_b64, ix, iy, iw, ih):
    cxc = px + PW / 2
    return f'''
  <g id="panel-{pid}">
    <rect x="{px}" y="{PY}" width="{PW}" height="{PH}" rx="28" fill="url(#{grad})" filter="url(#panelShadow)"/>
    <ellipse id="glow-{pid}" cx="{cxc:.0f}" cy="{PY+372}" rx="185" ry="150" fill="url(#{glow_id})" filter="url(#softBlur)"/>
    <image href="data:image/png;base64,{img_b64}" xlink:href="data:image/png;base64,{img_b64}"
           x="{ix:.1f}" y="{iy:.1f}" width="{iw:.1f}" height="{ih:.1f}"/>
    <text x="{cxc:.0f}" y="{PY+56}" text-anchor="middle" font-family="Montserrat, Arial, sans-serif" font-weight="700" font-size="13" letter-spacing="2" fill="#5b4a3f">{eyebrow}</text>
    <text x="{cxc:.0f}" y="{PY+104}" text-anchor="middle" font-family="Montserrat, Arial, sans-serif" font-weight="800" font-size="34" fill="#231a14">{l1}</text>
    <text x="{cxc:.0f}" y="{PY+144}" text-anchor="middle" font-family="Montserrat, Arial, sans-serif" font-weight="800" font-size="34" fill="#231a14">{l2}</text>
    <g id="cta-{pid}">
      <rect x="{cxc-118:.0f}" y="{PY+PH-84}" width="236" height="56" rx="28" fill="#ffffff" filter="url(#pillShadow)"/>
      <text x="{cxc:.0f}" y="{PY+PH-48}" text-anchor="middle" font-family="Montserrat, Arial, sans-serif" font-weight="700" font-size="16" fill="#231a14">{cta}</text>
    </g>
  </g>'''

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="1200" height="920" viewBox="0 0 1200 920">
  <!-- ══ Eddie Maguire — two-panel hero · fully editable ══
       Change panel colours: edit the <stop> colours in #gradWarm / #gradCool.
       Change glow: edit #glowWarm / #glowCool colours, or the softBlur amount.
       Shadows: #panelShadow / #pillShadow (feDropShadow stdDeviation/opacity).
       All headlines, eyebrows and buttons are live <text> — edit freely. -->
  <defs>
    <linearGradient id="gradWarm" x1="0" y1="0" x2="0.3" y2="1">
      <stop offset="0%"  stop-color="#FFC79F"/>
      <stop offset="56%" stop-color="#FF9FAE"/>
      <stop offset="100%" stop-color="#FF8FA3"/>
    </linearGradient>
    <linearGradient id="gradCool" x1="0" y1="0" x2="0.3" y2="1">
      <stop offset="0%"  stop-color="#ABE7D6"/>
      <stop offset="58%" stop-color="#82D0DD"/>
      <stop offset="100%" stop-color="#74C7D8"/>
    </linearGradient>
    <radialGradient id="glowWarm"><stop offset="0%" stop-color="#FFE2D2" stop-opacity="0.85"/><stop offset="100%" stop-color="#FFE2D2" stop-opacity="0"/></radialGradient>
    <radialGradient id="glowCool"><stop offset="0%" stop-color="#D6F4F4" stop-opacity="0.85"/><stop offset="100%" stop-color="#D6F4F4" stop-opacity="0"/></radialGradient>
    <filter id="softBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="40"/></filter>
    <filter id="panelShadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="14" stdDeviation="20" flood-color="#504232" flood-opacity="0.14"/></filter>
    <filter id="pillShadow" x="-40%" y="-60%" width="180%" height="220%"><feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#3c2819" flood-opacity="0.20"/></filter>
  </defs>

  <rect id="page-bg" x="0" y="0" width="1200" height="920" fill="#EBE7DF"/>

  <g id="kicker">
    <text x="20" y="70" font-family="Montserrat, Arial, sans-serif" font-weight="700" font-size="14" letter-spacing="2.4" fill="#E8720C">HOME APPLIANCES — DUNDALK</text>
    <text x="18" y="118" font-family="Montserrat, Arial, sans-serif" font-weight="800" font-size="46" fill="#1E1712">Big brands for every home.</text>
  </g>
{panel_svg("cooking", X0, "gradWarm", "COOKING", "The heart of", "the home.", "Shop Cookers →", "glowWarm", b64(cooker), cx0, cy0, cw0, ch0)}
{panel_svg("laundry", X1, "gradCool", "LAUNDRY", "Fresh, sorted.", "Every load.", "Shop Washing →", "glowCool", b64(washer), cx1, cy1, cw1, ch1)}
</svg>'''

path = os.path.join(OUT, "hero.svg")
with open(path, "w") as f: f.write(svg)
print("Wrote:")
print(" ", path, f"({os.path.getsize(path)//1024} KB)")
print(" ", os.path.join(OUT, "cooker-cutout.png"))
print(" ", os.path.join(OUT, "washer-cutout.png"))
