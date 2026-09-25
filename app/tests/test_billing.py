"""Paid plans through Stripe and Razorpay: checkout, signed webhooks, the workspace plan, invoices and cancelling.
The app's code runs for real against in-memory fakes of both providers."""
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.billing import BillingSubscription
from app.services import billing
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member

PLANS = {"plans": [
    {"id": "growth", "name": "Growth", "minutes_included": 2500, "features": ["5 agents"],
     "prices": {"razorpay": {"plan_id": "plan_G", "amount": 4999, "currency": "INR"},
                "stripe": {"price_id": "price_G", "amount": 59, "currency": "USD"}}},
    {"id": "starter", "name": "Starter", "minutes_included": 500, "features": [],
     "prices": {"stripe": {"price_id": "price_S", "amount": 19, "currency": "USD"}}},
]}
KEYS = {"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x",
        "RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "rzp_secret", "RAZORPAY_WEBHOOK_SECRET": "rzp_hook"}


class FakeProviders:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.url.host == "api.stripe.com":
            assert request.headers["authorization"] == "Bearer sk_test_x"
            if path == "/v1/customers":
                return httpx.Response(200, json={"id": "cus_1"})
            if path == "/v1/checkout/sessions":
                return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"})
            if path == "/v1/billing_portal/sessions":
                return httpx.Response(200, json={"url": "https://billing.stripe.com/p/session/1"})
            if path.startswith("/v1/subscriptions/"):
                return httpx.Response(200, json={"id": path.rsplit("/", 1)[1], "cancel_at_period_end": True})
        if request.url.host == "api.razorpay.com":
            if path == "/v1/subscriptions":
                return httpx.Response(200, json={"id": f"sub_{uuid.uuid4().hex[:8]}", "short_url": "https://rzp.io/i/abc", "status": "created"})
            if path.endswith("/cancel"):
                return httpx.Response(200, json={"status": "active"})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    def last(self, path_end: str) -> httpx.Request:
        return next(r for r in reversed(self.requests) if r.url.path.endswith(path_end))


def stripe_event(event_type: str, obj: dict, secret: str = "whsec_x", stamp: int | None = None) -> tuple[bytes, dict]:
    raw = json.dumps({"id": f"evt_{uuid.uuid4().hex}", "type": event_type, "data": {"object": obj}}).encode()
    stamp = stamp or int(time.time())
    sig = hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {"Stripe-Signature": f"t={stamp},v1={sig}", "Content-Type": "application/json"}


def razorpay_event(event: str, payload: dict, secret: str = "rzp_hook") -> tuple[bytes, dict]:
    raw = json.dumps({"event": event, "payload": payload, "created_at": int(time.time())}).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}", "Content-Type": "application/json"}


class BillingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.fake = FakeProviders()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plans = Path(tmp.name, "plans.json")
        plans.write_text(json.dumps(PLANS), encoding="utf-8")
        for p in (patch.dict(os.environ, {**KEYS, "BILLING_PLANS_FILE": str(plans)}),
                  patch.object(billing, "http", lambda: httpx.Client(transport=httpx.MockTransport(self.fake)))):
            p.start()
            self.addCleanup(p.stop)
        self.owner = _TenantClient(self.client)

    def stripe_hook(self, event_type, obj, **kw):
        raw, headers = stripe_event(event_type, obj, **kw)
        return self.client.post("/api/billing/webhook/stripe", content=raw, headers=headers)

    def razorpay_hook(self, event, payload, **kw):
        raw, headers = razorpay_event(event, payload, **kw)
        return self.client.post("/api/billing/webhook/razorpay", content=raw, headers=headers)


