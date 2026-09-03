from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app config, loaded from environment variables / .env.
    See .env.example for the full list of placeholders you need to fill in.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"

    # MongoDB — PLACEHOLDER until you create a real Atlas cluster
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "cloudcare"

    # Auth — FastAPI validates NextAuth's JWT, it never mints one (spec
    # section 2). This MUST be byte-for-byte the same value as the
    # frontend's NEXTAUTH_SECRET (apps/web/.env.local) — PLACEHOLDER below,
    # replace before shipping: openssl rand -base64 32
    nextauth_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"

    # AES-256-GCM key for CloudAccount.encrypted_credentials (spec section
    # 3) — must decode from base64 to exactly 32 bytes. PLACEHOLDER,
    # generate with: python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
    encryption_key: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    # AWS — a single dev-account fallback role used when a tenant hasn't
    # onboarded their own CloudAccount yet (services/adapters/aws_adapter.py)
    aws_region: str = "us-east-1"
    aws_read_role_arn: str = ""
    aws_external_id: str = ""

    # LLM — PLACEHOLDER, Decision Agent + chat orchestrator degrade to
    # deterministic-only behavior when this is empty (spec sections 4.3, 5)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Execution safety — the Executor Agent never makes a live cloud call;
    # this only toggles whether AUTO_APPROVE proposals are simulated
    # (status="simulated") or left disabled (status="disabled").
    execution_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
