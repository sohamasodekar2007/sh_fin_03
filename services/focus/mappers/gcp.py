"""
GCP FOCUS mapper.

No live GCP collector exists yet (a real one needs a service account with
roles/billing.viewer + roles/bigquery.dataViewer and a BigQuery billing
export dataset — out of scope for this phase). Until that's built, this
always delegates to the FOCUS sample dataset so the demo has real-shaped
data for GCP, and honestly reports FocusDataset.source="sample" rather than
pretending to have observed a live account.
"""

from __future__ import annotations

from packages.schemas.focus import FocusDataset
from services.focus.sample_loader import load_sample_dataset


def map_account_to_focus(tenant_id: str, account_id: str = "") -> FocusDataset:
    dataset = load_sample_dataset("gcp", tenant_id)
    if account_id:
        dataset.account_id = account_id
    return dataset
