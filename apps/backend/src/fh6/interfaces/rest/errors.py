"""Documented validation-error shape (FR-034a, Q5).

Single canonical body for 400 responses. The `supported` field is set
on what-if-style validation errors so the caller can discover the
closed kind set without consulting the API spec at runtime.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


def validation_error_400(
    message: str,
    *,
    field: str | None = None,
    supported: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> HTTPException:
    body: dict[str, Any] = {"error": "validation_failed", "message": message}
    if field is not None:
        body["field"] = field
    if supported is not None:
        body["supported"] = sorted(supported)
    if extra:
        body.update(extra)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=body)


def not_found(message: str, *, resource: str | None = None) -> HTTPException:
    body: dict[str, Any] = {"error": "not_found", "message": message}
    if resource is not None:
        body["resource"] = resource
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=body)


def confirm_required(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": "confirmation_required",
            "message": message,
            "header": "X-Confirm: true",
        },
    )
