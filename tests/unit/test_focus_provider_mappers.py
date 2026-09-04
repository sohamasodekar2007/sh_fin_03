from __future__ import annotations

from pathlib import Path

import pytest

from packages.schemas.focus import FocusDataset
from services.focus.mappers import gcp, vps

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_FILE = _REPO_ROOT / ".focus-samples" / "FOCUS-1.0" / "focus_sample_100000.csv.gz"

requires_sample_data = pytest.mark.skipif(
    not _SAMPLE_FILE.exists(),
    reason="FOCUS-Sample-Data not cloned into .focus-samples/",
)


@requires_sample_data
def test_gcp_mapper_delegates_to_sample_loader():
    dataset = gcp.map_account_to_focus("demo-tenant", account_id="my-gcp-project")

    assert isinstance(dataset, FocusDataset)
    assert dataset.source == "sample"
    assert dataset.provider == "gcp"
    assert dataset.account_id == "my-gcp-project"
    assert dataset.row_count > 0


# Azure's mapper (services/focus/mappers/azure.py) is no longer a sample
# delegate as of Phase 2b — it's the real collector-backed implementation,
# covered by tests/unit/test_azure_collector.py and
# tests/unit/test_focus_multiprovider.py instead.

# VPS's mapper (services/focus/mappers/vps.py) is no longer a sample
# delegate as of Phase 2c either — it's the real modelled-cost implementation
# (map_vps_to_focus), covered by tests/unit/test_vps_cost_model.py instead.
# map_account_to_focus() only survives as a deliberately-inert back-compat
# shim for the old placeholder signature.


def test_vps_map_account_to_focus_shim_is_intentionally_a_stub():
    dataset = vps.map_account_to_focus("demo-tenant", account_id="my-server")

    assert isinstance(dataset, FocusDataset)
    assert dataset.provider == "vps"
    assert dataset.source == "modelled"
    assert dataset.row_count == 0
    assert dataset.records == []
    assert "map_account_to_focus_is_a_stub_use_map_vps_to_focus" in dataset.warnings
