from copy import deepcopy


class SettlementService:
    def __init__(self, engine):
        self.engine = engine

    def key(self, player):
        return f"{player.id}:{self.engine.state.turn_sequence}"

    def cached(self, player):
        result = self.engine.state.settlement_results.get(self.key(player))
        return deepcopy(result) if result is not None else None

    def remember(self, player, result):
        self.engine.state.settlement_results[self.key(player)] = deepcopy(result)
        return result
