from typing import List, Dict
from datamodel import OrderDepth, TradingState, Order
import json

# ══════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════

POSITION_LIMITS = {
    "ASH_COATED_OSMIUM":    80,
    "INTARIAN_PEPPER_ROOT": 80,
}

# ── Pepper Root : régression parfaite (R² = 0.9999) ──────
# intercept observé augmente de ~1 000 par jour
# J-1 = 11000.3 | J0 = 12001.4 | J1 = 13003.1 | J2 = ~14004
PEPPER_SLOPE = 0.001001

PEPPER_INTERCEPT_BY_DAY: Dict[int, float] = {
    -1: 11000.3,
     0: 12001.4,
     1: 13003.1,
     2: 14004.0,   # extrapolé (+1000/jour)
     3: 15005.0,   # extrapolé de sécurité
}

# Seuil minimum de mispricing pour déclencher un market take
PEPPER_TAKE_THRESHOLD = 3   # prendre seulement si ask < fv - 3

# Demi-spread passif autour de la fair value pour le MM
PEPPER_MM_HALF_SPREAD = 4   # poster à fv - 4 / fv + 4

# ── Osmium : mean reversion pure ─────────────────────────
OSMIUM_FV          = 10001  # médiane réelle des données filtrées
OSMIUM_TAKE_EDGE   = 2      # prendre si ask <= fv - 2 ou bid >= fv + 2
OSMIUM_MM_SPREAD   = 4      # poster à fv - 4 / fv + 4

# Filtre anti-spike : ignorer le book si mid est hors de cette plage
OSMIUM_MIN_VALID   = 9500
OSMIUM_MAX_VALID   = 10500


# ══════════════════════════════════════════════════════════
#  UTILITAIRES
# ══════════════════════════════════════════════════════════

def best_bid_ask(order_depth: OrderDepth):
    bb = max(order_depth.buy_orders)  if order_depth.buy_orders  else None
    ba = min(order_depth.sell_orders) if order_depth.sell_orders else None
    return bb, ba


def take_orders(product, order_depth, fv, threshold, buy_cap, sell_cap):
    """Prend les ordres market clairement mispriced."""
    orders = []

    for ask_price in sorted(order_depth.sell_orders):
        if ask_price <= fv - threshold and buy_cap > 0:
            qty = min(-order_depth.sell_orders[ask_price], buy_cap)
            orders.append(Order(product, ask_price, qty))
            buy_cap -= qty

    for bid_price in sorted(order_depth.buy_orders, reverse=True):
        if bid_price >= fv + threshold and sell_cap > 0:
            qty = min(order_depth.buy_orders[bid_price], sell_cap)
            orders.append(Order(product, bid_price, -qty))
            sell_cap -= qty

    return orders, buy_cap, sell_cap


def post_passive(product, fv, half_spread, buy_cap, sell_cap):
    """Poste des ordres passifs autour de la fair value."""
    orders = []
    if buy_cap > 0:
        orders.append(Order(product, round(fv) - half_spread, buy_cap))
    if sell_cap > 0:
        orders.append(Order(product, round(fv) + half_spread, -sell_cap))
    return orders


# ══════════════════════════════════════════════════════════
#  TRADER PRINCIPAL
# ══════════════════════════════════════════════════════════

class Trader:

    def run(self, state: TradingState):
        memory = json.loads(state.traderData) if state.traderData else {}
        result = {}

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            pos      = state.position.get(product, 0)
            limit    = POSITION_LIMITS.get(product, 80)
            buy_cap  = limit - pos
            sell_cap = limit + pos

            bb, ba = best_bid_ask(order_depth)
            if bb is None or ba is None:
                result[product] = []
                continue

            mid = (bb + ba) / 2

            # ─────────────────────────────────────────────
            #  ASH_COATED_OSMIUM — mean reversion
            # ─────────────────────────────────────────────
            if product == "ASH_COATED_OSMIUM":

                # Filtre anti-spike
                if not (OSMIUM_MIN_VALID <= mid <= OSMIUM_MAX_VALID):
                    result[product] = []
                    continue

                fv = OSMIUM_FV

                # 1) Market taking
                taken, buy_cap, sell_cap = take_orders(
                    product, order_depth, fv,
                    threshold=OSMIUM_TAKE_EDGE,
                    buy_cap=buy_cap, sell_cap=sell_cap,
                )
                orders.extend(taken)

                # 2) Market making passif
                orders.extend(post_passive(
                    product, fv, OSMIUM_MM_SPREAD, buy_cap, sell_cap
                ))

            # ─────────────────────────────────────────────
            #  INTARIAN_PEPPER_ROOT — fair value linéaire
            # ─────────────────────────────────────────────
            elif product == "INTARIAN_PEPPER_ROOT":

                day = state.day if hasattr(state, "day") else memory.get("current_day", 0)

                if day in PEPPER_INTERCEPT_BY_DAY:
                    intercept = PEPPER_INTERCEPT_BY_DAY[day]
                else:
                    # Extrapolation de sécurité
                    intercept = 13003.1 + 1000.0 * (day - 1)

                memory["current_day"] = day
                fv = intercept + PEPPER_SLOPE * state.timestamp

                # 1) Market taking
                taken, buy_cap, sell_cap = take_orders(
                    product, order_depth, fv,
                    threshold=PEPPER_TAKE_THRESHOLD,
                    buy_cap=buy_cap, sell_cap=sell_cap,
                )
                orders.extend(taken)

                # 2) Market making passif
                orders.extend(post_passive(
                    product, fv, PEPPER_MM_HALF_SPREAD, buy_cap, sell_cap
                ))

            result[product] = orders

        return result, 0, json.dumps(memory)