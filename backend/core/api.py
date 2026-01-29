from __future__ import annotations

from typing import Any, cast

from rest_framework.viewsets import ModelViewSet


class TenantScopedQuerysetMixin:
    tenant_field = "tenant"

    def get_queryset(self):
        base_get_queryset = cast(Any, super()).get_queryset
        queryset = base_get_queryset()
        request = getattr(self, "request", None)
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return queryset.none()
        return queryset.filter(**{self.tenant_field: tenant})

    def perform_create(self, serializer) -> None:
        request = getattr(self, "request", None)
        tenant = getattr(request, "tenant", None)
        serializer.save(**{self.tenant_field: tenant})


class TenantScopedModelViewSet(TenantScopedQuerysetMixin, ModelViewSet):
    pass
