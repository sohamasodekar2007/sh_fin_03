"""
FOCUS 1.0 (FinOps Open Cost and Usage Spec) normalization schemas.

Column set, nullability and enum values below were derived empirically from
the real FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data repo
(FOCUS-1.0/focus_sample_100000.csv.gz — 100,000 anonymized real AWS,
Microsoft, Oracle and Google Cloud billing rows for Sept 2024), not guessed
from the spec document. See services/focus/sample_loader.py for the loader
that reads those files.

Two things worth knowing before touching this file:
  - The source CSV has 44 columns, one of which (`Id`, a bare numeric row
    sequence number sandwiched between ServiceCategory and ServiceName) is
    NOT part of the FOCUS 1.0 spec. It has no defined meaning, so it is
    captured in `extensions["Id"]` rather than promoted to a typed field.
  - ServiceCategory includes two values seen verbatim in the real data that
    are not part of FOCUS's official taxonomy ("GCP", "Web"). They are kept
    because the instruction was to extract what the data contains, not to
    silently coerce it into an idealized spec.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums — every member below was observed in the real 100k-row FOCUS sample.
# ---------------------------------------------------------------------------

# 99,451/100,000 "Usage" + 282 "Credit" + 256 "Adjustment" + 6 "Tax" + 3 "Purchase".
# 2 rows carried a lowercase "usage" — normalized to "Usage" on ingest (see
# _CHARGE_CATEGORY_ALIASES below), not treated as a distinct 6th category.
ChargeCategoryLiteral = Literal["Usage", "Credit", "Adjustment", "Tax", "Purchase"]

# All 15 non-empty distinct values observed. "Others" (7 rows) normalized to
# the canonical "Other" (5,447 rows). "GCP" and "Web" are not part of FOCUS's
# published taxonomy but appear verbatim in real Google Cloud / Microsoft
# rows in this dataset, so they are kept rather than invented away.
ServiceCategoryLiteral = Literal[
    "AI and Machine Learning",
    "Analytics",
    "Business Applications",
    "Compute",
    "Databases",
    "Developer Tools",
    "GCP",
    "Identity",
    "Integration",
    "Management and Governance",
    "Networking",
    "Other",
    "Security",
    "Storage",
    "Web",
]

ChargeFrequencyLiteral = Literal["One-Time", "Usage-Based", "Recurring"]
PricingCategoryLiteral = Literal["Standard", "Committed", "Dynamic", "Other"]
CommitmentDiscountCategoryLiteral = Literal["Spend", "Usage"]
CommitmentDiscountStatusLiteral = Literal["Used", "Unused"]
CommitmentDiscountTypeLiteral = Literal["Reservation", "Savings Plan"]

# Casing/spelling variants observed in the real sample, mapped to the
# canonical spelling used by the Literal types above.
_CHARGE_CATEGORY_ALIASES = {"usage": "Usage"}
_SERVICE_CATEGORY_ALIASES = {"others": "Other"}
_CHARGE_FREQUENCY_ALIASES = {"usage-based": "Usage-Based"}
_PRICING_CATEGORY_ALIASES = {"standard": "Standard"}


def _normalize_enum(value: Any, aliases: dict[str, str]) -> Any:
    if isinstance(value, str):
        fixed = aliases.get(value.strip().lower())
        if fixed:
            return fixed
    return value


def _none_if_blank(value: Any) -> Any:
    """The source CSV uses both empty string and the literal text "NULL"
    to mean missing — collapse both to None so Optional fields validate."""
    if isinstance(value, str) and value.strip() in ("", "NULL"):
        return None
    return value


def _as_utc_datetime(value: Any) -> Any:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


class FocusRecord(BaseModel):
    """One FOCUS 1.0 charge row. Field set is the full 44-column header of
    the real FOCUS-Sample-Data CSVs, minus the non-spec `Id` column (see
    module docstring), plus a typed `extensions` dict for that column and
    any future x_-prefixed vendor extensions (e.g. VPS's x_OriginalBilledCost
    in a later phase)."""

    model_config = {"str_strip_whitespace": True}

    # --- Billing account -----------------------------------------------
    BillingAccountId: str
    BillingAccountName: str | None = None
    SubAccountId: str | None = None
    SubAccountName: str | None = None
    BillingCurrency: str = "USD"

    # --- Billing period (monthly invoice window) ------------------------
    BillingPeriodStart: datetime
    BillingPeriodEnd: datetime

    # --- Charge period (the actual usage window this row covers) -------
    ChargePeriodStart: datetime
    ChargePeriodEnd: datetime

    # --- Charge classification ------------------------------------------
    ChargeCategory: ChargeCategoryLiteral
    ChargeClass: str | None = None
    ChargeDescription: str
    ChargeFrequency: ChargeFrequencyLiteral | None = None

    # --- Costs — Decimal always, never float, to preserve exact precision
    BilledCost: Decimal
    EffectiveCost: Decimal
    ListCost: Decimal | None = None
    ContractedCost: Decimal | None = None
    ListUnitPrice: Decimal | None = None
    ContractedUnitPrice: Decimal | None = None

    # --- Usage / pricing quantities --------------------------------------
    ConsumedQuantity: Decimal | None = None
    ConsumedUnit: str | None = None
    PricingQuantity: Decimal | None = None
    PricingUnit: str | None = None
    PricingCategory: PricingCategoryLiteral | None = None

    # --- Commitment discounts (reservations / savings plans) -------------
    CommitmentDiscountId: str | None = None
    CommitmentDiscountName: str | None = None
    CommitmentDiscountCategory: CommitmentDiscountCategoryLiteral | None = None
    CommitmentDiscountStatus: CommitmentDiscountStatusLiteral | None = None
    CommitmentDiscountType: CommitmentDiscountTypeLiteral | None = None

    # --- Provider / publisher / invoice -----------------------------------
    ProviderName: str
    PublisherName: str | None = None
    InvoiceIssuerName: str | None = None

    # --- Region ------------------------------------------------------------
    RegionId: str | None = None
    RegionName: str | None = None
    AvailabilityZone: str | None = None

    # --- Resource ------------------------------------------------------------
    ResourceId: str | None = None
    ResourceName: str | None = None
    ResourceType: str | None = None

    # --- Service / SKU ------------------------------------------------------
    ServiceCategory: ServiceCategoryLiteral | None = None
    ServiceName: str
    SkuId: str | None = None
    SkuPriceId: str | None = None

    # --- Tags ------------------------------------------------------------
    Tags: dict[str, Any] = Field(default_factory=dict)

    # --- Non-standard / vendor extension columns --------------------------
    # x_-prefixed FOCUS vendor extensions, plus any non-spec column found in
    # real source data (e.g. this sample dataset's bare "Id" column).
    extensions: dict[str, Any] = Field(default_factory=dict)

    # -- normalization -----------------------------------------------------

    @field_validator(
        "BillingAccountName", "SubAccountId", "SubAccountName", "ChargeClass",
        "PublisherName", "InvoiceIssuerName", "RegionId", "RegionName",
        "AvailabilityZone", "ResourceId", "ResourceName", "ResourceType",
        "SkuId", "SkuPriceId", "CommitmentDiscountId", "CommitmentDiscountName",
        "ConsumedUnit", "PricingUnit",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        return _none_if_blank(v)

    @field_validator(
        "ConsumedQuantity", "PricingQuantity", "ListCost", "ContractedCost",
        "ListUnitPrice", "ContractedUnitPrice",
        mode="before",
    )
    @classmethod
    def _blank_decimal_to_none(cls, v: Any) -> Any:
        return _none_if_blank(v)

    @field_validator(
        "BillingPeriodStart", "BillingPeriodEnd", "ChargePeriodStart", "ChargePeriodEnd",
        mode="before",
    )
    @classmethod
    def _ensure_utc(cls, v: Any) -> Any:
        return _as_utc_datetime(v)

    @field_validator("ChargeCategory", mode="before")
    @classmethod
    def _normalize_charge_category(cls, v: Any) -> Any:
        return _normalize_enum(v, _CHARGE_CATEGORY_ALIASES)

    @field_validator("ServiceCategory", mode="before")
    @classmethod
    def _normalize_service_category(cls, v: Any) -> Any:
        return _normalize_enum(_none_if_blank(v), _SERVICE_CATEGORY_ALIASES)

    @field_validator("ChargeFrequency", mode="before")
    @classmethod
    def _normalize_charge_frequency(cls, v: Any) -> Any:
        return _normalize_enum(_none_if_blank(v), _CHARGE_FREQUENCY_ALIASES)

    @field_validator("PricingCategory", mode="before")
    @classmethod
    def _normalize_pricing_category(cls, v: Any) -> Any:
        return _normalize_enum(_none_if_blank(v), _PRICING_CATEGORY_ALIASES)

    @field_validator(
        "CommitmentDiscountCategory", "CommitmentDiscountStatus", "CommitmentDiscountType",
        mode="before",
    )
    @classmethod
    def _blank_commitment_enum_to_none(cls, v: Any) -> Any:
        return _none_if_blank(v)

    @field_validator("Tags", mode="before")
    @classmethod
    def _parse_tags(cls, v: Any) -> Any:
        if v in (None, "", "NULL"):
            return {}
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            import json

            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except (ValueError, TypeError):
                return {}
        return {}

    # -- conformance checking (never raises) --------------------------------

    _REQUIRED_COLUMNS: ClassVar[tuple[str, ...]] = (
        "BillingAccountId", "BillingPeriodStart", "BillingPeriodEnd",
        "ChargePeriodStart", "ChargePeriodEnd", "ChargeCategory",
        "ChargeDescription", "BilledCost", "EffectiveCost", "ProviderName",
        "ServiceName",
    )

    @classmethod
    def validate_record(cls, data: dict[str, Any]) -> list[str]:
        """
        Conformance check over a raw (pre-model) FOCUS row dict. Returns a
        list of warning codes — never raises, so the caller can always
        persist the row and just attach these warnings to it.
        """
        warnings: list[str] = []

        for field in cls._REQUIRED_COLUMNS:
            value = _none_if_blank(data.get(field))
            if value is None:
                warnings.append(f"missing_required_column:{field}")

        currency = _none_if_blank(data.get("BillingCurrency"))
        if currency is not None and currency != "USD":
            warnings.append(f"currency_mismatch:{currency}")

        raw_cost = data.get("BilledCost")
        try:
            billed = Decimal(str(raw_cost)) if raw_cost not in (None, "", "NULL") else None
        except (InvalidOperation, TypeError, ValueError):
            billed = None
            warnings.append("invalid_billed_cost")

        if billed is not None and billed < 0:
            category = _normalize_enum(data.get("ChargeCategory"), _CHARGE_CATEGORY_ALIASES)
            if category != "Credit":
                warnings.append("negative_billed_cost_on_non_credit_row")

        return warnings

    # -- safe construction ("never drop a row silently") --------------------

    _REQUIRED_STR_DEFAULTS: ClassVar[tuple[str, ...]] = (
        "BillingAccountId", "ChargeDescription", "ProviderName", "ServiceName",
    )

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> tuple[FocusRecord, list[str]]:
        """
        Build a FocusRecord from a raw column dict, guaranteeing a record is
        always produced. Missing required fields get a safe placeholder
        value (empty string / zero) rather than raising, matching
        validate_record()'s "warn, never drop" contract. Returns
        (record, warnings) — warnings mirror validate_record() plus anything
        that had to be defaulted or coerced.
        """
        warnings = cls.validate_record(data)

        # Any column not declared on the model (e.g. this sample dataset's
        # non-spec "Id" column, or a real x_-prefixed vendor extension) is
        # swept into extensions here — once, generically — rather than
        # relying on each caller to strip it before calling from_raw().
        declared_fields = set(cls.model_fields) - {"extensions"}
        kwargs: dict[str, Any] = {}
        extensions: dict[str, Any] = dict(data.get("extensions") or {})
        for key, value in data.items():
            if key == "extensions":
                continue
            if key in declared_fields:
                kwargs[key] = value
            else:
                extensions[key] = value
        kwargs["extensions"] = extensions

        for field in cls._REQUIRED_STR_DEFAULTS:
            if _none_if_blank(kwargs.get(field)) is None:
                kwargs[field] = ""

        for field in ("BilledCost", "EffectiveCost"):
            raw = kwargs.get(field)
            if _none_if_blank(raw) is None:
                kwargs[field] = Decimal("0")

        now = datetime.now(timezone.utc)
        for field in ("BillingPeriodStart", "BillingPeriodEnd", "ChargePeriodStart", "ChargePeriodEnd"):
            if _none_if_blank(kwargs.get(field)) is None:
                kwargs[field] = now
                warnings.append(f"defaulted_missing_period:{field}")

        if _none_if_blank(kwargs.get("ChargeCategory")) is None:
            kwargs["ChargeCategory"] = "Usage"
            warnings.append("defaulted_missing_charge_category")

        try:
            record = cls(**kwargs)
        except Exception as exc:  # noqa: BLE001 - last-resort safety net, never raise out of from_raw
            warnings.append(f"coerced_after_validation_error:{exc}")
            # Strip anything that isn't a declared field and retry with the
            # safest possible payload so a row is never dropped outright.
            safe_kwargs = {k: v for k, v in kwargs.items() if k in cls.model_fields}
            for field in cls._REQUIRED_STR_DEFAULTS:
                safe_kwargs[field] = str(safe_kwargs.get(field) or "")
            for field in ("BilledCost", "EffectiveCost"):
                safe_kwargs[field] = Decimal("0")
            for field in ("BillingPeriodStart", "BillingPeriodEnd", "ChargePeriodStart", "ChargePeriodEnd"):
                safe_kwargs[field] = now
            safe_kwargs["ChargeCategory"] = "Usage"
            safe_kwargs.pop("extensions", None)
            record = cls(**safe_kwargs, extensions={"raw_unparseable_fields": {k: str(v) for k, v in data.items()}})

        return record, warnings


class FocusDataset(BaseModel):
    """One ingestion run's worth of FOCUS rows for a tenant/provider/account."""

    dataset_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    provider: str
    account_id: str
    focus_version: str = "1.2"

    # Recorded per-dataset because the real sample data is hourly, not
    # daily — downstream aggregation needs to know which it's looking at.
    granularity: Literal["hourly", "daily"] = "daily"

    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # "live_export": read from a real AWS/Azure FOCUS 1.0 Data Export.
    # "synthesized": derived from a CloudSnapshot (no FOCUS export configured).
    # "sample": loaded from FOCUS-Sample-Data, no live account connected.
    # "modelled": no billing API exists at all (VPS) — cost is computed
    # from a fixed monthly figure, never observed.
    source: Literal["live_export", "synthesized", "sample", "modelled"]

    row_count: int = 0
    records: list[FocusRecord] = Field(default_factory=list)

    # Per-dataset rollup of validate_record() warnings, in "code:row_index"
    # form, so a caller can see conformance issues without walking every row.
    warnings: list[str] = Field(default_factory=list)
