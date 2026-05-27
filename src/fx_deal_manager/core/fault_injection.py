from fx_deal_manager.core.config import settings


class PaymentSaveFaultError(Exception):
    """Simulated persistence failure for PMI G.6 testing."""

    def __init__(self, payment_index: int) -> None:
        self.payment_index = payment_index
        super().__init__(f"Simulated payment save failure after payment {payment_index}")


def check_payment_save_fault(payment_index: int) -> None:
    fault_after = settings.payment_save_fault_after
    if fault_after is not None and payment_index > fault_after:
        raise PaymentSaveFaultError(fault_after)
