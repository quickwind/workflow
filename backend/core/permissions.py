from __future__ import annotations

from rest_framework.permissions import BasePermission


class TenantRequired(BasePermission):
    message = "Tenant API key required."

    def has_permission(self, request, view) -> bool:
        return getattr(request, "tenant", None) is not None
