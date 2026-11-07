#!/usr/bin/env python3
"""
Signal engine for the 100-coin board.

Per coin it computes:
  - ICT market structure (HH/HL vs LH/LL) from swing pivots
  - Ichimoku position (above / inside / below the cloud)
  - EMA stack + RSI + ATR
  - Fair Value Gaps that are still unfilled
  - Liquidity pools (PDH/PDL, swing highs/lows)
  - A composite verdict: BUY / SELL / HOLD

The verdict is deliberately simple and explainable — no black box.
Every input contributes a signed weight; the sum decides the call, and the
card shows which inputs were live so a degraded feed can never masquerade
as a confident signal.
"""
import json
import os
import sys

CANDLES = '/root/crypto-dashboard/data/candles.json'
OUT = '/root/crypto-dashboard/data/signals.json'


# ---------------------------------------------------------------- helpers
def sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None


def ema_series(v, n):
    if len(v) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(v[:n]) / n
    out = [e]
    for x in v[n:]:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def rsi(v, n=14):
    if len(v) < n + 1:
        return None
    g = l = 0.0
    for i in range(-n, 0):
        ch = v[i] - v[i - 1]
        if ch >= 0:
            g += ch
        else:
            l -= ch
    ag, al = g / n, l / n
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1 + ag / al)


def atr(bars, n=14):
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, c = bars[i]['h'], bars[i]['l'], bars[i - 1]['c']
        trs.append(max(h - l, abs(h - c), abs(l - c)))
    return sum(trs[-n:]) / n


def pivots(bars, k=3):
    """Swing highs / lows using a k-bar fractal on highs/lows."""
    highs, lows = [], []
    h = [b['h'] for b in bars]
    l = [b['l'] for b in bars]
    for i in range(k, len(bars) - k):
        w = h[i - k:i + k + 1]
        if h[i] == max(w) and w.count(h[i]) == 1:
            highs.append((i, h[i]))
        w = l[i - k:i + k + 1]
        if l[i] == min(w) and w.count(l[i]) == 1:
            lows.append((i, l[i]))
    return highs, lows


def structure(highs, lows):
    """Return 'bull' / 'bear' / 'mixed' plus the two most recent pivots."""
    if len(highs) < 2 or len(lows) < 2:
        return 'mixed', None, None
    h2 = highs[-2:]
    l2 = lows[-2:]
    hh = h2[1][1] > h2[0][1]
    hl = l2[1][1] > l2[0][1]
    if hh and hl:
        return 'bull', h2[-1], l2[-1]
    if not hh and not hl:
        return 'bear', h2[-1], l2[-1]
    return 'mixed', h2[-1], l2[-1]


def ichimoku(bars):
    h = [b['h'] for b in bars]
    l = [b['l'] for b in bars]
    c = [b['c'] for b in bars]
    if len(bars) < 52:
        return None
    tenkan = (max(h[-9:]) + min(l[-9:])) / 2
    kijun = (max(h[-26:]) + min(l[-26:])) / 2
    spana = (tenkan + kijun) / 2
    spanb = (max(h[-52:-26]) + min(l[-52:-26])) / 2
    last = c[-1]
    if last > max(spana, spanb):
        pos = 'above'
    elif last < min(spana, spanb):
        pos = 'below'
    else:
        pos = 'inside'
    return {
        'tenkan': tenkan, 'kijun': kijun, 'spana': spana, 'spanb': spanb,
        'pos': pos,
        'cloud_top': max(spana, spanb), 'cloud_bot': min(spana, spanb),
    }


def fvgs(bars, lookback=40):
    """Unfilled fair value gaps, newest first."""
    out = []
    start = max(2, len(bars) - lookback)
    last = bars[-1]['c']
    for i in range(start, len(bars)):
        if bars[i]['l'] > bars[i - 2]['h']:
            out.append({'type': 'bull', 'lo': bars[i - 2]['h'], 'hi': bars[i]['l'],
                        't': bars[i]['t'], 'filled': last > bars[i]['l']})
        if bars[i]['h'] < bars[i - 2]['l']:
            out.append({'type': 'bear', 'lo': bars[i]['h'], 'hi': bars[i - 2]['l'],
                        't': bars[i]['t'], 'filled': last < bars[i]['h']})
    return out


def ema_stack(bars):
    c = [b['c'] for b in bars]
    e21 = ema_series(c, 21)
    e50 = ema_series(c, 50)
    e200 = ema_series(c, 200) if len(c) >= 200 else None
    last = c[-1]
    stack = 0
    if e21:
        stack += 1 if last > e21[-1] else -1
    if e50:
        stack += 1 if last > e50[-1] else -1
    if e200:
        stack += 1 if last > e200[-1] else -1
    return stack, {
        'ema21': e21[-1] if e21 else None,
        'ema50': e50[-1] if e50 else None,
        'ema200': e200[-1] if e200 else None,
    }


