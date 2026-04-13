from typing import List
from datamodel import OrderDepth, TradingState, Order
import json

POSITION_LIMITS = {"EMERALDS": 50, "TOMATOES": 50}
EMERALD_FAIR_VALUE = 10000
TOMATO_MA_WINDOW = 50

class Trader:

    def run(self, state: TradingState):
        # Récupérer la mémoire du tick précédent
        memory = json.loads(state.traderData) if state.traderData else {}
        tomato_history = memory.get("tomato_history", [])

        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            # Remplace la ligne 22-23 par :
            pos = state.position.get(product, 0)
            limit = POSITION_LIMITS.get(product, 50)  # 50 par défaut si produit inconnu
            buy_cap  = limit - pos
            sell_cap = limit + pos

            # --- Fair value selon le produit ---
            if product == "EMERALDS":
                fair_value = EMERALD_FAIR_VALUE

                # Market taking — si quelqu'un vend à 9999 ou moins, on achète
                for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                    if ask_price <= fair_value - 1 and buy_cap > 0:
                        qty = min(-ask_vol, buy_cap)
                        orders.append(Order(product, ask_price, qty))
                        buy_cap -= qty

                # Market taking — si quelqu'un achète à 10001 ou plus, on vend
                for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid_price >= fair_value + 1 and sell_cap > 0:
                        qty = min(bid_vol, sell_cap)
                        orders.append(Order(product, bid_price, -qty))
                        sell_cap -= qty

                # Market making — on poste des ordres passifs de chaque côté
                if buy_cap > 0:
                    orders.append(Order(product, fair_value - 1, buy_cap))   # bid à 9999
                if sell_cap > 0:
                    orders.append(Order(product, fair_value + 1, -sell_cap)) # ask à 10001

                result[product] = orders
                continue

            elif product == "TOMATOES":
                result[product] = []
                continue
            
            elif product == "RAINFOREST_RESIN":
                fair_value = 10000  # même logique qu'Emeralds
            elif product == "KELP":
                fair_value = None   # pas de stratégie → skip

            else:
                fair_value = None

            if fair_value is None:
                result[product] = []
                continue

            # --- Acheter ce qui est sous la fair value ---
            for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                if ask_price < fair_value and buy_cap > 0:
                    qty = min(-ask_vol, buy_cap)
                    orders.append(Order(product, ask_price, qty))
                    buy_cap -= qty

            # --- Vendre ce qui est au dessus ---
            for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                if bid_price > fair_value and sell_cap > 0:
                    qty = min(bid_vol, sell_cap)
                    orders.append(Order(product, bid_price, -qty))
                    sell_cap -= qty

            result[product] = orders

        # Sauvegarder la mémoire
        memory["tomato_history"] = tomato_history
        trader_data = json.dumps(memory)

        return result, 0, trader_data
