# CloudCare Cost Audit Report Template

Use this template for monthly, quarterly, or demo audit reporting of costs and savings captured by CloudCare. Replace bracketed values before sharing with finance, security, or leadership.

---

## 1. Report Metadata

| Field | Value |
|---|---|
| Report name | CloudCare Cost Optimization Audit |
| Reporting period | [YYYY-MM-DD] to [YYYY-MM-DD] |
| Prepared for | [Organization / Team] |
| Prepared by | CloudCare / [Owner name] |
| Tenant ID | [tenant_id] |
| Cloud account(s) | [AWS account / Azure subscription / VPS host] |
| Region(s) | [ap-south-1, global, etc.] |
| Report generated at | [timestamp with timezone] |
| Data source | [FOCUS live export / synthesized from CloudSnapshot / sample / modelled] |
| FOCUS version | [1.2] |

---

## 2. Executive Summary

During this reporting period, CloudCare monitored [resource_count] resources across [provider_count] provider(s), analyzed [focus_row_count] FOCUS cost rows, and produced [finding_count] optimization or governance findings.

| Metric | Value |
|---|---:|
| Total observed cost | $[total_cost_usd] |
| Total observed cost in INR | ₹[total_cost_inr] |
| Potential monthly savings identified | $[potential_monthly_savings_usd] |
| Annualized potential savings | $[annualized_potential_savings_usd] |
| Approved monthly savings | $[approved_monthly_savings_usd] |
| Executed or simulated savings | $[executed_monthly_savings_usd] |
| Pending approval savings | $[pending_monthly_savings_usd] |
| Blocked or refused savings | $[blocked_monthly_savings_usd] |

**Audit conclusion:** [Example: CloudCare identified material optimization opportunities, routed all risky actions through human approval, and preserved evidence for each decision.]

---

## 3. Cost Baseline

| Provider | Account / Subscription | Service category | Service name | Environment | Cost USD | Cost INR | Source |
|---|---|---|---|---|---:|---:|---|
| AWS | [account_id] | Compute | EC2 | development | $[amount] | ₹[amount] | [FOCUS live/synthesized] |
| AWS | [account_id] | Databases | RDS PostgreSQL | development | $[amount] | ₹[amount] | [FOCUS live/synthesized] |
| AWS | [account_id] | Databases | DynamoDB | development | $[amount] | ₹[amount] | [FOCUS live/synthesized] |

**Cost notes:**
- Currency stored by CloudCare: USD.
- INR is display-only, calculated using `USD_TO_INR=[rate]`.
- If source is `synthesized`, costs are allocated from account-level Cost Explorer totals and should be treated as directional per-resource estimates.
- If source is `modelled`, costs are internally allocated from a fixed monthly input, such as VPS monthly cost.

---

## 4. Resource Inventory Snapshot

| Resource type | Count | Key examples | Collection source |
|---|---:|---|---|
| EC2 instances | [count] | [i-...] | `cloud_snapshots.resources` |
| EBS volumes | [count] | [vol-...] | `cloud_snapshots.resources` |
| RDS instances | [count] | [db identifier] | `cloud_snapshots.resources` |
| DynamoDB tables | [count] | [table name] | `cloud_snapshots.resources` |
| Lambda functions | [count] | [function name] | `cloud_snapshots.resources` |
| VPCs | [count] | [vpc-...] | `cloud_snapshots.resources` |
| Security groups | [count] | [sg-...] | `cloud_snapshots.resources` |
| S3 buckets | [count] | [bucket] | `cloud_snapshots.resources` |

**Collection issues:**

| Source | Error type | Message | Retryable |
|---|---|---|---|
| [iam/sqs/etc.] | [AccessDenied/etc.] | [message] | [true/false] |

---

## 5. Findings Summary

| Rule ID | Severity | Count | Savings type | Notes |
|---|---:|---:|---|---|
| `ec2.idle.v1` | medium | [count] | billable | Low CPU and low network activity |
| `ec2.overprovisioned.v1` | low | [count] | billable | Low utilization with excess headroom |
| `ebs.unattached.v1` | low | [count] | billable | Detached volume cleanup candidate |
| `cost.anomaly.v1` | high | [count] | billable | Cost spike against trailing baseline |
| `rds.single_az.v1` | medium | [count] | governance | RDS availability risk |
| `rds.unencrypted.v1` | medium | [count] | governance | Encryption-at-rest gap |
| `rds.deletion_protection_disabled.v1` | medium | [count] | governance | Accidental deletion risk |
| `dynamodb.pitr_disabled.v1` | medium | [count] | governance | Recovery-point risk |
| `lambda.long_timeout.v1` | low | [count] | governance | Runtime/cost control review |
| `sg.open_ingress.v1` | high/critical | [count] | security | Sensitive port exposed publicly |

---

## 6. Detailed Findings

Repeat this section for each material finding.

### Finding [N]: [rule_id] on [resource_id]

| Field | Value |
|---|---|
| Resource ID | [resource_id] |
| Resource type | [resource_type] |
| Provider / region | [provider] / [region] |
| Environment | [development/staging/production/unknown] |
| Severity | [low/medium/high/critical] |
| Confidence | [0.00-1.00] |
| Estimated monthly savings | $[amount] |
| Annualized savings | $[amount] |
| Finding source | `analyzer_findings` |
| FOCUS dataset ID | [focus_dataset_id] |

