from enum import StrEnum


class DealState(StrEnum):
    DRAFT = "DRAFT"
    WAITING_FOR_POSITIONER = "WAITING_FOR_POSITIONER"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


class DealType(StrEnum):
    TOD = "TOD"
    TOM = "TOM"
    SPOT = "SPOT"
    FORWARD = "FORWARD"


class ValidationStatus(StrEnum):
    NOT_VALIDATED = "NOT_VALIDATED"
    VALID = "VALID"
    INVALID = "INVALID"


class OperationDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PaymentDirection(StrEnum):
    IN = "IN"
    OUT = "OUT"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    RETURN_FOR_EDIT = "RETURN_FOR_EDIT"
    REJECT = "REJECT"


class AccountType(StrEnum):
    NOSTRO = "NOSTRO"
