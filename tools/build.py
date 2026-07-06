#!/usr/bin/env python3
"""
Static catalogue generator for Eddie Maguire.
Reads content/raw/*.json (snapshot of the WooCommerce site) and writes a fully
static catalogue (no cart/checkout) into the repo, in the dark/orange theme.

Output:
  index.html                      homepage
  category/index.html             all categories
  category/<clean-slug>/index.html   one page per category (product grid)
  product/<slug>/index.html       one page per product (slug kept = no redirect needed)
  content/redirects.csv           old category URL -> new URL (301 map)

Run:  python3 tools/build.py
"""
import json, os, re, html, csv, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW  = ROOT / "content" / "raw"
SITE = "https://eddiemaguire.ie"

# Absolute base for canonical/Open-Graph/sitemap URLs. Must be the *live* origin
# so link previews + crawling work today. When the custom domain is pointed at
# Pages, change LIVE_ORIGIN to https://eddiemaguire.ie and drop BASE_PATH.
_BASE = os.environ.get("BASE_PATH", "").rstrip("/")
LIVE_ORIGIN = "https://meganpowellsquawkmedia.github.io"
SITE_ABS = LIVE_ORIGIN + _BASE
OG_IMAGE = "/assets/og-default.png"

# ---- shop details (from existing index.html / live site) ----
SHOP = {
    "name": "Eddie Maguire",
    "tagline": "Electrical & Furniture",
    "phone_display": "042 933 2043",
    "phone_tel": "042 933 2043".replace(" ", ""),
    "wa": "353899776472",
    "email": "info@eddiemaguire.ie",
    "address": "29 Church St, Dundalk",
    "hours": "Mon–Fri 9am–6pm · Sat 9am–5:30pm",
}

# Known appliance/furniture brands -> detect from product name start.
BRANDS = ["INDESIT","HOTPOINT","BOSCH","SAMSUNG","LG","WHIRLPOOL","BEKO","ZANUSSI",
    "AEG","SIEMENS","HISENSE","CANDY","HOOVER","ELECTROLUX","SHARP","PANASONIC",
    "MIELE","SMEG","NEFF","GORENJE","GRUNDIG","TOSHIBA","DAEWOO","RUSSELL HOBBS",
    "DELONGHI","DE'LONGHI","TEFAL","KENWOOD","DYSON","PHILIPS","BREVILLE","MORPHY RICHARDS",
    "TCL","SONY","JVC","BUSH","CELLINI","BELLING","STOVES","RANGEMASTER","FLAVEL",
    "NORDMENDE","MONTPELLIER","STATESMAN","WHITE KNIGHT","LIEBHERR","FISHER & PAYKEL",
    "VENINI","BLAUPUNKT","ELECTRIQ","COOKOLOGY"]
BRANDS.sort(key=len, reverse=True)  # match longest first

# Manual clean-slug overrides for the worst offenders (name/slug mismatches).
SLUG_OVERRIDES = {
    "integrated-refrigeration": "american-fridge-freezers",          # name "American"
    "integrated-refrigeration-home-appliances": "integrated-fridge-freezers",  # name "Integrated"
    "integrated": "integrated-dishwashers",                          # under Dishwashers
    "freestanding": "freestanding-dishwashers",                      # under Dishwashers
}

def slugify(s):
    s = html.unescape(s).lower()
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)

def esc(s):
    return html.escape(s or "", quote=True)

def detect_brand(name):
    up = html.unescape(name).upper()
    for b in BRANDS:
        if up.startswith(b + " ") or up == b:
            return b.title() if not b.isupper() or " " in b else b
    return ""

# Canonical brand casing so the same brand never appears twice (e.g. "NORDMENDE"
# from name-detection vs "Nordmende" from the stock take). Title-case by default,
# with exceptions for acronym brands.
BRAND_KEEP = {"lg": "LG", "tcl": "TCL", "jvc": "JVC", "aeg": "AEG", "jbl": "JBL",
              "hp": "HP", "rca": "RCA", "tp-link": "TP-Link", "akai": "Akai"}
def canon_brand(b):
    if not b: return ""
    k = re.sub(r"\s+", " ", str(b).strip()).lower()
    return BRAND_KEEP.get(k, str(b).strip().title())

def brand_of(p):
    """Best brand for a product: explicit supplier/stock 'brands' field, else detect from name.
    Always returned in a single canonical casing so filters don't double-up."""
    bs = p.get("brands") or []
    raw = html.unescape(str(bs[0]).strip()) if (bs and str(bs[0]).strip()) else detect_brand(p["name"])
    return canon_brand(raw)

def colour_of(name):
    """Detect a product colour from its name -> Black / White / Silver (or '')."""
    n = html.unescape(name or "").lower()
    if "black" in n or "graphite" in n or "anthracite" in n: return "Black"
    if "white" in n: return "White"
    if any(k in n for k in ("silver", "stainless", "inox", "s/steel", "brushed steel", "steel", "chrome")): return "Silver"
    return ""

def money(v):
    try:
        f = float(v)
        return f"€{f:,.0f}" if f == int(f) else f"€{f:,.2f}"
    except (TypeError, ValueError):
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# Load data
P = json.load(open(RAW / "products.json"))
C = json.load(open(RAW / "product_categories.json"))
PAGES = json.load(open(RAW / "pages.json"))

# Merge imported supplier (dropship) products + any new categories, if present.
_sp = RAW / "supplier_products.json"
_sc = RAW / "supplier_categories.json"
if _sc.exists():
    C += json.load(open(_sc))
