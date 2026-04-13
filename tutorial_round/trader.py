from typing import List
from datamodel import OrderDepth, TradingState, Order
import json

POSITION_LIMITS = {"EMERALDS": 50, "TOMATOES": 50}
EMERALD_FAIR_VALUE = 10000
TOMATO_MA_WINDOW = 50

class Trader:

    def run(self, state: TradingState):
        memory = json.loads(state.traderData) if state.traderData else {}
        tomato_history = memory.get("tomato_history", [])

        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)
            limit = POSITION_LIMITS.get(product, 50)
            buy_cap  = limit - pos
            sell_cap = limit + pos

            # -------------------------------------------------- EMERALDS
            if product == "EMERALDS":
                fair_value = EMERALD_FAIR_VALUE

                for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                    if ask_price <= fair_value - 1 and buy_cap > 0:
                        qty = min(-ask_vol, buy_cap)
                        orders.append(Order(product, ask_price, qty))
                        buy_cap -= qty

                for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid_price >= fair_value + 1 and sell_cap > 0:
                        qty = min(bid_vol, sell_cap)
                        orders.append(Order(product, bid_price, -qty))
                        sell_cap -= qty

                if buy_cap > 0:
                    orders.append(Order(product, fair_value - 1, buy_cap))
                if sell_cap > 0:
                    orders.append(Order(product, fair_value + 1, -sell_cap))

            # -------------------------------------------------- TOMATOES
            elif product == "TOMATOES":
                # Récupérer l'historique
                hist = tomato_history
                
                # Calculer le mid price actuel
                best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None
                best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None
                
                if best_bid is None or best_ask is None:
                    result[product] = []
                    continue
                    
                mid = (best_bid + best_ask) / 2
                hist.append(mid)
                if len(hist) > 200:
                    hist = hist[-200:]
                tomato_history = hist

                # Pas assez d'historique — on attend
                if len(hist) < 200:
                    result[product] = []
                    continue

                # Calculer les deux MA
                ma_short = sum(hist[-20:]) / 20
                ma_long  = sum(hist[-200:]) / 200
                signal   = ma_short - ma_long

                # Fair value = MA courte (meilleure estimation du prix actuel)
                fair_value = ma_short

                # Biais selon le signal
                if signal > 2:       # tendance haussière → on préfère acheter
                    buy_edge  = 1
                    sell_edge = 3
                elif signal < -2:    # tendance baissière → on préfère vendre
                    buy_edge  = 3
                    sell_edge = 1
                else:                # neutre → symétrique
                    buy_edge  = 2
                    sell_edge = 2

                # Market taking
                for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                    if ask_price <= fair_value - buy_edge and buy_cap > 0:
                        qty = min(-ask_vol, buy_cap)
                        orders.append(Order(product, ask_price, qty))
                        buy_cap -= qty

                for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid_price >= fair_value + sell_edge and sell_cap > 0:
                        qty = min(bid_vol, sell_cap)
                        orders.append(Order(product, bid_price, -qty))
                        sell_cap -= qty

                # Market making passif
                if buy_cap > 0:
                    orders.append(Order(product, round(fair_value) - buy_edge, buy_cap))
                if sell_cap > 0:
                    orders.append(Order(product, round(fair_value) + sell_edge, -sell_cap))

            # -------------------------------------------------- INCONNU
            else:
                pass  # nouveaux produits rounds suivants

            result[product] = orders

        memory["tomato_history"] = tomato_history
        trader_data = json.dumps(memory)

        return result, 0, trader_data