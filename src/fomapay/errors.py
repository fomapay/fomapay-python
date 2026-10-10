"""Erreurs du SDK FomaPay."""

from __future__ import annotations

from typing import Any


class FomaPayError(Exception):
    """Erreur de base. ``code`` est stable et exploitable par le programme
    (ex. ``ERROR_LEVEL_0_LIMIT_REACHED``) ; ``message`` est lisible par un humain."""

    def __init__(self, code: str, message: str, status: int = 0, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        #: Statut HTTP (0 quand il n'y a pas eu de réponse).
        self.status = status
        self.details = details or {}


class ApiError(FomaPayError):
    """L'API a répondu avec une erreur."""


class NetworkError(FomaPayError):
    """Aucune réponse : connexion impossible (``ERROR_NETWORK``) ou délai dépassé (``ERROR_TIMEOUT``)."""


class SignatureError(FomaPayError):
    """Signature de webhook invalide ou expirée."""


class ConfigurationError(FomaPayError):
    """Mauvaise utilisation du SDK (clé mal formée, secret manquant…)."""
