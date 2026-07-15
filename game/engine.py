from copy import deepcopy
from random import Random, randint
from time import monotonic

from .data_loader import GameDataLoader
from .bots import BotController
from .models import (
    ALLOWED_BOT_DELAYS,
    ALLOWED_ROUNDS,
    ALLOWED_SLOTS,
    ALLOWED_TURN_LIMITS,
    BOARD_SIZE,
    BUILDING_TYPES,
    BOT_STRATEGIES,
    GameState,
    HostConfig,
    MAX_EMERGENCY_LOAN_PRINCIPAL_WON,
    Player,
    START_BONUS_WON,
    new_id,
)
from .economy import apply_rate, apply_rate_rounded_50k, round_to_50k
from .state import StateRepository


class GameRuleError(ValueError):
    pass


class GameEngine:
    MAX_PROCESSED_KEYS = 1_000
    COMMERCIAL_VISIT_FEE_RATES = {
        1: (270, 1000),
        2: (243, 1000),
        3: (225, 1000),
        4: (207, 1000),
        5: (180, 1000),
    }

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.data = GameDataLoader(data_dir).load()
        self.rules = self.data["official_rules"]
        self.state = GameState()
        self.state.special_values = {item["id"]: item["initial_price"] for item in self.data["special_regions"]}
        self._human_join_order = 0
        self.repository = StateRepository(self.state, self.MAX_PROCESSED_KEYS)
        self.bot_controller = BotController(self)

    def run_serialized(self, operation):
        """Run one state operation under the game-wide reentrant lock."""
        return self.repository.serialized(operation)

    def configure(self, payload):
        self._require_lobby()
        config = HostConfig(
            total_slots=int(payload.get("total_slots", self.state.config.total_slots)),
            slot_types=list(payload.get("slot_types", self.state.config.slot_types)),
            bot_strategies=list(payload.get("bot_strategies", self.state.config.bot_strategies)),
            total_rounds=int(payload.get("total_rounds", self.state.config.total_rounds)),
            turn_limit_seconds=payload.get("turn_limit_seconds", self.state.config.turn_limit_seconds),
            bot_action_delay=payload.get("bot_action_delay", self.state.config.bot_action_delay),
            fast_simulation=bool(payload.get("fast_simulation", self.state.config.fast_simulation)),
        )
        if config.turn_limit_seconds in ("", "none", "unlimited"):
            config.turn_limit_seconds = None
        elif config.turn_limit_seconds is not None:
            config.turn_limit_seconds = int(config.turn_limit_seconds)
        config.bot_action_delay = float(config.bot_action_delay)
        config.normalize()
        self._validate_config(config)
        self.state.config = config
        self._sync_lobby_bots()
        self._log("config", "host_configured", {"total_slots": config.total_slots, "total_rounds": config.total_rounds})
        return self.public_state()

    def join(self, nickname):
        self._require_lobby()
        clean = str(nickname or "").strip()
        if not clean:
            raise GameRuleError("nickname cannot be blank")
        if any(player.nickname == clean and player.status != "exited" for player in self.state.players):
            raise GameRuleError("nickname already exists")
        slot = self._first_open_human_slot()
        if slot is None:
            raise GameRuleError("room is full")
        self._human_join_order += 1
        player = Player(
            id=new_id("human"),
            nickname=clean,
            is_bot=False,
            slot_index=slot,
            join_order=self._human_join_order,
        )
        self.state.players.append(player)
        self._log("lobby", "player_joined", {"player_id": player.id, "nickname": player.nickname})
        return player.public()

    def start_game(self):
        self._require_lobby()
        self._sync_lobby_bots()
        if len(self._active_slots()) != self.state.config.total_slots:
            raise GameRuleError("not all slots are filled")
        self.state.players.sort(key=lambda player: player.slot_index)
        for player in self.state.players:
            player.status = "active"
        self.state.phase = "active"
        self.state.current_turn_index = 0
        self.state.global_round = 1
        self._start_turn()
        self._log("game", "started", {"players": [player.id for player in self.state.players]})
        if self.state.config.fast_simulation:
            self.advance_automation()
        return self.public_state()

    def close_hosting(self):
        return self.reset_game(keep_config=False)

    def end_game(self):
        self._require_started()
        return self.finalize_game("host_ended")

    def prepare_new_game(self, keep_config=True):
        return self.reset_game(keep_config=keep_config)

    def reset_game(self, keep_config=False):
        config = deepcopy(self.state.config) if keep_config else HostConfig()
        self.state = GameState()
        self.repository.replace(self.state)
        self.state.config = config
        self.state.special_values = {item["id"]: item["initial_price"] for item in self.data["special_regions"]}
        self._human_join_order = 0
        return self.client_public_state()

    def pause(self):
        self._require_started()
        if not self.state.paused:
            self.state.turn_elapsed_before_pause = self.elapsed_turn_seconds()
            self.state.paused = True
        return self.public_state()

    def resume(self):
        self._require_started()
        if self.state.paused:
            self.state.paused = False
            self.state.turn_started_at = monotonic()
        return self.public_state()

    def roll_dice(self, player_id):
        player = self._require_current_player(player_id)
        if self.state.turn_has_rolled:
            raise GameRuleError("current player already rolled")
        dice = self._next_dice()
        self.state.last_dice = dice
        self.state.turn_has_rolled = True
        start_position = player.position
        player.position = self._move_position(player.position, dice)
        self._record_activity(player)
        self._log("turn", "dice_move", {"player_id": player.id, "dice": dice, "from": start_position, "to": player.position})
        if player.position == 0:
            self._settle_start(player)
        self._resolve_arrival(player)
        return {"dice": dice, "position": player.position}

    def end_turn(self, player_id):
        player = self._require_current_player(player_id)
        self._record_activity(player)
        self._finish_turn(player.id)
        return self.public_state()

    def take_turn_for_player(self, player_id, source):
        player = self._require_current_player(player_id)
        if source == "bot" and not player.is_bot:
            raise GameRuleError("only bot can use bot turn execution")
        if not self.state.turn_has_rolled:
            self.roll_dice(player_id)
        if player.is_bot:
            self.bot_controller.consider_asset_disposal(player)
            self.bot_controller.perform_investment(player)
        self._finish_turn(player_id)
        return self.public_state()

    def purchase_land(self, player_id):
        player = self._require_current_player(player_id)
        pending = self._require_pending(player_id, "purchase_land")
        region_id = pending["region_id"]
        price = self.region_by_id(region_id)["land_price"]
        if player.cash_won < 0:
            raise GameRuleError("negative cash cannot be used for spending or investment")
        if player.cash_won < price or player.cash_won - price < 0:
            raise GameRuleError("not enough cash to buy land")
        if region_id in self.state.land_ownership:
            raise GameRuleError("land already owned")
        player.cash_won -= price
        self._add_expense(player, price, "land_purchase", region_id)
        self.state.land_ownership[region_id] = player.id
        self.state.land_purchase_laps.setdefault(player.id, {})[region_id] = self.state.lap_numbers.get(player.id, 0)
        player.lands.append(region_id)
        self.state.pending_action = None
        self._log("asset", "land_purchased", {"player_id": player.id, "region_id": region_id, "price_won": price})
        return self.public_state()

    def decline_pending_action(self, player_id):
        self._require_current_player(player_id)
        if self.state.pending_action and self.state.pending_action.get("player_id") == player_id:
            self.state.pending_action = None
        return self.public_state()

    def build_on_land(self, player_id, building_type):
        player = self._require_current_player(player_id)
        building_type = str(building_type)
        if building_type not in BUILDING_TYPES:
            raise GameRuleError("unsupported building type")
        pending = self._require_pending(player_id, "build")
        region_id = pending["region_id"]
        if self.state.land_ownership.get(region_id) != player.id:
            raise GameRuleError("can build only on own land")
        if self.state.successful_build_edit_this_visit:
            raise GameRuleError("only one successful building edit is allowed per visit")
        price = self.data["building_prices"][region_id][building_type]
        if player.cash_won < 0:
            raise GameRuleError("negative cash cannot be used for spending or investment")
        if player.cash_won < price or player.cash_won - price < 0:
            raise GameRuleError("not enough cash to build")
        if building_type in {"industrial", "mixed_use"} and self._building_count(region_id, building_type) >= 1:
            raise GameRuleError(f"{building_type} building is limited to one per region")
        player.cash_won -= price
        self._add_expense(player, price, "building_construction", region_id)
        building = {
            "id": new_id("building"),
            "region_id": region_id,
            "building_type": building_type,
            "owner_id": player.id,
            "nominal_owner_id": player.id,
            "operator_id": player.id,
            "ownership_chain": [player.id],
            "construction_cost_won": price,
            "market_value_won": price,
        }
        self.state.buildings.append(building)
        player.buildings.append(building["id"])
        self.state.successful_build_edit_this_visit = True
        self.state.pending_action = None
        self._log("asset", "building_built", {"player_id": player.id, "region_id": region_id, "building_type": building_type, "cost_won": price})
        return self.public_state()

    def sell_building(self, player_id, building_id):
        player = self._require_current_player(player_id)
        building = self._find_building(building_id)
        if not building or building["nominal_owner_id"] != player.id:
            raise GameRuleError("building not found")
        self._require_building_edit_available(player, building["region_id"])
        if len(building.get("ownership_chain", [])) != 1:
            raise GameRuleError("building with split ownership cannot be sold")
        proceeds = 0
        market_value = max(0, int(building["market_value_won"]))
        if building["building_type"] == "residential":
            proceeds = market_value
            player.cash_won += proceeds
            self._add_income(player, proceeds, "building_sale", building["region_id"], True, "residential", building["id"])
        elif building["building_type"] == "commercial":
            self.state.pending_commercial_sale_refunds.append(
                {
                    "player_id": player.id,
                    "region_id": building["region_id"],
                    "recorded_market_value_won": market_value,
                    "refund_won": apply_rate_rounded_50k(market_value, 50, 100),
                    "created_lap": self.state.lap_numbers.get(player.id, 0),
                }
            )
        elif building["building_type"] not in {"industrial", "mixed_use"}:
            raise GameRuleError("unsupported building type")
        self.state.buildings = [item for item in self.state.buildings if item["id"] != building_id]
        if building_id in player.buildings:
            player.buildings.remove(building_id)
        self.state.successful_build_edit_this_visit = True
        self._log_bot_decision(player, f"sold {building['building_type']} proceeds={proceeds} delayed={building['building_type'] == 'commercial'}")
        self._log("asset", "building_sold", {"player_id": player.id, "building_id": building_id, "building_type": building["building_type"], "proceeds_won": proceeds})
        return self.public_state()

    def force_end_current_turn(self):
        player = self.current_player()
        if player:
            self._finish_turn(player.id)
        self.advance_automation()
        return self.public_state()

    def set_player_position(self, player_id, position):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        player.position = int(position) % BOARD_SIZE
        self.state.pending_action = None
        return player.public()

    def set_player_cash(self, player_id, cash_won):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        player.cash_won = int(cash_won)
        return player.public()

    def create_land_ownership(self, player_id, region_id):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        self.region_by_id(region_id)
        previous_owner_id = self.state.land_ownership.get(region_id)
        if previous_owner_id and previous_owner_id != player.id:
            previous = self._find_player(previous_owner_id)
            if previous and region_id in previous.lands:
                previous.lands.remove(region_id)
        self.state.land_ownership[region_id] = player.id
        if region_id not in player.lands:
            player.lands.append(region_id)
        return self.public_state()

    def create_building(self, player_id, region_id, building_type):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        self.region_by_id(region_id)
        if building_type not in BUILDING_TYPES:
            raise GameRuleError("unsupported building type")
        if self.state.land_ownership.get(region_id) != player.id:
            self.create_land_ownership(player_id, region_id)
        if building_type in {"industrial", "mixed_use"} and self._building_count(region_id, building_type) >= 1:
            raise GameRuleError(f"{building_type} building is limited to one per region")
        price = self.data["building_prices"][region_id][building_type]
        building = {
            "id": new_id("building"),
            "region_id": region_id,
            "building_type": building_type,
            "owner_id": player.id,
            "nominal_owner_id": player.id,
            "operator_id": player.id,
            "ownership_chain": [player.id],
            "construction_cost_won": price,
            "market_value_won": price,
        }
        self.state.buildings.append(building)
        player.buildings.append(building["id"])
        return self.public_state()

    def set_building_market_value(self, building_id, market_value_won):
        building = self._find_building(building_id)
        if not building:
            raise GameRuleError("building not found")
        building["market_value_won"] = max(0, int(market_value_won))
        return self.public_state()

    def adjusted_building_value(self, building):
        multiplier = self._event_multiplier_bps("building_market_value", self._find_player(self._building_operator_id(building)), building["region_id"])
        return round_to_50k(apply_rate(building["market_value_won"], multiplier, 10_000))

    def set_industrial_return_rate(self, rate_bps, explicit_override=False):
        rate_bps = int(rate_bps)
        if not explicit_override:
            rate_bps = self._clamp(rate_bps, 0, 2400)
        self.state.industrial_return_rate_bps = rate_bps
        self.state.industrial_return_explicit_override = bool(explicit_override)
        return {
            "industrial_return_rate_bps": rate_bps,
            "explicit_override": self.state.industrial_return_explicit_override,
        }

    def apply_event(self, event):
        if "industrial_return_rate_bps" in event:
            return self.set_industrial_return_rate(
                event["industrial_return_rate_bps"],
                bool(event.get("explicit_override", False)),
            )
        return {"ignored": True}

    def set_player_tax_rate(self, player_id, tax_rate_bps):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        self.state.tax_rate_overrides[player.id] = int(tax_rate_bps)
        return {"player_id": player.id, "tax_rate_bps": int(tax_rate_bps)}

    def create_loan(self, player_id, principal_won):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        return self._create_emergency_loan(player, int(principal_won), "dev")

    def settle_start_for_player(self, player_id):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        return self._settle_start(player)

    def run_laps(self, player_id, laps):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        for _ in range(int(laps)):
            if player.status == "bankrupt":
                break
            player.position = 0
            self._settle_start(player)
        return self.public_state()

    def bot_economy_summary(self):
        summary = []
        for player in self.state.players:
            if not player.is_bot:
                continue
            ledger = self._ledger(player)
            loan = self.state.loans.get(player.id)
            summary.append(
                {
                    "player_id": player.id,
                    "nickname": player.nickname,
                    "cash_won": player.cash_won,
                    "gross_income": ledger["gross_income"],
                    "tax_due": ledger["tax_due"],
                    "loan_remaining_due_won": loan["remaining_due_won"] if loan else 0,
                    "status": player.status,
                }
            )
        return {"bots": summary, "debug_log": list(self.state.bot_debug_log)}

    def force_bankruptcy(self, player_id, reason="forced"):
        if self.state.ended:
            raise GameRuleError("game has ended")
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        return self._bankrupt_player(player, reason)

    def set_no_action_count(self, player_id, count):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        self.state.no_action_counts[player.id] = int(count)
        if self.state.no_action_counts[player.id] >= 3 and not self.state.paused and not player.is_bot:
            self._exit_player(player, "no_action")
        return self.public_state()

    def record_bot_action_failure(self, player_id):
        player = self._find_player(player_id)
        if not player or not player.is_bot:
            raise GameRuleError("bot player not found")
        self._record_no_action(player, "bot_action_failure")
        self._log_bot_decision(player, "action failure recorded as no-action")
        return self.public_state()

    def respond_land_takeover(self, player_id, accept):
        pending = self.state.pending_land_takeover
        if not pending:
            raise GameRuleError("no pending land takeover")
        if pending["candidate_id"] != player_id:
            raise GameRuleError("only takeover candidate can respond")
        candidate = self._find_player(player_id)
        if accept and candidate and candidate.cash_won >= pending["land_price_won"]:
            candidate.cash_won -= pending["land_price_won"]
            self.state.land_ownership[pending["region_id"]] = candidate.id
            if pending["region_id"] not in candidate.lands:
                candidate.lands.append(pending["region_id"])
            for building in self.state.buildings:
                if building["region_id"] == pending["region_id"]:
                    chain = [member for member in building["ownership_chain"] if self._find_player(member) and self._find_player(member).status != "bankrupt"]
                    if candidate.id in chain:
                        candidate_index = chain.index(candidate.id)
                        building["ownership_chain"] = [candidate.id] + chain[candidate_index + 1 :]
                    else:
                        building["ownership_chain"] = [candidate.id]
                    building["nominal_owner_id"] = candidate.id
                    building["owner_id"] = candidate.id
                    building["operator_id"] = building["ownership_chain"][-1]
        else:
            if candidate:
                candidate.cash_won += pending["refund_won"]
                self._add_income(candidate, pending["refund_won"], "bankruptcy_takeover_declined_refund", pending["region_id"], True)
            self.state.land_ownership.pop(pending["region_id"], None)
            self.state.buildings = [building for building in self.state.buildings if building["region_id"] != pending["region_id"]]
        self.state.pending_land_takeover = None
        return self.public_state()

    def set_takeover_decision(self, player_id, accept):
        self.state.forced_takeover_decisions[player_id] = bool(accept)
        return {"player_id": player_id, "accept": bool(accept)}

    def skip_revival_wait(self, player_id, rounds=20):
        record = self.state.bankruptcy_records.get(player_id)
        if not record:
            raise GameRuleError("bankruptcy record not found")
        record["bankruptcy_round"] = self.state.global_round - int(rounds)
        return record

    def revive_player(self, player_id):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        if not self._can_revive(player):
            raise GameRuleError("revival conditions are not met")
        player.status = "active"
        player.position = 0
        player.cash_won = 10_000_000
        player.lands = []
        player.buildings = []
        player.loans = []
        player.operating_rights = []
        self.state.loans.pop(player.id, None)
        self.state.revival_counts[player.id] = self.state.revival_counts.get(player.id, 0) + 1
        self._log_bot_decision(player, "revived")
        return self.public_state()

    def evaluate_bot_revivals(self):
        for player in self.state.players:
            if not player.is_bot or player.status != "bankrupt":
                continue
            if not self._can_revive(player):
                continue
            remaining = self.state.config.total_rounds - self.state.global_round
            if player.bot_strategy in {"balanced", "conservative"}:
                decision = True
                reason = "default revive strategy"
            elif player.bot_strategy == "aggressive":
                decision = remaining > 60
                reason = f"aggressive comeback remaining={remaining}"
            else:
                decision = randint(1, 2) == 1
                reason = "random revive roll"
            self._log_bot_decision(player, f"{'revive' if decision else 'skip revive'}: {reason}")
            if decision:
                self.revive_player(player.id)
        return self.public_state()

    def trigger_event(self, event_id=None, player_id=None, region_id=None, source="manual"):
        event = self._choose_event(event_id)
        if not event["enabled"]:
            raise GameRuleError("event is disabled")
        if source not in {"event_cell", "chain", "manual"}:
            raise GameRuleError("unsupported event source")
        player = self._find_player(player_id) if player_id else self.current_player()
        if event["scope"] == "personal" and not player:
            raise GameRuleError("personal event requires player")
        if event["scope"] == "regional" and not region_id:
            region_id = self._first_region_id()
        active = {
            "id": event["id"],
            "scope": event["scope"],
            "player_id": player.id if player else None,
            "region_id": region_id,
            "effects": deepcopy(event["effects"]),
            "duration_rounds": int(event["duration_rounds"]),
            "recovery_rounds": int(event["recovery_rounds"]),
            "age_rounds": 0,
            "source": source,
        }
        self.state.active_events.append(active)
        self.state.event_history.append({"id": event["id"], "round": self.state.global_round, "source": source})
        self._log("event", "event_triggered", {"event_id": event["id"], "source": source, "player_id": player.id if player else None, "region_id": region_id})
        if player:
            self._build_personal_report(player)
        if event.get("can_chain_event") and event.get("chained_event_pool"):
            self.trigger_event(event["chained_event_pool"][0], player.id if player else None, region_id, source="chain")
        return self.public_state()

    def personal_report(self, player_id):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        return self._build_personal_report(player)

    def run_bot_simulation(self, config):
        runs = max(1, min(1000, int(config.get("runs", 1))))
        seed = int(config.get("seed", 1))
        rng = Random(seed)
        strategies = config.get("strategies") or ["balanced", "aggressive"]
        player_count = int(config.get("players", len(strategies)))
        player_count = max(2, min(4, player_count))
        total_rounds = int(config.get("total_rounds", 10))
        event_enabled = bool(config.get("events_enabled", True))
        event_frequency = max(0, int(config.get("event_frequency", 1)))
        start_cash = int(config.get("starting_cash", 10_000_000))
        strategy_stats = {}
        first_bankruptcy_rounds = []
        final_assets = []
        gap_sum = 0
        event_impacts = {}
        building_counts = {item: 0 for item in BUILDING_TYPES}
        building_income = {item: 0 for item in BUILDING_TYPES}
        loan_runs = 0
        revival_count = 0
        for run in range(runs):
            sim = GameEngine("data")
            slot_strategies = [strategies[index % len(strategies)] for index in range(player_count)]
            sim.configure({"total_slots": player_count, "slot_types": ["bot"] * player_count, "bot_strategies": slot_strategies, "total_rounds": total_rounds, "bot_action_delay": 0, "fast_simulation": False})
            sim.start_game()
            for player in sim.state.players:
                player.cash_won = start_cash
            sim.state.commercial_rate_multiplier_bps = int(config.get("commercial_rate_multiplier_bps", 10_000))
            sim.state.industrial_return_rate_bps = int(config.get("industrial_base_return_bps", 1200))
            sim.state.industrial_return_min_bps = int(config.get("industrial_min_bps", 0))
            sim.state.industrial_return_max_bps = int(config.get("industrial_max_bps", 2400))
            local_first_bankruptcy = None
            for _round in range(1, total_rounds + 1):
                for player in list(sim.state.players):
                    if player.status != "active":
                        continue
                    sim.state.current_turn_index = sim._turn_players().index(player)
                    if event_enabled and event_frequency and rng.randint(1, event_frequency) == 1:
                        event = rng.choice([item for item in sim.data["events"] if item["enabled"]])
                        before = player.cash_won
                        sim.trigger_event(event["id"], player.id, sim._first_region_id(), "event_cell")
                        event_impacts.setdefault(event["id"], []).append(player.cash_won - before)
                    sim.take_turn_for_player(player.id, "bot")
                    if player.status == "bankrupt" and local_first_bankruptcy is None:
                        local_first_bankruptcy = sim.state.global_round
                if sim.state.ended:
                    break
            assets = sorted((sim._player_total_asset(player) for player in sim.state.players), reverse=True)
            final_assets.extend(assets)
            gap_sum += (assets[0] - assets[1]) if len(assets) > 1 else 0
            if local_first_bankruptcy is not None:
                first_bankruptcy_rounds.append(local_first_bankruptcy)
            if sim.state.loans:
                loan_runs += 1
            for player in sim.state.players:
                strategy_stats.setdefault(player.bot_strategy, {"wins": 0, "games": 0, "asset_sum": 0})
                strategy_stats[player.bot_strategy]["games"] += 1
                strategy_stats[player.bot_strategy]["asset_sum"] += sim._player_total_asset(player)
            winner = max(sim.state.players, key=sim._player_total_asset)
            strategy_stats[winner.bot_strategy]["wins"] += 1
            for building in sim.state.buildings:
                building_counts[building["building_type"]] += 1
        result = {
            "strategy_win_rates": {k: v["wins"] / v["games"] for k, v in strategy_stats.items()},
            "average_first_bankruptcy_round": sum(first_bankruptcy_rounds) / len(first_bankruptcy_rounds) if first_bankruptcy_rounds else None,
            "average_final_asset": sum(final_assets) / len(final_assets) if final_assets else 0,
            "building_type_purchase_counts": building_counts,
            "building_type_income": building_income,
            "loan_incidence_rate": loan_runs / runs,
            "revival_count": revival_count,
            "average_top_asset_gap": gap_sum / runs,
            "event_average_impact": {k: sum(v) / len(v) for k, v in event_impacts.items()},
            "average_game_rounds": total_rounds,
            "runs": runs,
        }
        self.state.simulation_results = result
        return result

    def change_bot_strategy(self, player_id, strategy):
        player = self._find_player(player_id)
        if not player or not player.is_bot:
            raise GameRuleError("bot player not found")
        if strategy not in BOT_STRATEGIES:
            raise GameRuleError("unsupported bot strategy")
        strategy_data = self.data["bot_strategies"][strategy]
        player.bot_strategy = strategy
        player.risk_tolerance = int(strategy_data["risk_tolerance"])
        player.difficulty = strategy_data.get("difficulty", player.difficulty)
        return player.public()

    def run_next_turns(self, turns):
        for _ in range(int(turns)):
            if self.state.phase != "active" or self.state.ended:
                break
            player = self.current_player()
            if not player:
                break
            self.take_turn_for_player(player.id, source="bot" if player.is_bot else "dev")
        return self.public_state()

    def purchase_special_region(self, player_id):
        player = self._require_current_player(player_id)
        pending = self._require_pending(player_id, "purchase_special")
        special_id = pending["special_region_id"]
        price = self.special_by_id(special_id)["initial_price"]
        if player.cash_won < 0:
            raise GameRuleError("negative cash cannot be used for spending or investment")
        if player.cash_won < price:
            raise GameRuleError("not enough cash to buy special region")
        if special_id in self.state.special_ownership:
            raise GameRuleError("special region already owned")
        player.cash_won -= price
        self._add_expense(player, price, "special_region_purchase", special_id)
        self.state.special_ownership[special_id] = player.id
        self.state.special_values.setdefault(special_id, price)
        self.state.pending_action = None
        self._log("special", "special_purchased", {"player_id": player.id, "special_region_id": special_id, "price_won": price})
        return self.public_state()

    def force_special_sale_dice(self, dice):
        dice = int(dice)
        if dice < 1 or dice > 6:
            raise GameRuleError("dice must be 1..6")
        self.state.forced_special_sale_dice_once = dice
        return {"forced_special_sale_dice_once": dice}

    def set_special_external_visits(self, special_id, visits):
        special = self.special_by_id(special_id)
        self.state.special_values[special_id] = special["initial_price"] + apply_rate(
            special["initial_price"], 20 * int(visits), 100
        )
        return {"special_region_id": special_id, "current_value_won": self.state.special_values[special_id]}

    def propose_land_trade(self, requester_id, buyer_id, region_id):
        requester = self._require_current_player(requester_id)
        buyer = self._find_player(buyer_id)
        if not buyer:
            raise GameRuleError("trade target not found")
        if buyer.id == requester.id or buyer.status != "active":
            raise GameRuleError("trade target must be another active player")
        self._require_no_active_request()
        self._validate_land_trade(requester, buyer, region_id)
        self.state.land_trade_offer = {
            "id": new_id("trade"),
            "requester_id": requester.id,
            "buyer_id": buyer.id,
            "region_id": region_id,
            "price_won": self.region_by_id(region_id)["land_price"],
            "created_at": monotonic(),
            "timeout_seconds": 10,
            "requester_elapsed_before_trade": self.elapsed_turn_seconds(),
        }
        self.state.turn_elapsed_before_pause = self.elapsed_turn_seconds()
        self.state.turn_started_at = None
        if buyer.is_bot:
            return self.respond_land_trade(buyer.id, self.bot_controller.accepts_land_trade(buyer, self.state.land_trade_offer))
        return self.public_state()

    def respond_land_trade(self, responder_id, accept):
        offer = self.state.land_trade_offer
        if not offer:
            raise GameRuleError("no active land trade offer")
        if offer["buyer_id"] != responder_id:
            raise GameRuleError("only target player can respond")
        requester = self._find_player(offer["requester_id"])
        buyer = self._find_player(offer["buyer_id"])
        if not requester or not buyer:
            self.state.land_trade_offer = None
            raise GameRuleError("trade participant not found")
        if accept:
            self._execute_land_trade(requester, buyer, offer["region_id"], offer["price_won"])
        self.state.land_trade_offer = None
        self.state.turn_started_at = monotonic()
        return self.public_state()

    def expire_land_trade(self):
        if self.state.land_trade_offer and monotonic() - self.state.land_trade_offer["created_at"] >= 10:
            self.state.land_trade_offer = None
            self.state.turn_started_at = monotonic()
        return self.public_state()

    def run_bot_land_trade(self, seller_id, buyer_id, region_id):
        seller = self._find_player(seller_id)
        if not seller:
            raise GameRuleError("seller not found")
        if seller.id != self.current_player().id:
            self.state.current_turn_index = self._turn_players().index(seller)
            self._start_turn()
        return self.propose_land_trade(seller_id, buyer_id, region_id)

    def create_ownership_chain(self, building_id, chain):
        building = self._find_building(building_id)
        if not building:
            raise GameRuleError("building not found")
        chain = list(chain)
        if not chain or chain[0] != building["nominal_owner_id"]:
            raise GameRuleError("chain must start with nominal owner")
        for player_id in chain:
            if not self._find_player(player_id):
                raise GameRuleError("chain member not found")
        building["ownership_chain"] = chain
        building["operator_id"] = chain[-1]
        return self.public_state()

    def propose_operating_right_transfer(self, requester_id, target_id, building_id, price_won):
        requester = self._require_current_player(requester_id)
        target = self._find_player(target_id)
        building = self._find_building(building_id)
        if not target or not building:
            raise GameRuleError("transfer target or building not found")
        if target.id == requester.id or target.status != "active":
            raise GameRuleError("transfer target must be another active player")
        try:
            price_won = int(price_won)
        except (TypeError, ValueError) as exc:
            raise GameRuleError("transfer price must be an integer") from exc
        if price_won < 0:
            raise GameRuleError("transfer price cannot be negative")
        self._require_no_active_request()
        self._require_chain_member_on_region(requester, building)
        if self.state.successful_build_edit_this_visit:
            raise GameRuleError("building edit action already used this visit")
        chain = building["ownership_chain"]
        if requester.id not in chain:
            raise GameRuleError("requester is not a rights holder")
        self.state.operating_right_offer = {
            "id": new_id("opright"),
            "requester_id": requester.id,
            "target_id": target.id,
            "building_id": building_id,
            "price_won": price_won,
            "created_at": monotonic(),
            "timeout_seconds": 10,
            "requester_elapsed_before_trade": self.elapsed_turn_seconds(),
        }
        self.state.turn_elapsed_before_pause = self.elapsed_turn_seconds()
        self.state.turn_started_at = None
        if target.is_bot:
            return self.respond_operating_right_transfer(target.id, self.bot_controller.accepts_operating_right(target, self.state.operating_right_offer))
        return self.public_state()

    def respond_operating_right_transfer(self, responder_id, accept):
        offer = self.state.operating_right_offer
        if not offer:
            raise GameRuleError("no active operating right offer")
        if offer["target_id"] != responder_id:
            raise GameRuleError("only target player can respond")
        requester = self._find_player(offer["requester_id"])
        target = self._find_player(offer["target_id"])
        building = self._find_building(offer["building_id"])
        if accept and requester and target and building:
            if target.cash_won < offer["price_won"]:
                raise GameRuleError("target cannot afford operating right transfer")
            target.cash_won -= offer["price_won"]
            requester.cash_won += offer["price_won"]
            building["ownership_chain"].append(target.id)
            building["operator_id"] = building["ownership_chain"][-1]
            self.state.successful_build_edit_this_visit = True
        self.state.operating_right_offer = None
        self.state.turn_started_at = monotonic()
        return self.public_state()

    def request_usage_change(self, requester_id, building_id, new_type):
        requester = self._require_current_player(requester_id)
        building = self._find_building(building_id)
        if not building:
            raise GameRuleError("building not found")
        self._require_no_active_request()
        self._require_chain_member_on_region(requester, building)
        if new_type not in BUILDING_TYPES:
            raise GameRuleError("unsupported building type")
        if requester.cash_won < 0:
            raise GameRuleError("negative cash cannot be used for usage change")
        if self.state.successful_build_edit_this_visit:
            raise GameRuleError("building edit action already used this visit")
        if new_type in {"industrial", "mixed_use"} and self._building_count_excluding(building["region_id"], new_type, building_id) >= 1:
            raise GameRuleError(f"{new_type} building is limited to one per region")
        key = (requester.id, building_id, new_type, self.state.lap_numbers.get(requester.id, 0), requester.position)
        if key in self.state.blocked_usage_change_requests:
            raise GameRuleError("same usage change request cannot be repeated this visit")
        chain = building["ownership_chain"]
        requester_index = chain.index(requester.id)
        approvers = chain[:requester_index]
        cost = self.data["building_prices"][building["region_id"]][new_type]
        if requester.cash_won < cost:
            raise GameRuleError("not enough cash for usage change")
        self.state.usage_change_request = {
            "id": new_id("usage"),
            "requester_id": requester.id,
            "building_id": building_id,
            "new_type": new_type,
            "cost_won": cost,
            "approvers": approvers,
            "responses": {},
            "created_at": monotonic(),
            "timeout_seconds": 10,
            "blocked_key": key,
        }
        for approver_id in approvers:
            approver = self._find_player(approver_id)
            forced = self.state.forced_approval_responses.get(approver_id)
            if forced is not None:
                self.respond_usage_change(approver_id, forced)
            elif approver and approver.is_bot:
                self.respond_usage_change(approver_id, self.bot_controller.approves_usage_change(approver, self.state.usage_change_request))
        if not approvers:
            self._execute_usage_change()
        return self.public_state()

    def respond_usage_change(self, approver_id, approve):
        request = self.state.usage_change_request
        if not request:
            raise GameRuleError("no active usage change request")
        if approver_id not in request["approvers"]:
            raise GameRuleError("player is not an approver")
        request["responses"][approver_id] = bool(approve)
        if approve is False:
            self.state.blocked_usage_change_requests.add(tuple(request["blocked_key"]))
            self.state.usage_change_request = None
            return self.public_state()
        if all(request["responses"].get(player_id, True) for player_id in request["approvers"]) and set(request["responses"]) >= set(request["approvers"]):
            self._execute_usage_change()
        return self.public_state()

    def expire_usage_change(self):
        request = self.state.usage_change_request
        if request and monotonic() - request["created_at"] >= 10:
            for approver_id in request["approvers"]:
                request["responses"].setdefault(approver_id, True)
            self._execute_usage_change()
        return self.public_state()

    def recall_operating_rights(self, requester_id, building_id):
        requester = self._require_current_player(requester_id)
        building = self._find_building(building_id)
        if not building:
            raise GameRuleError("building not found")
        self._require_chain_member_on_region(requester, building)
        self._require_building_edit_available(requester, building["region_id"])
        chain = building["ownership_chain"]
        index = chain.index(requester.id)
        if index == len(chain) - 1:
            raise GameRuleError("no lower rights to recall")
        nominal_owner = self._find_player(chain[0])
        recipient = self._find_player(chain[-1])
        payout = max(0, int(building["market_value_won"]))
        if not nominal_owner or nominal_owner.cash_won < payout:
            raise GameRuleError("nominal owner cannot afford recall")
        nominal_owner.cash_won -= payout
        if recipient:
            recipient.cash_won += payout
            self._add_income(recipient, payout, "operating_right_recall", building["region_id"], True, building["building_type"], building["id"])
        building["ownership_chain"] = chain[: index + 1]
        building["operator_id"] = building["ownership_chain"][-1]
        self.state.successful_build_edit_this_visit = True
        return self.public_state()

    def force_approval_response(self, player_id, approve):
        self.state.forced_approval_responses[player_id] = bool(approve)
        return {"player_id": player_id, "approve": bool(approve)}

    def set_forced_dice(self, dice):
        dice = int(dice)
        if dice < 1 or dice > 6:
            raise GameRuleError("dice must be 1..6")
        self.state.forced_dice_once = dice
        return {"forced_dice_once": dice}

    def fast_forward_rounds(self, rounds=1):
        target = min(self.state.config.total_rounds, self.state.global_round + int(rounds))
        while self.state.phase == "active" and not self.state.ended and self.state.global_round < target:
            player = self.current_player()
            if not player:
                break
            self.take_turn_for_player(player.id, source="bot" if player.is_bot else "dev")
        return self.public_state()

    def set_bot_auto(self, enabled):
        self.state.bot_auto_enabled = bool(enabled)
        self.advance_automation()
        return self.public_state()

    def run_all_bot_max_speed(self):
        if any(not player.is_bot for player in self.state.players if player.status == "active"):
            raise GameRuleError("max speed all-bot run requires all active players to be bots")
        while self.state.phase == "active" and not self.state.ended:
            player = self.current_player()
            if not player:
                break
            self.take_turn_for_player(player.id, source="bot")
        return self.public_state()

    def advance_automation(self, force=False):
        if self.state.phase != "active" or self.state.paused or self.state.ended:
            return
        self.evaluate_bot_revivals()
        self.expire_land_trade()
        self.expire_operating_right_offer()
        self.expire_usage_change()
        if self._turn_timed_out():
            player = self.current_player()
            if player:
                self._record_no_action(player, "turn_timeout")
                self._finish_turn(player.id)
        while True:
            player = self.current_player()
            if not player or not player.is_bot:
                return
            if not force and not self.state.bot_auto_enabled and not self.state.config.fast_simulation:
                return
            if not self.should_run_current_bot():
                return
            self.take_turn_for_player(player.id, source="bot")

    def should_run_current_bot(self):
        if self.state.phase != "active" or self.state.paused or self.state.ended:
            return False
        player = self.current_player()
        if not player or not player.is_bot:
            return False
        delay = 0 if self.state.config.fast_simulation else float(player.action_delay or 0)
        return self.elapsed_turn_seconds() >= delay

    def current_player(self):
        active = self._turn_players()
        if not active:
            return None
        return active[self.state.current_turn_index % len(active)]

    def elapsed_turn_seconds(self):
        if self.state.turn_started_at is None:
            return self.state.turn_elapsed_before_pause
        if self.state.paused:
            return self.state.turn_elapsed_before_pause
        return self.state.turn_elapsed_before_pause + (monotonic() - self.state.turn_started_at)

    def with_idempotency(self, key, operation):
        return self.repository.idempotent(key, operation, GameRuleError)

    def ui_phase(self):
        if self.state.ended:
            return "finished"
        if self.state.paused:
            return "paused"
        if self.state.phase == "active":
            return "active"
        if any(not player.is_bot and player.status != "exited" for player in self.state.players):
            return "lobby"
        return "setup"

    def public_state(self):
        config = self.state.config
        return {
            "rules_version": self.rules["rules_version"],
            "phase": self.ui_phase(),
            "engine_phase": self.state.phase,
            "server_status": "online",
            "paused": self.state.paused,
            "ended": self.state.ended,
            "global_round": self.state.global_round,
            "current_turn_player_id": self.current_player().id if self.current_player() else None,
            "turn_has_rolled": self.state.turn_has_rolled,
            "last_dice": self.state.last_dice,
            "last_activity_player_id": self.state.last_activity_player_id,
            "elapsed_turn_seconds": round(self.elapsed_turn_seconds(), 3),
            "pending_action": self.state.pending_action,
            "land_ownership": dict(self.state.land_ownership),
            "buildings": list(self.state.buildings),
            "pending_commercial_sale_refunds": list(self.state.pending_commercial_sale_refunds),
            "special_ownership": dict(self.state.special_ownership),
            "special_values": dict(self.state.special_values),
            "land_trade_offer": deepcopy(self.state.land_trade_offer),
            "operating_right_offer": deepcopy(self.state.operating_right_offer),
            "usage_change_request": deepcopy(self.state.usage_change_request),
            "active_events": deepcopy(self.state.active_events),
            "event_history": list(self.state.event_history),
            "bankruptcy_records": deepcopy(self.state.bankruptcy_records),
            "bankruptcy_order": list(self.state.bankruptcy_order),
            "revival_counts": dict(self.state.revival_counts),
            "no_action_counts": dict(self.state.no_action_counts),
            "rankings": dict(self.state.rankings),
            "pending_land_takeover": deepcopy(self.state.pending_land_takeover),
            "industrial_return_rate_bps": self.state.industrial_return_rate_bps,
            "industrial_return_explicit_override": self.state.industrial_return_explicit_override,
            "public_wealth": self.public_wealth(),
            "final_results": deepcopy(self.state.final_results),
            "board": self.data["board"],
            "config": {
                "total_slots": config.total_slots,
                "slot_types": config.slot_types,
                "bot_strategies": config.bot_strategies,
                "total_rounds": config.total_rounds,
                "turn_limit_seconds": config.turn_limit_seconds,
                "bot_action_delay": config.bot_action_delay,
                "fast_simulation": config.fast_simulation,
            },
            "players": [player.public() for player in sorted(self.state.players, key=lambda p: p.slot_index)],
        }

    def host_state(self):
        state = self.public_state()
        state.update(
            {
                "personal_reports": deepcopy(self.state.personal_reports),
                "simulation_results": deepcopy(self.state.simulation_results),
                "debt_writeoffs": dict(self.state.debt_writeoffs),
                "ledgers": deepcopy(self.state.ledgers),
                "loans": deepcopy(self.state.loans),
                "tax_rate_overrides": dict(self.state.tax_rate_overrides),
                "last_settlement": deepcopy(self.state.last_settlement),
                "bot_debug_log": list(self.state.bot_debug_log),
                "game_log": list(self.state.game_log),
                "asset_history": deepcopy(self.state.asset_history),
            }
        )
        return state

    def client_public_state(self):
        state = self.public_state()
        state["players"] = [
            {
                "id": player["id"],
                "nickname": player["nickname"],
                "is_bot": player["is_bot"],
                "slot_index": player["slot_index"],
                "join_order": player["join_order"],
                "status": player["status"],
                "position": player["position"],
                "lands": player["lands"],
                "buildings": player["buildings"],
                "operating_rights": player["operating_rights"],
                **(
                    {
                        "bot_strategy": player.get("bot_strategy"),
                        "difficulty": player.get("difficulty"),
                        "risk_tolerance": player.get("risk_tolerance"),
                        "action_delay": player.get("action_delay"),
                    }
                    if player["is_bot"]
                    else {}
                ),
            }
            for player in state["players"]
        ]
        state["land_trade_offer"] = self._public_offer_summary(state.get("land_trade_offer"), "land_trade")
        state["operating_right_offer"] = self._public_offer_summary(state.get("operating_right_offer"), "operating_right")
        state["usage_change_request"] = self._public_offer_summary(state.get("usage_change_request"), "usage_change")
        state.pop("pending_commercial_sale_refunds", None)
        state.pop("bankruptcy_records", None)
        state.pop("pending_land_takeover", None)
        state["regions"] = deepcopy(self.data["regions"])
        state["special_regions"] = deepcopy(self.data["special_regions"])
        state["special_region_details"] = self._special_region_details()
        return state

    def _special_region_details(self):
        details = {}
        for special in self.data["special_regions"]:
            special_id = special["id"]
            initial = special["initial_price"]
            current = self.state.special_values.get(special_id, initial)
            increase = apply_rate(initial, 20, 100)
            details[special_id] = {
                "special_region_id": special_id,
                "name": special["name"],
                "initial_price_won": initial,
                "current_value_won": current,
                "external_visits": max(0, (current - initial) // max(1, increase)),
                "next_increase_won": increase,
                "owner_id": self.state.special_ownership.get(special_id),
                "forced_sale_min_won": apply_rate_rounded_50k(current, 84, 100),
                "forced_sale_max_won": apply_rate_rounded_50k(current, 104, 100),
            }
        return details

    def _public_offer_summary(self, offer, offer_type):
        if not offer:
            return None
        return {
            "type": offer_type,
            "active": True,
            "timeout_seconds": offer.get("timeout_seconds", 10),
            "response_rule": "auto_approve" if offer_type == "usage_change" else "auto_reject",
        }

    def player_private_state(self, player_id):
        player = self._find_player(player_id)
        if not player:
            raise GameRuleError("player not found")
        ledger = deepcopy(self.state.ledgers.get(player.id, {}))
        loan = deepcopy(self.state.loans.get(player.id))
        if loan:
            loan["interest_won"] = loan["total_due_won"] - loan["principal_won"]
            loan["due_laps_remaining"] = max(0, loan["due_lap"] - self.state.lap_numbers.get(player.id, 0))
            loan["auto_repay"] = True
        refunds = [
            deepcopy(item)
            for item in self.state.pending_commercial_sale_refunds
            if item["player_id"] == player.id
        ]
        last_settlement = self.state.last_settlement
        if not last_settlement or last_settlement.get("player_id") != player.id:
            last_settlement = None
        return {
            "player": player.public(),
            "ledger": ledger,
            "loan": loan,
            "tax_rate_bps": self._calculate_tax_rate_bps(player),
            "report": self._build_personal_report(player),
            "asset_history": deepcopy(self.state.asset_history.get(player.id, [])),
            "assets": self._player_assets(player),
            "pending_commercial_sale_refunds": refunds,
            "last_settlement": deepcopy(last_settlement),
            "allowed_actions": self._allowed_actions(player),
            "related_requests": self._related_requests(player),
            "bankruptcy": self._player_bankruptcy_state(player),
            "turn_remaining_seconds": self._turn_remaining_seconds(),
            "recent_income": deepcopy(ledger.get("income_entries", [])[-10:]),
            "recent_expenses": deepcopy(ledger.get("expense_entries", [])[-10:]),
            "active_events": [
                deepcopy(event)
                for event in self.state.active_events
                if event.get("player_id") in {None, player.id}
            ],
        }

    def _turn_remaining_seconds(self):
        limit = self.state.config.turn_limit_seconds
        if limit is None:
            return None
        return max(0, round(limit - self.elapsed_turn_seconds(), 1))

    def _action(self, allowed, reason="", **details):
        return {"allowed": bool(allowed), "reason": "" if allowed else reason, **details}

    def _allowed_actions(self, player):
        accepting = self.state.phase == "active" and not self.state.paused and not self.state.ended
        is_turn = accepting and self.current_player() is not None and self.current_player().id == player.id
        turn_reason = "현재 차례가 아닙니다."
        if not accepting:
            turn_reason = "현재 게임 상태에서는 행동할 수 없습니다."
        elif player.status != "active":
            turn_reason = "활성 플레이어만 행동할 수 있습니다."
        pending = self.state.pending_action if is_turn and self.state.pending_action and self.state.pending_action.get("player_id") == player.id else None
        cell = self.data["board"][player.position]
        current_region_id = cell.get("region_id") if cell.get("type") == "region" else None
        edit_used = self.state.successful_build_edit_this_visit
        request_active = bool(self.state.land_trade_offer or self.state.operating_right_offer or self.state.usage_change_request)
        current_buildings = [item for item in self.state.buildings if item["region_id"] == current_region_id]
        owned_current = bool(current_region_id and self.state.land_ownership.get(current_region_id) == player.id)
        chain_buildings = [item for item in current_buildings if player.id in item.get("ownership_chain", [])]

        trade_targets = []
        if is_turn and owned_current:
            for target in self._turn_players():
                if target.id == player.id:
                    continue
                try:
                    self._validate_land_trade(player, target, current_region_id)
                except GameRuleError:
                    continue
                trade_targets.append({"id": target.id, "nickname": target.nickname})

        build_allowed = bool(pending and pending.get("type") == "build" and not edit_used)
        build_reason = "현재 지역에서 건설할 수 없습니다."
        if edit_used:
            build_reason = "이번 방문의 건물 편집 기회를 이미 사용했습니다."
        elif not owned_current:
            build_reason = "내 토지가 아닙니다."

        has_sellable = any(
            item["nominal_owner_id"] == player.id and len(item.get("ownership_chain", [])) == 1
            for item in current_buildings
        )
        can_manage = is_turn and bool(current_region_id) and bool(chain_buildings or owned_current) and not edit_used and not request_active
        actions = {
            "roll": self._action(is_turn and not self.state.turn_has_rolled, "이미 주사위를 굴렸습니다." if is_turn else turn_reason),
            "end_turn": self._action(is_turn, turn_reason),
            "purchase_land": self._action(bool(pending and pending.get("type") == "purchase_land"), "구매 가능한 토지에 도착하지 않았습니다."),
            "decline_action": self._action(bool(pending), "포기할 대기 행동이 없습니다."),
            "purchase_special": self._action(bool(pending and pending.get("type") == "purchase_special"), "구매 가능한 특수지역에 도착하지 않았습니다."),
            "build": self._action(build_allowed, build_reason, building_types=list((pending or {}).get("available_buildings", []))),
            "manage": self._action(can_manage, "현재 지역에서 실행 가능한 관리 행동이 없습니다."),
            "sell_building": self._action(can_manage and has_sellable, "매각 가능한 단독 소유 건물이 없습니다."),
            "propose_land_trade": self._action(is_turn and owned_current and bool(trade_targets) and not request_active, "다른 요청이 진행 중이거나 권리가 분산되어 거래할 수 없습니다.", targets=trade_targets, region_id=current_region_id),
            "propose_operating_right": self._action(can_manage and bool(chain_buildings), "현재 지역에 양도할 운영권이 없습니다."),
            "request_usage_change": self._action(can_manage and bool(chain_buildings), "현재 지역에 용도 변경할 권리 보유 건물이 없습니다."),
            "recall_rights": self._action(
                can_manage and any(player.id in item.get("ownership_chain", [])[:-1] for item in chain_buildings),
                "회수할 하위 운영권이 없습니다.",
            ),
            "revive": self._action(self._can_revive(player), self._revival_reason(player)),
        }
        actions["trade"] = self._action(
            actions["propose_land_trade"]["allowed"] or actions["propose_operating_right"]["allowed"],
            "현재 지역에서 가능한 거래가 없습니다.",
        )
        return actions

    def _player_assets(self, player):
        player_names = {item.id: item.nickname for item in self.state.players}
        lands = []
        for region_id, owner_id in self.state.land_ownership.items():
            if owner_id != player.id:
                continue
            region = self.region_by_id(region_id)
            lands.append({
                "region_id": region_id,
                "name": region["name"],
                "land_price_won": region["land_price"],
                "building_ids": [item["id"] for item in self.state.buildings if item["region_id"] == region_id],
            })

        buildings = []
        for building in self.state.buildings:
            chain = list(building.get("ownership_chain") or [building["nominal_owner_id"]])
            if player.id not in chain and building.get("nominal_owner_id") != player.id:
                continue
            region = self.region_by_id(building["region_id"])
            operator_id = chain[-1]
            rate_bps = 0
            rate_kind = "없음"
            if building["building_type"] == "industrial":
                rate_bps = self._adjusted_industrial_rate_bps(player, building["region_id"])
                rate_kind = "출발지 수익률"
            elif building["building_type"] == "mixed_use":
                raw = self._adjusted_industrial_rate_bps(player, building["region_id"]) - 200
                rate_bps = raw if self.state.industrial_return_explicit_override else self._clamp(raw, 0, 2200)
                rate_kind = "출발지 수익률"
            elif building["building_type"] == "commercial":
                rate_bps = self._building_visit_fee_rate_bps(building["region_id"], "commercial")
                rate_kind = "방문료율"
            can_sell = (
                self.current_player() is not None
                and self.current_player().id == player.id
                and building["nominal_owner_id"] == player.id
                and len(chain) == 1
                and self.data["board"][player.position].get("region_id") == building["region_id"]
                and not self.state.successful_build_edit_this_visit
            )
            on_region = self.data["board"][player.position].get("region_id") == building["region_id"]
            can_edit = self.current_player() is not None and self.current_player().id == player.id and on_region and not self.state.successful_build_edit_this_visit
            nominal_owner = self._find_player(chain[0])
            can_recall = can_edit and player.id in chain[:-1] and bool(nominal_owner and nominal_owner.cash_won >= max(0, int(building["market_value_won"])))
            requester_index = chain.index(player.id)
            usage_chain = ([chain[0], player.id] if player.id != chain[0] else [chain[0]]) + [item for item in chain[1:] if item != player.id]
            usage_options = {}
            for building_type in sorted(BUILDING_TYPES):
                cost = self.data["building_prices"][building["region_id"]][building_type]
                blocked_key = (player.id, building["id"], building_type, self.state.lap_numbers.get(player.id, 0), player.position)
                limit_blocked = building_type in {"industrial", "mixed_use"} and self._building_count_excluding(building["region_id"], building_type, building["id"]) >= 1
                option_allowed = can_edit and player.cash_won >= cost and not limit_blocked and blocked_key not in self.state.blocked_usage_change_requests
                reason = ""
                if not can_edit:
                    reason = "권리 보유자가 해당 지역에 정확히 도착해야 합니다."
                elif player.cash_won < cost:
                    reason = "용도 변경 비용이 부족합니다."
                elif limit_blocked:
                    reason = f"{building_type} 건물은 지역당 하나만 허용됩니다."
                elif blocked_key in self.state.blocked_usage_change_requests:
                    reason = "같은 방문에서 거절된 요청은 다시 보낼 수 없습니다."
                usage_options[building_type] = {
                    "allowed": option_allowed,
                    "reason": reason,
                    "cost_won": cost,
                    "expected_chain": usage_chain,
                }
            sale_mode = {
                "residential": "현재 시세 즉시 지급",
                "commercial": "현재 시세 50%를 다음 출발지에서 지급",
                "industrial": "즉시 지급 없이 제거",
                "mixed_use": "즉시 지급 없이 제거",
            }[building["building_type"]]
            buildings.append({
                **deepcopy(building),
                "region_name": region["name"],
                "adjusted_market_value_won": self.adjusted_building_value(building),
                "nominal_owner_name": player_names.get(building["nominal_owner_id"], building["nominal_owner_id"]),
                "operator_name": player_names.get(operator_id, operator_id),
                "ownership_chain_names": [player_names.get(item, item) for item in chain],
                "return_rate_bps": rate_bps,
                "return_rate_kind": rate_kind,
                "sale_mode": sale_mode,
                "immediate_sale_proceeds_won": max(0, int(building["market_value_won"])) if building["building_type"] == "residential" else 0,
                "scheduled_refund_won": apply_rate_rounded_50k(max(0, int(building["market_value_won"])), 50, 100) if building["building_type"] == "commercial" else 0,
                "can_sell": can_sell,
                "sell_reason": "" if can_sell else "정확한 지역 도착, 단독 소유, 미사용 편집 기회가 필요합니다.",
                "can_transfer": can_edit and player.id in chain,
                "transfer_reason": "" if can_edit and player.id in chain else "권리 보유자가 해당 지역에 정확히 도착해야 합니다.",
                "can_request_usage_change": can_edit and player.id in chain,
                "usage_change_reason": "" if can_edit and player.id in chain else "권리 보유자가 해당 지역에 정확히 도착해야 합니다.",
                "usage_change_options": usage_options,
                "can_recall": can_recall,
                "recall_reason": "" if can_recall else "하위 권리가 없거나 명목 소유자가 회수 시세를 지급할 수 없습니다.",
                "recall_preview": {
                    "requester_id": player.id,
                    "nominal_owner_id": chain[0],
                    "current_operator_id": chain[-1],
                    "current_chain": chain,
                    "expected_chain": chain[: requester_index + 1],
                    "payout_won": max(0, int(building["market_value_won"])),
                    "payer_name": player_names.get(chain[0], chain[0]),
                    "recipient_name": player_names.get(chain[-1], chain[-1]),
                },
            })

        specials = []
        for special in self._special_region_details().values():
            if special["owner_id"] != player.id:
                continue
            specials.append(deepcopy(special))
        return {"lands": lands, "buildings": buildings, "special_regions": specials}

    def _request_view(self, offer, request_type, player):
        if not offer:
            return None
        participants = {offer.get("requester_id"), offer.get("buyer_id"), offer.get("target_id")}
        participants.update(offer.get("approvers", []))
        if player.id not in participants:
            return None
        result = deepcopy(offer)
        result["type"] = request_type
        result["remaining_seconds"] = max(0, round(offer.get("timeout_seconds", 10) - (monotonic() - offer["created_at"]), 1))
        result["response_rule"] = "auto_approve" if request_type == "usage_change" else "auto_reject"
        result["requester_name"] = getattr(self._find_player(offer.get("requester_id")), "nickname", offer.get("requester_id"))
        target_id = offer.get("buyer_id") or offer.get("target_id")
        result["target_name"] = getattr(self._find_player(target_id), "nickname", target_id)
        result["can_respond"] = player.id in ({offer.get("buyer_id"), offer.get("target_id")} | set(offer.get("approvers", []))) and player.id not in offer.get("responses", {})
        if offer.get("building_id"):
            building = self._find_building(offer["building_id"])
            if building:
                result["current_chain"] = list(building.get("ownership_chain", []))
                if request_type == "operating_right":
                    result["expected_chain"] = result["current_chain"] + [offer["target_id"]]
                elif request_type == "usage_change":
                    requester_id = offer["requester_id"]
                    nominal = result["current_chain"][0]
                    rest = [item for item in result["current_chain"][1:] if item != requester_id]
                    result["expected_chain"] = ([nominal, requester_id] if requester_id != nominal else [nominal]) + rest
        return result

    def _related_requests(self, player):
        return [
            item
            for item in (
                self._request_view(self.state.land_trade_offer, "land_trade", player),
                self._request_view(self.state.operating_right_offer, "operating_right", player),
                self._request_view(self.state.usage_change_request, "usage_change", player),
            )
            if item
        ]

    def _revival_reason(self, player):
        if player.status == "exited":
            return "자동 퇴장자는 부활할 수 없습니다."
        if player.status != "bankrupt":
            return "파산 상태가 아닙니다."
        record = self.state.bankruptcy_records.get(player.id)
        if not record:
            return "파산 기록이 없습니다."
        waited = self.state.global_round - record["bankruptcy_round"]
        if waited < 20:
            return f"부활까지 {20 - waited}라운드 남았습니다."
        if record["remaining_rounds"] <= 40:
            return "파산 당시 남은 라운드가 40 이하입니다."
        return "순위 또는 부활 횟수 조건을 충족하지 못했습니다."

    def _player_bankruptcy_state(self, player):
        record = deepcopy(self.state.bankruptcy_records.get(player.id))
        return {
            "status": player.status,
            "record": record,
            "can_revive": self._can_revive(player),
            "reason": self._revival_reason(player),
            "revival_count": self.state.revival_counts.get(player.id, 0),
            "spectating": player.status in {"bankrupt", "spectator", "exited"},
        }

    def public_wealth(self):
        rows = []
        totals = self._final_asset_totals()
        rankings = self._rank_players(totals)
        for player in sorted(self.state.players, key=lambda item: item.slot_index):
            rows.append(
                {
                    "player_id": player.id,
                    "nickname": player.nickname,
                    "status": player.status,
                    "total_asset_won": totals.get(player.id, 0),
                    "rank": rankings.get(player.id),
                }
            )
        return {"players": rows, "rankings": rankings}

    def finalize_game(self, reason="manual"):
        if self.state.final_results:
            return self.state.final_results
        self._settle_endgame_special_regions(apply_cash=reason == "final_round")
        totals = self._final_asset_totals()
        rankings = self._rank_players(totals)
        self.state.rankings.update(rankings)
        self.state.final_results = {
            "reason": reason,
            "global_round": self.state.global_round,
            "assets": totals,
            "rankings": rankings,
            "public_wealth": self.public_wealth(),
        }
        self.state.ended = True
        self.state.phase = "ended"
        self._log("final", "game_finalized", {"reason": reason, "rankings": rankings, "assets": totals})
        return self.state.final_results

    def export_results(self, kind="json"):
        if not self.state.final_results:
            self.finalize_game("export")
        result = deepcopy(self.state.final_results)
        if kind == "json":
            return result
        if kind == "csv":
            lines = ["player_id,nickname,status,total_asset_won,rank"]
            for row in result["public_wealth"]["players"]:
                lines.append(",".join(str(row[key]) for key in ("player_id", "nickname", "status", "total_asset_won", "rank")))
            return {"filename": "results.csv", "content_type": "text/csv", "body": "\n".join(lines)}
        if kind == "log":
            return {"log": list(self.state.game_log)}
        if kind == "asset-history":
            return {"asset_history": deepcopy(self.state.asset_history)}
        if kind == "bot-strategies":
            summary = {}
            for player in self.state.players:
                if player.is_bot:
                    summary.setdefault(player.bot_strategy, []).append(
                        {
                            "player_id": player.id,
                            "total_asset_won": result["assets"].get(player.id, 0),
                            "rank": result["rankings"].get(player.id),
                        }
                    )
            return {"bot_strategies": summary}
        raise GameRuleError("unsupported export kind")

    def configure_quick_game(self, preset="custom", custom=None, pause_at_round=None):
        self._require_lobby()
        presets = {
            "fast_10": {"total_rounds": 10, "fast_simulation": True},
            "standard_30": {"total_rounds": 30, "fast_simulation": True},
            "long_100": {"total_rounds": 100, "fast_simulation": True},
            "custom": dict(custom or {}),
        }
        if preset not in presets:
            raise GameRuleError("unsupported quick game preset")
        payload = presets[preset]
        self.state.quick_game_presets[preset] = deepcopy(payload)
        self.state.pause_at_round = int(pause_at_round) if pause_at_round else None
        return self.configure(payload)

    def run_quick_game(self):
        self._require_started()
        self.state.config.fast_simulation = True
        self.state.bot_auto_enabled = True
        while self.state.phase == "active" and not self.state.ended:
            if self.state.pause_at_round and self.state.global_round >= self.state.pause_at_round:
                self.pause()
                break
            player = self.current_player()
            if not player:
                break
            self.take_turn_for_player(player.id, source="bot" if player.is_bot else "dev")
        return self.host_state()

    def _validate_config(self, config):
        if config.total_slots not in ALLOWED_SLOTS:
            raise GameRuleError("total_slots must be 2..4")
        if config.total_rounds not in ALLOWED_ROUNDS:
            raise GameRuleError("total_rounds must be 10..300")
        if config.turn_limit_seconds not in ALLOWED_TURN_LIMITS:
            raise GameRuleError("turn_limit_seconds is not allowed")
        if config.bot_action_delay not in ALLOWED_BOT_DELAYS:
            raise GameRuleError("bot_action_delay is not allowed")
        for index, slot_type in enumerate(config.slot_types):
            if slot_type not in {"human", "bot"}:
                raise GameRuleError(f"slot_types[{index}] must be human or bot")
        for index, strategy in enumerate(config.bot_strategies):
            if strategy not in BOT_STRATEGIES:
                raise GameRuleError(f"bot_strategies[{index}] is not allowed")

    def _sync_lobby_bots(self):
        existing_humans = [p for p in self.state.players if not p.is_bot and p.status != "exited"]
        self.state.players = existing_humans
        bot_order = 0
        for slot, slot_type in enumerate(self.state.config.slot_types):
            if slot_type != "bot":
                continue
            bot_order += 1
            strategy = self.state.config.bot_strategies[slot]
            strategy_data = self.data["bot_strategies"][strategy]
            self.state.players.append(
                Player(
                    id=f"bot_slot_{slot}",
                    nickname=f"BOT {slot + 1}",
                    is_bot=True,
                    slot_index=slot,
                    join_order=slot,
                    bot_strategy=strategy,
                    difficulty=strategy_data.get("difficulty", "normal"),
                    risk_tolerance=int(strategy_data["risk_tolerance"]),
                    action_delay=self.state.config.bot_action_delay,
                )
            )

    def _first_open_human_slot(self):
        occupied = {player.slot_index for player in self.state.players if player.status != "exited"}
        for slot, slot_type in enumerate(self.state.config.slot_types):
            if slot_type == "human" and slot not in occupied:
                return slot
        return None

    def _active_slots(self):
        return {player.slot_index for player in self.state.players if player.status != "exited"}

    def _turn_players(self):
        return [player for player in sorted(self.state.players, key=lambda p: p.slot_index) if player.status == "active"]

    def _require_lobby(self):
        if self.state.phase != "lobby":
            raise GameRuleError("game already started")

    def _require_started(self):
        if self.state.phase not in {"active", "ended"}:
            raise GameRuleError("game has not started")

    def _require_current_player(self, player_id):
        if self.state.phase != "active" or self.state.paused or self.state.ended:
            raise GameRuleError("game is not accepting turn actions")
        player = self.current_player()
        if not player or player.id != player_id:
            raise GameRuleError("only current turn player can act")
        return player

    def _find_player(self, player_id):
        return next((player for player in self.state.players if player.id == player_id), None)

    def _find_building(self, building_id):
        return next((building for building in self.state.buildings if building["id"] == building_id), None)

    def _start_turn(self):
        self.state.turn_started_at = monotonic()
        self.state.turn_elapsed_before_pause = 0
        self.state.turn_has_rolled = False
        self.state.pending_action = None
        self.state.successful_build_edit_this_visit = False

    def _finish_turn(self, player_id):
        active = self._turn_players()
        if not active:
            self.finalize_game("no_active_players")
            return
        self.state.last_activity_player_id = player_id
        self.state.pending_action = None
        self._advance_event_steps()
        if self.state.current_turn_index >= len(active) - 1:
            self.state.global_round += 1
            self.state.current_turn_index = 0
            if self.state.global_round > self.state.config.total_rounds:
                self.finalize_game("final_round")
                return
        else:
            self.state.current_turn_index += 1
        if self._should_end_for_single_solvent_player():
            self.finalize_game("single_solvent_player")
            return
        self._record_asset_snapshot()
        if self.state.pause_at_round and self.state.global_round >= self.state.pause_at_round:
            self.pause()
            return
        self._start_turn()

    def _record_activity(self, player):
        self.state.last_activity_player_id = player.id
        self.state.no_action_counts[player.id] = 0

    def _record_no_action(self, player, reason):
        if self.state.paused:
            return
        self.state.no_action_counts[player.id] = self.state.no_action_counts.get(player.id, 0) + 1
        if player.is_bot:
            self._log_bot_decision(player, f"no-action recorded: {reason}")
            return
        if self.state.no_action_counts[player.id] >= 3:
            self._exit_player(player, reason)

    def _next_dice(self):
        if self.state.forced_dice_once is not None:
            dice = self.state.forced_dice_once
            self.state.forced_dice_once = None
            return dice
        return randint(1, 6)

    def _move_position(self, start, dice):
        target = start + dice
        if start != 0 and target >= BOARD_SIZE:
            return 0
        return target % BOARD_SIZE

    def _turn_timed_out(self):
        limit = self.state.config.turn_limit_seconds
        return limit is not None and self.elapsed_turn_seconds() >= limit

    def _resolve_arrival(self, player):
        self.state.pending_action = None
        self.state.successful_build_edit_this_visit = False
        cell = self.data["board"][player.position]
        if cell["type"] == "special":
            self._resolve_special_arrival(player, cell["special_region_id"])
            return
        if cell["type"] == "event":
            self.trigger_event(player_id=player.id, region_id=self._first_region_id(), source="event_cell")
            return
        if cell["type"] != "region":
            return
        region_id = cell["region_id"]
        owner_id = self.state.land_ownership.get(region_id)
        if owner_id is None:
            self.state.pending_action = {
                "type": "purchase_land",
                "player_id": player.id,
                "region_id": region_id,
                "price_won": self.region_by_id(region_id)["land_price"],
            }
            return
        if owner_id == player.id:
            self.state.pending_action = {
                "type": "build",
                "player_id": player.id,
                "region_id": region_id,
                "available_buildings": self.available_buildings(region_id),
            }
            return
        if not self._pay_building_visit_fees(player, region_id):
            self._pay_land_fee(player, owner_id, region_id)

    def _pay_land_fee(self, visitor, owner_id, region_id):
        owner = self._find_player(owner_id)
        fee = apply_rate_rounded_50k(self.region_by_id(region_id)["land_price"], 5, 100)
        visitor.cash_won -= fee
        self._add_expense(visitor, fee, "land_fee", region_id)
        if owner:
            owner.cash_won += fee
            self._add_income(owner, fee, "land_fee", region_id, taxable=True, building_type="land")
        self._log("fee", "land_fee_paid", {"visitor_id": visitor.id, "owner_id": owner_id, "region_id": region_id, "amount_won": fee})

    def _pay_building_visit_fees(self, visitor, region_id):
        paid_any = False
        for building in self.state.buildings:
            if building["region_id"] != region_id or building["building_type"] not in {"commercial", "mixed_use"}:
                continue
            operator = self._find_player(self._building_operator_id(building))
            if not operator:
                continue
            rate_bps = self._building_visit_fee_rate_bps(region_id, building["building_type"])
            fee = round_to_50k(apply_rate(self.adjusted_building_value(building), rate_bps, 10_000))
            if fee <= 0:
                continue
            visitor.cash_won -= fee
            operator.cash_won += fee
            self._add_expense(visitor, fee, "building_visit_fee", region_id, building["id"])
            self._add_income(operator, fee, "building_visit_fee", region_id, True, building["building_type"], building["id"])
            self._log("fee", "building_visit_fee_paid", {"visitor_id": visitor.id, "operator_id": operator.id, "building_id": building["id"], "amount_won": fee})
            paid_any = True
        return paid_any

    def _resolve_special_arrival(self, player, special_id):
        special = self.special_by_id(special_id)
        self.state.special_values.setdefault(special_id, special["initial_price"])
        owner_id = self.state.special_ownership.get(special_id)
        if owner_id is None:
            self.state.pending_action = {
                "type": "purchase_special",
                "player_id": player.id,
                "special_region_id": special_id,
                "price_won": special["initial_price"],
            }
            return
        if owner_id == player.id:
            self._force_sell_special_region(player, special_id)
            return
        self.state.special_values[special_id] += apply_rate(special["initial_price"], 20, 100)
        self._log("special", "special_external_visit", {"player_id": player.id, "special_region_id": special_id, "value_won": self.state.special_values[special_id]})

    def _force_sell_special_region(self, player, special_id):
        dice = self._next_special_sale_dice()
        payout = apply_rate_rounded_50k(self.state.special_values[special_id], {1: 84, 2: 88, 3: 92, 4: 96, 5: 100, 6: 104}[dice], 100)
        player.cash_won += payout
        self._add_income(player, payout, "special_region_forced_sale", special_id, True)
        self.state.special_ownership.pop(special_id, None)
        self.state.special_values[special_id] = self.special_by_id(special_id)["initial_price"]
        self.state.last_settlement = {"type": "special_forced_sale", "player_id": player.id, "special_region_id": special_id, "dice": dice, "payout_won": payout}
        self._log("special", "special_forced_sale", self.state.last_settlement)

    def _settle_endgame_special_regions(self, apply_cash=True):
        payouts = []
        for special_id, owner_id in list(self.state.special_ownership.items()):
            owner = self._find_player(owner_id)
            if not owner:
                continue
            payout = apply_rate_rounded_50k(self.state.special_values[special_id], 120, 100)
            if apply_cash:
                owner.cash_won += payout
                self._add_income(owner, payout, "special_region_endgame_value", special_id, True)
            payouts.append({"player_id": owner.id, "special_region_id": special_id, "payout_won": payout})
        if apply_cash:
            self.state.special_ownership.clear()
        self.state.last_settlement = {"type": "endgame_special_region_value", "payouts": payouts}
        self._log("special", "endgame_special_regions", {"payouts": payouts})

    def _next_special_sale_dice(self):
        if self.state.forced_special_sale_dice_once is not None:
            dice = self.state.forced_special_sale_dice_once
            self.state.forced_special_sale_dice_once = None
            return dice
        return randint(1, 6)

    def _has_commercial_or_mixed(self, region_id):
        return any(
            building["region_id"] == region_id and building["building_type"] in {"commercial", "mixed_use"}
            for building in self.state.buildings
        )

    def available_buildings(self, region_id):
        available = ["residential", "commercial"]
        if self._building_count(region_id, "industrial") < 1:
            available.append("industrial")
        if self._building_count(region_id, "mixed_use") < 1:
            available.append("mixed_use")
        return available

    def _building_count(self, region_id, building_type):
        return sum(
            1
            for building in self.state.buildings
            if building["region_id"] == region_id and building["building_type"] == building_type
        )

    def _require_pending(self, player_id, pending_type):
        pending = self.state.pending_action
        if not pending or pending.get("player_id") != player_id or pending.get("type") != pending_type:
            raise GameRuleError(f"no pending {pending_type} action")
        return pending

    def region_by_id(self, region_id):
        for region in self.data["regions"]:
            if region["id"] == region_id:
                return region
        raise GameRuleError("region not found")

    def special_by_id(self, special_id):
        for special in self.data["special_regions"]:
            if special["id"] == special_id:
                return special
        raise GameRuleError("special region not found")

    def _require_building_edit_available(self, player, region_id):
        if self.state.successful_build_edit_this_visit:
            raise GameRuleError("building edit action already used this visit")
        cell = self.data["board"][player.position]
        if cell["type"] != "region" or cell.get("region_id") != region_id:
            raise GameRuleError("nominal owner must be exactly on the building region")

    def _require_chain_member_on_region(self, player, building):
        if player.id not in building.get("ownership_chain", []):
            raise GameRuleError("player is not in operating right chain")
        cell = self.data["board"][player.position]
        if cell["type"] != "region" or cell.get("region_id") != building["region_id"]:
            raise GameRuleError("rights holder must be exactly on the building region")

    def _building_count_excluding(self, region_id, building_type, excluded_building_id):
        return sum(
            1
            for building in self.state.buildings
            if building["id"] != excluded_building_id
            and building["region_id"] == region_id
            and building["building_type"] == building_type
        )

    def _building_operator_id(self, building):
        chain = building.get("ownership_chain") or [building["nominal_owner_id"]]
        return chain[-1]

    def _require_no_active_request(self):
        if self.state.land_trade_offer or self.state.operating_right_offer or self.state.usage_change_request:
            raise GameRuleError("another trade or approval request is already active")

    def expire_operating_right_offer(self):
        if self.state.operating_right_offer and monotonic() - self.state.operating_right_offer["created_at"] >= 10:
            self.state.operating_right_offer = None
            self.state.turn_started_at = monotonic()
        return self.public_state()

    def _execute_usage_change(self):
        request = self.state.usage_change_request
        if not request:
            return
        requester = self._find_player(request["requester_id"])
        building = self._find_building(request["building_id"])
        if not requester or not building:
            self.state.usage_change_request = None
            raise GameRuleError("usage change participant not found")
        if requester.cash_won < request["cost_won"]:
            self.state.usage_change_request = None
            raise GameRuleError("not enough cash for usage change")
        requester.cash_won -= request["cost_won"]
        self._add_expense(requester, request["cost_won"], "usage_change", building["region_id"], building["id"])
        building["building_type"] = request["new_type"]
        building["construction_cost_won"] = request["cost_won"]
        building["market_value_won"] = max(0, int(building["market_value_won"]))
        chain = building["ownership_chain"]
        nominal = chain[0]
        rest = [member for member in chain[1:] if member != requester.id]
        building["ownership_chain"] = [nominal, requester.id] + rest if requester.id != nominal else [nominal] + rest
        building["operator_id"] = building["ownership_chain"][-1]
        self.state.successful_build_edit_this_visit = True
        self.state.usage_change_request = None

    def _validate_land_trade(self, requester, buyer, region_id):
        self.region_by_id(region_id)
        cell = self.data["board"][requester.position]
        if cell["type"] != "region" or cell.get("region_id") != region_id:
            raise GameRuleError("land owner must be exactly on the region")
        if self.state.land_ownership.get(region_id) != requester.id:
            raise GameRuleError("requester does not own land")
        rights_holders = set()
        for building in self.state.buildings:
            if building["region_id"] != region_id:
                continue
            rights_holders.update(building.get("ownership_chain", []))
            rights_holders.add(building.get("operator_id") or building["owner_id"])
        if len(rights_holders) > 1:
            raise GameRuleError("land with split building rights cannot be traded")
        if rights_holders and buyer.id not in rights_holders:
            raise GameRuleError("land with buildings can transfer only to the sole rights holder")

    def _execute_land_trade(self, requester, buyer, region_id, price):
        if buyer.cash_won < 0 or buyer.cash_won < price:
            raise GameRuleError("buyer cannot afford land trade")
        buyer.cash_won -= price
        requester.cash_won += price
        self._add_expense(buyer, price, "land_trade_purchase", region_id)
        self._add_income(requester, price, "land_trade_sale", region_id, True, "land")
        self.state.land_ownership[region_id] = buyer.id
        if region_id in requester.lands:
            requester.lands.remove(region_id)
        if region_id not in buyer.lands:
            buyer.lands.append(region_id)

    def commercial_visit_fee_rate(self, region_id):
        grade = self.region_by_id(region_id)["commercial_grade"]
        return self.COMMERCIAL_VISIT_FEE_RATES[grade]

    def commercial_visit_fee_rate_bps(self, region_id):
        numerator, denominator = self.commercial_visit_fee_rate(region_id)
        return int(numerator * 10_000 / denominator)

    def _building_visit_fee_rate_bps(self, region_id, building_type):
        commercial_bps = self.commercial_visit_fee_rate_bps(region_id)
        if building_type == "mixed_use":
            commercial_bps = max(0, commercial_bps - 500)
        commercial_bps = apply_rate(commercial_bps, self.state.commercial_rate_multiplier_bps, 10_000)
        event_multiplier = self._event_multiplier_bps("commercial_visit_rate", None, region_id)
        event_add = self._event_add_bps("commercial_visit_rate", None, region_id)
        return max(0, apply_rate(commercial_bps, event_multiplier, 10_000) + event_add)

    def _settle_start(self, player):
        self.state.lap_numbers[player.id] = self.state.lap_numbers.get(player.id, 0) + 1
        ledger = self._open_ledger(player)
        ledger["lap_number"] = self.state.lap_numbers.get(player.id, 0)
        self._pay_due_commercial_sale_refunds(player)
        settlement = {
            "player_id": player.id,
            "lap_number": ledger["lap_number"],
            "steps": [],
            "status_before": player.status,
        }
        settlement["steps"].append("1. industrial_and_mixed_income_loss")
        self._settle_lap_building_returns(player, ledger)
        settlement["steps"].append("2. taxable_income_fixed")
        ledger["taxable_income"] = max(0, ledger["gross_income"] - ledger["losses"])
        settlement["steps"].append("3. tax_notice_and_payment")
        ledger["tax_rate"] = self._calculate_tax_rate_bps(player)
        ledger["tax_due"] = round_to_50k(apply_rate(ledger["taxable_income"], ledger["tax_rate"], 10_000))
        player.cash_won -= ledger["tax_due"]
        if ledger["tax_due"]:
            self._add_expense(player, ledger["tax_due"], "tax", None)
        settlement["steps"].append("4. non_taxable_start_bonus")
        ledger["start_bonus"] = START_BONUS_WON
        player.cash_won += START_BONUS_WON
        ledger["income_entries"].append(
            {"source": "start_bonus", "amount_won": START_BONUS_WON, "taxable": False}
        )
        settlement["steps"].append("5. existing_loan_auto_payment")
        ledger["loan_payment"] += self._auto_repay_loan(player, player.cash_won)
        settlement["steps"].append("6. new_loan_decision")
        if player.cash_won < 0 and player.status != "bankrupt":
            if player.id in self.state.loans and self.state.loans[player.id]["remaining_due_won"] > 0:
                self._bankrupt_player(player, "duplicate_loan")
            else:
                needed = -player.cash_won
                self._create_emergency_loan(player, needed, "start_settlement")
        settlement["steps"].append("7. limit_maturity_bankruptcy")
        self._check_loan_maturity(player)
        settlement["steps"].append("8. settlement_created")
        settlement["ledger"] = deepcopy(self._ledger(player))
        settlement["cash_after"] = player.cash_won
        settlement["status_after"] = player.status
        self.state.last_settlement = settlement
        settlement["steps"].append("9. ready_for_turn_end")
        self._ledger(player)["closed"] = True
        return settlement

    def _pay_due_commercial_sale_refunds(self, player):
        remaining = []
        for refund in self.state.pending_commercial_sale_refunds:
            if refund["player_id"] != player.id:
                remaining.append(refund)
                continue
            if player.status in {"bankrupt", "exited"} or self.state.ended:
                continue
            player.cash_won += refund["refund_won"]
            self._add_income(player, refund["refund_won"], "commercial_sale_refund", refund["region_id"], True, "commercial")
        self.state.pending_commercial_sale_refunds = remaining

    def _settle_lap_building_returns(self, player, ledger):
        for building in self.state.buildings:
            if self._building_operator_id(building) != player.id:
                continue
            if building["building_type"] == "industrial":
                rate_bps = self._adjusted_industrial_rate_bps(player, building["region_id"])
            elif building["building_type"] == "mixed_use":
                raw_rate = self._adjusted_industrial_rate_bps(player, building["region_id"]) - 200
                rate_bps = raw_rate if self.state.industrial_return_explicit_override else self._clamp(raw_rate, 0, 2200)
            else:
                continue
            amount = round_to_50k(apply_rate(self.adjusted_building_value(building), rate_bps, 10_000))
            if amount >= 0:
                player.cash_won += amount
                self._add_income(
                    player,
                    amount,
                    "lap_building_return",
                    building["region_id"],
                    True,
                    building["building_type"],
                    building["id"],
                )
            else:
                player.cash_won += amount
                ledger["losses"] += abs(amount)
                self._add_expense(player, abs(amount), "lap_building_loss", building["region_id"], building["id"])

    def _new_lap_ledger(self, player):
        ledger = {
            "gross_income": 0,
            "taxable_income": 0,
            "losses": 0,
            "income_entries": [],
            "expense_entries": [],
            "tax_rate": 0,
            "tax_due": 0,
            "start_bonus": 0,
            "loan_payment": 0,
            "lap_number": self.state.lap_numbers.get(player.id, 0),
            "closed": False,
        }
        self.state.ledgers[player.id] = ledger
        return ledger

    def _ledger(self, player):
        if player.id not in self.state.ledgers:
            self.state.ledgers[player.id] = {
                "gross_income": 0,
                "taxable_income": 0,
                "losses": 0,
                "income_entries": [],
                "expense_entries": [],
                "tax_rate": 0,
                "tax_due": 0,
                "start_bonus": 0,
                "loan_payment": 0,
                "lap_number": self.state.lap_numbers.get(player.id, 0),
                "closed": False,
            }
        return self.state.ledgers[player.id]

    def _open_ledger(self, player):
        ledger = self._ledger(player)
        if ledger.get("closed"):
            return self._new_lap_ledger(player)
        return ledger

    def _add_income(self, player, amount, source, region_id=None, taxable=True, building_type=None, building_id=None):
        ledger = self._open_ledger(player)
        entry = {
            "source": source,
            "amount_won": int(amount),
            "taxable": bool(taxable),
            "region_id": region_id,
            "building_type": building_type,
            "building_id": building_id,
        }
        ledger["income_entries"].append(entry)
        ledger["gross_income"] += int(amount)
        if taxable:
            ledger["taxable_income"] += int(amount)
        self._log("money", "income_recorded", {"player_id": player.id, "source": source, "amount_won": int(amount), "taxable": bool(taxable)})

    def _add_expense(self, player, amount, source, region_id=None, building_id=None):
        ledger = self._open_ledger(player)
        ledger["expense_entries"].append(
            {
                "source": source,
                "amount_won": int(amount),
                "region_id": region_id,
                "building_id": building_id,
            }
        )
        self._log("money", "expense_recorded", {"player_id": player.id, "source": source, "amount_won": int(amount)})

    def _calculate_tax_rate_bps(self, player):
        if player.id in self.state.tax_rate_overrides:
            return self.state.tax_rate_overrides[player.id]
        rate = 0
        owned_land_ids = {region_id for region_id, owner_id in self.state.land_ownership.items() if owner_id == player.id}
        developed_land_ids = {
            building["region_id"]
            for building in self.state.buildings
            if building["owner_id"] == player.id
        }
        bought_this_lap = {
            region_id
            for region_id, lap_number in self.state.land_purchase_laps.get(player.id, {}).items()
            if lap_number == self.state.lap_numbers.get(player.id, 0)
        }
        for region_id in owned_land_ids:
            if region_id not in developed_land_ids and region_id not in bought_this_lap:
                rate += 50
        direct_counts = {}
        for building in self.state.buildings:
            if len(building.get("ownership_chain", [])) > 1:
                if self._building_operator_id(building) == player.id:
                    rate += 100 + self._event_add_bps("cumulative_tax_rate", player, None)
                continue
            if building["owner_id"] != player.id or self._building_operator_id(building) != player.id:
                continue
            building_type = building["building_type"]
            if building_type == "commercial":
                rate += 100
            elif building_type == "industrial":
                rate += 300
            elif building_type == "mixed_use":
                rate += 500
            rate += self._event_add_bps("building_tax_rate", player, building["region_id"])
            direct_counts[building["region_id"]] = direct_counts.get(building["region_id"], 0) + 1
        for count in direct_counts.values():
            rate += max(0, count - 1) * 100
        return rate

    def _create_emergency_loan(self, player, principal_won, reason):
        principal_won = int(principal_won)
        if principal_won <= 0:
            return self.state.loans.get(player.id)
        if player.id in self.state.loans and self.state.loans[player.id]["remaining_due_won"] > 0:
            self._bankrupt_player(player, "duplicate_loan")
            raise GameRuleError("duplicate emergency loan is not allowed")
        if principal_won > MAX_EMERGENCY_LOAN_PRINCIPAL_WON:
            self._bankrupt_player(player, "loan_limit_exceeded")
            return {"bankrupt": True, "reason": "loan limit exceeded"}
        total_due = apply_rate(principal_won, 110, 100)
        loan = {
            "principal_won": principal_won,
            "interest_rate_bps": 1000,
            "total_due_won": total_due,
            "remaining_due_won": total_due,
            "created_lap": self.state.lap_numbers.get(player.id, 0),
            "due_lap": self.state.lap_numbers.get(player.id, 0) + 3,
            "reason": reason,
        }
        self.state.loans[player.id] = loan
        player.loans = [loan]
        player.cash_won += principal_won
        self._ledger(player)["income_entries"].append(
            {"source": "emergency_loan", "amount_won": principal_won, "taxable": False}
        )
        self._log("loan", "emergency_loan_created", {"player_id": player.id, "principal_won": principal_won, "remaining_due_won": total_due})
        return loan

    def _auto_repay_loan(self, player, available_won):
        loan = self.state.loans.get(player.id)
        if not loan or loan["remaining_due_won"] <= 0 or available_won <= 0:
            return 0
        payment = min(player.cash_won, loan["remaining_due_won"], available_won)
        player.cash_won -= payment
        loan["remaining_due_won"] -= payment
        if loan["remaining_due_won"] <= 0:
            player.loans = []
            self.state.loans.pop(player.id, None)
        else:
            player.loans = [loan]
        self._log("loan", "loan_repaid", {"player_id": player.id, "amount_won": payment})
        return payment

    def _check_loan_maturity(self, player):
        loan = self.state.loans.get(player.id)
        if not loan:
            return
        if self.state.lap_numbers.get(player.id, 0) > loan["due_lap"] and loan["remaining_due_won"] > 0:
            self._bankrupt_player(player, "loan_maturity")

    def _clamp(self, value, low, high):
        return max(low, min(high, int(value)))

    def _bankrupt_player(self, player, reason, allow_finalize=True):
        if player.status == "bankrupt":
            return self.public_state()
        was_current = self.current_player() and player.id == self.current_player().id
        remaining_rounds = self.state.config.total_rounds - self.state.global_round
        debt = 0
        if player.id in self.state.loans:
            debt = self.state.loans[player.id]["remaining_due_won"]
        self.state.debt_writeoffs[player.id] = self.state.debt_writeoffs.get(player.id, 0) + debt
        self.state.bankruptcy_records[player.id] = {
            "reason": reason,
            "bankruptcy_round": self.state.global_round,
            "remaining_rounds": remaining_rounds,
            "status": "bankrupt",
        }
        self.state.bankruptcy_order.append(player.id)
        player.status = "bankrupt"
        player.cash_won = 0
        player.loans = []
        self.state.loans.pop(player.id, None)
        self.state.special_ownership = {k: v for k, v in self.state.special_ownership.items() if v != player.id}
        self.state.pending_commercial_sale_refunds = [item for item in self.state.pending_commercial_sale_refunds if item["player_id"] != player.id]
        for region_id, owner_id in list(self.state.land_ownership.items()):
            if owner_id == player.id:
                self._handle_bankrupt_land_owner(player, region_id)
        for building in list(self.state.buildings):
            if player.id in building.get("ownership_chain", []):
                self._handle_bankrupt_chain_member(player, building)
        player.lands = []
        player.buildings = []
        player.operating_rights = []
        if was_current:
            self._advance_event_steps()
            active = self._turn_players()
            if not active:
                self.finalize_game("no_active_players")
            else:
                self.state.global_round += 1
                self.state.current_turn_index = 0
                if self.state.global_round > self.state.config.total_rounds:
                    self.finalize_game("final_round")
                elif allow_finalize and self._should_end_for_single_solvent_player():
                    self.finalize_game("single_solvent_player")
                else:
                    self._start_turn()
        elif allow_finalize and self._should_end_for_single_solvent_player():
            self.finalize_game("single_solvent_player")
        self._log("bankruptcy", "player_bankrupt", {"player_id": player.id, "reason": reason})
        return self.public_state()

    def _exit_player(self, player, reason):
        previous_status = player.status
        player.status = previous_status if previous_status != "exited" else "active"
        self._bankrupt_player(player, reason, allow_finalize=False)
        self.state.bankruptcy_records.pop(player.id, None)
        if player.id in self.state.bankruptcy_order:
            self.state.bankruptcy_order.remove(player.id)
        self.state.rankings[player.id] = None
        player.status = "exited"
        self._log("exit", "player_exited", {"player_id": player.id, "reason": reason})
        if self._should_end_for_single_solvent_player():
            self.finalize_game("single_solvent_player")

    def _handle_bankrupt_land_owner(self, player, region_id):
        region_buildings = [building for building in self.state.buildings if building["region_id"] == region_id]
        if not region_buildings:
            self.state.land_ownership.pop(region_id, None)
            return
        candidate_id = region_buildings[0]["ownership_chain"][-1]
        candidate = self._find_player(candidate_id)
        land_price = self.region_by_id(region_id)["land_price"]
        refund = sum(max(0, int(building["market_value_won"])) for building in region_buildings if building["ownership_chain"][-1] == candidate_id)
        self.state.pending_land_takeover = {
            "bankrupt_owner_id": player.id,
            "candidate_id": candidate_id,
            "region_id": region_id,
            "land_price_won": land_price,
            "refund_won": refund,
        }
        decision = self.state.forced_takeover_decisions.get(candidate_id)
        if decision is not None:
            self.respond_land_takeover(candidate_id, decision)
        elif not candidate or candidate.is_bot:
            accept = bool(candidate and candidate.cash_won >= land_price and candidate.bot_strategy in {"balanced", "conservative", "aggressive"})
            if candidate:
                self._log_bot_decision(candidate, f"{'accept' if accept else 'decline'} bankrupt land takeover {region_id}")
            self.respond_land_takeover(candidate_id, accept)

    def _handle_bankrupt_chain_member(self, player, building):
        chain = building.get("ownership_chain", [])
        if player.id not in chain:
            return
        index = chain.index(player.id)
        if len(chain) == 1:
            self.state.buildings = [item for item in self.state.buildings if item["id"] != building["id"]]
            return
        if index == len(chain) - 1:
            building["ownership_chain"] = chain[:-1]
        elif index == 0:
            return
        else:
            building["ownership_chain"] = [member for member in chain if member != player.id]
        building["operator_id"] = building["ownership_chain"][-1]

    def _can_revive(self, player):
        if player.status != "bankrupt" or player.status == "exited":
            return False
        record = self.state.bankruptcy_records.get(player.id)
        if not record:
            return False
        if self.state.global_round - record["bankruptcy_round"] < 20:
            return False
        if record["remaining_rounds"] <= 40:
            return False
        bankrupt_players = [self._find_player(pid) for pid in self.state.bankruptcy_order if self._find_player(pid) and self._find_player(pid).status == "bankrupt"]
        if bankrupt_players:
            assets = {item.id: self._player_total_asset(item) for item in bankrupt_players}
            if player.id != min(assets, key=assets.get):
                return False
        order = self.state.bankruptcy_order
        if len(order) >= 2 and player.id == order[-1]:
            previous = self.state.bankruptcy_records.get(order[-2])
            if previous and abs(record["bankruptcy_round"] - previous["bankruptcy_round"]) < 15:
                return False
        max_revives = 1 if self.state.config.total_rounds <= 100 else 2
        return self.state.revival_counts.get(player.id, 0) < max_revives

    def _choose_event(self, event_id=None):
        events = [item for item in self.data["events"] if item["enabled"]]
        if event_id:
            for event in events:
                if event["id"] == event_id:
                    return event
            raise GameRuleError("event not found")
        return events[0]

    def _event_intensity_bps(self, active_event):
        age = int(active_event["age_rounds"])
        duration = max(1, int(active_event["duration_rounds"]))
        recovery = max(1, int(active_event["recovery_rounds"]))
        if age <= 0:
            return 0
        if age <= duration:
            return int(10_000 * age / duration)
        if age <= duration + recovery:
            return max(0, int(10_000 * (duration + recovery - age) / recovery))
        return 0

    def _event_applies(self, active_event, target, player, region_id):
        if target not in [effect["target"] for effect in active_event["effects"]]:
            return False
        if active_event["scope"] == "personal" and player and active_event.get("player_id") != player.id:
            return False
        if active_event["scope"] == "regional" and region_id and active_event.get("region_id") != region_id:
            return False
        return True

    def _event_multiplier_bps(self, target, player=None, region_id=None):
        multiplier = 10_000
        for active in self.state.active_events:
            if not self._event_applies(active, target, player, region_id):
                continue
            intensity = self._event_intensity_bps(active)
            for effect in active["effects"]:
                if effect["target"] == target and effect["operation"] == "multiply":
                    effective = 10_000 + apply_rate(effect["value_bps"] - 10_000, intensity, 10_000)
                    multiplier = apply_rate(multiplier, effective, 10_000)
        return multiplier

    def _event_add_bps(self, target, player=None, region_id=None):
        total = 0
        for active in self.state.active_events:
            if not self._event_applies(active, target, player, region_id):
                continue
            intensity = self._event_intensity_bps(active)
            for effect in active["effects"]:
                if effect["target"] == target and effect["operation"] == "add_bps":
                    total += apply_rate(effect["value_bps"], intensity, 10_000)
                if effect["target"] == target and effect["operation"] == "set_bps":
                    total += apply_rate(effect["value_bps"] - self.state.industrial_return_rate_bps, intensity, 10_000)
                    if effect.get("explicit_override"):
                        self.state.industrial_return_explicit_override = True
        return total

    def _adjusted_industrial_rate_bps(self, player, region_id):
        rate = self.state.industrial_return_rate_bps + self._event_add_bps("industrial_return_rate", player, region_id)
        rate += self._industry_mix_impact_bps(region_id)
        if self.state.industrial_return_explicit_override:
            return rate
        return self._clamp(rate, self.state.industrial_return_min_bps, self.state.industrial_return_max_bps)

    def _industry_mix_impact_bps(self, region_id):
        self.region_by_id(region_id)
        primary = self._event_add_bps("industry_cycle", None, region_id)
        secondary = self._event_add_bps("industry_cycle", None, region_id)
        return apply_rate(primary, 70, 100) + apply_rate(secondary, 30, 100)

    def _advance_event_steps(self):
        remaining = []
        for active in self.state.active_events:
            active["age_rounds"] += 1
            if active["age_rounds"] <= active["duration_rounds"] + active["recovery_rounds"]:
                remaining.append(active)
        self.state.active_events = remaining

    def _first_region_id(self):
        for cell in self.data["board"]:
            if cell["type"] == "region":
                return cell["region_id"]
        raise GameRuleError("region not found")

    def _build_personal_report(self, player):
        report = {
            "player_id": player.id,
            "building_value_changes": [],
            "return_rate_changes": self._event_add_bps("industrial_return_rate", player, None),
            "tax_rate_changes": self._event_add_bps("building_tax_rate", player, None) + self._event_add_bps("cumulative_tax_rate", player, None),
            "major_events": [event["id"] for event in self.state.active_events if event.get("player_id") in {None, player.id}],
            "industry_impact": self._event_add_bps("industry_cycle", player, None),
            "risk_factors": [],
            "outlook": "neutral",
        }
        for building in self.state.buildings:
            if self._building_operator_id(building) == player.id:
                report["building_value_changes"].append(
                    {
                        "building_id": building["id"],
                        "base_value_won": building["market_value_won"],
                        "adjusted_value_won": self.adjusted_building_value(building),
                    }
                )
        if report["tax_rate_changes"] > 0:
            report["risk_factors"].append("tax pressure")
        if report["return_rate_changes"] > 0:
            report["outlook"] = "positive"
        elif report["return_rate_changes"] < 0:
            report["outlook"] = "negative"
        self.state.personal_reports[player.id] = report
        return report

    def _player_total_asset(self, player):
        return self._final_asset_totals().get(player.id, 0)

    def _final_asset_totals(self):
        totals = {player.id: int(player.cash_won) for player in self.state.players}
        unpaid = {}
        for player in self.state.players:
            ledger = self.state.ledgers.get(player.id, {})
            unpaid[player.id] = int(ledger.get("tax_due", 0)) if not ledger.get("closed", False) else 0
        for region_id, owner_id in self.state.land_ownership.items():
            if owner_id in totals:
                totals[owner_id] += self.region_by_id(region_id)["land_price"]
        for building in self.state.buildings:
            value = self.adjusted_building_value(building)
            building_type = building["building_type"]
            nominal_id = building.get("nominal_owner_id")
            operator_id = self._building_operator_id(building)
            if building_type == "residential":
                if nominal_id in totals:
                    totals[nominal_id] += value
            elif building_type == "commercial":
                if nominal_id == operator_id:
                    if nominal_id in totals:
                        totals[nominal_id] += value
                else:
                    half = apply_rate_rounded_50k(value, 50, 100)
                    if nominal_id in totals:
                        totals[nominal_id] += half
                    if operator_id in totals:
                        totals[operator_id] += value - half
        for special_id, owner_id in self.state.special_ownership.items():
            if owner_id in totals:
                totals[owner_id] += apply_rate_rounded_50k(self.state.special_values[special_id], 120, 100)
        for player in self.state.players:
            loan = self.state.loans.get(player.id)
            if loan:
                totals[player.id] -= int(loan.get("remaining_due_won", 0))
            totals[player.id] -= unpaid.get(player.id, 0)
            totals[player.id] -= self.state.debt_writeoffs.get(player.id, 0)
            if player.status == "exited":
                totals[player.id] = 0
        return totals

    def _rank_players(self, totals):
        rankings = {}
        exited_ids = {player.id for player in self.state.players if player.status == "exited"}
        survivors = [player for player in self.state.players if player.status not in {"bankrupt", "exited"}]
        bankruptcy_index = {player_id: index for index, player_id in enumerate(self.state.bankruptcy_order)}
        bankrupts = [player for player in self.state.players if player.status == "bankrupt"]

        def land_value(player):
            return sum(self.region_by_id(region_id)["land_price"] for region_id, owner_id in self.state.land_ownership.items() if owner_id == player.id)

        def tie_dice(player):
            seed = sum(ord(ch) for ch in player.id)
            return Random(seed).randint(1, 6)

        ordered = sorted(
            survivors,
            key=lambda player: (totals.get(player.id, 0), land_value(player), len(player.lands), tie_dice(player)),
            reverse=True,
        )
        rank = 1
        for player in ordered:
            rankings[player.id] = rank
            rank += 1
        bankrupt_ordered = sorted(bankrupts, key=lambda player: bankruptcy_index.get(player.id, -1), reverse=True)
        for player in bankrupt_ordered:
            rankings[player.id] = rank
            rank += 1
        for player_id in exited_ids:
            rankings[player_id] = None
        return rankings

    def _should_end_for_single_solvent_player(self):
        if self.state.phase != "active" or self.state.ended:
            return False
        active = [player for player in self.state.players if player.status == "active"]
        if len(active) <= 1:
            return bool(active)
        return len(active) == 1

    def _record_asset_snapshot(self):
        totals = self._final_asset_totals()
        for player_id, total in totals.items():
            self.state.asset_history.setdefault(player_id, []).append({"global_round": self.state.global_round, "total_asset_won": total})

    def _log(self, category, message, details=None):
        self.state.game_log.append(
            {
                "round": self.state.global_round,
                "category": category,
                "message": message,
                "details": deepcopy(details or {}),
            }
        )
        self.state.game_log = self.state.game_log[-1000:]

    def _log_bot_decision(self, player, message):
        self.state.bot_debug_log.append(
            {
                "player_id": player.id,
                "nickname": player.nickname,
                "message": message,
            }
        )
        self.state.bot_debug_log = self.state.bot_debug_log[-100:]
        self._log("bot", "bot_decision", {"player_id": player.id, "message": message})
