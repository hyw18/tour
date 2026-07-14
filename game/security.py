"""Host authentication and same-origin request protection."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from time import monotonic, time

from flask import Request, session


@dataclass
class HostAuthenticator:
    token: str
    session_ttl_seconds: int = 8 * 60 * 60
    max_failures: int = 5
    failure_window_seconds: int = 60

    def __post_init__(self):
        self._failures: dict[str, list[float]] = {}

    @classmethod
    def create(cls, token: str | None = None, session_ttl_seconds: int = 8 * 60 * 60):
        return cls(token=token or secrets.token_urlsafe(24), session_ttl_seconds=session_ttl_seconds)

    def login(self, candidate: str | None, client_key: str = "unknown") -> str:
        now = monotonic()
        failures = [value for value in self._failures.get(client_key, []) if now - value < self.failure_window_seconds]
        self._failures[client_key] = failures
        if len(failures) >= self.max_failures:
            return "rate_limited"
        if not candidate or not secrets.compare_digest(self.token, str(candidate)):
            failures.append(now)
            return "invalid"
        self._failures.pop(client_key, None)
        session.clear()
        session["is_host"] = True
        session["host_authenticated_at"] = time()
        session["csrf_token"] = secrets.token_urlsafe(24)
        return "authenticated"

    def logout(self) -> None:
        session.clear()

    def is_authenticated(self) -> bool:
        if session.get("is_host") is not True:
            return False
        authenticated_at = session.get("host_authenticated_at")
        if not isinstance(authenticated_at, (int, float)):
            return False
        if time() - authenticated_at > self.session_ttl_seconds:
            session.clear()
            return False
        return True

    def csrf_token(self) -> str | None:
        return session.get("csrf_token") if self.is_authenticated() else None

    def valid_csrf(self, request: Request) -> bool:
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = self.csrf_token() or ""
        return bool(supplied and expected and secrets.compare_digest(supplied, expected))
