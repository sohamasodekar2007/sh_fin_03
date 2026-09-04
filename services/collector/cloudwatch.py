"""
CloudWatch metrics collector — PLACEHOLDER.

TODO: implement using boto3's CloudWatch GetMetricData API (blueprint 9,
research & references section 2). Pull CPUUtilization and NetworkIn/Out for
each instance over a 7-14 day window, matching the evidence window used by
classify_idle() in app/services/analyzer/rules.py.
"""


def get_cpu_utilization(session, instance_id: str, region: str, days: int = 14) -> list[dict]:
    raise NotImplementedError(
        "Wire this up to CloudWatch's GetMetricData API once a real AWS "
        "sandbox account is connected."
    )
