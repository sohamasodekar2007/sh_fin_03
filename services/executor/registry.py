"""
Executor template registry — lifted from blueprint section 10.1.

This is real, working validation logic (no AWS dependency). The actual
`stop_instance` boto3 call (blueprint 10.2) is a placeholder in actions.py
since it needs a real AWS session — but the registry + validation here you
can use and test immediately.
"""


class SecurityError(Exception):
    pass


class ValidationError(Exception):
    pass


ACTION_REGISTRY = {
    "ec2.stop.v1": {
        "allowed_action": "stop_instance",
        "required_params": {"instance_id": str, "region": str},
        "rollback_template": "ec2.start.v1",
        "max_risk": "low",
    },
    "ec2.start.v1": {
        "allowed_action": "start_instance",
        "required_params": {"instance_id": str, "region": str},
        "rollback_template": None,
        "max_risk": "low",
    },
    "ec2.resize.v1": {
        "allowed_action": "resize_instance",
        "required_params": {"instance_id": str, "region": str, "target_type": str},
        "rollback_template": "ec2.resize.v1",
        "max_risk": "medium",
    },
}


def validate_action(template_id: str, parameters: dict, policy_approved: bool) -> dict:
    template = ACTION_REGISTRY.get(template_id)
    if not template:
        raise SecurityError(f"Unknown action template: {template_id}")
    if not policy_approved:
        raise SecurityError("Policy denied this action")
    if set(parameters.keys()) != set(template["required_params"].keys()):
        raise ValidationError("Unexpected or missing action parameters")
    return template
