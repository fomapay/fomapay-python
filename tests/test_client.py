import asyncio
import json

import httpx
import pytest

import fomapay

KEY = "sk_test_unit"
PAYMENT = {"id": "pay_1", "reference": "FP-1", "status": "pending", "amount": 25, "currency": "USD", "orderId": "CMD-1", "champInconnu": 1}


def make_client(handler, **options):
    client = fomapay.Client(KEY, base_url="https://api.test", http_client=httpx.Client(transport=httpx.MockTransport(handler)), **options)
    waits = []
    client._sleep = waits.append
    return client, waits


def error(status, code, headers=None):
    return httpx.Response(status, json={"error": {"code": code, "message": "oups", "details": {"champ": "amount"}}}, headers=headers)


def test_rejects_malformed_secret_key():
    with pytest.raises(fomapay.ConfigurationError):
        fomapay.Client("pk_test_abc")


def test_create_sends_standard_format_and_idempotency_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(201, json=PAYMENT)

    client, _ = make_client(handler)
    payment = client.transactions.create(
        amount=25,
        currency=fomapay.USD,
        order_id="CMD-1",
        customer={"name": "Jean Marc", "phone": "+243810000000"},
        payment_modes=[fomapay.FOMAPAY_DIRECT, fomapay.MOBILE_MONEY],
        callback_url="https://marchand.cd/api/callback",
        metadata={"custom_field": "valeur"},
    )

    request = seen[0]
    assert request.method == "POST" and request.url.path == "/v1/payments"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["Idempotency-Key"].startswith("py-")
    assert json.loads(request.content) == {
        "amount": 25,
        "currency": "USD",
        "orderId": "CMD-1",
        "customer": {"name": "Jean Marc", "phone": "+243810000000"},
        "paymentModes": ["fomapay_direct", "mobile_money"],
        "callbackUrl": "https://marchand.cd/api/callback",
        "metadata": {"custom_field": "valeur"},
    }
    assert payment.order_id == "CMD-1" and payment.pending and not payment.succeeded
    assert payment.raw["champInconnu"] == 1


def test_retries_server_errors_with_the_same_idempotency_key():
    keys = []

    def handler(request):
        keys.append(request.headers["Idempotency-Key"])
        return error(503, "ERROR_UNAVAILABLE") if len(keys) < 3 else httpx.Response(201, json=PAYMENT)

    client, waits = make_client(handler)
    assert client.payments.create(amount=25, currency="USD").id == "pay_1"
    assert len(keys) == 3 and len(set(keys)) == 1
    assert len(waits) == 2 and 0.25 <= waits[0] <= 0.5 and 0.5 <= waits[1] <= 1


def test_gives_up_after_max_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return error(500, "ERROR_INTERNAL")

    client, _ = make_client(handler, max_retries=1)
    with pytest.raises(fomapay.ApiError) as raised:
        client.payments.retrieve("FP-1")
    assert len(calls) == 2 and raised.value.status == 500 and raised.value.code == "ERROR_INTERNAL"


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return error(403, "ERROR_LEVEL_0_LIMIT_REACHED")

    client, _ = make_client(handler)
    with pytest.raises(fomapay.ApiError) as raised:
        client.payments.create(amount=900, currency="USD")
    assert len(calls) == 1
    assert raised.value.code == "ERROR_LEVEL_0_LIMIT_REACHED" and raised.value.details == {"champ": "amount"}


def test_payouts_are_never_replayed():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return error(502, "ERROR_BAD_GATEWAY")
        raise httpx.ConnectError("coupure")

    client, _ = make_client(handler)
    for expected in (fomapay.ApiError, fomapay.NetworkError):
        with pytest.raises(expected):
            client.payouts.create(amount=10, currency="USD", operator=fomapay.MPESA, phone="+243810000000")
    assert len(calls) == 2
    assert "Idempotency-Key" not in calls[0].headers


def test_rate_limit_is_always_retried_and_honours_retry_after():
    calls = []

    def handler(request):
        calls.append(request)
        return error(429, "ERROR_RATE_LIMITED", {"Retry-After": "2"}) if len(calls) == 1 else httpx.Response(201, json=PAYMENT)

    client, waits = make_client(handler)
    client.payouts.create(amount=10, currency="USD", operator=fomapay.MPESA, phone="+243810000000")
    assert len(calls) == 2 and waits == [2.0]


def test_network_errors_and_timeouts():
    def handler(request):
        raise httpx.ReadTimeout("trop long")

    client, waits = make_client(handler)
    with pytest.raises(fomapay.NetworkError) as raised:
        client.balance.retrieve()
    assert raised.value.code == "ERROR_TIMEOUT" and raised.value.status == 0 and len(waits) == 2


def test_other_resources():
    def handler(request):
        path = request.url.path
        if path == "/v1/payments" and request.method == "GET":
            assert dict(request.url.params) == {"limit": "5", "status": "success"}
            return httpx.Response(200, json={"data": [PAYMENT]})
        if path == "/v1/payments/FP%2F1/mobile-money" or request.url.raw_path == b"/v1/payments/FP%2F1/mobile-money":
            assert json.loads(request.content) == {"operator": "airtel_money", "phone": "+243970000000"}
            return httpx.Response(200, json={**PAYMENT, "status": "processing"})
        if path == "/v1/payments/pay_1/simulate":
            return httpx.Response(200, json={**PAYMENT, "status": "success"})
        if path == "/v1/balance":
            return httpx.Response(200, json={"data": [{"currency": "USD", "available": 12.5}]})
        if path == "/v1/store":
            return httpx.Response(200, json={"id": "s1", "name": "Chez Foma", "shortCode": "FOMA", "kycLevel": 2, "paymentModes": ["fomapay_direct"]})
        return httpx.Response(404, json={"error": {"code": "ERROR_NOT_FOUND", "message": path}})

    client, _ = make_client(handler)
    assert [p.id for p in client.payments.list(limit=5, status="success")] == ["pay_1"]
    assert client.payments.pay_with_mobile_money("FP/1", operator=fomapay.AIRTEL_MONEY, phone="+243970000000").status == "processing"
    assert client.payments.simulate("pay_1").succeeded
    assert client.balance.retrieve()[0].available == 12.5
    store = client.store.retrieve()
    assert store.short_code == "FOMA" and store.kyc_level == 2


def test_async_client_mirrors_the_sync_client():
    calls = []

    def handler(request):
        calls.append(request)
        return error(500, "ERROR_INTERNAL") if len(calls) == 1 else httpx.Response(201, json=PAYMENT)

    async def scenario():
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with fomapay.AsyncClient(KEY, base_url="https://api.test", http_client=http) as client:
            waits = []

            async def sleep(seconds):
                waits.append(seconds)

            client._sleep = sleep
            payment = await client.transactions.create(amount=25, currency="USD", idempotency_key="CMD-1")
            return payment, waits

    payment, waits = asyncio.run(scenario())
    assert payment.id == "pay_1" and len(waits) == 1
    assert [call.headers["Idempotency-Key"] for call in calls] == ["CMD-1", "CMD-1"]
