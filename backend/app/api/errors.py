"""Shared API error helpers for the contract-only skeleton."""

from typing import NoReturn

from fastapi import HTTPException, status


def service_not_implemented(feature: str) -> NoReturn:
    """Keep route contracts runnable until their service is implemented."""

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "code": "service_not_implemented",
            "message": f"{feature} has an API contract but no service implementation yet.",
        },
    )
