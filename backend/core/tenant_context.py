from __future__ import annotations

import contextvars
from typing import Any

_current_tenant: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "current_tenant",
    default=None,
)


def set_current_tenant(tenant: Any) -> None:
    _current_tenant.set(tenant)


def get_current_tenant() -> Any:
    return _current_tenant.get()
