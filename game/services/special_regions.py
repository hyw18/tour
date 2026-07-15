class SpecialRegionService:
    def __init__(self, engine):
        self.engine = engine

    def current_value(self, special_id):
        special = self.engine.special_by_id(special_id)
        return self.engine.state.special_values.setdefault(special_id, special["initial_price"])

    def external_visit(self, special_id):
        special = self.engine.special_by_id(special_id)
        value = self.current_value(special_id) + special["initial_price"] * 20 // 100
        self.engine.state.special_values[special_id] = value
        return value
