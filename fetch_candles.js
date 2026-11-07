const TV = require('@mathieuc/tradingview');
const fs = require('fs');
const path = require('path');

// Exchange fallback chain — BINANCE first (best liquidity),
// then the venues that resolved the widest set in testing.
const EXCHANGES = ['BINANCE', 'GATEIO', 'MEXC', 'KUCOIN', 'BYBIT', 'OKX', 'BITGET', 'COINBASE'];

// Symbols known to live on a specific venue. The generic chain is tried
// first, but these short-circuit to the venue that actually lists them.
const PINNED = {
  wbt: 'KUCOIN', rain: 'KUCOIN', pearl: 'KUCOIN', flr: 'KUCOIN', grass: 'KUCOIN',
  btt: 'KUCOIN', bsv: 'KUCOIN', drv: 'KUCOIN', ohm: 'KUCOIN', spx: 'KUCOIN',
  pieverse: 'KUCOIN', jaaa: 'KUCOIN', bdx: 'KUCOIN', bp: 'KUCOIN',
  ub: 'KUCOIN', ousg: 'KUCOIN', '币安人生': 'KUCOIN', wbtc: 'KUCOIN',
};

const UNIVERSE = JSON.parse(fs.readFileSync(__dirname + '/universe.json', 'utf8'));
const OUT = process.env.OUT || path.join(__dirname, 'data/candles.json');
const RANGE = parseInt(process.env.RANGE || '120', 10);
const TF = process.env.TF || 'D';

function candidatesFor(coin) {
  const base = (coin.tv || '').split(':')[1] || (coin.symbol.toUpperCase() + 'USDT');
  const stem = base.endsWith('USDT') ? base.slice(0, -4) : base;
  const out = [];
  const pin = PINNED[coin.symbol.toLowerCase()];
  const order = pin ? [pin, ...EXCHANGES.filter(e => e !== pin)] : EXCHANGES;
  for (const ex of order) {
    out.push(`${ex}:${stem}USDT`);
    if (ex === 'COINBASE') out.push(`${ex}:${stem}USD`);
  }
  return out;
}

function barsFrom(chart) {
  const p = chart.periods || [];
  if (p.length < 30) return null;
  return p.map(x => ({
    t: new Date(x.time * 1000).toISOString().slice(0, 16),
    o: x.open, h: x.max, l: x.min, c: x.close, v: x.volume || 0
  }));
}

/**
 * One websocket session, many symbols subscribed at once.
 * TradingView resolves them all in parallel — 80 charts in one session works.
 */
async function session(pairs, waitMs) {
  const client = new TV.Client();
  const charts = pairs.map(({ sym }) => {
    const c = new client.Session.Chart();
    c.setMarket(sym, { timeframe: TF, range: RANGE });
    return c;
  });
  await new Promise(r => setTimeout(r, waitMs));
  const found = new Map();
  charts.forEach((c, i) => {
    const b = barsFrom(c);
    if (b) found.set(pairs[i].sym, b);
  });
  try { client.close && client.close(); } catch (e) { /* ignore */ }
  return found;
}

(async () => {
  const t0 = Date.now();
  const result = {};
  let pending = UNIVERSE.map(c => ({ coin: c, cands: candidatesFor(c) }));

  // ---- Pass 1: one session, all coins on their primary symbol ----
  const primary = pending.map(p => ({ coin: p.coin, sym: p.cands[0] }));
  console.error(`pass 1: ${primary.length} symbols`);
  let found = await session(primary, 14000);
  console.error(`pass 1 resolved: ${found.size}`);

  for (const { coin, sym } of primary) {
    const bars = found.get(sym);
    if (bars) result[coin.symbol] = { name: coin.name, rank: coin.rank, tv: sym, bars };
  }

  // ---- Pass 2: remaining coins, all fallback candidates in one session ----
  pending = pending.filter(p => !result[p.coin.symbol]);
  if (pending.length) {
    const retry = [];
    pending.forEach(p => p.cands.slice(1).forEach(sym => retry.push({ coin: p.coin, sym })));
    console.error(`pass 2: ${pending.length} coins / ${retry.length} candidate symbols`);
    found = await session(retry, 14000);
    console.error(`pass 2 resolved symbols: ${found.size}`);
    for (const { coin, sym } of retry) {
      if (result[coin.symbol]) continue;
      const bars = found.get(sym);
      if (bars) result[coin.symbol] = { name: coin.name, rank: coin.rank, tv: sym, bars };
    }
  }

  // ---- Anything still missing ----
  for (const c of UNIVERSE) {
    if (!result[c.symbol]) {
      result[c.symbol] = { name: c.name, rank: c.rank, tv: null, bars: [], error: 'unresolved' };
    }
  }

  const ok = Object.values(result).filter(s => s.bars.length > 0).length;
  const payload = {
    generated_at: new Date().toISOString(),
    timeframe: TF,
    range: RANGE,
    ok_count: ok,
    total: UNIVERSE.length,
    symbols: result
  };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(payload));
  console.error(`DONE ${ok}/${UNIVERSE.length} in ${((Date.now() - t0) / 1000).toFixed(0)}s -> ${OUT}`);
  const failed = Object.entries(result).filter(([, s]) => !s.bars.length).map(([k]) => k);
  if (failed.length) console.error('FAILED: ' + failed.join(','));
  process.exit(0);
})().catch(e => { console.error('FATAL', e.stack || e.message); process.exit(1); });
