import hashlib
import hmac
import json

import pytest

import fomapay

SECRET = "whsec_unit"
NOW = 1_800_000_000
BODY = json.dumps({"id": "evt_1", "type": "payment.succeeded", "created": "2026-10-10T10:00:00Z", "livemode": False, "data": {"id": "pay_1", "status": "success", "orderId": "CMD-1"}})


def sign(body=BODY, secret=SECRET, timestamp=NOW):
    digest = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_valid_signature_returns_the_event():
    event = fomapay.Webhook.construct_event(BODY.encode(), sign(), SECRET, now=NOW)
    assert event.type == "payment.succeeded" and event.data.succeeded and event.data.order_id == "CMD-1"
    assert fomapay.Webhook.verify(BODY, sign(), SECRET, now=NOW + 299)


def test_known_vector():
    # Vecteur commun à tous les SDKs FomaPay.
    header = "t=1700000000,v1=" + hmac.new(b"whsec_test", b'1700000000.{"id":"evt_1"}', hashlib.sha256).hexdigest()
    assert fomapay.webhook.verify('{"id":"evt_1"}', header, "whsec_test", now=1700000000)


@pytest.mark.parametrize(
    "body, header, now",
    [
        (BODY + " ", sign(), NOW),  # corps modifié
        (BODY, sign(secret="whsec_autre"), NOW),  # mauvais secret
        (BODY, sign(), NOW + 301),  # trop ancien
        (BODY, sign(), NOW - 301),  # horodatage dans le futur
        (BODY, "", NOW),
        (BODY, None, NOW),
        (BODY, "t=abc,v1=00", NOW),
        (BODY, f"t={NOW}", NOW),
    ],
)
def test_invalid_signatures_are_rejected(body, header, now):
    assert not fomapay.Webhook.verify(body, header, SECRET, now=now)
    with pytest.raises(fomapay.SignatureError):
        fomapay.Webhook.construct_event(body, header, SECRET, now=now)


def test_misuse_is_reported_as_configuration_error():
    with pytest.raises(fomapay.ConfigurationError):
        fomapay.Webhook.verify(BODY, sign(), "", now=NOW)
    with pytest.raises(fomapay.ConfigurationError):
        fomapay.Webhook.verify(json.loads(BODY), sign(), SECRET, now=NOW)
