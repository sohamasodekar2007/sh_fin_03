from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolves to the monorepo root .env regardless of the folder uvicorn is launched from
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """
    Central app config, loaded from environment variables / .env.
    See .env.example for the full list of placeholders you need to fill in.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # MongoDB — PLACEHOLDER until you create a real Atlas cluster
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "cloudcare"

    # Auth — PLACEHOLDER, replace with a real secret before shipping
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_expire_minutes: int = 60
    jwt_algorithm: str = "HS256"

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    resend_api_key: str = ""
    brevo_api_key: str = ""

    # WebAuthn
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "CloudCare"
    webauthn_origin: str = "http://localhost:3000"

    # AWS
    aws_region: str = "ap-south-1"
    aws_account_id: str = ""
    aws_profile: str | None = None
    aws_role_arn: str = ""
    aws_read_role_arn: str = ""
    aws_external_id: str = ""
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # AWS — Executor (Phase 6). A SEPARATE role from aws_read_role_arn —
    # the read role can never mutate anything, on purpose (see
    # services/collector/aws_session.py). Only services/executor/actions.py
    # assumes this one. Never widen the read role instead of setting this.
    aws_write_role_arn: str = ""

    # Real FOCUS 1.0 Data Export (optional — synthesis from CloudSnapshot is the fallback)
    focus_export_s3_bucket: str = ""
    focus_export_s3_prefix: str = ""

    # Azure
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_subscription_id: str = ""

    # Real Azure Cost Management FOCUS 1.0 export (optional — synthesis from
    # the collectors below is the fallback)
    azure_focus_storage_account: str = ""
    azure_focus_container: str = ""

    # VPS — company-owned server, no billing API. Cost is modelled, not
    # observed; see services/focus/mappers/vps.py.
    vps_host: str = ""
    vps_port: int = 22
    vps_username: str = "cloudcare"
    vps_ssh_key_path: str = "~/.ssh/cloudcare_vps"
    vps_ssh_key_passphrase: str = ""  # never a password — key-only auth
    vps_company_name: str = "CloudCare"

    vps_monthly_cost: str = "0"
    vps_monthly_cost_currency: str = "INR"

    vps_metrics_endpoint: str = ""  # optional Prometheus/node_exporter URL; preferred over SSH when set
    vps_sar_backfill_enabled: bool = True
    vps_sar_backfill_days: int = 14

    # Currency — USD is the stored currency everywhere; INR is a
    # display-only subscript computed at render time. See
    # cloudcare_demo's build plan Q5.
    usd_to_inr: float = 83.0

    # LLM — GPT-4o, shared by the Decision agent (Phase 4) and the chatbot
    # (Phase 7) via services/llm/client.py. OPENAI_BASE_URL stays
    # configurable so this can route through an OpenAI-compatible proxy —
    # whichever endpoint it points at, use that endpoint's own key, never
    # mix a real OpenAI key with a third-party base_url.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 3

    # Approval loop (Phase 5) — the frontend origin the approval email's
    # buttons link into (APP_BASE_URL/approve/<token>), and the secret that
    # HMAC-signs those single-use tokens. Deliberately a DIFFERENT secret
    # from jwt_secret — a leaked approval-token secret should not also
    # forge login sessions, and vice versa.
    app_base_url: str = "http://localhost:3000"
    approval_token_secret: str = "dev-only-insecure-approval-secret-change-me"

    # Execution safety — EXECUTION_ENABLED defaults false so a missing/
    # misconfigured .env can never execute anything. EXECUTION_MODE is the
    # simulation/live runtime switch (services/executor/actions.py). The
    # allowlist tag is a HARD gate, independent of execution_mode — no
    # resource without it may ever be mutated, in simulation or live.
    execution_enabled: bool = False
    execution_mode: str = "simulation"
    execution_allowlist_tag: str = "cloudcare:managed=true"

    # Scheduler — hourly monitor -> analyzer -> decision -> supervisor pipeline
    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    # NOTE: cached for the process lifetime — uvicorn --reload only watches
    # .py files, so a .env-only edit is NOT picked up until the worker
    # actually restarts. Touch any watched source file (or fully restart
    # the process) after changing .env.
    return Settings()
