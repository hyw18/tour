class BankruptcyService:
    def __init__(self, engine):
        self.engine = engine

    def takeover_chain(self, pending, building, candidate_id):
        snapshot = pending["chain_snapshots"][building["id"]]
        return self.engine.rights_service.rebuild_for_takeover(
            snapshot,
            pending["bankrupt_owner_id"],
            candidate_id,
        )
