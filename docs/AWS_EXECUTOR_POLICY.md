# CloudCare Executor AWS Policy

Use a dedicated write role for the Executor Agent. Do not reuse the read role
used by collectors, and do not use root or long-lived admin keys for execution.

Runtime gates in `services/executor/actions.py` still apply even when this role
exists:

- `EXECUTION_ENABLED=true`
- `EXECUTION_MODE=live`
- proposal status must be `approved`
- live AWS tags are re-read immediately before mutation
- the target resource must have `cloudcare:managed=true` or the configured
  `EXECUTION_ALLOWLIST_TAG`

## Trust Policy

Set the trusted principal to the identity that runs the API, and keep the
external ID aligned with `AWS_EXTERNAL_ID`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<account-id>:user/<cloudcare-api-user>"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<AWS_EXTERNAL_ID>"
        }
      }
    }
  ]
}
```

## Permission Policy

This is intentionally narrower than `AmazonEC2FullAccess`. It covers the
current Executor actions: stop/start, resize, schedule tag, snapshot, and
delete detached volumes.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCurrentStateBeforeExecution",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeVolumes",
        "ec2:DescribeSnapshots",
        "ec2:DescribeTags",
        "cloudwatch:DescribeAlarms"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ManageAllowlistedInstances",
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:ModifyInstanceAttribute",
        "ec2:CreateTags"
      ],
      "Resource": "arn:aws:ec2:*:<account-id>:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/cloudcare:managed": "true"
        }
      }
    },
    {
      "Sid": "SnapshotAllowlistedVolumesBeforeDelete",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateSnapshot"
      ],
      "Resource": "arn:aws:ec2:*:<account-id>:volume/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/cloudcare:managed": "true"
        }
      }
    },
    {
      "Sid": "DeleteAllowlistedDetachedVolumes",
      "Effect": "Allow",
      "Action": [
        "ec2:DeleteVolume"
      ],
      "Resource": "arn:aws:ec2:*:<account-id>:volume/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/cloudcare:managed": "true"
        }
      }
    },
    {
      "Sid": "TagExecutorSnapshots",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags"
      ],
      "Resource": "arn:aws:ec2:*:<account-id>:snapshot/*"
    }
  ]
}
```

## Live Switch

After simulation passes, restart the API with:

```env
EXECUTION_ENABLED=true
EXECUTION_MODE=live
AWS_WRITE_ROLE_ARN=arn:aws:iam::<account-id>:role/CloudCareExecutorRole
EXECUTION_ALLOWLIST_TAG=cloudcare:managed=true
```

Only resources carrying the allowlist tag can be changed.
