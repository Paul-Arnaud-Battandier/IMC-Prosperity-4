from typing import List, Dict
from datamodel import OrderDepth, TradingState, Order
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

# ── Hydrogel : MM pur autour du mid (pas de FV fixe) ─────
# Backtesté : final=+120k, drawdown ~0
HYDROGEL_MM_SPREAD   = 5     # poster à mid ± 5
HYDROGEL_TAKE_EDGE   = 2     # take si ask < mid - 2
HYDROGEL_MIN_VALID   = 9500
HYDROGEL_MAX_VALID   = 10500

# ── Velvetfruit Extract (spot) ────────────────────────────
VEV_SPOT_MM_SPREAD   = 3
VEV_SPOT_TAKE_EDGE   = 2
VEV_SPOT_MIN_VALID   = 4000
VEV_SPOT_MAX_VALID   = 7000

# ── Options VEV — Black-Scholes ───────────────────────────
SIGMA                = 0.0133   # σ implicite calibré sur données R3
TTE_START_R3         = 5        # TTE au début du round 3 (jours Prosperity)
# Strikes tradables (ATM/near-ATM ont de la time_value)
TRADEABLE_VEV        = {"VEV_5000","VEV_5100","VEV_5200","VEV_5300","VEV_5400","VEV_5500"}
DEEP_ITM_VEV         = {"VEV_4000","VEV_4500"}
DEEP_OTM_VEV         = {"VEV_6000","VEV_6500"}
OPT_MM_HALF_SPREAD   = 2
OPT_TAKE_THRESHOLD   = 3

# Delta hedge
DELTA_HEDGE          = True
DELTA_HEDGE_THRESH   = 5       # hedger si exposition > 5 unités


# ══════════════════════════════════════════════════════════
#  BLACK-SCHOLES (sans dépendance numpy/scipy)
# ══════════════════════════════════════════════════════════

def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0:   return max(S - K, 0.0)
    if sigma <= 0: return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma**2 * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _ncdf(d1) - K * _ncdf(d2)

def bs_delta(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0:   return 1.0 if S > K else 0.0
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
        memory  = json.loads(state.traderData) if state.traderData else {}
        result  = {}

        # ── TTE (décroît d'1 par round) ────────────────────
        TTE = memory.get("TTE", TTE_START_R3)
        # Détecter changement de round via saut de timestamp
        last_ts  = memory.get("last_ts", 0)
        if state.timestamp < last_ts:     # timestamp a redémarré → nouveau round
            TTE = max(TTE - 1, 0.01)
        memory["last_ts"] = state.timestamp
        memory["TTE"]     = TTE

        # ── Prix spot VELVETFRUIT_EXTRACT ───────────────────
        spot_price = memory.get("last_spot", 5250.0)
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            od_s = state.order_depths["VELVETFRUIT_EXTRACT"]
            bb, ba = best_bid_ask(od_s)
            if bb and ba and VEV_SPOT_MIN_VALID < (bb+ba)/2 < VEV_SPOT_MAX_VALID:
                spot_price = (bb + ba) / 2
                memory["last_spot"] = spot_price

        # ── Delta exposure totale des options ───────────────
        total_delta_exp = 0.0
        for prod, K in VEV_STRIKES.items():
            pos_opt = state.position.get(prod, 0)
            if pos_opt != 0:
                total_delta_exp += bs_delta(spot_price, K, TTE, SIGMA) * pos_opt

        # ── Traitement produit par produit ──────────────────
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

            # ── HYDROGEL_PACK ─────────────────────────────
            if product == "HYDROGEL_PACK":
                if not (HYDROGEL_MIN_VALID <= mid <= HYDROGEL_MAX_VALID):
                    result[product] = []; continue

                # ✅ FIX CRITIQUE : FV = mid observé (pas de valeur fixe)
                # Neutre directionnellement, capture uniquement le spread
                fv = mid

                taken, buy_cap, sell_cap = take_orders(
                    product, od, fv, HYDROGEL_TAKE_EDGE, buy_cap, sell_cap)
                orders.extend(taken)
                orders.extend(post_passive(product, fv, HYDROGEL_MM_SPREAD, buy_cap, sell_cap))

            # ── VELVETFRUIT_EXTRACT (spot) ─────────────────
            elif product == "VELVETFRUIT_EXTRACT":
                if not (VEV_SPOT_MIN_VALID < mid < VEV_SPOT_MAX_VALID):
                    result[product] = []; continue

                # Delta hedge
                if DELTA_HEDGE and abs(total_delta_exp) > DELTA_HEDGE_THRESH:
                    hedge_qty = max(-sell_cap, min(buy_cap, round(-total_delta_exp)))
                    if hedge_qty > 0:
                        orders.append(Order(product, ba, hedge_qty))
                        buy_cap = max(0, buy_cap - hedge_qty)
                    elif hedge_qty < 0:
                        orders.append(Order(product, bb, hedge_qty))
                        sell_cap = max(0, sell_cap + hedge_qty)

                # MM autour du mid spot
                fv = mid
                taken, buy_cap, sell_cap = take_orders(
                    product, od, fv, VEV_SPOT_TAKE_EDGE, buy_cap, sell_cap)
                orders.extend(taken)
                orders.extend(post_passive(product, fv, VEV_SPOT_MM_SPREAD, buy_cap, sell_cap))

            # ── OPTIONS VEV ───────────────────────────────
            elif product in VEV_STRIKES:
                K = VEV_STRIKES[product]

                if product in DEEP_OTM_VEV:
                    result[product] = []; continue  # quasi sans valeur

                elif product in DEEP_ITM_VEV:
                    # Delta ≈ 1 : pricer comme S - K
                    fv = max(spot_price - K, 0.0)
                    if fv <= 0: result[product] = []; continue
                    taken, buy_cap, sell_cap = take_orders(
                        product, od, fv, 2, buy_cap, sell_cap)
                    orders.extend(taken)
                    orders.extend(post_passive(product, fv, 2, buy_cap, sell_cap))

                elif product in TRADEABLE_VEV:
                    # BS pricing
                    fv = bs_call(spot_price, K, TTE, SIGMA)
                    if fv <= 0: result[product] = []; continue
                    taken, buy_cap, sell_cap = take_orders(
                        product, od, fv, OPT_TAKE_THRESHOLD, buy_cap, sell_cap)
                    orders.extend(taken)
                    orders.extend(post_passive(
                        product, fv, OPT_MM_HALF_SPREAD, buy_cap, sell_cap))

            result[product] = orders

        return result, 0, json.dumps(memory)