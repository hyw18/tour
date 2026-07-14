from random import choice


class BotController:
    def __init__(self, engine):
        self.engine = engine

    def run_due_bots(self):
        while self.engine.should_run_current_bot():
            player = self.engine.current_player()
            if not player or not player.is_bot:
                return
            if self.engine.state.config.fast_simulation:
                self.engine.take_turn_for_player(player.id, source="bot")
                continue
            self.engine.take_turn_for_player(player.id, source="bot")

    def choose_action(self, player):
        if player.bot_strategy == "random":
            return choice(["roll_and_end"])
        return "roll_and_end"
