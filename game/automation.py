"""A single application-owned automation loop.

The loop owns no game rules. It only schedules serialized engine ticks, which
keeps GET handlers read-only and makes the clock manually tickable in tests.
"""

from __future__ import annotations

from threading import Event, Thread


class AutomationWorker:
    def __init__(self, engine, interval_seconds: float = 0.1):
        self.engine = engine
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="game-automation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def tick(self) -> None:
        self.engine.run_serialized(lambda: self.engine.advance_automation(force=True))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.tick()
