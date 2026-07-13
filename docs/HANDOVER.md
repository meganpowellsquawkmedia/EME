# EME — Session Handover (2026-07-13)

Quick state + next steps for whoever picks this up. Deep detail lives in the
assistant's memory files; this is the fast orientation.

## Where the site is
Live: https://meganpowellsquawkmedia.github.io/EME/ (GitHub Pages, `/EME/` subpath).
Deploy: **automatic** — pushing anything under `content/**`, `assets/**`, `tools/**`,
or `.pages.yml` triggers `.github/workflows/build.yml` ("Rebuild & deploy site"),
which runs `BASE_PATH=/EME python3 tools/build.py` and commits the output. Confirmed
working. **You no longer manually build+commit HTML** — just edit data and push.

## Data model (IMPORTANT — changed)
- Source of truth = **one file per product**: `content/products/<id>.json`.
  `tools/build.py` reads these. The old `content/raw/*.json` dumps and the CSV
  overrides (`price_overrides.csv`, `category_overrides.csv`, `removed_products.csv`)
  are **retired/archive only**. Edit a product = edit its JSON (or use the admin).
- `"hidden": true` on a product = removed from the site.

## Admin panel (Pages CMS) — DONE & live
- David logs into **app.pagescms.org** → Products → edits price/photo/name/hide → Save
  → auto-publishes in ~2 min. Config is `.pages.yml`. Guide: `docs/ADMIN-GUIDE.md`.
- The Pages CMS *shell* can't be reskinned (hosted app). Editing UX is tunable via
  `.pages.yml`. Deeper UX tweaks (single `image` field, category dropdown, hiding
  internal fields) need a small schema+build refactor — see the `eme-admin-panel`
  memory for specifics + the multi-category caveat. Do these at the START of a session.

## Departments live (all stock-verified, priced)
Home Appliances (fridges, dishwashers, cookers, washing machines, dryers),
Mobile Phones (own dept), Technology → Landline & Cordless Phones. ~220 products.
Everything else was pulled off (unverified) — add back per stock take.

## Open to-dos
1. **Photos: 141/220 done, ~79 on placeholders.** The rest need David's EDL/Expert
   supplier portal (iPhones by colour, obscure landlines, Irish-brand appliances).
   When he sends them: save as `<model>.jpg` in ~/Downloads → import loop, or set
   `images[0].src` in the product JSON. Sourcing playbook: `eme-photo-sources` memory.
2. **New departments** (TVs, small appliances, furniture, garden) — same workflow:
   photograph the EasyRetail stock take → assistant transcribes to a check-sheet →
   Megan verifies prices → build. See any of the `eme-*-stock` memories for the pattern.
3. **Business name** — site says "Electrical & Furniture"; Megan chose to keep it
   (furniture + phones coming). No action unless she changes her mind.
4. **Custom domain** — company owns eddiemaguire.ie (Letshost). Pointing it at Pages
   drops the `/EME/` hack. When done: in `tools/build.py` set
   `LIVE_ORIGIN = "https://eddiemaguire.ie"` and drop BASE_PATH (see `eme-seo-redirects`).

## Also built this stretch
New appliance hero, tidy 7→ department menus, SEO layer (WhatsApp/OG previews,
sitemap, JSON-LD structured data, favicon), 301 redirects for old WP URLs.
