import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from apps.api.config import get_settings
from services.collector.ec2_collector import EC2Collector
from packages.aws.session import AWSClientFactory


def main() -> None:
    settings = get_settings()

    factory = AWSClientFactory(settings)

    collector = EC2Collector(
        client_factory=factory,
        region=settings.aws_region,
    )

    resources = collector.collect()

    output = {
        "status": "complete",
        "region": settings.aws_region,
        "resource_count": len(resources),
        "resources": [
            resource.model_dump(mode="json")
            for resource in resources
        ],
    }

    print(
        json.dumps(
            output,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