if _sp.exists():
    P += json.load(open(_sp))
_fp = RAW / "fridge_products.json"          # rebuilt from EasyRetail stock take + dealer images
if _fp.exists():
    P += json.load(open(_fp))
_mp = RAW / "manual_products.json"          # hand-added stock (new lines, awaiting real photo/price)
if _mp.exists():
    P += json.load(open(_mp))

# Removed/cleared products. Optional CSV (product_id,...) — these are dropped
# from the whole catalogue. Used to wipe a category for a fresh rebuild.
REMOVED = set()
_rmf = ROOT / "content" / "removed_products.csv"
if _rmf.exists():
    for _r in csv.DictReader(open(_rmf)):
        if _r.get("product_id"):
            REMOVED.add(str(_r["product_id"]))
if REMOVED:
    P = [p for p in P if str(p["id"]) not in REMOVED]

# Quality gate: omit any product with no photo — no image, not shown on the site.
_before = len(P)
P = [p for p in P if p.get("images") and str((p["images"][0] or {}).get("src", "")).strip()]
_omitted_noimg = _before - len(P)

# ── Category structure fixes (clean up the mis-nested WooCommerce tree) ──
# Collapse ~47 scattered top-level departments into 7 clean ones by re-parenting
# the strays, renaming the ALL-CAPS supplier imports, and hiding utility buckets.
PARENT_FIXES = {
    # → Furniture (717)
    33: 717, 1099: 717, 1094: 717, 7: 717, 670: 717, 34: 717, 1107: 717,
    58: 717, 66: 717, 59: 717, 667: 717, 71: 717, 85: 717, 83: 717, 84: 717,
    86: 717, 1097: 717, 82: 717, 61: 717, 72: 717, 20: 717,
    # → TVs & Audio (877)
    918: 877, 923: 877, 878: 877, 858: 877, 940: 877, 935: 877, 852: 877,
    686: 877, 1491: 877,
    # → Small Appliances (718)
    985: 718, 1024: 718, 1036: 718, 1451: 718, 1405: 718, 969: 718,
    # → Technology (690): promote it to top-level, then nest tech under it
    690: 0, 727: 690, 691: 690, 990001: 690, 695: 690, 1480: 690, 990002: 690,
    # → Garden & DIY (1419)
    1525: 1419, 1527: 1419, 1528: 1419, 1529: 1419,
    # → Home Appliances (696)
    1453: 696, 1578: 696,
}
NAME_FIXES = {
    766: "Landline & Cordless Phones", 695: "Dash Cams",
    877: "TVs & Audio", 918: "Hi-Fi Systems", 923: "Radios", 878: "Headphones",
    858: "Audio & Radio", 940: "Bluetooth Speakers", 935: "Clock Radios",
    985: "Ironing", 1024: "Juicers", 1036: "Food Preparation", 969: "Personal Care",
    72: "Mattresses", 1578: "Washing Machines", 686: "TVs", 1419: "Garden & DIY",
}
# Utility/meta buckets hidden from the department menus (pages still exist).
HIDDEN_TOP = {37, 740, 62, 1016}   # All Products, Brands, Sales, duplicate COOKING
for c in C:
    if c["id"] in PARENT_FIXES: c["parent"] = PARENT_FIXES[c["id"]]
    if c["id"] in NAME_FIXES:   c["name"]   = NAME_FIXES[c["id"]]

# Per-product category overrides (recategorisation). product_id -> category_id.
# Written by tools/recategorise_phones.py; replaces a product's categories.
CATEGORY_OVERRIDES = {}
_cof = ROOT / "content" / "category_overrides.csv"
if _cof.exists():
    for _r in csv.DictReader(open(_cof)):
        if _r.get("category_id"):
            CATEGORY_OVERRIDES[str(_r["product_id"])] = int(_r["category_id"])

# Manual price overrides. Optional CSV: product_id,price (extra columns ignored).
# Lets you set your own price for any product without editing the raw WP/supplier
# data — keeps source data canonical and changes reversible. Leave file absent to
# use each product's own price (WP price, or supplier RRP).
OVERRIDES = {}
_ovf = ROOT / "content" / "price_overrides.csv"
if _ovf.exists():
    for _r in csv.DictReader(open(_ovf)):
        if _r.get("price"):
            OVERRIDES[str(_r["product_id"])] = _r["price"]

# Category image overrides: category slug (clean or original) -> image path/URL.
# Lets us set a custom hero/card image for any category (e.g. phones -> iPhone).
CAT_IMAGES = {}
_cif = ROOT / "content" / "category_images.csv"
if _cif.exists():
    for _r in csv.DictReader(open(_cif)):
        if _r.get("image"):
            CAT_IMAGES[_r["slug"].strip()] = _r["image"].strip()

# Local image map (downloaded copies). url -> /assets/img/xxx. Falls back to the
# original URL for anything not yet localized, so it's safe during a partial run.
IMAGE_MAP = {}
_imf = ROOT / "content" / "image_map.json"
if _imf.exists():
    try: IMAGE_MAP = json.load(open(_imf))
    except Exception: IMAGE_MAP = {}

def local_img(url):
    return IMAGE_MAP.get(url, url)

# Asset cache-busting: append a content hash so updated CSS/JS always reloads.
def _asset_ver(rel):
    import hashlib
    f = ROOT / rel
    try: return hashlib.md5(f.read_bytes()).hexdigest()[:8]
    except OSError: return "1"
