"""Modèles renvoyés par l'API FomaPay."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

#: Devises acceptées.
USD = "USD"
CDF = "CDF"

#: Modes de paiement. ``fomapay_direct`` est disponible dès le Niveau 0 ;
#: ``mobile_money`` est réservé aux boutiques vérifiées (Niveau 1+).
FOMAPAY_DIRECT = "fomapay_direct"
MOBILE_MONEY = "mobile_money"

#: Opérateurs Mobile Money.
MPESA = "mpesa"
ORANGE_MONEY = "orange_money"
AIRTEL_MONEY = "airtel_money"

_CAMEL = {
    "order_id": "orderId",
    "payment_modes": "paymentModes",
    "callback_url": "callbackUrl",
    "payer_phone": "payerPhone",
    "qr_code": "qrCode",
    "store_id": "storeId",
    "failure_code": "failureCode",
    "failure_reason": "failureReason",
    "expires_at": "expiresAt",
    "completed_at": "completedAt",
    "created_at": "createdAt",
    "short_code": "shortCode",
    "logo_url": "logoUrl",
    "kyc_level": "kycLevel",
}


def _build(cls: type, data: dict[str, Any]) -> Any:
    """Construit un modèle à partir du JSON de l'API, en ignorant les champs inconnus
    (l'API peut en ajouter sans casser les intégrations existantes)."""
    values = {}
    for f in fields(cls):
        if f.name == "raw":
            continue
        key = _CAMEL.get(f.name, f.name)
        if key in data and data[key] is not None:
            values[f.name] = data[key]
    return cls(**values, raw=data)


@dataclass(frozen=True)
class Payment:
    """Un paiement, un retrait ou tout autre mouvement."""

    id: str = ""
    object: str = "payment"
    reference: str = ""
    status: str = ""
    amount: float = 0.0
    fee: float = 0.0
    net: float = 0.0
    currency: str = ""
    channel: str | None = None
    order_id: str | None = None
    description: str | None = None
    customer: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    payment_modes: list[str] = field(default_factory=list)
    callback_url: str | None = None
    payer_phone: str | None = None
    qr_code: str | None = None
    livemode: bool = False
    store_id: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    expires_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    #: Réponse JSON complète de l'API.
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    @property
    def pending(self) -> bool:
        """Le paiement attend encore le client ou l'opérateur."""
        return self.status in ("pending", "processing")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Payment":
        return _build(cls, data)


@dataclass(frozen=True)
class Balance:
    """Solde disponible de la boutique dans une devise."""

    currency: str = ""
    available: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Balance":
        return _build(cls, data)


@dataclass(frozen=True)
class Store:
    """Boutique liée à la clé, avec les modes que son niveau KYC autorise."""

    id: str = ""
    name: str = ""
    short_code: str = ""
    logo_url: str | None = None
    livemode: bool = False
    kyc_level: int = 0
    payment_modes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Store":
        return _build(cls, data)


@dataclass(frozen=True)
class Event:
    """Événement de webhook : ``payment.succeeded``, ``payment.failed``, ``payout.succeeded``…"""

    id: str = ""
    type: str = ""
    created: str = ""
    livemode: bool = False
    #: Le paiement (ou retrait) concerné.
    data: Payment = field(default_factory=Payment)
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Event":
        return cls(
            id=payload.get("id", ""),
            type=payload.get("type", ""),
            created=payload.get("created", ""),
            livemode=bool(payload.get("livemode")),
            data=Payment.from_dict(payload.get("data") or {}),
            raw=payload,
        )
