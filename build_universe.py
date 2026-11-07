#!/usr/bin/env python3
"""Build the 100-coin universe from CoinGecko top-250 market cap.

Strategy: walk down the market-cap list and keep coins until we have 100
TRADEABLE ones. Stablecoins, wrapped/staked variants, exchange tokens and
obviously-non-trading symbols are skipped so the board stays meaningful.
"""
import json
import time
import urllib.request

# Explicitly excluded: stablecoins, wrapped/staked/bridged assets, exchange
# tokens, and non-trade utility. Everything here has no meaningful price action.
EXCLUDE = {
    # stablecoins
    'pearl','jaaa','ohm','pieverse','bp','ousg','币安人生','un','ustb','usdtb','usx','susdx',
    'usdt','usdc','usds','dai','fdusd','usdd','usdp','tusd','usdtb','usde','susde',
    'pyusd','usdy','usdf','rlusd','usd0','usdgo','usdy','bfusd','buidl','ustb','usyc',
    'usdg','usdy','ousd','gho','oeds','eursafo','eurs','eurc','apxusd','safo','eutbl',
    'usdtb','usual','usd0','ylds','sofid','reusd','stable','a7a5','bf','xaut','paxg',
    'kaufman','kau','usdtb',
    # wrapped / staked / bridged
    'wbtc','cbbtc','wbbtc','btcb','wbeth','weth','wsteth','steth','sfrxeth','rseth',
    'weeth','ezeth','wstusdt','wsol','solv','wbnb','wpol','wavax','wtrx','wton',
    'wldo','wbeam','wmatic','wtao','wbtc','solstaked','msol','jitosol','bnsol',
    'wstusdt','solv','wbeth','ezeth','rseth','weeth',
    # exchange / infra tokens with no clean USDT pair
    'leo','cro','kcs','bgb','gt','htx','bf','bitget','okx','kucoin','htx','binance',
    'mexc','bybit','gate','mstr','mstrx','tst',
    # no spot pair / not tradeable
    'un','u','m','nm','w','figr_heloc','pc0000031','spcxb','cards','hash','pengu',
    'apepe','kmno','koge','gala','jst','vvv','jup','mint','sei','stable',
    'xaut','paxg','wbeth','gno','arweave','ar','sonic','s','turbo','bome','move',
    'sxt','usdt','sun','t',
}

# Coins that resolve on a non-Binance venue — map to a venue that works.
VENUE = {
    'hype': 'GATEIO', 'xmr': 'KUCOIN', 'mnt': 'KUCOIN', 'okb': 'GATEIO',
    'rain': 'GATEIO', 'cc': 'GATEIO', 'pi': 'GATEIO', 'kas': 'MEXC', 'lit': 'GATEIO',
    'gho': 'GATEIO', 'pearl': 'MEXC', 'xdc': 'GATEIO', 'gvprice': 'GATEIO',
    'sky': 'MEXC', 'morpho': 'MEXC', 'wld': 'MEXC', 'icp': 'GATEIO',
    'algo': 'GATEIO', 'render': 'MEXC', 'jup': 'GATEIO', 'nexo': 'MEXC',
    'ethfi': 'GATEIO', 'bendc': 'GATEIO', 'layerzero': 'GATEIO',
    'zro': 'GATEIO', 'virtual': 'MEXC', 'grass': 'GATEIO', 'btt': 'GATEIO',
    'drv': 'GATEIO', 'bsv': 'GATEIO', 'spx': 'MEXC', 'strk': 'GATEIO',
    'apx': 'GATEIO', 'xtz': 'GATEIO', 'pendle': 'GATEIO', 'flr': 'GATEIO',
    'ray': 'MEXC', 'vet': 'GATEIO', 'tia': 'GATEIO', 'crv': 'GATEIO',
    'virtuals': 'MEXC', 'kite': 'GATEIO', 'ohm': 'GATEIO', 'bonk': 'GATEIO',
    'op': 'GATEIO', 'dcr': 'GATEIO', 'cfx': 'GATEIO', 'kaia': 'GATEIO',
    'grt': 'GATEIO', 'floki': 'GATEIO', 'lunc': 'GATEIO', 'frax': '', 'crvfrx': '', 'lq': '', 'usds': '',
}


def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (dashboard)'})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == tries - 1:
                print(f"FAIL: {e}", flush=True)
                return None
            time.sleep(4 * (i + 1))
    return None


def main():
    raw = fetch('https://api.coingecko.com/api/v3/coins/markets'
                '?vs_currency=usd&order=market_cap_desc&per_page=250&page=1'
                '&sparkline=false&price_change_percentage=1h,24h,7d')
    if not raw:
        print("CoinGecko fetch failed")
        return

    coins = []
    seen = set()
    for c in raw:
        sym = (c.get('symbol') or '').lower()
        if not sym or sym in EXCLUDE or sym in seen:
            continue
        if len(sym) > 14:
            continue
        seen.add(sym)
        venue = VENUE.get(sym, 'BINANCE')
        coins.append({
            'id': c['id'],
            'symbol': sym,
            'name': c['name'],
            'tv': f"{venue}:{sym.upper()}USDT",
            'mc': c.get('market_cap') or 0,
            'rank': c.get('market_cap_rank') or 999,
            'cg_price': c.get('current_price') or 0,
            'cg_24h': c.get('price_change_percentage_24h_in_currency'),
            'cg_7d': c.get('price_change_percentage_7d_in_currency'),
        })
        if len(coins) >= 100:
            break

    print(f"universe: {len(coins)} coins")
    with open('/root/crypto-dashboard/universe.json', 'w') as f:
        json.dump(coins, f, indent=1, ensure_ascii=False)
    for c in coins[:8]:
        print(f"  {c['rank']:3} {c['symbol']:12} {c['tv']}")
    print('  ...')
    for c in coins[-5:]:
        print(f"  {c['rank']:3} {c['symbol']:12} {c['tv']}")


if __name__ == '__main__':
    main()
