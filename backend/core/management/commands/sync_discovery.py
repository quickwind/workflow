from __future__ import annotations

from typing import Any, cast

from django.core.management.base import BaseCommand, CommandError

from core.discovery import sync_discovery_for_tenant
from core.models import Tenant, TenantDiscoveryEndpoint


class Command(BaseCommand):
    help = "Sync tenant discovery payloads into catalog and directory data."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            dest="tenant",
            help="Tenant id or slug to sync.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        tenant_selector = options.get("tenant")
        endpoint_manager = cast(Any, TenantDiscoveryEndpoint)._default_manager
        endpoints = endpoint_manager.select_related("tenant")
        if tenant_selector:
            tenant = self._get_tenant(tenant_selector)
            endpoints = endpoints.filter(tenant=tenant)

        if not endpoints.exists():
            raise CommandError("No discovery endpoints found for sync.")

        for endpoint in endpoints:
            result = sync_discovery_for_tenant(endpoint.tenant, endpoint)
            self.stdout.write(
                f"tenant={result.tenant_id} status={result.status} errors={len(result.errors)}"
            )

    def _get_tenant(self, selector: str) -> Tenant:
        tenant = None
        tenant_manager = cast(Any, Tenant)._default_manager
        if selector.isdigit():
            tenant = tenant_manager.filter(id=int(selector)).first()
        if tenant is None:
            tenant = tenant_manager.filter(slug=selector).first()
        if tenant is None:
            raise CommandError("Tenant not found.")
        return tenant
