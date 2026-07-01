/* Client-side category filtering: brand chips + price min/max + sort. */
(function () {
  var filters = document.querySelector('.filters');
  var grid = document.getElementById('grid');
  if (!filters || !grid) return;

  var cards = Array.prototype.slice.call(grid.querySelectorAll('.product-card'));
  var order = cards.slice();                       // original ("Featured") order
  var bchips = Array.prototype.slice.call(filters.querySelectorAll('[data-b]'));
  var cchips = Array.prototype.slice.call(filters.querySelectorAll('[data-c]'));
  var chips = bchips.concat(cchips);
  var fmin = document.getElementById('fmin');
  var fmax = document.getElementById('fmax');
  var fsort = document.getElementById('fsort');
  var fcount = document.getElementById('fcount');
  var fclear = document.getElementById('fclear');

  function priceOf(card) {
    var p = parseFloat(card.getAttribute('data-price'));
    return isNaN(p) ? Infinity : p;
  }

  function apply() {
    var activeB = bchips.filter(function (c) { return c.classList.contains('on'); })
                        .map(function (c) { return c.getAttribute('data-b'); });
    var activeC = cchips.filter(function (c) { return c.classList.contains('on'); })
                        .map(function (c) { return c.getAttribute('data-c'); });
    var lo = parseFloat(fmin.value); if (isNaN(lo)) lo = -Infinity;
    var hi = parseFloat(fmax.value); if (isNaN(hi)) hi = Infinity;

    var shown = 0;
    cards.forEach(function (card) {
      var brand = card.getAttribute('data-brand') || '';
      var colour = card.getAttribute('data-colour') || '';
      var price = parseFloat(card.getAttribute('data-price'));
      var okBrand = activeB.length === 0 || activeB.indexOf(brand) > -1;
      var okColour = activeC.length === 0 || activeC.indexOf(colour) > -1;
      var okPrice = isNaN(price) ? (lo === -Infinity && hi === Infinity) : (price >= lo && price <= hi);
      var vis = okBrand && okColour && okPrice;
      card.style.display = vis ? '' : 'none';
      if (vis) shown++;
    });

    if (fcount) fcount.textContent = shown + (shown === 1 ? ' product' : ' products');
    updateBadges(activeB.length, activeC.length);
    sort();
  }

  function updateBadges(nb, nc) {
    var bb = filters.querySelector('[data-count="b"]');
    var cb = filters.querySelector('[data-count="c"]');
    if (bb) bb.textContent = nb ? ' (' + nb + ')' : '';
    if (cb) cb.textContent = nc ? ' (' + nc + ')' : '';
  }

  function sort() {
    var v = fsort ? fsort.value : '';
    var arr = order.slice();
    if (v === 'asc') arr.sort(function (a, b) { return priceOf(a) - priceOf(b); });
    else if (v === 'desc') arr.sort(function (a, b) { return priceOf(b) - priceOf(a); });
    else if (v === 'az') arr.sort(function (a, b) {
      return (a.getAttribute('data-name') || '').localeCompare(b.getAttribute('data-name') || '');
    });
    arr.forEach(function (c) { grid.appendChild(c); });
  }

  // dropdown open/close
  var drops = Array.prototype.slice.call(filters.querySelectorAll('.fdrop'));
  drops.forEach(function (d) {
    var btn = d.querySelector('.fdrop-btn');
    if (!btn) return;
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var wasOpen = d.classList.contains('open');
      drops.forEach(function (x) { x.classList.remove('open'); });
      if (!wasOpen) d.classList.add('open');
    });
    var panel = d.querySelector('.fdrop-panel');
    if (panel) panel.addEventListener('click', function (e) { e.stopPropagation(); });
  });
  document.addEventListener('click', function () {
    drops.forEach(function (x) { x.classList.remove('open'); });
  });

  chips.forEach(function (c) {
    c.addEventListener('click', function () { c.classList.toggle('on'); apply(); });
  });
  [fmin, fmax].forEach(function (e) { e.addEventListener('input', apply); });
  if (fsort) fsort.addEventListener('change', apply);
  if (fclear) fclear.addEventListener('click', function () {
    chips.forEach(function (c) { c.classList.remove('on'); });
    fmin.value = ''; fmax.value = ''; if (fsort) fsort.value = '';
    apply();
  });

  apply();   // initialise count
})();
