from typing import List, Dict
from datamodel import OrderDepth, TradingState, Order
import json

LIMIT = 10 
BETA = 0.0240 # Ton Beta validé

def get_wap(od: OrderDepth):
    if not od.buy_orders or not od.sell_orders: return None
    best_bid, bid_vol = max(od.buy_orders.items())
    best_ask, ask_vol = min(od.sell_orders.items())
    return (best_bid * abs(ask_vol) + best_ask * bid_vol) / (bid_vol + abs(ask_vol))

class Trader:
    GROUPS = {
        "TRANSLATORS": ["TRANSLATOR_SPACE_GRAY", "TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_ECLIPSE_CHARCOAL", "TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_VOID_BLUE"],
        "VISORS": ["UV_VISOR_YELLOW", "UV_VISOR_AMBER", "UV_VISOR_ORANGE", "UV_VISOR_RED", "UV_VISOR_MAGENTA"]
    }

    def run(self, state: TradingState):
        result = {}
        # Mémoire pour stocker les offsets moyens de CHAQUE produit
        # history = { "PRODUCT_NAME": [rolling_avg_offset] }
        memory = json.loads(state.traderData) if state.traderData else {"last_leader_price": None, "offsets": {}}
        offsets = memory.get("offsets", {})

        current_waps = {p: get_wap(od) for p, od in state.order_depths.items() if get_wap(od)}
        
        # Moyennes de groupes
        leader_mids = [current_waps[p] for p in self.GROUPS["TRANSLATORS"] if p in current_waps]
        follower_mids = [current_waps[p] for p in self.GROUPS["VISORS"] if p in current_waps]
        
        if not leader_mids or not follower_mids:
            return {}, 0, json.dumps(memory)

        current_leader_avg = sum(leader_mids) / len(leader_mids)
        current_follower_avg = sum(follower_mids) / len(follower_mids)

        # 1. Calcul du Bonus Lead-Lag
        bonus = 0
        if memory["last_leader_price"] is not None:
            bonus = (current_leader_avg - memory["last_leader_price"]) * BETA

        # 2. Mise à jour dynamique des Offsets (Apprentissage en direct)
        for product in self.GROUPS["VISORS"]:
            if product in current_waps:
                # L'écart actuel de ce produit par rapport à la moyenne de son groupe
                current_offset = current_waps[product] - current_follower_avg
                # On lisse l'offset pour éviter de réagir au bruit (Moyenne mobile exponentielle simple)
                prev_offset = offsets.get(product, current_offset)
                offsets[product] = prev_offset * 0.8 + current_offset * 0.2

        # 3. Exécution Sniper
        for product in self.GROUPS["VISORS"]:
            if product not in state.order_depths: continue
            
            od = state.order_depths[product]
            pos = state.position.get(product, 0)
            
            # FV = Moyenne du groupe + Son décalage habituel + Anticipation du leader
            product_offset = offsets.get(product, 0)
            fv = current_follower_avg + product_offset + bonus
            
            best_bid = max(od.buy_orders.keys())
            best_ask = min(od.sell_orders.keys())

            # Logique Maker : on se place 1 tick devant les autres si on est loin de la FV
            buy_price = int(min(best_bid + 1, fv - 1))
            sell_price = int(max(best_ask - 1, fv + 1))

            orders: List[Order] = []
            if pos < LIMIT:
                orders.append(Order(product, buy_price, LIMIT - pos))
            if pos > -LIMIT:
                orders.append(Order(product, sell_price, -(LIMIT + pos)))

            result[product] = orders

        memory["last_leader_price"] = current_leader_avg
        memory["offsets"] = offsets
        return result, 0, json.dumps(memory)