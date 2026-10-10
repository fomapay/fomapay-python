"""Logique partagée par le client synchrone et le client asynchrone :
construction des requêtes, politique de nouvelles tentatives, lecture des réponses."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .errors import ApiError, ConfigurationError, NetworkError

DEFAULT_BASE_URL = "https://api.fomapay.cd"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
MAX_BACKOFF = 8.0
VERSION = "0.1.0"


def check_secret_key(secret_key: str) -> None:
    if not isinstance(secret_key, str) or not secret_key.startswith(("sk_test_", "sk_live_")):
        raise ConfigurationError(
            "ERROR_INVALID_API_KEY",
            "Clé secrète absente ou mal formée : elle commence par sk_test_ ou sk_live_ (FomaPay Business › Développeurs).",
        )


def new_idempotency_key() -> str:
    """Clé unique : rejouer la requête ne crée pas de doublon."""
    return f"py-{uuid.uuid4().hex}"


def backoff(attempt: int) -> float:
    """0,5 s, 1 s, 2 s… plafonné à 8 s, avec un aléa pour désynchroniser les clients."""
    delay = min(0.5 * (2**attempt), MAX_BACKOFF)
    return delay / 2 + random.uniform(0, delay / 2)


def clean(params: dict[str, Any]) -> dict[str, Any]:
    """Retire les paramètres laissés à ``None``."""
    return {key: value for key, value in params.items() if value is not None}


def path(*segments: str) -> str:
    return "/" + "/".join(quote(segment, safe="") for segment in segments)


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    params: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    #: Rend un POST rejouable sans risque.
    idempotency_key: str | None = None

    @property
    def replayable(self) -> bool:
        return self.method == "GET" or self.idempotency_key is not None

    def headers(self, secret_key: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {secret_key}",
            "Accept": "application/json",
            "User-Agent": f"fomapay-python/{VERSION}",
        }
        if self.idempotency_key:
            headers["Idempotency-Key"] = self.idempotency_key
        return headers


@dataclass(frozen=True)
class Outcome:
    """Résultat d'une tentative : une donnée, ou une erreur éventuellement rejouable."""

    data: Any = None
    error: Exception | None = None
    retry: bool = False
    wait: float | None = None


def from_response(request: Request, response: httpx.Response) -> Outcome:
    if response.is_success:
        if not response.content:
            return Outcome()
        try:
            return Outcome(data=response.json())
        except json.JSONDecodeError:
            return Outcome(error=ApiError("ERROR_INVALID_RESPONSE", "Réponse illisible de l'API FomaPay.", response.status_code))

    try:
        envelope = response.json().get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        envelope = {}
    error = ApiError(
        envelope.get("code") or "ERROR_UNKNOWN",
        envelope.get("message") or f"Erreur HTTP {response.status_code}",
        response.status_code,
        envelope.get("details"),
    )
    if response.status_code == 429:
        # La gateway a refusé la requête avant tout traitement : toujours rejouable.
        retry_after = response.headers.get("Retry-After", "")
        wait = min(float(retry_after), MAX_BACKOFF) if retry_after.isdigit() and int(retry_after) > 0 else None
        return Outcome(error=error, retry=True, wait=wait)
    return Outcome(error=error, retry=response.status_code >= 500 and request.replayable)


def from_exception(request: Request, exc: httpx.HTTPError) -> Outcome:
    if isinstance(exc, httpx.TimeoutException):
        error: Exception = NetworkError("ERROR_TIMEOUT", "FomaPay n'a pas répondu dans le délai imparti.")
    else:
        error = NetworkError("ERROR_NETWORK", f"Impossible de joindre FomaPay : {exc}")
    error.__cause__ = exc
    return Outcome(error=error, retry=request.replayable)