# ---------------------------------------------------------------- engine
def analyse(sym, rec):
    bars = rec.get('bars') or []
    if len(bars) < 30:
        return {
            'symbol': sym, 'name': rec.get('name'), 'rank': rec.get('rank'),
            'tv': rec.get('tv'), 'status': 'no-data',
            'error': rec.get('error', 'insufficient bars'),
        }

    # TradingView returns newest-first — normalise to oldest-first
    bars = sorted(bars, key=lambda b: b['t'])
    c = [b['c'] for b in bars]
    h = [b['h'] for b in bars]
    l = [b['l'] for b in bars]
    last = c[-1]
    prev = c[-2] if len(c) > 1 else last

    highs, lows = pivots(bars)
    struct, ph, pl = structure(highs, lows)
    ich = ichimoku(bars)
    stack, emas = ema_stack(bars)
    r = rsi(c)
    a = atr(bars)
    gaps = fvgs(bars)
    unfilled_bull = [g for g in gaps if g['type'] == 'bull' and not g['filled']]
    unfilled_bear = [g for g in gaps if g['type'] == 'bear' and not g['filled']]

    # ---- weighted score -------------------------------------------------
    score = 0.0
    weight = 0.0
    parts = []

    def add(label, val, w):
        nonlocal score, weight
        if val is None:
            return
        score += val * w
        weight += w
        parts.append({'label': label, 'value': val, 'weight': w})

    add('structure', {'bull': 1, 'bear': -1, 'mixed': 0}[struct], 3)
    add('ichimoku', {'above': 1, 'inside': 0, 'below': -1}[ich['pos']] if ich else None, 2)
    add('ema_stack', stack, 2)
    add('rsi', (1 if (r is not None and r < 35) else (-1 if (r is not None and r > 65) else 0))
        if r is not None else None, 1)
    # short-term momentum: last close vs 5 bars ago
    if len(c) > 5:
        mom = (last - c[-6]) / c[-6] * 100
        add('momentum', 1 if mom > 1.5 else (-1 if mom < -1.5 else 0), 1)
    # position inside the daily range (close location value)
    rng = h[-1] - l[-1]
    if rng > 0:
        clv = (last - l[-1]) / rng
        add('range_pos', 1 if clv > 0.7 else (-1 if clv < 0.3 else 0), 1)

    norm = score / weight if weight else 0.0
    # Verdict is assigned LATER, relative to the whole board (percentile).
    # A uniformly bearish market would otherwise print 90x SELL and tell the
    # user nothing. The absolute score stays visible on every card.
    verdict, cls = 'HOLD', 'hold'

    # ---- levels ---------------------------------------------------------
    pdh = max(h[-2:]) if len(h) >= 2 else last
    pdl = min(l[-2:]) if len(l) >= 2 else last
    targets = []
    if a:
        for k in (1, 2, 3):
            targets.append({'label': f'ATR {k}x', 'up': last + a * k, 'down': last - a * k})

    # nearest unfilled FVG as the first pullback zone
    zone = None
    if verdict == 'BUY' and unfilled_bull:
        g = min(unfilled_bull, key=lambda x: abs((x['lo'] + x['hi']) / 2 - last))
        zone = {'type': 'bull FVG', 'lo': g['lo'], 'hi': g['hi']}
    elif verdict == 'SELL' and unfilled_bear:
        g = min(unfilled_bear, key=lambda x: abs((x['lo'] + x['hi']) / 2 - last))
        zone = {'type': 'bear FVG', 'lo': g['lo'], 'hi': g['hi']}

    chg24 = (last - c[-2]) / c[-2] * 100 if len(c) > 1 else 0
    chg7 = (last - c[-8]) / c[-8] * 100 if len(c) > 7 else 0

    return {
        'symbol': sym,
        'name': rec.get('name'),
        'rank': rec.get('rank'),
        'tv': rec.get('tv'),
        'status': 'ok',
        'price': last,
        'chg_24h': round(chg24, 2),
        'chg_7d': round(chg7, 2),
        'verdict': verdict,
        'cls': cls,
        'score': round(norm, 3),
        'inputs': len(parts),
        'total_inputs': 6,
        'structure': struct,
        'ichimoku': ich['pos'] if ich else None,
        'ema_stack': stack,
        'rsi': round(r, 1) if r is not None else None,
        'atr': round(a, 8) if a else None,
        'atr_pct': round(a / last * 100, 2) if a else None,
        'ema': {k: (round(v, 10) if v is not None else None) for k, v in emas.items()},
        'pdh': round(pdh, 10),
        'pdl': round(pdl, 10),
        'swing_high': round(ph[1], 10) if ph else None,
        'swing_low': round(pl[1], 10) if pl else None,
        'unfilled_bull_fvg': len(unfilled_bull),
        'unfilled_bear_fvg': len(unfilled_bear),
        'zone': zone,
        'targets': [{'label': t['label'],
                     'up': round(t['up'], 10), 'down': round(t['down'], 10)} for t in targets],
        'last_bar': bars[-1]['t'],
        'bars': len(bars),
    }


