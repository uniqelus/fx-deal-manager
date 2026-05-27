from dataclasses import dataclass

from fx_deal_manager.domain.models import NostroAccount
from fx_deal_manager.services.payment_calculator import CalculatedPayment


@dataclass(frozen=True)
class NostroAssignmentError:
    field: str
    message: str


class NostroAssignmentService:
    @staticmethod
    def assign(
        payments: list[CalculatedPayment],
        nostro_by_currency: dict[str, NostroAccount],
    ) -> tuple[list[tuple[CalculatedPayment, str]], list[NostroAssignmentError]]:
        assigned: list[tuple[CalculatedPayment, str]] = []
        errors: list[NostroAssignmentError] = []

        for payment in payments:
            nostro = nostro_by_currency.get(payment.currency_code)
            if nostro is None:
                errors.append(
                    NostroAssignmentError(
                        field="payments",
                        message=f"No active nostro account for currency {payment.currency_code}",
                    )
                )
            else:
                # account_code в FX сохраняем как account_number из NSI —
                # это же поле используется в качестве идентификатора счёта
                # при отправке платежа в ПОЗИЦИИ-АСУБАНК.
                assigned.append((payment, nostro.account_number))

        return assigned, errors
