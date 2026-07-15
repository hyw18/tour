from fractions import Fraction


class EventEffectCalculator:
    def __init__(self, engine):
        self.engine = engine

    def multiplier(self, target, player=None, region_id=None):
        multiplier = Fraction(1, 1)
        for active in self.engine.state.active_events:
            if not self.engine._event_applies(active, target, player, region_id):
                continue
            intensity = Fraction(self.engine._event_intensity_bps(active), 10_000)
            for effect in active["effects"]:
                if effect["target"] == target and effect["operation"] == "multiply":
                    effect_multiplier = Fraction(effect["value_bps"], 10_000)
                    multiplier *= 1 + (effect_multiplier - 1) * intensity
        return multiplier

    def combined_multiplier(self, targets, player=None, region_id=None):
        result = Fraction(1, 1)
        for target in targets:
            result *= self.multiplier(target, player, region_id)
        return result

    def has_explicit_override(self, target, player=None, region_id=None):
        return any(
            effect.get("explicit_override")
            for active in self.engine.state.active_events
            if self.engine._event_applies(active, target, player, region_id)
            for effect in active["effects"]
            if effect["target"] == target and effect["operation"] == "set_bps"
        )
