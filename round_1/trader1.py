from typing import List
from datamodel import OrderDepth, TradingState, Order
import json

POSITION_LIMITS = {
    "ASH_COATED_OSMIUM":    80,
    "INTARIAN_PEPPER_ROOT": 80,
}

# Pente fixe observée sur 3 jours
PEPPER_SLOPE = 0.001001  # moyenne des 3 jours

class Trader:

    def run(self, state: TradingState):
        memory   = json.loads(state.traderData) if state.traderData else {}
        result   = {}

        for product in state.order_depths:
            order_depth = state.order_depths[product]
            orders: List[Order] = []
            pos      = state.position.get(product, 0)
            limit    = POSITION_LIMITS.get(product, 80)
            buy_cap  = limit - pos
            sell_cap = limit + pos

            best_bid = max(order_depth.buy_orders)  if order_depth.buy_orders  else None
            best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None
            if best_bid is None or best_ask is None:
                result[product] = []
                continue

            mid = (best_bid + best_ask) / 2

            # -------------------- ASH_COATED_OSMIUM
            # Mean reversion fixe comme Emeralds
            if product == "ASH_COATED_OSMIUM":
                fv = 10000

                for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                    if ask_price <= fv - 1 and buy_cap > 0:
                        qty = min(-ask_vol, buy_cap)
                        orders.append(Order(product, ask_price, qty))
                        buy_cap -= qty

                for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid_price >= fv + 1 and sell_cap > 0:
                        qty = min(bid_vol, sell_cap)
                        orders.append(Order(product, bid_price, -qty))
                        sell_cap -= qty

                if buy_cap > 0:
                    orders.append(Order(product, fv - 1, buy_cap))
                if sell_cap > 0:
                    orders.append(Order(product, fv + 1, -sell_cap))

            # -------------------- INTARIAN_PEPPER_ROOT
            # Fair value linéaire : intercept + slope * timestamp
            elif product == "INTARIAN_PEPPER_ROOT":

                # Estimer l'intercept en ligne
                # intercept = mid_price - slope * timestamp
                current_intercept = mid - PEPPER_SLOPE * state.timestamp

                # Moyenne mobile de l'intercept pour le stabiliser
                intercept_hist = memory.get("pepper_intercept", [])
                intercept_hist.append(current_intercept)
                if len(intercept_hist) > 50:
                    intercept_hist = intercept_hist[-50:]
                memory["pepper_intercept"] = intercept_hist

                intercept = sum(intercept_hist) / len(intercept_hist)
                fv = intercept + PEPPER_SLOPE * state.timestamp

                for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                    if ask_price <= fv - 1 and buy_cap > 0:
                        qty = min(-ask_vol, buy_cap)
                        orders.append(Order(product, ask_price, qty))
                        buy_cap -= qty

                for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid_price >= fv + 1 and sell_cap > 0:
                        qty = min(bid_vol, sell_cap)
                        orders.append(Order(product, bid_price, -qty))
                        sell_cap -= qty

                if buy_cap > 0:
                    orders.append(Order(product, round(fv) - 1, buy_cap))
                if sell_cap > 0:
                    orders.append(Order(product, round(fv) + 1, -sell_cap))

            else:
                pass

            result[product] = orders

        return result, 0, json.dumps(memory)