CSS_VER = _asset_ver("assets/site.css")
JS_VER = _asset_ver("assets/filters.js")

def eff_price(p):
    """Effective price fields, applying any override (override = flat price, no sale)."""
    ov = OVERRIDES.get(str(p["id"]))
    if ov:
        return ov, ov, ""          # price, regular, sale
    return p.get("price"), p.get("regular_price"), p.get("sale_price")

byid = {c["id"]: c for c in C}
children = {}
for c in C:
    children.setdefault(c["parent"], []).append(c)

# Apply per-product category overrides (replace a product's categories).
for p in P:
    ov = CATEGORY_OVERRIDES.get(str(p["id"]))
    if ov is not None and ov in byid:
        p["categories"] = [{"id": ov, "name": html.unescape(byid[ov]["name"])}]

# Assign clean unique slugs to every category
name_counts = {}
for c in C:
    name_counts[slugify(c["name"])] = name_counts.get(slugify(c["name"]), 0) + 1

clean = {}
used = set()
for c in C:
    if c["slug"] in SLUG_OVERRIDES:
        cs = SLUG_OVERRIDES[c["slug"]]
    else:
        base = slugify(c["name"])
        # disambiguate duplicate names by prefixing parent
        if name_counts[base] > 1 and c["parent"] in byid:
            cs = slugify(byid[c["parent"]]["name"] + "-" + c["name"])
        else:
            cs = base
    # ensure global uniqueness
    final, n = cs, 2
    while final in used:
        final = f"{cs}-{n}"; n += 1
    used.add(final)
    clean[c["id"]] = final

def cat_url(cid): return f"/category/{clean[cid]}/"
def crumb_chain(cid):
    chain = []
    while cid and cid in byid:
        chain.append(byid[cid]); cid = byid[cid]["parent"]
    return list(reversed(chain))

# index products by category id
prods_in = {}
for p in P:
    for c in p.get("categories", []):
        prods_in.setdefault(c["id"], []).append(p)

# real product count per category INCLUDING descendants (computed from merged P,
# not the stale WP `count` field). Used for display, sorting and empty-hiding.
def _descendants(cid):
    out = []
    for ch in children.get(cid, []):
        out.append(ch["id"]); out += _descendants(ch["id"])
    return out
cat_total = {}
for c in C:
    ids = [c["id"]] + _descendants(c["id"])
    seen = set()
    for i in ids:
        for p in prods_in.get(i, []):
            seen.add(p["id"])
    cat_total[c["id"]] = len(seen)

# ─────────────────────────────────────────────────────────────────────────────
# HTML partials
def head(title, desc, css_path="/assets/site.css", path="/", image=None, jsonld=None):
    canon = SITE_ABS + path
    img = image or OG_IMAGE
    if img.startswith("/"): img = SITE_ABS + img          # absolutise local images
    ld = f'\n<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canon)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(SHOP['name'])} — {esc(SHOP['tagline'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canon)}">
<meta property="og:image" content="{esc(img)}">
<meta property="og:locale" content="en_IE">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(img)}">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/favicon.png" sizes="32x32">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800;900&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{css_path}?v={CSS_VER}">{ld}
</head>
<body>"""

def localbusiness_ld():
    return json.dumps({
        "@context": "https://schema.org", "@type": "HomeGoodsStore",
        "name": SHOP["name"], "image": SITE_ABS + OG_IMAGE,
        "@id": SITE_ABS + "/", "url": SITE_ABS + "/",
        "telephone": SHOP["phone_display"], "email": SHOP["email"],
        "address": {"@type": "PostalAddress", "streetAddress": "29 Church St",
                    "addressLocality": "Dundalk", "addressRegion": "Co. Louth",
                    "postalCode": "", "addressCountry": "IE"},
        "openingHoursSpecification": [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday"], "opens": "09:00", "closes": "18:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": "Saturday", "opens": "09:00", "closes": "17:30"},
        ],
        "priceRange": "€€",
        "sameAs": [f"https://wa.me/{SHOP['wa']}"],
    }, ensure_ascii=False)

def product_ld(p, name, abs_img, price_v):
    data = {"@context": "https://schema.org", "@type": "Product", "name": name,
            "image": abs_img, "sku": str(p.get("sku") or p["id"]),
            "url": SITE_ABS + f"/product/{p['slug']}/"}
    b = detect_brand(p["name"])
    if b: data["brand"] = {"@type": "Brand", "name": b}
    if price_v:
        data["offers"] = {"@type": "Offer", "priceCurrency": "EUR", "price": str(price_v),
                          "availability": "https://schema.org/InStock",
                          "url": SITE_ABS + f"/product/{p['slug']}/",
                          "seller": {"@type": "Organization", "name": SHOP["name"]}}
    return json.dumps(data, ensure_ascii=False)

WA_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.125.558 4.122 1.533 5.856L.054 23.5l5.823-1.454A11.934 11.934 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.885 0-3.651-.518-5.166-1.42l-.371-.22-3.453.863.927-3.384-.242-.389A9.96 9.96 0 012 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/></svg>'

def header():
    return f"""<header>
  <a href="/" class="logo">
    <div class="logo-text"><span class="name">{SHOP['name']}</span><span class="sub">{SHOP['tagline']}</span></div>
  </a>
  <nav>
    <a href="/category/">Shop</a>
    <a href="/about-us/">About</a>
    <a href="/contact-us/">Contact</a>
    <a href="https://wa.me/{SHOP['wa']}" class="nav-cta">{WA_SVG} Enquire</a>
  </nav>
  <div class="hamburger" onclick="this.closest('header').classList.toggle('menu-open')" aria-label="Menu"><span></span><span></span><span></span></div>
