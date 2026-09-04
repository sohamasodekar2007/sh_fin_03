from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from apps.api.config import Settings


class AWSAuthenticationError(Exception):
    """Raised when CloudCare cannot assume the configured AWS role."""


class AWSClientFactory:
    def __init__(self, settings: Settings):
        self.settings = settings

        self._assumed_session: boto3.Session | None = None
        self._expires_at: datetime | None = None

        self._botocore_config = Config(
            connect_timeout=5,
            read_timeout=20,
            retries={
                "max_attempts": 4,
                "mode": "standard",
            },
            user_agent_extra="CloudCare/1.0",
        )

    def _base_session(self) -> boto3.Session:
        profile_name = (
            self.settings.aws_profile.strip()
            if self.settings.aws_profile
            else None
        )

        return boto3.Session(
            aws_access_key_id=self.settings.aws_access_key_id or None,
            aws_secret_access_key=self.settings.aws_secret_access_key or None,
            profile_name=profile_name or None,
            region_name=self.settings.aws_region,
        )

    def _session_needs_refresh(self) -> bool:
        if self._assumed_session is None or self._expires_at is None:
            return True

        refresh_before = datetime.now(timezone.utc) + timedelta(minutes=5)

        return refresh_before >= self._expires_at

    def _assume_role(self) -> boto3.Session:
        base_session = self._base_session()

        sts = base_session.client(
            "sts",
            region_name=self.settings.aws_region,
            config=self._botocore_config,
        )

        kwargs: dict[str, Any] = {
            "RoleArn": self.settings.aws_role_arn or getattr(self.settings, "aws_read_role_arn", ""),
            "RoleSessionName": "cloudcare-local-collector",
            "DurationSeconds": 3600,
        }
        if self.settings.aws_external_id and len(self.settings.aws_external_id.strip()) >= 2:
            kwargs["ExternalId"] = self.settings.aws_external_id.strip()

        try:
            response = sts.assume_role(**kwargs)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get(
                "Code",
                "UNKNOWN_AWS_ERROR",
            )

            raise AWSAuthenticationError(
                f"CloudCare could not assume the AWS role: {error_code}"
            ) from error

        credentials = response["Credentials"]

        self._expires_at = credentials["Expiration"]

        self._assumed_session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=self.settings.aws_region,
        )

        return self._assumed_session

    def session(self) -> boto3.Session:
        role_arn = self.settings.aws_role_arn or getattr(self.settings, "aws_read_role_arn", "")
        if role_arn and "arn:aws:iam" in role_arn and "role/" in role_arn:
            if self._session_needs_refresh():
                try:
                    return self._assume_role()
                except Exception as e:
                    print(f"[AWS Session] Assume role error: {e}")
            if self._assumed_session:
                return self._assumed_session

        if self.settings.aws_access_key_id and self.settings.aws_secret_access_key:
            return boto3.Session(
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
                region_name=self.settings.aws_region,
            )

        return self._base_session()

    def client(
        self,
        service_name: str,
        region_name: str | None = None,
    ) -> Any:
        target_region = region_name or self.settings.aws_region

        if service_name == "ce":
            target_region = "us-east-1"

        return self.session().client(
            service_name,
            region_name=target_region,
            config=self._botocore_config,
        )
