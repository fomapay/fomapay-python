# fomapay-python

SDK Python officiel de **FomaPay** : encaissez en RDC par **FomaPay Direct** (QR / code marchand, dès le Niveau 0) et par **Mobile Money** (M-Pesa, Orange Money, Airtel Money, dès le Niveau 1).

- Client synchrone `Client` et asynchrone `AsyncClient` (FastAPI, Django async…)
- Nouvelles tentatives automatiques et délai d'attente
- Vérification des webhooks (HMAC-SHA256)
- Python 3.9+, une seule dépendance (`httpx`)

> SDK **serveur** : il utilise votre clé secrète `sk_…`, qui ne doit jamais se retrouver dans une application mobile ou un navigateur.

## Intégration en 3 étapes

### 1. Installer

```bash
pip install fomapay
```

### 2. Créer un paiement

```python
import fomapay

client = fomapay.Client("sk_test_…")  # FomaPay Business › Développeurs

payment = client.payments.create(
    amount=1000,
    currency="CDF",
    order_id="CMD-2026-001",
    customer={"name": "Jean Marc", "phone": "+243810000000", "email": "jean@example.com"},
    payment_modes=["fomapay_direct", "mobile_money"],
    callback_url="https://marchand.cd/api/callback",
    metadata={"custom_field": "valeur"},
)

print(payment.reference, payment.qr_code)  # à afficher au client (FomaPay Direct)

# ou débiter directement son compte Mobile Money (push USSD)
client.payments.pay_with_mobile_money(payment.id, operator="airtel_money", phone="+243970000000")
```

### 3. Recevoir la confirmation (webhook)

```python
from fastapi import FastAPI, Header, HTTPException, Request
import fomapay

app = FastAPI()

@app.post("/webhooks/fomapay")
async def fomapay_webhook(request: Request, x_fomapay_signature: str = Header(None)):
    try:
        event = fomapay.Webhook.construct_event(await request.body(), x_fomapay_signature, "whsec_…")
    except fomapay.SignatureError:
        raise HTTPException(400, "signature invalide")

    if event.type == "payment.succeeded":
        livrer(event.data.order_id)
    return {"received": True}
```

Passez toujours le **corps brut** de la requête : un JSON décodé puis réencodé ne donne plus la même signature. `fomapay.Webhook.verify(payload, header, secret)` renvoie simplement `True` / `False`.

## Asynchrone

```python
async with fomapay.AsyncClient("sk_test_…") as client:
    payment = await client.payments.create(amount=25, currency="USD", order_id="CMD-8921")
```

`AsyncClient` expose exactement les mêmes méthodes que `Client`.

## Référence

| Appel | Rôle |
| --- | --- |
| `client.payments.create(...)` | Crée une demande de paiement |
| `client.payments.retrieve(id_ou_reference)` | Relit un paiement |
| `client.payments.list(limit=, status=)` | Derniers paiements de la boutique |
| `client.payments.pay_with_mobile_money(id, operator=, phone=)` | Push USSD vers le client |
| `client.payments.simulate(id, "success" \| "failed")` | Force l'issue (sandbox uniquement) |
| `client.payouts.create(amount=, currency=, operator=, phone=)` | Retrait vers Mobile Money |
| `client.balance.retrieve()` | Solde par devise |
| `client.store.retrieve()` | Boutique, niveau KYC et modes autorisés |

`client.transactions` est un alias de `client.payments`. Les montants sont en unités de la devise (`12.5` = 12,50 USD). Chaque modèle garde la réponse complète de l'API dans `.raw`.

## Erreurs

```python
try:
    client.payments.create(amount=900, currency="USD")
except fomapay.ApiError as e:       # l'API a répondu avec une erreur
    print(e.code, e.message, e.status, e.details)
except fomapay.NetworkError as e:   # ERROR_NETWORK ou ERROR_TIMEOUT
    ...
```

Toutes héritent de `fomapay.FomaPayError`. Le `code` est stable (`ERROR_VALIDATION`, `ERROR_LEVEL_0_LIMIT_REACHED`, `ERROR_NOT_FOUND`…).

## Fiabilité

- **Délai** : 30 s par défaut — `Client(key, timeout=10)`.
- **Nouvelles tentatives** : 2 par défaut (`max_retries=`), avec attente exponentielle (0,5 s, 1 s… plafonnée à 8 s). Ne sont rejouées que les requêtes sans risque : les lectures, et les créations de paiement, qui portent toujours un en-tête `Idempotency-Key`. Un `429` est toujours rejoué en respectant `Retry-After`.
- **Idempotence** : passez `idempotency_key="CMD-2026-001"` pour qu'un appel répété par votre propre code renvoie le même paiement.
- **Retraits** : jamais rejoués automatiquement. Après une `NetworkError`, vérifiez l'état avant de relancer.

## Sandbox

Avec une clé `sk_test_…`, aucun argent ne circule. Pour un push Mobile Money, le numéro décide de l'issue : terminé par `0001` → refusé, par `0002` → jamais validé, sinon confirmé après ~3 s.

## Tests

```bash
pip install -e ".[dev]"
pytest                       # tests unitaires
FOMAPAY_API_URL=http://localhost:8080 FOMAPAY_TEST_SECRET_KEY=sk_test_… pytest   # + intégration sandbox
```

Licence MIT.
