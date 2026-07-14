from dataclasses import dataclass, field
from time import monotonic
from uuid import uuid4


STARTING_CASH_WON = 10_000_000
START_BONUS_WON = 3_000_000
MAX_EMERGENCY_LOAN_PRINCIPAL_WON = 20_000_000
BOARD_SIZE = 40
ALLOWED_SLOTS = {2, 3, 4}
ALLOWED_ROUNDS = range(10, 301)
ALLOWED_TURN_LIMITS = {15, 30, 45, 60, 75, 90, None}
ALLOWED_BOT_DELAYS = {0, 0.5, 1, 2}
PLAYER_STATUSES = {"lobby", "active", "bankrupt", "spectator", "exited"}
BOT_STRATEGIES = {"balanced", "aggressive", "conservative", "random"}
BUILDING_TYPES = {"residential", "commercial", "industrial", "mixed_use"}


@dataclass
class Player:
    id: str
    nickname: str
    is_bot: bool
    slot_index: int
    join_order: int
    status: str = "lobby"
    cash_won: int = STARTING_CASH_WON
    position: int = 0
    lands: list = field(default_factory=list)
    buildings: list = field(default_factory=list)
    loans: list = field(default_factory=list)
    operating_rights: list = field(default_factory=list)
    bot_strategy: str | None = None
    difficulty: str | None = None
    risk_tolerance: int | None = None
    action_delay: float | None = None

    def public(self):
        data = {
            "id": self.id,
            "nickname": self.nickname,
            "is_bot": self.is_bot,
            "slot_index": self.slot_index,
            "join_order": self.join_order,
            "status": self.status,
            "cash_won": self.cash_won,
            "position": self.position,
            "lands": self.lands,
            "buildings": self.buildings,
            "loans": [] if not self.loans else ["private"],
            "operating_rights": self.operating_rights,
        }
        if self.is_bot:
            data.update(
                {
                    "bot_strategy": self.bot_strategy,
                    "difficulty": self.difficulty,
                    "risk_tolerance": self.risk_tolerance,
                    "action_delay": self.action_delay,
                }
            )
        return data


@dataclass
class HostConfig:
    total_slots: int = 2
    slot_types: list[str] = field(default_factory=lambda: ["human", "bot"])
    bot_strategies: list[str] = field(default_factory=lambda: ["balanced", "balanced"])
    total_rounds: int = 10
    turn_limit_seconds: int | None = 30
    bot_action_delay: float = 1
    fast_simulation: bool = False

    def normalize(self):
        self.slot_types = self.slot_types[: self.total_slots]
        self.bot_strategies = self.bot_strategies[: self.total_slots]
        while len(self.slot_types) < self.total_slots:
            self.slot_types.append("human")
        while len(self.bot_strategies) < self.total_slots:
            self.bot_strategies.append("balanced")


@dataclass
class GameState:
    config: HostConfig = field(default_factory=HostConfig)
    players: list[Player] = field(default_factory=list)
    phase: str = "lobby"
    current_turn_index: int = 0
    global_round: int = 1
    paused: bool = False
    ended: bool = False
    turn_started_at: float | None = None
    turn_elapsed_before_pause: float = 0
    turn_has_rolled: bool = False
    last_dice: int | None = None
    last_activity_player_id: str | None = None
    processed_keys: dict[str, dict] = field(default_factory=dict)
    forced_dice_once: int | None = None
    bot_auto_enabled: bool = False
    land_ownership: dict = field(default_factory=dict)
    buildings: list = field(default_factory=list)
    pending_action: dict | None = None
    successful_build_edit_this_visit: bool = False
    industrial_return_rate_bps: int = 1200
    industrial_return_explicit_override: bool = False
    lap_numbers: dict = field(default_factory=dict)
    land_purchase_laps: dict = field(default_factory=dict)
    ledgers: dict = field(default_factory=dict)
    tax_rate_overrides: dict = field(default_factory=dict)
    loans: dict = field(default_factory=dict)
    last_settlement: dict | None = None
    bot_debug_log: list = field(default_factory=list)
    pending_commercial_sale_refunds: list = field(default_factory=list)
    special_ownership: dict = field(default_factory=dict)
    special_values: dict = field(default_factory=dict)
    forced_special_sale_dice_once: int | None = None
    land_trade_offer: dict | None = None
    operating_right_offer: dict | None = None
    usage_change_request: dict | None = None
    forced_approval_responses: dict = field(default_factory=dict)
    blocked_usage_change_requests: set = field(default_factory=set)
    active_events: list = field(default_factory=list)
    event_history: list = field(default_factory=list)
    personal_reports: dict = field(default_factory=dict)
    commercial_rate_multiplier_bps: int = 10_000
    industrial_return_min_bps: int = 0
    industrial_return_max_bps: int = 2400
    simulation_results: dict | None = None
    bankruptcy_records: dict = field(default_factory=dict)
    bankruptcy_order: list = field(default_factory=list)
    debt_writeoffs: dict = field(default_factory=dict)
    revival_counts: dict = field(default_factory=dict)
    no_action_counts: dict = field(default_factory=dict)
    rankings: dict = field(default_factory=dict)
    pending_land_takeover: dict | None = None
    forced_takeover_decisions: dict = field(default_factory=dict)
    game_log: list = field(default_factory=list)
    asset_history: dict = field(default_factory=dict)
    final_results: dict | None = None
    quick_game_presets: dict = field(default_factory=dict)
    pause_at_round: int | None = None
    created_at: float = field(default_factory=monotonic)

    def reset_runtime(self):
        self.phase = "lobby"
        self.current_turn_index = 0
        self.global_round = 1
        self.paused = False
        self.ended = False
        self.turn_started_at = None
        self.turn_elapsed_before_pause = 0
        self.turn_has_rolled = False
        self.last_dice = None
        self.last_activity_player_id = None
        self.processed_keys.clear()
        self.forced_dice_once = None
        self.bot_auto_enabled = False
        self.land_ownership.clear()
        self.buildings.clear()
        self.pending_action = None
        self.successful_build_edit_this_visit = False
        self.industrial_return_rate_bps = 1200
        self.industrial_return_explicit_override = False
        self.lap_numbers.clear()
        self.land_purchase_laps.clear()
        self.ledgers.clear()
        self.tax_rate_overrides.clear()
        self.loans.clear()
        self.last_settlement = None
        self.bot_debug_log.clear()
        self.pending_commercial_sale_refunds.clear()
        self.special_ownership.clear()
        self.special_values.clear()
        self.forced_special_sale_dice_once = None
        self.land_trade_offer = None
        self.operating_right_offer = None
        self.usage_change_request = None
        self.forced_approval_responses.clear()
        self.blocked_usage_change_requests.clear()
        self.active_events.clear()
        self.event_history.clear()
        self.personal_reports.clear()
        self.commercial_rate_multiplier_bps = 10_000
        self.industrial_return_min_bps = 0
        self.industrial_return_max_bps = 2400
        self.simulation_results = None
        self.bankruptcy_records.clear()
        self.bankruptcy_order.clear()
        self.debt_writeoffs.clear()
        self.revival_counts.clear()
        self.no_action_counts.clear()
        self.rankings.clear()
        self.pending_land_takeover = None
        self.forced_takeover_decisions.clear()
        self.game_log.clear()
        self.asset_history.clear()
        self.final_results = None
        self.quick_game_presets.clear()
        self.pause_at_round = None


def new_id(prefix):
    return f"{prefix}_{uuid4().hex[:10]}"
