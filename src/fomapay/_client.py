"""Clients FomaPay : ``Client`` (synchrone) et ``AsyncClient`` (asyncio)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from . import _core
from ._core import Request, clean, path
from .models import Balance, Payment, Store


def _payment_request(params: dict[str, Any]) -> Request:
    idempotency_key = params.pop("idempotency_key", None) or _core.new_idempotency_key()
    body = clean(
        {
            "amount": params["amount"],
            "currency": params["currency"],
            "orderId": params.get("order_id"),
            "description": params.get("description"),
            "customer": params.get("customer"),
            "paymentModes": params.get("payment_modes"),
            "callbackUrl": params.get("callback_url"),
            "metadata": params.get("metadata"),
        }
    )
    return Request("POST", "/v1/payments", body=body, idempotency_key=idempotency_key)


def _payout_request(amount: float, currency: str, operator: str, phone: str, description: str | None) -> Request:
    # Pas de clé d'idempotence : un retrait n'est jamais rejoué automatiquement.
    body = clean({"amount": amount, "currency": currency, "operator": operator, "phone": phone, "description": description})
    return Request("POST", "/v1/payouts", body=body)


# ───────────────────────────── Client synchrone ─────────────────────────────


class Client:
    """Client serveur FomaPay.

    >>> client = Client("sk_test_…")
    >>> payment = client.payments.create(amount=25, currency="USD", order_id="CMD-8921")
    """

    def __init__(
        self,
        secret_key: str,
        *,
        base_url: str = _core.DEFAULT_BASE_URL,
        timeout: float = _core.DEFAULT_TIMEOUT,
        max_retries: int = _core.DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
    ) -> None:
        _core.check_secret_key(secret_key)
        self._secret_key = secret_key
        self._max_retries = max(0, max_retries)
        self._http = http_client or httpx.Client(timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._sleep = time.sleep

        self.payments = Payments(self)
        #: Alias de ``payments``.
        self.transactions = self.payments
        self.payouts = Payouts(self)
        self.balance = BalanceResource(self)
        self.store = StoreResource(self)

    @property
    def livemode(self) -> bool:
        return self._secret_key.startswith("sk_live_")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, request: Request) -> Any:
        attempt = 0
        while True:
            try:
                response = self._http.request(
                    request.method,
                    self._base_url + request.path,
                    params=request.params,
                    json=request.body,
                    headers=request.headers(self._secret_key),
                )
                outcome = _core.from_response(request, response)
            except httpx.HTTPError as exc:
                outcome = _core.from_exception(request, exc)

            if outcome.error is None:
                return outcome.data
            if not outcome.retry or attempt >= self._max_retries:
                raise outcome.error
            self._sleep(outcome.wait if outcome.wait is not None else _core.backoff(attempt))
            attempt += 1


class Payments:
    def __init__(self, client: Client) -> None:
        self._client = client

    def create(
        self,
        *,
        amount: float,
        currency: str,
        order_id: str | None = None,
        description: str | None = None,
        customer: dict[str, Any] | None = None,
        payment_modes: list[str] | None = None,
        callback_url: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Payment:
        """Crée une demande de paiement. ``idempotency_key`` (ex. l'identifiant de commande)
        garantit qu'un appel répété renvoie le même paiement."""
        return Payment.from_dict(self._client._request(_payment_request(locals())))

    def retrieve(self, payment_id: str) -> Payment:
        """Relit un paiement par son identifiant ou sa référence (FP-…)."""
        return Payment.from_dict(self._client._request(Request("GET", path("v1", "payments", payment_id))))

    def list(self, *, limit: int | None = None, status: str | None = None) -> list[Payment]:
        data = self._client._request(Request("GET", "/v1/payments", params=clean({"limit": limit, "status": status})))
        return [Payment.from_dict(item) for item in data["data"]]

    def pay_with_mobile_money(self, payment_id: str, *, operator: str, phone: str) -> Payment:
        """Envoie la demande de débit (push USSD) sur le téléphone du client."""
        request = Request("POST", path("v1", "payments", payment_id, "mobile-money"), body={"operator": operator, "phone": phone})
        return Payment.from_dict(self._client._request(request))

    def simulate(self, payment_id: str, outcome: str = "success") -> Payment:
        """Force l'issue d'un paiement (``success`` ou ``failed``). Sandbox uniquement."""
        request = Request("POST", path("v1", "payments", payment_id, "simulate"), body={"outcome": outcome})
        return Payment.from_dict(self._client._request(request))


class Payouts:
    def __init__(self, client: Client) -> None:
        self._client = client

    def create(self, *, amount: float, currency: str, operator: str, phone: str, description: str | None = None) -> Payment:
        """Retrait du solde de la boutique vers un compte Mobile Money.
        Jamais rejoué automatiquement après une erreur réseau : un retrait ne doit pas partir deux fois."""
        return Payment.from_dict(self._client._request(_payout_request(amount, currency, operator, phone, description)))


class BalanceResource:
    def __init__(self, client: Client) -> None:
        self._client = client

    def retrieve(self) -> list[Balance]:
        return [Balance.from_dict(item) for item in self._client._request(Request("GET", "/v1/balance"))["data"]]


class StoreResource:
    def __init__(self, client: Client) -> None:
        self._client = client

    def retrieve(self) -> Store:
        return Store.from_dict(self._client._request(Request("GET", "/v1/store")))


# ───────────────────────────── Client asynchrone ─────────────────────────────


class AsyncClient:
    """Client serveur FomaPay pour asyncio (FastAPI, Django async…).

    >>> async with AsyncClient("sk_test_…") as client:
    ...     payment = await client.payments.create(amount=25, currency="USD")
    """

    def __init__(
        self,
        secret_key: str,
        *,
        base_url: str = _core.DEFAULT_BASE_URL,
        timeout: float = _core.DEFAULT_TIMEOUT,
        max_retries: int = _core.DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        _core.check_secret_key(secret_key)
        self._secret_key = secret_key
        self._max_retries = max(0, max_retries)
        self._http = http_client or httpx.AsyncClient(timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._sleep = asyncio.sleep

        self.payments = AsyncPayments(self)
        #: Alias de ``payments``.
        self.transactions = self.payments
        self.payouts = AsyncPayouts(self)
        self.balance = AsyncBalanceResource(self)
        self.store = AsyncStoreResource(self)

    @property
    def livemode(self) -> bool:
        return self._secret_key.startswith("sk_live_")

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _request(self, request: Request) -> Any:
        attempt = 0
        while True:
            try:
                response = await self._http.request(
                    request.method,
                    self._base_url + request.path,
                    params=request.params,
                    json=request.body,
                    headers=request.headers(self._secret_key),
                )
                outcome = _core.from_response(request, response)
            except httpx.HTTPError as exc:
                outcome = _core.from_exception(request, exc)

            if outcome.error is None:
                return outcome.data
            if not outcome.retry or attempt >= self._max_retries:
                raise outcome.error
            await self._sleep(outcome.wait if outcome.wait is not None else _core.backoff(attempt))
            attempt += 1


class AsyncPayments:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(
        self,
        *,
        amount: float,
        currency: str,
        order_id: str | None = None,
        description: str | None = None,
        customer: dict[str, Any] | None = None,
        payment_modes: list[str] | None = None,
        callback_url: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Payment:
        return Payment.from_dict(await self._client._request(_payment_request(locals())))

    async def retrieve(self, payment_id: str) -> Payment:
        return Payment.from_dict(await self._client._request(Request("GET", path("v1", "payments", payment_id))))

    async def list(self, *, limit: int | None = None, status: str | None = None) -> list[Payment]:
        data = await self._client._request(Request("GET", "/v1/payments", params=clean({"limit": limit, "status": status})))
        return [Payment.from_dict(item) for item in data["data"]]

    async def pay_with_mobile_money(self, payment_id: str, *, operator: str, phone: str) -> Payment:
        request = Request("POST", path("v1", "payments", payment_id, "mobile-money"), body={"operator": operator, "phone": phone})
        return Payment.from_dict(await self._client._request(request))

    async def simulate(self, payment_id: str, outcome: str = "success") -> Payment:
        request = Request("POST", path("v1", "payments", payment_id, "simulate"), body={"outcome": outcome})
        return Payment.from_dict(await self._client._request(request))


class AsyncPayouts:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(self, *, amount: float, currency: str, operator: str, phone: str, description: str | None = None) -> Payment:
        return Payment.from_dict(await self._client._request(_payout_request(amount, currency, operator, phone, description)))


class AsyncBalanceResource:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def retrieve(self) -> list[Balance]:
        return [Balance.from_dict(item) for item in (await self._client._request(Request("GET", "/v1/balance")))["data"]]


class AsyncStoreResource:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def retrieve(self) -> Store:
        return Store.from_dict(await self._client._request(Request("GET", "/v1/store")))