</header>"""

def footer():
    tops = sorted([c for c in children.get(0, []) if cat_total[c["id"]] and c["id"] not in HIDDEN_TOP], key=lambda x: -cat_total[x["id"]])[:6]
    shoplinks = "".join(f'<li><a href="{cat_url(c["id"])}">{esc(html.unescape(c["name"]))}</a></li>' for c in tops)
    return f"""<footer>
  <div class="footer-top">
    <div class="footer-brand">
      <a href="/" class="logo"><div class="logo-text"><span class="name">{SHOP['name']}</span><span class="sub">{SHOP['tagline']}</span></div></a>
      <p>Your local electrical &amp; furniture store in Dundalk. Family run, community focused, and always happy to help. Browse online, buy in store.</p>
    </div>
    <div class="footer-col"><h4>Shop</h4><ul>{shoplinks}<li><a href="/category/">All categories</a></li></ul></div>
    <div class="footer-col"><h4>Company</h4><ul>
      <li><a href="/about-us/">About Us</a></li>
      <li><a href="/contact-us/">Contact</a></li>
      <li><a href="/delivery-returns/">Delivery</a></li>
      <li><a href="/returns-replacements/">Returns</a></li>
      <li><a href="/terms-and-conditions/">Terms &amp; Conditions</a></li>
      <li><a href="/privacy-policy/">Privacy Policy</a></li>
    </ul></div>
    <div class="footer-col"><h4>Visit Us</h4><ul>
      <li><a href="https://maps.google.com/?q={esc(SHOP['address'])}">{esc(SHOP['address'])}</a></li>
      <li><a href="tel:{SHOP['phone_tel']}">{SHOP['phone_display']}</a></li>
      <li><a href="mailto:{SHOP['email']}">{SHOP['email']}</a></li>
      <li style="margin-top:12px;color:var(--orange)">{SHOP['hours']}</li>
    </ul></div>
  </div>
  <div class="footer-bottom">
    <p>© 2026 {SHOP['name']} {SHOP['tagline']}. All rights reserved.</p>
    <p>Made with <span>♥</span> in Dundalk</p>
  </div>
</footer>
</body></html>"""

def product_card(p):
    img = local_img(p["images"][0]["src"]) if p.get("images") else ""
    brand = brand_of(p)
    name = html.unescape(p["name"])
    if brand and name.upper().startswith(brand.upper()):
        name = name[len(brand):].strip()
    price_v, reg, sale = eff_price(p)
    price = money(price_v)
    try: pnum = float(price_v)
    except (TypeError, ValueError): pnum = ""
    on_sale = sale and reg and sale != reg
    was = f'<span class="was">{money(reg)}</span>' if on_sale else ""
    badge = '<span class="sale-badge">Sale</span>' if on_sale else ""
    price_disp = f"{price} {was}" if price else '<span class="poa">Price on request</span>'
    colour = colour_of(p["name"])
    return f"""<a href="/product/{esc(p['slug'])}/" class="product-card" data-brand="{esc(brand.lower())}" data-colour="{esc(colour.lower())}" data-price="{pnum}" data-name="{esc(name.lower())}">
  <div class="product-thumb-wrap">{badge}<div class="product-thumb"><img src="{esc(img)}" alt="{esc(name)}" loading="lazy"></div></div>
  <div class="product-info">
    {f'<div class="product-brand">{esc(brand)}</div>' if brand else ''}
    <div class="product-name">{esc(name)}</div>
    <div class="product-price-row"><span class="product-price">{price_disp}</span></div>
  </div>
</a>"""

def write(path, content):
    full = ROOT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT PAGES
def build_products():
    for p in P:
        cats = p.get("categories", [])
        # deepest category for breadcrumb
        chain = []
        if cats:
            deepest = max(cats, key=lambda c: len(crumb_chain(c["id"])))
            chain = crumb_chain(deepest["id"])
        crumbs = '<a href="/">Home</a><span class="sep">/</span><a href="/category/">Shop</a>'
        for c in chain:
            crumbs += f'<span class="sep">/</span><a href="{cat_url(c["id"])}">{esc(html.unescape(c["name"]))}</a>'
        crumbs += f'<span class="sep">/</span><span class="current">{esc(html.unescape(p["name"])[:40])}</span>'

        brand = detect_brand(p["name"])
        imgs = p.get("images", [])
        main = local_img(imgs[0]["src"]) if imgs else ""
        thumbs = "".join(f'<img src="{esc(local_img(i["src"]))}" alt="" onclick="document.getElementById(\'pdpmain\').src=this.src">' for i in imgs[:6])
        price_v, reg, sale = eff_price(p)
        price = money(price_v)
        on_sale = sale and reg and sale != reg
        was = f'<span class="was">{money(reg)}</span>' if on_sale else ""
        is_supplier = p.get("_source") == "supplier"
        stat = p.get("stock_status")
        if is_supplier:
            # dropship line: ordered in, not in-store stock
            if stat == "instock":
                stock_html = '<span class="pdp-stock"><span class="dot"></span>In stock — available to order</span>'
            elif stat == "onbackorder":
                stock_html = '<span class="pdp-stock"><span class="dot"></span>Available to order — incoming stock</span>'
            else:
                stock_html = '<span class="pdp-stock out"><span class="dot"></span>Please enquire for availability</span>'
            note = (f'🛈 This item is available to order. Message or call us and we\'ll arrange it for you '
                    f'— collect in store at {esc(SHOP["address"])} or ask about delivery.')
        else:
            stock_html = ('<span class="pdp-stock"><span class="dot"></span>In stock — available in store</span>'
                          if stat == "instock" else '<span class="pdp-stock out"><span class="dot"></span>Please enquire for availability</span>')
            note = f'🛈 This is our online catalogue. To buy, call us or pop into the store at {esc(SHOP["address"])} — we\'ll sort you out.'
        desc = p.get("description") or p.get("short_description") or ""
        wa_text = f"Hi, I'm interested in: {html.unescape(p['name'])} ({SITE}/product/{p['slug']}/)"
        wa_link = "https://wa.me/" + SHOP["wa"] + "?text=" + re.sub(r"\s+", "%20", wa_text)

        body = f"""{header()}
