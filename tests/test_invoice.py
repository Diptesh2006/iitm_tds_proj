import random

from fastapi.testclient import TestClient

from api.index import app


client = TestClient(app)


def test_randomized_invoices():
    rng = random.Random(42)
    templates = [
        "Vendor: {vendor}\nInvoice Date: 2026-01-01\nDue Date: {date}\n"
        "Subtotal: USD 12.00\nAmount Due: {currency} {amount}",
        "Supplier: {vendor}\nPay by {date}\nGrand Total: {currency} {amount}",
        "Invoice from {vendor}\nPayment due {date}\nInvoice total = {currency} {amount}",
    ]
    for index in range(30):
        vendor = f"Acme-{rng.randrange(0x1000000):06x} Industries Ltd."
        date = f"2026-{rng.randrange(1, 13):02d}-{rng.randrange(1, 29):02d}"
        amount = round(rng.uniform(50, 9050), 2)
        currency = rng.choice(("USD", "EUR", "GBP"))
        text = templates[index % len(templates)].format(
            vendor=vendor, date=date, amount=f"{amount:,.2f}", currency=currency
        )
        response = client.post("/extract", json={"text": text})
        assert response.status_code == 200, response.text
        data = response.json()
        assert set(data) == {"vendor", "amount", "currency", "date"}
        assert vendor.lower() in data["vendor"].lower()
        assert abs(data["amount"] - amount) <= 0.01, (text, data)
        assert data["currency"] == currency
        assert data["date"] == date


def test_empty_and_garbage_are_validation_errors():
    for text in ("", "not an invoice"):
        response = client.post("/extract", json={"text": text})
        assert response.status_code == 422


def test_cors_preflight():
    response = client.options(
        "/extract",
        headers={
            "Origin": "https://exam.sanand.workers.dev",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
