from app.core.enums.billing_enums import PaymentGateway
from app.modules.billing.services.gateways.base_gateway import PaymentGatewayBase
from app.modules.billing.services.gateways.flutterwave_gateway import (
    FlutterwaveGateway,
)
from app.modules.billing.services.gateways.paystack_gateway import (
    PaystackGateway,
)
from app.modules.billing.services.gateways.stripe_gateway import (
    StripeGateway,
)


def get_payment_gateway(
    gateway: PaymentGateway | str,
) -> PaymentGatewayBase:
    """
    Return the configured payment gateway implementation.
    """

    if isinstance(gateway, str):
        try:
            gateway = PaymentGateway(gateway.lower())
        except ValueError as exc:
            raise ValueError(
                f"Unsupported payment gateway: {gateway}"
            ) from exc

    gateways: dict[PaymentGateway, type[PaymentGatewayBase]] = {
        PaymentGateway.STRIPE: StripeGateway,
        PaymentGateway.PAYSTACK: PaystackGateway,
        PaymentGateway.FLUTTERWAVE: FlutterwaveGateway,
    }

    gateway_class = gateways.get(gateway)

    if gateway_class is None:
        raise ValueError(
            f"Unsupported payment gateway: {gateway}"
        )

    return gateway_class()