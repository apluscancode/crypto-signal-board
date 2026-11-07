/* Crypto Signal Board — renders signals.json into cards.
   Verdict only, plus the raw numbers behind it. No charts, no noise. */
(function () {
  'use strict';

  var DATA = null;
  var state = { filter: 'all', q: '', sort: 'verdict' };
  var VERDICT_ORDER = { BUY: 0, SELL: 1, HOLD: 2 };

  var $ = function (s) { return document.querySelector(s); };
  var board = $('#board');

  // ---- formatting -------------------------------------------------------
  function fmtPrice(v) {
    if (v === null || v === undefined) return '—';
    var a = Math.abs(v);
    if (a >= 1000) return v.toLocaleString('en-US', { maximumFractionDigits: 1 });
    if (a >= 1) return v.toFixed(2);
    if (a >= 0.01) return v.toFixed(4);
    return v.toPrecision(4);
  }
  function fmtPct(v) {
    if (v === null || v === undefined) return '—';
    return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
  }
  function chgClass(v) { return v > 0.001 ? 'up' : (v < -0.001 ? 'dn' : 'fl'); }
  function structLabel(s) {
    return { bull: 'صعودی', bear: 'نزولی', mixed: 'مبهم' }[s] || '—';
  }
  function ichLabel(s) {
    return { above: 'بالای ابر', inside: 'داخل ابر', below: 'زیر ابر' }[s] || '—';
  }

  // Persian digits for the verdict word
  var PERSIAN = { BUY: 'خرید', SELL: 'فروش', HOLD: 'انتظار' };

  function timeAgo(iso) {
    if (!iso) return '—';
    var t = new Date(iso).getTime();
    if (isNaN(t)) return '—';
    var d = Math.floor((Date.now() - t) / 60000);
    if (d < 1) return 'همین حالا';
    if (d < 60) return d + ' دقیقه پیش';
    var h = Math.floor(d / 60);
    if (h < 24) return h + ' ساعت پیش';
    return Math.floor(h / 24) + ' روز پیش';
  }

  // ---- card -------------------------------------------------------------
  function card(s) {
    var el = document.createElement('article');
    el.className = 'card ' + (s.cls || 'hold');

    var range = (s.pct !== null && s.pct !== undefined) ? s.pct : 50;
    var score = s.score || 0;
    // score runs roughly -1.1 .. +1.1 -> map to 0..100 with 50 = neutral
    var pos = Math.max(0, Math.min(100, 50 + score * 45));
    var w = Math.abs(pos - 50);
    var left = Math.min(50, pos);
    var col = score > 0.15 ? 'var(--buy)' : (score < -0.15 ? 'var(--sell)' : 'var(--hold)');

    el.innerHTML =
      '<div class="card-top">' +
        '<div class="id">' +
          '<span class="sym"></span>' +
          '<span class="nm"></span>' +
          '<span class="rank"></span>' +
        '</div>' +
        '<span class="v"></span>' +
      '</div>' +
      '<div class="px">' +
        '<span class="p"></span>' +
        '<span class="chg"></span>' +
        '<span class="chg" style="color:var(--tx3)"></span>' +
      '</div>' +
      '<div class="bar"><i class="mid"></i><i style="background:' + col + '"></i></div>' +
      '<div class="meta">' +
        '<div class="m"><span>ساختار</span><b class="m-s"></b></div>' +
        '<div class="m"><span>ایچیموکو</span><b class="m-i"></b></div>' +
        '<div class="m"><span>RSI</span><b class="m-r"></b></div>' +
      '</div>' +
      '<div class="lv">' +
        '<span>نقدینگی <b class="lv-lo"></b></span>' +
        '<span>امتیاز <b class="lv-sc"></b></span>' +
        '<span>قدرت نسبی <b class="lv-rs"></b></span>' +
      '</div>';

    // textContent everywhere — no HTML injection from data
    q(el, '.sym').textContent = s.symbol;
    q(el, '.nm').textContent = s.name || '';
    q(el, '.rank').textContent = s.rank ? '#' + s.rank + ' · ' + (s.tv || '') : (s.tv || '');
    q(el, '.v').textContent = PERSIAN[s.verdict] || s.verdict || '—';
    q(el, '.p').textContent = fmtPrice(s.price);
    var c24 = q(el, '.px .chg');
    c24.classList.add(chgClass(s.chg_24h));
    c24.textContent = fmtPct(s.chg_24h) + ' ۲۴س';
    var c7 = q(el, '.px .chg:nth-of-type(3)');
    c7.classList.add(chgClass(s.chg_7d));
    c7.textContent = fmtPct(s.chg_7d) + ' ۷ر';
    q(el, '.m-s').textContent = structLabel(s.structure);
    q(el, '.m-i').textContent = ichLabel(s.ichimoku);
    q(el, '.m-r').textContent = s.rsi !== null && s.rsi !== undefined ? s.rsi : '—';
    q(el, '.lv-lo').textContent = fmtPrice(s.pdl);
    q(el, '.lv-sc').textContent = (s.score >= 0 ? '+' : '') + s.score.toFixed(2);
    q(el, '.lv-rs').textContent = s.rs_vs_btc !== undefined && s.rs_vs_btc !== null
      ? fmtPct(s.rs_vs_btc) : '—';

    // score bar
    var fill = el.querySelectorAll('.bar i')[1];
    fill.style.left = left + '%';
    fill.style.width = w + '%';

    return el;
  }

  function q(root, sel) { return root.querySelector(sel); }

  // ---- rendering --------------------------------------------------------
  function visible() {
    var list = DATA.signals.filter(function (s) {
      if (s.status !== 'ok') return false;
      if (state.filter !== 'all' && s.verdict !== state.filter) return false;
      if (state.q) {
        var needle = state.q.toLowerCase();
        var hay = (s.symbol + ' ' + (s.name || '') + ' ' + (s.tv || '')).toLowerCase();
        if (hay.indexOf(needle) === -1) return false;
      }
      return true;
    });

    var k = state.sort;
    list.sort(function (a, b) {
      if (k === 'score') return (b.score || 0) - (a.score || 0);
      if (k === 'rank') return (a.rank || 999) - (b.rank || 999);
      if (k === 'chg24') return (b.chg_24h || 0) - (a.chg_24h || 0);
      if (k === 'chg7') return (b.chg_7d || 0) - (a.chg_7d || 0);
      if (k === 'rsi') return (a.rsi === null ? 999 : a.rsi) - (b.rsi === null ? 999 : b.rsi);
      if (k === 'rs') return (b.rs_vs_btc || 0) - (a.rs_vs_btc || 0);
      var va = VERDICT_ORDER[a.verdict], vb = VERDICT_ORDER[b.verdict];
      if (va !== vb) return va - vb;
      return Math.abs(b.score || 0) - Math.abs(a.score || 0);
    });
    return list;
  }

  function render() {
    var list = visible();
    board.innerHTML = '';
    if (!list.length) {
      board.innerHTML = '<div class="empty">کوینی با این فیلتر پیدا نشد</div>';
      return;
    }
    var frag = document.createDocumentFragment();
    list.forEach(function (s) { frag.appendChild(card(s)); });
    board.appendChild(frag);
  }

  function renderHead() {
    $('#t-buy').textContent = DATA.buy;
    $('#t-hold').textContent = DATA.hold;
    $('#t-sell').textContent = DATA.sell;
    $('#f-all').textContent = DATA.total;
    $('#f-buy').textContent = DATA.buy;
    $('#f-hold').textContent = DATA.hold;
    $('#f-sell').textContent = DATA.sell;

    var reg = $('#regime');
    reg.classList.remove('bear', 'bull', 'neutral');
    reg.classList.add(DATA.regime || 'neutral');
    $('#regime-val').textContent = DATA.regime_fa || '—';
    $('#regime-sub').textContent =
      'میانگین امتیاز ' + (DATA.avg_score >= 0 ? '+' : '') + (DATA.avg_score || 0).toFixed(2) +
      ' · زیر ابر: ' + (DATA.ichimoku_below || 0) + ' / بالای ابر: ' + (DATA.ichimoku_above || 0) +
      ' · BTC ۷روزه: ' + fmtPct(DATA.btc_chg_7d);

    var up = $('#updated');
    up.textContent = 'آخرین به‌روزرسانی: ' + timeAgo(DATA.generated_at);
  }

  // ---- events -----------------------------------------------------------
  function bind() {
    document.querySelectorAll('.f').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.f').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        state.filter = btn.getAttribute('data-f');
        render();
      });
    });
    $('#search').addEventListener('input', function (e) {
      state.q = e.target.value.trim();
      render();
    });
    $('#sort').addEventListener('change', function (e) {
      state.sort = e.target.value;
      render();
    });
  }

  // ---- boot -------------------------------------------------------------
  function fail(msg) {
    board.innerHTML = '<div class="empty">' + msg + '</div>';
  }

  fetch('data/signals.json', { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (json) {
      DATA = json;
      renderHead();
      render();
      bind();
      document.body.dataset.ready = '1';
    })
    .catch(function (e) {
      fail('داده در دسترس نیست (' + e.message + '). کمی بعد دوباره تلاش کنید.');
      document.body.dataset.ready = 'error';
    });
})();
