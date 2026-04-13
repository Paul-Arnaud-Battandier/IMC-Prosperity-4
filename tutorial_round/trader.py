import sys
import os

project_root = os.path.abspath("C:\\Users\\paulp\\OneDrive - Groupe INSEEC (POCE)\\Bureau\\IMC-Prosperity-4")
sys.path.insert(0, project_root)

from typing import List
from collections import deque
from datamodel import OrderDepth, TradingState, Order
import json

# --- Paramètres ---
POSITION_LIMITS = {"EMERALDS": 50, "TOMATOES": 50}
EMERALD_FAIR_VALUE = 10000
TOMATO_MA_WINDOW = 50  # nombre de ticks pour la moyenne mobile

class Trader:

    def run(self, state: TradingState):
        # Récupérer la mémoire du tick précédent
        memory = json.loads(state.traderData) if state.traderData else {}
        tomato_history = memory.get("tomato_history", [])

        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)
            buy_cap  = POSITION_LIMITS[product] - pos
            sell_cap = POSITION_LIMITS[product] + pos

            # --- Fair value selon le produit ---
            if product == "EMERALDS":
                fair_value = EMERALD_FAIR_VALUE

            elif product == "TOMATOES":
                # Calculer le mid price actuel
                best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None
                best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None
                if best_bid and best_ask:
                    mid = (best_bid + best_ask) / 2
                    tomato_history.append(mid)
                    if len(tomato_history) > TOMATO_MA_WINDOW:
                        tomato_history = tomato_history[-TOMATO_MA_WINDOW:]
                fair_value = sum(tomato_history) / len(tomato_history) if tomato_history else None

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
