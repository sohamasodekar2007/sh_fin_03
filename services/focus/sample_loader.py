"""
Loads real FOCUS 1.0 rows from a local clone of

    https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data

into .focus-samples/ at the repo root (gitignored).

PROVIDER -> SAMPLE-FILE MAPPING, derived from what's actually in the repo
(not assumed): FOCUS-1.0/ ships ONE combined, multi-provider CSV per size
tier (1K / 10K / 100K rows) — see FOCUS-1.0/README.md — not a separate file
per provider. Every row carries its own ProviderName ("AWS", "Microsoft",
"Oracle" or "Google Cloud"), so "loading provider X" means filtering that
column, not opening a different file. The 100K-row file
(focus_sample_100000.csv.gz) is the only one of the three that contains all
four providers — Google Cloud has just 2 rows in the entire dataset, and 0
rows in the 1K/10K files — so it's the one this loader reads from.
"""

from __future__ import annotations

import csv
import gzip
import logging
from pathlib import Path

from packages.schemas.focus import FocusDataset, FocusRecord

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SAMPLE_DIR = _REPO_ROOT / ".focus-samples" / "FOCUS-1.0"
_SAMPLE_FILE = "focus_sample_100000.csv.gz"

# our provider slug -> the ProviderName value(s) that identify it in the
# combined sample CSV.
_PROVIDER_NAME_MAP: dict[str, tuple[str, ...]] = {
    "aws": ("AWS",),
    "azure": ("Microsoft",),
    "gcp": ("Google Cloud",),
    "oracle": ("Oracle",),
}

DEFAULT_MAX_ROWS_PER_PROVIDER = 500


class FocusSampleDataNotFoundError(FileNotFoundError):
    pass


def load_sample_dataset(
    provider: str,
    tenant_id: str,
    max_rows: int = DEFAULT_MAX_ROWS_PER_PROVIDER,
    sample_dir: Path | None = None,
) -> FocusDataset:
    """
    Load up to `max_rows` real FOCUS 1.0 rows for `provider` from the cloned
    FOCUS-Sample-Data repo. Every row is passed through
    FocusRecord.from_raw(), so a malformed row is warned about, never
    dropped.
    """
    provider_key = provider.strip().lower()
    provider_names = _PROVIDER_NAME_MAP.get(provider_key)
    if not provider_names:
        raise ValueError(
            f"No FOCUS sample data mapping for provider={provider!r}. "
            f"Known providers: {sorted(_PROVIDER_NAME_MAP)}. VPS has no FOCUS "
            "sample equivalent — it gets a modelled cost basis in a later phase."
        )

    directory = sample_dir or _DEFAULT_SAMPLE_DIR
    path = directory / _SAMPLE_FILE
    if not path.exists():
        raise FocusSampleDataNotFoundError(
            f"FOCUS sample data not found at {path}. Clone "
            "https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data "
            "into .focus-samples/ at the repo root before calling load_sample_dataset()."
        )

    records: list[FocusRecord] = []
    warnings: list[str] = []
    row_index = 0

    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            if raw_row.get("ProviderName") not in provider_names:
                continue

            record, row_warnings = FocusRecord.from_raw(raw_row)
            warnings.extend(f"{w}:row_{row_index}" for w in row_warnings)
            records.append(record)
            row_index += 1

            if len(records) >= max_rows:
                break

    account_id = records[0].BillingAccountId if records else ""

    logger.info(
        "focus.sample_loader: loaded %d rows for provider=%s tenant=%s from %s "
        "(%d conformance warnings)",
        len(records), provider_key, tenant_id, _SAMPLE_FILE, len(warnings),
    )

    return FocusDataset(
        tenant_id=tenant_id,
        provider=provider_key,
        account_id=account_id,
        # Empirically ~1 hour between ChargePeriodStart/End in this sample —
        # see packages/schemas/focus.py module docstring.
        granularity="hourly",
        source="sample",
        row_count=len(records),
        records=records,
        warnings=warnings,
    )
