"""Explicit API view builders."""


class GameViews:
    def __init__(self, engine):
        self.engine = engine

    def public(self):
        return self.engine.client_public_state()

    def host(self):
        # Host play information follows the public game rules. Operational
        # status and config are already part of the public compatibility view.
        state = self.engine.client_public_state()
        state["game_log"] = list(self.engine.state.game_log)
        return state

    def player(self, player_id):
        return self.engine.player_private_state(player_id)

    def debug(self):
        return self.engine.host_state()
