#!/usr/bin/env bash
# Pulls all content from the live WooCommerce/WordPress site into content/raw/.
# Reproducible: re-run anytime to refresh the snapshot (e.g. just before cutover).
# Usage: WP_APP_PW="xxxx ...." ./tools/fetch_wp.sh
set -euo pipefail

SITE="https://eddiemaguire.ie"
USER="david"
: "${WP_APP_PW:?Set WP_APP_PW env var to the application password}"
AUTH="$USER:$WP_APP_PW"

OUT="$(cd "$(dirname "$0")/.." && pwd)/content/raw"
mkdir -p "$OUT"

# Fetch every page of a paginated endpoint into one JSON array file.
fetch_all() {
  local label="$1" path="$2" extra="${3:-}"
  local page=1 tmp="$OUT/.$label.tmp"
  : > "$tmp"
  echo "[" > "$OUT/$label.json"
  local first=1
  while : ; do
    local resp
    resp=$(curl -s -u "$AUTH" "$SITE/wp-json/$path?per_page=100&page=$page${extra:+&$extra}")
    # stop on empty array or error object
    local n
    n=$(printf '%s' "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d) if isinstance(d,list) else -1)" 2>/dev/null || echo -1)
    if [ "$n" -le 0 ]; then break; fi
    printf '%s' "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print('\n'.join(json.dumps(x) for x in d))" >> "$tmp"
    echo "  $label page $page -> $n items"
    if [ "$n" -lt 100 ]; then break; fi
    page=$((page+1))
  done
  # join newline-delimited objects into a JSON array
  python3 -c "
import sys,json
objs=[json.loads(l) for l in open('$tmp') if l.strip()]
json.dump(objs, open('$OUT/$label.json','w'), indent=2, ensure_ascii=False)
print(f'  => $label.json: {len(objs)} total')
"
  rm -f "$tmp"
}

echo '== Fetching content =='
fetch_all products            "wc/v3/products"            "status=publish"
fetch_all product_categories  "wc/v3/products/categories"
fetch_all pages               "wp/v2/pages"               "status=publish,draft,private"
fetch_all posts               "wp/v2/posts"               "status=publish"
fetch_all post_categories     "wp/v2/categories"
echo 'Done.'
