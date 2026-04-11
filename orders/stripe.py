import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_payment_intent(amount, currency=None, metadata=None):
    """
    Create a Stripe PaymentIntent.
    Amount is in decimal (e.g. 99.00) — we convert to cents.
    Returns the client_secret for the frontend.
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


def retrieve_payment_intent(payment_intent_id):
    return stripe.PaymentIntent.retrieve(payment_intent_id)


def construct_webhook_event(payload, sig_header):
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
