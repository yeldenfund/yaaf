"""Coletor GMX V2 (Arbitrum) via Subsquid GraphQL."""
import json
import urllib.request
from pathlib import Path

GRAPHQL_URL = "https://gmx.squids.live/gmx-synthetics-arbitrum:prod/api/graphql"
TOKENS_URL = "https://arbitrum-api.gmxinfra.io/tokens"
CACHE_FILE = Path(__file__).parent.parent / "gmx_tokens.json"

SCALE_USD = 10**30


def _post(query: str, variables: dict | None = None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; observatory/1.0)",
            "Accept": "application/json",
            "Origin": "https://gmx.squids.live",
        },
        method="POST",
    )
    import time
    last_err = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            if "errors" in data:
                # size limit é fatal, não retry
                msg = str(data["errors"])
                if "size limit" in msg:
                    raise RuntimeError(f"size limit: {msg}")
                last_err = RuntimeError(f"GraphQL error: {msg}")
                time.sleep(2 ** attempt)
                continue
            return data["data"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (521, 522, 523, 524, 429):
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise last_err or RuntimeError("max retries exceeded")


def load_tokens() -> dict:
    """Cache de address -> {symbol, decimals}."""
    if CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text())
            if isinstance(cached, dict):
                return cached
            # se o cache estiver em formato de lista, reindexa
            return {t["address"].lower(): {"symbol": t.get("symbol"), "decimals": int(t.get("decimals", 18))}
                    for t in cached if isinstance(t, dict) and t.get("address")}
        except Exception:
            pass  # cache inválido, recarrega

    req = urllib.request.Request(
        TOKENS_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; observatory/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())

    # a API retorna {"tokens": [...]}
    raw = data.get("tokens") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raw = []

    out = {}
    for t in raw:
        if not isinstance(t, dict):
            continue
        addr = (t.get("address") or "").lower()
        if not addr:
            continue
        out[addr] = {
            "symbol": t.get("symbol") or addr[:10],
            "decimals": int(t.get("decimals", 18)),
        }
    CACHE_FILE.write_text(json.dumps(out, indent=2))
    return out



def fetch_trade_actions(since_ts: int = 0, until_ts: int = 0, limit: int = 200) -> list:
    """Pagina TradeActions. Limit baixo (200) por causa do size limit do Subsquid."""
    query = """
    query($since: Int!, $limit: Int!, $until: Int!) {
      tradeActions(
        where: {eventName_eq: "OrderExecuted", orderType_in: [4,5,6,7],
                timestamp_gte: $since, timestamp_lt: $until}
        limit: $limit, orderBy: timestamp_ASC
      ) {
        account marketAddress positionLifecycleId basePnlUsd pnlUsd
        sizeDeltaUsd positionSizeInUsd initialCollateralDeltaAmount initialCollateralTokenAddress
        positionFeeAmount borrowingFeeAmount fundingFeeAmount
        priceImpactUsd liquidationFeeAmount executionPrice
        isLong orderType reason timestamp transactionHash
      }
    }
    """
    if until_ts == 0:
        import time
        until_ts = int(time.time()) + 60
    data = _post(query, {"since": since_ts, "until": until_ts, "limit": limit})
    actions = data.get("tradeActions", []) or []
    tokens = load_tokens()
    markets = load_markets()
    return [n for n in (normalize(a, tokens, markets) for a in actions) if n is not None]


def load_markets() -> dict:
    """Cache de marketAddress -> symbol, via indexToken."""
    cache = Path(__file__).parent.parent / "gmx_markets.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass

    data = _post("{ markets(limit: 500) { id indexToken } }")
    tokens = load_tokens()
    out = {}
    for m in data.get("markets", []):
        market_addr = (m.get("id") or "").lower()
        index_addr = (m.get("indexToken") or "").lower()
        if not market_addr:
            continue
        tok = tokens.get(index_addr, {})
        out[market_addr] = tok.get("symbol") or index_addr[:10]
    cache.write_text(json.dumps(out, indent=2))
    return out


