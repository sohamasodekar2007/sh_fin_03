"""
Cost Explorer collector — PLACEHOLDER.

TODO: implement using boto3's Cost Explorer GetCostAndUsage API. Note from
the blueprint / earlier project discussion: Cost Explorer data can lag
several hours behind CloudWatch, so cache results and consider an
estimated-cost fallback (instance type x hours running) for live demos.
"""


def get_cost_and_usage(session, start_date: str, end_date: str) -> list[dict]:
    raise NotImplementedError(
        "Wire this up to AWS Cost Explorer's GetCostAndUsage API once a "
        "real AWS sandbox account is connected."
    )
