from datetime import datetime, timedelta, timezone
from typing import Any

from packages.schemas.cloud_metrics import DailyCost
from packages.schemas.cloud_snapshot import CloudSnapshot, CollectionIssue
from services.collector.cloudwatch_collector import CloudWatchCollector
from services.collector.cost_collector import CostExplorerCollector
from services.collector.ec2_collector import EBSCollector, EC2Collector


class AWSCollectorService:
    def __init__(
        self,
        client_factory: Any,
        region: str,
        account_id: str,
        cost_cache_hours: int = 6,
    ) -> None:
        self.client_factory = client_factory
        self.region = region
        self.account_id = account_id
        self.cost_cache_hours = cost_cache_hours

        self._cached_costs: list[DailyCost] | None = None
        self._cost_cache_expires_at: datetime | None = None

    @staticmethod
    def _normalize_resource(resource: Any) -> dict[str, Any]:
        if isinstance(resource, dict):
            return resource

        if hasattr(resource, "model_dump"):
            return resource.model_dump(mode="python")

        raise TypeError(
            f"Unsupported resource type: {type(resource).__name__}"
        )

    @staticmethod
    def _extract_instance_ids(
        resources: list[dict[str, Any]],
    ) -> list[str]:
        instance_ids: list[str] = []

        for resource in resources:
            possible_id = (
                resource.get("instance_id")
                or resource.get("resource_id")
                or resource.get("id")
            )

            if (
                isinstance(possible_id, str)
                and possible_id.startswith("i-")
            ):
                instance_ids.append(possible_id)

        return instance_ids

    @staticmethod
    def _issue(
        source: str,
        error: Exception,
        retryable: bool = True,
    ) -> CollectionIssue:
        safe_message = str(error)[:300]

        return CollectionIssue(
            source=source,
            error_type=type(error).__name__,
            message=safe_message,
            retryable=retryable,
        )

    def _run_ec2_collector(self) -> list[Any]:
        collector = EC2Collector(
            client_factory=self.client_factory,
            region=self.region,
        )

        collect_method = getattr(collector, "collect", None)

        if not callable(collect_method):
            collect_method = getattr(
                collector,
                "collect_instances",
                None,
            )

        if not callable(collect_method):
            raise AttributeError(
                "EC2Collector must define collect() "
                "or collect_instances()"
            )

        return collect_method()

    def _run_ebs_collector(self) -> list[Any]:
        collector = EBSCollector(
            client_factory=self.client_factory,
            region=self.region,
        )
        return collector.collect()

    def _get_daily_costs(
        self,
        force_refresh: bool = False,
    ) -> list[DailyCost]:
        now = datetime.now(timezone.utc)

        cache_is_valid = (
            self._cached_costs is not None
            and self._cost_cache_expires_at is not None
            and now < self._cost_cache_expires_at
        )

        if cache_is_valid and not force_refresh:
            return self._cached_costs or []

        cost_client = self.client_factory.client(
            "ce",
            region_name="us-east-1",
        )

        collector = CostExplorerCollector(
            cost_explorer_client=cost_client
        )

        # 30 days, not 7 — matches the dashboard's default cost-summary
        # window (GET /v1/focus/cost-summary?period_days=30) and gives the
        # FOCUS synthesis fallback (services/focus/mappers/aws.py) enough
        # history for a real prior-period delta instead of always coming
        # back None for lack of data reaching that far back.
        costs = collector.collect_daily_costs(days=30)

        self._cached_costs = costs
        self._cost_cache_expires_at = now + timedelta(
            hours=self.cost_cache_hours
        )

        return costs

    def collect_snapshot(
        self,
        force_cost_refresh: bool = False,
    ) -> CloudSnapshot:
        resources: list[dict[str, Any]] = []
        cpu_metrics = []
        daily_costs: list[DailyCost] = []
        issues: list[CollectionIssue] = []

        successful_sources = 0
        ec2_succeeded = False

        try:
            raw_resources = self._run_ec2_collector()

            resources = [
                self._normalize_resource(resource)
                for resource in raw_resources
            ]

            ec2_succeeded = True
            successful_sources += 1

        except Exception as error:
            issues.append(self._issue("ec2", error))

        try:
            raw_volumes = self._run_ebs_collector()

            resources.extend(
                self._normalize_resource(volume)
                for volume in raw_volumes
            )

            successful_sources += 1

        except Exception as error:
            issues.append(self._issue("ebs", error))

        if ec2_succeeded:
            try:
                instance_ids = self._extract_instance_ids(
                    resources
                )

                cloudwatch_client = self.client_factory.client(
                    "cloudwatch",
                    region_name=self.region,
                )

                cloudwatch_collector = CloudWatchCollector(
                    cloudwatch_client=cloudwatch_client,
                    region=self.region,
                )

                cpu_metrics = (
                    cloudwatch_collector.collect_cpu_metrics(
                        instance_ids=instance_ids,
                        hours=24,
                    )
                )

                successful_sources += 1

            except Exception as error:
                issues.append(
                    self._issue("cloudwatch", error)
                )
        else:
            issues.append(
                CollectionIssue(
                    source="cloudwatch",
                    error_type="DependencyError",
                    message=(
                        "CloudWatch collection skipped because "
                        "EC2 inventory collection failed."
                    ),
                    retryable=True,
                )
            )

        try:
            daily_costs = self._get_daily_costs(
                force_refresh=force_cost_refresh
            )

            successful_sources += 1

        except Exception as error:
            issues.append(
                self._issue("cost_explorer", error)
            )

        if not issues:
            status = "success"
        elif successful_sources > 0:
            status = "partial"
        else:
            status = "failed"

        return CloudSnapshot(
            account_id=self.account_id,
            region=self.region,
            collected_at=datetime.now(timezone.utc),
            status=status,
            resource_count=len(resources),
            metric_count=len(cpu_metrics),
            cost_day_count=len(daily_costs),
            resources=resources,
            cpu_metrics=cpu_metrics,
            daily_costs=daily_costs,
            issues=issues,
        )
