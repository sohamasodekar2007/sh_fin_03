"""
Azure client factory — the AzureClientFactory analog of
packages/aws/session.py:AWSClientFactory. Builds one ClientSecretCredential
from AZURE_TENANT_ID/AZURE_CLIENT_ID/AZURE_CLIENT_SECRET and reuses it
across every typed management client; azure-identity's credential object
handles its own token acquisition/refresh, so "caching" here just means
constructing it once per factory instance rather than per call.

Never logs the client secret — only ever reads it from settings to build
the credential, and print()/logging.debug() must not be added anywhere
that touches self._client_secret.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential

if TYPE_CHECKING:
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.costmanagement import CostManagementClient
    from azure.mgmt.resource import ResourceManagementClient
    from azure.monitor.query import MetricsQueryClient

    from apps.api.config import Settings


class AzureAuthenticationError(Exception):
    """Raised when CloudCare cannot authenticate against Azure with the
    configured service principal."""


class AzureClientFactory:
    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self.subscription_id = settings.azure_subscription_id
        self._credential: ClientSecretCredential | None = None

    def credential(self) -> ClientSecretCredential:
        if self._credential is None:
            if not (
                self.settings.azure_tenant_id
                and self.settings.azure_client_id
                and self.settings.azure_client_secret
            ):
                raise AzureAuthenticationError(
                    "AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET are not fully set."
                )
            self._credential = ClientSecretCredential(
                tenant_id=self.settings.azure_tenant_id,
                client_id=self.settings.azure_client_id,
                client_secret=self.settings.azure_client_secret,
            )
        return self._credential

    def compute_client(self) -> "ComputeManagementClient":
        from azure.mgmt.compute import ComputeManagementClient

        if not self.subscription_id:
            raise AzureAuthenticationError("AZURE_SUBSCRIPTION_ID is not set.")
        return ComputeManagementClient(self.credential(), self.subscription_id)

    def resource_client(self) -> "ResourceManagementClient":
        from azure.mgmt.resource import ResourceManagementClient

        if not self.subscription_id:
            raise AzureAuthenticationError("AZURE_SUBSCRIPTION_ID is not set.")
        return ResourceManagementClient(self.credential(), self.subscription_id)

    def cost_management_client(self) -> "CostManagementClient":
        from azure.mgmt.costmanagement import CostManagementClient

        return CostManagementClient(self.credential())

    def metrics_query_client(self) -> "MetricsQueryClient":
        from azure.monitor.query import MetricsQueryClient

        return MetricsQueryClient(self.credential())

    def subscription_scope(self) -> str:
        if not self.subscription_id:
            raise AzureAuthenticationError("AZURE_SUBSCRIPTION_ID is not set.")
        return f"/subscriptions/{self.subscription_id}"

    def verify_access(self) -> bool:
        """A cheap, real API call to confirm the service principal actually
        has a role assignment on the subscription — registering an app and
        granting it access are two separate Azure steps, and this is the
        step that catches a missing one before a collector run does."""
        if not (
            self.subscription_id
            and self.settings.azure_tenant_id
            and self.settings.azure_client_id
            and self.settings.azure_client_secret
        ):
            return False

        try:
            client = self.resource_client()
            next(iter(client.resource_groups.list()), None)
            return True
        except ClientAuthenticationError:
            return False
        except AzureAuthenticationError:
            return False