<div class="page-body">
<div class="crumbs">{crumbs}</div>
<div class="pdp">
  <div>
    <div class="pdp-gallery"><img id="pdpmain" src="{esc(main)}" alt="{esc(html.unescape(p['name']))}"></div>
    {f'<div class="pdp-thumbs">{thumbs}</div>' if len(imgs) > 1 else ''}
  </div>
  <div>
    {f'<div class="pdp-brand">{esc(brand)}</div>' if brand else ''}
    <h1>{esc(html.unescape(p['name']))}</h1>
    <div class="pdp-price">{f'<span class="now">{price}</span> {was}' if price else '<span class="now poa-now">Price on request</span>'}</div>
    {stock_html}
    <div class="pdp-actions">
      <a href="{wa_link}" class="btn-primary">{WA_SVG} Enquire on WhatsApp</a>
      <a href="tel:{SHOP['phone_tel']}" class="btn-secondary">Call {SHOP['phone_display']} →</a>
    </div>
    <p class="note-instore">{note}</p>
    <div class="pdp-desc">{desc}</div>
  </div>
</div>
</div>
{footer()}"""
        abs_img = (SITE_ABS + main) if main.startswith("/") else main
        page = head(f"{html.unescape(p['name'])} | {SHOP['name']}",
                    re.sub('<[^<]+?>', '', html.unescape(p.get('short_description') or p['name']))[:155],
                    path=f"/product/{p['slug']}/", image=abs_img,
                    jsonld=product_ld(p, html.unescape(p['name']), abs_img, price_v)) + body
        write(f"product/{p['slug']}/index.html", page)
    print(f"  products: {len(P)} pages")

# CATEGORY PAGES
def build_categories():
    for c in C:
        prods = prods_in.get(c["id"], [])
        # include products from descendant categories too
        def descendants(cid):
            out = []
            for ch in children.get(cid, []):
                out.append(ch["id"]); out += descendants(ch["id"])
            return out
        seen = {p["id"] for p in prods}
        for d in descendants(c["id"]):
            for p in prods_in.get(d, []):
                if p["id"] not in seen:
                    prods.append(p); seen.add(p["id"])
        prods.sort(key=lambda p: (p.get("stock_status") != "instock", html.unescape(p["name"])))

        chain = crumb_chain(c["id"])
        crumbs = '<a href="/">Home</a><span class="sep">/</span><a href="/category/">Shop</a>'
        for cc in chain[:-1]:
            crumbs += f'<span class="sep">/</span><a href="{cat_url(cc["id"])}">{esc(html.unescape(cc["name"]))}</a>'
        crumbs += f'<span class="sep">/</span><span class="current">{esc(html.unescape(c["name"]))}</span>'

        subcats = sorted([s for s in children.get(c["id"], []) if cat_total[s["id"]]], key=lambda x: -cat_total[x["id"]])
        subnav = ""
        if subcats:
            chips = "".join(f'<a href="{cat_url(s["id"])}" class="btn-secondary" style="font-size:13px">{esc(html.unescape(s["name"]))}</a>' for s in subcats)
            subnav = f'<div style="display:flex;flex-wrap:wrap;gap:14px;padding:8px 48px 0">{chips}</div>'

        grid = "".join(product_card(p) for p in prods) or '<p style="color:var(--muted);padding:0 48px">No products in this category yet.</p>'
        cname = esc(html.unescape(c["name"]))
        ccount = f"{len(prods)} product{'s' if len(prods)!=1 else ''}"

        # filter bar (client-side): brand chips + price min/max + sort
        filterbar = ""
        if len(prods) >= 4:
            brands_in = sorted({brand_of(p) for p in prods if brand_of(p)}, key=str.lower)
            nums = []
            for p in prods:
                try: nums.append(float(eff_price(p)[0]))
                except (TypeError, ValueError): pass
            pmin = int(min(nums)) if nums else 0
            pmax = int(max(nums)) + 1 if nums else 0
            brand_block = ""
            if len(brands_in) >= 2:
                chips_html = "".join(f'<button type="button" class="brand-chip" data-b="{esc(b.lower())}">{esc(b)}</button>' for b in brands_in)
                brand_block = ('<div class="fdrop"><button type="button" class="fdrop-btn">Brand'
                               '<span class="fdrop-n" data-count="b"></span><span class="caret">▾</span></button>'
                               f'<div class="fdrop-panel"><div class="brand-chips">{chips_html}</div></div></div>')
            present_cols = {colour_of(p["name"]) for p in prods}
            colours_in = [col for col in ("Black", "White", "Silver") if col in present_cols]
            colour_block = ""
            if len(colours_in) >= 2:
                cchips = "".join(f'<button type="button" class="brand-chip" data-c="{col.lower()}">{col}</button>' for col in colours_in)
                colour_block = ('<div class="fdrop"><button type="button" class="fdrop-btn">Colour'
                                '<span class="fdrop-n" data-count="c"></span><span class="caret">▾</span></button>'
                                f'<div class="fdrop-panel"><div class="brand-chips">{cchips}</div></div></div>')
            filterbar = f'''<div class="filters">
  {brand_block}
  {colour_block}
  <div class="fdrop"><button type="button" class="fdrop-btn">Price<span class="caret">▾</span></button>
    <div class="fdrop-panel price-panel"><input type="number" class="f-price" id="fmin" placeholder="{pmin}" min="0"><span class="f-dash">–</span><input type="number" class="f-price" id="fmax" placeholder="{pmax}" min="0"></div></div>
  <select id="fsort" class="fsort-inline"><option value="">Sort: Featured</option><option value="asc">Price: low to high</option><option value="desc">Price: high to low</option><option value="az">Name: A–Z</option></select>
  <button type="button" id="fclear" class="f-clear">Clear</button>
  <span class="f-count" id="fcount"></span>
</div>'''
        img_ov = CAT_IMAGES.get(clean[c["id"]]) or CAT_IMAGES.get(c["slug"])
        if img_ov:
            head_block = (f'<div class="cat-hero"><div class="cat-hero-bg" style="background-image:url(\'{esc(img_ov)}\')"></div>'
                          f'<div class="cat-hero-overlay"></div>'
                          f'<div class="cat-hero-content"><h1>{cname}</h1><div class="count">{ccount}</div></div></div>')
        else:
            head_block = f'<div class="page-head"><h1>{cname}</h1><div class="count">{ccount}</div></div>'
        body = f"""{header()}
