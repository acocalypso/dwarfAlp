from __future__ import annotations

import contextvars
from itertools import count
from threading import Lock
from typing import Any, Callable, TypeVar

from fastapi import HTTPException, Request

T = TypeVar("T")


_current_request: contextvars.ContextVar[Request | None] = contextvars.ContextVar("alpaca_current_request", default=None)
_server_transaction_counter = count(1)
_transaction_lock = Lock()
_UINT32_MAX = 4294967295


async def bind_request_context(request: Request):
    token = _current_request.set(request)
    try:
        yield
    finally:
        _current_request.reset(token)


def alpaca_response(
    value: Any = None,
    *,
    error_number: int = 0,
    error_message: str = "",
    client_transaction_id: int | None = None,
    client_id: int | None = None,
) -> dict[str, Any]:
    """Wrap a value in the standard Alpaca response envelope."""
    request = _current_request.get()
    if client_transaction_id is None:
        client_transaction_id = _extract_uint32_from_request(request, "ClientTransactionID")
    if client_id is None:
        client_id = _extract_uint32_from_request(request, "ClientID")

    payload: dict[str, Any] = {
        "ClientTransactionID": client_transaction_id if client_transaction_id is not None else 0,
        "ServerTransactionID": _next_server_transaction_id(),
        "ErrorNumber": error_number,
        "ErrorMessage": error_message,
    }
    if client_id is not None:
        payload["ClientID"] = client_id
    if value is not None:
        payload["Value"] = value
    return payload


def _next_server_transaction_id() -> int:
    global _server_transaction_counter
    with _transaction_lock:
        current = next(_server_transaction_counter)
        if current > _UINT32_MAX:
            _server_transaction_counter = count(1)
            current = next(_server_transaction_counter)
    return current


def _extract_uint32_from_request(request: Request | None, name: str) -> int | None:
    if request is None:
        return None
    raw_value = request.query_params.get(name)
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value & _UINT32_MAX


def require_parameter(name: str, *values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    raise HTTPException(status_code=400, detail=f"{name} parameter required")


def _convert_value(value: Any, converter: Callable[[Any], T]) -> T:
    try:
        return converter(value)
    except Exception as exc:  # pragma: no cover - conversion error
        raise HTTPException(status_code=400, detail=f"Invalid value for parameter") from exc


def _cast(value: Any, expected_type: type[T]) -> T:
    if isinstance(value, expected_type):
        return value
    if expected_type is bool:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True  # type: ignore[return-value]
            if lowered in {"false", "0", "no", "off"}:
                return False  # type: ignore[return-value]
        return expected_type(value)  # type: ignore[arg-type]
    return expected_type(value)  # type: ignore[arg-type]


async def resolve_parameter(
    request: Request,
    name: str,
    expected_type: type[T],
    *preferred_values: Any,
) -> T:
    for candidate in preferred_values:
        if candidate is not None:
            return candidate

    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        body = await request.json()
        if isinstance(body, dict) and name in body:
            return _cast(body[name], expected_type)

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        if name in form:
            return _cast(form[name], expected_type)

    raise HTTPException(status_code=400, detail=f"{name} parameter required")
