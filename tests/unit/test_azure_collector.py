from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

from packages.azure.session import AzureAuthenticationError, AzureClientFactory
from services.collector.azure.cost_collector import (
    AzureCostCollectionError,
    AzureCostCollector,
    AzureCostRateLimitedError,
    _parse_usage_date,
)
from services.collector.azure.disk_collector import (
    AzureDiskCollectionError,
    AzureDiskCollector,
    normalize_disk,
)
from services.collector.azure.metrics_collector import AzureMetricsCollector, _percentile
from services.collector.azure.vm_collector import (
    AzureVMCollectionError,
    AzureVMCollector,
    find_tag,
    normalize_environment,
    normalize_vm,
    power_state_from_instance_view,
    resource_group_from_id,
)


def _settings(**overrides):
    base = dict(
        azure_tenant_id="tenant-1",
        azure_client_id="client-1",
        azure_client_secret="secret-1",
        azure_subscription_id="sub-1",
    )
    base.update(overrides)
    return MagicMock(**base)


# ---------------------------------------------------------------------------
# packages/azure/session.py
# ---------------------------------------------------------------------------


def test_client_factory_raises_when_credentials_incomplete():
    factory = AzureClientFactory(_settings(azure_client_secret=""))
    with pytest.raises(AzureAuthenticationError):
        factory.credential()


def test_client_factory_caches_credential_instance():
    factory = AzureClientFactory(_settings())
    with patch("packages.azure.session.ClientSecretCredential") as mock_cred_cls:
        mock_cred_cls.return_value = Mock()
        first = factory.credential()
        second = factory.credential()
    assert first is second
    mock_cred_cls.assert_called_once_with(tenant_id="tenant-1", client_id="client-1", client_secret="secret-1")


def test_compute_client_requires_subscription_id():
    factory = AzureClientFactory(_settings(azure_subscription_id=""))
    with pytest.raises(AzureAuthenticationError):
        factory.compute_client()


def test_subscription_scope_format():
    factory = AzureClientFactory(_settings())
    assert factory.subscription_scope() == "/subscriptions/sub-1"


def test_verify_access_true_when_resource_groups_listable():
    factory = AzureClientFactory(_settings())
    fake_client = Mock()
    fake_client.resource_groups.list.return_value = iter([Mock()])
    factory.resource_client = Mock(return_value=fake_client)

    assert factory.verify_access() is True


def test_verify_access_false_on_authentication_failure():
    factory = AzureClientFactory(_settings())
    factory.resource_client = Mock(side_effect=ClientAuthenticationError("nope"))

    assert factory.verify_access() is False


def test_verify_access_false_when_credentials_missing():
    factory = AzureClientFactory(_settings(azure_client_secret=""))
    assert factory.verify_access() is False


# ---------------------------------------------------------------------------
# vm_collector.py
# ---------------------------------------------------------------------------


def test_find_tag_case_insensitive():
    assert find_tag({"Environment": "prod"}, "environment") == "prod"
    assert find_tag({}, "environment") is None


def test_normalize_environment_aliases():
    assert normalize_environment({"Environment": "PROD"}) == "production"
    assert normalize_environment({"Environment": "stg"}) == "staging"
    assert normalize_environment({}) == "unknown"


def test_resource_group_from_id_parses_arm_path():
    resource_id = "/subscriptions/sub-1/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/vm1"
    assert resource_group_from_id(resource_id) == "my-rg"


def test_resource_group_from_id_returns_none_when_absent():
    assert resource_group_from_id("/not/an/arm/path") is None


def test_power_state_from_instance_view_extracts_running():
    status = Mock(code="PowerState/running")
    vm = Mock(instance_view=Mock(statuses=[Mock(code="ProvisioningState/succeeded"), status]))
    assert power_state_from_instance_view(vm) == "running"


def test_power_state_unknown_when_no_instance_view():
    vm = Mock(instance_view=None)
    assert power_state_from_instance_view(vm) == "unknown"


