# pyright: reportMissingImports=false
from __future__ import annotations

from typing import cast

from django.contrib.auth.models import AnonymousUser  # type: ignore[reportMissingImports]
from rest_framework import authentication, exceptions  # type: ignore[reportMissingImports]

from .models import Tenant, TenantApiKey
from .tenant_context import set_current_tenant


class TenantApiKeyAuthentication(authentication.BaseAuthentication):
    header_name = "X-Tenant-Api-Key"

    def authenticate(self, request):
        raw_key = request.headers.get(self.header_name)
        if raw_key is None:
            return None
        if not raw_key.strip():
            raise exceptions.AuthenticationFailed("Invalid tenant API key.")

        if getattr(request, "tenant_api_key_provided", False):
            tenant_api_key = getattr(request, "tenant_api_key", None)
        else:
            tenant_api_key = TenantApiKey.authenticate(raw_key)

        if tenant_api_key is None:
            raise exceptions.AuthenticationFailed("Invalid tenant API key.")

        tenant = cast(Tenant, tenant_api_key.tenant)
        request.tenant = tenant
        request.tenant_api_key = tenant_api_key
        request.tenant_api_key_provided = True
        set_current_tenant(tenant)

        return AnonymousUser(), tenant_api_key