**Evidence:**

| Metric / fact | Value | Source |
|---|---:|---|
| [cpu_p95/storage_encrypted/port/etc.] | [value] | [FOCUS column / AWS API field] |

**Decision rationale:**  
[Plain-English rationale from Decision Agent.]

**Risk notes:**  
[Supervisor risk notes, dependency context, or policy reason codes.]

---

## 7. Proposals and Approval Trail

| Proposal ID | Resource | Action | Template | Savings/mo | Risk | Status | Human approval required | Policy outcome |
|---|---|---|---|---:|---|---|---|---|
| [proposal_id] | [resource_id] | [action_type] | [template_id] | $[amount] | [low/medium/high] | [status] | [true/false] | [needs_approval/blocked] |

**Approval evidence:**

| Proposal ID | Approved / rejected by | Via | Timestamp | Notes |
|---|---|---|---|---|
| [proposal_id] | [user_id/email] | [dashboard/email] | [timestamp] | [reason] |

Collections to reference:
- `proposals`
- `supervisor_reviews`
- `approval_tokens`
- `agent_command_runs`

---

## 8. Execution and Verification Trail

| Execution ID | Proposal ID | Action | Mode | Status | AWS call made | Before state | After state | Reason codes |
|---|---|---|---|---|---|---|---|---|
| [execution_id] | [proposal_id] | [stop_instance/delete_volume/etc.] | [simulation/live] | [executed/refused/blocked/no_op] | [true/false] | [summary] | [summary] | [codes] |

**Execution controls:**
- `EXECUTION_ENABLED`: [true/false]
- `EXECUTION_MODE`: [simulation/live]
- Required allowlist tag: `cloudcare:managed=true`
- Write role: [AWS_WRITE_ROLE_ARN or not configured]
- SQS enabled: [true/false]
- SQS queue status: [running / blocked by IAM / disabled]

---

## 9. Email Notification Evidence

| Notification type | Recipient | Provider | Sent | Timestamp | Reason / error |
|---|---|---|---|---|---|
| Agent command analysis | [masked email] | Brevo | [true/false] | [timestamp] | [reason] |
| Approval request | [masked email] | Brevo | [true/false] | [timestamp] | [reason] |
| Execution completion | [masked email] | Brevo | [true/false] | [timestamp] | [reason] |

**Email controls checked:**
- Brevo API key configured: [yes/no]
- SMTP fallback configured: [yes/no]
- Sender verified: [yes/no]
- Recipient source: [current user / tenant user fallback]

---

## 10. Savings Ledger

| Category | Monthly USD | Annual USD | Status |
|---|---:|---:|---|
| Identified savings | $[amount] | $[amount] | Findings created |
| Proposed savings | $[amount] | $[amount] | Decision Agent created proposal |
| Approved savings | $[amount] | $[amount] | Human approved |
| Executed or simulated savings | $[amount] | $[amount] | Executor completed |
| Refused / blocked savings | $[amount] | $[amount] | Policy or executor blocked |
| Pending savings | $[amount] | $[amount] | Awaiting approval |

**Savings recognition policy:**
- Potential savings are not booked until a proposal is approved.
- Executed savings are not treated as realized until verification confirms the expected resource state or billing reduction.
- Audit-only findings such as RDS encryption, DynamoDB PITR, and security-group ingress use `$0` savings unless a separate migration or remediation estimate is approved.

---

## 11. Risk and Governance Notes

| Control | Status | Evidence |
|---|---|---|
| LLM cannot choose executable templates directly | [pass/fail] | Decision uses deterministic template map |
| Production requires human approval | [pass/fail] | Policy outcome / supervisor review |
| Missing owner tag forces review | [pass/fail] | Dependency context / tags |
| Protected resources blocked | [pass/fail] | Policy reason codes |
| Live execution requires allowlist tag | [pass/fail] | Executor refusal or action record |
| Email approval links are signed | [pass/fail] | Approval token record |
| SQS execution queue is permissioned | [pass/fail] | SQS status / IAM policy |

---

## 12. Data Export Checklist

Attach or link the following evidence when filing the audit:

- [ ] `agent_command_runs` record for the reporting run.
- [ ] Latest `cloud_snapshots` document.
- [ ] FOCUS dataset metadata and row count.
- [ ] `analyzer_findings` export.
- [ ] `decision_proposals` export.
- [ ] `proposals` export with statuses.
- [ ] `supervisor_reviews` export.
- [ ] `execution_audit` export.
- [ ] Email receipt/status evidence.
- [ ] Any IAM/SQS/CORS/deployment exceptions discovered during the period.

---

## 13. Final Sign-Off

| Role | Name | Decision | Date |
|---|---|---|---|
| FinOps owner | [name] | [approved/rejected] | [date] |
| Engineering owner | [name] | [approved/rejected] | [date] |
| Security owner | [name] | [approved/rejected] | [date] |
| Finance owner | [name] | [approved/rejected] | [date] |

**Final remarks:**  
[Summarize what was saved, what is pending, what was blocked, and what must be fixed before the next audit cycle.]
