from typing import List
from prosperity3bt.datamodel import OrderDepth, TradingState, Order


FAIR_VALUE = {
    "EMERALDS": 10000,
    "TOMATOES": 5006,   # à affiner après analyse des Tomatoes
}

POSITION_LIMIT = {
    "EMERALDS": 50,
    "TOMATOES": 50,
}


class Trader:
    def run(self, state: TradingState):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            fair_value = FAIR_VALUE.get(product)
            if fair_value is None:
                continue

            pos = state.position.get(product, 0)
            buy_cap  = POSITION_LIMIT[product] - pos   # combien on peut encore acheter
            sell_cap = POSITION_LIMIT[product] + pos   # combien on peut encore vendre

            # -- Acheter si quelqu'un vend sous la fair value --
            for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                if ask_price < fair_value and buy_cap > 0:
                    qty = min(-ask_vol, buy_cap)
                    orders.append(Order(product, ask_price, qty))
                    buy_cap -= qty

            # -- Vendre si quelqu'un achète au dessus de la fair value --
            for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                if bid_price > fair_value and sell_cap > 0:
                    qty = min(bid_vol, sell_cap)
                    orders.append(Order(product, bid_price, -qty))
                    sell_cap -= qty

            result[product] = orders

        return result, 0, ""