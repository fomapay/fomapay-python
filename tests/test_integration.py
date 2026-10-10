"""Tests d'intégration contre le sandbox FomaPay.

Ils ne s'exécutent que si FOMAPAY_TEST_SECRET_KEY (sk_test_…) est définie ;
FOMAPAY_API_URL cible un backend local :

    FOMAPAY_API_URL=http://localhost:8080 FOMAPAY_TEST_SECRET_KEY=sk_test_… pytest tests/test_integration.py
"""

import asyncio
import os
import time

import pytest

import fomapay

KEY = os.environ.get("FOMAPAY_TEST_SECRET_KEY", "")
OPTIONS = {"base_url": os.environ["FOMAPAY_API_URL"]} if os.environ.get("FOMAPAY_API_URL") else {}

pytestmark = pytest.mark.skipif(not KEY, reason="FOMAPAY_TEST_SECRET_KEY non définie")


def test_sandbox_sync():
    with fomapay.Client(KEY, **OPTIONS) as client:
        store = client.store.retrieve()
        assert not store.livemode and len(store.payment_modes) == 2

        # Format standard d'une transaction, dans les deux modes.
        payment = client.payments.create(
            amount=1000,
            currency=fomapay.CDF,
            order_id="CMD-2026-001",
            customer={"name": "Jean Marc", "phone": "+243810000000", "email": "jean@example.com"},
            payment_modes=[fomapay.FOMAPAY_DIRECT, fomapay.MOBILE_MONEY],
            callback_url="https://marchand.cd/api/callback",
            metadata={"custom_field": "valeur"},
        )
        assert payment.status == "pending" and payment.callback_url == "https://marchand.cd/api/callback" and payment.qr_code

        # Mode Mobile Money : l'opérateur simulé confirme après ~3 s.
        final = client.payments.pay_with_mobile_money(payment.id, operator=fomapay.AIRTEL_MONEY, phone="+243970000000")
        assert final.status == "processing"
        deadline = time.time() + 10
        while final.pending:
            assert time.time() < deadline, "le paiement Mobile Money n'a pas été confirmé à temps"
            time.sleep(1)
            final = client.payments.retrieve(payment.reference)
        assert final.succeeded and final.channel == "airtel_money"

        # Mode FomaPay Direct : issue forcée en sandbox.
        direct = client.payments.create(amount=12.5, currency=fomapay.USD, payment_modes=[fomapay.FOMAPAY_DIRECT])
        assert client.payments.simulate(direct.id, "success").succeeded

        # Idempotence : la même clé renvoie le même paiement.
        first = client.payments.create(amount=3, currency="USD", idempotency_key=f"py-it-{payment.id}")
        again = client.payments.create(amount=3, currency="USD", idempotency_key=f"py-it-{payment.id}")
        assert first.id == again.id

        assert client.payments.list(limit=5, status="success")
        assert client.balance.retrieve()

        with pytest.raises(fomapay.ApiError) as invalid:
            client.payments.create(amount=-1, currency="USD")
        assert invalid.value.code == "ERROR_VALIDATION"
        with pytest.raises(fomapay.ApiError) as missing:
            client.payments.retrieve("FP-INEXISTANT")
        assert missing.value.code == "ERROR_NOT_FOUND" and missing.value.status == 404


def test_sandbox_async():
    async def scenario():
        async with fomapay.AsyncClient(KEY, **OPTIONS) as client:
            store, payment = await asyncio.gather(
                client.store.retrieve(),
                client.payments.create(amount=7, currency="USD", order_id="CMD-ASYNC"),
            )
            paid = await client.payments.simulate(payment.id, "failed")
            return store, payment, paid

    store, payment, paid = asyncio.run(scenario())
    assert store.id and payment.order_id == "CMD-ASYNC" and paid.status == "failed"
