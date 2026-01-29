from __future__ import annotations

from typing import Callable, cast

from django.http import HttpRequest, HttpResponse

from .models import TenantApiKey
from .tenant_context import set_current_tenant


class TenantContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        meta = cast(dict[str, str], request.META)
        raw_key = meta.get("HTTP_X_TENANT_API_KEY")
        tenant_api_key = None
        tenant = None

        if raw_key:
            tenant_api_key = TenantApiKey.authenticate(raw_key)
            if tenant_api_key is not None:
                tenant = tenant_api_key.tenant

        setattr(request, "tenant_api_key_provided", raw_key is not None)
        setattr(request, "tenant_api_key", tenant_api_key)
        setattr(request, "tenant", tenant)
        set_current_tenant(tenant)

        try:
            return self.get_response(request)
        finally:
            set_current_tenant(None)
