from typing import List
from datamodel import OrderDepth, TradingState, Order
import json

POSITION_LIMITS    = {"EMERALDS": 50, "TOMATOES": 50}
EMERALD_FAIR_VALUE = 10000
TOMATO_MA_WINDOW   = 200
TOMATO_MA_SHORT    = 20


def compute_ofi(market_trades, product):
    trades   = market_trades.get(product, [])
    if not trades:
        return 0.0
    buy_vol  = sum(t.quantity for t in trades if t.buyer != "")
    sell_vol = sum(t.quantity for t in trades if t.seller != "")
    total    = buy_vol + sell_vol
    if total == 0:
        return 0.0
    return (buy_vol - sell_vol) / total


class Trader:

    def run(self, state: TradingState):
        memory         = json.loads(state.traderData) if state.traderData else {}
        tomato_history = memory.get("tomato_history", [])
        ofi_history    = memory.get("ofi_history", {})

        result = {}

        for product in state.order_depths:
            order_depth = state.order_depths[product]
            orders: List[Order] = []
            pos      = state.position.get(product, 0)
            limit    = POSITION_LIMITS.get(product, 50)
            buy_cap  = limit - pos
            sell_cap = limit + pos

            best_bid = max(order_depth.buy_orders)  if order_depth.buy_orders  else None
            best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None

            if best_bid is None or best_ask is None:
                result[product] = []
                continue

            ofi = compute_ofi(state.market_trades, product)

            # ------------------------------------------ EMERALDS
            if product == "EMERALDS":
                fv = EMERALD_FAIR_VALUE + round(ofi * 2)

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

            # ------------------------------------------ TOMATOES
            elif product == "TOMATOES":
                mid = (best_bid + best_ask) / 2
                tomato_history.append(mid)
                if len(tomato_history) > TOMATO_MA_WINDOW:
                    tomato_history = tomato_history[-TOMATO_MA_WINDOW:]

                if len(tomato_history) < TOMATO_MA_WINDOW:
                    result[product] = []
                    continue

                ma_short = sum(tomato_history[-TOMATO_MA_SHORT:]) / TOMATO_MA_SHORT
                ma_long  = sum(tomato_history) / TOMATO_MA_WINDOW
                signal   = ma_short - ma_long

                # Signal combiné MA + OFI
                combined = signal + (ofi * 5)
                fv       = ma_short

                if combined > 2:
                    buy_edge, sell_edge = 1, 3
                elif combined < -2:
                    buy_edge, sell_edge = 3, 1
                else:
                    buy_edge, sell_edge = 2, 2

                for ask_price, ask_vol in sorted(order_depth.sell_orders.items()):
                    if ask_price <= fv - buy_edge and buy_cap > 0:
                        qty = min(-ask_vol, buy_cap)
                        orders.append(Order(product, ask_price, qty))
                        buy_cap -= qty

                for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid_price >= fv + sell_edge and sell_cap > 0:
                        qty = min(bid_vol, sell_cap)
                        orders.append(Order(product, bid_price, -qty))
                        sell_cap -= qty

                if buy_cap > 0:
                    orders.append(Order(product, round(fv) - buy_edge, buy_cap))
                if sell_cap > 0:
                    orders.append(Order(product, round(fv) + sell_edge, -sell_cap))

            else:
                pass

            # Stocker OFI
            h = ofi_history.get(product, [])
            h.append(float(ofi))
            ofi_history[product] = h[-50:]

            result[product] = orders

        memory["tomato_history"] = tomato_history
        memory["ofi_history"]    = ofi_history
        return result, 0, json.dumps(memory)