<div class="page-body">
<div class="crumbs">{crumbs}</div>
{head_block}
{subnav}
{filterbar}
<div class="product-grid" id="grid">{grid}</div>
</div>
<script src="/assets/filters.js?v={JS_VER}" defer></script>
{footer()}"""
        page = head(f"{html.unescape(c['name'])} | {SHOP['name']}",
                    f"Browse {html.unescape(c['name'])} at {SHOP['name']}, Dundalk. {len(prods)} products. Buy in store.",
                    path=cat_url(c["id"])) + body
        write(f"category/{clean[c['id']]}/index.html", page)
    print(f"  categories: {len(C)} pages")

# CATEGORY INDEX
def build_category_index():
    tops = sorted([c for c in children.get(0, []) if cat_total[c["id"]] and c["id"] not in HIDDEN_TOP], key=lambda x: -cat_total[x["id"]])
    chips = ""
    for t in tops:
        chips += f"""<a href="{cat_url(t['id'])}" class="cat-chip">
  <h3>{esc(html.unescape(t['name']))}</h3>
  <div class="sub">{cat_total[t['id']]} products</div>
</a>"""
    body = f"""{header()}
<div class="page-body">
<div class="crumbs"><a href="/">Home</a><span class="sep">/</span><span class="current">Shop</span></div>
<div class="page-head"><h1>Shop by category</h1><div class="count">{len(P)} products across {len(C)} categories</div></div>
<div class="cat-chip-grid">{chips}</div>
</div>
{footer()}"""
    write("category/index.html", head(f"Shop | {SHOP['name']}", f"Browse all categories at {SHOP['name']}, Dundalk.", path="/category/") + body)
    print("  category index: 1 page")

# HOMEPAGE
def build_home():
    tops = sorted([c for c in children.get(0, []) if cat_total[c["id"]] and c["id"] not in HIDDEN_TOP], key=lambda x: -cat_total[x["id"]])[:6]
    cards = ""
    for i, t in enumerate(tops):
        img = CAT_IMAGES.get(clean[t["id"]]) or CAT_IMAGES.get(t["slug"]) or ""
        if not img:
            for p in prods_in.get(t["id"], []) or sum((prods_in.get(d["id"], []) for d in children.get(t["id"], [])), []):
                if p.get("images"): img = local_img(p["images"][0]["src"]); break
        wide = " wide" if i in (0, 5) else ""
        subs = sorted([s for s in children.get(t["id"], []) if cat_total[s["id"]]], key=lambda x: -cat_total[x["id"]])[:1]
        tag = html.unescape(subs[0]["name"]) if subs else f"{cat_total[t['id']]} products"
        cards += f"""<a href="{cat_url(t['id'])}" class="cat-card{wide}">
  <div class="cat-card-bg" style="background-image:url('{esc(img)}')"></div>
  <div class="cat-card-overlay"></div>
  <div class="cat-card-content"><span class="cat-card-tag">{esc(tag)}</span><div class="cat-card-title">{esc(html.unescape(t['name']))}</div></div>
  <div class="cat-card-arrow">→</div>
</a>"""
    body = f"""{header()}
<section class="phero">
  <div class="phero-inner">
    <div class="phero-text">
      <div class="hero-eyebrow">Electrical &amp; Furniture — Dundalk</div>
      <h1>Everything<br>for your <span>home.</span></h1>
      <p>From the latest tech to furniture for every room — browse the full range online, then call in or message us in store.</p>
      <div class="hero-actions">
        <a href="/category/" class="btn-primary">Browse the range →</a>
        <a href="https://wa.me/{SHOP['wa']}" class="btn-secondary">WhatsApp Us →</a>
      </div>
    </div>
    <div class="phero-img"><div class="phero-img-glow"></div><img src="/assets/hero-phone.png" alt="iPhone 17 Pro Max"></div>
  </div>
