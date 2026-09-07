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
    "wa": "353852414790",
    "email": "info@eddiemaguire.ie",
    "address": "29 Church St, Dundalk",
    "hours": "Mon–Fri 9am–6pm · Sat 9am–5:30pm",
}

# ---- CMS-editable site content (David edits these in the admin) ----
def _load_json(rel, default):
    f = ROOT / rel
    if f.exists():
        try:
            return json.load(open(f, encoding="utf-8"))
        except Exception as _e:
            print(f"  {rel} load error:", _e)
    return default

_SET = _load_json("content/settings.json", {})
SHOP["name"] = _SET.get("name") or SHOP["name"]
SHOP["tagline"] = _SET.get("tagline") or SHOP["tagline"]
SHOP["phone_display"] = _SET.get("phone") or SHOP["phone_display"]
SHOP["phone_tel"] = SHOP["phone_display"].replace(" ", "")
SHOP["wa"] = _SET.get("whatsapp") or SHOP["wa"]
SHOP["email"] = _SET.get("email") or SHOP["email"]
SHOP["address"] = _SET.get("address") or SHOP["address"]
SHOP["hours"] = _SET.get("hours") or SHOP["hours"]
NAV = _SET.get("nav") or [{"label": "Electrical", "link": "/category/"},
                          {"label": "Home", "link": "/category/"},
                          {"label": "Garden", "link": "/category/"}]
TOPSTRIP = _SET.get("topstrip") or [{"icon": "🚚", "bold": "Free local delivery", "text": "around Dundalk"},
                                    {"icon": "🏬", "bold": "Buy in store", "text": "— " + SHOP["address"]},
                                    {"icon": "💬", "bold": "Ask us anything", "text": "on WhatsApp"}]
FOOTER_BLURB = _SET.get("footer_blurb") or ("Your local electrical & furniture store in Dundalk. "
    "Family run, community focused, and always happy to help. Browse online, buy in store.")
HOME = _load_json("content/homepage.json", {})
def hp(k, d=""):
    v = HOME.get(k)
    return v if v not in (None, "") else d

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
# Products: one JSON file per product in content/products/ (edited via the CMS).
# This is the single source of truth; the raw WooCommerce/supplier/fridge dumps
# in content/raw/ are kept only as an archive/seed.
P = []
_PRODDIR = ROOT / "content" / "products"
if _PRODDIR.exists():
    for _f in sorted(_PRODDIR.rglob("*.json")):   # recurse category subfolders
        try:
            _p = json.load(open(_f, encoding="utf-8"))
        except Exception:
            continue
        if not _p.get("hidden"):
            P.append(_p)

C = json.load(open(RAW / "product_categories.json"))
PAGES = json.load(open(RAW / "pages.json"))
_sc = RAW / "supplier_categories.json"
if _sc.exists():
    C += json.load(open(_sc))

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
    766: 690,        # Landline & Cordless Phones -> under Technology
    767: 0,          # Mobile Phones -> its own top-level department
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
    72: "Mattresses", 686: "TVs", 1419: "Garden & DIY",
}
# Utility/meta buckets hidden from the department menus (pages still exist).
HIDDEN_TOP = {37, 740, 62, 1016}   # All Products, Brands, Sales, duplicate COOKING
for c in C:
    if c["id"] in PARENT_FIXES: c["parent"] = PARENT_FIXES[c["id"]]
    if c["id"] in NAME_FIXES:   c["name"]   = NAME_FIXES[c["id"]]

# Price & category are now baked into each content/products/<id>.json file
# (edited via the CMS), so the old CSV overrides are retired — leaving them on
# would clobber edits made through the admin.
CATEGORY_OVERRIDES = {}
OVERRIDES = {}

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
# Product detail helpers. Each product's description / features / specs now live
# in its own JSON file (CMS-editable); content/enrich.json is the retired seed.

def clean_title(p, brand):
    """Descriptive product title with the leading brand + model stripped, for cards/PDP."""
    t = html.unescape(p["name"]); sku = p.get("sku") or ""
    if brand: t = re.sub(r"^" + re.escape(brand) + r"\b", "", t, flags=re.I)
    if sku: t = t.replace(sku, "")
    t = t.replace("|", " ").replace(":", " ")
    t = re.sub(r"[—\-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -—,|")
    return t or html.unescape(p["name"])

def kind_of(p):
    n = html.unescape(p["name"]).lower()
    cats = " ".join(c.get("name", "").lower() for c in p.get("categories", []))
    s = n + " " + cats
    if "washer" in s and "dryer" in s: return "washer dryer"
    if "tumble" in s or ("dryer" in s and "washer" not in s): return "tumble dryer"
    if "washing machine" in s or "washing" in cats: return "washing machine"
    if "dishwash" in s: return "dishwasher"
    if "fridge" in s or "freezer" in s or "refriger" in s: return "fridge freezer"
    if "cooker" in s or "oven" in s or "cooking" in cats: return "cooker"
    if "iphone" in s or "mobile" in cats or "smartphone" in s: return "phone"
    if "cordless" in s or "landline" in s or "dect" in s or "corded" in s: return "phone"
    return ""

def facets(p):
    """Attribute facets parsed from the product name for filters / chips / specs."""
    name = html.unescape(p["name"]); fc = {}
    m = re.search(r"(\d{2,3})\s?cm", name);           fc["Width"] = m.group(1) + "cm" if m else None
    m = re.search(r"(\d{1,2})\s?kg", name, re.I);      fc["Capacity"] = m.group(1) + "kg" if m else None
    m = re.search(r"(\d{2,4})\s?GB", name, re.I);      fc["Storage"] = m.group(1) + "GB" if m else None
    if re.search(r"dual[- ]fuel", name, re.I):         fc["Fuel"] = "Dual fuel"
    elif re.search(r"\bLPG\b", name):                  fc["Fuel"] = "Gas (LPG)"
    elif re.search(r"\bgas\b", name, re.I):            fc["Fuel"] = "Gas"
    elif kind_of(p) == "cooker":                       fc["Fuel"] = "Electric"
    else:                                              fc["Fuel"] = None
    fc["Colour"] = colour_of(name) or None
    return {k: v for k, v in fc.items() if v}

def real_desc(p):
    d = re.sub(r"<[^>]+>", " ", (p.get("description") or p.get("short_description") or ""))
    d = re.sub(r"\s+", " ", html.unescape(d)).strip()
    if d.lower().startswith("this ") and "." in d:
        out = " ".join(re.split(r"(?<=\.)\s", d)[:2]).strip()
        if 40 < len(out) < 360: return out
    return ""

def blurb(p, fc, brand):
    sku = p.get("sku") or ""; lead = ("The %s %s" % (brand, sku)).strip(); k = kind_of(p)
    if k == "cooker":
        t = "range cooker" if "range" in p["name"].lower() else ("built-in oven" if "built-in" in p["name"].lower() else "freestanding cooker")
        s = "%s is a %s%s" % (lead, (fc["Width"] + " " if fc.get("Width") else ""), t)
        s += {"Dual fuel": " with a gas hob and electric oven", "Gas": " running on natural gas",
              "Gas (LPG)": " running on LPG / bottled gas", "Electric": " with a ceramic hob and fan oven"}.get(fc.get("Fuel"), "") + "."
    elif k in ("washing machine", "washer dryer", "tumble dryer"):
        s = "%s is a %s%s." % (lead, k, (" with a %s load capacity" % fc["Capacity"]) if fc.get("Capacity") else "")
    elif k == "fridge freezer":
        s = "%s is a fridge freezer%s." % (lead, (" finished in %s" % fc["Colour"].lower()) if fc.get("Colour") else "")
    elif k == "phone":
        s = "The %s." % clean_title(p, brand).rstrip(".")
    else:
        s = "%s." % lead
    return real_desc(p) or (s + " Call in to our Church Street showroom in Dundalk for a closer look, or message us on WhatsApp and we'll help you choose.").replace("  ", " ")

def glance_html(fc):
    items = [(lbl, fc[k]) for k, lbl in [("Width", "Width"), ("Capacity", "Capacity"),
             ("Storage", "Storage"), ("Fuel", "Fuel"), ("Colour", "Colour")] if fc.get(k)][:4]
    if not items: return ""
    return '<div class="glance">' + "".join(
        '<div class="g"><span class="k">%s</span><span class="v">%s</span></div>' % (esc(l), esc(v)) for l, v in items) + '</div>'

STARS = '<span class="stars">★★★★★<span class="rev">No reviews yet</span></span>'

# Featured departments (homepage tiles + top nav). slug -> label; resolved to real categories.
FEATURED = [
    ("home-appliances-cooking", "Cookers"),
    ("refrigeration", "Fridges & Freezers"),
    ("washing-machines", "Washing Machines"),
    ("tumble-dryer", "Tumble Dryers"),
    ("washer-dryer", "Washer Dryers"),
    ("dishwashers", "Dishwashers"),
    ("mobile-phones", "Mobile Phones"),
    ("landline-and-cordless-phones", "Landline & Cordless Phones"),
]
slug2id = {clean[c["id"]]: c["id"] for c in C}

def cat_first_image(cid):
    """A representative image for a category (its own products, then descendants)."""
    pool = list(prods_in.get(cid, []))
    for d in _descendants(cid):
        pool += prods_in.get(d, [])
    for p in pool:
        if p.get("images"):
            src = local_img(p["images"][0]["src"])
            if src and "placeholder" not in src: return src
    return CAT_IMAGES.get(clean.get(cid, ""), "/assets/placeholder-product.svg")

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
                          "url": SITE_ABS + f"/product/{p['slug']}/",
                          "seller": {"@type": "Organization", "name": SHOP["name"]}}
    return json.dumps(data, ensure_ascii=False)

WA_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.125.558 4.122 1.533 5.856L.054 23.5l5.823-1.454A11.934 11.934 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.885 0-3.651-.518-5.166-1.42l-.371-.22-3.453.863.927-3.384-.242-.389A9.96 9.96 0 012 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/></svg>'

def nav_links():
    # Top-level shop sections (editable in the CMS via content/settings.json).
    out = "".join(f'<a href="{esc(n.get("link") or "/category/")}">{esc(n.get("label",""))}</a>' for n in NAV)
    return out + '<a class="cats-enq" href="/enquiry/">Make an Enquiry</a>'

