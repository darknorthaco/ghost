"""HTTP client for GHOST workers — optional; explicit TLS; no implicit network downgrade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import httpx


def _verify_for_tls(tls_enabled: bool, tls_controller_cert_path: str | None) -> bool | str:
    """Explicit certificate pin when TLS is enabled; no silent downgrade."""
    if not tls_enabled:
        return True
    if not tls_controller_cert_path:
        raise ValueError("tls_controller_cert_path is required when tls_enabled is true")
    p = Path(tls_controller_cert_path)
    if not p.is_file():
        raise FileNotFoundError(f"tls_controller_cert_path does not exist: {tls_controller_cert_path}")
    return str(p)


@dataclass
class HttpWorkerClient:
    """Minimal task dispatch to a worker base URL; TLS is explicit and opt-in."""

    base_url: str
    timeout_sec: float = 30.0
    tls_enabled: bool = False
    tls_controller_cert_path: str | None = None

    def _client(self) -> httpx.Client:
        verify = _verify_for_tls(self.tls_enabled, self.tls_controller_cert_path)
        return httpx.Client(timeout=self.timeout_sec, verify=verify)

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + path

    def health(self) -> dict[str, Any]:
        with self._client() as c:
            r = c.get(self._url("/health"))
            r.raise_for_status()
            return r.json()

    def execute_task(
        self,
        task_id: str,
        task_type: str,
        parameters: Mapping[str, Any],
        priority: int = 0,
    ) -> dict[str, Any]:
        payload = {
            "task_id": task_id,
            "task_type": task_type,
            "parameters": dict(parameters),
            "priority": priority,
        }
        with self._client() as c:
            r = c.post(self._url("/tasks/execute"), json=payload)
            r.raise_for_status()
            return r.json()
