from typing import List, Dict
from datamodel import OrderDepth, TradingState, Order, Trade
import json, math

# ══════════════════════════════════════════════════════════
#  POSITION LIMITS
# ══════════════════════════════════════════════════════════
POSITION_LIMITS = {
    "HYDROGEL_PACK":       200,
    "VELVETFRUIT_EXTRACT": 200,
    "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300,
    "VEV_5100": 300, "VEV_5200": 300, "VEV_5300": 300,
    "VEV_5400": 300, "VEV_5500": 300, "VEV_6000": 300,
    "VEV_6500": 300,
}

VEV_STRIKES = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000,
    "VEV_5100": 5100, "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500, "VEV_6000": 6000,
    "VEV_6500": 6500,
}

# ══════════════════════════════════════════════════════════
#  PARAMÈTRES
# ══════════════════════════════════════════════════════════

# ── Hydrogel ──────────────────────────────────────────────
HYDROGEL_MM_SPREAD  = 5
HYDROGEL_TAKE_EDGE  = 2
HYDROGEL_MAX_POS    = 50       # position limit réduite → évite crash directionnel
HYDROGEL_MIN_VALID  = 9500
HYDROGEL_MAX_VALID  = 10500

# ── Velvetfruit spot ──────────────────────────────────────
VEV_SPOT_MM_SPREAD  = 3
VEV_SPOT_TAKE_EDGE  = 2

# ── Options ───────────────────────────────────────────────
# σ RECALIBRÉE sur données R4 (TTE=4) — corrige le bug -20k
# Plus de σ uniforme : chaque strike a sa propre σ implicite
SIGMA_BY_STRIKE: Dict[int, float] = {
    4000: 0.0365,   # deep ITM — σ_impl élevée mais irrelevant (price = S-K)
    4500: 0.0213,   # deep ITM
    5000: 0.0150,   # ATM — calibré sur données R4
    5100: 0.0146,
    5200: 0.0149,   # ← était 0.0133, causait SHORT catastrophique
    5300: 0.0152,   # ← idem, le pire offenseur (-9810 en R3)
    5400: 0.0143,
    5500: 0.0155,
    6000: 0.0262,   # OTM extrême — ignoré dans le trading
    6500: 0.0397,
}

TTE_START_R4        = 4        # TTE au début du round 4

TRADEABLE_VEV       = {"VEV_5000","VEV_5100","VEV_5200","VEV_5300","VEV_5400","VEV_5500"}
DEEP_ITM_VEV        = {"VEV_4000","VEV_4500"}
DEEP_OTM_VEV        = {"VEV_6000","VEV_6500"}

OPT_MM_HALF_SPREAD  = 2
OPT_TAKE_THRESHOLD  = 3

# ── Position limit par option : ✅ FIX CRITIQUE R3 ────────
# R3 : position limit = 300 → SHORT -300 × delta = -105 unités spot non couvertes
# R4 : cap à 50 par strike → exposition max = 50 × delta ≈ 18 unités spot
OPT_MAX_POS         = 50

# ── Mark 67 : informed trader (suit les achats spot) ──────
FOLLOW_MARK67       = True
MARK67_BOOST        = 5        # unités supplémentaires si Mark 67 achète

# ── Mark 22 : market maker options OTM ───────────────────
# Mark 22 vend massivement VEV_5300/5400/5500
# → Ces options sont correctement pricées côté vendeur
# → On NE DOIT PAS shorter ces options (c'est ce qui a coulé R3)
# → On peut les acheter si C_obs < BS_fv - threshold


# ══════════════════════════════════════════════════════════
#  BLACK-SCHOLES
# ══════════════════════════════════════════════════════════

def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0:     return max(S - K, 0.0)
    if sigma <= 0: return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma**2 * T) / (sigma * math.sqrt(T))
    return S * _ncdf(d1) - K * _ncdf(d1 - sigma * math.sqrt(T))

def bs_delta(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0:     return 1.0 if S > K else 0.0
    if sigma <= 0: return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + 0.5 * sigma**2 * T) / (sigma * math.sqrt(T))
    return _ncdf(d1)


# ══════════════════════════════════════════════════════════
#  UTILITAIRES
# ══════════════════════════════════════════════════════════

def best_bid_ask(od: OrderDepth):
    bb = max(od.buy_orders)  if od.buy_orders  else None
    ba = min(od.sell_orders) if od.sell_orders else None
    return bb, ba

def take_orders(product, od, fv, threshold, buy_cap, sell_cap):
    orders = []
    for ap in sorted(od.sell_orders):
        if ap <= fv - threshold and buy_cap > 0:
            q = min(-od.sell_orders[ap], buy_cap)
            orders.append(Order(product, ap, q)); buy_cap -= q
    for bp in sorted(od.buy_orders, reverse=True):
        if bp >= fv + threshold and sell_cap > 0:
            q = min(od.buy_orders[bp], sell_cap)
            orders.append(Order(product, bp, -q)); sell_cap -= q
    return orders, buy_cap, sell_cap

def post_passive(product, fv, half_spread, buy_cap, sell_cap):
    orders = []
    if buy_cap  > 0: orders.append(Order(product, round(fv) - half_spread,  buy_cap))
    if sell_cap > 0: orders.append(Order(product, round(fv) + half_spread, -sell_cap))
    return orders