def main():
    with open(CANDLES) as f:
        data = json.load(f)

    signals = []
    for sym, rec in data.get('symbols', {}).items():
        try:
            signals.append(analyse(sym, rec))
        except Exception as e:
            signals.append({'symbol': sym, 'name': rec.get('name'),
                            'rank': rec.get('rank'), 'tv': rec.get('tv'),
                            'status': 'error', 'error': str(e)[:120]})

    ok = sum(1 for s in signals if s.get('status') == 'ok')

    # ---- relative verdicts ------------------------------------------------
    # Rank the board by absolute score and hand out BUY / SELL to the tails.
    live = [s for s in signals if s.get('status') == 'ok']
    live.sort(key=lambda s: s['score'])
    n = len(live)
    top_cut = max(1, round(n * 0.15))       # 15% best  -> BUY
    bot_cut = max(1, round(n * 0.15))       # 15% worst -> SELL
    for i, s in enumerate(live):
        s['pct'] = round((i + 1) / n * 100, 1) if n else None
        if i >= n - top_cut:
            s['verdict'], s['cls'] = 'BUY', 'buy'
        elif i < bot_cut:
            s['verdict'], s['cls'] = 'SELL', 'sell'
        else:
            s['verdict'], s['cls'] = 'HOLD', 'hold'

    # Relative strength vs BTC — is this coin outperforming the market?
    btc = next((s for s in live if s['symbol'] == 'btc'), None)
    btc_chg7 = btc['chg_7d'] if btc else 0.0
    for s in live:
        s['rs_vs_btc'] = round(s['chg_7d'] - btc_chg7, 2)

    # Market regime — the aggregate read on the whole board.
    avg = sum(s['score'] for s in live) / len(live) if live else 0
    bear_ich = sum(1 for s in live if s.get('ichimoku') == 'below')
    bull_ich = sum(1 for s in live if s.get('ichimoku') == 'above')
    regime = 'bearish' if avg < -0.3 else ('bullish' if avg > 0.3 else 'neutral')
    regime_fa = {'bearish': 'نزولی', 'bullish': 'صعودی', 'neutral': 'خنثی'}[regime]

    order = {'BUY': 0, 'SELL': 1, 'HOLD': 2}
    signals.sort(key=lambda s: (order.get(s.get('verdict'), 3),
                                 -abs(s.get('score') or 0)))
    payload = {
        'generated_at': data.get('generated_at'),
        'timeframe': data.get('timeframe'),
        'ok_count': ok,
        'total': len(signals),
        'buy': sum(1 for s in signals if s.get('verdict') == 'BUY'),
        'sell': sum(1 for s in signals if s.get('verdict') == 'SELL'),
        'hold': sum(1 for s in signals if s.get('verdict') == 'HOLD'),
        'regime': regime,
        'regime_fa': regime_fa,
        'avg_score': round(avg, 3),
        'btc_chg_7d': round(btc_chg7, 2),
        'ichimoku_below': bear_ich,
        'ichimoku_above': bull_ich,
        'signals': signals,
    }
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f"signals: {ok}/{len(signals)} ok | BUY {payload['buy']} SELL {payload['sell']} HOLD {payload['hold']}")
    print(f"regime: {regime_fa} (avg {avg:+.2f}) | ich below {bear_ich} / above {bull_ich} | BTC7d {btc_chg7:+.1f}%")
    for s in signals[:8]:
        if s.get('status') == 'ok':
            print(f"  {s['verdict']:5} {s['symbol']:8} score={s['score']:+.2f} pct={s['pct']:5.1f} "
                  f"rsi={s['rsi']} struct={s['structure']} ich={s['ichimoku']} rs={s['rs_vs_btc']:+.1f}%")
    return 0


if __name__ == '__main__':
    sys.exit(main())
