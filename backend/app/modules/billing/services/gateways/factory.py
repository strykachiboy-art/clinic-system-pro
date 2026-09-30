from __future__ import annotations

from app.core.enums.billing_enums import PaymentGateway
from app.modules.billing.services.gateways.base_gateway import (
    PaymentGatewayBase,
)
from app.modules.billing.services.gateways.flutterwave_gateway import (
    FlutterwaveGateway,
)
from app.modules.billing.services.gateways.paystack_gateway import (
    PaystackGateway,
)
from app.modules.billing.services.gateways.stripe_gateway import (
    StripeGateway,
)
from app.modules.settings.services.integration_config_service import (
    get_integration_credentials,
)


_GATEWAY_IMPLEMENTATIONS: dict[
    PaymentGateway,
    type[PaymentGatewayBase],
] = {
    PaymentGateway.STRIPE: StripeGateway,
    PaymentGateway.PAYSTACK: PaystackGateway,
    PaymentGateway.FLUTTERWAVE: FlutterwaveGateway,
}


def get_payment_gateway(
    gateway: PaymentGateway | str,
    *,
    clinic_id: int,
) -> PaymentGatewayBase:
    if isinstance(gateway, str):
        gateway_value = gateway.strip().lower()

        try:
            gateway = PaymentGateway(
                gateway_value
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported payment gateway: {gateway}"
            ) from exc

    gateway_class = _GATEWAY_IMPLEMENTATIONS.get(
        gateway
    )

    if gateway_class is None:
        raise ValueError(
            f"Unsupported payment gateway: {gateway}"
        )

    credentials = get_integration_credentials(
        clinic_id,
        gateway.value,
    )

    return gateway_class(
        credentials=credentials,
    )