def test_normalize_vm_maps_all_fields():
    resource_id = "/subscriptions/sub-1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1"
    vm = Mock()
    vm.id = resource_id
    vm.name = "vm1"
    vm.location = "eastus"
    vm.tags = {"Environment": "dev", "Owner": "team-a"}
    vm.hardware_profile = Mock(vm_size="Standard_D2s_v3")
    vm.instance_view = Mock(statuses=[Mock(code="PowerState/running")])

    record = normalize_vm(vm, datetime.now(timezone.utc))

    assert record.resource_id == resource_id  # never truncated
    assert record.resource_group == "rg1"
    assert record.region == "eastus"
    assert record.instance_type == "Standard_D2s_v3"
    assert record.state == "running"
    assert record.environment == "development"
    assert record.provider == "azure"
    assert record.resource_type == "azure_vm"
    assert record.warnings == []


def test_normalize_vm_warns_on_missing_tags_and_environment():
    vm = Mock()
    vm.id = "/subscriptions/sub-1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm2"
    vm.name = "vm2"
    vm.location = "eastus"
    vm.tags = {}
    vm.hardware_profile = None
    vm.instance_view = None

    record = normalize_vm(vm, datetime.now(timezone.utc))

    assert record.instance_type == "unknown"
    assert record.state == "unknown"
    assert "RESOURCE_HAS_NO_TAGS" in record.warnings
    assert "ENVIRONMENT_TAG_MISSING_OR_INVALID" in record.warnings


def test_vm_collector_uses_status_only_true_string():
    factory = Mock()
    compute_client = Mock()
    compute_client.virtual_machines.list_all.return_value = iter([])
    factory.compute_client.return_value = compute_client

    AzureVMCollector(factory).collect()

    compute_client.virtual_machines.list_all.assert_called_once_with(status_only="true")


def test_vm_collector_raises_on_authentication_error():
    factory = Mock()
    compute_client = Mock()
    compute_client.virtual_machines.list_all.side_effect = ClientAuthenticationError("bad creds")
    factory.compute_client.return_value = compute_client

    with pytest.raises(AzureVMCollectionError):
        AzureVMCollector(factory).collect()


# ---------------------------------------------------------------------------
# disk_collector.py
# ---------------------------------------------------------------------------


def test_normalize_disk_flags_unattached():
    disk = Mock()
    disk.id = "/subscriptions/sub-1/resourceGroups/rg1/providers/Microsoft.Compute/disks/disk1"
    disk.name = "disk1"
    disk.location = "eastus"
    disk.tags = {"Environment": "prod"}
    disk.sku = Mock(name="Premium_LRS")
    disk.sku.name = "Premium_LRS"
    disk.disk_size_gb = 128
    disk.disk_state = "Unattached"

    record = normalize_disk(disk, datetime.now(timezone.utc))

    assert record.state == "unattached"
    assert record.instance_type == "128GB-Premium_LRS"
    assert "UNATTACHED_DISK" in record.warnings
    assert record.resource_type == "azure_disk"


def test_normalize_disk_attached_no_warning():
    disk = Mock()
    disk.id = "/subscriptions/sub-1/resourceGroups/rg1/providers/Microsoft.Compute/disks/disk2"
    disk.name = "disk2"
    disk.location = "eastus"
    disk.tags = {"Environment": "prod"}
    disk.sku = Mock()
    disk.sku.name = "Standard_LRS"
    disk.disk_size_gb = 32
    disk.disk_state = "Attached"

    record = normalize_disk(disk, datetime.now(timezone.utc))

    assert record.state == "attached"
    assert "UNATTACHED_DISK" not in record.warnings


def test_disk_collector_collect_unattached_filters():
    factory = Mock()
    compute_client = Mock()

    unattached = Mock(id="/x/disk1", location="eastus", tags={}, disk_size_gb=1, disk_state="Unattached")
    unattached.name = "disk1"
    unattached.sku = Mock()
    unattached.sku.name = "Standard_LRS"
    attached = Mock(id="/x/disk2", location="eastus", tags={}, disk_size_gb=1, disk_state="Attached")
    attached.name = "disk2"
    attached.sku = Mock()
    attached.sku.name = "Standard_LRS"

    compute_client.disks.list.return_value = iter([unattached, attached])
    factory.compute_client.return_value = compute_client

    result = AzureDiskCollector(factory).collect_unattached()

    assert len(result) == 1
    assert result[0].name == "disk1"


