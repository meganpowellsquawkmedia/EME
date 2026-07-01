# Eddie Maguire's — Website Project Context

## What This Project Is
A static single-file website for **Eddie Maguire's Home & Electrical**, an independent electronics and furniture store in Dundalk, Ireland. Built in pure HTML/CSS/JS, hosted on GitHub Pages. No ecommerce, no CMS, no backend — just a catalogue/brochure site where customers browse and enquire via WhatsApp.

## Live Site & Repo
- **Live URL:** https://meganpowellsquawkmedia.github.io/EME/
- **Repo:** meganpowellsquawkmedia/EME
- **Main file:** index.html (single file — everything lives here)
- **Domain to point here eventually:** eddiemaguires.ie

## Business Details
- **Business name:** Eddie Maguire's Home & Electrical
- **Address:** 29 Church St, Dundalk, Co. Louth
- **Phone:** 042 933 2043
- **Email:** info@eddiemaguire.ie
- **WhatsApp:** 089 977 6472 (international: +353899776472)
- **Opening hours:** Mon–Fri 9am–6pm | Saturday 9am–5:30pm | Sunday & Bank Holidays: Closed
- **Part of Expert Ireland network** (but do NOT use Expert branding/logos on the site)

## Brand & Design
- **Primary colour:** #E8720C (orange)
- **Dark background:** #1A1210 (near-black)
- **Secondary dark:** #2A1E1A, #221612, #2E2320
- **Text:** #EDE8E3 (almost white)
- **Muted text:** #E8E2DC
- **Heading font:** Montserrat (700, 800, 900)
- **Body font:** Inter (300, 400, 500)
- **Overall feel:** Dark, bold, modern — think premium local retailer, not cheap electrical chain

## Logo
- Logo is embedded as base64 in index.html (no external file dependency)
- Orange house + plug icon on transparent background
- Text in header reads "Eddie Maguire's" with subtitle "Home & Electrical"
- ALL images and logos should be base64 embedded — no external file references

## Site Structure (Planned)
### Done ✅
- Homepage (index.html) — hero, ticker, category grid, gifts section, WhatsApp strip, about section, footer
- Scrolling ticker strip in orange below header

### To Build ❌
- Mobile hamburger menu (currently doesn't open/close)
- Category pages: Furniture, Home Appliances, Technology, TVs & Audio, Small Appliances, Garden
- Gifts pages: For Him, For Her
- About page
- Contact page
- Each category page needs product grid: photo + name + price

## Product Categories & Subcategories
- **Furniture** → Living, Bedroom, Dining, Occasional
- **Home Appliances** → Washing Machines, Dishwashers, Fridge Freezers, Ovens & Hobs
- **TVs & Audio** → TVs, Audio & Radio, Headphones
- **Technology** → Mobile Phones, Tablets, Laptops, Smarthome
- **Small Appliances** → Kettles & Toasters, Coffee Machines, Irons, Microwaves, Air Fryers
- **Garden** → Lawnmowers, BBQs, Hedgecutters
- **Gifts** → For Him, For Her (pulls from existing categories — not separate products)

## Key Decisions Made
- NO online ordering or ecommerce — catalogue only
- WhatsApp button is the primary CTA throughout
- Gifts section pulls from existing product categories (not separate stock)
- Images should be base64 embedded, not external URLs
- Unsplash placeholder images are still in use — need replacing with real photos
- Supplier for some furniture: Parisot (and others via Forever Furniture trading name)
- Do NOT mention Forever Furniture on the site

## Customer Profile
- Primarily women, aged 25–60
- Local Dundalk area
- Browse-first, then enquire — not impulse buyers
- Digestible layouts, warm feel, easy navigation

## Ticker Strip Content
```
Beds, Sofas & Dining
Nespresso & Bean-to-Cup Coffee
The Latest Samsung & Telefunken TVs
Washing Machines & Dishwashers
iPhones, Androids & Tablets
BBQs, Lawnmowers & More
Kettles, Irons & Air Fryers
Hollywood Mirrors & Dressing Tables
Laptops & Smart Home Tech
100% Irish — 29 Church St, Dundalk
```

## Workflow Notes
- Megan manages the site (web content editor at Squawk Media)
- David is the store owner — needs to approve designs before full build-out
- Changes go live via git push to main branch
- To deploy: `git add . && git commit -m "description" && git push`
- GitHub Pages auto-deploys within ~60 seconds of push
