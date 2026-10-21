"""Payment gateways for KNET and Visa/Mastercard (online renewals). Every gateway does the
same two steps, so switching provider changes only this file:

    start(payment)            -> where to send the family (the provider's payment page)
    verify(payment, outcome, signature) -> (paid, gateway reference)

``TestGateway`` stands in for the provider's page in development and demos: a portal page
with Approve and Decline buttons. Its outcomes are signed so they cannot be forged."""

import hashlib
import hmac

from app.core.config import get_settings
from app.models import RenewalPayment


def _key() -> bytes:
    from app.api.portal import _code_key  # the portal's secret key

    return _code_key()


class TestGateway:
    name = "test"

    @staticmethod
    def signature(reference: str, outcome: str) -> str:
        return hmac.new(_key(), f"{reference}:{outcome}".encode(), hashlib.sha256).hexdigest()[:32]

    def start(self, payment: RenewalPayment) -> str:
        return f"/portal/pay/{payment.reference}"

    def verify(self, payment: RenewalPayment, outcome: str, sig: str) -> tuple[bool, str]:
        if outcome not in ("approve", "decline") or not hmac.compare_digest(
            sig or "", self.signature(payment.reference, outcome)
        ):
            return False, ""
        return outcome == "approve", f"TEST-{payment.reference}"


GATEWAYS = {"test": TestGateway}


def get_gateway() -> TestGateway:
    return GATEWAYS[get_settings().payment_gateway]()


def online_payments_enabled() -> bool:
    s = get_settings()
    return not (s.payment_gateway == "test" and s.environment == "production")
