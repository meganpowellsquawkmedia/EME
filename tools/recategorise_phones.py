#!/usr/bin/env python3
"""
Clean up the mis-categorised "Telephones" tree.

WooCommerce had laptops, tablets, dashcams, a dishwasher and a grass trimmer
tagged under Telephones. This splits the real phones into Mobile vs
Landline/Cordless and moves everything else to a sensible category.

Writes content/category_overrides.csv (product_id,category_id,note) which
build.py applies (it replaces that product's categories). Re-run any time.
"""
import json, csv, re, html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "content" / "raw"

P = json.load(open(RAW / "products.json")) + json.load(open(RAW / "supplier_products.json"))
C = json.load(open(RAW / "product_categories.json")) + json.load(open(RAW / "supplier_categories.json"))
byid = {c["id"]: c for c in C}
children = {}
for c in C:
    children.setdefault(c["parent"], []).append(c)

def descendants(cid):
    out = [cid]
    for ch in children.get(cid, []):
        out += descendants(ch["id"])
    return out
TEL = set(descendants(754))  # Telephones tree

# target category ids
MOBILE, LANDLINE = 767, 766          # Mobile Phones / (Corded &) Cordless
DASHCAM, LAPTOPS, TABLETS = 695, 727, 691
DISHWASHERS, GARDEN, TVAUDIO = 698, 1419, 877

# first matching rule wins
RULES = [
    (DISHWASHERS, ["dishwasher"]),
    (GARDEN,      ["grass", "strimmer", "hedge"]),
    (TVAUDIO,     ["aerial"]),
    (DASHCAM,     ["dashcam", "dash cam", "nextbase"]),
    (LAPTOPS,     ["laptop", "vivobook", "tuf gaming", "notebook", "disc drive", "dvd-rw", "dvd rw"]),
    (TABLETS,     ["tablet", "galaxy tab", "redmi pad", " tab ", " pad "]),
    (LANDLINE,    ["cordless", "dect", "corded", "landline", "big button", "big-button",
                   "answer machine", "answering", "senior phone", "ampli", "talkhome",
                   "bigtel", "phoneeasy", "xtra ", "home phone", "boost button", " ds",
                   "combi telephone", "telephone set", "swissvoice s5"]),
    (MOBILE,      ["smartphone", "smart phone", "redmi note", "xiaomi", "honor", "flip phone",
                   "clamshell", "noa ", "hammer", "emporiahappy", "emporiasmart", "emporiajoy",
                   "activeglam", "mobile phone", "5g", "4g"]),
]
# note: LANDLINE before MOBILE so "Swissvoice Xtra" (cordless) and senior corded
# phones aren't caught by the mobile "4g"/"smartphone" keywords.

def classify(name):
    t = f" {name.lower()} "
    for cid, kws in RULES:
        if any(k in t for k in kws):
            return cid
    return MOBILE  # phones tree fallback

rows = []
for p in P:
    pids = {c["id"] for c in p.get("categories", [])}
    if not (pids & TEL):
        continue
    name = html.unescape(p["name"])
    cid = classify(name)
    cur = sorted(pids)
    if [cid] != cur:  # only record real changes
        rows.append([p["id"], cid, html.unescape(byid[cid]["name"]), name[:60]])

with open(ROOT / "content" / "category_overrides.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["product_id", "category_id", "category_name", "product"])
    w.writerows(rows)

from collections import Counter
dist = Counter(r[2] for r in rows)
print(f"wrote {len(rows)} category overrides")
for cat, n in dist.most_common():
    print(f"  {n:>3}  -> {cat}")
