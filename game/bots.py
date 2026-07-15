from random import choice, randint

from .economy import apply_rate_rounded_50k


class BotStrategy:
    """Strategy-only scoring and choices; it never mutates game state."""

    def __init__(self, player):
        self.player = player

    @property
    def name(self):
        return self.player.bot_strategy or "balanced"

    def reserve_ratio(self):
        return {
            "aggressive": 0.10,
            "conservative": 0.45,
            "random": 0.20,
            "balanced": 0.25,
        }.get(self.name, 0.25)

    def should_buy_land(self, price, has_loan=False):
        if self.player.cash_won < 0:
            return False
        reserve = self.reserve_ratio() + (0.20 if has_loan else 0)
        return self.player.cash_won - price >= int(self.player.cash_won * reserve)

    def choose_building(self, available, prices):
        if self.player.cash_won < 0:
            return None
        affordable = [
            item
            for item in available
            if self.player.cash_won - prices[item] >= int(self.player.cash_won * self.reserve_ratio())
        ]
        if not affordable:
            return None
        preferences = {
            "aggressive": ("mixed_use", "commercial", "industrial", "residential"),
            "conservative": ("industrial", "residential", "commercial", "mixed_use"),
            "balanced": ("residential", "commercial", "industrial", "mixed_use"),
        }
        if self.name == "random":
            return choice([*affordable, None])
        return next((item for item in preferences.get(self.name, preferences["balanced"]) if item in affordable), None)

    def accepts_land_trade(self, price, has_loan=False):
        if self.player.cash_won < price or self.player.cash_won < 0:
            return False
        if self.name == "aggressive":
            return self.player.cash_won - price >= int(self.player.cash_won * 0.10)
        if self.name == "conservative":
            return self.player.cash_won - price >= int(self.player.cash_won * 0.50) and not has_loan
        if self.name == "random":
            return randint(1, 2) == 1
        return self.player.cash_won - price >= int(self.player.cash_won * 0.25)

    def accepts_operating_right(self, price, expected_income, has_loan=False):
        accepted = self.player.cash_won >= price and expected_income >= int(price * 0.1)
        if self.name == "aggressive":
            return self.player.cash_won >= price
        if self.name == "conservative":
            return accepted and not has_loan
        return accepted

    def approves_usage_change(self, new_type):
        if self.name == "conservative" and new_type in {"commercial", "mixed_use"}:
            return False
        return True


class BotController:
    """Queries engine state, chooses an action, then calls validated engine APIs."""

    def __init__(self, engine):
        self.engine = engine

    def run_due_bots(self):
        while self.engine.should_run_current_bot():
            player = self.engine.current_player()
            if not player or not player.is_bot:
                return
            self.engine.take_turn_for_player(player.id, source="bot")

    def choose_action(self, player):
        pending = self.engine.state.pending_action
        if not pending or pending.get("player_id") != player.id:
            return {"type": "none"}
        strategy = BotStrategy(player)
        if pending["type"] == "purchase_land":
            return {
                "type": "purchase_land" if strategy.should_buy_land(pending["price_won"], player.id in self.engine.state.loans) else "decline"
            }
        if pending["type"] == "build":
            if self.engine.state.successful_build_edit_this_visit:
                return {"type": "decline"}
            building_type = strategy.choose_building(
                pending["available_buildings"],
                self.engine.data["building_prices"][pending["region_id"]],
            )
            return {"type": "build", "building_type": building_type} if building_type else {"type": "decline"}
        if pending["type"] == "purchase_special":
            current = self.engine.state.special_values.get(pending["special_region_id"], pending["price_won"])
            risk_margin = 0.40 if strategy.name == "conservative" else 0.15
            affordable = player.cash_won - pending["price_won"] >= int(player.cash_won * strategy.reserve_ratio())
            return {"type": "purchase_special" if affordable and current >= int(pending["price_won"] * (1 - risk_margin)) else "decline"}
        return {"type": "decline"}

    def perform_investment(self, player):
        # A land purchase can create one follow-up build decision. The guard
        # prevents malformed pending state from turning this into an action loop.
        for _ in range(2):
            pending = self.engine.state.pending_action
            if not pending or pending.get("player_id") != player.id:
                return
            self.engine._log_bot_decision(
                player,
                f"pending={pending['type']} cash={player.cash_won} tax={self.engine._calculate_tax_rate_bps(player)} loan={bool(self.engine.state.loans.get(player.id))}",
            )
            if player.cash_won < 0:
                self.engine._log_bot_decision(player, "skip investment: negative cash")
                self.engine.decline_pending_action(player.id)
                return
            action = self.choose_action(player)
            if action["type"] == "purchase_land":
                self.engine._log_bot_decision(player, f"buy land expected_fee={apply_rate_rounded_50k(pending['price_won'], 5, 100)} price={pending['price_won']}")
                self.engine.purchase_land(player.id)
                continue
            if action["type"] == "build":
                self.engine._log_bot_decision(player, f"build {action['building_type']} cost={self.engine.data['building_prices'][pending['region_id']][action['building_type']]}")
                self.engine.build_on_land(player.id, action["building_type"])
            elif action["type"] == "purchase_special":
                self.engine._log_bot_decision(player, f"buy special {pending['special_region_id']} price={pending['price_won']}")
                self.engine.purchase_special_region(player.id)
            else:
                self.engine._log_bot_decision(player, f"skip {pending['type']}: strategy declined")
                self.engine.decline_pending_action(player.id)
            return

    def consider_asset_disposal(self, player):
        if player.cash_won >= 0 and not self.engine.state.loans.get(player.id):
            return
        for building in list(self.engine.state.buildings):
            if building["nominal_owner_id"] != player.id or self.engine.data["board"][player.position].get("region_id") != building["region_id"]:
                continue
            try:
                self.engine._log_bot_decision(player, f"sell review {building['building_type']} loan_or_cash_risk")
                self.engine.sell_building(player.id, building["id"])
            except ValueError as exc:
                self.engine._log_bot_decision(player, f"sell rejected: {exc}")
            return

    def accepts_land_trade(self, bot, offer):
        accepted = BotStrategy(bot).accepts_land_trade(offer["price_won"], bot.id in self.engine.state.loans)
        self.engine._log_bot_decision(bot, f"{'accept' if accepted else 'reject'} trade {offer['region_id']} price={offer['price_won']}")
        return accepted

    def accepts_operating_right(self, bot, offer):
        building = self.engine._find_building(offer["building_id"])
        expected = apply_rate_rounded_50k(building["market_value_won"], 12, 100) if building else 0
        accepted = BotStrategy(bot).accepts_operating_right(offer["price_won"], expected, bot.id in self.engine.state.loans)
        self.engine._log_bot_decision(bot, f"{'accept' if accepted else 'reject'} operating right price={offer['price_won']} expected={expected}")
        return accepted

    def approves_usage_change(self, bot, request):
        approved = BotStrategy(bot).approves_usage_change(request["new_type"])
        self.engine._log_bot_decision(bot, f"{'approve' if approved else 'reject'} usage change to {request['new_type']}")
        return approved
