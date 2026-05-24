from fastapi import Request
from fastapi.responses import JSONResponse

from fx_deal_manager.services.validation import ValidationIssue


class ValidationFailedError(Exception):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__("Validation failed")


async def validation_failed_handler(_request: Request, exc: ValidationFailedError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": [{"field": issue.field, "message": issue.message} for issue in exc.issues]
        },
    )
