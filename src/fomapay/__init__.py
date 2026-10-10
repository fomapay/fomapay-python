"""SDK Python officiel de FomaPay — paiements FomaPay Direct et Mobile Money (RDC).

    import fomapay

    client = fomapay.Client("sk_test_…")
    payment = client.payments.create(amount=25, currency="USD", order_id="CMD-8921")
"""

from . import webhook
from ._client import AsyncClient, Client
from ._core import VERSION as __version__
from .errors import ApiError, ConfigurationError, FomaPayError, NetworkError, SignatureError
from .models import (
    AIRTEL_MONEY,
    CDF,
    FOMAPAY_DIRECT,
    MOBILE_MONEY,
    MPESA,
    ORANGE_MONEY,
    USD,
    Balance,
    Event,
    Payment,
    Store,
)

#: Alias dans le style des autres SDKs : ``fomapay.Webhook.verify(...)``.
Webhook = webhook

__all__ = [
    "AIRTEL_MONEY",
    "CDF",
    "FOMAPAY_DIRECT",
    "MOBILE_MONEY",
    "MPESA",
    "ORANGE_MONEY",
    "USD",
    "ApiError",
    "AsyncClient",
    "Balance",
    "Client",
    "ConfigurationError",
    "Event",
    "FomaPayError",
    "NetworkError",
    "Payment",
    "SignatureError",
    "Store",
    "Webhook",
    "__version__",
    "webhook",
]
