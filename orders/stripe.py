import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_payment_intent(amount, currency=None, metadata=None):
    """
    Create a Stripe PaymentIntent.
    Used by memberships, consultations, and donations.
    Amount is in decimal (e.g. 99.00) — we convert to cents.
    """
    return stripe.PaymentIntent.create(
        amount=int(amount * 100),  # convert to cents
        currency=currency or settings.CURRENCY,
        metadata=metadata or {},
        automatic_payment_methods={
            "enabled": True,
            "allow_redirects": "never",
        },
    )


def create_checkout_session(line_items, success_url, cancel_url, metadata=None):
    """
    Create a Stripe Checkout Session.
    Used for direct purchases and cart checkout.
    Returns a session with a `url` the frontend redirects to.
    line_items: list of dicts with price_data or price + quantity.
    """
    return stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=line_items,
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata or {},
    )


def retrieve_payment_intent(payment_intent_id):
    return stripe.PaymentIntent.retrieve(payment_intent_id)


def construct_webhook_event(payload, sig_header):
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