</section>
<section class="categories" id="categories">
  <div class="categories-header">
    <div><div class="section-label">What we stock</div><h2 class="section-title">Browse<br>by category</h2></div>
    <a href="/category/" class="btn-secondary">View all →</a>
  </div>
  <div class="categories-grid">{cards}</div>
</section>
<div class="whatsapp-strip">
  <div><h2>Not sure what you're looking for?</h2><p>Message us on WhatsApp — we're happy to help you find the right product.</p></div>
  <a href="https://wa.me/{SHOP['wa']}" class="btn-whatsapp">{WA_SVG} Message Us on WhatsApp</a>
</div>
<section class="about" id="about">
  <div>
    <div class="section-label">Who we are</div>
    <h2 class="section-title">A family<br>store, built<br>on trust.</h2>
    <div style="margin-top:32px">
      <p>Eddie Maguire has been serving the Dundalk community for years, offering a carefully chosen range of electrical, appliances and furniture for every home and budget.</p>
      <p>We're not a faceless website. We're a real shop, with real people who know their products inside out. Come in and browse, or get in touch — we'll point you in the right direction.</p>
    </div>
    <div class="about-stats">
      <div class="stat"><div class="stat-num">{len(P)}+</div><div class="stat-label">Products in store</div></div>
      <div class="stat"><div class="stat-num">100%</div><div class="stat-label">Irish owned</div></div>
      <div class="stat"><div class="stat-num">30+</div><div class="stat-label">Years in business</div></div>
      <div class="stat"><div class="stat-num">1</div><div class="stat-label">Town, Dundalk</div></div>
    </div>
  </div>
  <div class="about-image">
    <img src="https://images.unsplash.com/photo-1604014237800-1c9102c219da?w=800&auto=format&fit=crop" alt="{SHOP['name']} store interior">
    <div class="about-image-badge">Est. in Dundalk</div>
  </div>
</section>
{footer()}"""
    write("index.html", head(f"{SHOP['name']} — {SHOP['tagline']} | Dundalk",
        "Electrical, appliances & furniture in Dundalk. Browse our full range online, buy in store. " + str(len(P)) + " products.",
        path="/", jsonld=localbusiness_ld()) + body)
    print("  homepage: 1 page")

# CONTENT PAGES (About, Delivery, Returns, Terms) + bespoke Contact
def sanitize(content):
    c = content
    c = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', c, flags=re.S | re.I)  # drop scripts/styles
    c = re.sub(r'\[/?[^\]]+\]', '', c)            # drop WP/VC shortcodes
    c = re.sub(r'<!--.*?-->', '', c, flags=re.S)  # drop block comments
    # strip wp/woo/form remnants
    c = re.sub(r'<form[^>]*>.*?</form>', '', c, flags=re.S | re.I)
    c = re.sub(r'\son\w+="[^"]*"', '', c)          # inline event handlers
    c = re.sub(r'\sclass="[^"]*"', '', c)          # WP classes (we restyle via .prose)
    c = re.sub(r'\sstyle="[^"]*"', '', c)
    return c.strip()

def render_prose_page(slug, title, content_html, desc):
    body = f"""{header()}
<div class="page-body">
<div class="crumbs"><a href="/">Home</a><span class="sep">/</span><span class="current">{esc(title)}</span></div>
<div class="page-head"><h1>{esc(title)}</h1></div>
<div class="prose-wrap"><div class="prose">{content_html}</div></div>
</div>
{footer()}"""
    write(f"{slug}/index.html", head(f"{title} | {SHOP['name']}", desc, path=f"/{slug}/") + body)

def build_contact():
    maps = f"https://www.google.com/maps?q={esc(SHOP['address'])}&output=embed"
    body = f"""{header()}
<div class="page-body">
<div class="crumbs"><a href="/">Home</a><span class="sep">/</span><span class="current">Contact</span></div>
<div class="page-head"><h1>Get in touch</h1><div class="count">We're here to help — call in, call us, or message us on WhatsApp.</div></div>
<div class="contact-grid">
  <div class="contact-block">
    <div class="contact-row"><div class="ico">📍</div><div><div class="lbl">Visit the store</div><div class="val"><a href="https://maps.google.com/?q={esc(SHOP['address'])}">{esc(SHOP['address'])}</a></div></div></div>
    <div class="contact-row"><div class="ico">📞</div><div><div class="lbl">Call us</div><div class="val"><a href="tel:{SHOP['phone_tel']}">{SHOP['phone_display']}</a></div></div></div>
    <div class="contact-row"><div class="ico">✉️</div><div><div class="lbl">Email</div><div class="val"><a href="mailto:{SHOP['email']}">{SHOP['email']}</a></div></div></div>
    <div class="contact-row"><div class="ico">🕑</div><div><div class="lbl">Opening hours</div><div class="val">{SHOP['hours']}<br>Sun: Closed</div></div></div>
    <div class="pdp-actions" style="margin-top:8px">
      <a href="https://wa.me/{SHOP['wa']}" class="btn-primary">{WA_SVG} WhatsApp Us</a>
      <a href="tel:{SHOP['phone_tel']}" class="btn-secondary">Call {SHOP['phone_display']} →</a>
    </div>
  </div>
  <iframe class="contact-map" src="{maps}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" title="Map to {esc(SHOP['name'])}"></iframe>