# ══════════════════════════════════════════════════════════
#  TRADER
# ══════════════════════════════════════════════════════════

class Trader:

    def run(self, state: TradingState):
        memory = json.loads(state.traderData) if state.traderData else {}
        result = {}

        # ── TTE ────────────────────────────────────────────
        TTE     = memory.get("TTE", TTE_START_R4)
        last_ts = memory.get("last_ts", 0)
        if state.timestamp < last_ts:
            TTE = max(TTE - 1, 0.01)
        memory["last_ts"] = state.timestamp
        memory["TTE"]     = TTE

        # ── Spot ───────────────────────────────────────────
        spot_price = memory.get("last_spot", 5250.0)
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            od_s = state.order_depths["VELVETFRUIT_EXTRACT"]
            bb_s, ba_s = best_bid_ask(od_s)
            if bb_s and ba_s and 4000 < (bb_s+ba_s)/2 < 7000:
                spot_price = (bb_s + ba_s) / 2
                memory["last_spot"] = spot_price

        # ── Détecter trades de Mark 67 sur le spot ─────────
        mark67_net = 0
        if FOLLOW_MARK67 and hasattr(state, 'market_trades'):
            for prod, tlist in state.market_trades.items():
                if prod == "VELVETFRUIT_EXTRACT":
                    for t in tlist:
                        if t.buyer == "Mark 67":
                            mark67_net += t.quantity
                        elif t.seller == "Mark 67":
                            mark67_net -= t.quantity

        # ── Produit par produit ────────────────────────────
        for product, od in state.order_depths.items():
            orders: List[Order] = []
            pos      = state.position.get(product, 0)
            limit    = POSITION_LIMITS.get(product, 200)
            buy_cap  = limit - pos
            sell_cap = limit + pos

            bb, ba = best_bid_ask(od)
            if bb is None or ba is None:
                result[product] = []; continue
            mid = (bb + ba) / 2

            # ── HYDROGEL ──────────────────────────────────
            if product == "HYDROGEL_PACK":
                if not (HYDROGEL_MIN_VALID <= mid <= HYDROGEL_MAX_VALID):
                    result[product] = []; continue
                buy_cap  = max(0, min(buy_cap,  HYDROGEL_MAX_POS - pos))
                sell_cap = max(0, min(sell_cap, HYDROGEL_MAX_POS + pos))
                fv = mid
                taken, buy_cap, sell_cap = take_orders(
                    product, od, fv, HYDROGEL_TAKE_EDGE, buy_cap, sell_cap)
                orders.extend(taken)
                orders.extend(post_passive(product, fv, HYDROGEL_MM_SPREAD, buy_cap, sell_cap))

            # ── VEV SPOT ──────────────────────────────────
            elif product == "VELVETFRUIT_EXTRACT":
                if not (4000 < mid < 7000):
                    result[product] = []; continue
                fv = mid
                # Boost si Mark 67 achète ce tick
                if FOLLOW_MARK67 and mark67_net > 0:
                    buy_cap = min(buy_cap + MARK67_BOOST, limit - pos)
                taken, buy_cap, sell_cap = take_orders(
                    product, od, fv, VEV_SPOT_TAKE_EDGE, buy_cap, sell_cap)
                orders.extend(taken)
                orders.extend(post_passive(product, fv, VEV_SPOT_MM_SPREAD, buy_cap, sell_cap))

            # ── OPTIONS VEV ───────────────────────────────
            elif product in VEV_STRIKES:
                K     = VEV_STRIKES[product]
                sigma = SIGMA_BY_STRIKE.get(K, 0.0149)

                if product in DEEP_OTM_VEV:
                    result[product] = []; continue

                elif product in DEEP_ITM_VEV:
                    fv = max(spot_price - K, 0.0)
                    if fv <= 0: result[product] = []; continue
                    # ✅ Cap position deep ITM aussi
                    buy_cap  = max(0, min(buy_cap,  OPT_MAX_POS - pos))
                    sell_cap = max(0, min(sell_cap, OPT_MAX_POS + pos))
                    taken, buy_cap, sell_cap = take_orders(
                        product, od, fv, 2, buy_cap, sell_cap)
                    orders.extend(taken)
                    orders.extend(post_passive(product, fv, 2, buy_cap, sell_cap))

                elif product in TRADEABLE_VEV:
                    # ✅ σ recalibrée par strike
                    fv = bs_call(spot_price, K, TTE, sigma)
                    if fv <= 0: result[product] = []; continue

                    # ✅ Cap position : évite SHORT massif non couvert
                    buy_cap  = max(0, min(buy_cap,  OPT_MAX_POS - pos))
                    sell_cap = max(0, min(sell_cap, OPT_MAX_POS + pos))

                    taken, buy_cap, sell_cap = take_orders(
                        product, od, fv, OPT_TAKE_THRESHOLD, buy_cap, sell_cap)
                    orders.extend(taken)
                    orders.extend(post_passive(
                        product, fv, OPT_MM_HALF_SPREAD, buy_cap, sell_cap))

            result[product] = orders

        return result, 0, json.dumps(memory)