def header():
    strip = "".join(f'<span>{s.get("icon","")} <b>{esc(s.get("bold",""))}</b> {esc(s.get("text",""))}</span>' for s in TOPSTRIP)
    return f"""<div class="tstrip"><div class="wrap">
  {strip}
</div></div>
<header class="site"><div class="wrap">
  <a class="brand" href="/">{SHOP['name'].upper()}<small>{SHOP['tagline'].upper()}</small></a>
  <form class="search" onsubmit="return false"><input placeholder="Search cookers, fridges, washing machines…" aria-label="Search"><button>Search</button></form>
  <div class="hactions">
    <a href="tel:{SHOP['phone_tel']}">📞 {SHOP['phone_display']}</a>
    <a class="wa" href="https://wa.me/{SHOP['wa']}">{WA_SVG} Enquire</a>
  </div>
</div></header>
<nav class="cats"><div class="wrap">{nav_links()}</div></nav>"""

def footer():
    shoplinks = "".join(f'<li><a href="/category/{slug}/">{esc(lbl)}</a></li>'
                        for slug, lbl in FEATURED if slug in slug2id and cat_total.get(slug2id[slug]))
    return f"""<footer class="site"><div class="wrap">
  <div class="footer-brand">
    <a href="/" class="brand">{SHOP['name'].upper()}</a>
    <p>{esc(FOOTER_BLURB)}</p>
  </div>
  <div><h4>Shop</h4><ul>{shoplinks}<li><a href="/category/">All categories</a></li></ul></div>
  <div><h4>Company</h4><ul>
    <li><a href="/about-us/">About Us</a></li>
    <li><a href="/contact-us/">Contact</a></li>
    <li><a href="/enquiry/">Make an Enquiry</a></li>
    <li><a href="/delivery-returns/">Delivery</a></li>
    <li><a href="/returns-replacements/">Returns</a></li>
    <li><a href="/terms-and-conditions/">Terms &amp; Conditions</a></li>
    <li><a href="/privacy-policy/">Privacy Policy</a></li>
  </ul></div>
  <div><h4>Visit Us</h4><ul>
    <li><a href="https://maps.google.com/?q={esc(SHOP['address'])}">{esc(SHOP['address'])}</a></li>
    <li><a href="tel:{SHOP['phone_tel']}">{SHOP['phone_display']}</a></li>
    <li><a href="mailto:{SHOP['email']}">{SHOP['email']}</a></li>
    <li class="footer-hours">{SHOP['hours']}</li>
  </ul></div>
</div>
<div class="wrap footer-bottom">
  <span>© 2026 {SHOP['name']} {SHOP['tagline']}. All rights reserved.</span>
  <span>Made with <span>♥</span> in Dundalk</span>
</div>
</footer>
</body></html>"""

