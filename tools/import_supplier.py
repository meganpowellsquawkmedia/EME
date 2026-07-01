#!/usr/bin/env python3
"""
Import the EDL dropship supplier feed (CSV) into the catalogue.

Reads the supplier CSV, drops products we already have (by model number),
auto-categorises the rest into the existing category tree (creating a few new
categories where there's a genuine gap), and writes:
    content/raw/supplier_products.json     (product objects, same shape as WP products)
    content/raw/supplier_categories.json   (any NEW categories created)

build.py merges these in automatically. RRP is used as the selling price.
Trade price is kept (private) for margin reference but never displayed.

Run:  python3 tools/import_supplier.py "/path/to/feed.csv"
"""
import csv, json, re, sys, html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW  = ROOT / "content" / "raw"
CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/meganpowell/Downloads/EDL - Dropship Product List - Online Assets 15.05.26 (1).csv"

def norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
def slugify(s):
    s = html.unescape(s or "").lower()
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)
def money(s):
    m = re.search(r"[\d]+(?:[.,]\d+)?", (s or "").replace(",", ""))
    return m.group(0) if m else ""

# ── existing categories: name/slug -> id (targets for mapping) ────────────────
C = json.load(open(RAW / "product_categories.json"))
cat_by_slug = {c["slug"]: c["id"] for c in C}
cat_name = {c["id"]: html.unescape(c["name"]) for c in C}

# NEW categories we may need (id, name, slug, parent). Parent 0 = top-level.
NEW_CATS = {
    "smartwatches": dict(id=990001, name="Smartwatches", slug="smartwatches", parent=0, count=0),
    "baby-monitors": dict(id=990002, name="Baby Monitors", slug="baby-monitors", parent=0, count=0),
}
def cid(slug_or_new):
    if slug_or_new in cat_by_slug: return cat_by_slug[slug_or_new]
    if slug_or_new in NEW_CATS:    return NEW_CATS[slug_or_new]["id"]
    raise KeyError(slug_or_new)

# ── keyword -> category slug, first match wins (order matters) ────────────────
RULES = [
    # baby first (sleep trainers / nursery / sterilisers / extra baby cams)
    (["baby monitor", "baby unit", "dect baby", "sleep trainer", "night light",
      "steriliser", "sterilizer", "additional camera for dvm", "bottle warmer"], "baby-monitors"),
    (["smartwatch", "smart watch", "fitness tracker", "fitness watch"], "smartwatches"),
    # security cameras / cctv
    (["security camera", "wifi camera", "wi-fi camera", "ip camera", "cctv",
      "smart home security", "doorbell"], "security"),
    # phones (incl. senior / amplified / corded home phones)
    (["smartphone", "smart phone", "mobile phone", "sim free", "sim-free"], "mobile-phones"),
    (["cordless phone", "dect phone", "big button", "big-button", "answer machine",
      "answering machine", "corded phone", "corded home phone", "amplified corded",
      "amplified", "senior phone", "phoneeasy", "bigtel", "combi telephone",
      "home phone", "talkhome", "telephone set", "telephone"], "corded-cordless"),
    # audio
    (["clock radio"], "clock-radios"),
    (["pocket radio"], "pocket-radio"),
    (["turntable", "record player", "vinyl", "entertainment center", "entertainment centre"], "record-players"),
    (["karaoke", "pa system", "p.a.", "soundbar", "bluetooth speaker", "party speaker",
      " speaker", "subwoofer"], "bluetooth-speakers"),
    (["headphone", "earphone", "earbud", "ear bud"], "headphones"),
    (["hi-fi", "hifi", "micro system", "music system", "cd player", "midi system", "boombox"], "hi-fi-systems"),
    (["dab radio", "fm radio", "internet radio", " radio"], "radios"),
    # tv & av accessories
    (["dvd player", "blu-ray", "projector", "aerial", "remote control", "set top box",
      "freeview", "media player"], "tv-and-audio"),
    # kitchen small appliances
    (["microwave"], "microwave"),
    (["air fryer", "deep fryer", "fryer"], "fryers"),
    (["kettle", "toaster"], "kettle-toasters"),
    (["espresso", "coffee machine", "coffee maker", "barista", "bean to cup", "nespresso", " coffee"], "coffee-machines"),
    (["juicer"], "juicers"),
    (["ice cream maker", "gelato", "food slicer", "blender", "food processor", "chopper",
      "hand mixer", "stand mixer", "smoothie", "food prep"], "food-preparation"),
    # garment care vs floor care (order matters: floor care first to catch steam mop)
    (["steam mop", "steam cleaner", "window cleaner", "spot cleaner", "carpet cleaner"], "vacuum"),
    (["steam generator", "garment steamer", "clothes steamer", "handheld steamer",
      "steam iron", "ironing", " iron "], "ironing"),
    (["vacuum", "hoover", "cordless vac", "stick vac", "handheld vac"], "vacuum"),
    (["dehumidifier"], "dehumidifier"),
    (["cooling fan", "tower fan", "desk fan", "pedestal fan"], "fans"),
    # heating incl. heated blankets/throws and stove fires
    (["heated blanket", "heated throw", "electric blanket", "heated under", "heated wearable",
      "stove fire", "electric fire", "fire stove", "log effect", "heater", "radiator",
      "convector", "fan heater", "oil filled"], "heating"),
    # refrigeration
    (["wine cooler", "beverage cooler", "drinks cooler", "wine fridge"], "undercounter"),
    (["table top freezer", "chest freezer", "box freezer", "freezer"], "box-freezers"),
    (["table top fridge", "larder fridge", "mini fridge", "fridge"], "undercounter"),
    # personal care / health
    (["shaver", "hair clipper", "hair dryer", "hair straightener", "trimmer", "epilator",
      "toothbrush", "massage", "blood pressure", "thermometer", " scale", "foot spa"], "personal-care"),
    # lighting
    (["desk lamp", "table lamp", " lamp", "torch", "head torch", "flashlight", "lantern"], "lamps"),
    # garden
    (["garden hose", "hose", "planter", "trellis", "lawn", "garden"], "home-and-garden"),
    # cookware / kitchenware (teapots, pots, flasks, urns, mills, sets)
    (["saucepan", "frying pan", "frypan", "cookware", "knife", "knives", "cutlery",
      "utensil", "colander", "chopping board", "bakeware", "roaster", "stockpot",
      "wok", "casserole", "teapot", "milk pot", "sauce pot", "pepper mill",
      "salt and pepper", "salt & pepper", "food flask", "flask", "catering urn",
      "urn", "thermos", "cookware set", "pan set"], "cookware"),
]
DEFAULT = "small-appliances"  # catch-all