def test_disk_collector_raises_on_http_error():
    factory = Mock()
    compute_client = Mock()
    error = HttpResponseError("boom")
    error.error = None
    compute_client.disks.list.side_effect = error
    factory.compute_client.return_value = compute_client

    with pytest.raises(AzureDiskCollectionError):
        AzureDiskCollector(factory).collect()


# ---------------------------------------------------------------------------
# metrics_collector.py
# ---------------------------------------------------------------------------


def test_percentile_matches_known_values():
    assert _percentile([], 95) == 0.0
    assert _percentile([10.0], 95) == 10.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)


def _fake_metric(name: str, values: list[float]) -> Mock:
    # Mock(name=...) sets the mock's own repr name, not a `.name` attribute
    # — must be assigned after construction to be readable as metric.name.
    point_objs = [Mock(average=v) for v in values]
    series = Mock(data=point_objs)
    metric = Mock(timeseries=[series])
    metric.name = name
    return metric


def test_metrics_collector_computes_cpu_and_memory_percentiles():
    factory = Mock()
    metrics_client = Mock()
    cpu_metric = _fake_metric("Percentage CPU", [10.0, 20.0, 30.0, 90.0])
    mem_metric = _fake_metric("Available Memory Bytes", [1_000_000.0, 2_000_000.0])
    result = Mock(metrics=[cpu_metric, mem_metric])
    metrics_client.query_resource.return_value = result
    factory.metrics_query_client.return_value = metrics_client

    collector = AzureMetricsCollector(factory, tenant_id="demo-tenant")
    metrics = collector.collect_resource_metrics(["/subscriptions/sub-1/.../vm1"], window_days=14)

    assert len(metrics) == 1
    m = metrics[0]
    assert m.sample_count == 4
    assert m.cpu_avg == pytest.approx((10 + 20 + 30 + 90) / 4, rel=1e-3)
    assert m.mem_p95 is not None


def test_metrics_collector_skips_resource_with_no_cpu_data():
    """A deallocated VM or one without diagnostics returns no CPU
    datapoints — it must be skipped, never recorded with a fabricated 0%,
    which would manufacture a false idle finding."""
    factory = Mock()
    metrics_client = Mock()
    empty_result = Mock(metrics=[])
    metrics_client.query_resource.return_value = empty_result
    factory.metrics_query_client.return_value = metrics_client

    collector = AzureMetricsCollector(factory, tenant_id="demo-tenant")
    metrics = collector.collect_resource_metrics(["/subscriptions/sub-1/.../vm-deallocated"])

    assert metrics == []


def test_metrics_collector_continues_past_a_failing_resource():
    factory = Mock()
    metrics_client = Mock()

    def side_effect(resource_id, **kwargs):
        if "bad" in resource_id:
            raise RuntimeError("query failed")
        return Mock(metrics=[_fake_metric("Percentage CPU", [5.0, 6.0])])

    metrics_client.query_resource.side_effect = side_effect
    factory.metrics_query_client.return_value = metrics_client

    collector = AzureMetricsCollector(factory, tenant_id="demo-tenant")
    metrics = collector.collect_resource_metrics(["/x/bad-vm", "/x/good-vm"])

    assert len(metrics) == 1
    assert metrics[0].resource_id == "/x/good-vm"


def test_metrics_collector_rejects_invalid_window():
    factory = Mock()
    with pytest.raises(ValueError):
        AzureMetricsCollector(factory, tenant_id="demo-tenant").collect_resource_metrics(["/x/vm"], window_days=0)


# ---------------------------------------------------------------------------
# cost_collector.py
# ---------------------------------------------------------------------------


def test_parse_usage_date_handles_int_yyyymmdd():
    assert _parse_usage_date(20240915).isoformat() == "2024-09-15"


def test_parse_usage_date_handles_iso_string():
    assert _parse_usage_date("2024-09-15").isoformat() == "2024-09-15"