def product_card(p):
    img = local_img(p["images"][0]["src"]) if p.get("images") else "/assets/placeholder-product.svg"
    brand = brand_of(p)
    title = clean_title(p, brand)
    fc = facets(p)
    price_v, reg, sale = eff_price(p)
    price = money(price_v)
    try: pnum = float(price_v)
    except (TypeError, ValueError): pnum = ""
    on_sale = sale and reg and sale != reg
    was = f'<span class="was">{money(reg)}</span>' if on_sale else ""
    badge = '<span class="sale-badge">Sale</span>' if on_sale else ""
    price_disp = f"{price}{was}" if price else '<span class="poa">Price on request</span>'
    colour = colour_of(p["name"])
    chipvals = [v for k, v in fc.items() if k in ("Width", "Capacity", "Storage", "Fuel", "Colour")][:2]
    chips = "".join(f'<span class="chip">{esc(v)}</span>' for v in chipvals)
    dataf = " ".join('data-%s="%s"' % (k.lower(), esc(v)) for k, v in fc.items())
    model = f'<div class="model">Model: {esc(p.get("sku"))}</div>' if p.get("sku") else '<div class="model"></div>'
    wa = "https://wa.me/" + SHOP["wa"]
    return f"""<div class="card" data-brand="{esc(brand)}" data-colour="{esc(colour)}" data-price="{pnum}" data-name="{esc(html.unescape(p['name']))}" {dataf}>
  {badge}<div class="imgw"><img src="{esc(img)}" alt="{esc(html.unescape(p['name']))}" loading="lazy"></div>
  {f'<div class="bd">{esc(brand)}</div>' if brand else '<div class="bd"></div>'}
  <a class="nm" href="/product/{esc(p['slug'])}/">{esc(title)}</a>
  {model}
  {STARS}
  <div class="chips">{chips}</div>
  <div class="price">{price_disp}</div>
  <div class="vat">Price includes VAT</div>
  <div class="cbtns"><a class="btn btn-o" href="{wa}">Enquire</a><a class="btn btn-g" href="/product/{esc(p['slug'])}/">Details</a></div>
</div>"""

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
        imgs = [i for i in p.get("images", []) if i and i.get("src")]
        main = local_img(imgs[0]["src"]) if imgs else "/assets/placeholder-product.svg"
        price_v, reg, sale = eff_price(p)
        price = money(price_v)
        on_sale = sale and reg and sale != reg
        was = f'<span class="was">{money(reg)}</span>' if on_sale else ""
        desc = p.get("description") or p.get("short_description") or ""
        wa_text = f"Hi, I'm interested in: {html.unescape(p['name'])} ({SITE}/product/{p['slug']}/)"
        wa_link = "https://wa.me/" + SHOP["wa"] + "?text=" + re.sub(r"\s+", "%20", wa_text)

        brand2 = brand_of(p)
        title = clean_title(p, brand2)
        fc = facets(p); kind = kind_of(p) or "Product"
        # breadcrumb (new style)
        crumb = '<a href="/">Home</a> / <a href="/category/">Shop</a>'
        for cc in chain:
            crumb += f' / <a href="{cat_url(cc["id"])}">{esc(html.unescape(cc["name"]))}</a>'
        crumb += f' / <b>{esc(p.get("sku") or title)}</b>'
        # gallery thumbs
        if len(imgs) > 1:
            thumbs_html = "".join(
                f'<div class="t{" on" if i==0 else ""}" data-src="{esc(local_img(im["src"]))}"><img src="{esc(local_img(im["src"]))}" alt=""></div>'
                for i, im in enumerate(imgs[:6]))
        else:
            thumbs_html = f'<div class="t on"><img src="{esc(main)}" alt=""></div><div class="t">More<br>photos<br>soon</div>'
        price_html = (f'<div class="price">{price}{was}</div><div class="vat">Price includes VAT'
                      + (f' · model {esc(p.get("sku"))}' if p.get("sku") else '') + '</div>') if price else \
                     '<div class="price"><span class="poa">Price on request</span></div>'
        # overview / features / specs — all CMS-editable per product; fall back to generated.
        _cms = re.sub(r"<[^>]+>", " ", html.unescape(p.get("description") or ""))
        _cms = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", _cms).replace("**", "").replace("__", "")
        _cms = re.sub(r"\s+", " ", _cms).strip()
        if "call or message" in _cms.lower() or "in stock in store" in _cms.lower() or len(_cms) < 25:
            _cms = ""   # ignore any old auto boilerplate / trivial text
        lead_txt = _cms or blurb(p, fc, brand2)
        p_feats = [x for x in (p.get("features") or []) if str(x).strip()]
        p_specs = [s for s in (p.get("specs") or []) if s]
        if p_feats:
            feats = p_feats
        else:
            feats = []
            if fc.get("Width"): feats.append(f"{fc['Width']} width")
            if fc.get("Capacity"): feats.append(f"{fc['Capacity']} load capacity")
            if fc.get("Storage"): feats.append(f"{fc['Storage']} storage")
            if fc.get("Fuel"): feats.append({"Dual fuel": "Dual fuel — gas hob with electric oven", "Gas": "Gas cooker — natural gas", "Gas (LPG)": "Gas cooker — LPG / bottled gas", "Electric": "Electric — ceramic hob & fan oven"}.get(fc["Fuel"], fc["Fuel"]))
            if fc.get("Colour"): feats.append(f"{fc['Colour']} finish")
            feats.append(f"{brand2} — model {p.get('sku') or 'see in store'}" if brand2 else "Part of our range at Eddie Maguire, Dundalk")
            feats.append("Local delivery & setup advice available")
        spec = [("Brand", brand2), ("Model number", p.get("sku") or "—"), ("Product type", kind.title())]
        if p_specs:
            for s in p_specs:
                if isinstance(s, dict):
                    spec.append((s.get("label", ""), s.get("value", "")))
                elif isinstance(s, (list, tuple)) and len(s) == 2:
                    spec.append((s[0], s[1]))
        else:
            for kk, lbl in [("Width", "Width"), ("Capacity", "Load capacity"), ("Storage", "Storage"), ("Fuel", "Fuel type"), ("Colour", "Colour")]:
                if fc.get(kk): spec.append((lbl, fc[kk]))
            spec += [("Guarantee", "Manufacturer guarantee — ask in store")]
        specnote = "" if p_specs else '<div class="specnote">Specifications shown are compiled from the details we hold; full manufacturer specs are available in store.</div>'
        feat_html = "".join(f"<li>{esc(x)}</li>" for x in feats)
        spec_html = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in spec)
        wp_block = ""
        # related
        related = [q for q in prods_in.get(cats[0]["id"], []) if q["slug"] != p["slug"]][:4] if cats else []
        rel_html = "".join(product_card(q) for q in related)
        rel_section = f'<div class="related"><h2>You Might Also Like</h2><div class="grid">{rel_html}</div></div>' if related else ""
        enq_q = re.sub(r"\s+", "+", (brand2 + " " + (p.get("sku") or title)).strip())

        body = f"""{header()}
<div class="wrap">
<div class="crumb">{crumb}</div>
<div class="pdp">
  <div class="gallery">
    <div class="thumbs">{thumbs_html}</div>
    <div class="gmain"><img id="pdpmain" src="{esc(main)}" alt="{esc(html.unescape(p['name']))}"></div>
  </div>
  <div class="pinfo">
    {f'<div class="bd">{esc(brand2)}</div>' if brand2 else ''}
    <h1>{esc(title)}</h1>
    <div class="pmodel">Model: {esc(p.get('sku') or '—')}</div>
    {STARS}
    {glance_html(fc)}
    <div class="pricebox">
      {price_html}
      <div class="delivery">
        <div class="row"><span class="ic">🏬</span><div><b>Collect in store</b> — reserve by phone or message</div></div>
        <div class="row"><span class="ic">🚚</span><div><b>Local delivery</b> around Dundalk — ask us for a quote</div></div>
        <div class="row"><span class="ic">💬</span><div><b>Questions?</b> Message us and we'll help you choose</div></div>
      </div>
      <div class="ctas">
        <a class="ctabig" href="{wa_link}">{WA_SVG} Enquire on WhatsApp</a>
        <a class="ctacall" href="tel:{SHOP['phone_tel']}">📞 Call {SHOP['phone_display']}</a>
        <a class="ctarsv" href="https://wa.me/{SHOP['wa']}">Reserve for collection</a>
        <a class="enq-link" href="/enquiry/?product={enq_q}">Prefer a form? Make an enquiry →</a>
      </div>
    </div>
    <div class="trustrow">
      <div class="trust"><b>Family run</b>Trusted Dundalk retailer</div>
      <div class="trust"><b>Real shop</b>See it before you buy</div>
      <div class="trust"><b>Local advice</b>We know our products</div>
    </div>
  </div>
</div>
<div class="psection"><h2>Overview</h2><p class="leadp">{esc(lead_txt)}</p><ul class="feat-list">{feat_html}</ul></div>
<div class="psection"><h2>Specifications</h2><table class="spectab"><tbody>{spec_html}</tbody></table>{specnote}</div>
{wp_block}
{rel_section}
</div>
<div class="stickybar" id="sbar"><div class="wrap">
  <img class="sb-img" src="{esc(main)}" alt="">
  <div class="sb-nm">{esc(brand2)} {esc(p.get('sku') or title)}</div>
  <div class="sb-pr">{price if price else ''}</div>
  <a class="sb-cta" href="{wa_link}">{WA_SVG} Enquire</a>
</div></div>
<script>
(function(){{var b=document.getElementById('sbar');if(b)addEventListener('scroll',function(){{b.classList.toggle('on',scrollY>640)}});
document.querySelectorAll('.thumbs .t[data-src]').forEach(function(t){{t.addEventListener('click',function(){{
  document.getElementById('pdpmain').src=t.dataset.src;
  document.querySelectorAll('.thumbs .t').forEach(function(x){{x.classList.remove('on')}});t.classList.add('on');}})}});}})();
</script>
{footer()}"""
        abs_img = (SITE_ABS + main) if main.startswith("/") else main
        page = head(f"{html.unescape(p['name'])} | {SHOP['name']}",
                    lead_txt[:155],
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
        crumb = '<a href="/">Home</a> / <a href="/category/">Shop</a>'
        for cc in chain[:-1]:
            crumb += f' / <a href="{cat_url(cc["id"])}">{esc(html.unescape(cc["name"]))}</a>'
        crumb += f' / <b>{esc(html.unescape(c["name"]))}</b>'

        subcats = sorted([s for s in children.get(c["id"], []) if cat_total[s["id"]]], key=lambda x: -cat_total[x["id"]])
        subnav = ""
        if subcats:
            chips = "".join(f'<a href="{cat_url(s["id"])}">{esc(html.unescape(s["name"]))}</a>' for s in subcats)
            subnav = f'<div class="subnav">{chips}</div>'

        cards = "".join(product_card(p) for p in prods) or '<div class="nores">No products in this category yet.</div>'
        cname = esc(html.unescape(c["name"]))
        ccount = f"{len(prods)} product{'s' if len(prods)!=1 else ''}"

        # ── filter sidebar (client-side): Brand + up to 2 attribute facets + Colour + Price ──
        from collections import Counter as _Counter
        bc = _Counter(brand_of(p) for p in prods if brand_of(p))
        fcounts = {}
        for p in prods:
            for k, v in facets(p).items():
                fcounts.setdefault(k, _Counter())[v] += 1
        colc = _Counter(colour_of(p["name"]) for p in prods if colour_of(p["name"]))
        sec = [k for k in ("Fuel", "Capacity", "Width", "Storage") if len(fcounts.get(k, {})) > 1][:2]

        def fopts(counter, cls):
            return "".join(
                f'<label class="fopt"><input type="checkbox" class="{cls}" value="{esc(str(k))}"><span>{esc(str(k))}</span></label>'
                for k, v in sorted(counter.items(), key=lambda x: (-x[1], str(x[0]))))

        groups = ""
        dims = []
        if len(bc) > 1:
            groups += f'<div class="fgroup"><h4>Brand</h4>{fopts(bc, "f-brand")}</div>'; dims.append("brand")
        for k in sec:
            groups += f'<div class="fgroup"><h4>{esc(k)}</h4>{fopts(fcounts[k], "f-"+k.lower())}</div>'; dims.append(k.lower())
        if len(colc) > 1 and "colour" not in dims:
            groups += f'<div class="fgroup"><h4>Colour</h4>{fopts(colc, "f-colour")}</div>'; dims.append("colour")
        nums = []
        for p in prods:
            try: nums.append(float(eff_price(p)[0]))
            except (TypeError, ValueError): pass
        pricegroup = ""
        if nums:
            brackets = [(0, 300, "Under €300"), (300, 600, "€300 – €600"), (600, 1000, "€600 – €1,000"), (1000, 10**9, "€1,000+")]
            present = [(a, z, l) for a, z, l in brackets if any(a <= n < z for n in nums)]
            if len(present) > 1:
                opts = "".join(f'<label class="fopt"><input type="radio" name="pr" class="f-price" value="{a}-{z}"><span>{esc(l)}</span></label>' for a, z, l in present)
                pricegroup = f'<div class="fgroup"><h4>Price</h4>{opts}</div>'

        show_filters = len(prods) >= 4 and (groups or pricegroup)
        dims_js = ",".join(f'"{d}"' for d in dims)
        top_brands = ", ".join(b for b, _ in bc.most_common(4))
        intro = (f"Our {html.unescape(c['name'])} range at {SHOP['name']}, Dundalk"
                 + (f", including {top_brands}." if top_brands else ".")
                 + " Not sure which suits you? Message us on WhatsApp and we'll help you choose.")

        maincol = f"""<main>
      <div class="lhead"><div><h1>{cname}</h1></div>
        <div class="sortbar">Sort <select id="sort"><option value="feat">Featured</option><option value="lo">Price: low to high</option><option value="hi">Price: high to low</option><option value="az">Name A–Z</option></select></div>
      </div>
      {subnav}
      <p class="intro">{esc(intro)}</p>
      <div class="grid" id="grid">{cards}</div>
    </main>"""

        if show_filters:
            listing = f"""<div class="plist">
    <aside class="filters">
      <div class="fgroup" style="display:flex;justify-content:space-between;align-items:center;padding-bottom:10px"><strong style="font-size:13px;text-transform:uppercase;letter-spacing:.05em">Filter</strong><button class="clearf" type="button" onclick="clearAll()">Clear all</button></div>
      {groups}{pricegroup}
    </aside>
    {maincol}
  </div>
  <script>
  (function(){{
    var DIMS=[{dims_js}];
    window.clearAll=function(){{document.querySelectorAll('.filters input').forEach(function(i){{i.checked=false}});applyF()}};
    function checked(cls){{return Array.from(document.querySelectorAll('.'+cls+':checked')).map(function(x){{return x.value}})}}
    window.applyF=function(){{
      var sel={{}};DIMS.forEach(function(d){{sel[d]=checked('f-'+d)}});
      var pr=(document.querySelector('.f-price:checked')||{{}}).value;
      var cards=Array.prototype.slice.call(document.querySelectorAll('.card'));var vis=0;
      cards.forEach(function(c){{var ok=true;
        DIMS.forEach(function(d){{if(sel[d].length&&sel[d].indexOf(c.dataset[d])<0)ok=false}});
        if(pr){{var pp=pr.split('-');var v=+c.dataset.price;if(v< +pp[0]||v>= +pp[1])ok=false}}
        c.style.display=ok?'':'none';if(ok)vis++;}});
      var s=document.getElementById('sort').value;var g=document.getElementById('grid');
      var shown=cards.filter(function(c){{return c.style.display!=='none'}});
      shown.sort(function(x,y){{return s==='lo'?x.dataset.price-y.dataset.price:s==='hi'?y.dataset.price-x.dataset.price:s==='az'?(x.dataset.name>y.dataset.name?1:-1):0}});
      shown.forEach(function(c){{g.appendChild(c)}});
      var nr=document.getElementById('nores');
      if(!vis){{if(!nr){{nr=document.createElement('div');nr.id='nores';nr.className='nores';nr.textContent='No products match those filters.';g.appendChild(nr)}}}}else if(nr)nr.remove();
    }};
    document.querySelectorAll('.filters input').forEach(function(i){{i.addEventListener('change',applyF)}});
    document.getElementById('sort').addEventListener('change',applyF);
  }})();
  </script>"""
        else:
            listing = f'<div style="padding:12px 0 60px">{maincol}</div>'

        body = f"""{header()}
<div class="wrap">
<div class="crumb">{crumb}</div>
{listing}
</div>
{footer()}"""
        page = head(f"{html.unescape(c['name'])} | {SHOP['name']}",
                    f"Browse {html.unescape(c['name'])} at {SHOP['name']}, Dundalk. Buy in store.",
                    path=cat_url(c["id"])) + body
        write(f"category/{clean[c['id']]}/index.html", page)
    print(f"  categories: {len(C)} pages")

# CATEGORY INDEX
def build_category_index():
    tiles = ""
    for slug, lbl in FEATURED:
        if slug not in slug2id or not cat_total.get(slug2id[slug]): continue
        cid = slug2id[slug]
        tiles += f"""<a class="tile" href="/category/{slug}/">
  <div class="tw"><img src="{esc(cat_first_image(cid))}" alt="{esc(lbl)}" loading="lazy"></div>
  <h3>{esc(lbl)}</h3><div class="go">Shop now →</div></a>"""
    tops = sorted([c for c in children.get(0, []) if cat_total[c["id"]] and c["id"] not in HIDDEN_TOP], key=lambda x: -cat_total[x["id"]])
    deptrow = "".join(f'<a class="subnav-a" href="{cat_url(t["id"])}"></a>' for t in [])  # (kept simple)
    body = f"""{header()}
<div class="wrap">
<div class="crumb"><a href="/">Home</a> / <b>Shop</b></div>
<div class="page-head"><h1>Shop By Category</h1><div class="count">Browse our departments</div></div>
</div>
<section class="section" style="padding-top:20px"><div class="wrap"><div class="tiles">{tiles}</div></div></section>
{footer()}"""
    write("category/index.html", head(f"Shop | {SHOP['name']}", f"Browse all categories at {SHOP['name']}, Dundalk.", path="/category/") + body)
    print("  category index: 1 page")

# HOMEPAGE
def build_home():
    total = len(P)
    # hero visual — prefer a range cooker photo, else any cooker/appliance photo
    def pick_photo(cid, want=None):
        pool = list(prods_in.get(cid, []))
        for d in _descendants(cid): pool += prods_in.get(d, [])
        if want:
            for p in pool:
                if want.lower() in html.unescape(p["name"]).lower() and p.get("images"):
                    s = local_img(p["images"][0]["src"])
                    if "placeholder" not in s: return p, s
        for p in pool:
            if p.get("images"):
                s = local_img(p["images"][0]["src"])
                if "placeholder" not in s: return p, s
        return None, "/assets/placeholder-product.svg"
    cook_id = slug2id.get("home-appliances-cooking")
    _, _hero_auto = pick_photo(cook_id, "range") if cook_id else (None, "/assets/placeholder-product.svg")
    hero_img = hp("hero_image", _hero_auto)

    # category tiles (featured, consistent sizing) — lead with the Build-a-Bed feature
    tiles = ('<a class="tile" href="/build-a-bed/">'
             '<div class="tw" style="padding:0;overflow:hidden">'
             '<img src="/assets/img/aurora-ottoman-1.jpg" alt="Build your bed" loading="lazy" '
             'style="width:100%;height:100%;object-fit:cover;mix-blend-mode:normal"></div>'
             '<h3>Build Your Bed</h3><div class="go">Design yours →</div></a>')
    for slug, lbl in FEATURED:
        if slug not in slug2id or not cat_total.get(slug2id[slug]): continue
        cid = slug2id[slug]
        tiles += f"""<a class="tile" href="/category/{slug}/">
  <div class="tw"><img src="{esc(cat_first_image(cid))}" alt="{esc(lbl)}" loading="lazy"></div>
  <h3>{esc(lbl)}</h3><div class="go">Shop now →</div></a>"""

    # popular banners — three photographed products across departments
    banners = ""
    for slug, want in [("mobile-phones", "iPhone"), ("home-appliances-cooking", "Range"), ("refrigeration", None)]:
        cid = slug2id.get(slug)
        if not cid: continue
        p, img = pick_photo(cid, want)
        if not p: continue
        b = brand_of(p); t = clean_title(p, b); pr = money(eff_price(p)[0])
        banners += f"""<a class="banner" href="/product/{esc(p['slug'])}/">
      <div class="bimg"><img src="{esc(img)}" alt="{esc(html.unescape(p['name']))}"></div>
      <div class="btext"><div class="bd">{esc(b)}</div><h3>{esc(t)}</h3><div class="pr">{pr}</div><div class="go">View details →</div></div>
    </a>"""

    # brands strip — top brands by count
    from collections import Counter as _Counter
    allb = _Counter(brand_of(p) for p in P if brand_of(p))
    brands_row = "".join(f"<span>{esc(b)}</span>" for b, _ in allb.most_common(12))

    _vp = hp("valueprops", [{"icon": "🚚", "title": "Free Local Delivery", "subtitle": "Around Dundalk"},
                            {"icon": "🏬", "title": "Buy In Store", "subtitle": SHOP["address"]},
                            {"icon": "💬", "title": "Real Advice", "subtitle": "We know our products"},
                            {"icon": "🛠️", "title": "Family Run", "subtitle": "Trusted locally"}])
    valprops = "".join(f'<div class="vp"><span class="ic">{v.get("icon","")}</span><div><b>{esc(v.get("title",""))}</b><span>{esc(v.get("subtitle",""))}</span></div></div>' for v in _vp)
    hero_title = "<br>".join(esc(x) for x in hp("hero_title", "Big Brands.\nReal Advice.\nLocal Prices.").split("\n"))
    _stats = hp("stats", [{"number": "100%", "label": "Irish owned"}, {"number": "30+", "label": "Years in business"}, {"number": "1", "label": "Town — Dundalk"}])
    stats_html = "".join(f'<div class="stat"><div class="n">{esc(s.get("number",""))}</div><div class="l">{esc(s.get("label",""))}</div></div>' for s in _stats)

    body = f"""{header()}
<section class="hero"><div class="wrap">
  <div class="hero-copy">
    <div class="eyebrow">{esc(hp("hero_eyebrow", "Home Appliances & Phones — Dundalk"))}</div>
    <h1>{hero_title}</h1>
    <p>{esc(hp("hero_text", "Your family-run electrical & furniture store on Church St. Browse our full range online, then call in or message us — we'll help you choose."))}</p>
    <div class="cta"><a class="bigbtn o" href="#cats">{esc(hp("hero_cta_label", "Shop All Categories"))}</a><a class="bigbtn w" href="https://wa.me/{SHOP['wa']}">{WA_SVG} Message Us</a></div>
  </div>
  <div class="hero-visual"><img src="{esc(hero_img)}" alt="Featured appliance"></div>
</div></section>
<div class="valprops">{valprops}</div>
<div class="wrap"><div class="brands-strip"><div class="lab">{esc(hp("brands_label", "Trusted Brands We Stock"))}</div><div class="brands-row">{brands_row}</div></div></div>
<section class="section" id="cats"><div class="wrap">
  <div class="section-label">{esc(hp("category_label", "What We Stock"))}</div><h2>{esc(hp("category_title", "Shop By Category"))}</h2>
  <div class="tiles">{tiles}</div>
</div></section>
<section class="section" style="background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line)"><div class="wrap">
  <div class="section-label">{esc(hp("popular_label", "Featured"))}</div><h2>{esc(hp("popular_title", "Popular Right Now"))}</h2>
  <div class="banners">{banners}</div>
</div></section>
<section class="section"><div class="wrap"><div class="whatsapp-strip">
  <div><h2>{esc(hp("whatsapp_title", "Not Sure What You Need?"))}</h2><p>{esc(hp("whatsapp_text", "Message us on WhatsApp — we're happy to help you find the right product for your home and budget."))}</p></div>
  <a class="bigbtn w" href="https://wa.me/{SHOP['wa']}">{WA_SVG} Message Us On WhatsApp</a>
</div></div></section>
<section class="section"><div class="wrap">
  <div class="section-label">{esc(hp("about_label", "Who We Are"))}</div><h2>{esc(hp("about_title", "A Family Store, Built On Trust"))}</h2>
  <p style="color:var(--muted);max-width:660px;margin:0 0 24px">{esc(hp("about_text", "Eddie Maguire has served the Dundalk community for years with a carefully chosen range of electrical, appliances and furniture for every home and budget. We're a real shop with real people who know their products."))}</p>
  <div class="aboutband">{stats_html}</div>
</div></section>
{footer()}"""
    write("index.html", head(f"{SHOP['name']} — {SHOP['tagline']} | Dundalk",
        "Electrical, appliances & furniture in Dundalk. Browse our full range online, buy in store.",
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
<div class="wrap">
<div class="crumb"><a href="/">Home</a> / <b>{esc(title)}</b></div>
<div class="page-head"><h1>{esc(title)}</h1></div>
<div class="prose-wrap"><div class="prose">{content_html}</div></div>
</div>
{footer()}"""
    write(f"{slug}/index.html", head(f"{title} | {SHOP['name']}", desc, path=f"/{slug}/") + body)

def build_contact():
    maps = f"https://www.google.com/maps?q={esc(SHOP['address'])}&output=embed"
    body = f"""{header()}
<div class="wrap">
<div class="crumb"><a href="/">Home</a> / <b>Contact</b></div>
<div class="page-head"><h1>Get In Touch</h1><div class="count">We're here to help — call in, call us, or message us on WhatsApp.</div></div>
<div class="contact-grid">
  <div class="contact-block">
    <div class="contact-row"><div class="ico">📍</div><div><div class="lbl">Visit the store</div><div class="val"><a href="https://maps.google.com/?q={esc(SHOP['address'])}">{esc(SHOP['address'])}</a></div></div></div>
    <div class="contact-row"><div class="ico">📞</div><div><div class="lbl">Call us</div><div class="val"><a href="tel:{SHOP['phone_tel']}">{SHOP['phone_display']}</a></div></div></div>
    <div class="contact-row"><div class="ico">✉️</div><div><div class="lbl">Email</div><div class="val"><a href="mailto:{SHOP['email']}">{SHOP['email']}</a></div></div></div>
    <div class="contact-row"><div class="ico">🕑</div><div><div class="lbl">Opening hours</div><div class="val">{SHOP['hours']}<br>Sun: Closed</div></div></div>
    <div class="cta" style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
      <a href="https://wa.me/{SHOP['wa']}" class="bigbtn w">{WA_SVG} WhatsApp Us</a>
      <a href="tel:{SHOP['phone_tel']}" class="bigbtn g">Call {SHOP['phone_display']}</a>
    </div>
  </div>
  <iframe class="contact-map" src="{maps}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" title="Map to {esc(SHOP['name'])}"></iframe>
</div>
</div>
{footer()}"""
    write("contact-us/index.html", head(f"Contact | {SHOP['name']}",
        f"Contact {SHOP['name']}, {SHOP['address']}. Call {SHOP['phone_display']} or message us on WhatsApp.",
        path="/contact-us/", jsonld=localbusiness_ld()) + body)

def build_enquiry():
    # Static-site enquiry form: no backend — on submit it composes the message and
    # hands it to WhatsApp or the customer's email client (they press send).
    body = f"""{header()}
<div class="wrap">
<div class="crumb"><a href="/">Home</a> / <b>Make an Enquiry</b></div>
<div class="page-head"><h1>Make An Enquiry</h1><div class="count">Tell us what you're after and we'll get back to you. Send it straight to us on WhatsApp, or by email — whichever suits.</div></div>
<div class="enq-grid">
  <form class="enq-form" onsubmit="return false" novalidate>
    <label class="fld"><span>Your name</span><input id="f-name" type="text" autocomplete="name" placeholder="Jane Murphy"></label>
    <label class="fld"><span>Phone or email <small>(so we can reply)</small></span><input id="f-contact" type="text" autocomplete="tel" placeholder="087 123 4567 or you@email.com"></label>
    <label class="fld"><span>Product you're interested in <small>(optional)</small></span><input id="f-product" type="text" placeholder="e.g. Beko FDC6731S cooker"></label>
    <label class="fld"><span>Your message</span><textarea id="f-msg" rows="5" placeholder="Is this in stock? What's your best price? Can you deliver to Dundalk?"></textarea></label>
    <div class="enq-actions">
      <button type="button" class="ctabig" onclick="enqSend('wa')">{WA_SVG} Send via WhatsApp</button>
      <button type="button" class="ctacall" onclick="enqSend('email')">✉️ Send by Email</button>
    </div>
    <p class="enq-note">No account needed. Your details are only used to answer your enquiry — nothing is stored on this website.</p>
  </form>
  <aside class="enq-side">
    <h3>Prefer to talk?</h3>
    <div class="contact-row"><div class="ico">📞</div><div><div class="lbl">Call us</div><div class="val"><a href="tel:{SHOP['phone_tel']}">{SHOP['phone_display']}</a></div></div></div>
    <div class="contact-row"><div class="ico">💬</div><div><div class="lbl">WhatsApp</div><div class="val"><a href="https://wa.me/{SHOP['wa']}">Message us</a></div></div></div>
    <div class="contact-row"><div class="ico">✉️</div><div><div class="lbl">Email</div><div class="val"><a href="mailto:{SHOP['email']}">{SHOP['email']}</a></div></div></div>
    <div class="contact-row"><div class="ico">📍</div><div><div class="lbl">Visit the store</div><div class="val">{esc(SHOP['address'])}</div></div></div>
    <div class="contact-row"><div class="ico">🕑</div><div><div class="lbl">Opening hours</div><div class="val">{SHOP['hours']}<br>Sun: Closed</div></div></div>
  </aside>
</div>
</div>
<script>
(function(){{
  var q=new URLSearchParams(location.search);
  function set(id,val){{ if(val){{ var el=document.getElementById(id); if(el) el.value=val; }} }}
  set('f-product', q.get('product')); set('f-name', q.get('name'));
  set('f-contact', q.get('contact')); set('f-msg', q.get('msg'));
}})();
function v(id){{ var el=document.getElementById(id); return el ? (el.value||'').trim() : ''; }}
function enqBody(){{
  var lines=[]; var n=v('f-name'),c=v('f-contact'),p=v('f-product'),msg=v('f-msg');
  if(n) lines.push('Name: '+n);
  if(c) lines.push('Contact: '+c);
  if(p) lines.push('Product: '+p);
  if(msg) lines.push('Message: '+msg);
  return lines.join('\\n');
}}
function enqSend(how){{
  if(!v('f-name') || !v('f-contact')){{ alert('Please add your name and a phone number or email so we can reply.'); return; }}
  var text = enqBody();
  if(how==='wa'){{
    window.open('https://wa.me/{SHOP['wa']}?text='+encodeURIComponent(text), '_blank');
  }} else {{
    var subj = 'Website enquiry' + (v('f-product') ? (' — '+v('f-product')) : '');
    window.location.href = 'mailto:{SHOP['email']}?subject='+encodeURIComponent(subj)+'&body='+encodeURIComponent(text);
  }}
}}
</script>
{footer()}"""
    write("enquiry/index.html", head(f"Make an Enquiry | {SHOP['name']}",
        f"Send an enquiry to {SHOP['name']}, Dundalk — by WhatsApp or email. We'll get back to you.",
        path="/enquiry/") + body)

# ── Minimal Markdown → HTML (stdlib only) for the CMS-editable content pages ──
def _md_inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'(?<![*\w])\*([^*]+)\*(?![*\w])', r'<em>\1</em>', t)
    return t

def md_to_html(md):
    lines = md.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1; continue
        m = re.match(r'^(#{1,6})\s+(.*)$', s)
        if m:
            lvl = max(2, min(len(m.group(1)) + 1, 4))
            out.append(f"<h{lvl}>{_md_inline(m.group(2).strip())}</h{lvl}>"); i += 1; continue
        if re.match(r'^[-*]\s+', s):
            items = []
            while i < n and re.match(r'^\s*[-*]\s+', lines[i]):
                items.append(_md_inline(re.sub(r'^\s*[-*]\s+', '', lines[i]).strip())); i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"); continue
        if re.match(r'^\d+\.\s+', s):
            items = []
            while i < n and re.match(r'^\s*\d+\.\s+', lines[i]):
                items.append(_md_inline(re.sub(r'^\s*\d+\.\s+', '', lines[i]).strip())); i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>"); continue
        para = [s]; i += 1
        while i < n and lines[i].strip() and not re.match(r'^(#{1,6}\s|[-*]\s|\d+\.\s)', lines[i].strip()):
            para.append(lines[i].strip()); i += 1
        out.append("<p>" + _md_inline(" ".join(para)) + "</p>")
    return "\n".join(out)

def build_bedbuilder():
    # "Build Your Bed" — Aurora base + in-store headboards, made to order in Aurora's
    # full fabric range. The preview bed AND every headboard tile recolour LIVE in the
    # browser: the chosen fabric colour is pushed through each real photo's velvet
    # shading (canvas), keeping genuine folds, tufting & sheen.
    SIZES = [("Single 3′", "90 × 190 cm"), ("Small Double 4′", "120 × 190 cm"),
             ("Double 4′6″", "135 × 190 cm"), ("King 5′", "150 × 200 cm"), ("Super King 6′", "180 × 200 cm")]
    FABRICS = [
        ("Plush Velvet", ["Charcoal", "China Blue", "Coffee", "Cream", "Emerald", "Pink"]),
        ("Spice Velvet", ["Armour", "Beige", "Denim", "Ivory", "Petrol", "Pink", "Turmeric"]),
        ("Wool", ["Clay", "Latte", "Shadow", "Steel"]),
        ("Naples", ["Beige", "Cream", "Silver"]),
        ("Matiz", ["Beige", "Silver"]),
        ("Alessia", ["Silver", "Smoke"]),
        ("Linoso", ["Duck Egg", "Midnight Blue"]),
        ("Airforce", ["Blue"]),
    ]
    SW_RGB = {
        "plush-velvet-charcoal": (104, 109, 120), "plush-velvet-china-blue": (47, 127, 145),
        "plush-velvet-coffee": (162, 151, 133), "plush-velvet-cream": (202, 201, 197),
        "plush-velvet-emerald": (81, 108, 90), "plush-velvet-pink": (197, 187, 188),
        "spice-velvet-armour": (150, 150, 152), "spice-velvet-beige": (144, 121, 112),
        "spice-velvet-denim": (57, 77, 112), "spice-velvet-ivory": (199, 196, 192),
        "spice-velvet-petrol": (142, 155, 153), "spice-velvet-pink": (180, 131, 148),
        "spice-velvet-turmeric": (152, 102, 44), "wool-clay": (145, 140, 138),
        "wool-latte": (165, 148, 134), "wool-shadow": (107, 106, 107), "wool-steel": (134, 135, 136),
        "naples-beige": (172, 154, 136), "naples-cream": (189, 179, 161), "naples-silver": (174, 168, 161),
        "matiz-beige": (136, 134, 128), "matiz-silver": (130, 131, 132),
        "alessia-silver": (171, 169, 165), "alessia-smoke": (141, 140, 143),
        "linoso-duck-egg": (121, 141, 142), "linoso-midnight-blue": (81, 99, 114),
        "airforce-blue": (89, 107, 122),
    }
    HEADBOARDS = [("Panel", "panel"), ("Florence", "florence"), ("Button Top", "button-top"),
                  ("Diamond", "diamond"), ("Malaga", "malaga"), ("Roma", "roma"),
                  ("Verona", "verona"), ("Milan", "milan"), ("Studded", "studded"),
                  ("Double Studded", "double-studded"), ("Winged", "winged"),
                  ("Framed", "framed"), ("Sorrento", "sorrento")]
    def fslug(rng, col): return (rng + "-" + col).lower().replace(" ", "-")
    DRAWER_PRICE = 40
    DEFAULT_SLUG = "plush-velvet-charcoal"
    sw_json = "{" + ",".join(f'"{k}":[{r},{g},{b}]' for k, (r, g, b) in SW_RGB.items()) + "}"
    hb_json = "[" + ",".join(f'"{s}"' for _, s in HEADBOARDS) + "]"
    base_btns = ('<button type="button" class="bb-base on" data-kind="storage">'
                 '<b>Storage</b><span>Ottoman lift-up base</span></button>'
                 '<button type="button" class="bb-base" data-kind="standard">'
                 '<b>Standard</b><span>Divan, optional drawers</span></button>')
    SIZE_BUCKET = ["3", "46", "46", "5", "6"]  # price bucket per size (Aurora price card)
    size_btns = "".join(
        f'<button type="button" class="bb-size{" on" if i==3 else ""}" data-size="{esc(nm)}" data-bucket="{SIZE_BUCKET[i]}">{esc(nm)}</button>'
        for i, (nm, dim) in enumerate(SIZES))
    def side_btns(side):
        return "".join(f'<button type="button" class="bb-dwr{" on" if k==0 else ""}" data-side="{side}" data-n="{k}">{k}</button>' for k in (0, 1, 2))
    groups = ""
    for rng, cols in FABRICS:
        sw = "".join(
            f'<button type="button" class="bb-sw{" on" if fslug(rng,c)==DEFAULT_SLUG else ""}" '
            f'style="--img:url(\'/assets/img/swatch-{fslug(rng,c)}.jpg\')" '
            f'data-slug="{fslug(rng,c)}" data-name="{esc(rng)} — {esc(c)}"><span class="bb-chip"></span>'
            f'<span class="bb-lbl">{esc(c)}</span></button>'
            for c in cols)
        groups += f'<div class="bb-group"><div class="bb-gh">{esc(rng)}</div><div class="bb-grid">{sw}</div></div>'
    # headboard tiles: a live-recolour canvas per style + a "no headboard" option
    hb_tiles = ('<button type="button" class="bb-hb bb-hb-none on" data-hb="" data-slug="">'
                '<span class="bb-hbimg bb-hbnone">No headboard</span><span class="bb-hblbl">Just the base</span></button>')
    hb_tiles += "".join(
        f'<button type="button" class="bb-hb" data-hb="{esc(name)}" data-slug="{slug}">'
        f'<span class="bb-zbtn" data-zoom="1" title="Zoom">⤢</span>'
        f'<canvas class="bb-hbcanvas" data-slug="{slug}" width="300" height="200"></canvas>'
        f'<span class="bb-hblbl">{esc(name)}</span></button>'
        for name, slug in HEADBOARDS)
    # hidden sources + masks for headboard recolour (paths get the deploy base path applied)
    hb_srcs = "".join(
        f'<img id="hbsrc-{slug}" src="/assets/img/headboard-{slug}.jpg" hidden alt="">'
        f'<img id="hbmsk-{slug}" src="/assets/img/hbmask-{slug}.png" hidden alt="">'
        for _, slug in HEADBOARDS)
    wa = SHOP["wa"]
    body = f"""{header()}
<style>
.bb{{display:grid;grid-template-columns:1fr 1fr;gap:32px;padding:8px 0 64px;align-items:start}}
@media(max-width:900px){{.bb{{grid-template-columns:1fr}}}}
@media(min-width:901px){{.bb-preview{{position:sticky;top:150px}}}}
.bb-stage{{position:relative;background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden;aspect-ratio:1/1}}
.bb-stage canvas{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}}
.bb-tag{{position:absolute;left:12px;bottom:12px;background:rgba(26,18,16,.82);color:#fff;font-size:12px;font-weight:700;padding:6px 12px;border-radius:20px;letter-spacing:.02em;z-index:2}}
.bb-feat{{position:absolute;right:12px;top:12px;width:34%;max-width:150px;border-radius:10px;border:2px solid #fff;box-shadow:0 4px 12px rgba(0,0,0,.18);z-index:2}}
.bb-chosen{{display:flex;gap:14px;align-items:center;margin-top:14px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px}}
.bb-swatch{{width:72px;height:72px;border-radius:10px;flex:none;border:1px solid rgba(0,0,0,.12);background:var(--img) center/cover,var(--soft)}}
.bb-chosen-name{{font-family:Montserrat;font-weight:800;font-size:15px;text-transform:uppercase;letter-spacing:.02em}}
.bb-chosen-sub{{color:var(--muted);font-size:13px;margin-top:3px}}
.bb-note{{margin-top:12px;font-size:12px;color:var(--muted);line-height:1.5}}
.bb-step{{margin-bottom:24px}}
.bb-step h3{{font-size:15px;text-transform:uppercase;letter-spacing:.04em;margin:0 0 12px}}
.bb-step .hint{{font-size:12.5px;color:var(--muted);margin:-6px 0 10px}}
.bb-bases{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.bb-base{{border:1.5px solid var(--line);background:#fff;border-radius:12px;padding:12px 14px;text-align:left;cursor:pointer}}
.bb-base b{{display:block;font-size:14px;text-transform:uppercase;letter-spacing:.02em}}
.bb-base span{{font-size:12px;color:var(--muted)}}
.bb-base.on{{border-color:var(--orange);background:#fff7ef}}
.bb-sizes,.bb-dwr-row{{display:flex;flex-wrap:wrap;gap:8px}}
.bb-size,.bb-dwr,.bb-mount{{border:1.5px solid var(--line);background:#fff;border-radius:10px;padding:10px 14px;font-weight:700;font-size:13px;cursor:pointer}}
.bb-size.on,.bb-dwr.on,.bb-mount.on{{border-color:var(--orange);color:var(--orange);background:#fff7ef}}
.bb-dwr{{min-width:44px;text-align:center}}
.bb-dwr-side{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.bb-dwr-side .lab{{font-size:12.5px;color:#444;width:74px}}
.bb-group{{margin-bottom:18px}}
.bb-gh{{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:8px}}
.bb-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:10px}}
.bb-sw{{border:0;background:none;padding:0;cursor:pointer;text-align:center}}
.bb-chip{{display:block;height:60px;border-radius:9px;border:2px solid transparent;background:var(--img) center/cover,#ddd;box-shadow:0 0 0 1px rgba(0,0,0,.10) inset}}
.bb-sw.on .bb-chip{{border-color:var(--orange);box-shadow:0 0 0 1px var(--orange),0 6px 14px rgba(0,0,0,.16)}}
.bb-lbl{{display:block;font-size:11px;color:#444;margin-top:5px;line-height:1.2}}
.bb-hbs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:10px}}
.bb-hb{{border:0;background:none;padding:0;cursor:pointer;text-align:center}}
.bb-hbimg,.bb-hbcanvas{{display:block;width:100%;height:72px;border-radius:9px;border:2px solid transparent;box-shadow:0 0 0 1px rgba(0,0,0,.10) inset;background:#f4f1ec}}
.bb-hbimg{{display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--muted)}}
.bb-hbcanvas{{object-fit:contain}}
.bb-hb.on .bb-hbimg,.bb-hb.on .bb-hbcanvas{{border-color:var(--orange);box-shadow:0 0 0 1px var(--orange),0 6px 14px rgba(0,0,0,.16)}}
.bb-hbnone{{font-weight:700;letter-spacing:.02em;color:#777}}
.bb-hblbl{{display:block;font-size:11.5px;color:#444;margin-top:5px;line-height:1.2}}
.bb-cta{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:6px}}
.bb-summary{{font-weight:700;margin-bottom:12px;font-size:14px}}
.bb-summary b{{color:var(--orange)}}
.bb-price{{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:14px;background:var(--soft)}}
.bb-price-row{{display:flex;justify-content:space-between;font-size:13.5px;color:#444;padding:3px 0}}
.bb-price-row b{{font-weight:700;color:var(--ink)}}
.bb-price-total{{display:flex;justify-content:space-between;align-items:baseline;border-top:1px solid var(--line);margin-top:8px;padding-top:8px;font-family:Montserrat;font-weight:800;text-transform:uppercase;letter-spacing:.02em;font-size:14px}}
.bb-price-total b{{font-size:22px;color:var(--orange)}}
.bb-price-note{{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.45}}
.bb-you{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}}
@media(max-width:420px){{.bb-you{{grid-template-columns:1fr}}}}
.bb-in{{width:100%;border:1.5px solid var(--line);border-radius:10px;padding:10px 12px;font-size:13.5px;font-family:inherit;background:#fff;box-sizing:border-box}}
.bb-in:focus{{outline:0;border-color:var(--orange)}}
.bb-cta .ctabig{{padding:12px;font-size:13px;letter-spacing:.05em;border-radius:11px;gap:8px}}
.bb-cta .ctacall{{padding:10px;font-size:12px;letter-spacing:.05em;border-radius:11px;background:#fff;color:var(--orange);border:1.5px solid var(--orange)}}
.bb-cta .ctacall:hover{{background:#fff7ef}}
.bb-cta .ctarsv{{border:0;background:none;padding:8px 4px;margin-top:4px;text-transform:none;letter-spacing:0;font-size:12.5px;font-weight:600;color:var(--muted);text-align:center}}
.bb-cta .ctarsv:hover{{color:var(--orange)}}
.bb-cta .ctabig,.bb-cta .ctacall,.bb-cta .ctarsv{{margin-top:8px}}
.bb-stage{{cursor:zoom-in}}
.bb-zoomhint{{position:absolute;right:12px;bottom:12px;background:rgba(26,18,16,.72);color:#fff;font-size:11px;font-weight:700;padding:5px 11px;border-radius:20px;z-index:2;pointer-events:none}}
.bb-swatch{{cursor:zoom-in}}
.bb-hb{{position:relative}}
.bb-zbtn{{position:absolute;top:4px;right:4px;width:24px;height:24px;border:0;border-radius:50%;background:rgba(26,18,16,.55);color:#fff;font-size:13px;line-height:24px;text-align:center;cursor:zoom-in;z-index:3;padding:0}}
.bb-zbtn:hover{{background:rgba(26,18,16,.85)}}
#bbZoom{{position:fixed;inset:0;background:rgba(18,14,12,.9);display:none;flex-direction:column;align-items:center;justify-content:center;z-index:99999;padding:24px;cursor:zoom-out}}
#bbZoom:not([hidden]){{display:flex}}
#bbZoom img{{max-width:94vw;max-height:84vh;border-radius:12px;box-shadow:0 24px 70px rgba(0,0,0,.55);background:#fff;object-fit:contain}}
#bbZoomCap{{color:#fff;font-weight:700;font-size:15px;margin-top:16px;letter-spacing:.02em;text-align:center}}
#bbZoomX{{position:fixed;top:16px;right:24px;color:#fff;font-size:34px;line-height:1;cursor:pointer;font-weight:300}}
</style>
<div class="wrap">
<div class="crumb"><a href="/">Home</a> / <b>Build Your Bed</b></div>
<div class="page-head"><h1>Build Your Bed</h1><div class="count">Design your bed — pick the size, base, fabric and headboard, and watch it change colour with a live price. Handcrafted to order by Aurora in Ireland — send us your combination to order.</div></div>
<div class="bb">
  <div class="bb-preview">
    <div class="bb-stage">
      <canvas id="bbCanvas" width="1000" height="1000"></canvas>
      <img id="bbFeat" class="bb-feat" src="/assets/img/base-ottoman.jpg" alt="Ottoman lift-up storage">
      <div class="bb-tag" id="bbTag">Ottoman storage base</div>
      <div class="bb-zoomhint">⤢ Tap to zoom</div>
    </div>
    <div class="bb-chosen">
      <div class="bb-swatch" id="bbSwatch" style="--img:url('/assets/img/swatch-{DEFAULT_SLUG}.jpg')"></div>
      <div><div class="bb-chosen-name" id="bbName">Plush Velvet — Charcoal</div><div class="bb-chosen-sub" id="bbSub">Ottoman Storage Bed · King 5′</div></div>
    </div>
    <div class="bb-note">The bed and headboards below all preview in your chosen fabric colour on real Aurora pieces; the inset shows the ottoman lift. Every bed is upholstered to order — call in to Church Street to feel the swatches in person.</div>
    <img id="srcDivan" src="/assets/img/base-standard-divan.jpg" hidden alt="">
    <img id="srcDrawer" src="/assets/img/base-standard-drawer.jpg" hidden alt="">
    <img id="mskDivan" src="/assets/img/mask-divan.png" hidden alt="">
    <img id="mskDrawer" src="/assets/img/mask-drawer.png" hidden alt="">
    {hb_srcs}
  </div>
  <div class="bb-controls">
    <div class="bb-step"><h3><span class="bb-num"></span> · Choose your size</h3><div class="bb-sizes" id="bbSizes">{size_btns}</div></div>
    <div class="bb-step"><h3><span class="bb-num"></span> · Choose your base</h3><div class="bb-bases">{base_btns}</div></div>
    <div class="bb-step" id="bbDrawerStep" hidden>
      <h3><span class="bb-num"></span> · Add drawers</h3>
      <div class="hint">Up to 2 drawers each side · €{DRAWER_PRICE} per drawer.</div>
      <div class="bb-dwr-side"><span class="lab">Left side</span><div class="bb-dwr-row">{side_btns("L")}</div></div>
      <div class="bb-dwr-side"><span class="lab">Right side</span><div class="bb-dwr-row">{side_btns("R")}</div></div>
    </div>
    <div class="bb-step"><h3><span class="bb-num"></span> · Choose your fabric</h3>{groups}</div>
    <div class="bb-step">
      <h3><span class="bb-num"></span> · Choose your headboard <span style="text-transform:none;font-weight:500;color:var(--muted);font-size:12px">(optional)</span></h3>
      <div class="hint">In-store styles — each shown in your chosen fabric.</div>
      <div class="bb-hbs">{hb_tiles}</div>
      <div id="bbMount" hidden style="margin-top:14px">
        <div class="hint" style="margin-bottom:8px">Fitting:</div>
        <div class="bb-dwr-row">
          <button type="button" class="bb-mount on" data-mount="Strutted">Strutted</button>
          <button type="button" class="bb-mount" data-mount="Floor-standing 54″">Floor-standing 54″</button>
        </div>
      </div>
    </div>
    <div class="bb-cta">
      <div class="bb-summary">Your bed: <b id="bbSum">Ottoman Storage Bed · King 5′ · Plush Velvet — Charcoal</b></div>
      <div class="bb-price">
        <div class="bb-price-row"><span id="bbPrBaseLbl">Base</span><b id="bbPrBase">€—</b></div>
        <div class="bb-price-row" id="bbPrHbRow" hidden><span id="bbPrHbLbl">Headboard</span><b id="bbPrHb">€—</b></div>
        <div class="bb-price-row" id="bbPrDwRow" hidden><span id="bbPrDwLbl">Drawers</span><b id="bbPrDw">€—</b></div>
        <div class="bb-price-total"><span>Estimated total</span><b id="bbPrTotal">€—</b></div>
        <div class="bb-price-note">Guide price — includes your fabric choice. Delivery quoted separately; confirm final price with us when you enquire.</div>
      </div>
      <div class="bb-you">
        <input id="bbYname" class="bb-in" type="text" autocomplete="name" placeholder="Your name">
        <input id="bbContact" class="bb-in" type="text" autocomplete="tel" placeholder="Phone or email">
      </div>
      <a class="ctabig" id="bbWa" href="https://wa.me/{wa}">{WA_SVG} Enquire on WhatsApp</a>
      <a class="ctacall" href="tel:{SHOP['phone_tel']}">Call the shop</a>
      <a class="ctarsv" id="bbForm" href="/enquiry/">Prefer a form? Send an enquiry →</a>
    </div>
  </div>
</div>
</div>
<div id="bbZoom" hidden><span id="bbZoomX">×</span><img id="bbZoomImg" alt="Zoomed preview"><div id="bbZoomCap"></div></div>
<script>
(function(){{
  var SW={sw_json}, HBS={hb_json}, DP={DRAWER_PRICE};
  var HB_FLOOR=['winged','sorrento','framed'];  // floor-standing only — no 27" strutted option
  // Aurora price card (David's in-store prices). Buckets: 3=Single, 46=4'/4'6", 5=King, 6=Super King.
  var PRICE={{
    base:{{ standard:{{'3':149,'46':199,'5':249,'6':279}}, storage:{{'3':419,'46':649,'5':699,'6':799}} }},
    hb:{{ 'Strutted':{{'3':99,'46':129,'5':149,'6':199}}, 'Floor-standing 54″':{{'3':null,'46':219,'5':259,'6':379}} }}
  }};
  var kind="storage", size="King 5′", bucket="5", fabric="Plush Velvet — Charcoal", fslug="{DEFAULT_SLUG}",
      hb="", hbslug="", mount="Strutted", L=0, R=0;
  var canvas=document.getElementById('bbCanvas'), ctx=canvas.getContext('2d',{{willReadFrequently:true}});
  var feat=document.getElementById('bbFeat'), tag=document.getElementById('bbTag'),
      sw=document.getElementById('bbSwatch'), nm=document.getElementById('bbName'),
      sub=document.getElementById('bbSub'), sum=document.getElementById('bbSum'),
      wa=document.getElementById('bbWa'), form=document.getElementById('bbForm'),
      nameEl=document.getElementById('bbYname'), contactEl=document.getElementById('bbContact'),
      dstep=document.getElementById('bbDrawerStep'), mstep=document.getElementById('bbMount');
  function renumber(){{
    var n=1;
    document.querySelectorAll('.bb-step').forEach(function(s){{
      if(s.hidden) return; var el=s.querySelector('.bb-num'); if(el) el.textContent=n++;
    }});
  }}
  // ---- shared recolour engine ----
  function buildBank(imgEl, mskEl, TW, TH){{
    var oc=document.createElement('canvas'); oc.width=TW; oc.height=TH;
    var octx=oc.getContext('2d',{{willReadFrequently:true}});
    function fit(img){{ var iw=img.naturalWidth,ih=img.naturalHeight,s=Math.min(TW/iw,TH/ih);
      var w=iw*s,h=ih*s; octx.drawImage(img,(TW-w)/2,(TH-h)/2,w,h); }}
    octx.fillStyle='#fff'; octx.fillRect(0,0,TW,TH); fit(imgEl);
    var orig=octx.getImageData(0,0,TW,TH);
    octx.fillStyle='#000'; octx.fillRect(0,0,TW,TH); fit(mskEl);
    var md=octx.getImageData(0,0,TW,TH).data;
    var alpha=new Float32Array(TW*TH), lum=new Float32Array(TW*TH), sumL=0, cnt=0, d=orig.data;
    for(var i=0,p=0;i<md.length;i+=4,p++){{
      var a=md[i]/255; alpha[p]=a;
      var l=0.299*d[i]+0.587*d[i+1]+0.114*d[i+2]; lum[p]=l;
      if(a>0.5){{sumL+=l;cnt++;}}
    }}
    return {{orig:orig, alpha:alpha, lum:lum, meanL:(cnt?sumL/cnt:160), w:TW, h:TH}};
  }}
  // fabric family -> how much of the photo's velvet sheen to keep (k) + a subtle
  // micro-texture so matte fabrics don't read as velvet. Swatch tiles stay the real photo.
  var FTEX={{velvet:{{k:1.0,lo:0.40,hi:1.62,tex:0,mode:''}}, soft:{{k:0.80,lo:0.50,hi:1.42,tex:0.03,mode:'cord'}},
    weave:{{k:0.60,lo:0.55,hi:1.30,tex:0.05,mode:'grid'}}, linen:{{k:0.56,lo:0.55,hi:1.28,tex:0.05,mode:'grid'}},
    wool:{{k:0.50,lo:0.60,hi:1.22,tex:0.07,mode:'noise'}}}};
  function fam(s){{
    if(s.indexOf('wool-')===0) return 'wool';
    if(s.indexOf('linoso-')===0) return 'linen';
    if(s.indexOf('matiz-')===0||s.indexOf('alessia-')===0) return 'weave';
    if(s.indexOf('naples-')===0) return 'soft';
    return 'velvet';
  }}
  function ftex(){{ return FTEX[fam(fslug)]; }}
  function recolorInto(cv, b, c, ft){{
    if(!b) return; if(cv.width!==b.w){{cv.width=b.w;cv.height=b.h;}}
    var cx=cv.getContext('2d'); var src=b.orig.data, out=cx.createImageData(b.w,b.h), o=out.data,
        al=b.alpha, lum=b.lum, mL=b.meanL, W=b.w, k=ft.k, tex=ft.tex, mode=ft.mode;
    for(var i=0,p=0;i<o.length;i+=4,p++){{
      var a=al[p];
      if(a<=0.003){{o[i]=src[i];o[i+1]=src[i+1];o[i+2]=src[i+2];o[i+3]=src[i+3];continue;}}
      var r=1+(lum[p]/mL-1)*k; if(r<ft.lo)r=ft.lo; if(r>ft.hi)r=ft.hi;
      if(tex){{ var x=p%W, y=(p/W)|0, t;
        if(mode==='noise'){{ var hsh=((x*73856093)^(y*19349663))>>>0; t=1+(((hsh&255)/255)-0.5)*tex*2; }}
        else if(mode==='cord'){{ t=1+((x%3<1)?tex:-tex*0.5); }}
        else {{ t=1+(((x%4<2)?1:-1)+((y%4<2)?1:-1))*tex*0.5; }}
        r*=t; }}
      var nr=c[0]*r, ng=c[1]*r, nb=c[2]*r;
      o[i]  =src[i]  *(1-a)+(nr>255?255:nr)*a;
      o[i+1]=src[i+1]*(1-a)+(ng>255?255:ng)*a;
      o[i+2]=src[i+2]*(1-a)+(nb>255?255:nb)*a;
      o[i+3]=255;
    }}
    cx.putImageData(out,0,0);
  }}
  var bank={{}}, hbBank={{}}, bigBank={{}};
  function baseKey(){{ return (kind==='standard' && (L+R)>0) ? 'drawer' : 'divan'; }}
  function bigHbBank(slug){{
    if(bigBank[slug]) return bigBank[slug];
    var img=document.getElementById('hbsrc-'+slug), msk=document.getElementById('hbmsk-'+slug);
    if(!img||!img.naturalWidth) return null;
    bigBank[slug]=buildBank(img,msk,1000,1000); return bigBank[slug];  // headboard fit on white 1000²
  }}
  function paintPreview(){{
    // once a headboard is chosen, show a big picture of it (recoloured); else the base
    if(hbslug){{ var b=bigHbBank(hbslug); if(b){{ recolorInto(canvas, b, SW[fslug]||[150,150,150], ftex()); return; }} }}
    recolorInto(canvas, bank[baseKey()], SW[fslug]||[150,150,150], ftex());
  }}
  function paintBase(){{ paintPreview(); }}
  function paintHeadboards(){{
    var c=SW[fslug]||[150,150,150], ft=ftex();
    HBS.forEach(function(s){{
      var b=hbBank[s]; if(!b) return;
      var cv=document.querySelector('.bb-hbcanvas[data-slug="'+s+'"]'); if(cv) recolorInto(cv,b,c,ft);
    }});
  }}
  function refresh(skipPaint){{
    var storage=kind==='storage', d=(kind==='standard'?(L+R):0);
    dstep.hidden=storage; feat.style.display=(storage&&!hbslug)?'':'none'; mstep.hidden=(hb==='');
    var floorOnly=HB_FLOOR.indexOf(hbslug)>=0;   // Winged/Sorrento/Framed: floor-standing only
    var strutBtn=document.querySelector('.bb-mount[data-mount="Strutted"]');
    if(strutBtn) strutBtn.style.display=floorOnly?'none':'';
    if(floorOnly && mount!=='Floor-standing 54″'){{ mount='Floor-standing 54″';
      document.querySelectorAll('.bb-mount').forEach(function(x){{x.classList.toggle('on',x.dataset.mount===mount);}}); }}
    renumber();
    var baseLabel=storage?'Ottoman Storage Bed':'Standard Bed';
    tag.textContent=hbslug?(hb+' headboard'):(storage?'Ottoman storage base':(d>0?'Standard base + drawers':'Standard divan base'));
    nm.textContent=fabric; sub.textContent=baseLabel+' · '+size;
    var cost=d*DP;
    var extra=(!storage&&d>0)?(' · '+d+' drawer'+(d>1?'s':'')+' (+€'+cost+')'):(storage?' · lift-up storage':'');
    var hbTxt=hb?(' · '+hb+' headboard'+(mount!=='Strutted'?' ('+mount+')':'')):'';
    sum.textContent=baseLabel+' · '+size+' · '+fabric+extra+hbTxt;
    // ---- live price (Aurora price card) ----
    var basePrice=PRICE.base[storage?'storage':'standard'][bucket];
    var hbPrice=hb?PRICE.hb[mount][bucket]:0;   // null = floor-standing not made in Single
    var hbNA=hb&&(hbPrice===null||hbPrice===undefined);
    var total=basePrice+(hbNA?0:(hbPrice||0))+cost;
    function eur(n){{ return '€'+n.toLocaleString('en-IE'); }}
    document.getElementById('bbPrBaseLbl').textContent=(storage?'Storage base':'Standard base')+' · '+size;
    document.getElementById('bbPrBase').textContent=eur(basePrice);
    var hbRow=document.getElementById('bbPrHbRow'); hbRow.hidden=!hb;
    if(hb){{ document.getElementById('bbPrHbLbl').textContent=hb+(mount!=='Strutted'?' (floor-standing)':'')+' headboard';
      document.getElementById('bbPrHb').textContent=hbNA?'Ask us':eur(hbPrice); }}
    var dwRow=document.getElementById('bbPrDwRow'); dwRow.hidden=!(d>0);
    if(d>0){{ document.getElementById('bbPrDwLbl').textContent=d+' drawer'+(d>1?'s':'')+' (€'+DP+' each)';
      document.getElementById('bbPrDw').textContent=eur(cost); }}
    document.getElementById('bbPrTotal').textContent=eur(total)+(hbNA?' +':'');
    var priceTxt=eur(total)+(hbNA?' + headboard (price on request)':'');
    var who=(nameEl.value||'').trim(), contact=(contactEl.value||'').trim();
    var spec=baseLabel+' — '+size+' — '+fabric+(!storage&&d>0?(' — '+d+' drawers'):'')+(hb?(' — '+hb+' headboard ('+mount+')'):'');
    var msg='Hi, I\\'m interested in this bed:\\n'+baseLabel+'\\nSize: '+size+'\\nFabric: '+fabric;
    if(!storage) msg+='\\nDrawers: '+d+(d>0?(' (+€'+cost+')'):'');
    msg+='\\nHeadboard: '+(hb?(hb+' ('+mount+')'+(hbNA?' — price on request':'')):'None');
    msg+='\\nEstimated total: '+priceTxt;
    if(who) msg+='\\nName: '+who;
    if(contact) msg+='\\nContact: '+contact;
    wa.href='https://wa.me/{wa}?text='+encodeURIComponent(msg);
    form.href='/enquiry/?product='+encodeURIComponent(spec)
      +(who?('&name='+encodeURIComponent(who)):'')+(contact?('&contact='+encodeURIComponent(contact)):'')
      +'&msg='+encodeURIComponent('Build a Bed — '+spec+'. Estimated total: '+priceTxt+'.');
    if(!skipPaint) paintBase();
  }}
  // ---- controls ----
  document.querySelectorAll('.bb-size').forEach(function(b){{b.addEventListener('click',function(){{
    document.querySelectorAll('.bb-size').forEach(function(x){{x.classList.remove('on')}}); b.classList.add('on');
    size=b.dataset.size; bucket=b.dataset.bucket; refresh();}});}});
  document.querySelectorAll('.bb-base').forEach(function(b){{b.addEventListener('click',function(){{
    document.querySelectorAll('.bb-base').forEach(function(x){{x.classList.remove('on')}}); b.classList.add('on');
    kind=b.dataset.kind;
    if(kind==='storage'){{L=0;R=0;document.querySelectorAll('.bb-dwr').forEach(function(x){{x.classList.toggle('on', x.dataset.n==='0');}});}}
    refresh();}});}});
  document.querySelectorAll('.bb-dwr').forEach(function(b){{b.addEventListener('click',function(){{
    var side=b.dataset.side;
    document.querySelectorAll('.bb-dwr[data-side="'+side+'"]').forEach(function(x){{x.classList.remove('on')}}); b.classList.add('on');
    if(side==='L')L=+b.dataset.n; else R=+b.dataset.n; refresh();}});}});
  document.querySelectorAll('.bb-sw').forEach(function(b){{b.addEventListener('click',function(){{
    document.querySelectorAll('.bb-sw').forEach(function(x){{x.classList.remove('on')}}); b.classList.add('on');
    fabric=b.dataset.name; fslug=b.dataset.slug;
    sw.style.setProperty('--img', getComputedStyle(b).getPropertyValue('--img'));
    paintHeadboards(); refresh();}});}});
  document.querySelectorAll('.bb-hb').forEach(function(b){{b.addEventListener('click',function(){{
    document.querySelectorAll('.bb-hb').forEach(function(x){{x.classList.remove('on')}}); b.classList.add('on');
    hb=b.dataset.hb; hbslug=b.dataset.slug; refresh();}});}});
  document.querySelectorAll('.bb-mount').forEach(function(b){{b.addEventListener('click',function(){{
    document.querySelectorAll('.bb-mount').forEach(function(x){{x.classList.remove('on')}}); b.classList.add('on');
    mount=b.dataset.mount; refresh();}});}});
  [nameEl,contactEl].forEach(function(el){{ el.addEventListener('input',function(){{ refresh(true); }}); }});
  // ---- zoom / lightbox ----
  var zoom=document.getElementById('bbZoom'), zoomImg=document.getElementById('bbZoomImg'), zoomCap=document.getElementById('bbZoomCap');
  function openZoom(src,cap){{ zoomImg.src=src; zoomCap.textContent=cap||''; zoom.hidden=false; }}
  function closeZoom(){{ zoom.hidden=true; zoomImg.removeAttribute('src'); }}
  zoom.addEventListener('click',closeZoom);
  document.getElementById('bbZoomX').addEventListener('click',closeZoom);
  document.addEventListener('keydown',function(e){{ if(e.key==='Escape') closeZoom(); }});
  document.querySelector('.bb-stage').addEventListener('click',function(e){{
    if(e.target===feat){{ openZoom(feat.src,'Ottoman lift-up storage'); return; }}
    openZoom(canvas.toDataURL('image/jpeg',0.92), hbslug?(hb+' — '+fabric):(fabric+' · '+(kind==='storage'?'Ottoman':'Standard')+' base')); }});
  sw.addEventListener('click',function(){{
    var v=getComputedStyle(sw).getPropertyValue('--img').trim();
    var s2=v.slice(v.indexOf('(')+1, v.lastIndexOf(')')).replace(/['"]/g,'').trim();
    if(s2) openZoom(s2, fabric); }});
  function zoomHeadboardSrc(slug){{
    var img=document.getElementById('hbsrc-'+slug), msk=document.getElementById('hbmsk-'+slug);
    var W2=Math.min(900,img.naturalWidth), H2=Math.round(img.naturalHeight*W2/img.naturalWidth);
    var b=buildBank(img,msk,W2,H2);
    var oc=document.createElement('canvas'); recolorInto(oc,b,SW[fslug]||[150,150,150],ftex());
    return oc.toDataURL('image/jpeg',0.92);
  }}
  document.querySelectorAll('.bb-hb .bb-zbtn').forEach(function(btn){{ btn.addEventListener('click',function(e){{
    e.stopPropagation(); var tile=btn.closest('.bb-hb'); var slug=tile.dataset.slug;
    openZoom(zoomHeadboardSrc(slug), tile.dataset.hb+' — '+fabric); }}); }});
  // ---- load images then first paint ----
  function onImg(img, cb){{ if(img.complete && img.naturalWidth) cb(); else img.onload=cb; }}
  var pending=0, started=false;
  function done(){{ if(started && pending<=0) refresh(); }}
  // base banks
  [['divan','srcDivan','mskDivan'],['drawer','srcDrawer','mskDrawer']].forEach(function(t){{
    pending++; var img=document.getElementById(t[1]), msk=document.getElementById(t[2]), n=0;
    function tb(){{ if(++n>=2){{ bank[t[0]]=buildBank(img,msk,img.naturalWidth,img.naturalHeight); pending--; done(); }} }}
    onImg(img,tb); onImg(msk,tb);
  }});
  // headboard banks (normalised 300x200 tiles)
  HBS.forEach(function(s){{
    pending++; var img=document.getElementById('hbsrc-'+s), msk=document.getElementById('hbmsk-'+s), n=0;
    function tb(){{ if(++n>=2){{ hbBank[s]=buildBank(img,msk,300,200);
      var cv=document.querySelector('.bb-hbcanvas[data-slug="'+s+'"]'); if(cv) recolorInto(cv,hbBank[s],SW[fslug],ftex());
      pending--; done(); }} }}
    onImg(img,tb); onImg(msk,tb);
  }});
  started=true; done();
}})();
</script>
{footer()}"""
    write("build-a-bed/index.html", head(f"Build Your Bed | {SHOP['name']}",
        "Design your Aurora bed — pick size, base (ottoman storage or standard with drawers), fabric and headboard, and watch it change colour. Handcrafted to order, at Eddie Maguire, Dundalk.",
        path="/build-a-bed/") + body)
    print("  build-a-bed: 1 page")

def build_pages():
    # Content pages from content/pages/*.md (yaml-frontmatter markdown, CMS-editable).
    n = 0
    pdir = ROOT / "content" / "pages"
    order = ["about-us", "delivery-returns", "returns-replacements", "terms-and-conditions", "privacy-policy"]
    def render_md(f):
        raw = f.read_text(encoding="utf-8")
        title = f.stem.replace("-", " ").title()
        body_md = raw
        m = re.match(r'^﻿?---\s*\n(.*?)\n---\s*\n(.*)$', raw, re.S)
        if m:
            tm = re.search(r'^\s*title:\s*(.+?)\s*$', m.group(1), re.M)
            if tm: title = tm.group(1).strip().strip('"\'')
            body_md = m.group(2)
        content_html = md_to_html(body_md.strip())
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", content_html)).strip()[:155]
        render_prose_page(slugify(f.stem), title, content_html, desc or title)
    seen = set()
    if pdir.exists():
        for slug in order:
            f = pdir / (slug + ".md")
            if f.exists(): render_md(f); seen.add(f.name); n += 1
        for f in sorted(pdir.glob("*.md")):
            if f.name not in seen: render_md(f); n += 1
    build_contact(); n += 1
    build_enquiry(); n += 1
    print(f"  content pages: {n} pages (content/pages/*.md + contact + enquiry)")

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
    paths += [f"/{s}/" for s in ("build-a-bed", "about-us", "contact-us", "enquiry", "delivery-returns",
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
    for d in ("product", "category", "product-category", "about-us", "contact-us", "enquiry",
              "delivery-returns", "returns-replacements", "terms-and-conditions",
              "privacy-policy", "build-a-bed"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    print("Building catalogue…")
    build_home()
    build_category_index()
    build_categories()
    build_products()
    build_pages()
    build_bedbuilder()
    build_redirects()
    build_sitemap()
    apply_base(os.environ.get("BASE_PATH", ""))
    print("Done.")
