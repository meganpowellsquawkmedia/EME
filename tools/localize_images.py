#!/usr/bin/env python3
"""
Download all product images into the repo so the site is self-contained
(independent of WordPress / external CDNs).

Reads products.json + supplier_products.json, downloads each referenced image
(first 6 per product = what we render), resizes/compresses for web, and writes
content/image_map.json  { original_url: "/assets/img/<hash>.<ext>" }.

build.py's local_img() uses that map and falls back to the original URL for any
image not yet downloaded — so it's safe to run while the build keeps working.

Resumable: re-run to fetch only what's missing.  Read-only on the sources.
Run:  python3 tools/localize_images.py
"""
import json, hashlib, io, urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "content" / "raw"
IMGDIR = ROOT / "assets" / "img"
IMGDIR.mkdir(parents=True, exist_ok=True)
MAP = ROOT / "content" / "image_map.json"
MAXDIM = 1000
UA = "EddieMaguire-imagelocalizer/1.0"

P = json.load(open(RAW / "products.json")) + json.load(open(RAW / "supplier_products.json"))
urls = []
seen = set()
for p in P:
    for i in p.get("images", [])[:6]:
        s = (i.get("src") or "").strip()
        if s.startswith("http") and s not in seen:
            seen.add(s); urls.append(s)

image_map = json.load(open(MAP)) if MAP.exists() else {}

def local_name(url):
    h = hashlib.md5(url.encode()).hexdigest()[:14]
    ext = urlparse(url).path.rsplit(".", 1)[-1].lower()
    if "/" in ext or len(ext) > 4 or not ext.isalnum():
        ext = "jpg"
    return f"{h}.{ext}"

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

total = len(urls); ok = 0; fail = 0
for n, url in enumerate(urls, 1):
    name = local_name(url)
    dest = IMGDIR / name
    rel = f"/assets/img/{name}"
    if dest.exists():
        image_map[url] = rel
        continue
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=30).read()
        wrote = False
        if HAVE_PIL:
            try:
                im = Image.open(io.BytesIO(data))
                im.load()
                if max(im.size) > MAXDIM:
                    im.thumbnail((MAXDIM, MAXDIM), Image.LANCZOS)
                fmt = (im.format or "JPEG").upper()
                if fmt in ("JPEG", "MPO"):
                    im.convert("RGB").save(dest, "JPEG", quality=82, optimize=True)
                elif fmt == "PNG":
                    im.save(dest, "PNG", optimize=True)
                elif fmt == "GIF":
                    im.save(dest)
                elif fmt == "WEBP":
                    im.save(dest, "WEBP", quality=82)
                else:
                    dest.write_bytes(data)  # avif/bmp/etc -> keep raw
                wrote = True
            except Exception:
                pass
        if not wrote:
            dest.write_bytes(data)
        image_map[url] = rel
        ok += 1
        if n % 50 == 0:
            json.dump(image_map, open(MAP, "w"))
            print(f"[{n}/{total}] {ok} ok, {fail} failed", flush=True)
    except Exception as e:
        fail += 1
        print(f"[{n}/{total}] FAIL {url[:70]}: {e}", flush=True)

json.dump(image_map, open(MAP, "w"), indent=0)
print(f"DONE: {ok} downloaded, {fail} failed, {len(image_map)} mapped -> content/image_map.json", flush=True)
