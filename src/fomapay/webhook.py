"""Vérification des webhooks FomaPay (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from .errors import ConfigurationError, SignatureError
from .models import Event

#: En-tête HTTP qui porte la signature.
SIGNATURE_HEADER = "X-FomaPay-Signature"
#: Âge maximal accepté pour un événement, en secondes (anti-rejeu).
DEFAULT_TOLERANCE = 300


def _check(payload: str | bytes, header: str | None, secret: str, tolerance: int, now: float | None) -> None:
    if not secret:
        raise ConfigurationError("ERROR_WEBHOOK_SECRET_MISSING", "Le secret de signature du webhook (whsec_…) est requis.")
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if not isinstance(payload, (bytes, bytearray)):
        raise ConfigurationError("ERROR_RAW_BODY_REQUIRED", "Passez le corps BRUT de la requête (bytes ou str), pas un objet déjà décodé.")

    parts = dict(part.strip().split("=", 1) for part in (header or "").split(",") if "=" in part)
    timestamp, signature = parts.get("t", ""), parts.get("v1", "")
    if not timestamp.isdigit() or not signature:
        raise SignatureError("ERROR_INVALID_SIGNATURE", "En-tête de signature absent ou mal formé.")

    expected = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + bytes(payload), hashlib.sha256).hexdigest()
    # Comparaison en temps constant.
    if not hmac.compare_digest(expected, signature.lower()):
        raise SignatureError("ERROR_INVALID_SIGNATURE", "La signature ne correspond pas au contenu reçu.")

    # L'horodatage n'est contrôlé qu'après la signature : il est alors authentique.
    if abs((time.time() if now is None else now) - int(timestamp)) > tolerance:
        raise SignatureError("ERROR_INVALID_SIGNATURE", "Événement trop ancien : rejeu refusé.")


def verify(payload: str | bytes, header: str | None, secret: str, tolerance: int = DEFAULT_TOLERANCE, *, now: float | None = None) -> bool:
    """Indique si la signature ``X-FomaPay-Signature`` est valide pour ce corps brut."""
    try:
        _check(payload, header, secret, tolerance, now)
    except SignatureError:
        return False
    return True


def construct_event(payload: str | bytes, header: str | None, secret: str, tolerance: int = DEFAULT_TOLERANCE, *, now: float | None = None) -> Event:
    """Vérifie la signature puis renvoie l'événement ; lève ``SignatureError`` sinon."""
    _check(payload, header, secret, tolerance, now)
    try:
        return Event.from_dict(json.loads(payload))
    except (ValueError, AttributeError) as exc:
        raise SignatureError("ERROR_INVALID_PAYLOAD", "Le corps du webhook n'est pas un événement FomaPay valide.") from exc