def categorise(name, brand):
    t = f" {name.lower()} "
    for kws, slug in RULES:
        if any(k in t for k in kws):
            return slug
    return DEFAULT

# ── existing products: model index for dedupe ────────────────────────────────
P = json.load(open(RAW / "products.json"))
ours_blob = " ".join(norm(p["name"]) + norm(p["slug"]) for p in P)
ours_slugs = {p["slug"] for p in P}

# ── read feed ────────────────────────────────────────────────────────────────
rows = [x for x in csv.DictReader(open(CSV_PATH, newline="", encoding="utf-8-sig", errors="replace"))]
img_cols = [f"Image {i}" for i in range(1, 26)]

products, used_slugs, cat_counts = [], set(ours_slugs), {}
skipped_existing = 0
for i, x in enumerate(rows):
    name = (x.get("Name") or "").strip()
    if not name:
        continue
    model = norm(x.get("Model No.", ""))
    if model and len(model) >= 4 and model in ours_blob:
        skipped_existing += 1
        continue

    slug = slugify(name) or f"edl-{model}"
    base = slug; n = 2
    while slug in used_slugs:
        slug = f"{base}-{n}"; n += 1
    used_slugs.add(slug)

    imgs = [{"src": x[c].strip()} for c in img_cols if x.get(c, "").strip()]
    rrp = money(x.get("RRP", ""))
    try: instock = int(re.sub(r"[^\d]", "", x.get("In Stock", "0")) or 0)
    except: instock = 0
    try: incoming = int(re.sub(r"[^\d]", "", x.get("Incoming  Stock", "0")) or 0)
    except: incoming = 0
    stock = "instock" if instock > 0 else ("onbackorder" if incoming > 0 else "outofstock")

    cslug = categorise(name, x.get("Brand", ""))
    cat_counts[cslug] = cat_counts.get(cslug, 0) + 1
    catid = cid(cslug)

    products.append({
        "id": 800000 + i,
        "name": name,
        "slug": slug,
        "price": rrp,
        "regular_price": rrp,
        "sale_price": "",
        "stock_status": stock,
        "sku": x.get("Model No.", "").strip(),
        "categories": [{"id": catid, "name": cat_name.get(catid) or NEW_CATS.get(cslug, {}).get("name", "")}],
        "images": imgs,
        "description": (x.get("Long Description") or x.get("Short & Long Description") or "").strip(),
        "short_description": (x.get("Short Description") or "").strip(),
        "brands": [x.get("Brand", "").strip()] if x.get("Brand", "").strip() else [],
        "_source": "supplier",
        "_ean": x.get("EAN", "").strip(),
        "_trade_price": money(x.get("Trade price", "")),
    })

# only keep new categories that actually got products
new_cats_used = [v for k, v in NEW_CATS.items() if cat_counts.get(k)]

json.dump(products, open(RAW / "supplier_products.json", "w"), indent=2, ensure_ascii=False)
json.dump(new_cats_used, open(RAW / "supplier_categories.json", "w"), indent=2, ensure_ascii=False)

print(f"imported {len(products)} new products (skipped {skipped_existing} already in catalogue)")
print(f"new categories created: {[c['name'] for c in new_cats_used] or 'none'}")
print("\ncategory distribution:")
for slug, n in sorted(cat_counts.items(), key=lambda kv: -kv[1]):
    print(f"  {n:>4}  {slug}")