class TestPlansAndCheckout(BillingTestCase):
    def test_overview_lists_plans_and_who_can_pay(self):
        body = self.owner.get("/api/billing").json()
        self.assertEqual((body["plan"], body["subscription"], body["can_manage"]), ("Free", None, True))
        growth = next(p for p in body["plans"] if p["id"] == "growth")
        self.assertEqual({(pr["provider"], pr["currency"], pr["available"]) for pr in growth["prices"]},
                         {("razorpay", "INR", True), ("stripe", "USD", True)})
        admin = _Member(self.client, self.owner, "Admin")
        self.assertFalse(admin.get("/api/billing").json()["can_manage"])
        self.assertEqual(admin.post("/api/billing/checkout", json={"plan_id": "growth", "provider": "stripe"}).status_code, 403)
        with patch.dict(os.environ, {"RAZORPAY_WEBHOOK_SECRET": ""}):
            growth = next(p for p in self.owner.get("/api/billing").json()["plans"] if p["id"] == "growth")
            self.assertFalse(next(pr for pr in growth["prices"] if pr["provider"] == "razorpay")["available"])
            self.assertEqual(self.owner.post("/api/billing/checkout", json={"plan_id": "growth", "provider": "razorpay"}).status_code, 400)

    def test_stripe_checkout(self):
        res = self.owner.post("/api/billing/checkout", json={"plan_id": "growth", "provider": "stripe"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["url"], "https://checkout.stripe.com/c/pay/cs_1")
        form = {k: v[0] for k, v in parse_qs(self.fake.last("/checkout/sessions").content.decode()).items()}
        self.assertEqual((form["mode"], form["customer"], form["line_items[0][price]"]), ("subscription", "cus_1", "price_G"))
        self.assertEqual((form["client_reference_id"], form["subscription_data[metadata][tenant_id]"]), (self.owner.tenant_id,) * 2)
        self.assertTrue(form["success_url"].endswith("/billing?checkout=success"))
        # Nothing changes until Stripe confirms.
        self.assertEqual(self.owner.get("/api/billing").json()["plan"], "Free")
        self.assertEqual(self.owner.post("/api/billing/checkout", json={"plan_id": "nope", "provider": "stripe"}).status_code, 404)
        self.assertEqual(self.owner.post("/api/billing/checkout", json={"plan_id": "starter", "provider": "razorpay"}).status_code, 400)

    def test_razorpay_checkout(self):
        res = self.owner.post("/api/billing/checkout", json={"plan_id": "growth", "provider": "razorpay"})
        self.assertEqual(res.json()["url"], "https://rzp.io/i/abc")
        sent = self.fake.last("/v1/subscriptions")
        body = json.loads(sent.content)
        self.assertEqual((body["plan_id"], body["notes"]["tenant_id"]), ("plan_G", self.owner.tenant_id))
        self.assertTrue(sent.headers["authorization"].startswith("Basic "))


class TestStripeWebhooks(BillingTestCase):
    def subscribe(self):
        self.owner.post("/api/billing/checkout", json={"plan_id": "growth", "provider": "stripe"})
        self.assertEqual(self.stripe_hook("checkout.session.completed", {"mode": "subscription", "client_reference_id": self.owner.tenant_id,
                                                                         "subscription": "sub_1" + self.owner.tenant_id[:8], "customer": "cus_1"}).status_code, 200)
        self.sub_id = "sub_1" + self.owner.tenant_id[:8]
        period_end = int(time.time()) + 30 * 86400
        self.assertEqual(self.stripe_hook("customer.subscription.created", {
            "id": self.sub_id, "status": "active", "current_period_end": period_end, "cancel_at_period_end": False,
            "metadata": {"tenant_id": self.owner.tenant_id}, "items": {"data": [{"price": {"id": "price_G"}}]}}).status_code, 200)

    def test_signatures_are_required(self):
        self.assertEqual(self.stripe_hook("customer.subscription.created", {}, secret="forged").status_code, 401)
        self.assertEqual(self.stripe_hook("customer.subscription.created", {}, stamp=int(time.time()) - 3600).status_code, 401)
        self.assertEqual(self.client.post("/api/billing/webhook/stripe", content=b"{}").status_code, 401)

    def test_subscription_lifecycle(self):
        self.subscribe()
        body = self.owner.get("/api/billing").json()
        self.assertEqual((body["plan"], body["subscription"]["status"], body["subscription"]["plan_name"]), ("Growth", "active", "Growth"))
        self.assertEqual(self.owner.post("/api/billing/checkout", json={"plan_id": "starter", "provider": "stripe"}).status_code, 409)

        invoice = {"id": "in_1" + self.owner.tenant_id[:6], "number": "AVN-0001", "amount_paid": 5900, "currency": "usd",
                   "subscription": self.sub_id, "hosted_invoice_url": "https://invoice.stripe.com/i/1"}
        raw, headers = stripe_event("invoice.paid", invoice)
        self.assertEqual(self.client.post("/api/billing/webhook/stripe", content=raw, headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/billing/webhook/stripe", content=raw, headers=headers).json()["status"], "duplicate")
        [row] = self.owner.get("/api/billing").json()["invoices"]
        self.assertEqual((row["number"], row["amount"], row["currency"], row["status"]), ("AVN-0001", 59.0, "USD", "paid"))

        self.assertEqual(self.owner.post("/api/billing/portal").json()["url"], "https://billing.stripe.com/p/session/1")
        cancelled = self.owner.post("/api/billing/cancel").json()
        self.assertEqual((cancelled["plan"], cancelled["subscription"]["cancel_at_period_end"]), ("Growth", True))
        self.assertIn(b"cancel_at_period_end=true", self.fake.last(f"/v1/subscriptions/{self.sub_id}").content)

        self.stripe_hook("customer.subscription.deleted", {"id": self.sub_id, "status": "canceled", "metadata": {"tenant_id": self.owner.tenant_id},
                                                           "items": {"data": [{"price": {"id": "price_G"}}]}})
        body = self.owner.get("/api/billing").json()
        self.assertEqual((body["plan"], body["subscription"]["status"]), ("Free", "ended"))

    def test_failed_payment_keeps_the_plan_while_stripe_retries(self):
        self.subscribe()
        self.stripe_hook("customer.subscription.updated", {"id": self.sub_id, "status": "past_due", "metadata": {"tenant_id": self.owner.tenant_id},
                                                           "items": {"data": [{"price": {"id": "price_G"}}]}})
        body = self.owner.get("/api/billing").json()
        self.assertEqual((body["plan"], body["subscription"]["status"]), ("Growth", "past_due"))

    def test_other_workspaces_see_nothing(self):
        self.subscribe()
        other = _TenantClient(self.client)
        body = other.get("/api/billing").json()
        self.assertEqual((body["plan"], body["subscription"], body["invoices"]), ("Free", None, []))
        self.assertEqual(other.post("/api/billing/cancel").status_code, 404)


class TestRazorpayWebhooks(BillingTestCase):
    def test_subscription_lifecycle(self):
        self.owner.post("/api/billing/checkout", json={"plan_id": "growth", "provider": "razorpay"})
        db = SessionLocal()
        try:
            sub_id = db.query(BillingSubscription).filter(BillingSubscription.tenant_id == self.owner.tenant_id).one().provider_subscription_id
        finally:
            db.close()
        entity = {"id": sub_id, "plan_id": "plan_G", "status": "active", "notes": {"tenant_id": self.owner.tenant_id},
                  "current_start": int(time.time()), "current_end": int(time.time()) + 30 * 86400}
        self.assertEqual(self.razorpay_hook("subscription.activated", {"subscription": {"entity": entity}}, secret="forged").status_code, 401)
        self.assertEqual(self.razorpay_hook("subscription.activated", {"subscription": {"entity": entity}}).status_code, 200)
        self.assertEqual(self.owner.get("/api/billing").json()["plan"], "Growth")

        payment = {"id": "pay_1", "amount": 499900, "currency": "INR", "invoice_id": "inv_" + sub_id[-6:]}
        self.razorpay_hook("subscription.charged", {"subscription": {"entity": entity}, "payment": {"entity": payment}})
        [row] = self.owner.get("/api/billing").json()["invoices"]
        self.assertEqual((row["amount"], row["currency"], row["status"], row["provider"]), (4999.0, "INR", "paid", "razorpay"))

        self.assertTrue(self.owner.post("/api/billing/cancel").json()["subscription"]["cancel_at_period_end"])
        self.assertEqual(json.loads(self.fake.last("/cancel").content), {"cancel_at_cycle_end": 1})
        self.assertEqual(self.owner.post("/api/billing/portal").status_code, 400)  # Stripe only

        self.razorpay_hook("subscription.cancelled", {"subscription": {"entity": dict(entity, status="cancelled")}})
        self.assertEqual(self.owner.get("/api/billing").json()["plan"], "Free")


if __name__ == "__main__":
    unittest.main()
