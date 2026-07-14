"""Concurrency boundary for one in-memory game."""

from copy import deepcopy
from threading import RLock


class StateRepository:
    def __init__(self, state, max_processed_keys=1_000):
        self.state = state
        self.max_processed_keys = max_processed_keys
        self.lock = RLock()

    def replace(self, state):
        with self.lock:
            self.state = state

    def serialized(self, operation):
        with self.lock:
            return operation()

    def idempotent(self, key, operation, error_type):
        with self.lock:
            if not key:
                raise error_type("Idempotency-Key header is required")
            if key in self.state.processed_keys:
                return deepcopy(self.state.processed_keys[key])
            result = operation()
            self.state.processed_keys[key] = deepcopy(result)
            while len(self.state.processed_keys) > self.max_processed_keys:
                self.state.processed_keys.pop(next(iter(self.state.processed_keys)))
            return result
