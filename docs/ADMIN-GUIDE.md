# Eddie Maguire — Product Admin Guide

The site now has a **visual admin panel** (Pages CMS) where David can edit
products — change a price, swap a photo, hide something out of stock — with no
code and no waiting on Megan. Saves go live automatically in ~2 minutes.

---

## Part 1 — One-time setup (Megan, ~10 minutes)

Do these once to switch it on. All in a web browser.

1. **Give David a login.**
   - David creates a free account at **github.com** (any email; no payment).
   - In the EME repo → **Settings → Collaborators → Add people** → add David's
     GitHub username → role **Write**. He accepts the email invite.

2. **Connect the admin.**
   - Go to **app.pagescms.org** and sign in with GitHub.
   - Authorize it for the **meganpowellsquawkmedia/EME** repository only.
   - It reads the `.pages.yml` file already in the repo and shows the
     **Products** list automatically. David does the same sign-in once.

3. **Turn on auto-publish** (one file — has to be added from GitHub's website,
   not by the tooling, for security reasons):
   - In the EME repo click **Add file → Create new file**.
   - Name it exactly: `.github/workflows/build.yml`
   - Paste in the contents of **`docs/build.yml.txt`** (in this repo).
   - Click **Commit changes**.
   - This is what rebuilds and publishes the site whenever David saves.

4. **That's it.** Any save in the admin now publishes itself in ~2 minutes.

> Tip: bookmark **app.pagescms.org** for David. After the first sign-in it
> remembers him — one click to get in.

---

## Part 2 — Using the admin (David)

1. Go to **app.pagescms.org** and click **Sign in with GitHub**.
2. Open **Products**. You'll see a searchable list — type a model number or
   name to find something.
3. Click a product to edit it:
   - **Price (€)** — just the number (e.g. `599` or `129.99`).
   - **Photo** — click to upload a new image from your computer.
   - **Product name / Model number / Description** — edit the text.
   - **Hide from website** — toggle on to take something off the site
     (e.g. sold out) without deleting it. Toggle off to bring it back.
4. Click **Save**. Done — the change appears on the live site in ~2 minutes.

**To take a product off the site:** open it, switch **Hide from website** on,
Save. (Nothing is lost — flip it back any time.)

---

## How it works (for reference)

- Each product is a small file in `content/products/<id>.json`.
- Saving in the admin commits that file to GitHub.
- A GitHub Action rebuilds the static site and publishes it — no server, no
  monthly cost, nothing that can be hacked.
- Prices/photos/text are all edited here now; the old spreadsheet override
  files (`price_overrides.csv` etc.) are retired.

## Adding a brand-new product

Best done with Megan for now: new items need a unique **Internal ID** and a
**Category** picked from the existing list. Editing existing products (price,
photo, hide) is the everyday self-serve job and needs none of that.
