import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from apps.api.config import get_settings
from services.collector.collector_service import AWSCollectorService
from packages.aws.session import AWSClientFactory


def extract_account_id(role_arn: str) -> str:
    parts = role_arn.split(":")

    if len(parts) < 5 or not parts[4]:
        raise ValueError("Invalid AWS role ARN")

    return parts[4]


def main() -> None:
    settings = get_settings()
    factory = AWSClientFactory(settings)

    service = AWSCollectorService(
        client_factory=factory,
        region=settings.aws_region,
        account_id=extract_account_id(
            settings.aws_role_arn
        ),
        cost_cache_hours=6,
    )

    snapshot = service.collect_snapshot()

    print(snapshot.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
