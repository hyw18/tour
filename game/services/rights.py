class RightsService:
    def __init__(self, engine, error_type):
        self.engine = engine
        self.error_type = error_type

    def validate_chain(self, building, chain):
        chain = list(chain)
        if not chain:
            raise self.error_type("ownership chain cannot be empty")
        if chain[0] != building["nominal_owner_id"]:
            raise self.error_type("chain must start with nominal owner")
        if len(chain) != len(set(chain)):
            raise self.error_type("duplicate player in ownership chain")
        if any(not self.engine._find_player(player_id) for player_id in chain):
            raise self.error_type("chain member not found")
        return chain

    def rebuild_for_takeover(self, snapshot, bankrupt_owner_id, candidate_id):
        middle = []
        for player_id in snapshot:
            if player_id in {bankrupt_owner_id, candidate_id} or player_id in middle:
                continue
            player = self.engine._find_player(player_id)
            if player and player.status not in {"bankrupt", "exited"}:
                middle.append(player_id)
        return [candidate_id, *middle]

    def normalize_consolidated_trade(self, building, new_owner_id):
        building["nominal_owner_id"] = new_owner_id
        building["owner_id"] = new_owner_id
        building["ownership_chain"] = [new_owner_id]
        building["operator_id"] = new_owner_id
        return self.validate_chain(building, building["ownership_chain"])
