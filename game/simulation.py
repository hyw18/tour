"""Isolated, cancellable bot simulation jobs."""

from __future__ import annotations

import csv
import io
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from time import time
from uuid import uuid4

from .engine import GameEngine, GameRuleError


@dataclass
class SimulationJob:
    id: str
    config: dict
    status: str = "queued"
    completed_runs: int = 0
    total_runs: int = 0
    results: list[dict] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time)
    cancel_event: Event = field(default_factory=Event, repr=False)

    def view(self, include_results=False):
        data = {
            "id": self.id,
            "status": self.status,
            "completed_runs": self.completed_runs,
            "total_runs": self.total_runs,
            "progress": self.completed_runs / self.total_runs if self.total_runs else 0,
            "error": self.error,
        }
        if include_results:
            data["results"] = deepcopy(self.results)
        return data


class SimulationJobManager:
    def __init__(self, data_dir, max_jobs=2, max_runs=1_000):
        self.data_dir = data_dir
        self.max_jobs = max_jobs
        self.max_runs = max_runs
        self._jobs: dict[str, SimulationJob] = {}
        self._lock = Lock()

    def create(self, config):
        runs = int(config.get("runs", 1))
        if runs < 1 or runs > self.max_runs:
            raise GameRuleError(f"runs must be 1..{self.max_runs}")
        with self._lock:
            active = sum(job.status in {"queued", "running", "cancelling"} for job in self._jobs.values())
            if active >= self.max_jobs:
                raise GameRuleError("too many simulation jobs")
            job = SimulationJob(uuid4().hex, deepcopy(config), total_runs=runs)
            self._jobs[job.id] = job
            Thread(target=self._run, args=(job,), name=f"simulation-{job.id[:8]}", daemon=True).start()
            return job.view()

    def get(self, job_id, include_results=False):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise GameRuleError("simulation job not found")
            return job.view(include_results)

    def cancel(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise GameRuleError("simulation job not found")
            if job.status in {"queued", "running"}:
                job.status = "cancelling"
                job.cancel_event.set()
            return job.view()

    def export(self, job_id, kind):
        job = self.get(job_id, include_results=True)
        if kind == "json":
            return job
        if kind != "csv":
            raise GameRuleError("unsupported simulation export kind")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["run", "strategy_win_rates", "loan_rate", "average_top_asset_gap"])
        for index, result in enumerate(job["results"], 1):
            writer.writerow([index, result.get("strategy_win_rates"), result.get("loan_rate"), result.get("average_top_asset_gap")])
        return output.getvalue()

    def _run(self, job):
        job.status = "running"
        try:
            base = deepcopy(job.config)
            base["runs"] = 1
            seed = int(base.get("seed", 0))
            for index in range(job.total_runs):
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                    return
                isolated = GameEngine(self.data_dir)
                base["seed"] = seed + index
                result = isolated.run_bot_simulation(base)
                with self._lock:
                    job.results.append(result)
                    job.completed_runs += 1
            job.status = "completed"
        except Exception as exc:  # worker boundary: preserve failures for clients
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = "failed"