def normalize(action: dict, tokens: dict, markets: dict | None = None) -> dict:
    """Converte TradeAction GMX para schema comum."""
    markets = markets or load_markets()
    market_addr = (action.get("marketAddress") or "").lower()
    symbol = markets.get(market_addr, market_addr[:10])

    def u(x):  # USD (1e30)
        return float(x) / SCALE_USD if x else 0.0

    # decimals do token de collateral (não do index)
    coll_token_addr = (action.get("initialCollateralTokenAddress") or "").lower()
    coll_token = tokens.get(coll_token_addr, {})
    collateral_decimals = coll_token.get("decimals", 6)
    collateral_scale = 10 ** collateral_decimals

    def c(x):  # collateral units
        return float(x) / collateral_scale if x else 0.0

    base_pnl = u(action.get("basePnlUsd"))
    pnl_usd = u(action.get("pnlUsd"))
    size_usd = u(action.get("sizeDeltaUsd"))
    collateral = c(action.get("initialCollateralDeltaAmount"))

    fees = (
        c(action.get("positionFeeAmount"))
        + c(action.get("borrowingFeeAmount"))
        + c(action.get("fundingFeeAmount"))
        + c(action.get("liquidationFeeAmount"))
    )

    # R-multiple real: pnl / collateral depositado
    # filtra trades minúsculos (< $1 collateral) que geram R absurdo
    if collateral < 1.0:
        return None
    r_multiple = pnl_usd / collateral
    if abs(r_multiple) > 20.0:
        return None

    order_type = action.get("orderType")
    kind = {4: "MARKET_DEC", 5: "LIMIT_DEC", 6: "STOP_DEC", 7: "LIQUIDATION"}.get(order_type, "UNKNOWN")

    return {
        "account": action.get("account"),
        "t": action.get("timestamp"),
        "market": symbol,
        "side": "BUY" if not action.get("isLong") else "SELL",  # fechou long = vendeu
        "dir": kind,
        "action": "CLOSE",
        "price": u(action.get("executionPrice")),
        "size": size_usd,
        "usd_notional": size_usd,
        "fee": fees,
        "closed_pnl": pnl_usd,
        "base_pnl": base_pnl,
        "collateral": collateral,
        "r_multiple": r_multiple,
        "price_impact_usd": u(action.get("priceImpactUsd")),
        "lifecycle_id": action.get("positionLifecycleId"),
        "tx_hash": action.get("transactionHash"),
        "source": "gmx",
    }


def fetch_trader_trades(account: str, tokens: dict, since_ts: int = 0, max_pages: int = 10) -> list:
    """Pega todos os TradeActions de um trader."""
    all_actions = []
    last_ts = since_ts
    for _ in range(max_pages):
        query = """
        query($account: String!, $since: Int!, $limit: Int!) {
          tradeActions(
            where: {account_eq: $account, eventName_eq: "OrderExecuted",
                    orderType_in: [4,5,6,7], timestamp_gte: $since}
            limit: $limit, orderBy: timestamp_ASC
          ) {
            account marketAddress positionLifecycleId basePnlUsd pnlUsd
            sizeDeltaUsd positionSizeInUsd initialCollateralDeltaAmount initialCollateralTokenAddress
            positionFeeAmount borrowingFeeAmount fundingFeeAmount
            priceImpactUsd liquidationFeeAmount executionPrice
            isLong orderType reason timestamp transactionHash
          }
        }
        """
        data = _post(query, {"account": account, "since": last_ts, "limit": 1000})
        batch = data.get("tradeActions", []) or []
        if not batch:
            break
        all_actions.extend(batch)
        if len(batch) < 1000:
            break
        last_ts = batch[-1]["timestamp"]

    return [n for n in (normalize(a, tokens) for a in all_actions) if n is not None]
