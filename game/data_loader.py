import json
from pathlib import Path

from jsonschema import ValidationError, validate


class DataValidationError(RuntimeError):
    pass


class GameDataLoader:
    REQUIRED_FILES = {
        "regions": "regions.json",
        "board": "board.json",
        "building_prices": "building_prices.json",
        "industries": "industries.json",
        "special_regions": "special_regions.json",
        "events": "events.json",
        "bot_strategies": "bot_strategies.json",
    }

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    def load(self):
        loaded = {}
        for key, filename in self.REQUIRED_FILES.items():
            path = self.data_dir / filename
            if not path.exists():
                raise DataValidationError(f"{filename}: missing required data file")
            try:
                loaded[key] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise DataValidationError(f"{filename}: invalid JSON at line {exc.lineno}") from exc
            self._validate_json_schema(loaded[key], filename)
        self._validate_regions(loaded["regions"], "regions.json")
        self._validate_board(loaded["board"], "board.json")
        self._validate_building_prices(loaded["building_prices"], "building_prices.json")
        self._validate_industries(loaded["industries"], "industries.json")
        self._validate_special_regions(loaded["special_regions"], "special_regions.json")
        self._validate_events(loaded["events"], "events.json")
        self._validate_bot_strategies(loaded["bot_strategies"], "bot_strategies.json")
        self._validate_cross_file_rules(loaded)
        self._validate_schema_files()
        return loaded

    def _require_list(self, value, filename):
        if not isinstance(value, list):
            raise DataValidationError(f"{filename}: root must be a list")

    def _require_dict(self, value, filename):
        if not isinstance(value, dict):
            raise DataValidationError(f"{filename}: root must be an object")

    def _validate_regions(self, data, filename):
        self._require_list(data, filename)
        seen = set()
        for index, item in enumerate(data):
            self._item_object(item, filename, index)
            for field in (
                "id",
                "name",
                "land_price",
                "population_density",
                "commercial_grade",
                "primary_industry",
                "secondary_industries",
            ):
                if not item.get(field):
                    raise DataValidationError(f"{filename}[{index}].{field}: required")
            if not isinstance(item["land_price"], int) or item["land_price"] <= 0:
                raise DataValidationError(f"{filename}[{index}].land_price: positive integer won required")
            if item["commercial_grade"] not in {1, 2, 3, 4, 5}:
                raise DataValidationError(f"{filename}[{index}].commercial_grade: must be 1..5")
            if not isinstance(item["secondary_industries"], list):
                raise DataValidationError(f"{filename}[{index}].secondary_industries: list required")
            if item["id"] in seen:
                raise DataValidationError(f"{filename}[{index}].id: duplicate {item['id']}")
            seen.add(item["id"])

    def _validate_board(self, data, filename):
        self._require_list(data, filename)
        if len(data) != 40:
            raise DataValidationError(f"{filename}: board must contain exactly 40 cells")
        counts = {"start": 0, "region": 0, "special": 0, "event": 0, "transport": 0}
        for index, item in enumerate(data):
            self._item_object(item, filename, index)
            if item.get("index") != index:
                raise DataValidationError(f"{filename}[{index}].index: must equal {index}")
            if not item.get("name") or not item.get("type"):
                raise DataValidationError(f"{filename}[{index}]: name and type are required")
            if item["type"] not in counts:
                raise DataValidationError(f"{filename}[{index}].type: unsupported type {item['type']}")
            counts[item["type"]] += 1
        expected = {"start": 1, "region": 25, "special": 4, "event": 9, "transport": 1}
        if counts != expected:
            raise DataValidationError(f"{filename}: cell type counts must be {expected}, got {counts}")

    def _validate_building_prices(self, data, filename):
        self._require_dict(data, filename)
        required = {"land", "residential", "commercial", "industrial", "mixed_use"}
        for region_id, prices in data.items():
            self._require_dict(prices, f"{filename}.{region_id}")
            missing = required.difference(prices)
            if missing:
                raise DataValidationError(f"{filename}.{region_id}: missing prices {sorted(missing)}")
            for key, value in prices.items():
                if not isinstance(value, int) or value < 0:
                    raise DataValidationError(f"{filename}.{region_id}.{key}: price must be non-negative integer won")

    def _validate_industries(self, data, filename):
        self._require_list(data, filename)
        for index, item in enumerate(data):
            self._item_object(item, filename, index)
            if not item.get("id") or not item.get("name"):
                raise DataValidationError(f"{filename}[{index}]: id and name are required")

    def _validate_special_regions(self, data, filename):
        self._require_list(data, filename)
        for index, item in enumerate(data):
            self._item_object(item, filename, index)
            if not item.get("id") or not item.get("name"):
                raise DataValidationError(f"{filename}[{index}]: id and name are required")
            if not isinstance(item.get("initial_price"), int) or item["initial_price"] <= 0:
                raise DataValidationError(f"{filename}[{index}].initial_price: positive integer won required")

    def _validate_events(self, data, filename):
        self._require_list(data, filename)
        if len(data) < 20:
            raise DataValidationError(f"{filename}: at least 20 events are required")
        scope_counts = {"personal": 0, "regional": 0, "nationwide": 0}
        allowed_targets = {
            "building_market_value",
            "commercial_visit_rate",
            "industrial_return_rate",
            "building_tax_rate",
            "cumulative_tax_rate",
            "economic_growth",
            "trade_balance",
            "industry_cycle",
            "regional_economy",
        }
        protected_targets = {
            "land_price",
            "starting_cash",
            "start_bonus",
            "loan_principal_limit",
            "movement_rule",
            "player_slots",
            "total_rounds",
            "turn_limit_seconds",
        }
        for index, item in enumerate(data):
            self._item_object(item, filename, index)
            for field in (
                "id",
                "title",
                "public_description",
                "private_description",
                "scope",
                "targets",
                "effects",
                "duration_rounds",
                "recovery_rounds",
                "can_chain_event",
                "chained_event_pool",
                "weight",
                "enabled",
            ):
                if field not in item:
                    raise DataValidationError(f"{filename}[{index}].{field}: required")
            if item["scope"] not in scope_counts:
                raise DataValidationError(f"{filename}[{index}].scope: unsupported scope")
            scope_counts[item["scope"]] += 1
            for target in item["targets"]:
                if target in protected_targets:
                    raise DataValidationError(f"{filename}[{index}].targets: protected target {target}")
                if target not in allowed_targets:
                    raise DataValidationError(f"{filename}[{index}].targets: unsupported target {target}")
            for effect_index, effect in enumerate(item["effects"]):
                self._require_dict(effect, f"{filename}[{index}].effects[{effect_index}]")
                target = effect.get("target")
                if target in protected_targets:
                    raise DataValidationError(f"{filename}[{index}].effects[{effect_index}].target: protected target {target}")
                if target not in allowed_targets:
                    raise DataValidationError(f"{filename}[{index}].effects[{effect_index}].target: unsupported target {target}")
                if effect.get("operation") not in {"multiply", "add_bps", "set_bps"}:
                    raise DataValidationError(f"{filename}[{index}].effects[{effect_index}].operation: unsupported")
                if not isinstance(effect.get("value_bps"), int):
                    raise DataValidationError(f"{filename}[{index}].effects[{effect_index}].value_bps: integer required")
        if scope_counts["personal"] < 6 or scope_counts["regional"] < 7 or scope_counts["nationwide"] < 7:
            raise DataValidationError(f"{filename}: requires personal>=6 regional>=7 nationwide>=7")

    def _validate_bot_strategies(self, data, filename):
        self._require_dict(data, filename)
        expected = {"balanced", "aggressive", "conservative", "random"}
        missing = expected.difference(data.keys())
        if missing:
            raise DataValidationError(f"{filename}: missing bot strategies {sorted(missing)}")
        for key, value in data.items():
            self._require_dict(value, f"{filename}.{key}")
            if not isinstance(value.get("risk_tolerance"), int):
                raise DataValidationError(f"{filename}.{key}.risk_tolerance: integer required")
            if not isinstance(value.get("description"), str):
                raise DataValidationError(f"{filename}.{key}.description: string required")

    def _item_object(self, item, filename, index):
        if not isinstance(item, dict):
            raise DataValidationError(f"{filename}[{index}]: item must be an object")

    def _validate_cross_file_rules(self, loaded):
        regions = {region["id"]: region for region in loaded["regions"]}
        prices = loaded["building_prices"]
        if set(regions) != set(prices):
            raise DataValidationError("regions.json/building_prices.json: region ids must match")
        for region_id, region in regions.items():
            if region["land_price"] != prices[region_id]["land"]:
                raise DataValidationError(
                    f"regions.json/building_prices.json:{region_id}: land_price differs"
                )
        board_region_ids = [cell.get("region_id") for cell in loaded["board"] if cell["type"] == "region"]
        if board_region_ids != [region["id"] for region in loaded["regions"]]:
            raise DataValidationError("board.json: region cells must follow regions.json order")
        special_ids = {item["id"] for item in loaded["special_regions"]}
        event_ids = {item["id"] for item in loaded["events"]}
        for index, cell in enumerate(loaded["board"]):
            if cell["type"] == "special" and cell.get("special_region_id") not in special_ids:
                raise DataValidationError(f"board.json[{index}].special_region_id: unknown special region")
            if cell["type"] == "event" and cell.get("event_id") not in event_ids:
                raise DataValidationError(f"board.json[{index}].event_id: unknown event")

    def _validate_schema_files(self):
        schema_dir = self.data_dir / "schemas"
        required = [
            "board.schema.json",
            "regions.schema.json",
            "building_prices.schema.json",
            "industries.schema.json",
            "special_regions.schema.json",
            "events.schema.json",
            "bot_strategies.schema.json",
        ]
        for name in required:
            path = schema_dir / name
            if not path.exists():
                raise DataValidationError(f"schemas/{name}: missing required schema file")
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise DataValidationError(f"schemas/{name}: invalid JSON at line {exc.lineno}") from exc

    def _validate_json_schema(self, data, filename):
        schema_path = self.data_dir / "schemas" / filename.replace(".json", ".schema.json")
        if not schema_path.exists():
            raise DataValidationError(f"schemas/{schema_path.name}: missing required schema file")
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            validate(instance=data, schema=schema)
        except json.JSONDecodeError as exc:
            raise DataValidationError(f"schemas/{schema_path.name}: invalid JSON at line {exc.lineno}") from exc
        except ValidationError as exc:
            path = ".".join(str(part) for part in exc.absolute_path)
            location = f"{filename}.{path}" if path else filename
            raise DataValidationError(f"{location}: schema validation failed: {exc.message}") from exc