</div>
</div>
{footer()}"""
    write("contact-us/index.html", head(f"Contact | {SHOP['name']}",
        f"Contact {SHOP['name']}, {SHOP['address']}. Call {SHOP['phone_display']} or message us on WhatsApp.",
        path="/contact-us/", jsonld=localbusiness_ld()) + body)

def build_pages():
    by_slug = {p["slug"]: p for p in PAGES}
    # prose pages rendered straight from WP content (skip empty Privacy, commerce pages, Home)
    prose = ["about-us", "delivery-returns", "returns-replacements", "terms-and-conditions"]
    n = 0
    for slug in prose:
        p = by_slug.get(slug)
        if not p:
            continue
        raw = p["content"]["rendered"]
        clean = sanitize(raw)
        if not re.sub(r"<[^>]+>", "", clean).strip():
            continue  # skip empty
        title = html.unescape(p["title"]["rendered"])
        desc = re.sub(r"<[^>]+>", "", html.unescape(raw))[:155].strip()
        render_prose_page(slug, title, clean, desc or title)
        n += 1
    build_contact(); n += 1
    # local legal/info pages from content/legal/*.html (e.g. privacy-policy)
    legal_dir = ROOT / "content" / "legal"
    if legal_dir.exists():
        for f in sorted(legal_dir.glob("*.html")):
            slug = f.stem
            title = slug.replace("-", " ").title().replace("And", "and")
            content_html = f.read_text(encoding="utf-8")
            desc = re.sub(r"<[^>]+>", " ", content_html)
            desc = re.sub(r"\s+", " ", desc).strip()[:155]
            render_prose_page(slug, title, content_html, desc or title)
            n += 1
    print(f"  content pages: {n} pages (about, delivery, returns, terms, contact, legal)")

# REDIRECT STUBS (old WooCommerce category url -> new)
# GitHub Pages can't do server-side 301s, so we emit a static stub at each old
# path that instantly forwards to the new URL. Google treats an instant
# meta-refresh + rel=canonical as a permanent redirect, preserving rankings.
REDIRECT_STUB = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Page moved</title>
<link rel="canonical" href="{new}">
<meta http-equiv="refresh" content="0; url={new}">
<meta name="robots" content="noindex, follow">
<script>location.replace(document.querySelector('link[rel=canonical]').href)</script>
</head>
<body>
<p>This page has moved. <a href="{new}">Continue to {title}</a>.</p>
</body>
</html>
"""

def build_redirects():
    rows = [["old_path", "new_path", "type", "title"]]
    n = 0
    for c in C:
        old_path = f"/product-category/{c['slug']}/"
        new = cat_url(c["id"])
        name = html.unescape(c["name"])
        rows.append([old_path, new, "category", name])
        # products keep their slug -> no redirect needed, but record for completeness
        write(f"product-category/{c['slug']}/index.html",
              REDIRECT_STUB.format(new=new, title=esc(name)))
        n += 1
    with open(ROOT / "content" / "redirects.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"  redirects: {n} category stubs -> /product-category/... (map: content/redirects.csv)")

def build_sitemap():
    """XML sitemap + robots.txt with absolute live URLs (no base rewrite needed)."""
    paths = ["/", "/category/"]
    paths += [f"/{s}/" for s in ("about-us", "contact-us", "delivery-returns",
              "returns-replacements", "terms-and-conditions", "privacy-policy")]
    paths += [cat_url(c["id"]) for c in C if cat_total[c["id"]] and c["id"] not in HIDDEN_TOP]
    paths += [f"/product/{p['slug']}/" for p in P]
    seen, urls = set(), []
    for p in paths:
        if p in seen: continue
        seen.add(p); urls.append(p)
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml.append(f"  <url><loc>{esc(SITE_ABS + u)}</loc></url>")
    xml.append("</urlset>")
    write("sitemap.xml", "\n".join(xml) + "\n")
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_ABS}/sitemap.xml\n")
    print(f"  sitemap: {len(urls)} urls -> sitemap.xml + robots.txt")

def apply_base(base):
    """Prefix all root-relative internal links (href/src/url()) with a base path,
    e.g. '/EME' for GitHub Pages project sites. Set BASE_PATH env var; empty = root."""
    base = (base or "").rstrip("/")
    if not base:
        return
    a = re.compile(r'((?:href|src)=")/(?!/)')
    u = re.compile(r"""(url\(\s*['"]?)/(?!/)""")
    m = re.compile(r'(content="\d+;\s*url=)/(?!/)')  # meta-refresh redirect target
    n = 0
    for f in ROOT.rglob("*.html"):
        t = f.read_text(encoding="utf-8")
        t2 = m.sub(rf"\1{base}/", u.sub(rf"\1{base}/", a.sub(rf"\1{base}/", t)))
        if t2 != t:
            f.write_text(t2, encoding="utf-8"); n += 1
    print(f"  base path '{base}' applied to {n} pages")

if __name__ == "__main__":
    # clean previous generated output (keep raw, tools, assets)
    for d in ("product", "category", "product-category", "about-us", "contact-us",
              "delivery-returns", "returns-replacements", "terms-and-conditions",
              "privacy-policy"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    print("Building catalogue…")
    build_home()
    build_category_index()
    build_categories()
    build_products()
    build_pages()
    build_redirects()
    build_sitemap()
    apply_base(os.environ.get("BASE_PATH", ""))
    print("Done.")