def _fake_query_result(columns: list[str], rows: list[list]) -> Mock:
    column_objs = [Mock(name=c) for c in columns]
    for col_obj, name in zip(column_objs, columns):
        col_obj.name = name
    return Mock(columns=column_objs, rows=rows)


def test_cost_collector_parses_rows_grouped_by_resource():
    factory = Mock()
    factory.subscription_scope.return_value = "/subscriptions/sub-1"
    cost_client = Mock()
    cost_client.query.usage.return_value = _fake_query_result(
        ["UsageDate", "ResourceId", "Cost", "Currency"],
        [
            [20240915, "/subscriptions/sub-1/.../vm1", 1.2345, "USD"],
            [20240916, "/subscriptions/sub-1/.../vm1", 2.5, "USD"],
        ],
    )
    factory.cost_management_client.return_value = cost_client

    costs = AzureCostCollector(factory).collect_daily_costs(days=30)

    assert len(costs) == 2
    assert costs[0].resource_id == "/subscriptions/sub-1/.../vm1"
    assert costs[0].cost == Decimal("1.2345")
    assert costs[0].usage_date.isoformat() == "2024-09-15"


def test_cost_collector_returns_empty_list_when_no_rows():
    factory = Mock()
    factory.subscription_scope.return_value = "/subscriptions/sub-1"
    cost_client = Mock()
    cost_client.query.usage.return_value = Mock(columns=[], rows=[])
    factory.cost_management_client.return_value = cost_client

    assert AzureCostCollector(factory).collect_daily_costs() == []


def test_cost_collector_raises_on_authentication_error():
    factory = Mock()
    factory.subscription_scope.return_value = "/subscriptions/sub-1"
    cost_client = Mock()
    cost_client.query.usage.side_effect = ClientAuthenticationError("bad creds")
    factory.cost_management_client.return_value = cost_client

    with pytest.raises(AzureCostCollectionError):
        AzureCostCollector(factory).collect_daily_costs()


def test_cost_collector_retries_once_honouring_retry_after_then_succeeds():
    factory = Mock()
    factory.subscription_scope.return_value = "/subscriptions/sub-1"
    cost_client = Mock()

    rate_limited = HttpResponseError("slow down")
    rate_limited.status_code = 429
    rate_limited.response = Mock(headers={"Retry-After": "1"})

    success_result = _fake_query_result(
        ["UsageDate", "ResourceId", "Cost"], [[20240915, "/x/vm1", 3.0]]
    )

    cost_client.query.usage.side_effect = [rate_limited, success_result]
    factory.cost_management_client.return_value = cost_client

    with patch("services.collector.azure.cost_collector.time.sleep") as mock_sleep:
        costs = AzureCostCollector(factory).collect_daily_costs()

    mock_sleep.assert_called_once_with(1.0)
    assert len(costs) == 1
    assert costs[0].cost == Decimal("3.0")


def test_cost_collector_gives_up_after_retry_still_rate_limited():
    factory = Mock()
    factory.subscription_scope.return_value = "/subscriptions/sub-1"
    cost_client = Mock()

    rate_limited = HttpResponseError("slow down")
    rate_limited.status_code = 429
    rate_limited.response = Mock(headers={"Retry-After": "2"})

    cost_client.query.usage.side_effect = [rate_limited, rate_limited]
    factory.cost_management_client.return_value = cost_client

    with patch("services.collector.azure.cost_collector.time.sleep"):
        with pytest.raises(AzureCostRateLimitedError):
            AzureCostCollector(factory).collect_daily_costs()


def test_cost_collector_raises_rate_limited_immediately_with_no_retry_after_header():
    factory = Mock()
    factory.subscription_scope.return_value = "/subscriptions/sub-1"
    cost_client = Mock()

    rate_limited = HttpResponseError("slow down")
    rate_limited.status_code = 429
    rate_limited.response = Mock(headers={})

    cost_client.query.usage.side_effect = rate_limited
    factory.cost_management_client.return_value = cost_client

    with pytest.raises(AzureCostRateLimitedError):
        AzureCostCollector(factory).collect_daily_costs()
